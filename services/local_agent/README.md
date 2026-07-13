# OmniLit Local Agent

独立、回环地址限定的本地查询服务。当前切片只暴露健康检查、种子图谱、分页邻居与文献投影，
复用桌面端已有 Python 图谱逻辑，不接受任意命令或文件路径。

安全边界：

- 只允许显式 IP 回环地址，拒绝 `0.0.0.0` 和非回环地址；
- 每次进程使用至少 24 字符的 Bearer Token；桌面生命周期管理器后续负责生成和注入；
- 浏览器 Origin 使用精确白名单，CLI/桌面无 Origin 请求仍必须认证；
- record/node 输入拒绝路径分隔符、`..`、控制字符和超长值；
- 图谱缓存限制 32 MiB，请求体限制 64 KiB，并发请求使用有界信号量；
- 错误和结构化日志不记录 Token、文献内容或本地绝对路径。

开发启动：

```text
set OMNILIT_LOCAL_AGENT_TOKEN=<至少 24 字符的随机令牌>
python -m services.local_agent --port 8765 --origin http://127.0.0.1:4173
```

Web 启动后在“本地文献库连接”页面填写 `http://127.0.0.1:8765` 和启动时使用的 Token；
连接信息只保存在当前标签页会话，未配置时显示演示数据模式，不会静默伪装为本地服务。
Qt 桌面入口现由 `LocalAgentManager` 负责随机令牌、固定参数
拉起、协议健康检查、5 秒周期监测、限次重启和退出回收；状态对象不会返回令牌。当前请求
查询以外还提供受控 `graph.audit` 长任务：创建、轮询、取消、结果引用、队列和并发上限、
5 分钟默认超时，以及 Agent 重启后的未完成任务显式失败恢复。任务类型来自内部白名单，
不能通过请求指定命令、模块或文件路径；状态写入 `runtime/local_agent/tasks`，结果单独存放。

`POST /v1/graphs/{recordId}/projection` 复用桌面端 `knowledge_graph_lod`，按视口、缩放和固定
预算返回真实节点、聚合节点及投影诊断。固定层级预算为 overview 240、normal 480、detail
900，绝对上限 1,200；服务拒绝超长 pin 列表和未知布局类型。

图谱视图接口为 `GET/POST /v1/graphs/{recordId}/views`、
`GET/DELETE /v1/graphs/{recordId}/views/{viewId}`。它与 QML 共用
`knowledge_graph_views.json`，写入采用同目录原子替换；恢复时会删除已经不存在的节点和关系，
并返回 reconciliation 计数及可直接渲染的共享 GraphData。视图文件限制 1 MiB、每篇文献
100 项，请求仍受 64 KiB、Token、Origin 和并发限制。
