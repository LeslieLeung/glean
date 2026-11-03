"""Run with python3 -m unittest discover -s scripts/tests -v.

Set GLEAN_MIGRATION_DOCKER_TEST=1 to include a disposable real PostgreSQL migration.
The integration test uses preloaded images and lightweight stand-ins for app services.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "migrate-to-pgvector.py"
spec = importlib.util.spec_from_file_location("migration", SCRIPT)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def source_config(project: str = "glean_migration_test") -> dict:
    app_env = {
        "DATABASE_URL": "postgresql+asyncpg://glean:test@postgres:5432/glean_test",
        "REDIS_URL": "redis://redis:6379/0",
        "SECRET_KEY": "literal-$SECRET-$(do-not-execute)-'quoted'",
        "VECTOR_BACKEND": "milvus",
        "CUSTOM_SETTING": "keep me",
    }
    services = {
        name: {
            "image": "postgres:16-alpine",
            "entrypoint": ["sh", "-c", "exec sleep infinity"],
            "init": True,
            "healthcheck": {"test": ["CMD", "true"], "interval": "1s"},
            "environment": copy.deepcopy(app_env) if name in {"backend", "worker"} else {},
        }
        for name in sorted(migration.CORE_SERVICES | migration.MILVUS_SERVICES)
    }
    services["postgres"] = {
        "image": "postgres:16-alpine",
        "environment": {
            "POSTGRES_DB": "glean_test",
            "POSTGRES_USER": "glean",
            "POSTGRES_PASSWORD": "test",
        },
        "volumes": [
            {"type": "volume", "source": "postgres_data", "target": "/var/lib/postgresql/data"}
        ],
        "healthcheck": {
            "test": ["CMD", "pg_isready", "-h", "127.0.0.1", "-U", "glean", "-d", "glean_test"],
            "interval": "1s",
            "retries": 30,
        },
    }
    services["redis"] = {
        "image": "redis:8-alpine",
        "command": ["redis-server", "--appendonly", "yes"],
        "volumes": [{"type": "volume", "source": "redis_data", "target": "/data"}],
        "healthcheck": {"test": ["CMD", "redis-cli", "ping"], "interval": "1s"},
    }
    services["backend"]["depends_on"] = {
        name: {"condition": "service_healthy"} for name in ("postgres", "redis", "milvus")
    }
    services["worker"]["depends_on"] = {"backend": {"condition": "service_healthy"}}
    services["backend"]["build"] = {"context": "/old/source"}
    services["backend"]["pull_policy"] = "always"
    return {
        "name": project,
        "services": services,
        "volumes": {key: {"name": f"{project}_{key}"} for key in ("postgres_data", "redis_data")},
    }


class FakeDocker:
    def __init__(self, source: dict) -> None:
        self.source = source
        self.calls: list[list[str]] = []
        self.version = "160010"
        self.embedding_status = "idle"
        self.containers = {}
        for name, service in source["services"].items():
            self.containers[name] = {
                "Image": f"sha256:{name}",
                "State": {"Running": True},
                "Config": {
                    "Labels": {"com.docker.compose.project": source["name"]},
                    "Env": [
                        f"{key}={value}" for key, value in service.get("environment", {}).items()
                    ],
                },
                "Mounts": [
                    {
                        "Destination": mount["target"],
                        "Name": source["volumes"][mount["source"]]["name"],
                    }
                    for mount in service.get("volumes", [])
                ],
            }

    def __call__(self, args: list[str], **kwargs) -> str:
        self.calls.append(args)
        if args[:2] == ["docker", "inspect"]:
            return json.dumps([self.containers[args[-1]]])
        if args[-3:] == ["config", "--format", "json"]:
            return json.dumps(migration.compose_dollars(self.source, escape=True))
        if "ps" in args:
            return args[-1]
        if args[-1] == "SHOW server_version_num":
            return self.version
        if args[-1] == migration.EMBEDDING_SQL:
            return self.embedding_status
        return ""


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "state"
        self.source = source_config()
        self.volume_names = {"postgres": "new_postgres", "redis": "new_redis"}
        self.args = migration.parser().parse_args(["migrate", "--image-tag", "1.2.3"])
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def saved_migration(self, phase: str) -> migration.Migration:
        self.directory.mkdir(exist_ok=True)
        value = migration.Migration(self.directory)
        value.state = {
            "phase": phase,
            "project": "test",
            "deployment_directory": str(self.directory),
            "image_tag": "1.2.3",
            "volume_names": self.volume_names,
            "original_volume_names": {"postgres": "old_pg", "redis": "old_redis"},
        }
        migration.save_json(value.state_path, value.state)
        (self.directory / "database.dump").write_bytes(b"fixture")
        migration.save_json(self.directory / "counts.json", "entries|3")
        return value

    def test_target_preserves_settings_and_separates_data(self) -> None:
        self.source["services"]["web"]["ports"] = [{"target": 80, "published": "8088"}]
        original = copy.deepcopy(self.source)
        target = migration.make_target(self.source, "1.2.3", self.volume_names)
        self.assertEqual(set(target["services"]), migration.CORE_SERVICES)
        self.assertEqual(target["services"]["web"]["ports"], original["services"]["web"]["ports"])
        self.assertEqual(
            target["services"]["backend"]["environment"]["SECRET_KEY"],
            original["services"]["backend"]["environment"]["SECRET_KEY"],
        )
        self.assertEqual(target["services"]["backend"]["environment"]["CUSTOM_SETTING"], "keep me")
        self.assertNotIn("milvus", target["services"]["backend"]["depends_on"])
        self.assertNotIn("build", target["services"]["backend"])
        self.assertNotIn("pull_policy", target["services"]["backend"])
        self.assertEqual(
            target["services"]["worker"]["depends_on"]["backend"]["condition"],
            "service_healthy",
        )
        self.assertEqual(target["services"]["worker"]["environment"]["RUN_MIGRATIONS"], "false")
        self.assertEqual(target["volumes"]["pgvector_postgres"]["name"], "new_postgres")
        self.assertNotIn("postgres_data", target["volumes"])
        self.assertEqual(self.source, original)

    def test_dry_run_does_not_mutate_deployment_or_create_state(self) -> None:
        docker = FakeDocker(self.source)
        self.args.dry_run = True
        with mock.patch.object(migration, "run", docker):
            migration.Migration(self.directory).prepare(self.args)
        self.assertFalse(self.directory.exists())
        self.assertFalse(
            any("tag" in call or "stop" in call or "up" in call for call in docker.calls)
        )

    def test_preflight_rejects_unsupported_or_mismatched_deployments(self) -> None:
        cases = (
            "external_db",
            "bind_mount",
            "postgres17",
            "wrong_volume",
            "changed_secret",
            "rebuilding",
        )
        for case in cases:
            with self.subTest(case=case):
                source = copy.deepcopy(self.source)
                if case == "external_db":
                    source["services"]["backend"]["environment"]["DATABASE_URL"] = (
                        "postgresql://u:p@external/db"
                    )
                if case == "bind_mount":
                    source["services"]["postgres"]["volumes"][0]["type"] = "bind"
                docker = FakeDocker(source)
                if case == "postgres17":
                    docker.version = "170001"
                if case == "wrong_volume":
                    docker.containers["postgres"]["Mounts"][0]["Name"] = "other"
                if case == "changed_secret":
                    docker.containers["backend"]["Config"]["Env"] = []
                if case == "rebuilding":
                    docker.embedding_status = "rebuilding"
                self.args.dry_run = True
                with (
                    mock.patch.object(migration, "run", docker),
                    self.assertRaises(migration.MigrationError),
                ):
                    migration.Migration(self.directory).prepare(self.args)
                self.assertFalse(self.directory.exists())

    def test_snapshots_are_private_and_pin_actual_images(self) -> None:
        self.directory.mkdir()
        with mock.patch.object(migration, "run", FakeDocker(self.source)):
            migration.Migration(self.directory).prepare(self.args)
        saved = json.loads((self.directory / "original.compose.json").read_text())
        for name, service in saved["services"].items():
            self.assertTrue(
                service["image"].startswith(f"glean-rollback/glean_migration_test-{name}:")
            )
        for name in ("original.compose.json", "pgvector.compose.json", "state.json"):
            self.assertEqual((self.directory / name).stat().st_mode & 0o777, 0o600)

    def test_partial_restore_retries_only_verified_target_database(self) -> None:
        value = self.saved_migration("old_stopped")
        with (
            mock.patch.object(value, "compose"),
            mock.patch.object(value, "assert_mount"),
            mock.patch.object(value, "pg", side_effect=RuntimeError("restore interrupted")),
            self.assertRaises(RuntimeError),
        ):
            value.migrate()
        self.assertEqual(migration.Migration(self.directory).state["phase"], "old_stopped")
        resumed = migration.Migration(self.directory)
        with (
            mock.patch.object(resumed, "compose") as compose,
            mock.patch.object(resumed, "assert_mount") as mounts,
            mock.patch.object(resumed, "pg") as pg,
            mock.patch.object(resumed, "sql", side_effect=["entries|3", "CREATE EXTENSION"]),
        ):
            resumed.migrate()
            self.assertEqual(resumed.state["phase"], "complete")
            self.assertEqual(mounts.call_count, 2)
            self.assertTrue(all(call.args[0] for call in compose.call_args_list))
            self.assertTrue(any("dropdb" in str(call.args) for call in compose.call_args_list))
            pg.assert_called_once()
            compose.reset_mock()
            resumed.migrate()
            compose.assert_not_called()

    def test_wrong_target_volume_stops_before_drop_or_restore(self) -> None:
        value = self.saved_migration("old_stopped")
        with (
            mock.patch.object(value, "compose") as compose,
            mock.patch.object(
                value, "assert_mount", side_effect=migration.MigrationError("wrong mount")
            ),
            mock.patch.object(value, "pg") as pg,
        ):
            with self.assertRaises(migration.MigrationError):
                value.migrate()
            self.assertFalse(any("dropdb" in str(call.args) for call in compose.call_args_list))
            pg.assert_not_called()

    def test_startup_retry_does_not_restore_again(self) -> None:
        value = self.saved_migration("restored")
        with (
            mock.patch.object(value, "compose", side_effect=RuntimeError("unhealthy")),
            self.assertRaises(RuntimeError),
        ):
            value.migrate()
        resumed = migration.Migration(self.directory)
        with (
            mock.patch.object(resumed, "compose") as compose,
            mock.patch.object(resumed, "pg") as pg,
        ):
            resumed.migrate()
            compose.assert_called_once_with(True, "up", "-d", "--wait", "--wait-timeout", "300")
            pg.assert_not_called()

    def test_rollback_resumes_with_pinned_original_config(self) -> None:
        value = self.saved_migration("complete")
        with (
            mock.patch.object(value, "compose", side_effect=["", RuntimeError("interrupted")]),
            self.assertRaises(RuntimeError),
        ):
            value.rollback()
        resumed = migration.Migration(self.directory)
        self.assertEqual(resumed.state["rollback_from"], "complete")
        with mock.patch.object(resumed, "compose") as compose:
            resumed.rollback()
            self.assertEqual(resumed.state["phase"], "rolled_back")
            compose.assert_any_call(
                False, "up", "-d", "--wait", "--wait-timeout", "300", "--pull", "never"
            )
            self.assertFalse(
                any(
                    "--volumes" in call.args or "-v" in call.args for call in compose.call_args_list
                )
            )
            with self.assertRaises(migration.MigrationError):
                resumed.migrate()

    def test_rollback_before_cutover_does_not_stop_new_configuration(self) -> None:
        value = self.saved_migration("quiesced")
        with mock.patch.object(value, "compose") as compose:
            value.rollback()
            self.assertEqual(compose.call_count, 1)
            self.assertFalse(compose.call_args.args[0])


@unittest.skipUnless(
    os.environ.get("GLEAN_MIGRATION_DOCKER_TEST") == "1", "Opt-in Docker integration test"
)
class DockerMigrationTests(unittest.TestCase):
    def test_real_dump_restore_resume_and_rollback(self) -> None:
        project = f"glean_migration_test_{secrets.token_hex(4)}"
        original_run = migration.run
        with tempfile.TemporaryDirectory(
            prefix="glean-migration-test-", dir="/data/workspace"
        ) as temporary:
            directory = Path(temporary)
            source = source_config(project)
            source["services"]["backend"].pop("build")
            source["services"]["backend"].pop("pull_policy")
            source_path = directory / "compose.json"
            migration.save_json(source_path, migration.compose_dollars(source, escape=True))
            state_directory = directory / "state"
            command = ["docker", "compose", "-p", project, "-f", str(source_path)]
            value = migration.Migration(state_directory)
            new_volumes = []
            rollback_images = []
            try:
                original_run(
                    [*command, "up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never"]
                )
                sql = " ".join(
                    f"CREATE TABLE {table} (id integer PRIMARY KEY, content text); INSERT INTO {table} VALUES (1, 'saved-$literal');"
                    for table in ("users", "subscriptions", "entries", "bookmarks", "user_entries")
                )
                sql += ' CREATE TABLE system_configs (key text PRIMARY KEY, value jsonb); INSERT INTO system_configs VALUES (\'embedding\', \'{"status":"disabled","enabled":false}\');'
                original_run(
                    [
                        *command,
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-U",
                        "glean",
                        "-d",
                        "glean_test",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-c",
                        sql,
                    ],
                    capture=True,
                )
                original_run(
                    [
                        *command,
                        "exec",
                        "-T",
                        "redis",
                        "redis-cli",
                        "SET",
                        "old_queue_marker",
                        "preserved",
                    ],
                    capture=True,
                )
                args = migration.parser().parse_args(
                    [
                        "migrate",
                        "--image-tag",
                        "16-alpine",
                        "--compose",
                        str(source_path),
                        "--skip-pull",
                        "--dry-run",
                    ]
                )
                value.prepare(args)
                self.assertFalse(state_directory.exists())
                args.dry_run = False
                state_directory.mkdir(mode=0o700)
                with mock.patch.dict(
                    migration.APP_REPOSITORIES,
                    dict.fromkeys(migration.APP_REPOSITORIES, "postgres"),
                ):
                    value.prepare(args)
                new_volumes = list(value.state["volume_names"].values())
                rollback = json.loads((state_directory / "original.compose.json").read_text())
                rollback_images = [service["image"] for service in rollback["services"].values()]
                # Simulate an interrupted restore after committing data, before saving its checkpoint.
                original_pg = value.pg
                interrupted = False

                def interrupt_restore(target, executable, *args, **kwargs):
                    nonlocal interrupted
                    output = original_pg(target, executable, *args, **kwargs)
                    if target and executable == "pg_restore" and not interrupted:
                        interrupted = True
                        raise RuntimeError("simulated crash after pg_restore commit")
                    return output

                with (
                    mock.patch.object(value, "pg", side_effect=interrupt_restore),
                    self.assertRaises(RuntimeError),
                ):
                    value.migrate()
                resumed = migration.Migration(state_directory)
                self.assertEqual(resumed.state["phase"], "old_stopped")
                resumed.migrate()
                self.assertEqual(
                    resumed.sql(True, "SELECT content FROM bookmarks"), "saved-$literal"
                )
                self.assertTrue(
                    resumed.sql(True, "SELECT extversion FROM pg_extension WHERE extname='vector'")
                )
                self.assertEqual(
                    resumed.compose(
                        True,
                        "exec",
                        "-T",
                        "redis",
                        "redis-cli",
                        "EXISTS",
                        "old_queue_marker",
                        capture=True,
                    ),
                    "0",
                )
                environment = dict(
                    item.split("=", 1)
                    for item in resumed.inspect_service(True, "backend")["Config"]["Env"]
                )
                self.assertEqual(
                    environment["SECRET_KEY"],
                    source["services"]["backend"]["environment"]["SECRET_KEY"],
                )
                self.assertEqual(environment["CUSTOM_SETTING"], "keep me")
                resumed.sql(True, "INSERT INTO bookmarks VALUES (2, 'new-only')")
                resumed.migrate()  # A completed migration must not erase the new write.
                self.assertEqual(resumed.sql(True, "SELECT count(*) FROM bookmarks"), "2")
                resumed.rollback()
                self.assertEqual(resumed.sql(False, "SELECT count(*) FROM bookmarks"), "1")
                self.assertEqual(
                    resumed.compose(
                        False,
                        "exec",
                        "-T",
                        "redis",
                        "redis-cli",
                        "GET",
                        "old_queue_marker",
                        capture=True,
                    ),
                    "preserved",
                )
                self.assertEqual(resumed.state["phase"], "rolled_back")
            finally:
                # Clean up only the unique test project, volumes, and image aliases.
                subprocess.run([*command, "down", "--volumes", "--remove-orphans"], check=False)
                if new_volumes:
                    subprocess.run(["docker", "volume", "rm", *new_volumes], check=False)
                if rollback_images:
                    subprocess.run(
                        ["docker", "image", "rm", *rollback_images],
                        check=False,
                        stdout=subprocess.DEVNULL,
                    )


if __name__ == "__main__":
    unittest.main()
