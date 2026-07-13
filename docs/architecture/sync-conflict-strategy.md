# Sync and conflict strategy

OmniLit 不允许桌面、Local Agent 或 Cloud API 静默覆盖研究集合与工作空间状态。

## 当前本地权威状态

`data/downloads/library_state.json` 是桌面研究集合、收藏关系和比较工作区的本地权威文件。
状态格式为 schema version 2，并包含单调递增 `revision`、`updated_at` 和以下同步状态：

- `local_only`：仅存在于本地；
- `pending_sync`：已产生待上传操作；
- `synced`：本地 revision 已被云端确认；
- `conflict`：云端和本地从同一基线产生了不同操作；
- `deleting`：删除操作待云端确认。

QML 与 Local Agent 的每次 mutation 都必须携带读取时的 `expectedRevision`。共享存储在跨进程
排他锁内重新读取文件；revision 不一致时拒绝写入。Local Agent 映射为 HTTP 409
`library_state_conflict`，前端重新读取最新状态并明确提示用户重试，不自动覆盖。

写入采用同目录临时文件和 `os.replace`。损坏 JSON 会先保存 `.bak` 再恢复默认状态；内置集合
不可删除，比较工作区最多四篇，recordId 只作为不透明键，不参与路径拼接。

## 当前 Cloud API 快照同步

`services/cloud_api` 已实现租户级加密快照基线。客户端发送 `deviceId`、`baseCloudRevision` 和
本地 `LibraryState`；基线等于服务端当前版本时，服务端以 AES-GCM 加密保存快照并返回递增
`cloudRevision`。基线陈旧时返回 HTTP 409、当前云端副本和 `conflictId`，不会写入客户端副本。

Web 账户页提供两种显式选择：保留云端并取消本次同步，或以冲突响应中的当前版本作为新基线，
明确用本地副本覆盖。API Client 只对这一已声明接口接受 409 业务结果；通用 409 仍是错误，
非幂等写入不会自动重试。

当前同步只包含集合、收藏关系和比较工作区 DTO，不包含 PDF、全文、本地路径或令牌。分享 ACL
由服务端租户边界控制，用户必须先显式启用 `allowShareLinks`；分享令牌只存哈希且创建后只返回一次。

## 后续细粒度同步规则

研究集合采用“版本快照 + 操作日志”：

- 创建集合：服务器分配稳定 UUID，客户端临时 ID 在确认后映射；
- 重命名：同一集合的并发重命名进入 `conflict`，由用户选择名称，不使用最后写入静默覆盖；
- 收藏关系：以 `(collectionId, recordId)` 的 add/remove 操作合并，重复操作幂等；
- 集合删除：先进入 `deleting`，若远端包含本地未知修改则保留副本并提示；
- 比较工作区：属于用户设备草稿，默认 `local_only`；用户明确开启同步后才上传；
- 权限或分享变更：始终以服务器 ACL revision 为准，冲突时拒绝客户端 mutation。

当前版本快照为后续操作日志同步提供安全基线；细粒度合并、离线队列和删除保留副本尚未实现。
离线队列不得包含 PDF 路径、访问令牌或未授权全文。

## 云图谱同步

图谱使用独立 `(tenantId, recordId, cloudRevision)` 加密快照。同步路径 recordId 必须与 GraphData
一致；客户端携带 `baseCloudRevision`，陈旧版本返回 HTTP 409、当前服务端 GraphData 与 conflictId。
Web 明确提供“保留云端”或“使用本地副本覆盖”，不会自动合并语义节点或最后写入覆盖。

当前单图限制 10,000 节点、40,000 关系、16 MiB 请求和 24 MiB 加密载荷。保存视图使用相同
GraphViewState，单图最多 100 个；恢复时与当前云图谱 reconciliation，已删除节点/关系不会复活。
图谱和视图落盘均为 AES-GCM 密文。

## 验证要求

- 两个写入者使用相同 revision 时只能有一个成功；
- 冲突后文件保持合法且只包含成功操作；
- schema 限制四篇比较记录；
- 409 不被 API Client 当作可自动重试错误；
- 损坏文件备份、内置集合保护和原子替换均有测试。
- 云端快照密文不包含可搜索的 recordId 明文，凭据与分享/会话令牌只保存哈希；
- 两个租户不能读取、撤销或导出对方资源；撤销或过期分享不能继续解析；
- Cloud HTTP 边界覆盖精确 Origin、CORS 预检、限流、请求上限、安全响应头和非 TLS 外部绑定拒绝。
