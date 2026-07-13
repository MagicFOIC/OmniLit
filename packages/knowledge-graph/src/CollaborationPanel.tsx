import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { PROTOCOL_VERSION, type CollaborationAnnotation, type CollaborationEvent, type CollaborationMutationRequest, type CollaborationMutationResult, type CollaborationSnapshot } from "@omnilit/shared-schema"

export interface CollaborationDataSource {
  getSnapshot(request: { recordId: string; signal: AbortSignal }): Promise<CollaborationSnapshot>
  mutate(request: { recordId: string; mutation: CollaborationMutationRequest; signal: AbortSignal }): Promise<CollaborationMutationResult>
  subscribe(request: { recordId: string; afterRevision: number; onEvent: (event: CollaborationEvent) => void; onReset: (currentRevision: number) => void; signal: AbortSignal }): Promise<number>
}

interface CollaborationPanelProps {
  recordId: string
  dataSource: CollaborationDataSource
  target: { type: "graph" | "node" | "edge"; id: string; label: string }
}

type LoadStatus = "loading" | "ready" | "error"
type ConnectionStatus = "connecting" | "live" | "reconnecting" | "error"

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "团队批注操作失败"
}

function errorCode(reason: unknown): string {
  return typeof reason === "object" && reason !== null && "payload" in reason
    ? String((reason as { payload?: { code?: string } }).payload?.code ?? "")
    : ""
}

export function applyCollaborationEvent(current: CollaborationSnapshot, event: CollaborationEvent): CollaborationSnapshot {
  if (event.revision <= current.revision) return current
  const remaining = current.annotations.filter((annotation) => annotation.id !== event.annotationId)
  const annotations = event.action === "annotation.upserted" && event.annotation ? [...remaining, event.annotation] : remaining
  return { ...current, revision: event.revision, annotations }
}

