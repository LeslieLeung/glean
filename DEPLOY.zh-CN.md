# Glean 部署指南

本指南提供了在生产环境中部署 Glean 的完整说明。

## 目录

- [快速部署](#快速部署)
- [生产环境部署](#生产环境部署)
- [服务架构](#服务架构)
- [环境配置](#环境配置)
- [管理员账号管理](#管理员账号管理)
- [更新 Glean](#更新-glean)
- [备份与恢复](#备份与恢复)
- [监控与日志](#监控与日志)
- [故障排查](#故障排查)
- [HTTPS 配置](#https-配置)
- [安全最佳实践](#安全最佳实践)
- [性能调优](#性能调优)

## 快速部署

### 完整部署（推荐）

包含 Milvus，支持 Phase 3 功能（智能推荐、偏好学习）：

```bash
# 下载 docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.yml -o docker-compose.yml

# 启动所有服务
docker compose up -d

# 访问：
# - Web 应用: http://localhost
# - 管理后台: http://localhost:3001
```

### 精简部署（不含 Milvus）

如果不需要 Phase 3 功能，可以使用精简版：

```bash
# 下载精简版
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.lite.yml -o docker-compose.yml

# 启动服务
docker compose up -d
```

**后续步骤：**
1. 创建管理员账号（参见[管理员账号管理](#管理员账号管理)）
2. 配置生产环境变量（参见[环境配置](#环境配置)）

## 生产环境部署

### 前置要求

- Docker Engine 24.0+ 和 Docker Compose V2
- 至少 2GB 内存和 10GB 磁盘空间
- 域名（推荐用于 HTTPS）
- 反向代理（nginx/Caddy）用于 HTTPS（推荐）

### 分步设置指南

#### 1. 下载部署文件

```bash
# 创建部署目录
mkdir -p ~/glean && cd ~/glean

# 下载 docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.yml -o docker-compose.yml

# 下载环境变量模板
curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/.env.example -o .env
```

#### 2. 配置环境变量

编辑 `.env` 并设置安全的值：

```bash
nano .env
```

**必须修改的关键配置：**

```bash
# JWT 密钥 - 必须修改！
# 生成方法: openssl rand -hex 32
SECRET_KEY=your-long-random-secret-key-here

# 数据库凭据
POSTGRES_PASSWORD=your-secure-database-password

# 管理员账号（首次启动时自动创建）
CREATE_ADMIN=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!

# 端口（按需调整）
WEB_PORT=80
ADMIN_PORT=3001

# 生产环境禁用调试模式
DEBUG=false
```

所有可用选项请参见[环境配置](#环境配置)。

#### 3. 启动服务

```bash
# 以分离模式启动所有服务
docker compose up -d

# 验证所有服务正在运行
docker compose ps
```

预期输出：
```
NAME              IMAGE                                    STATUS
glean-admin       ghcr.io/leslieleung/glean-admin:latest   Up (healthy)
glean-backend     ghcr.io/leslieleung/glean-backend:latest Up (healthy)
glean-postgres    postgres:16-alpine                       Up (healthy)
glean-redis       redis:8-alpine                           Up (healthy)
glean-web         ghcr.io/leslieleung/glean-web:latest     Up
glean-worker      ghcr.io/leslieleung/glean-backend:latest Up
```

#### 4. 验证部署

```bash
# 检查后端健康状态
curl http://localhost/api/health

# 查看日志
docker compose logs -f

# 验证管理员账号已创建（如果 CREATE_ADMIN=true）
docker compose logs backend | grep "Admin Account Created"
```

#### 5. 访问 Glean

- **Web 应用**: `http://localhost`（或 `http://your-server-ip`）
- **管理后台**: `http://localhost:3001`
- **API 文档**: `http://localhost/api/docs`（如果 DEBUG=true）

## 服务架构

### 完整部署

Glean 由 Docker Compose 编排的 9 个服务组成：

**核心服务：**

| 服务       | 容器名称       | 说明                           | 依赖关系        |
| ---------- | -------------- | ------------------------------ | --------------- |
| postgres   | glean-postgres | PostgreSQL 16 数据库           | -               |
| redis      | glean-redis    | Redis 8 任务队列               | -               |
| backend    | glean-backend  | FastAPI REST API 服务器        | postgres, redis |
| worker     | glean-worker   | arq 后台工作进程（订阅源同步） | postgres, redis |
| web        | glean-web      | React Web 前端（nginx）        | backend         |
| admin      | glean-admin    | 管理后台（nginx）              | backend         |

**Milvus 服务（Phase 3 功能）：**

| 服务          | 容器名称            | 说明                       | 依赖关系           |
| ------------- | ------------------- | -------------------------- | ------------------ |
| milvus-etcd   | glean-milvus-etcd   | etcd 协调服务              | -                  |
| milvus-minio  | glean-milvus-minio  | MinIO 对象存储             | -                  |
| milvus        | glean-milvus        | 向量数据库（用于 embedding）| milvus-etcd, minio |

**服务启动顺序：**
1. `postgres` 和 `redis` 首先启动（带健康检查）
2. `backend` 在数据库/Redis 健康后启动（运行迁移）
3. `worker` 在后端健康后启动
4. `web` 和 `admin` 在后端就绪后启动
5. `milvus-etcd` 和 `milvus-minio` 并行启动，然后是 `milvus`

### 精简部署

不包含 Milvus 服务（共 6 个服务）。使用 `docker-compose.lite.yml` 配置。

**数据持久化：**
- `postgres_data` - PostgreSQL 数据库文件
- `redis_data` - Redis 持久化（AOF）
- `glean_logs` - 应用日志（backend + worker）
- `milvus_etcd_data` - Milvus etcd 数据（可选）
- `milvus_minio_data` - Milvus 对象存储（可选）
- `milvus_data` - Milvus 向量数据库（可选）

**网络：**
- 所有服务通过 `glean-network` 桥接网络通信
- 仅 `web`（端口 80）、`admin`（端口 3001）和可选的 `milvus`（端口 19530）暴露到宿主机

## 环境配置

### 核心设置

| 变量                | 必需 | 默认值                       | 说明                          |
| ------------------- | ---- | ---------------------------- | ----------------------------- |
| `SECRET_KEY`        | 是   | `change-me-in-production...` | JWT 签名密钥（至少 32 字符）  |
| `POSTGRES_DB`       | 否   | `glean`                      | 数据库名称                    |
| `POSTGRES_USER`     | 否   | `glean`                      | 数据库用户名                  |
| `POSTGRES_PASSWORD` | 是   | `glean`                      | 数据库密码                    |
| `DEBUG`             | 否   | `false`                      | 启用调试模式和 API 文档       |

### 端口配置

| 变量         | 默认值 | 说明             |
| ------------ | ------ | ---------------- |
| `WEB_PORT`   | `80`   | Web 界面端口     |
| `ADMIN_PORT` | `3001` | 管理后台端口     |

### 管理员账号自动创建

| 变量              | 默认值        | 说明                       |
| ----------------- | ------------- | -------------------------- |
| `CREATE_ADMIN`    | `false`       | 首次启动时自动创建管理员   |
| `ADMIN_USERNAME`  | `admin`       | 管理员用户名               |
| `ADMIN_PASSWORD`  | -             | 管理员密码（启用时必需）   |
| `ADMIN_ROLE`      | `super_admin` | 管理员角色                 |

### 日志配置

| 变量              | 默认值                    | 说明                          |
| ----------------- | ------------------------- | ----------------------------- |
| `LOG_LEVEL`       | `INFO`                    | 日志级别（DEBUG/INFO/WARNING）|
| `LOG_FILE`        | `/app/logs/glean-api.log` | 日志文件路径（backend）       |
| `LOG_ROTATION`    | `100 MB`                  | 日志轮转大小                  |
| `LOG_RETENTION`   | `30 days`                 | 日志保留期限                  |
| `LOG_COMPRESSION` | `gz`                      | 日志压缩格式                  |

### Milvus 配置（Phase 3 功能）

Milvus 是可选的，提供向量数据库功能用于智能推荐和偏好学习。

**启用 Milvus：**
```bash
docker compose --profile milvus up -d
```

**Milvus 连接设置：**

| 变量                        | 默认值          | 说明                           |
| --------------------------- | --------------- | ------------------------------ |
| `MILVUS_HOST`               | `localhost`     | Milvus 服务器地址              |
| `MILVUS_PORT`               | `19530`         | Milvus 服务器端口              |
| `MILVUS_USER`               | -               | Milvus 用户名（如启用认证）    |
| `MILVUS_PASSWORD`           | -               | Milvus 密码（如启用认证）      |
| `MILVUS_ENTRIES_COLLECTION` | `entries`       | 文章向量集合名称               |
| `MILVUS_PREFS_COLLECTION`   | `user_preferences` | 用户偏好集合名称            |

### Embedding 配置（Phase 3 功能）

使用 Milvus 进行智能推荐时需要配置：

| 变量                   | 默认值                  | 说明                                              |
| ---------------------- | ----------------------- | ------------------------------------------------- |
| `EMBEDDING_PROVIDER`   | `sentence-transformers` | 提供商：sentence-transformers、openai、volc-engine |
| `EMBEDDING_MODEL`      | `all-MiniLM-L6-v2`      | 模型名称                                          |
| `EMBEDDING_DIMENSION`  | `384`                   | 向量维度（必须匹配模型）                          |
| `EMBEDDING_API_KEY`    | -                       | API 密钥（用于 openai/volc-engine）               |
| `EMBEDDING_BASE_URL`   | -                       | 自定义 API 端点（可选）                           |
| `EMBEDDING_BATCH_SIZE` | `20`                    | embedding 生成批次大小                            |
| `EMBEDDING_MAX_RETRIES`| `3`                     | 失败请求最大重试次数                              |
| `EMBEDDING_TIMEOUT`    | `30`                    | 请求超时时间（秒）                                |

**支持的提供商：**
- **sentence-transformers** - 本地 embedding 模型（无需 API 密钥）
  - 模型：`all-MiniLM-L6-v2` (384维)、`paraphrase-multilingual-MiniLM-L12-v2` (384维)
- **openai** - OpenAI embedding API
  - 模型：`text-embedding-3-small` (1536维)、`text-embedding-3-large` (3072维)
  - 需要：`EMBEDDING_API_KEY`
- **volc-engine** - 火山引擎/字节跳动 embedding API
  - 模型：`doubao-embedding` (1024维)
  - 需要：`EMBEDDING_API_KEY` 或 `ARK_API_KEY`

完整配置参考请见 [.env.example](.env.example)。

## 管理员账号管理

### 首次启动时自动创建

在 `.env` 中设置环境变量：

```bash
CREATE_ADMIN=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!
```

然后启动服务：

```bash
docker compose up -d

# 验证管理员已创建
docker compose logs backend | grep "Admin Account Created"
```

### 部署后手动创建

```bash
# 生成随机密码（推荐）
docker exec -it glean-backend /app/scripts/create-admin-docker.sh

# 指定自定义凭据
docker exec -it glean-backend /app/scripts/create-admin-docker.sh myusername MySecurePass123!
```

### 密码要求

管理员密码必须满足以下条件：
- 至少 8 个字符
- 包含至少一个大写字母
- 包含至少一个小写字母
- 包含至少一个数字
- 包含至少一个特殊字符

## 更新 Glean

### 更新到最新版本

```bash
# 拉取最新镜像
docker compose pull

# 使用新镜像重启服务
docker compose up -d

# 数据库迁移会在后端启动时自动运行
# 验证服务健康
docker compose ps
```

### 更新到特定版本

```bash
# 编辑 docker-compose.yml 并修改镜像标签
# 例如: ghcr.io/leslieleung/glean-backend:v1.2.3

# 拉取并重启
docker compose pull
docker compose up -d
```

### 回滚到先前版本

```bash
# 停止服务
docker compose down

# 编辑 docker-compose.yml 使用之前的镜像标签

# 使用之前的版本启动
docker compose up -d
```

## 备份与恢复

### 数据库备份

**自动备份脚本：**

```bash
#!/bin/bash
# backup-glean.sh

BACKUP_DIR="$HOME/glean-backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# 备份 PostgreSQL
docker exec glean-postgres pg_dump -U glean glean | gzip > "$BACKUP_DIR/glean_db_$DATE.sql.gz"

# 备份卷
docker run --rm \
  -v glean_postgres_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/postgres_data_$DATE.tar.gz -C /data .

docker run --rm \
  -v glean_redis_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/redis_data_$DATE.tar.gz -C /data .

echo "备份完成: $BACKUP_DIR"
```

使其可执行并运行：

```bash
chmod +x backup-glean.sh
./backup-glean.sh
```

**使用 cron 设置每日备份：**

```bash
# 编辑 crontab
crontab -e

# 添加每天凌晨 2 点的备份任务
0 2 * * * /path/to/backup-glean.sh
```

### 数据库恢复

**从 SQL 转储恢复：**

```bash
# 停止服务
docker compose down

# 仅启动 PostgreSQL
docker compose up -d postgres

# 恢复数据库
gunzip -c glean_db_20250101_020000.sql.gz | docker exec -i glean-postgres psql -U glean -d glean

# 重启所有服务
docker compose up -d
```

**从卷备份恢复：**

```bash
# 停止服务
docker compose down

# 删除旧卷
docker volume rm glean_postgres_data

# 创建新卷
docker volume create glean_postgres_data

# 从备份恢复
docker run --rm \
  -v glean_postgres_data:/data \
  -v "$HOME/glean-backups":/backup \
  alpine tar xzf /backup/postgres_data_20250101_020000.tar.gz -C /data

# 启动服务
docker compose up -d
```

## 监控与日志

### 查看日志

```bash
# 所有服务（跟踪模式）
docker compose logs -f

# 特定服务
docker compose logs -f backend
docker compose logs -f worker

# 最后 100 行
docker compose logs --tail=100 backend

# 带时间戳的日志
docker compose logs -t backend
```

### 日志文件

应用日志存储在 `glean_logs` 卷中：

```bash
# 查看后端日志
docker exec glean-backend tail -f /app/logs/glean-api.log

# 查看 worker 日志
docker exec glean-worker tail -f /app/logs/glean-worker.log
```

### 健康检查

所有服务都配置了健康检查：

```bash
# 检查服务健康状态
docker compose ps

# 检查特定服务健康状态
docker inspect glean-backend --format='{{.State.Health.Status}}'

# 查看健康检查日志
docker inspect glean-backend --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### 资源使用

```bash
# 查看资源使用情况
docker stats

# 特定服务
docker stats glean-backend glean-postgres glean-redis
```

## 故障排查

### 服务无法启动

**检查错误日志：**

```bash
docker compose logs backend
docker compose logs postgres
```

**验证健康检查：**

```bash
docker compose ps
```

**常见问题：**

1. **端口冲突**: 在 `.env` 中修改 `WEB_PORT` 或 `ADMIN_PORT`
2. **数据库连接失败**: 确保 PostgreSQL 在后端启动前健康
3. **Redis 连接失败**: 确保 Redis 在 worker 启动前健康

### 数据库连接错误

**验证 PostgreSQL 健康：**

```bash
docker compose ps postgres

# 应该显示: Up (healthy)
```

**测试数据库连接：**

```bash
docker exec glean-postgres pg_isready -U glean
```

**检查数据库日志：**

```bash
docker compose logs postgres
```

### Worker 不抓取订阅源

**检查 worker 状态：**

```bash
docker compose ps worker
docker compose logs worker
```

**验证 Redis 连接：**

```bash
docker exec glean-redis redis-cli ping
# 应该返回: PONG
```

**手动触发订阅源抓取（用于调试）：**

```bash
# 进入后端容器
docker exec -it glean-backend bash

# 通过 API 触发订阅源更新
curl http://localhost:8000/api/feeds/refresh
```

### 无法访问 Web 界面

**验证服务正在运行：**

```bash
docker compose ps web backend
```

**检查 nginx 日志：**

```bash
docker compose logs web
```

**直接测试后端：**

```bash
curl http://localhost/api/health
```

**常见问题：**

1. **端口 80 已被占用**: 在 `.env` 中修改 `WEB_PORT`
2. **后端不健康**: 检查后端日志
3. **防火墙阻止**: 确保端口已开放

### 管理后台无法加载

**验证 admin 服务正在运行：**

```bash
docker compose ps admin
```

**检查 admin 服务日志：**

```bash
docker compose logs admin
```

**验证后端连接：**

```bash
curl http://localhost:3001/
```

### 内存使用过高

**检查哪个服务消耗内存：**

```bash
docker stats
```

**常见原因：**

1. **PostgreSQL 缓存**: 正常行为，PostgreSQL 使用可用 RAM 作为缓存
2. **后端 workers**: 调整 uvicorn workers（参见[性能调优](#性能调优)）
3. **Worker 任务**: 大批量订阅源抓取

### 磁盘空间问题

**检查 Docker 磁盘使用：**

```bash
docker system df
```

**清理未使用的资源：**

```bash
# 删除未使用的镜像
docker image prune -a

# 删除未使用的卷（注意：不要删除 glean 卷！）
docker volume prune

# 删除已停止的容器
docker container prune
```

**轮转日志：**

```bash
# 截断 Docker 日志
truncate -s 0 $(docker inspect --format='{{.LogPath}}' glean-backend)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' glean-worker)
```

## HTTPS 配置

对于生产环境部署，使用反向代理配置 HTTPS。

### 选项 1: Caddy（推荐）

**Caddyfile:**

```caddy
glean.yourdomain.com {
    reverse_proxy localhost:80
}

admin.yourdomain.com {
    reverse_proxy localhost:3001
}
```

**启动 Caddy:**

```bash
caddy run --config Caddyfile
```

Caddy 会自动获取和续期 Let's Encrypt 证书。

### 选项 2: Nginx with Certbot

**安装 Certbot:**

```bash
sudo apt install certbot python3-certbot-nginx
```

**Nginx 配置** (`/etc/nginx/sites-available/glean`):

```nginx
# Web 应用
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

# 管理后台
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

**启用站点并获取 SSL 证书：**

```bash
sudo ln -s /etc/nginx/sites-available/glean /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 获取 SSL 证书
sudo certbot --nginx -d glean.yourdomain.com -d admin.yourdomain.com
```

**更新 CORS 源：**

编辑 `.env`:

```bash
CORS_ORIGINS='["https://glean.yourdomain.com", "https://admin.yourdomain.com"]'
```

重启后端：

```bash
docker compose restart backend
```

## 安全最佳实践

### 1. 修改默认凭据

**生产环境部署前：**

- ✅ 生成强 `SECRET_KEY`（32+ 随机字符）
- ✅ 修改 `POSTGRES_PASSWORD`
- ✅ 设置强 `ADMIN_PASSWORD`

```bash
# 生成安全的 SECRET_KEY
openssl rand -hex 32

# 生成安全的密码
openssl rand -base64 24
```

### 2. 禁用调试模式

```bash
DEBUG=false
```

这会禁用 API 文档端点（`/api/docs`）。

### 3. 限制 CORS 源

将 `CORS_ORIGINS` 设置为仅您的实际域名：

```bash
CORS_ORIGINS='["https://yourdomain.com", "https://admin.yourdomain.com"]'
```

### 4. 使用 HTTPS

生产环境始终使用 HTTPS（参见 [HTTPS 配置](#https-配置)）。

### 5. 定期更新

保持 Docker 镜像最新：

```bash
# 每周更新例程
docker compose pull
docker compose up -d
```

订阅 [Glean 发布](https://github.com/LeslieLeung/glean/releases) 以获取安全更新。

### 6. 定期备份

设置每日自动备份（参见[备份与恢复](#备份与恢复)）。

### 7. 网络安全

**防火墙规则：**

```bash
# 仅允许 HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 如果 admin 在不同端口且应受限
sudo ufw deny 3001/tcp
```

**使用 Docker secrets 存储敏感数据（高级）：**

生产环境中使用 Docker secrets 替代环境变量。

### 8. 监控日志

定期检查日志中的可疑活动：

```bash
# 查找失败的登录尝试
docker compose logs backend | grep "login failed"

# 监控异常 API 调用
docker compose logs backend | grep "ERROR"
```

### 9. 限制资源使用

在 `docker-compose.yml` 中设置资源限制：

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

## 性能调优

### 后端 Workers

根据 CPU 核心数调整 uvicorn workers：

编辑 `docker-compose.yml`:

```yaml
services:
  backend:
    command: ["uv", "run", "--no-sync", "uvicorn", "glean_api.main:app",
              "--host", "0.0.0.0", "--port", "8000",
              "--workers", "4"]  # 根据 CPU 核心数调整
```

**推荐配置**: 2 × CPU 核心数 + 1

### 订阅源抓取频率

Worker 默认每 15 分钟抓取一次订阅源。

要调整频率，需要修改 `backend/apps/worker/glean_worker/main.py` 中的代码：

```python
# 默认: 每 15 分钟
cron_jobs=[cron(scheduled_fetch, minute={0, 15, 30, 45})]

# 每小时
cron_jobs=[cron(scheduled_fetch, minute=0)]

# 每 30 分钟
cron_jobs=[cron(scheduled_fetch, minute={0, 30})]
```

修改后需要重新构建后端镜像。

### 数据库连接池

对于高流量部署，可以调整 SQLAlchemy 连接池设置。

编辑 `backend/packages/database/glean_database/session.py`:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # 默认: 5
    max_overflow=20,       # 默认: 10
    pool_pre_ping=True,
    pool_recycle=3600,
)
```

### PostgreSQL 性能

对于高负载部署，调整 PostgreSQL 设置：

编辑 `docker-compose.yml`:

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

### Redis 持久化

如果不需要 Redis 持久化（仅任务队列）：

```yaml
services:
  redis:
    command: redis-server --save ""  # 禁用 RDB 快照
```

这会提高性能但重启时任务会丢失。

### Nginx 缓存

对于高流量部署，为 nginx 添加缓存：

为 web 服务创建自定义 nginx 配置：

```nginx
# 自定义 nginx.conf
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

## 其他资源

- **文档**: [README.zh-CN.md](README.zh-CN.md)
- **开发指南**: [DEVELOPMENT.md](DEVELOPMENT.md)
- **问题追踪**: [GitHub Issues](https://github.com/LeslieLeung/glean/issues)
- **Discord 社区**: [加入 Discord](https://discord.gg/KMKC4sRVSJ)

如有本指南未涵盖的问题，请在 GitHub 上提交 issue 或加入我们的 Discord 社区。
