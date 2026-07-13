# OmniLit PostgreSQL、附件与 S3 备份恢复

生产 Compose 使用 Restic 加密仓库保存一致时间窗口内的 PostgreSQL custom dump、私有附件对象和已批准公共附件对象，并把本地仓库复制到 S3。隔离区内容不是已发布权威数据，但尚在审核的投稿元数据和审计记录位于 PostgreSQL 中。

## 备份内容与边界

- PostgreSQL：账户、Workspace、同步 revision/cursor、公共投稿、许可、审核与审计。
- `/objects/private`：账户私有加密对象。
- `/objects/public`：管理员控制的公共对象。
- Restic 仓库：使用独立 `restic-password.txt` 加密；数据库字段与对象还使用独立 Cloud data key 加密。
- S3：保存 Restic 加密 pack，不应依赖存储桶默认加密代替 Restic。建议开启版本控制、对象锁和最小权限专用凭据。

当前备份是每日全量逻辑 dump 加对象增量去重，不提供 PostgreSQL PITR。可接受的 RPO 由 `OMNILIT_BACKUP_INTERVAL_SECONDS` 决定。

## 日常检查

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --since=48h backup
docker compose --env-file deploy/.env -f deploy/compose.yaml exec backup restic -r /backups/restic snapshots
docker compose --env-file deploy/.env -f deploy/compose.yaml exec backup restic -r /backups/restic check
```

同时在独立主机使用 S3 凭据运行 `restic snapshots` 和 `restic check --read-data-subset`。只看到本地快照不代表异地复制成功。

## 隔离恢复演练

1. 准备一台不接收生产流量的服务器，安装与生产相同版本的 Docker/Compose。
2. 从安全保管位置取得 `restic-password.txt`、Cloud data key 和 S3 只读凭据。
3. 将指定快照恢复到临时目录：

   ```bash
   export RESTIC_PASSWORD_FILE=/secure/restic-password.txt
   export AWS_ACCESS_KEY_ID='...'
   export AWS_SECRET_ACCESS_KEY='...'
   restic -r 's3:https://s3.example.com/bucket/omnilit' snapshots
   restic -r 's3:https://s3.example.com/bucket/omnilit' restore <snapshot-id> --target /srv/omnilit-restore
   ```

4. 找到恢复的 `omnilit-*.dump`，向全新空数据库恢复：

   ```bash
   createdb omnilit_restore
   pg_restore --exit-on-error --no-owner --no-privileges --dbname omnilit_restore /srv/omnilit-restore/tmp/omnilit-*.dump
   ```

5. 将恢复的私有/公共对象挂载到隔离 Cloud API，使用原 Cloud data key 启动相同应用版本。
6. 校验：账户数与 Workspace 数、每账户隔离、同步最高 cursor、未解决冲突、公共记录版本、许可记录、审核/下架审计、附件引用、对象大小和 SHA-256。
7. 使用两个测试账户完成登录、私有查询、增量同步、公共检索和已验证账户附件下载。
8. 记录快照时间、恢复开始/完成时间、实际 RPO/RTO、缺失对象和修复措施，然后销毁隔离环境。

## 灾难恢复到生产

先停止 Caddy/Cloud API/backup，阻止新写入；保留故障卷只读副本。恢复到新的 PostgreSQL 数据卷和新的附件卷，完成上述校验后再切换 Caddy。不要在未校验时覆盖唯一生产卷，也不要混用不同快照中的数据库和对象目录。

恢复后立即轮换数据库、S3、SMTP、Turnstile 和运维凭据；Cloud data key 与 Restic 密码只有在完成数据重加密迁移后才能轮换。保留事故时间线和不可篡改审计副本。
