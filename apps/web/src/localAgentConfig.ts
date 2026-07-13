const SESSION_KEY = "omnilit.local-agent.v1"

export interface LocalAgentConnection {
  baseUrl: string
  token: string
}

function sessionStore(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage
  } catch {
    return undefined
  }
}

export function normalizeLocalAgentConnection(baseUrl: string, token: string): LocalAgentConnection {
  const url = new URL(baseUrl.trim())
  const hostname = url.hostname.toLowerCase()
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]", "::1"].includes(hostname)) {
    throw new Error("Local Agent 必须使用本机回环 HTTP 地址。")
  }
  if (url.username || url.password || url.search || url.hash || (url.pathname !== "/" && url.pathname !== "")) {
    throw new Error("Local Agent 地址只能包含协议、主机和端口。")
  }
  const cleanToken = token.trim()
  if (cleanToken.length < 24) throw new Error("Local Agent Token 至少需要 24 个字符。")
  return { baseUrl: url.origin, token: cleanToken }
}

export function readLocalAgentConnection(): LocalAgentConnection | undefined {
  const raw = sessionStore()?.getItem(SESSION_KEY)
  if (!raw) return undefined
  try {
    const parsed = JSON.parse(raw) as Partial<LocalAgentConnection>
    return normalizeLocalAgentConnection(parsed.baseUrl ?? "", parsed.token ?? "")
  } catch {
    sessionStore()?.removeItem(SESSION_KEY)
    return undefined
  }
}

export function saveLocalAgentConnection(baseUrl: string, token: string): LocalAgentConnection {
  const connection = normalizeLocalAgentConnection(baseUrl, token)
  const storage = sessionStore()
  if (!storage) throw new Error("当前浏览器不允许保存会话配置。")
  storage.setItem(SESSION_KEY, JSON.stringify(connection))
  return connection
}

export function clearLocalAgentConnection(): void {
  sessionStore()?.removeItem(SESSION_KEY)
}

export async function probeLocalAgent(connection: LocalAgentConnection, signal?: AbortSignal): Promise<void> {
  const controller = signal ? undefined : new AbortController()
  const timeout = controller ? globalThis.setTimeout(() => controller.abort(), 5000) : undefined
  let response: Response
  try {
    response = await fetch(`${connection.baseUrl}/v1/health`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${connection.token}`,
        "X-OmniLit-Protocol-Version": "1.0"
      },
      signal: signal ?? controller?.signal
    })
  } catch (reason) {
    const origin = typeof window === "undefined" ? "当前网页 Origin" : window.location.origin
    const detail = reason instanceof Error && reason.name === "AbortError" ? "连接超时" : "网络或 CORS 拒绝"
    throw new Error(`${detail}：无法访问 ${connection.baseUrl}。请确认 Local Agent 正在运行，并使用 --origin ${origin} 启动。`)
  } finally {
    if (timeout !== undefined) globalThis.clearTimeout(timeout)
  }
  const payload = await response.json().catch(() => undefined) as { protocolVersion?: string; status?: string; service?: string; message?: string } | undefined
  if (!response.ok) throw new Error(payload?.message || `Local Agent 返回 HTTP ${response.status}`)
  if (payload?.protocolVersion !== "1.0" || payload.status !== "ready" || payload.service !== "omnilit-local-agent") {
    throw new Error("目标服务不是兼容的 OmniLit Local Agent。")
  }
}