export function CollaborationPanel({ recordId, dataSource, target }: CollaborationPanelProps) {
  const [snapshot, setSnapshot] = useState<CollaborationSnapshot>()
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading")
  const [connection, setConnection] = useState<ConnectionStatus>("connecting")
  const [body, setBody] = useState("")
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  const revisionRef = useRef(0)
  const operationRef = useRef<AbortController | undefined>(undefined)

  const applySnapshot = useCallback((next: CollaborationSnapshot) => {
    revisionRef.current = next.revision
    setSnapshot(next)
    setLoadStatus("ready")
  }, [])

  const load = useCallback(async (signal: AbortSignal) => {
    setLoadStatus("loading")
    setMessage("")
    try {
      applySnapshot(await dataSource.getSnapshot({ recordId, signal }))
      return true
    } catch (reason) {
      if (!signal.aborted) {
        setLoadStatus("error")
        setMessage(errorMessage(reason))
      }
      return false
    }
  }, [applySnapshot, dataSource, recordId])

  const applyEvent = useCallback((event: CollaborationEvent) => {
    revisionRef.current = Math.max(revisionRef.current, event.revision)
    setSnapshot((current) => current ? applyCollaborationEvent(current, event) : current)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    operationRef.current = controller
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  useEffect(() => {
    if (loadStatus !== "ready") return undefined
    const controller = new AbortController()
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    const retryDelay = (): Promise<void> => new Promise((resolve) => {
      const onAbort = () => {
        if (retryTimer !== undefined) clearTimeout(retryTimer)
        resolve()
      }
      retryTimer = setTimeout(() => {
        controller.signal.removeEventListener("abort", onAbort)
        resolve()
      }, 1_000)
      controller.signal.addEventListener("abort", onAbort, { once: true })
    })
    const run = async (): Promise<void> => {
      setConnection("connecting")
      while (!controller.signal.aborted) {
        let resetRequired = false
        try {
          await dataSource.subscribe({ recordId, afterRevision: revisionRef.current, onEvent: applyEvent, onReset: () => { resetRequired = true }, signal: controller.signal })
          if (controller.signal.aborted) return
          if (resetRequired) {
            applySnapshot(await dataSource.getSnapshot({ recordId, signal: controller.signal }))
          }
          setConnection("live")
        } catch (reason) {
          if (controller.signal.aborted) return
          if (["unauthorized", "permission_denied", "team_access_disabled"].includes(errorCode(reason))) {
            setConnection("error")
            setMessage(errorMessage(reason))
            return
          }
          setConnection("reconnecting")
          await retryDelay()
        }
      }
    }
    void run()
    return () => {
      controller.abort()
      if (retryTimer !== undefined) clearTimeout(retryTimer)
    }
  }, [applyEvent, applySnapshot, dataSource, loadStatus, recordId])

  useEffect(() => () => operationRef.current?.abort(), [])

  const annotations = useMemo(() => [...(snapshot?.annotations ?? [])].sort((left, right) => right.revision - left.revision), [snapshot?.annotations])

  async function mutate(mutation: CollaborationMutationRequest): Promise<void> {
    operationRef.current?.abort()
    const controller = new AbortController()
    operationRef.current = controller
    setBusy(true)
    setMessage("")
    try {
      const result = await dataSource.mutate({ recordId, mutation, signal: controller.signal })
      if (!controller.signal.aborted) applyEvent(result.event)
    } catch (reason) {
      if (!controller.signal.aborted && errorCode(reason) === "collaboration_conflict") {
        const loaded = await load(controller.signal)
        if (!controller.signal.aborted && loaded) setMessage("检测到其他成员的新修改；已刷新批注，请重新提交。")
      } else if (!controller.signal.aborted) {
        setMessage(errorMessage(reason))
      }
      throw reason
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  async function createAnnotation(): Promise<void> {
    const cleanBody = body.trim()
    if (!snapshot?.canEdit || !cleanBody) return
    try {
      await mutate({ protocolVersion: PROTOCOL_VERSION, baseRevision: revisionRef.current, clientMutationId: crypto.randomUUID(), action: "upsert", targetType: target.type, targetId: target.id, body: cleanBody })
      setBody("")
      setMessage("团队批注已同步。")
    } catch {
      // mutate reports the actionable error or conflict state.
    }
  }

  async function deleteAnnotation(annotation: CollaborationAnnotation): Promise<void> {
    if (!snapshot?.canEdit) return
    try {
      await mutate({ protocolVersion: PROTOCOL_VERSION, baseRevision: revisionRef.current, clientMutationId: crypto.randomUUID(), action: "delete", annotationId: annotation.id, targetType: annotation.targetType, targetId: annotation.targetId })
      setMessage("团队批注已删除。")
    } catch {
      // mutate reports the actionable error or conflict state.
    }
  }

  return <section className="kg-collaboration" aria-labelledby="collaboration-title">
    <header><div><p className="kg-kicker">实时团队研究</p><h2 id="collaboration-title">共享批注</h2></div><span className={`kg-live-status is-${connection}`}>{connection === "live" ? "实时连接" : connection === "reconnecting" ? "正在重连" : connection === "error" ? "连接受限" : "正在连接"}</span></header>
    {loadStatus === "loading" && <p role="status">正在读取团队批注…</p>}
    {loadStatus === "error" && <p role="alert">{message}<button type="button" onClick={() => { const controller = new AbortController(); operationRef.current = controller; void load(controller.signal) }}>重试</button></p>}
    {loadStatus === "ready" && snapshot?.canEdit && snapshot.syncEnabled && <form className="kg-collaboration-form" onSubmit={(event) => { event.preventDefault(); void createAnnotation() }}><label>批注目标<strong>{target.label}</strong><textarea required maxLength={4000} value={body} onChange={(event) => setBody(event.target.value)} placeholder="记录需要团队确认的证据、方法或结论…" /></label><button type="submit" disabled={busy || !body.trim()}>{busy ? "同步中…" : "添加批注"}</button></form>}
    {loadStatus === "ready" && !snapshot?.canEdit && <p>你拥有只读权限；可以实时查看团队批注，但不能修改。</p>}
    {loadStatus === "ready" && snapshot?.canEdit && !snapshot.syncEnabled && <p>账户已关闭“同步批注”；仍可读取或删除既有云端批注，但不能新增或更新。</p>}
    {loadStatus === "ready" && annotations.length === 0 && <p role="status">尚无团队批注。</p>}
    {annotations.length > 0 && <ul>{annotations.map((annotation) => <li key={annotation.id}><div><strong>{annotation.authorDisplayName}</strong><span>{annotation.targetType} · {annotation.targetId}</span></div><p>{annotation.body}</p><footer><time dateTime={annotation.updatedAt}>{new Date(annotation.updatedAt).toLocaleString()}</time>{snapshot?.canEdit && <button type="button" disabled={busy} aria-label={`删除 ${annotation.authorDisplayName} 的批注`} onClick={() => void deleteAnnotation(annotation)}>删除</button>}</footer></li>)}</ul>}
    {message && loadStatus !== "error" && <p className="kg-collaboration-message" role="status">{message}</p>}
  </section>
}
