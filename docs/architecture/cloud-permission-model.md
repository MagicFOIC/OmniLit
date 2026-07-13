# Cloud team and resource permission model

OmniLit Cloud API 使用“租户角色 + 资源 ACL + Owner 数据控制”三层判断。租户 ID 永远来自已验证
会话，客户端不能通过请求体或路径切换租户。

## 租户角色

| 能力 | Owner | Admin | Member |
|---|---:|---:|---:|
| 查看成员列表 | 是 | 是 | 是 |
| 邀请 Member | 是 | 是 | 否 |
| 邀请 Admin | 是 | 否 | 否 |
| 修改成员角色 | 是 | 否 | 否 |
| 移除 Member | 是 | 是 | 否 |
| 移除 Admin | 是 | 否 | 否 |
| 管理资源 ACL | 是 | 否 | 否 |
| 查看租户审计 | 是 | 是 | 否 |
| 导出/删除整个租户 | 是 | 否 | 否 |

Owner 不可通过成员接口删除或降级。Admin 不能邀请、修改或移除其他 Admin。删除成员时，其会话和
用户级 ACL 通过外键级联或显式清理立即失效。

## 资源 ACL

当前资源类型为 `library_state`、`collection`、`graph` 与 `graph_view`，权限为：

- `viewer`：读取资源；
- `editor`：读取、同步写入并创建不超过自身权限的分享；
- `none`：删除显式授权。

ACL principal 可以是同租户用户或整个 tenant。Owner 始终拥有资源；其他角色不因 Admin 身份自动
获得研究数据。Owner 的 `allowTeamAccess` 为总否决开关：关闭时，任何非 Owner ACL 均不生效。
服务端在每次读取、同步或分享操作时重新检查，不依赖 UI 隐藏按钮。

## 邀请安全

邀请 token 使用 32 字节随机值，数据库只保存 SHA-256；明文只在创建响应中返回一次。接受邀请是
公开但精确限流的接口，token 过期、被新邀请替代或使用一次后均返回同一受控错误。接受成功会创建
独立密码哈希和八小时会话，不继承邀请者会话。

## 当前限制

一个账户当前只有一个 `tenantId`，尚不支持同一身份切换多个租户；邀请已注册邮箱会被拒绝。资源
ACL 已覆盖云端文献库快照和云图谱。图谱视图继承所属 `graph` 的权限，不建立可绕过父图谱的第二套
授权；公开分享 graph 或 graph_view 时也先检查父图谱 editor。外部身份提供商、企业目录同步、
Owner 转移和审批工作流尚未实现。

图谱团队批注继承父 `graph` ACL：snapshot/event/SSE 要求 viewer，mutation 要求 editor；非 Owner
继续受 `allowTeamAccess` 限制。新增/更新还要求 Owner 启用 `syncAnnotations`，但关闭同步不阻止删除
既有批注。SSE 每次重连重新鉴权，ACL 撤销最迟在当前 25 秒有界连接结束后生效。
