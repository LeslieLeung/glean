# Glean Deployment Guide

This guide provides comprehensive instructions for deploying Glean in production environments.

## Table of Contents

- [Quick Deployment](#quick-deployment)
- [Production Deployment](#production-deployment)
- [Service Architecture](#service-architecture)
- [Environment Configuration](#environment-configuration)
- [Admin Account Management](#admin-account-management)
- [Updating Glean](#updating-glean)
- [Backup and Restore](#backup-and-restore)
- [Monitoring and Logs](#monitoring-and-logs)
- [Troubleshooting](#troubleshooting)
- [HTTPS Setup](#https-setup)
- [Security Best Practices](#security-best-practices)
- [Performance Tuning](#performance-tuning)

## Quick Deployment

### Full Deployment (Recommended)

Includes Milvus for Phase 3 features (smart recommendations, preference learning):

```bash
# Download docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.yml -o docker-compose.yml

# (Optional) Create .env file to customize admin credentials
cat > .env << EOF
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$(openssl rand -base64 24)
SECRET_KEY=$(openssl rand -base64 32)
EOF

# ⚠️ IMPORTANT: Save the generated passwords before proceeding!
cat .env

# Start all services
docker compose up -d

# Access:
# - Web App: http://localhost
# - Admin Dashboard: http://localhost:3001 (default: admin / Admin123!)
```

**Default admin account**: If you don't create a `.env` file, the default credentials are:
- Username: `admin`
- Password: `Admin123!`
- ⚠️ **Change this password in production!**

### Lite Deployment (Without Milvus)

For lighter deployments if you don't need Phase 3 features:

```bash
# Download lite version
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.lite.yml -o docker-compose.yml

# (Optional) Create .env file to customize admin credentials
cat > .env << EOF
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$(openssl rand -base64 24)
SECRET_KEY=$(openssl rand -base64 32)
EOF

# ⚠️ IMPORTANT: Save the generated passwords
cat .env

# Start services
docker compose up -d
```

**Default admin account**: If you don't create a `.env` file, the default credentials are:
- Username: `admin`
- Password: `Admin123!`
- Dashboard: http://localhost:3001
- ⚠️ **Change this password in production!**

**Next steps**:
1. Log in to admin dashboard at http://localhost:3001
2. Change the default password
3. Configure additional environment variables for production (see [Environment Configuration](#environment-configuration))

### Testing Pre-release Versions

Pre-release versions (alpha/beta/rc) are available for testing upcoming features:

**Method 1: Using .env file (recommended)**

```bash
# Add to your .env file
echo "IMAGE_TAG=v0.3.0-alpha.1" >> .env

# Start with pre-release images
docker compose up -d
```

**Method 2: Inline environment variable**

```bash
# Set version and start in one command
IMAGE_TAG=v0.3.0-alpha.1 docker compose up -d
```

**Method 3: Export environment variable**

```bash
# Export for current shell session
export IMAGE_TAG=v0.3.0-alpha.1

# Start services
docker compose up -d
```

**Important notes:**
- Pre-release versions are for testing only
- Not recommended for production use
- Won't trigger auto-updates for Electron apps
- May contain bugs or incomplete features

Browse available pre-releases at: https://github.com/LeslieLeung/glean/releases

To switch back to stable:
```bash
# Remove IMAGE_TAG from .env or unset it
unset IMAGE_TAG

# Or set it back to latest
export IMAGE_TAG=latest

# Pull and restart with latest stable
docker compose pull
docker compose up -d
```

## Production Deployment

### Prerequisites

- Docker Engine 24.0+ and Docker Compose V2
- Domain name (recommended for HTTPS)
- Reverse proxy (nginx/Caddy) for HTTPS (recommended)

### Step-by-Step Setup

#### 1. Download Deployment Files

```bash
# Create deployment directory
mkdir -p ~/glean && cd ~/glean

# Download docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.yml -o docker-compose.yml

# Download environment template
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/.env.example -o .env
```

#### 2. Configure Environment Variables

Edit `.env` and set secure values:

```bash
nano .env
```

**Critical settings to change:**

```bash
# JWT secret key - MUST CHANGE!
# Generate with: openssl rand -hex 32
SECRET_KEY=your-long-random-secret-key-here

# Database credentials
POSTGRES_PASSWORD=your-secure-database-password

# Admin account (auto-create on first startup)
CREATE_ADMIN=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!

# Ports (adjust if needed)
WEB_PORT=80
ADMIN_PORT=3001

# Disable debug mode in production
DEBUG=false
```

See [Environment Configuration](#environment-configuration) for all available options.

#### 3. Start Services

```bash
# Start all services in detached mode
docker compose up -d

# Verify all services are running
docker compose ps
```

Expected output:
```
NAME              IMAGE                                    STATUS
glean-admin       ghcr.io/leslieleung/glean-admin:latest   Up (healthy)
glean-backend     ghcr.io/leslieleung/glean-backend:latest Up (healthy)
glean-postgres    postgres:16-alpine                       Up (healthy)
glean-redis       redis:8-alpine                           Up (healthy)
glean-web         ghcr.io/leslieleung/glean-web:latest     Up
glean-worker      ghcr.io/leslieleung/glean-backend:latest Up
```

#### 4. Verify Deployment

```bash
# Check backend health
curl http://localhost/api/health

# Check logs
docker compose logs -f

# Verify admin account was created (if CREATE_ADMIN=true)
docker compose logs backend | grep "Admin Account Created"
```

#### 5. Access Glean

- **Web App**: `http://localhost` (or `http://your-server-ip`)
- **Admin Dashboard**: `http://localhost:3001`
- **API Documentation**: `http://localhost/api/docs` (if DEBUG=true)

## Service Architecture

### Full Deployment

Glean consists of 9 services orchestrated by Docker Compose:

**Core services:**

| Service    | Container Name | Description                         | Dependencies       |
| ---------- | -------------- | ----------------------------------- | ------------------ |
| postgres   | glean-postgres | PostgreSQL 16 database              | -                  |
| redis      | glean-redis    | Redis 8 for task queue              | -                  |
| backend    | glean-backend  | FastAPI REST API server             | postgres, redis    |
| worker     | glean-worker   | arq background worker (feed sync)   | postgres, redis    |
| web        | glean-web      | React web frontend (nginx)          | backend            |
| admin      | glean-admin    | Admin dashboard (nginx)             | backend            |

**Milvus services (Phase 3 features):**

| Service       | Container Name      | Description                    | Dependencies       |
| ------------- | ------------------- | ------------------------------ | ------------------ |
| milvus-etcd   | glean-milvus-etcd   | etcd for Milvus coordination   | -                  |
| milvus-minio  | glean-milvus-minio  | MinIO object storage           | -                  |
| milvus        | glean-milvus        | Vector database for embeddings | milvus-etcd, minio |

**Service startup order:**
1. `postgres` and `redis` start first (with health checks)
2. `backend` starts after DB/Redis are healthy (runs migrations)
3. `worker` starts after backend is healthy
4. `web` and `admin` start after backend is ready
5. `milvus-etcd` and `milvus-minio` start in parallel, then `milvus`

### Lite Deployment

Excludes Milvus services (6 services total). Use `docker-compose.lite.yml` for this configuration.

**Data persistence:**
- `postgres_data` - PostgreSQL database files
- `redis_data` - Redis persistence (AOF)
- `glean_logs` - Application logs (backend + worker)
- `milvus_etcd_data` - Milvus etcd data (optional)
- `milvus_minio_data` - Milvus object storage (optional)
- `milvus_data` - Milvus vector database (optional)

**Networking:**
- All services communicate via `glean-network` bridge network
- Only `web` (port 80), `admin` (port 3001), and optionally `milvus` (port 19530) are exposed to host

## Environment Configuration

### Core Settings

| Variable            | Required | Default                              | Description                           |
| ------------------- | -------- | ------------------------------------ | ------------------------------------- |
| `SECRET_KEY`        | Yes      | `change-me-in-production...`         | JWT signing key (min 32 chars)        |
| `POSTGRES_DB`       | No       | `glean`                              | Database name                         |
| `POSTGRES_USER`     | No       | `glean`                              | Database username                     |
| `POSTGRES_PASSWORD` | Yes      | `glean`                              | Database password                     |
| `DEBUG`             | No       | `false`                              | Enable debug mode and API docs        |

### Port Configuration

| Variable     | Default | Description              |
| ------------ | ------- | ------------------------ |
| `WEB_PORT`   | `80`    | Web interface port       |
| `ADMIN_PORT` | `3001`  | Admin dashboard port     |

### Admin Account Auto-Creation

| Variable          | Default | Description                          |
| ----------------- | ------- | ------------------------------------ |
| `CREATE_ADMIN`    | `false` | Auto-create admin on first startup   |
| `ADMIN_USERNAME`  | `admin` | Admin username                       |
| `ADMIN_PASSWORD`  | -       | Admin password (required if enabled) |
| `ADMIN_ROLE`      | `super_admin` | Admin role                     |

### Logging Configuration

| Variable          | Default                      | Description                    |
| ----------------- | ---------------------------- | ------------------------------ |
| `LOG_LEVEL`       | `INFO`                       | Log level (DEBUG/INFO/WARNING) |
| `LOG_FILE`        | `/app/logs/glean-api.log`    | Log file path (backend)        |
| `LOG_ROTATION`    | `100 MB`                     | Log rotation size              |
| `LOG_RETENTION`   | `30 days`                    | Log retention period           |
| `LOG_COMPRESSION` | `gz`                         | Log compression format         |

### Milvus Configuration (Phase 3 Features)

Milvus is optional and provides vector database capabilities for smart recommendations and preference learning.

**Enable Milvus:**
```bash
docker compose --profile milvus up -d
```

**Milvus connection settings:**

| Variable                  | Default     | Description                       |
| ------------------------- | ----------- | --------------------------------- |
| `MILVUS_HOST`             | `localhost` | Milvus server host                |
| `MILVUS_PORT`             | `19530`     | Milvus server port                |
| `MILVUS_USER`             | -           | Milvus username (if auth enabled) |
| `MILVUS_PASSWORD`         | -           | Milvus password (if auth enabled) |
| `MILVUS_ENTRIES_COLLECTION` | `entries` | Collection name for entry vectors |
| `MILVUS_PREFS_COLLECTION` | `user_preferences` | Collection name for user preferences |

### Embedding Configuration (Phase 3 Features)

Required when using Milvus for smart recommendations:

| Variable               | Default                  | Description                                      |
| ---------------------- | ------------------------ | ------------------------------------------------ |
| `EMBEDDING_PROVIDER`   | `sentence-transformers`  | Provider: sentence-transformers, openai, volc-engine |
| `EMBEDDING_MODEL`      | `all-MiniLM-L6-v2`       | Model name                                       |
| `EMBEDDING_DIMENSION`  | `384`                    | Vector dimension (must match model)              |
| `EMBEDDING_API_KEY`    | -                        | API key (for openai/volc-engine)                 |
| `EMBEDDING_BASE_URL`   | -                        | Custom API endpoint (optional)                   |
| `EMBEDDING_BATCH_SIZE` | `20`                     | Batch size for embedding generation              |
| `EMBEDDING_MAX_RETRIES`| `3`                      | Max retries for failed requests                  |
| `EMBEDDING_TIMEOUT`    | `30`                     | Request timeout in seconds                       |

**Supported providers:**
- **sentence-transformers** - Local embedding models (no API key required)
  - Models: `all-MiniLM-L6-v2` (384d), `paraphrase-multilingual-MiniLM-L12-v2` (384d)
- **openai** - OpenAI embedding API
  - Models: `text-embedding-3-small` (1536d), `text-embedding-3-large` (3072d)
  - Requires: `EMBEDDING_API_KEY`
- **volc-engine** - Volcengine/ByteDance embedding API
  - Models: `doubao-embedding` (1024d)
  - Requires: `EMBEDDING_API_KEY` or `ARK_API_KEY`

For complete configuration reference, see [.env.example](.env.example).

## Admin Account Management

Glean automatically creates a default admin account on first startup. You can customize the credentials or disable auto-creation if needed.

### Default Admin Account

**By default**, when you start Glean for the first time, an admin account is automatically created with:

- **Username**: `admin`
- **Password**: `Admin123!`
- **Role**: `super_admin`

⚠️ **Security Warning**: Change the default password immediately in production environments!

You can verify the admin account was created by checking the logs:

```bash
docker compose logs backend | grep "Admin Account Created"
```

### Method 1: Customize Admin Credentials (Recommended for Production)

To use custom credentials instead of the defaults, set environment variables in `.env` **before** starting services:

```bash
# Admin credentials (customize these!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!

# Optional: specify role (default: super_admin)
ADMIN_ROLE=super_admin

# Optional: disable auto-creation (if you want to create manually)
# CREATE_ADMIN=false
```

Then start services:

```bash
docker compose up -d

# Verify admin was created
docker compose logs backend | grep "Admin Account Created"
```

**Important notes**:
- Admin account is created automatically on first startup
- Default credentials are `admin / Admin123!` - **change this in production!**
- Credentials are displayed during startup - check logs with `docker compose logs backend`
- If admin already exists, no new admin will be created (no error)
- To disable auto-creation, set `CREATE_ADMIN=false` in `.env`
- The auto-creation runs during container startup via `entrypoint.sh`

**Example output**:
```
==============================================
  Admin Account Created Successfully!
==============================================
  Username: admin
  Password: Admin123!
  Role: super_admin
==============================================

  Please save these credentials securely!
  Change the default password in production!
==============================================
```

### Method 2: Manual Creation After Deployment

**Best for**: Creating additional admins, resetting credentials

#### Option A: Simple wrapper (generates random password)

```bash
# Generate secure random password automatically
docker exec -it glean-backend /app/scripts/create-admin-docker.sh

# With custom username
docker exec -it glean-backend /app/scripts/create-admin-docker.sh myusername

# With custom username and password
docker exec -it glean-backend /app/scripts/create-admin-docker.sh myusername MySecurePass123!

# With custom username, password, and role
docker exec -it glean-backend /app/scripts/create-admin-docker.sh myusername MySecurePass123! admin
```

The script will display the credentials after successful creation.

#### Option B: Direct Python script (more control)

```bash
# Basic usage
docker exec -it glean-backend uv run python scripts/create-admin.py \
  --username admin --password MySecurePass123!

# Force recreate if admin exists (no confirmation prompt)
docker exec -it glean-backend uv run python scripts/create-admin.py \
  --username admin --password NewPassword123! --force

# Specify custom role
docker exec -it glean-backend uv run python scripts/create-admin.py \
  --username admin --password Pass123! --role admin
```

**Script options**:
- `--username`: Admin username (default: `admin`)
- `--password`: Admin password (default: `Admin123!`)
- `--role`: Admin role - `super_admin` or `admin` (default: `super_admin`)
- `--force`, `-f`: Force recreate if user exists (skip confirmation)

### Security Best Practices

1. **Use strong passwords**: Generate random passwords with `openssl rand -base64 24`
2. **Change default password**: Never use `Admin123!` in production
3. **Disable auto-creation**: Set `CREATE_ADMIN=false` after first startup
4. **Limit admin accounts**: Only create for authorized personnel
5. **Use unique usernames**: Avoid generic names like "admin" in production
6. **Rotate passwords regularly**: Update passwords periodically
7. **Monitor access**: Review admin login logs for suspicious activity
8. **Secure the admin port**: Use firewall rules to restrict access to port 3001

### Admin Roles

Glean supports two admin roles:

| Role          | Description            | Permissions                      |
| ------------- | ---------------------- | -------------------------------- |
| `super_admin` | Super administrator    | Full system access (recommended) |
| `admin`       | Standard administrator | Standard admin access            |

*Note: Currently, both roles have identical permissions. Role-based permission differentiation will be implemented in future releases.*

### Accessing Admin Dashboard

After creating an admin account, access the admin dashboard at:

- **Default**: http://localhost:3001
- **Custom port**: http://localhost:${ADMIN_PORT} (if `ADMIN_PORT` is set in `.env`)

Login with your admin credentials to manage users and view system statistics.

### Troubleshooting

**Admin already exists error**:
```bash
# Use --force flag to recreate
docker exec -it glean-backend uv run python scripts/create-admin.py \
  --username admin --password NewPass123! --force
```

**Cannot connect to database**:
```bash
# Verify database is running
docker compose ps postgres

# Check database health
docker exec -it glean-postgres pg_isready -U glean
```

**Password validation failed**:
- Ensure password meets all requirements (8+ chars, mixed case, number, special char)
- Check for unsupported special characters

For more detailed admin setup instructions, see [docs/admin-setup.md](docs/admin-setup.md).

## Updating Glean

### Update to Latest Version

```bash
# Pull latest images
docker compose pull

# Restart services with new images
docker compose up -d

# Database migrations run automatically on backend startup
# Verify services are healthy
docker compose ps
```

### Update to Specific Version

```bash
# Edit docker-compose.yml and change image tags
# Example: ghcr.io/leslieleung/glean-backend:v1.2.3

# Pull and restart
docker compose pull
docker compose up -d
```

### Rollback to Previous Version

```bash
# Stop services
docker compose down

# Edit docker-compose.yml to use previous image tag

# Start with previous version
docker compose up -d
```

## Backup and Restore

### Database Backup

**Automated backup script:**

```bash
#!/bin/bash
# backup-glean.sh

BACKUP_DIR="$HOME/glean-backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup PostgreSQL
docker exec glean-postgres pg_dump -U glean glean | gzip > "$BACKUP_DIR/glean_db_$DATE.sql.gz"

# Backup volumes
docker run --rm \
  -v glean_postgres_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/postgres_data_$DATE.tar.gz -C /data .

docker run --rm \
  -v glean_redis_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/redis_data_$DATE.tar.gz -C /data .

echo "Backup completed: $BACKUP_DIR"
```

Make executable and run:

```bash
chmod +x backup-glean.sh
./backup-glean.sh
```

**Set up daily backups with cron:**

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/backup-glean.sh
```

### Database Restore

**From SQL dump:**

```bash
# Stop services
docker compose down

# Start only PostgreSQL
docker compose up -d postgres

# Restore database
gunzip -c glean_db_20250101_020000.sql.gz | docker exec -i glean-postgres psql -U glean -d glean

# Restart all services
docker compose up -d
```

**From volume backup:**

```bash
# Stop services
docker compose down

# Remove old volume
docker volume rm glean_postgres_data

# Create new volume
docker volume create glean_postgres_data

# Restore from backup
docker run --rm \
  -v glean_postgres_data:/data \
  -v "$HOME/glean-backups":/backup \
  alpine tar xzf /backup/postgres_data_20250101_020000.tar.gz -C /data

# Start services
docker compose up -d
```

## Monitoring and Logs

### View Logs

```bash
# All services (follow mode)
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f worker

# Last 100 lines
docker compose logs --tail=100 backend

# Logs with timestamps
docker compose logs -t backend
```

### Log Files

Application logs are stored in the `glean_logs` volume:

```bash
# View backend logs
docker exec glean-backend tail -f /app/logs/glean-api.log

# View worker logs
docker exec glean-worker tail -f /app/logs/glean-worker.log
```

### Health Checks

All services have health checks configured:

```bash
# Check service health status
docker compose ps

# Inspect specific service health
docker inspect glean-backend --format='{{.State.Health.Status}}'

# View health check logs
docker inspect glean-backend --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### Resource Usage

```bash
# View resource usage
docker stats

# Specific services
docker stats glean-backend glean-postgres glean-redis
```

## Troubleshooting

### Services Won't Start

**Check logs for errors:**

```bash
docker compose logs backend
docker compose logs postgres
```

**Verify health checks:**

```bash
docker compose ps
```

**Common issues:**

1. **Port conflicts**: Change `WEB_PORT` or `ADMIN_PORT` in `.env`
2. **Database connection failed**: Ensure PostgreSQL is healthy before backend starts
3. **Redis connection failed**: Ensure Redis is healthy before worker starts

### Database Connection Errors

**Verify PostgreSQL is healthy:**

```bash
docker compose ps postgres

# Should show: Up (healthy)
```

**Test database connection:**

```bash
docker exec glean-postgres pg_isready -U glean
```

**Check database logs:**

```bash
docker compose logs postgres
```

### Worker Not Fetching Feeds

**Check worker status:**

```bash
docker compose ps worker
docker compose logs worker
```

**Verify Redis connection:**

```bash
docker exec glean-redis redis-cli ping
# Should return: PONG
```

**Manually trigger feed fetch (for debugging):**

```bash
# Access backend container
docker exec -it glean-backend bash

# Trigger feed update via API
curl http://localhost:8000/api/feeds/refresh
```

### Cannot Access Web Interface

**Verify services are running:**

```bash
docker compose ps web backend
```

**Check nginx logs:**

```bash
docker compose logs web
```

**Test backend directly:**

```bash
curl http://localhost/api/health
```

**Common issues:**

1. **Port 80 already in use**: Change `WEB_PORT` in `.env`
2. **Backend not healthy**: Check backend logs
3. **Firewall blocking**: Ensure ports are open

### Admin Dashboard Not Loading

**Verify admin service is running:**

```bash
docker compose ps admin
```

**Check admin service logs:**

```bash
docker compose logs admin
```

**Verify backend connection:**

```bash
curl http://localhost:3001/
```

### High Memory Usage

**Check which service is consuming memory:**

```bash
docker stats
```

**Common causes:**

1. **PostgreSQL cache**: Normal behavior, PostgreSQL uses available RAM for cache
2. **Backend workers**: Adjust uvicorn workers (see [Performance Tuning](#performance-tuning))
3. **Worker tasks**: Large feed fetching batches

### Disk Space Issues

**Check Docker disk usage:**

```bash
docker system df
```

**Clean up unused resources:**

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes (CAUTION: Don't remove glean volumes!)
docker volume prune

# Remove stopped containers
docker container prune
```

**Rotate logs:**

```bash
# Truncate Docker logs
truncate -s 0 $(docker inspect --format='{{.LogPath}}' glean-backend)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' glean-worker)
```

## HTTPS Setup

For production deployments, use HTTPS with a reverse proxy.

### Option 1: Caddy (Recommended)

**Caddyfile:**

```caddy
glean.yourdomain.com {
    reverse_proxy localhost:80
}

admin.yourdomain.com {
    reverse_proxy localhost:3001
}
```

**Start Caddy:**

```bash
caddy run --config Caddyfile
```

Caddy automatically obtains and renews Let's Encrypt certificates.

### Option 2: Nginx with Certbot

**Install Certbot:**

```bash
sudo apt install certbot python3-certbot-nginx
```

**Nginx configuration** (`/etc/nginx/sites-available/glean`):

```nginx
# Web App
server {
    listen 80;
    server_name glean.yourdomain.com;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Admin Dashboard
server {
    listen 80;
    server_name admin.yourdomain.com;

    location / {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable site and get SSL certificate:**

```bash
sudo ln -s /etc/nginx/sites-available/glean /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Obtain SSL certificates
sudo certbot --nginx -d glean.yourdomain.com -d admin.yourdomain.com
```

**Update CORS origins:**

Edit `.env`:

```bash
CORS_ORIGINS='["https://glean.yourdomain.com", "https://admin.yourdomain.com"]'
```

Restart backend:

```bash
docker compose restart backend
```

## Security Best Practices

### 1. Change Default Credentials

**Before production deployment:**

- ✅ Generate strong `SECRET_KEY` (32+ random characters)
- ✅ Change `POSTGRES_PASSWORD`
- ✅ Set strong `ADMIN_PASSWORD`

```bash
# Generate secure SECRET_KEY
openssl rand -hex 32

# Generate secure password
openssl rand -base64 24
```

### 2. Disable Debug Mode

```bash
DEBUG=false
```

This disables the API documentation endpoint (`/api/docs`).

### 3. Restrict CORS Origins

Set `CORS_ORIGINS` to only your actual domains:

```bash
CORS_ORIGINS='["https://yourdomain.com", "https://admin.yourdomain.com"]'
```

### 4. Use HTTPS

Always use HTTPS in production (see [HTTPS Setup](#https-setup)).

### 5. Regular Updates

Keep Docker images up to date:

```bash
# Weekly update routine
docker compose pull
docker compose up -d
```

Subscribe to [Glean releases](https://github.com/LeslieLeung/glean/releases) for security updates.

### 6. Regular Backups

Set up automated daily backups (see [Backup and Restore](#backup-and-restore)).

### 7. Network Security

**Firewall rules:**

```bash
# Allow HTTP/HTTPS only
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# If admin is on different port and should be restricted
sudo ufw deny 3001/tcp
```

**Use Docker secrets for sensitive data (advanced):**

Instead of environment variables, use Docker secrets for production.

### 8. Monitor Logs

Regularly check logs for suspicious activity:

```bash
# Look for failed login attempts
docker compose logs backend | grep "login failed"

# Monitor unusual API calls
docker compose logs backend | grep "ERROR"
```

### 9. Limit Resource Usage

Set resource limits in `docker-compose.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          memory: 512M
```

## Performance Tuning

### Backend Workers

Adjust uvicorn workers based on CPU cores:

Edit `docker-compose.yml`:

```yaml
services:
  backend:
    command: ["uv", "run", "--no-sync", "uvicorn", "glean_api.main:app",
              "--host", "0.0.0.0", "--port", "8000",
              "--workers", "4"]  # Adjust based on CPU cores
```

**Recommendation**: 2 × CPU cores + 1

### Feed Fetch Frequency

The worker fetches feeds every 15 minutes by default.

To adjust, you need to modify the code in `backend/apps/worker/glean_worker/main.py`:

```python
# Default: every 15 minutes
cron_jobs=[cron(scheduled_fetch, minute={0, 15, 30, 45})]

# Hourly
cron_jobs=[cron(scheduled_fetch, minute=0)]

# Every 30 minutes
cron_jobs=[cron(scheduled_fetch, minute={0, 30})]
```

After changes, rebuild the backend image.

### Database Connection Pooling

SQLAlchemy pool settings can be tuned for high-traffic deployments.

Edit `backend/packages/database/glean_database/session.py`:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # Default: 5
    max_overflow=20,       # Default: 10
    pool_pre_ping=True,
    pool_recycle=3600,
)
```

### PostgreSQL Performance

For high-load deployments, tune PostgreSQL settings:

Edit `docker-compose.yml`:

```yaml
services:
  postgres:
    command:
      - postgres
      - -c
      - shared_buffers=256MB
      - -c
      - max_connections=200
      - -c
      - effective_cache_size=1GB
```

### Redis Persistence

If you don't need Redis persistence (task queue only):

```yaml
services:
  redis:
    command: redis-server --save ""  # Disable RDB snapshots
```

This improves performance but tasks will be lost on restart.

### Nginx Caching

For high-traffic deployments, add caching to nginx:

Create custom nginx config for web service:

```nginx
# Custom nginx.conf
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g;

server {
    location /api/ {
        proxy_cache api_cache;
        proxy_cache_valid 200 5m;
        proxy_pass http://backend:8000;
    }
}
```

---

## Additional Resources

- **Documentation**: [README.md](README.md)
- **Development Guide**: [DEVELOPMENT.md](DEVELOPMENT.md)
- **Issue Tracker**: [GitHub Issues](https://github.com/LeslieLeung/glean/issues)
- **Discord Community**: [Join Discord](https://discord.gg/KMKC4sRVSJ)

For questions or issues not covered in this guide, please open an issue on GitHub or join our Discord community.
