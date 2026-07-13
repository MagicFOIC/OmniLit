# OmniLit 0.1.0 多用户生产部署

本文对应 Ubuntu/Debian、Docker Compose、Caddy 同域名 HTTPS 部署。公网只开放 `80/443`；Caddy 将 `/` 转发到 Web，将 `/v1/*` 转发到 Cloud API。PostgreSQL、ClamAV、备份服务和可选 Prometheus 均不直接暴露公网。

## 服务器要求

- 最低建议：4 vCPU、8 GB RAM；ClamAV 启动和更新病毒库时会占用较多内存。
- 磁盘容量至少覆盖 PostgreSQL、所有账户私有配额、公共存储池、隔离区和本地备份。
- 域名的 A/AAAA 记录已指向服务器，安全组开放 TCP 80/443 和 UDP 443。
- 安装 Docker Engine 与 Compose v2。部署用户能运行 `docker compose`，仓库和 `deploy/secrets` 仅该用户可读。

## 1. 准备配置和密钥

```bash
git clone <你的 OmniLit 仓库地址> /opt/omnilit
cd /opt/omnilit
cp deploy/.env.example deploy/.env
mkdir -p deploy/secrets
chmod 700 deploy/secrets
openssl rand -base64 32 | tr -d '\n' > deploy/secrets/postgres-password.txt
openssl rand -base64 32 | tr -d '\n' > deploy/secrets/cloud-data-key.txt
openssl rand -hex 32 | tr -d '\n' > deploy/secrets/cloud-metrics-token.txt
openssl rand -base64 32 | tr -d '\n' > deploy/secrets/restic-password.txt
chmod 600 deploy/secrets/*.txt
```

另外创建 `turnstile-secret.txt`、`smtp-password.txt`、`s3-access-key.txt` 和 `s3-secret-key.txt`。编辑 `deploy/.env`：

- `OMNILIT_DOMAIN`：实际域名，不带协议和路径。
- `OMNILIT_ACME_EMAIL`：证书通知邮箱。
- `OMNILIT_APP_VERSION=0.1.0`：与桌面版一致。
- Turnstile site key/secret：在 Cloudflare Turnstile 创建当前域名站点后取得。
- SMTP：推荐使用已验证发件域名的 587/STARTTLS 服务。
- `OMNILIT_S3_REPOSITORY`：Restic S3 地址，例如 `s3:https://s3.example.com/bucket/omnilit`。
- 所有 `*_FILE` 路径指向刚创建的 secret 文件。

不要把 `deploy/.env`、`deploy/secrets`、数据库、附件卷或 Restic 密码提交到 Git。Cloud 数据密钥丢失后，私有数据不可恢复；Restic 密码丢失后，备份不可恢复。

## 2. 校验并启动

```bash
cd /opt/omnilit
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build --pull
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

验证：

```bash
curl -fsS https://你的域名/v1/health/live
curl -fsS https://你的域名/v1/health/ready
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100 cloud-api caddy clamav
```

健康结果应同时显示 `appVersion: "0.1.0"`、`status: "ready"`。如果 ClamAV 尚在下载病毒库，Cloud API 会等待其健康检查；公共附件扫描服务不可用时会拒绝完成上传，不会绕过扫描。

## 3. 初始化首个管理员

先在网页完成开放注册和邮箱验证，再从服务器执行：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec cloud-api \
  python -m services.cloud_api bootstrap-admin --email admin@example.com
```

该命令只接受已存在且已验证的账户，不提供公网提权接口。之后管理员可通过专用审核接口处理投稿。普通团队角色不会自动获得其他用户的个人 Workspace 权限。

## 4. 数据空间行为

- 桌面本地 Workspace 原地保留，同步默认关闭；本地 `runtime/sync/sync.sqlite3` 只保存同步游标、outbox、tombstone 与冲突，不保存密码或 Refresh Token。
- 登录不等于授权同步。用户必须明确启用私有同步，并分别授权文献、集合、图谱、设置、批注、PDF、全文和提取结果。
- 每个云账户由服务端绑定一个个人 Workspace；客户端不能提交其他账户的 `workspace_id`。
- 公共投稿是不可变快照。管理员批准后形成独立公共副本；私有修改、删除或账户删除不会自动修改已发布公共记录。
- 公共附件必须通过格式、文件签名、哈希、ClamAV 和许可审核。匿名用户只能读取公共 DTO；附件下载要求已验证账户。

## 5. 备份与恢复验收

`backup` 服务每天执行 PostgreSQL custom dump，将 dump、私有对象和公共对象写入本地加密 Restic 仓库，再复制到 S3。查看备份：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=200 backup
docker compose --env-file deploy/.env -f deploy/compose.yaml exec backup \
  restic -r /backups/restic snapshots
```

至少每季度在隔离服务器恢复一次。恢复流程：停止写入，选择快照，将 PostgreSQL dump 和对象目录恢复到临时位置，使用 `pg_restore` 写入空数据库，核对账户数、Workspace 数、公共记录版本、许可、审计、对象引用和 SHA-256；验收成功后才切换生产。详细步骤见 [cloud-backup-recovery.md](cloud-backup-recovery.md)。

## 6. 更新和回滚

```bash
cd /opt/omnilit
git fetch --tags
git checkout <已审核版本>
docker compose --env-file deploy/.env -f deploy/compose.yaml build --pull
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
```

升级前先确认最新本地与 S3 快照可读。不要让旧镜像直接连接已升级的数据库；回滚必须先停止服务并恢复升级前的完整快照。密钥轮换也不是简单替换文件，必须执行解密再加密迁移。

## 7. 上线验收清单

- 两个已验证账户互相看不到私有文献、同步变更和附件。
- 未勾选 PDF/全文/批注时，请求中不存在对应内容。
- 离线修改进入 outbox，重连后幂等上传；陈旧 revision 返回冲突而非覆盖。
- 四种文献目标均可选择：仅本地、仅私有、仅公共、私有与公共同时。
- 重复 DOI/标识/附件哈希进入合并或冲突流程，未审核投稿无法匿名访问。
- SMTP、Turnstile、ClamAV、Caddy HTTPS、PostgreSQL、磁盘、配额、审核积压和备份新鲜度均有监控。
- 完成一次从 S3 到隔离环境的全量恢复，并记录 RPO/RTO。

可选监控仅绑定回环地址：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml --profile monitoring up -d prometheus
```

不要把 Prometheus 端口直接开放公网；通过 SSH 隧道或运维 VPN 访问。
