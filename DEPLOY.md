# Glean Deployment Guide

This guide provides instructions for deploying Glean in different environments.

## Development Environment

For local development with Docker:

```bash
# Start PostgreSQL, Redis and Milvus
docker compose -f docker-compose.dev.yml up -d

# Run backend services locally
make api    # Terminal 1
make worker # Terminal 2
make web    # Terminal 3
```

## Production Deployment

### Prerequisites

- Docker and Docker Compose installed
- Domain name (optional, for HTTPS)
- Reverse proxy (nginx/Caddy) for HTTPS (optional)

### Setup Steps

1. **Copy environment configuration**

```bash
cp deploy/.env.prod.example .env.prod
```

2. **Edit `.env.prod` and set secure values**

Important fields to change:
- `POSTGRES_PASSWORD` - Strong database password
- `REDIS_PASSWORD` - Strong Redis password
- `SECRET_KEY` - Long random string for JWT signing
- `CORS_ORIGINS` - Your frontend domain(s) in JSON array format
- `WEB_PORT` - Port for the web interface (default: 80)

3. **Build and start services**

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d --build
```

4. **Run database migrations**

```bash
docker exec -it glean-backend uv run alembic -c packages/database/alembic.ini upgrade head
```

5. **Verify services are running**

```bash
docker compose -f deploy/docker-compose.prod.yml ps

# Check logs
docker compose -f deploy/docker-compose.prod.yml logs -f
```

6. **Access the application**

- Web interface: `http://localhost` (or your configured WEB_PORT)
- API docs: `http://localhost/api/docs`

### Service Architecture

The production deployment includes:

- **postgres** - PostgreSQL database
- **redis** - Redis for task queue
- **backend** - FastAPI application (4 workers via uvicorn)
- **worker** - arq background worker for feed fetching
- **frontend** - Nginx serving React app with API proxy

### Updating the Application

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d --build

# Run new migrations if any
docker exec -it glean-backend uv run alembic -c packages/database/alembic.ini upgrade head
```

### Backup and Restore

**Backup database:**

```bash
docker exec glean-postgres pg_dump -U glean glean > glean_backup_$(date +%Y%m%d).sql
```

**Restore database:**

```bash
cat glean_backup_YYYYMMDD.sql | docker exec -i glean-postgres psql -U glean -d glean
```

**Backup volumes:**

```bash
docker run --rm -v deploy_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data_backup.tar.gz -C /data .
docker run --rm -v deploy_redis_data:/data -v $(pwd):/backup alpine tar czf /backup/redis_data_backup.tar.gz -C /data .
```

### Monitoring

View logs:

```bash
# All services
docker compose -f deploy/docker-compose.prod.yml logs -f

# Specific service
docker compose -f deploy/docker-compose.prod.yml logs -f backend
docker compose -f deploy/docker-compose.prod.yml logs -f worker
```

### Troubleshooting

**Services won't start:**

Check logs for specific errors:
```bash
docker compose -f deploy/docker-compose.prod.yml logs backend
```

**Database connection errors:**

Verify PostgreSQL is healthy:
```bash
docker compose -f deploy/docker-compose.prod.yml ps postgres
```

**Worker not fetching feeds:**

Check worker logs and Redis connection:
```bash
docker compose -f deploy/docker-compose.prod.yml logs worker
docker exec -it glean-redis redis-cli -a YOUR_REDIS_PASSWORD ping
```

### HTTPS Configuration (Recommended)

For production, use a reverse proxy like Caddy or nginx with Let's Encrypt.

**Example Caddy configuration:**

```caddy
yourdomain.com {
    reverse_proxy localhost:80
}
```

**Example nginx configuration:**

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Security Recommendations

1. Change all default passwords in `.env.prod`
2. Use strong SECRET_KEY (at least 32 random characters)
3. Set up HTTPS with valid SSL certificate
4. Restrict CORS_ORIGINS to your actual domain
5. Keep Docker images updated
6. Regular database backups
7. Monitor logs for suspicious activity
8. Consider using Docker secrets for sensitive data

### Performance Tuning

**Backend workers:**

Adjust uvicorn workers in `deploy/docker-compose.prod.yml`:
```yaml
command: ["uv", "run", "uvicorn", "glean_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Feed fetch frequency:**

Edit `backend/apps/worker/glean_worker/main.py` and adjust the cron schedule:
```python
cron_jobs=[cron(scheduled_fetch, minute={0, 15, 30, 45})]
```

**Database connection pooling:**

SQLAlchemy pool settings can be adjusted in database session configuration.
