# Migrate an existing Milvus deployment to pgvector

[简体中文](MIGRATE_PGVECTOR.zh-CN.md)

Run the migration script from your existing deployment directory:

```bash
python3 scripts/migrate-to-pgvector.py migrate --image-tag RELEASE_IMAGE_TAG
```

Replace `RELEASE_IMAGE_TAG` with the published image tag of a release that supports
pgvector. Use a fixed version, not `latest`. The API, worker, web, and admin are
upgraded together. Keep external access closed during the maintenance window.

## Requirements

- Linux, Python 3.11+, Docker, and a recent Docker Compose V2 or newer.
- An existing, running Glean deployment using local PostgreSQL 16, local Redis,
  named data volumes, and the standard six core services (plus optional Milvus).
- Run from the original deployment directory, with its original Compose files and
  environment. The default source is `docker-compose.yml` and Compose's normal
  `.env` loading. Finish any existing embedding validation/rebuild first.
- Enough disk space for a database dump, a restored database, and new vectors.
  Keep your normal independent deployment backups; retained local volumes are
  not an off-machine backup.

If you deployed by downloading only a Compose file, first download the script
from the release you are installing:

```bash
release_ref='RELEASE_GIT_TAG'
mkdir -p scripts
curl -fSL "https://raw.githubusercontent.com/LeslieLeung/glean/${release_ref}/scripts/migrate-to-pgvector.py" \
  -o scripts/migrate-to-pgvector.py
```

## Optional prerequisite check

```bash
python3 scripts/migrate-to-pgvector.py migrate --image-tag RELEASE_IMAGE_TAG --dry-run
```

This checks the running services, PostgreSQL version, configuration consistency,
volume mounts, and embedding state without stopping services or creating backups.
It does not download images or verify embedding-provider credentials/quota.

For custom Compose files, repeat `--compose` in their original merge order. Extra
arguments are only needed on the initial run:

```bash
python3 scripts/migrate-to-pgvector.py migrate --image-tag RELEASE_IMAGE_TAG \
  --compose docker-compose.yml --compose docker-compose.production.yml \
  --env-file .env.production --project-name glean
```

The script rejects external PostgreSQL/Redis, bind-mounted database/queue data,
nonstandard additional services, profiles, and other PostgreSQL major versions.
Those deployments need an adapted migration. `--skip-pull` uses preloaded images.

## What the script handles

The script snapshots the resolved configuration, pins the exact old images, and
preserves credentials, ports, proxy/network settings, and custom environment
settings. It downloads new images before stopping the old application, then
exports PostgreSQL, verifies the archive, and stops the old stack.

It restores into a fresh PostgreSQL 16 pgvector volume and starts a fresh Redis
queue, leaving all old PostgreSQL, Redis, and Milvus volumes intact. A logical
restore avoids assuming that the old Alpine data directory is portable to the
new Debian-based pgvector image. Business-table counts are compared before the
application starts, and `vector` is enabled in the target database.

Finally, the new API runs Alembic migrations and the worker starts after backend
health checks pass. If embedding was enabled, Glean automatically validates and
rebuilds article vectors, then preferences from retained history. Milvus vectors
are regenerated, not copied; this may incur embedding-provider charges. Old
queued jobs are not transferred; scheduled feed fetching resumes in the new worker.

The command finishes when the services are healthy. Check Admin → Settings →
Embedding until `idle` (Operational), inspect failed entries, and verify articles,
subscriptions, bookmarks, reading state, and recommendation/smart-sorting behavior.
Disabled vectorization remains disabled. If rebuilding fails, inspect the admin
error and worker logs before retrying through the embedding admin controls/API.

## Resume, status, and rollback

If interrupted or failed, fix the error and resume in the same directory:

```bash
python3 scripts/migrate-to-pgvector.py migrate
python3 scripts/migrate-to-pgvector.py status
```

Checkpoints prevent repeating a completed restore. An incomplete restore resets
only the verified new target database; once the restored checkpoint is saved,
retries do not discard subsequent application writes. Errors leave state intact
and do not automatically switch the deployment back.

To return to the pre-migration images and volumes:

```bash
python3 scripts/migrate-to-pgvector.py rollback
```

Rollback keeps the new volume, but new writes made after migration will not appear
in the old deployment. The old schema, old queue, old images, and Milvus are
restored together. Do not roll back by changing only an image tag.

## Running the migrated deployment

The original Compose and `.env` files are unchanged. Use the script's Compose
helper to operate the saved active configuration:

```bash
python3 scripts/migrate-to-pgvector.py compose ps
python3 scripts/migrate-to-pgvector.py compose logs --tail=100 backend worker
python3 scripts/migrate-to-pgvector.py compose up -d
```

State, the database dump, and configuration snapshots are stored in
`.glean-pgvector-migration/`, with restricted permissions and a Git ignore rule.
Do not remove it or the rollback image tags until the migration is accepted.
Do not publish the snapshots: they contain credentials. Keep using the helper or
consolidate the saved configuration into your permanent deployment configuration
before returning to ordinary `docker compose` commands. The helper selects the
old configuration after rollback.

An optional global `--state-dir PATH` changes the state location; supply it before
`migrate`, `status`, `rollback`, or `compose` on every invocation. After rollback,
use a new state directory for a new migration so that a fresh backup is taken.
The script never deletes data volumes. Clean up old volumes explicitly only after
accepting the migration and keeping an independent backup.
