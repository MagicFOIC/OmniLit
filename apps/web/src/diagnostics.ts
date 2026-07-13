export const DIAGNOSTIC_STORAGE_KEY = "omnilit.diagnostics.v1"
const MAX_DIAGNOSTICS = 20

export type WebDiagnosticSource = "react" | "window" | "promise"

export interface WebDiagnosticEvent {
  reportVersion: 1
  occurredAt: string
  source: WebDiagnosticSource
  code: "render_error" | "uncaught_error" | "unhandled_rejection"
  exceptionType: string
  fingerprint: string
}

export type WebDiagnosticSink = (event: WebDiagnosticEvent) => void | Promise<void>

let diagnosticSink: WebDiagnosticSink | undefined

export function configureWebDiagnosticSink(sink?: WebDiagnosticSink): void {
  diagnosticSink = sink
}

function safeExceptionType(reason: unknown): string {
  if (reason instanceof TypeError) return "TypeError"
  if (reason instanceof RangeError) return "RangeError"
  if (reason instanceof ReferenceError) return "ReferenceError"
  if (reason instanceof SyntaxError) return "SyntaxError"
  if (reason instanceof URIError) return "URIError"
  if (reason instanceof EvalError) return "EvalError"
  if (reason instanceof Error) return "Error"
  return "Unknown"
}

function fingerprint(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(16).padStart(8, "0")
}

export function createWebDiagnostic(source: WebDiagnosticSource, code: WebDiagnosticEvent["code"], reason?: unknown): WebDiagnosticEvent {
  const exceptionType = safeExceptionType(reason)
  return { reportVersion: 1, occurredAt: new Date().toISOString(), source, code, exceptionType, fingerprint: fingerprint(`${source}:${code}:${exceptionType}`) }
}

export function storeWebDiagnostic(event: WebDiagnosticEvent, storage?: Pick<Storage, "getItem" | "setItem">): void {
  try {
    const destination = storage ?? (typeof window === "undefined" ? undefined : window.sessionStorage)
    if (!destination) return
    const parsed = JSON.parse(destination.getItem(DIAGNOSTIC_STORAGE_KEY) ?? "[]") as unknown
    const current = Array.isArray(parsed) ? parsed.filter((item): item is WebDiagnosticEvent => typeof item === "object" && item !== null) : []
    destination.setItem(DIAGNOSTIC_STORAGE_KEY, JSON.stringify([...current.slice(-(MAX_DIAGNOSTICS - 1)), event]))
  } catch {
    // Diagnostics must never break the product or fall back to less private storage.
  }
}

export function recordWebDiagnostic(source: WebDiagnosticSource, code: WebDiagnosticEvent["code"], reason?: unknown): void {
  const event = createWebDiagnostic(source, code, reason)
  storeWebDiagnostic(event)
  if (diagnosticSink) void Promise.resolve(diagnosticSink(event)).catch(() => undefined)
}
