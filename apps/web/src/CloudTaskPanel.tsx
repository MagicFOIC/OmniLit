import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import type { CloudServiceMetrics, Task, UserAccount } from "@omnilit/shared-schema"

interface CloudTaskPanelProps {
  client: ApiClient
  account: UserAccount
}

interface GraphAuditResult extends Record<string, unknown> {
  recordId: string
  nodeCount: number
  edgeCount: number
  nodeTypes: Record<string, number>
  relationTypes: Record<string, number>
}

const ACTIVE_STATUSES = new Set<Task["status"]>(["created", "queued", "running", "stopping"])

export function CloudTaskPanel({ client, account }: CloudTaskPanelProps) {
  const [recordId, setRecordId] = useState("paper-001")
  const [task, setTask] = useState<Task>()
  const [result, setResult] = useState<GraphAuditResult>()
  const [metrics, setMetrics] = useState<CloudServiceMetrics>()
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState("")
  const canReadMetrics = account.roles.some((role) => role === "owner" || role === "admin")

  useEffect(() => {
    if (!canReadMetrics) return undefined
    const controller = new AbortController()
    void client.getCloudMetrics(controller.signal).then(setMetrics).catch((error: unknown) => {
      if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : "云服务指标加载失败")
    })
    return () => controller.abort()
  }, [canReadMetrics, client])

  useEffect(() => {
    if (!task || !ACTIVE_STATUSES.has(task.status)) return undefined
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async (): Promise<void> => {
      try {
        const next = await client.getTask(task.id, controller.signal)
        if (controller.signal.aborted) return
        setTask(next)
        if (next.status === "succeeded") {
          setResult(await client.getTaskResult<GraphAuditResult>(next.id, controller.signal))
          if (canReadMetrics) setMetrics(await client.getCloudMetrics(controller.signal))
          setStatus("云图谱审计已完成。")
        } else if (ACTIVE_STATUSES.has(next.status)) {
          timer = setTimeout(() => { void poll() }, 750)
        } else {
          setStatus(next.error?.message ?? next.message ?? "云任务已结束。")
        }
      } catch (error) {
        if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : "云任务状态刷新失败")
      }
    }
    timer = setTimeout(() => { void poll() }, 250)
    return () => {
      controller.abort()
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [canReadMetrics, client, task?.id, task?.status])

  async function createAudit(): Promise<void> {
    const normalized = recordId.trim()
    if (!normalized) return
    setBusy(true)
    setStatus("")
    setResult(undefined)
    try {
      const created = await client.createTask("graph.audit", { recordId: normalized })
      setTask(created)
      setStatus("云图谱审计已进入受控队列。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "云任务创建失败")
    } finally {
      setBusy(false)
    }
  }

  async function cancel(): Promise<void> {
    if (!task?.cancellable) return
    setBusy(true)
    try {
      const cancelled = await client.cancelTask(task.id)
      setTask(cancelled)
      setStatus(cancelled.status === "cancelled" ? "云任务已取消。" : "正在安全停止云任务。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "云任务取消失败")
    } finally {
      setBusy(false)
    }
  }

  const progressTotal = Math.max(1, task?.progress.total ?? 1)
  const progressValue = Math.min(progressTotal, task?.progress.completed ?? 0)
  return (
    <section className="info-card cloud-task-panel">
      <h2>云端长任务与运行指标</h2>
      <p>在租户隔离的持久队列中审计已同步图谱；任务可轮询、取消，并在服务重启后明确标记失败。</p>
      <form className="cloud-task-create" onSubmit={(event) => { event.preventDefault(); void createAudit() }}>
        <label>云图谱 recordId<input required maxLength={256} value={recordId} onChange={(event) => setRecordId(event.target.value)} /></label>
        <button type="submit" disabled={busy}>创建图谱审计</button>
      </form>
      {task ? <div className="cloud-task-status" aria-live="polite">
        <div><strong>{task.type}</strong><span>{task.status} · {task.progress.message ?? task.message ?? "等待状态更新"}</span></div>
        <progress max={progressTotal} value={progressValue}>{progressValue} / {progressTotal}</progress>
        {task.cancellable && <button type="button" disabled={busy} onClick={() => void cancel()}>取消任务</button>}
      </div> : <p>尚未创建云端任务。</p>}
      {result && <dl className="cloud-task-result"><dt>图谱</dt><dd>{result.recordId}</dd><dt>节点</dt><dd>{result.nodeCount}</dd><dt>关系</dt><dd>{result.edgeCount}</dd></dl>}
      {canReadMetrics && <div className="cloud-metrics"><h3>租户运行指标</h3>{metrics ? <dl><dt>服务状态</dt><dd>{metrics.status}</dd><dt>运行时间</dt><dd>{Math.floor(metrics.uptimeSeconds)} 秒</dd><dt>用户 / 图谱</dt><dd>{metrics.tenantUsers} / {metrics.cloudGraphs}</dd><dt>协作 / 审计事件</dt><dd>{metrics.collaborationEvents} / {metrics.auditEvents}</dd></dl> : <p>正在加载运行指标…</p>}</div>}
      <p className="mutation-status" role="status">{status}</p>
    </section>
  )
}
