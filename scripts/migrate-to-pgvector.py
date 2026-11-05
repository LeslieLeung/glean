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
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
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
DEFAULT_COMPOSE_FILES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "compose.override.yaml",
    "compose.override.yml",
    "docker-compose.override.yaml",
    "docker-compose.override.yml",
)


class MigrationError(Exception):
    """A failed prerequisite or consistency check."""


def run(
    args: list[str],
    *,
    capture: bool = False,
    input_file: BinaryIO | None = None,
    output_file: BinaryIO | None = None,
    environment: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        args,
        check=True,
        stdin=input_file,
        stdout=subprocess.PIPE if capture else output_file,
        env=environment,
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


def save_bytes(path: Path, value: bytes, mode: int = 0o600) -> None:
    temporary = path.with_name(path.name + ".pgvector.tmp")
    with temporary.open("wb") as stream:
        os.chmod(temporary, mode)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def file_digest(path: Path) -> str | None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise MigrationError(f"Expected a regular deployment file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def yaml_block(lines: list[str], path: tuple[str, ...]) -> tuple[int, int]:
    """Locate a mapping block in our template or Compose's canonical YAML output."""
    start, end = 0, len(lines)
    for depth, key in enumerate(path):
        indent = depth * 2
        pattern = re.compile(rf"^{' ' * indent}{re.escape(key)}:")
        found = next((i for i in range(start, end) if pattern.match(lines[i])), None)
        if found is None:
            return end, end
        start = found
        end = next(
            (
                i
                for i in range(start + 1, end)
                if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= indent
            ),
            end,
        )
    return start, end


def patch_yaml(
    document: str, rendered: str, path: tuple[str, ...], *, remove_if_missing: bool = False
) -> str:
    """Copy only a changed field, leaving the template's other text untouched."""
    lines, source = document.splitlines(keepends=True), rendered.splitlines(keepends=True)
    start, end = yaml_block(lines, path)
    first, last = yaml_block(source, path)
    if first == last and not remove_if_missing:
        raise MigrationError(f"Cannot locate Compose field: {'.'.join(path)}")
    lines[start:end] = source[first:last]
    return "".join(lines)


def update_dotenv(document: str, values: dict[str, str]) -> str:
    """Update assignments without leaving stale duplicates or losing other settings."""
    pending = dict(values)
    assignment = re.compile(
        r"""(?m)^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*"""
        r"""(?:"(?:[^"\\]|\\[\s\S])*"|'(?:[^'\\]|\\[\s\S])*'|[^\r\n]*)[ \t]*(?:\#[^\r\n]*)?$"""
    )

    def replace(match: re.Match[str]) -> str:
        key = match[1]
        if key not in values:
            return match[0]
        if key not in pending:
            return ""
        value = pending.pop(key)
        return f"{key}={json.dumps(value.replace('$', '$$'), ensure_ascii=False)}"

    result = assignment.sub(replace, document).rstrip() + "\n"
    if pending:
        result += "\n# Updated by migrate-to-pgvector.py finalize.\n"
        result += "".join(
            f"{key}={json.dumps(value.replace('$', '$$'), ensure_ascii=False)}\n"
            for key, value in sorted(pending.items())
        )
    return result


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
            "source_files": [
                os.path.abspath(name) for name in args.compose or ["docker-compose.yml"]
            ],
            "env_files": [os.path.abspath(args.env_file)] if args.env_file else [],
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
        print("After verifying the migration, run finalize to install ordinary Compose files.")

    def deployment_files(self) -> dict[str, bytes | None]:
        """Only these default entry points are replaced; custom inputs are archived."""
        files: dict[str, bytes | None] = dict.fromkeys(DEFAULT_COMPOSE_FILES)
        files["docker-compose.yml"] = (self.directory / "deployment.compose.yml").read_bytes()
        files[".env"] = (self.directory / "deployment.env").read_bytes()
        return files

    def prepare_deployment(self, args: argparse.Namespace) -> None:
        """Keep the release template and its variables; patch deployment-specific fields."""
        output = self.directory / "deployment.compose.yml"
        env_path = self.directory / "deployment.env"
        prepared = self.directory / "deployment-files.json"
        if prepared.exists():
            expected = json.loads(prepared.read_text())
            if expected != {"compose": file_digest(output), "env": file_digest(env_path)}:
                raise MigrationError(
                    "Prepared deployment files changed; restore them before retrying."
                )
            return
        template_path = (
            args.template or Path(__file__).resolve().parents[1] / "docker-compose.pgvector.yml"
        )
        if not template_path.is_file():
            raise MigrationError(
                "Download the release's docker-compose.pgvector.yml or supply finalize --template PATH."
            )
        template = template_path.read_text()
        target = compose_dollars(
            json.loads((self.directory / "pgvector.compose.json").read_text()), escape=False
        )
        target["name"] = self.state["project"]
        # Reuse the template's logical volume keys while keeping the actual new volumes.
        for service, logical, mount_path in (
            ("postgres", "postgres_data", "/var/lib/postgresql/data"),
            ("redis", "redis_data", "/data"),
        ):
            mount = data_mount(target, service, mount_path)
            old_key = mount["source"]
            if old_key != logical:
                target["volumes"][logical] = target["volumes"].pop(old_key)
                for config in target["services"].values():
                    for item in config.get("volumes", []):
                        if item.get("type") == "volume" and item.get("source") == old_key:
                            item["source"] = logical
            # The volumes already exist, with labels from the migration's logical keys.
            target["volumes"][logical] = {
                "name": self.state["volume_names"][service],
                "external": True,
            }

        values = {
            "COMPOSE_FILE": "docker-compose.yml",
            "COMPOSE_PROJECT_NAME": self.state["project"],
            "IMAGE_TAG": self.state["image_tag"],
            "VECTOR_BACKEND": "pgvector",
            "PGVECTOR_DATABASE_URL": "",
        }
        # Map template environment references back to the actual migrated values.
        candidates: dict[str, set[str]] = {}
        section = ""
        for line in template.splitlines():
            match = re.fullmatch(r"  ([\w-]+):", line)
            if match:
                section = match[1]
            binding = re.fullmatch(r"      ([\w]+): \$\{([\w]+)(?::-[^}]*)?\}", line)
            if binding and section in target["services"]:
                key, variable = binding.groups()
                actual = target["services"][section].get("environment", {}).get(key)
                if actual is not None:
                    candidates.setdefault(variable, set()).add(str(actual))
        for variable, options in candidates.items():
            values[variable] = next(iter(options)) if len(options) == 1 else ""
        for service, variable in (("web", "WEB_PORT"), ("admin", "ADMIN_PORT")):
            ports = target["services"][service].get("ports", [])
            if len(ports) == 1 and isinstance(ports[0], dict) and ports[0].get("target") == 80:
                values[variable] = str(ports[0]["published"])

        deployment = Path(self.state["deployment_directory"])
        sources = [str(deployment / ".env"), *self.state.get("env_files", [])]
        if args.env_file:
            sources.append(os.path.abspath(args.env_file))
        environment = ""
        for name in dict.fromkeys(sources):
            path = Path(name)
            if file_digest(path) is not None:
                environment += path.read_text().rstrip() + "\n"
        save_bytes(env_path, update_dotenv(environment, values).encode())

        candidate = self.directory / "template.compose.yml"
        save_bytes(candidate, template.encode())
        command = [
            "docker",
            "compose",
            "--project-directory",
            str(deployment),
            "--project-name",
            self.state["project"],
            "--env-file",
            str(env_path),
        ]
        variables = set(re.findall(r"\$\{(\w+)", template)) | values.keys()
        render_environment = {
            key: value for key, value in os.environ.items() if key not in variables
        }

        def render(path: Path, output_format: str) -> str:
            return run(
                [*command, "-f", str(path), "config", "--format", output_format],
                capture=True,
                environment=render_environment,
            )

        base = compose_dollars(
            json.loads(render(candidate, "json")),
            escape=False,
        )
        adjusted = self.directory / "template-target.compose.json"
        save_json(adjusted, compose_dollars(target, escape=True))
        target = compose_dollars(
            json.loads(render(adjusted, "json")),
            escape=False,
        )
        rendered = render(adjusted, "yaml") + "\n"
        document = template.replace(
            "docker compose -f docker-compose.pgvector.yml", "docker compose"
        )
        for service, config in target["services"].items():
            for key, value in config.items():
                original: Any = base["services"][service].get(key)
                if key == "environment":
                    original_environment: dict[str, Any] = original or {}
                    for setting, actual in value.items():
                        if actual != original_environment.get(setting):
                            document = patch_yaml(
                                document, rendered, ("services", service, key, setting)
                            )
                elif value != original:
                    document = patch_yaml(
                        document,
                        rendered,
                        ("services", service, key),
                        remove_if_missing=value is None or value in ({}, []),
                    )
        for key in ("volumes", "networks", "configs", "secrets"):
            for name, value in target.get(key, {}).items():
                if value != base.get(key, {}).get(name):
                    path = (key, name) if key in base else (key,)
                    document = patch_yaml(document, rendered, path)
                    if key not in base:
                        break
        # Validate before publishing the cached installation files or archiving originals.
        save_bytes(candidate, document.encode())
        installed = compose_dollars(
            json.loads(render(candidate, "json")),
            escape=False,
        )
        for service, config in target["services"].items():
            for key, value in config.items():
                actual = installed["services"][service].get(key)
                if key == "environment":
                    installed_environment: dict[str, Any] = actual or {}
                    matches = all(
                        installed_environment.get(setting) == expected
                        for setting, expected in value.items()
                    )
                else:
                    matches = actual == value
                if not matches:
                    raise MigrationError(
                        f"Template did not preserve migrated setting: {service}.{key}"
                    )
        for key in ("volumes", "networks", "configs", "secrets"):
            if any(
                installed.get(key, {}).get(name) != value
                for name, value in target.get(key, {}).items()
            ):
                raise MigrationError(f"Template did not preserve migrated {key}.")
        save_bytes(output, document.encode())
        save_json(prepared, {"compose": file_digest(output), "env": file_digest(env_path)})

    def deployment_backup(self, args: argparse.Namespace) -> dict[str, Any]:
        archive = self.directory / "deployment-backup.tar.gz"
        deployment = Path(self.state["deployment_directory"])
        if not archive.exists():
            if self.state.get("deployment_backup"):
                raise MigrationError(
                    "Saved deployment backup is missing; restore it before retrying."
                )
            paths = {deployment / name for name in self.deployment_files()}
            source_files: list[str] = self.state.get("source_files", []) + self.state.get(
                "env_files", []
            )
            additional_compose: list[str] = args.compose or []
            source_files += [os.path.abspath(name) for name in additional_compose]
            if args.env_file:
                source_files.append(os.path.abspath(args.env_file))
            for name in source_files:
                paths.add(Path(os.path.abspath(name)))
            manifest: dict[str, Any] = {"deployment_directory": str(deployment), "files": []}
            temporary = archive.with_suffix(".tmp")
            with temporary.open("wb") as stream:
                os.chmod(temporary, 0o600)
                with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
                    for index, path in enumerate(sorted(paths)):
                        digest = file_digest(path)
                        member = None
                        mode = 0o600
                        if digest is not None:
                            member = (
                                f"deployment/{path.relative_to(deployment)}"
                                if path.is_relative_to(deployment)
                                else f"external/{index}/{path.name}"
                            )
                            mode = path.stat().st_mode & 0o777
                            bundle.add(path, arcname=member, recursive=False)
                        manifest["files"].append(
                            {"path": str(path), "member": member, "sha256": digest, "mode": mode}
                        )
                    payload = json.dumps(manifest, indent=2).encode()
                    info = tarfile.TarInfo("manifest.json")
                    info.size = len(payload)
                    info.mode = 0o600
                    bundle.addfile(info, io.BytesIO(payload))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(archive)
        # Read every member before touching deployment files, including on retries.
        with tarfile.open(archive, "r:gz") as bundle:
            manifest_file = bundle.extractfile("manifest.json")
            if manifest_file is None:
                raise MigrationError("Deployment backup has no manifest.")
            manifest = json.load(manifest_file)
            if manifest["deployment_directory"] != str(deployment):
                raise MigrationError("Deployment backup belongs to a different directory.")
            for item in manifest["files"]:
                if item["member"] is not None:
                    member_file = bundle.extractfile(item["member"])
                    if (
                        member_file is None
                        or hashlib.sha256(member_file.read()).hexdigest() != item["sha256"]
                    ):
                        raise MigrationError("Deployment backup failed its integrity check.")
        return manifest

    def check_deployment_files(self, manifest: dict[str, Any]) -> None:
        originals = {item["path"]: item for item in manifest["files"]}
        deployment = Path(self.state["deployment_directory"])
        for name, content in self.deployment_files().items():
            path = deployment / name
            installed_digest = hashlib.sha256(content).hexdigest() if content is not None else None
            if file_digest(path) not in {originals[str(path)]["sha256"], installed_digest}:
                raise MigrationError(
                    f"Deployment file changed after backup; preserve your edits first: {path}"
                )

    def finalize(self, args: argparse.Namespace) -> None:
        if self.state["phase"] != "complete":
            raise MigrationError("Complete the migration before running finalize.")
        if self.state.get("finalized"):
            print("Deployment files already installed; use docker compose normally.")
            return
        if os.environ.get("COMPOSE_FILE") or os.environ.get("COMPOSE_PROJECT_NAME"):
            raise MigrationError(
                "Unset shell COMPOSE_FILE and COMPOSE_PROJECT_NAME before finalize."
            )
        self.compose(True, "config", "--quiet")
        self.prepare_deployment(args)
        manifest = self.deployment_backup(args)
        self.check_deployment_files(manifest)
        # Persist the backup checkpoint before replacing any original file.
        self.state["deployment_backup"] = str(self.directory / "deployment-backup.tar.gz")
        save_json(self.state_path, self.state)
        deployment = Path(self.state["deployment_directory"])
        for name, content in self.deployment_files().items():
            path = deployment / name
            if content is None:
                path.unlink(missing_ok=True)
            else:
                save_bytes(path, content)
        self.state["finalized"] = True
        save_json(self.state_path, self.state)
        print(f"Original deployment files archived: {self.state['deployment_backup']}")
        print(
            f"Deployment files installed in {deployment}; use docker compose up -d, logs, ps, or down."
        )

    def restore_deployment_files(self) -> None:
        if not self.state.get("deployment_backup") or self.state.get("deployment_files_restored"):
            return
        manifest = self.deployment_backup(argparse.Namespace(compose=None, env_file=None))
        self.check_deployment_files(manifest)
        originals = {item["path"]: item for item in manifest["files"]}
        deployment = Path(self.state["deployment_directory"])
        with tarfile.open(self.state["deployment_backup"], "r:gz") as bundle:
            for name in self.deployment_files():
                path = deployment / name
                item = originals[str(path)]
                if item["member"] is None:
                    path.unlink(missing_ok=True)
                else:
                    stream = bundle.extractfile(item["member"])
                    if stream is None:
                        raise MigrationError("Deployment backup is missing an original file.")
                    save_bytes(path, stream.read(), item["mode"])
        self.state["deployment_files_restored"] = True
        save_json(self.state_path, self.state)

    def rollback(self) -> None:
        phase = self.state["phase"]
        if phase == "rolled_back":
            print("Already rolled back.")
            return
        if self.state.get("deployment_backup") and not self.state.get("deployment_files_restored"):
            manifest = self.deployment_backup(argparse.Namespace(compose=None, env_file=None))
            self.check_deployment_files(manifest)
        if phase != "rollback_started":
            self.state["rollback_from"] = phase
            self.advance("rollback_started")
        print("Restoring the pre-migration deployment. New pgvector writes remain in its volume.")
        if PHASES.index(self.state["rollback_from"]) >= PHASES.index("old_stopped"):
            self.compose(True, "down", "--timeout", "120")
        self.compose(False, "up", "-d", "--wait", "--wait-timeout", "300", "--pull", "never")
        self.restore_deployment_files()
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
    finalize = commands.add_parser(
        "finalize",
        help="Archive original deployment files and install the migrated Compose configuration",
    )
    finalize.add_argument(
        "--compose",
        action="append",
        help="Additional original Compose file to archive (for older migration state)",
    )
    finalize.add_argument(
        "--env-file", help="Additional original env file to archive (for older migration state)"
    )
    finalize.add_argument(
        "--template",
        type=Path,
        help="Release pgvector Compose template (default: docker-compose.pgvector.yml beside scripts/)",
    )
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
            installed = bool(migration.state.get("finalized")) and not migration.state.get(
                "deployment_files_restored", False
            )
            print(f"Deployment files installed: {installed}")
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
            elif args.action == "finalize":
                migration.finalize(args)
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
    except (
        MigrationError,
        OSError,
        ValueError,
        tarfile.TarError,
        subprocess.CalledProcessError,
    ) as error:
        # CalledProcessError includes argv; keep resolved credentials out of diagnostics.
        message = (
            f"Docker command failed (exit {error.returncode})."
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        print(f"Error: {message}", file=sys.stderr)
        if (directory / "state.json").exists():
            print(
                "Saved state retained. Fix the error and retry the same command, or run rollback.",
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        print(
            "Interrupted. Saved checkpoints are retained; retry the same command or run rollback.",
            file=sys.stderr,
        )
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
