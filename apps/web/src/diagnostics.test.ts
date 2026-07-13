import { describe, expect, it } from "vitest"
import { configureWebDiagnosticSink, createWebDiagnostic, DIAGNOSTIC_STORAGE_KEY, recordWebDiagnostic, storeWebDiagnostic, type WebDiagnosticEvent } from "./diagnostics"

describe("privacy-safe web diagnostics", () => {
  it("stores only a bounded classification and fingerprint", () => {
    const values = new Map<string, string>()
    const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) }
    const sensitive = new Error("token=secret /Users/researcher/private-paper.pdf")
    for (let index = 0; index < 24; index += 1) storeWebDiagnostic(createWebDiagnostic("react", "render_error", sensitive), storage)
    const raw = values.get(DIAGNOSTIC_STORAGE_KEY) ?? ""
    const reports = JSON.parse(raw) as unknown[]
    expect(reports).toHaveLength(20)
    expect(raw).not.toContain("secret")
    expect(raw).not.toContain("private-paper")
    expect(raw).not.toContain("stack")
    expect(raw).not.toContain("TypeError")
    expect(raw).toContain('"exceptionType":"Error"')
  })

  it("uses fixed exception classes instead of custom messages or names", () => {
    const custom = Object.assign(new Error("research content"), { name: "secret-project-name" })
    const report = createWebDiagnostic("promise", "unhandled_rejection", custom)
    expect(report.exceptionType).toBe("Error")
    expect(JSON.stringify(report)).not.toContain("secret-project")
    expect(report.fingerprint).toMatch(/^[0-9a-f]{8}$/)
  })

  it("can forward the same privacy-safe event to an explicitly configured sink", async () => {
    const forwarded: WebDiagnosticEvent[] = []
    configureWebDiagnosticSink((event) => { forwarded.push(event) })
    try {
      recordWebDiagnostic("window", "uncaught_error", new Error("private research content"))
      await Promise.resolve()
      expect(forwarded).toHaveLength(1)
      expect(JSON.stringify(forwarded[0])).not.toContain("private research")
    } finally {
      configureWebDiagnosticSink()
    }
  })
})
