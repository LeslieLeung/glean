#!/usr/bin/env python3
"""Migrate a local Glean Compose deployment without changing its original volumes.

Only Python's standard library and Docker Compose V2 are required. Run --help for
usage. Configuration snapshots contain credentials and are kept in a private,
ignored state directory. No application credentials are passed through a shell.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

CORE_SERVICES = {"postgres", "redis", "backend", "worker", "web", "admin"}
MILVUS_SERVICES = {"milvus", "milvus-etcd", "milvus-minio"}
APP_REPOSITORIES = {
    "backend": "ghcr.io/leslieleung/glean-backend",
    "worker": "ghcr.io/leslieleung/glean-backend",
    "web": "ghcr.io/leslieleung/glean-web",
    "admin": "ghcr.io/leslieleung/glean-admin",
}
PHASES = ("prepared", "pulled", "quiesced", "backed_up", "old_stopped", "restored", "complete")
COUNT_SQL = (
    " UNION ALL ".join(
        f"SELECT '{table}', count(*) FROM {table}"
        for table in ("users", "subscriptions", "entries", "bookmarks", "user_entries")
    )
    + " ORDER BY 1"
)
EMBEDDING_SQL = "SELECT COALESCE(value->>'status', '') FROM system_configs WHERE key='embedding'"
PG_SHELL = 'exec "$@" -U "$POSTGRES_USER" -d "$POSTGRES_DB"'


class MigrationError(Exception):
    """A failed prerequisite or consistency check."""


def run(
    args: list[str],
    *,
    capture: bool = False,
    input_file: BinaryIO | None = None,
    output_file: BinaryIO | None = None,
) -> str:
    result = subprocess.run(
        args,
        check=True,
        stdin=input_file,
        stdout=subprocess.PIPE if capture else output_file,
    )
    return result.stdout.decode().strip() if capture else ""


def save_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def compose_dollars(value: Any, *, escape: bool) -> Any:
    """Compose config output escapes dollar signs; decode on read, encode on save."""
    if isinstance(value, str):
        return value.replace("$", "$$") if escape else value.replace("$$", "$")
    if isinstance(value, list):
        return [compose_dollars(item, escape=escape) for item in value]
    if isinstance(value, dict):
        return {key: compose_dollars(item, escape=escape) for key, item in value.items()}
    return value


def data_mount(config: dict[str, Any], service: str, target: str) -> dict[str, Any]:
    mounts = [
        mount
        for mount in config["services"][service].get("volumes", [])
        if mount["target"] == target
    ]
    if len(mounts) != 1 or mounts[0].get("type") != "volume":
        raise MigrationError(f"{service} must use a named volume at {target}; migrate manually.")
    return mounts[0]


def make_target(
    source: dict[str, Any], image_tag: str, volume_names: dict[str, str]
) -> dict[str, Any]:
    target = copy.deepcopy(source)
    for service in MILVUS_SERVICES:
        target["services"].pop(service, None)
    for name, service in target["services"].items():
        service.pop("build", None)
        service.pop("pull_policy", None)
        dependencies = service.get("depends_on", {})
        service["depends_on"] = {
            key: value for key, value in dependencies.items() if key not in MILVUS_SERVICES
        }
        if name in APP_REPOSITORIES:
            service["image"] = f"{APP_REPOSITORIES[name]}:{image_tag}"
        if name in {"backend", "worker"}:
            environment = service.setdefault("environment", {})
            environment["VECTOR_BACKEND"] = "pgvector"
            environment["PGVECTOR_DATABASE_URL"] = ""
            environment["RUN_MIGRATIONS"] = "true" if name == "backend" else "false"
            for key in ("MILVUS_HOST", "MILVUS_PORT", "MILVUS_USER", "MILVUS_PASSWORD"):
                environment.pop(key, None)
    target["services"]["postgres"]["image"] = "pgvector/pgvector:pg16"
    # The image's temporary init server accepts Unix-socket connections before
    # initialization finishes. TCP only becomes available on the final server.
    target["services"]["postgres"].setdefault("healthcheck", {})["test"] = [
        "CMD-SHELL",
        'pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
    ]
    target["services"]["worker"].setdefault("depends_on", {})["backend"] = {
        "condition": "service_healthy"
    }
    for service, mount_path in (("postgres", "/var/lib/postgresql/data"), ("redis", "/data")):
        mount = data_mount(target, service, mount_path)
        mount["source"] = f"pgvector_{service}"
        target.setdefault("volumes", {})[mount["source"]] = {"name": volume_names[service]}
    # Drop unused declarations, so the active configuration references no old data volumes.
    used_volumes = {
        mount["source"]
        for service in target["services"].values()
        for mount in service.get("volumes", [])
        if mount.get("type") == "volume"
    }
    target["volumes"] = {
        key: value for key, value in target["volumes"].items() if key in used_volumes
    }
    return target


class Migration:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.state_path = directory / "state.json"
        self.state: dict[str, Any] = (
            json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        )

    def compose(self, target: bool, *args: str, **kwargs: Any) -> str:
        filename = "pgvector.compose.json" if target else "original.compose.json"
        return run(
            [
                "docker",
                "compose",
                "--project-directory",
                self.state["deployment_directory"],
                "--project-name",
                self.state["project"],
                "-f",
                str(self.directory / filename),
                *args,
            ],
            **kwargs,
        )

    def advance(self, phase: str) -> None:
        self.state["phase"] = phase
        save_json(self.state_path, self.state)
        print(f"Migration phase: {phase}", flush=True)

    def inspect_service(self, target: bool, service: str) -> dict[str, Any]:
        container = self.compose(target, "ps", "-a", "-q", service, capture=True)
        if not container or "\n" in container:
            raise MigrationError(f"Expected one existing container for {service}.")
        return json.loads(run(["docker", "inspect", container], capture=True))[0]

    def assert_mount(self, target: bool, service: str, path: str, expected: str) -> None:
        mounts = [
            mount
            for mount in self.inspect_service(target, service)["Mounts"]
            if mount["Destination"] == path
        ]
        if len(mounts) != 1 or mounts[0].get("Name") != expected:
            raise MigrationError(f"Unexpected {service} data volume; stopped to protect old data.")

    def pg(self, target: bool, executable: str, *args: str, **kwargs: Any) -> str:
        return self.compose(
            target,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            PG_SHELL,
            "sh",
            executable,
            *args,
            **kwargs,
        )

    def sql(self, target: bool, query: str) -> str:
        return self.pg(target, "psql", "-At", "-v", "ON_ERROR_STOP=1", "-c", query, capture=True)

    def prepare(self, args: argparse.Namespace) -> None:
        if not args.image_tag or not re.fullmatch(r"[\w][\w.-]{0,127}", args.image_tag, re.ASCII):
            raise MigrationError("Supply --image-tag with a published pgvector release image tag.")
        if args.image_tag == "latest":
            raise MigrationError("Use a fixed release image tag instead of latest.")
        command = ["docker", "compose"]
        if args.project_name:
            command.extend(["--project-name", args.project_name])
        if args.env_file:
            command.extend(["--env-file", str(Path(args.env_file).resolve())])
        for filename in args.compose or ["docker-compose.yml"]:
            command.extend(["-f", str(Path(filename).resolve())])
        source = compose_dollars(
            json.loads(run([*command, "config", "--format", "json"], capture=True)), escape=False
        )
        services = set(source["services"])
        if not services >= CORE_SERVICES or services - CORE_SERVICES - MILVUS_SERVICES:
            raise MigrationError("Only the six standard Glean services and Milvus are supported.")
        if any(service.get("profiles") for service in source["services"].values()):
            raise MigrationError("Compose profiles are not supported; migrate manually.")
        containers: dict[str, dict[str, Any]] = {}
        for name in sorted(services):
            container = run([*command, "ps", "-a", "-q", name], capture=True)
            if not container or "\n" in container:
                raise MigrationError(f"Start the existing {name} service before migrating.")
            inspected = json.loads(run(["docker", "inspect", container], capture=True))[0]
            if not inspected["State"]["Running"]:
                raise MigrationError(f"The existing {name} service must be running.")
            if inspected["Config"]["Labels"].get("com.docker.compose.project") != source["name"]:
                raise MigrationError("The running containers do not match this Compose project.")
            containers[name] = inspected
        for name in ("postgres", "backend", "worker"):
            environment = source["services"][name].get("environment", {})
            live = dict(item.split("=", 1) for item in containers[name]["Config"]["Env"])
            keys = (
                ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
                if name == "postgres"
                else ("DATABASE_URL", "REDIS_URL", "SECRET_KEY")
            )
            if any(
                not environment.get(key) or str(environment[key]) != live.get(key) for key in keys
            ):
                raise MigrationError(f"The {name} environment differs from the running deployment.")
            if name != "postgres" and live.get("VECTOR_BACKEND", "milvus").lower() != "milvus":
                raise MigrationError("The running application is not using Milvus.")
            if (
                name != "postgres"
                and environment.get("VECTOR_BACKEND", "milvus").lower() != "milvus"
            ):
                raise MigrationError("The original Compose configuration must still select Milvus.")
        database = source["services"]["postgres"]["environment"]["POSTGRES_DB"]
        if database in {"postgres", "template0", "template1"}:
            raise MigrationError(
                "Use a dedicated application database, not a PostgreSQL system DB."
            )
        for name in ("backend", "worker"):
            environment = source["services"][name]["environment"]
            url = urlparse(environment["DATABASE_URL"])
            redis = urlparse(environment["REDIS_URL"])
            if (
                url.hostname != "postgres"
                or url.port not in {None, 5432}
                or unquote(url.path.removeprefix("/")) != database
                or redis.hostname != "redis"
                or redis.port not in {None, 6379}
            ):
                raise MigrationError(
                    "External PostgreSQL/Redis connections require manual migration."
                )
        original_volumes = {}
        for name, path in (("postgres", "/var/lib/postgresql/data"), ("redis", "/data")):
            mount = data_mount(source, name, path)
            expected = source["volumes"][mount["source"]]["name"]
            live_mounts = [m for m in containers[name]["Mounts"] if m["Destination"] == path]
            if len(live_mounts) != 1 or live_mounts[0].get("Name") != expected:
                raise MigrationError(f"The {name} Compose volume differs from its running volume.")
            original_volumes[name] = expected
        for name in ("postgres", "redis", "backend"):
            healthcheck = source["services"][name].get("healthcheck", {})
            if not healthcheck.get("test") or healthcheck.get("disable"):
                raise MigrationError(f"The {name} service must have a healthcheck.")
        version = run(
            [
                *command,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                PG_SHELL,
                "sh",
                "psql",
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "SHOW server_version_num",
            ],
            capture=True,
        )
        if not 160000 <= int(version) < 170000:
            raise MigrationError("This script supports PostgreSQL 16 only.")
        embedding = run(
            [
                *command,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                PG_SHELL,
                "sh",
                "psql",
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                EMBEDDING_SQL,
            ],
            capture=True,
        )
        if embedding in {"validating", "rebuilding"}:
            raise MigrationError("Wait for the existing embedding validation/rebuild to finish.")
        print(f"Project: {source['name']}; PostgreSQL 16; target image tag: {args.image_tag}")
        print("A fresh PostgreSQL volume and Redis queue will be used; old volumes are retained.")
        if args.dry_run:
            print(
                "Dry run complete. No services, images, volumes, or migration state were changed."
            )
            return
        identifier = secrets.token_hex(6)
        volume_names = {
            name: f"{source['name']}_pgvector_{identifier}_{name}" for name in ("postgres", "redis")
        }
        rollback = copy.deepcopy(source)
        for name, inspected in containers.items():
            tag = f"glean-rollback/{source['name']}-{name}:{identifier}"
            run(["docker", "image", "tag", inspected["Image"], tag])
            rollback["services"][name]["image"] = tag
            rollback["services"][name].pop("build", None)
            rollback["services"][name].pop("pull_policy", None)
        save_json(self.directory / "original.compose.json", compose_dollars(rollback, escape=True))
        save_json(
            self.directory / "pgvector.compose.json",
            compose_dollars(make_target(source, args.image_tag, volume_names), escape=True),
        )
        self.state = {
            "project": source["name"],
            "deployment_directory": str(Path.cwd()),
            "image_tag": args.image_tag,
            "volume_names": volume_names,
            "original_volume_names": original_volumes,
            "skip_pull": args.skip_pull,
        }
        self.compose(True, "config", "--quiet")
        self.advance("prepared")

    def migrate(self) -> None:
        if self.state["phase"] not in PHASES:
            raise MigrationError("Rollback has started; finish rollback before a new migration.")
        if self.state["phase"] == "prepared":
            if self.state["skip_pull"]:
                images = self.compose(True, "config", "--images", capture=True).splitlines()
                for image in sorted(set(images)):
                    run(["docker", "image", "inspect", image], capture=True)
            else:
                self.compose(True, "pull")
            self.advance("pulled")
        if self.state["phase"] == "pulled":
            print("Stopping application writes for the database backup.", flush=True)
            self.compose(False, "stop", "-t", "120", "web", "admin", "backend", "worker")
            # Check again after stopping writes to close the preflight race.
            if self.sql(False, EMBEDDING_SQL) in {"validating", "rebuilding"}:
                raise MigrationError(
                    "An embedding rebuild started; run rollback and let it finish."
                )
            self.advance("quiesced")
        if self.state["phase"] == "quiesced":
            for name, path in (("postgres", "/var/lib/postgresql/data"), ("redis", "/data")):
                self.assert_mount(False, name, path, self.state["original_volume_names"][name])
            temporary = self.directory / "database.dump.partial"
            with temporary.open("wb") as stream:
                self.pg(False, "pg_dump", "-Fc", output_file=stream)
            with temporary.open("rb") as stream:
                self.compose(
                    False,
                    "exec",
                    "-T",
                    "postgres",
                    "pg_restore",
                    "--list",
                    input_file=stream,
                    capture=True,
                )
            counts = self.sql(False, COUNT_SQL)
            save_json(self.directory / "counts.json", counts)
            temporary.replace(self.directory / "database.dump")
            self.advance("backed_up")
        if self.state["phase"] == "backed_up":
            self.compose(False, "down", "--timeout", "120")
            self.advance("old_stopped")
        if self.state["phase"] == "old_stopped":
            self.compose(True, "up", "-d", "--wait", "--wait-timeout", "300", "postgres", "redis")
            for name, path in (("postgres", "/var/lib/postgresql/data"), ("redis", "/data")):
                self.assert_mount(True, name, path, self.state["volume_names"][name])
            # Until the restored checkpoint, no new application has been started.
            # Reset only this verified, dedicated target DB so partial restores can resume.
            self.compose(
                True,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'exec dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB"',
            )
            self.compose(
                True,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'exec createdb -U "$POSTGRES_USER" -T template0 "$POSTGRES_DB"',
            )
            with (self.directory / "database.dump").open("rb") as stream:
                self.pg(
                    True,
                    "pg_restore",
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                    "--single-transaction",
                    input_file=stream,
                )
            if self.sql(True, COUNT_SQL) != json.loads(
                (self.directory / "counts.json").read_text()
            ):
                raise MigrationError("Restored business-table counts do not match the backup.")
            self.sql(True, "CREATE EXTENSION IF NOT EXISTS vector")
            self.advance("restored")
        if self.state["phase"] == "restored":
            self.compose(True, "up", "-d", "--wait", "--wait-timeout", "300")
            self.advance("complete")
        print("Migration complete. Check Admin > Settings > Embedding until idle.")
        print("Embedding regeneration runs in the background and may incur provider charges.")
        print(f"Backups and active Compose configuration: {self.directory}")

    def rollback(self) -> None:
        phase = self.state["phase"]
        if phase == "rolled_back":
            print("Already rolled back.")
            return
        if phase != "rollback_started":
            self.state["rollback_from"] = phase
            self.advance("rollback_started")
        print("Restoring the pre-migration deployment. New pgvector writes remain in its volume.")
        if PHASES.index(self.state["rollback_from"]) >= PHASES.index("old_stopped"):
            self.compose(True, "down", "--timeout", "120")
        self.compose(False, "up", "-d", "--wait", "--wait-timeout", "300", "--pull", "never")
        self.advance("rolled_back")
        print("Rollback complete. Original images, PostgreSQL, Redis, and Milvus are active.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state-dir", type=Path, default=Path(".glean-pgvector-migration"))
    commands = result.add_subparsers(dest="action", required=True)
    migrate = commands.add_parser("migrate", help="Migrate, or resume an interrupted migration")
    migrate.add_argument(
        "--image-tag", help="Published release image tag, required for a new migration"
    )
    migrate.add_argument(
        "--compose", action="append", help="Original Compose file; repeat for overrides"
    )
    migrate.add_argument(
        "--env-file", help="Original env file (default: Compose's normal .env loading)"
    )
    migrate.add_argument("--project-name", help="Original Compose project name, if customized")
    migrate.add_argument("--dry-run", action="store_true", help="Read-only prerequisite checks")
    migrate.add_argument("--skip-pull", action="store_true", help="Use already downloaded images")
    commands.add_parser("rollback", help="Restore the original images and volumes")
    commands.add_parser("status", help="Show the saved migration phase")
    compose = commands.add_parser(
        "compose", help="Run Compose against the active saved configuration"
    )
    compose.add_argument("arguments", nargs=argparse.REMAINDER)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    os.umask(0o077)
    directory = args.state_dir.resolve()
    try:
        run(["docker", "compose", "version"], capture=True)
        migration = Migration(directory)
        if args.action == "migrate" and args.dry_run:
            if migration.state:
                raise MigrationError("Migration state already exists; use status to inspect it.")
            migration.prepare(args)
            return 0
        if args.action != "migrate" and not migration.state:
            raise MigrationError("No saved migration was found in this state directory.")
        if args.action == "status":
            print(f"Project: {migration.state['project']}")
            print(f"Image tag: {migration.state['image_tag']}")
            print(f"Phase: {migration.state['phase']}")
            print(f"State and backups: {directory}")
            return 0
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (directory / "lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise MigrationError("Another migration command is already running.") from error
            # Reload after acquiring the lock; another process may just have finished.
            migration = Migration(directory)
            if args.action == "migrate":
                if not migration.state:
                    migration.prepare(args)
                elif args.image_tag and args.image_tag != migration.state["image_tag"]:
                    raise MigrationError(
                        "Resume with the saved image tag; it cannot change mid-migration."
                    )
                migration.migrate()
            elif args.action == "rollback":
                migration.rollback()
            else:
                arguments = args.arguments
                if arguments[:1] == ["--"]:
                    arguments = arguments[1:]
                if not arguments:
                    raise MigrationError("Supply a Compose command, such as compose ps.")
                phase = migration.state["phase"]
                if phase not in {"complete", "rolled_back"}:
                    raise MigrationError(
                        "Finish migration/rollback before using the compose helper."
                    )
                migration.compose(phase == "complete", *arguments)
    except (MigrationError, OSError, ValueError, subprocess.CalledProcessError) as error:
        # CalledProcessError includes argv; keep resolved credentials out of diagnostics.
        message = (
            f"Docker command failed (exit {error.returncode})."
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        print(f"Error: {message}", file=sys.stderr)
        if (directory / "state.json").exists():
            print(
                "Saved state retained. Fix the error and rerun migrate, or run rollback.",
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        print(
            "Interrupted. Saved checkpoints are retained; rerun migrate or rollback.",
            file=sys.stderr,
        )
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
