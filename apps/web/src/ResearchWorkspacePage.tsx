import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import type { ApiClient } from "@omnilit/api-client"
import type { PlatformBridge } from "@omnilit/platform-bridge"
import { PROTOCOL_VERSION, type LibraryState, type ResearchWorkspace } from "@omnilit/shared-schema"

interface ResearchWorkspacePageProps { client: ApiClient; bridge: PlatformBridge }

function workspaceMarkdown(workspace: ResearchWorkspace): string {
  const rows = workspace.records.map((record) => [
    `## ${record.title}`,
    `- Record ID: ${record.recordId}`,
    `- Authors: ${record.authorsText || "Unknown"}`,
    `- Year: ${record.year || "Unknown"}`,
    `- Source: ${record.journalTitle || record.source || "Unknown"}`,
    `- Keywords: ${record.keywordsText || "None"}`,
    "",
    record.abstract || "Abstract unavailable.",
  ].join("\n"))
  return [`# OmniLit research comparison`, "", ...rows].join("\n\n")
}

function graphRoute(recordId: string, recordTitle: string): string {
  const query = new URLSearchParams({ recordId, recordTitle })
  return `/graph?${query.toString()}`
}

export function ResearchWorkspacePage({ client, bridge }: ResearchWorkspacePageProps) {
  const [workspace, setWorkspace] = useState<ResearchWorkspace>()
  const [libraryState, setLibraryState] = useState<LibraryState>()
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState("")
  const [status, setStatus] = useState("")

  useEffect(() => {
    const controller = new AbortController()
    setError("")
    void Promise.all([client.getResearchWorkspace(controller.signal), client.getLibraryState(controller.signal)])
      .then(([nextWorkspace, nextState]) => { setWorkspace(nextWorkspace); setLibraryState(nextState) })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "研究工作空间加载失败") })
    return () => controller.abort()
  }, [client, refresh])

  async function removeRecord(recordId: string): Promise<void> {
    if (!libraryState) return
    setStatus("正在更新比较工作区…")
    try {
      await client.mutateLibraryState({ protocolVersion: PROTOCOL_VERSION, action: "remove_compare_record", expectedRevision: libraryState.revision, recordId })
      setStatus("已移出比较工作区")
      setRefresh((value) => value + 1)
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "工作空间更新失败")
      setRefresh((value) => value + 1)
    }
  }

  async function exportWorkspace(): Promise<void> {
    if (!workspace?.records.length) return
    try {
      const result = await bridge.saveFile({ suggestedName: "omnilit-research-comparison.md", data: workspaceMarkdown(workspace), mimeType: "text/markdown;charset=utf-8" })
      setStatus(result.saved ? `已导出 ${result.fileName}` : "未导出")
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "导出失败")
    }
  }

  return <section className="research-workspace-page">
    <header className="page-header"><div><p className="eyebrow">Shared Research Workspace</p><h1>研究工作空间</h1><p>以同一组比较 ID 驱动浏览器和桌面端，不在 React 复制文献业务规则。</p></div><button type="button" disabled={!workspace?.records.length} onClick={() => void exportWorkspace()}>导出比较</button></header>
    {error ? <div className="state-panel state-error"><h2>无法加载研究工作空间</h2><p>{error}</p><button type="button" onClick={() => setRefresh((value) => value + 1)}>重试</button></div>
      : !workspace ? <div className="state-panel" aria-busy="true"><h2>正在加载比较文献</h2></div>
      : workspace.status === "unavailable" ? <div className="state-panel"><h2>本地文献缓存不可用</h2><p>{workspace.message}</p></div>
      : workspace.status === "empty" ? <div className="state-panel"><h2>比较工作区为空</h2><p>{workspace.message}</p><Link to="/library">从文献库加入文献</Link></div>
      : <><div className="workspace-summary"><strong>{workspace.records.length}/{workspace.compareLimit} 篇文献</strong><span>{workspace.message}</span><Link to="/ai">生成研究简报</Link></div><div className="comparison-scroll"><table className="comparison-table"><caption>研究文献横向比较</caption><thead><tr><th scope="col">比较维度</th>{workspace.records.map((record) => <th scope="col" key={record.recordId}>{record.title}</th>)}</tr></thead><tbody>
        <tr><th scope="row">作者</th>{workspace.records.map((record) => <td key={record.recordId}>{record.authorsText || "—"}</td>)}</tr>
        <tr><th scope="row">年份 / 来源</th>{workspace.records.map((record) => <td key={record.recordId}>{record.year || "—"}<br />{record.journalTitle || record.source || "—"}</td>)}</tr>
        <tr><th scope="row">关键词</th>{workspace.records.map((record) => <td key={record.recordId}>{record.keywordsText || "—"}</td>)}</tr>
        <tr><th scope="row">本地状态</th>{workspace.records.map((record) => <td key={record.recordId}>{record.downloaded ? "PDF 已下载" : record.pdfStatus || "无 PDF"}<br />{record.hasExtraction ? "已解析" : "未解析"}</td>)}</tr>
        <tr><th scope="row">摘要证据</th>{workspace.records.map((record) => <td key={record.recordId}>{record.abstract || "暂无摘要，不能推断结论。"}</td>)}</tr>
        <tr><th scope="row">操作</th>{workspace.records.map((record) => <td key={record.recordId}><div className="table-actions"><Link to={graphRoute(record.recordId, record.title)}>打开图谱</Link><button type="button" onClick={() => void removeRecord(record.recordId)}>移出比较</button></div></td>)}</tr>
      </tbody></table></div></>}
    <p className="mutation-status" role="status">{status}</p>
  </section>
}
