# Glean 开发指南

[English](DEVELOPMENT.md)

本指南介绍如何在本地从源码运行 Glean。使用已发布的镜像自托管时，请参阅[部署指南](DEPLOY.zh-CN.md)。

## 环境要求

- Python 3.11 和 uv，用于后端开发
- Node.js 24.15.0 或更新的 24.x 版本，含 npm
- pnpm，版本以 [frontend/package.json](frontend/package.json) 为准
- Docker（含 Docker Compose v2）和 Make

Python 3.11 和 Node.js 24 与 CI 使用的版本一致。使用 Node.js 24 时，前端测试依赖要求至少为 24.15.0。

## 本地搭建

先克隆仓库，再进入根目录安装依赖。

```bash
git clone https://github.com/LeslieLeung/glean.git
cd glean
UV_PYTHON=3.11 make install
test -e .env || cp .env.example .env
```

`make install` 会安装根目录的 npm 依赖，通过 uv 安装后端工作区的所有包，并通过 pnpm 安装前端工作区的依赖。

在根目录的 `.env` 中取消 `DATABASE_URL` 的注释，使用下方连接地址。设置 `DEBUG=true` 后即可访问交互式 API 文档。

```dotenv
DATABASE_URL=postgresql+asyncpg://glean:devpassword@localhost:5432/glean
DEBUG=true
```

启动带 pgvector 扩展的 PostgreSQL 和 Redis，应用数据库迁移，再启动 API、Worker、Web 应用和管理后台。

```bash
docker compose -f docker-compose.dev.pgvector.yml up -d --wait
make db-upgrade
make dev-all
```

| 服务                            | 本地地址                           |
| ------------------------------- | ---------------------------------- |
| Web 应用                        | <http://localhost:3000>            |
| 管理后台                        | <http://localhost:3001>            |
| API 健康检查                    | <http://localhost:8000/api/health> |
| API 文档（需启用 `DEBUG=true`） | <http://localhost:8000/api/docs>   |

也可以在不同终端分别运行 `make api`、`make worker`、`make web` 或 `make admin`。开发桌面端时，先启动本地 API，再运行 `make electron`。

上述配置使用 `VECTOR_BACKEND=pgvector`。开发 Milvus 相关功能时，用 `make up` 启动依赖，并在 `.env` 中设置 `VECTOR_BACKEND=milvus` 和 `MILVUS_HOST=localhost`。两套 Compose 配置共用容器名称和宿主机端口，切换前先停止正在运行的一套。

按 Ctrl+C 停止应用进程，再运行 `docker compose -f docker-compose.dev.pgvector.yml down` 停止 pgvector 环境。使用 Milvus 时运行 `make down`。

## 本地管理员账号

应用数据库迁移后，在仓库根目录运行以下命令创建管理员。

```bash
(cd backend && uv run python scripts/create-admin.py)
```

使用本地默认账号 `admin` 和密码 `Admin123!` 登录管理后台。可通过脚本参数 `--username` 和 `--password` 自定义凭据。阅读器使用独立账号，可在 Web 应用中注册。

如果脚本在显示 `Admin user created successfully!` 后报 `'str' object has no attribute 'value'`，账号已保存，错误发生在打印角色时。可以用刚才设置的凭据登录。

使用自定义数据库时，先在终端中导出 `DATABASE_URL`，再运行管理员脚本或数据库迁移命令。这些命令读取 shell 环境变量，未设置时使用默认的本地数据库。

## 数据库迁移

修改 SQLAlchemy 模型后，生成迁移并检查内容，再应用迁移。迁移文件位于 [backend/packages/database/glean_database/migrations/versions](backend/packages/database/glean_database/migrations/versions)。

```bash
make db-migrate MSG="describe the schema change"
make db-upgrade
```

## 测试与代码检查

```bash
make test
make test ARGS="-k auth"
(cd frontend && pnpm test)
make lint
(cd frontend && pnpm typecheck)
```

`make test` 会在 5433 端口启动独立的 PostgreSQL 测试实例。`make test-cov` 会在 `backend/htmlcov/` 生成 HTML 覆盖率报告。运行 `make test-db-down` 可以停止测试数据库并删除其数据卷。

使用 `make format` 格式化代码，使用 `(cd frontend && pnpm build)` 构建前端。安装 pre-commit 后，可用 `make pre-commit-install` 安装 Git 钩子，用 `make pre-commit-run` 手动执行检查，用 `make pre-commit-uninstall` 卸载钩子。

## 仓库结构

| 路径                                       | 内容                                   |
| ------------------------------------------ | -------------------------------------- |
| [backend/apps/api](backend/apps/api)       | FastAPI 服务                           |
| [backend/apps/worker](backend/apps/worker) | 后台任务                               |
| [backend/packages](backend/packages)       | 数据库、核心业务、RSS 和向量相关共享包 |
| [frontend/apps/web](frontend/apps/web)     | 阅读器和 Electron 桌面端               |
| [frontend/apps/admin](frontend/apps/admin) | 管理后台                               |
| [frontend/packages](frontend/packages)     | 共享 UI、API 客户端、类型、翻译和日志  |

代码风格和 Pull Request 约定见[仓库开发规范](AGENTS.md)。
