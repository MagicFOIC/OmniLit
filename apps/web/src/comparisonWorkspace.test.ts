import { describe, expect, it } from "vitest"
import type { ResearchWorkspace } from "@omnilit/shared-schema"
import { comparisonRecordTitle } from "./comparisonWorkspace"

const workspace: ResearchWorkspace = {
  protocolVersion: "1.0",
  status: "ready",
  compareLimit: 4,
  message: "",
  records: [{
    recordId: "e9ff2c80e79c1bdbc1ccd2a2f2447e694d",
    title: "A Readable Literature Title",
    authorsText: "",
    year: "",
    journalTitle: "",
    source: "",
    abstract: "",
    keywordsText: "",
    pdfStatus: "",
    downloaded: false,
    hasExtraction: false,
    collectionIds: []
  }]
}

describe("comparison workspace titles", () => {
  it("shows the literature title instead of its opaque record id", () => {
    expect(comparisonRecordTitle("e9ff2c80e79c1bdbc1ccd2a2f2447e694d", workspace)).toBe("A Readable Literature Title")
  })

  it("does not expose an opaque id when its record is unavailable", () => {
    expect(comparisonRecordTitle("missing-record-id", workspace)).toBe("文献已不可用")
  })
})
