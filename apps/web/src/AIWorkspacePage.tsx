import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import type { ApiClient } from "@omnilit/api-client"
import type { PlatformBridge } from "@omnilit/platform-bridge"
import { PROTOCOL_VERSION, type BusinessSettings, type ResearchBriefRequest, type ResearchBriefResult, type ResearchWorkspace, type Task } from "@omnilit/shared-schema"

interface AIWorkspacePageProps { client: ApiClient; bridge: PlatformBridge }
const FINAL_TASK_STATUSES = new Set<Task["status"]>(["succeeded", "failed", "cancelled"])

function briefMarkdown(result: ResearchBriefResult): string {
  return [`# ${result.title}`, "", ...result.sections.flatMap((section) => [`## ${section.heading}`, "", section.body, "", `Evidence: ${section.evidenceRecordIds.join(", ")}`]), "", ...result.warnings.map((warning) => `> ${warning}`)].join("\n")
}

export function AIWorkspacePage({ client, bridge }: AIWorkspacePageProps) {
  const [workspace, setWorkspace] = useState<ResearchWorkspace>()
  const [settings, setSettings] = useState<BusinessSettings>()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [focus, setFocus] = useState<ResearchBriefRequest["focus"]>("overview")
  const [mode, setMode] = useState<ResearchBriefRequest["mode"]>("evidence_only")
  const [question, setQuestion] = useState("")
  const [task, setTask] = useState<Task>()
  const [result, setResult] = useState<ResearchBriefResult>()
  const [error, setError] = useState("")
  const [status, setStatus] = useState("")
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setError("")
    void Promise.all([client.getResearchWorkspace(controller.signal), client.getBusinessSettings(controller.signal)])
      .then(([nextWorkspace, nextSettings]) => {
        setWorkspace(nextWorkspace)
        setSettings(nextSettings)
        setSelectedIds((current) => current.length ? current.filter((id) => nextWorkspace.records.some((record) => record.recordId === id)).slice(0, nextSettings.aiEvidenceLimit) : nextWorkspace.records.slice(0, nextSettings.aiEvidenceLimit).map((record) => record.recordId))
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "AI 工作区加载失败") })
    return () => controller.abort()
  }, [client, refresh])

  useEffect(() => {
    if (!task || FINAL_TASK_STATUSES.has(task.status)) return undefined
    const controller = new AbortController()
    const timer = globalThis.setInterval(() => {
      void client.getTask(task.id, controller.signal).then(async (next) => {
        if (next.status === "succeeded") {
          const value = await client.getTaskResult<ResearchBriefResult>(next.id, controller.signal)
          if (!controller.signal.aborted) {
            setTask(next)
            setResult(value)
            setStatus("研究简报已生成")
          }
        } else if (next.status === "failed") {
          setTask(next)
          setStatus(next.error?.message || "研究简报任务失败")
        } else if (next.status === "cancelled") {
          setTask(next)
          setStatus("研究简报任务已取消")
        } else setTask(next)
      }).catch((reason: unknown) => { if (!controller.signal.aborted) setStatus(reason instanceof Error ? reason.message : "任务状态读取失败") })
    }, 500)
    return () => { controller.abort(); globalThis.clearInterval(timer) }
  }, [client, task])

  const modelReady = Boolean(settings?.allowRemoteResearchContent && settings.aiCredentialConfigured && settings.aiEndpoint && settings.aiModel)

  function toggleRecord(recordId: string): void {
    if (!settings) return
    setSelectedIds((current) => current.includes(recordId) ? current.filter((id) => id !== recordId) : current.length < settings.aiEvidenceLimit ? [...current, recordId] : current)
  }

  async function startBrief(): Promise<void> {
    if (!selectedIds.length) return
    setError("")
    setResult(undefined)
    setStatus("正在创建可取消任务…")
    try {
      const created = await client.createTask("research.brief", { protocolVersion: PROTOCOL_VERSION, recordIds: selectedIds, focus, question: question.trim(), mode })
      setTask(created)
      setStatus("研究简报任务已排队")
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "任务创建失败")
    }
  }

  async function cancelTask(): Promise<void> {
    if (!task?.cancellable) return
    try {
      setTask(await client.cancelTask(task.id))
      setStatus("正在取消任务…")
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "取消失败")
    }
  }

  async function exportBrief(): Promise<void> {
    if (!result) return
    try {
      const saved = await bridge.saveFile({ suggestedName: "omnilit-research-brief.md", data: briefMarkdown(result), mimeType: "text/markdown;charset=utf-8" })
      setStatus(saved.saved ? `已导出 ${saved.fileName}` : "未导出")
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "导出失败")
    }
  }

  return <section className="ai-workspace-page"><header className="page-header"><div><p className="eyebrow">Evidence-aware AI Workspace</p><h1>AI 工作区</h1><p>默认只在本地生成可追溯证据简报；远程模型必须经过显式授权和环境密钥配置。</p></div><span className="status-pill">{modelReady ? "远程模型已就绪" : "本地证据模式"}</span></header>
    {error ? <div className="state-panel state-error"><h2>无法加载 AI 工作区</h2><p>{error}</p><button type="button" onClick={() => setRefresh((value) => value + 1)}>重试</button></div>
      : !workspace || !settings ? <div className="state-panel" aria-busy="true"><h2>正在加载研究证据</h2></div>
      : workspace.status !== "ready" ? <div className="state-panel"><h2>比较工作区尚未准备</h2><p>{workspace.message}</p><Link to="/library">从文献库加入比较文献</Link></div>
      : <div className="ai-layout"><form className="ai-controls" onSubmit={(event) => { event.preventDefault(); void startBrief() }}><fieldset><legend>证据文献（最多 {settings.aiEvidenceLimit} 篇）</legend>{workspace.records.map((record) => <label className="control-row" key={record.recordId}><input type="checkbox" checked={selectedIds.includes(record.recordId)} onChange={() => toggleRecord(record.recordId)} /><span>{record.title}</span></label>)}</fieldset><label>分析重点<select value={focus} onChange={(event) => setFocus(event.target.value as ResearchBriefRequest["focus"])}><option value="overview">证据概览</option><option value="methods">方法比较</option><option value="findings">发现比较</option><option value="gaps">证据缺口</option></select></label><label>研究问题（可选）<textarea maxLength={500} rows={4} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：这些研究的方法边界有何差异？" /></label><fieldset><legend>处理模式</legend><label><input type="radio" name="brief-mode" value="evidence_only" checked={mode === "evidence_only"} onChange={() => setMode("evidence_only")} /> 本地确定性证据编排</label><label><input type="radio" name="brief-mode" value="model" checked={mode === "model"} disabled={!modelReady} onChange={() => setMode("model")} /> 已配置远程模型</label>{!modelReady && <small>远程模式未启用；请在业务设置中确认内容外发，并由运行环境提供密钥。</small>}</fieldset><div className="form-actions"><button type="submit" disabled={!selectedIds.length || Boolean(task && !FINAL_TASK_STATUSES.has(task.status))}>生成研究简报</button><button type="button" disabled={!task?.cancellable} onClick={() => void cancelTask()}>取消任务</button></div>{task && <div className="task-progress" aria-live="polite"><progress max={Math.max(1, task.progress.total)} value={task.progress.completed} /><span>{task.progress.message || task.message || task.status}</span></div>}</form><section className="brief-result" aria-live="polite"><header><h2>{result?.title || "研究简报"}</h2><button type="button" disabled={!result} onClick={() => void exportBrief()}>导出 Markdown</button></header>{result ? <>{result.sections.map((section) => <article key={`${section.heading}:${section.evidenceRecordIds.join(",")}`}><h3>{section.heading}</h3><p>{section.body}</p><small>证据：{section.evidenceRecordIds.join(" · ")}</small></article>)}{result.warnings.map((warning) => <p className="brief-warning" key={warning}>{warning}</p>)}</> : <p>选择文献和分析重点后生成。结果不会把本地证据编排冒充为模型输出。</p>}</section></div>}
    <p className="mutation-status" role="status">{status}</p>
  </section>
}
