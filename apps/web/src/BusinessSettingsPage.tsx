import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type BusinessSettings, type BusinessSettingsUpdateRequest } from "@omnilit/shared-schema"
import { applyBusinessSettings } from "./uiSettings"

interface BusinessSettingsPageProps { client: ApiClient }

function updateRequest(settings: BusinessSettings): BusinessSettingsUpdateRequest {
  return {
    protocolVersion: PROTOCOL_VERSION, expectedRevision: settings.revision,
    themeMode: settings.themeMode, density: settings.density, reduceMotion: settings.reduceMotion,
    highContrast: settings.highContrast, startPage: settings.startPage,
    defaultLibrarySort: settings.defaultLibrarySort, aiEvidenceLimit: settings.aiEvidenceLimit,
    aiEndpoint: settings.aiEndpoint, aiModel: settings.aiModel,
    allowRemoteResearchContent: settings.allowRemoteResearchContent,
  }
}

export function BusinessSettingsPage({ client }: BusinessSettingsPageProps) {
  const [settings, setSettings] = useState<BusinessSettings>()
  const [status, setStatus] = useState("")
  const [error, setError] = useState("")
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError("")
    void client.getBusinessSettings(controller.signal).then((value) => { setSettings(value); applyBusinessSettings(value) }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "业务设置加载失败") })
    return () => controller.abort()
  }, [client, refresh])

  function patch<K extends keyof BusinessSettings>(key: K, value: BusinessSettings[K]): void {
    setSettings((current) => current ? { ...current, [key]: value } : current)
  }

  async function save(): Promise<void> {
    if (!settings) return
    setStatus("正在保存…")
    try {
      const updated = await client.updateBusinessSettings(updateRequest(settings))
      setSettings(updated)
      applyBusinessSettings(updated)
      setStatus("业务设置已保存")
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "设置保存失败")
      setRefresh((value) => value + 1)
    }
  }

  async function reset(): Promise<void> {
    if (!settings) return
    const defaults: BusinessSettings = { ...settings, themeMode: "system", density: "comfortable", reduceMotion: false, highContrast: false, startPage: "graph", defaultLibrarySort: "relevance_desc", aiEvidenceLimit: 4, aiEndpoint: "", aiModel: "", allowRemoteResearchContent: false }
    setSettings(defaults)
    setStatus("默认值尚未保存")
  }

  return <section className="business-settings-page"><header className="page-header"><div><p className="eyebrow">Shared Business Settings</p><h1>业务设置</h1><p>仅管理可跨浏览器与桌面共享的业务偏好；文件夹、系统更新和平台证书仍由桌面容器负责。</p></div><span>revision {settings?.revision ?? "—"}</span></header>
    {error ? <div className="state-panel state-error"><h2>无法加载业务设置</h2><p>{error}</p><button type="button" onClick={() => setRefresh((value) => value + 1)}>重试</button></div>
      : !settings ? <div className="state-panel" aria-busy="true"><h2>正在加载业务设置</h2></div>
      : <form className="settings-grid" onSubmit={(event) => { event.preventDefault(); void save() }}><section className="info-card"><h2>界面与可访问性</h2><label>主题<select value={settings.themeMode} onChange={(event) => patch("themeMode", event.target.value as BusinessSettings["themeMode"])}><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></label><label>信息密度<select value={settings.density} onChange={(event) => patch("density", event.target.value as BusinessSettings["density"])}><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label><label className="control-row"><input type="checkbox" checked={settings.reduceMotion} onChange={(event) => patch("reduceMotion", event.target.checked)} />减少动效</label><label className="control-row"><input type="checkbox" checked={settings.highContrast} onChange={(event) => patch("highContrast", event.target.checked)} />增强对比度</label></section><section className="info-card"><h2>研究默认值</h2><label>启动页面<select value={settings.startPage} onChange={(event) => patch("startPage", event.target.value as BusinessSettings["startPage"])}><option value="graph">知识图谱</option><option value="library">文献库</option><option value="collections">研究集合</option><option value="workspace">研究工作空间</option><option value="statistics">统计分析</option><option value="ai">AI 工作区</option></select></label><label>文献默认排序<select value={settings.defaultLibrarySort} onChange={(event) => patch("defaultLibrarySort", event.target.value as BusinessSettings["defaultLibrarySort"])}><option value="relevance_desc">相关性</option><option value="year_desc">年份（新到旧）</option><option value="year_asc">年份（旧到新）</option><option value="downloaded_first">已下载优先</option><option value="title_asc">标题</option></select></label><label>AI 证据篇数<input type="number" min={1} max={4} value={settings.aiEvidenceLimit} onChange={(event) => patch("aiEvidenceLimit", Math.max(1, Math.min(4, Number(event.target.value) || 1)))} /></label></section><section className="info-card settings-wide"><h2>远程 AI 数据边界</h2><p>默认关闭。开启后，只有 AI 工作区选择“远程模型”时，所选文献摘要和研究问题才会发往指定 HTTPS 端点。API Key 只从 Local Agent 进程环境变量读取，不经此页面保存或返回。</p><label className="control-row"><input type="checkbox" checked={settings.allowRemoteResearchContent} onChange={(event) => patch("allowRemoteResearchContent", event.target.checked)} />我明确允许把所选研究内容发送到配置的远程模型</label><label>HTTPS 模型端点<input type="url" disabled={!settings.allowRemoteResearchContent} value={settings.aiEndpoint} onChange={(event) => patch("aiEndpoint", event.target.value)} placeholder="https://provider.example/v1/chat/completions" /></label><label>模型 ID<input disabled={!settings.allowRemoteResearchContent} value={settings.aiModel} maxLength={160} onChange={(event) => patch("aiModel", event.target.value)} /></label><p className={settings.aiCredentialConfigured ? "setting-ready" : "setting-warning"}>{settings.aiCredentialConfigured ? "运行环境已提供 OMNILIT_AI_API_KEY。" : "运行环境未提供 OMNILIT_AI_API_KEY；远程模型保持不可用。"}</p></section><div className="settings-actions"><button type="submit">保存设置</button><button type="button" onClick={() => void reset()}>恢复默认值</button></div></form>}
    <p className="mutation-status" role="status">{status}</p>
  </section>
}
