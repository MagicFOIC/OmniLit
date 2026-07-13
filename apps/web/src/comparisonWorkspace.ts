import type { ResearchWorkspace } from "@omnilit/shared-schema"

export function comparisonRecordTitle(recordId: string, workspace: ResearchWorkspace | undefined): string {
  if (!workspace) return "正在加载文献名…"
  return workspace.records.find((record) => record.recordId === recordId)?.title.trim() || "文献已不可用"
}
