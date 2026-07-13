# Platform Bridge

`packages/platform-bridge` 是共享 React 产品代码访问运行环境能力的唯一入口。业务组件不得
直接读取 `window.qt`、`window.qtBridge`、`window.__TAURI__` 或 Electron 全局对象。

当前实现：

- `BrowserPlatformBridge`：浏览器文件选择、Blob 下载、HTTP(S) 外链和应用信息。
- `MockPlatformBridge`：固定文件、应用信息、Local Agent 状态及任务进度事件，用于测试。
- `QtWebChannelPlatformBridge`：在受信 Qt WebEngine 页面中按需加载 Qt 自带
  `qwebchannel.js`，只暴露应用信息、Local Agent 状态和 HTTP(S) 外链。图谱、时间轴、PDF、
  文件路径和任务结果不经过 QWebChannel。
- 浏览器不支持的文件管理器定位会抛出 `PlatformCapabilityError`，Local Agent 未配置时返回
  `available: false`，不伪造桌面路径或成功状态。
- 外部链接仅允许 HTTP/HTTPS。
- `createPlatformBridge` 只在精确 loopback origin 且 hash 参数含 `embedded=1` 时选择 Qt
  实现；普通浏览器继续使用 Browser Bridge。

Qt 适配器保持最小能力面。后续新增桌面能力仍须先扩展同一 `PlatformBridge` 接口；大型图谱、
PDF、长文本和高频数据流继续通过受认证 Local Agent HTTP/WebSocket/SSE 或文件引用传输。

Qt 容器不把会话令牌写入 URL、QML 或日志。桌面端的同源请求拦截器只对当前 Local Agent 的
精确 scheme/host/port 注入 Bearer Token；Local Agent 仅从已认证的 `/app/` 路径提供构建产物，
并返回严格 CSP、`no-store`、`nosniff`、`no-referrer` 和 same-origin 资源策略。
