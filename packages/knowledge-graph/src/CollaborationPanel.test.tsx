import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { CollaborationSnapshot } from "@omnilit/shared-schema"
import type { CollaborationDataSource } from "./CollaborationPanel"
import { applyCollaborationEvent, CollaborationPanel } from "./CollaborationPanel"

describe("CollaborationPanel", () => {
  it("renders a semantic loading state without leaking credentials", () => {
    const dataSource: CollaborationDataSource = {
      getSnapshot: async () => ({ protocolVersion: "1.0", recordId: "paper-001", revision: 0, canEdit: true, syncEnabled: true, annotations: [] }),
      mutate: async () => { throw new Error("unused") },
      subscribe: async () => 0
    }
    const html = renderToStaticMarkup(<CollaborationPanel recordId="paper-001" dataSource={dataSource} target={{ type: "graph", id: "paper-001", label: "整个图谱" }} />)
    expect(html).toContain("共享批注")
    expect(html).toContain("正在读取团队批注")
    expect(html).not.toContain("Authorization")
  })

  it("applies ordered upsert and delete events without replaying stale revisions", () => {
    const snapshot: CollaborationSnapshot = { protocolVersion: "1.0", recordId: "paper-001", revision: 0, canEdit: true, syncEnabled: true, annotations: [] }
    const annotation = { protocolVersion: "1.0", id: "note-1", recordId: "paper-001", targetType: "graph", targetId: "paper-001", body: "Review", authorId: "owner", authorDisplayName: "Owner", revision: 1, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z" } as const
    const upsert = { protocolVersion: "1.0", recordId: "paper-001", revision: 1, clientMutationId: "m1", action: "annotation.upserted", annotationId: "note-1", annotation, actorId: "owner", occurredAt: "2026-01-01T00:00:00Z" } as const
    const afterUpsert = applyCollaborationEvent(snapshot, upsert)
    expect(afterUpsert.annotations).toEqual([annotation])
    expect(applyCollaborationEvent(afterUpsert, upsert)).toBe(afterUpsert)
    const deleted = applyCollaborationEvent(afterUpsert, { ...upsert, revision: 2, action: "annotation.deleted", annotation: undefined })
    expect(deleted.annotations).toEqual([])
    expect(deleted.revision).toBe(2)
  })
})
