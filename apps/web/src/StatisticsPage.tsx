import { useEffect, useState, type ReactNode } from "react"
import type { ApiClient } from "@omnilit/api-client"
import type { PlatformBridge } from "@omnilit/platform-bridge"
import type { ResearchStatistics, ResearchStatisticsBucket } from "@omnilit/shared-schema"

interface StatisticsPageProps { client: ApiClient; bridge: PlatformBridge }

function bucketTable(title: string, buckets: ResearchStatisticsBucket[], total: number): ReactNode {
  return <section className="analytics-card"><h2>{title}</h2>{buckets.length ? <table><thead><tr><th scope="col">项目</th><th scope="col">数量</th><th scope="col">占比</th></tr></thead><tbody>{buckets.map((bucket) => <tr key={bucket.key}><th scope="row">{bucket.label}</th><td>{bucket.count}</td><td><meter min={0} max={Math.max(1, total)} value={bucket.count}>{bucket.count}</meter></td></tr>)}</tbody></table> : <p>暂无数据。</p>}</section>
}

function statisticsCsv(statistics: ResearchStatistics): string {
  const rows = ["dimension,key,label,count"]
  for (const [dimension, buckets] of [["year", statistics.yearBuckets], ["source", statistics.sourceBuckets], ["pdf_status", statistics.pdfStatusBuckets], ["keyword", statistics.topKeywords], ["collection", statistics.collectionBuckets]] as const) {
    for (const bucket of buckets) rows.push([dimension, bucket.key, bucket.label, String(bucket.count)].map((value) => `"${value.replaceAll('"', '""')}"`).join(","))
  }
  return `\uFEFF${rows.join("\r\n")}\r\n`
}

export function StatisticsPage({ client, bridge }: StatisticsPageProps) {
  const [statistics, setStatistics] = useState<ResearchStatistics>()
  const [error, setError] = useState("")
  const [refresh, setRefresh] = useState(0)
  const [status, setStatus] = useState("")
  useEffect(() => {
    const controller = new AbortController()
    setError("")
    void client.getResearchStatistics(controller.signal).then(setStatistics).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "统计分析加载失败") })
    return () => controller.abort()
  }, [client, refresh])

  async function exportStatistics(): Promise<void> {
    if (!statistics) return
    try {
      const result = await bridge.saveFile({ suggestedName: "omnilit-research-statistics.csv", data: statisticsCsv(statistics), mimeType: "text/csv;charset=utf-8" })
      setStatus(result.saved ? `已导出 ${result.fileName}` : "未导出")
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "导出失败")
    }
  }

  return <section className="statistics-page"><header className="page-header"><div><p className="eyebrow">Shared Analytics</p><h1>统计分析</h1><p>聚合在 Local Agent 侧完成，React 只呈现统一统计 DTO。</p></div><button type="button" disabled={!statistics || statistics.status !== "ready"} onClick={() => void exportStatistics()}>导出 CSV</button></header>
    {error ? <div className="state-panel state-error"><h2>无法加载统计分析</h2><p>{error}</p><button type="button" onClick={() => setRefresh((value) => value + 1)}>重试</button></div>
      : !statistics ? <div className="state-panel" aria-busy="true"><h2>正在聚合文献统计</h2></div>
      : statistics.status === "unavailable" ? <div className="state-panel"><h2>本地文献缓存不可用</h2><p>{statistics.message}</p></div>
      : statistics.status === "empty" ? <div className="state-panel"><h2>暂无可分析文献</h2><p>{statistics.message}</p></div>
      : <><div className="metric-grid"><article><strong>{statistics.totalRecords}</strong><span>文献总数</span></article><article><strong>{statistics.downloadedRecords}</strong><span>已下载 PDF</span></article><article><strong>{statistics.extractedRecords}</strong><span>已解析文献</span></article><article><strong>{statistics.compareRecords}</strong><span>比较工作区</span></article></div><div className="analytics-grid">{bucketTable("年度分布", statistics.yearBuckets, statistics.totalRecords)}{bucketTable("来源分布", statistics.sourceBuckets, statistics.totalRecords)}{bucketTable("PDF 状态", statistics.pdfStatusBuckets, statistics.totalRecords)}{bucketTable("高频关键词", statistics.topKeywords, statistics.totalRecords)}{bucketTable("研究集合", statistics.collectionBuckets, statistics.totalRecords)}</div></>}
    <p className="mutation-status" role="status">{status}</p>
  </section>
}
