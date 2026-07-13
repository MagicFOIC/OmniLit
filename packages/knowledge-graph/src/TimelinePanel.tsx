import { useEffect, useState } from "react"
import type { GraphTimeline } from "@omnilit/shared-schema"
import type { KnowledgeGraphState } from "./state"

export interface TimelineQuerySelection {
  startYear: number
  endYear: number
  playbackYear: number
}

export interface TimelinePanelProps {
  timeline: KnowledgeGraphState["timeline"]
  onQuery: (selection: TimelineQuerySelection) => void
  onRetry: () => void
  onCancel: () => void
  onSelectPaper: (nodeId: string) => void
}

export function nextTimelinePlaybackYear(years: number[], playbackYear: number, endYear: number): number | undefined {
  return years.find((year) => year > playbackYear && year <= endYear)
}

function TimelineContent({ data, onQuery, onSelectPaper }: { data: GraphTimeline; onQuery: (selection: TimelineQuerySelection) => void; onSelectPaper: (nodeId: string) => void }) {
  const [playing, setPlaying] = useState(false)
  const years = data.yearRange.years
  const { startYear, endYear, playbackYear } = data.selection

  useEffect(() => {
    if (!playing) return undefined
    const nextYear = nextTimelinePlaybackYear(years, playbackYear, endYear)
    if (nextYear === undefined) {
      setPlaying(false)
      return undefined
    }
    const timer = globalThis.setTimeout(() => onQuery({ startYear, endYear, playbackYear: nextYear }), 900)
    return () => globalThis.clearTimeout(timer)
  }, [endYear, onQuery, playbackYear, playing, startYear, years])

  const updateRange = (nextStart: number, nextEnd: number) => {
    const normalizedStart = Math.min(nextStart, nextEnd)
    const normalizedEnd = Math.max(nextStart, nextEnd)
    const nextPlayback = Math.max(normalizedStart, Math.min(normalizedEnd, playbackYear))
    setPlaying(false)
    onQuery({ startYear: normalizedStart, endYear: normalizedEnd, playbackYear: nextPlayback })
  }

  return <>
    <div className="kg-timeline-controls">
      <label>起始年份<select value={startYear} onChange={(event) => updateRange(Number(event.target.value), endYear)}>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
      <label>结束年份<select value={endYear} onChange={(event) => updateRange(startYear, Number(event.target.value))}>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
      <button type="button" aria-pressed={playing} onClick={() => setPlaying((current) => !current)}>{playing ? "暂停演化" : "播放演化"}</button>
      <button type="button" disabled={playbackYear === startYear} onClick={() => { setPlaying(false); onQuery({ startYear, endYear, playbackYear: startYear }) }}>回到起点</button>
      <output aria-live="polite">当前：{data.selection.effectiveEndYear}</output>
    </div>
    <ol className="kg-timeline-years" aria-label="按年份排列的论文与主题里程碑">
      {data.events.map((event) => <li key={event.year} className={event.year === data.selection.effectiveEndYear ? "is-current" : ""}>
        <time>{event.year}</time>
        <div className="kg-timeline-event">
          {event.turningPoints.map((point) => <p className="kg-timeline-milestone" key={`${point.type}-${point.year}-${point.title}`}><strong>{point.title}</strong><span>{point.explanation}</span></p>)}
          {event.topics.map((topic) => <p className="kg-timeline-topic" key={topic.topicId}><strong>{topic.name}</strong><span>新增 {topic.newCount} 篇 · 累计 {topic.cumulative} 篇</span></p>)}
          <ul>{event.papers.map((paper) => <li key={paper.recordId}><button type="button" onClick={() => onSelectPaper(paper.nodeId)}><strong>{paper.title}</strong><span>{paper.topicName || "未归类主题"} · 被引 {paper.citedByCount}</span></button></li>)}</ul>
        </div>
      </li>)}
    </ol>
    <div className="kg-timeline-insights">
      <section><h3>关键引用路径</h3>{data.keyPaths.length ? <ul>{data.keyPaths.slice(0, 3).map((path) => <li key={path.id}><strong>{path.label}</strong><span>{path.years.join(" → ")} · {path.explanation}</span></li>)}</ul> : <p>当前时间窗口内尚无至少两篇论文组成的关键路径。</p>}</section>
      <section><h3>主题演化速度</h3>{data.topicSpeedComparisons.length ? <ul>{data.topicSpeedComparisons.slice(0, 3).map((item) => <li key={`${item.leftTopicId}-${item.rightTopicId}`}>{item.explanation}</li>)}</ul> : <p>主题数量不足，暂不能比较演化速度。</p>}</section>
    </div>
  </>
}

export function TimelinePanel({ timeline, onQuery, onRetry, onCancel, onSelectPaper }: TimelinePanelProps) {
  return <section className="kg-timeline" aria-labelledby="timeline-title">
    <header><div><p className="kg-kicker">图谱 × 时间</p><h2 id="timeline-title">知识演化时间轴</h2></div>{timeline.status === "loading" && <button type="button" onClick={onCancel}>取消更新</button>}</header>
    {timeline.status === "idle" && <p role="status">正在准备时间演化数据…</p>}
    {timeline.status === "loading" && !timeline.data && <p role="status">正在读取桌面端共享演化缓存…</p>}
    {timeline.status === "error" && <div role="alert"><p>{timeline.message}</p><button type="button" onClick={onRetry}>重试</button></div>}
    {timeline.status === "empty" && <p role="status">当前时间窗口没有可显示的论文。</p>}
    {timeline.data && <TimelineContent data={timeline.data} onQuery={onQuery} onSelectPaper={onSelectPaper} />}
  </section>
}
