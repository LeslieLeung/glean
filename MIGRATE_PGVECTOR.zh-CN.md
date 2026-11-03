# 将现有 Milvus 部署迁移到 pgvector

[English](MIGRATE_PGVECTOR.md)

在原部署目录执行一条命令：

```bash
python3 scripts/migrate-to-pgvector.py migrate --image-tag RELEASE_IMAGE_TAG
```

把 `RELEASE_IMAGE_TAG` 替换为支持 pgvector 的已发布镜像标签，使用固定版本，不要用
`latest`。API、worker、web 和 admin 会一起升级。维护窗口内请关闭外部访问。

## 前置条件

- Linux、Python 3.11+、Docker，以及较新的 Docker Compose V2 或更新版本。
- 当前 Glean 正在运行，使用本机 PostgreSQL 16、本机 Redis、命名数据卷和标准的六个
  核心服务，可包含 Milvus 服务。
- 在原部署目录使用原 Compose 文件和环境配置执行。默认读取 `docker-compose.yml`，
  并沿用 Compose 的 `.env` 加载规则。已有 embedding 校验或重建任务时，请先等待完成。
- 磁盘空间足够保存数据库备份、恢复后的数据库及新向量。保留日常独立备份；
  脚本保留的本机旧卷不等于异地备份。

如果之前只下载了 Compose 文件，请先从目标发布版本下载脚本：

```bash
release_ref='RELEASE_GIT_TAG'
mkdir -p scripts
curl -fSL "https://raw.githubusercontent.com/LeslieLeung/glean/${release_ref}/scripts/migrate-to-pgvector.py" \
  -o scripts/migrate-to-pgvector.py
```

## 可选：先检查环境

```bash
python3 scripts/migrate-to-pgvector.py migrate --image-tag RELEASE_IMAGE_TAG --dry-run
```

检查运行中的服务、PostgreSQL 版本、配置一致性、数据卷及 embedding 状态，不停止服务、
不创建备份。此检查不下载镜像，也不验证 embedding 服务商的凭据和额度。

使用自定义 Compose 文件时，按原合并顺序重复传入 `--compose`。这些参数只需首次执行时提供：

```bash
python3 scripts/migrate-to-pgvector.py migrate --image-tag RELEASE_IMAGE_TAG \
  --compose docker-compose.yml --compose docker-compose.production.yml \
  --env-file .env.production --project-name glean
```

脚本会拒绝外部 PostgreSQL/Redis、数据库或队列使用绑定挂载、额外的非标准服务、
Compose profiles 和其他 PostgreSQL 主版本。这些部署需要调整迁移方案。
已提前下载镜像时，可加 `--skip-pull`。

## 脚本会自动处理什么

脚本保存解析后的配置，固定实际运行的旧镜像，保留凭据、端口、反向代理、网络和自定义
环境设置。先下载新镜像，再停止旧应用、导出 PostgreSQL、检查备份归档并停止旧部署。

随后恢复到全新的 PostgreSQL 16 pgvector 数据卷，启用新的 Redis 队列，保留全部旧
PostgreSQL、Redis 和 Milvus 数据卷。逻辑备份恢复避免直接跨 Alpine/Debian 镜像复用
旧数据库目录。启动应用前会比较业务表记录数量，并在新数据库启用 `vector` 扩展。

最后，新 API 自动执行 Alembic 迁移，worker 等待后端健康后启动。如果原来开启了
embedding，Glean 会自动校验、重新生成文章向量，再根据保留的历史重建用户偏好。
Milvus 向量会重新计算，不直接复制，因此可能产生 embedding API 费用。
旧队列任务不会搬迁；新版 worker 会恢复定时抓取。

服务健康后脚本结束。请在管理后台「设置 → Embedding」等待 `idle`（正常运行），
检查失败文章，并验证文章、订阅、收藏、阅读状态、推荐和智能排序。
原来未启用的向量化不会自动开启。重建报错时，先查看后台错误和 worker 日志，修复后通过
embedding 管理界面或 API 重试。

## 失败后继续、查看状态和回滚

中断或失败后，修复问题，在相同目录继续执行：

```bash
python3 scripts/migrate-to-pgvector.py migrate
python3 scripts/migrate-to-pgvector.py status
```

脚本保存检查点，不会重复执行已完成的恢复。尚未完成的恢复只会重建经过卷检查的新目标
数据库；保存恢复完成的检查点后，重试不会丢弃应用后续的新写入。
报错时会保留现场，不自动切回旧部署。

需要恢复到迁移前的旧镜像和旧数据卷时：

```bash
python3 scripts/migrate-to-pgvector.py rollback
```

回滚保留新卷，但迁移后产生的新写入不会出现在旧部署中。
脚本会一起恢复旧数据库结构、旧队列、旧镜像和 Milvus，不要只修改镜像版本来回滚。

## 迁移后如何管理部署

原 Compose 和 `.env` 文件保持不变。后续使用脚本的 Compose 入口操作保存的当前配置：

```bash
python3 scripts/migrate-to-pgvector.py compose ps
python3 scripts/migrate-to-pgvector.py compose logs --tail=100 backend worker
python3 scripts/migrate-to-pgvector.py compose up -d
```

迁移状态、数据库备份和配置快照保存在 `.glean-pgvector-migration/`，有权限保护并已加入
Git 忽略规则。确认迁移成功前，不要删除该目录或回滚镜像标签。
快照包含凭据，请勿公开。继续使用该入口，或先将保存的配置整理为正式部署配置，
再恢复普通 `docker compose` 操作。回滚后，该入口会自动使用旧配置。

可选的全局参数 `--state-dir PATH` 可以指定其他状态目录；每次都需要放在 `migrate`、
`status`、`rollback` 或 `compose` 前。回滚后重新迁移时，请指定新状态目录，重新备份。
脚本不会删除任何数据卷。确认迁移成功且保有独立备份后，再手工清理旧卷。
