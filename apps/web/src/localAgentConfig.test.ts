import { afterEach, describe, expect, it, vi } from "vitest"
import { clearLocalAgentConnection, normalizeLocalAgentConnection, probeLocalAgent, readLocalAgentConnection, saveLocalAgentConnection } from "./localAgentConfig"

function storage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key) },
    setItem: (key, value) => { values.set(key, value) }
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("runtime Local Agent connection", () => {
  it("accepts only loopback HTTP endpoints", () => {
    expect(normalizeLocalAgentConnection("http://127.0.0.1:8765", "x".repeat(24)).baseUrl).toBe("http://127.0.0.1:8765")
    expect(() => normalizeLocalAgentConnection("https://example.com", "x".repeat(24))).toThrow("回环")
    expect(() => normalizeLocalAgentConnection("http://192.168.1.2:8765", "x".repeat(24))).toThrow("回环")
  })

  it("stores the token only in session storage", () => {
    const sessionStorage = storage()
    vi.stubGlobal("window", { sessionStorage })
    saveLocalAgentConnection("http://localhost:8765", "t".repeat(24))
    expect(readLocalAgentConnection()?.token).toBe("t".repeat(24))
    clearLocalAgentConnection()
    expect(readLocalAgentConnection()).toBeUndefined()
  })

  it("validates the health response before connection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ protocolVersion: "1.0", status: "ready", service: "omnilit-local-agent" }), { status: 200, headers: { "Content-Type": "application/json" } })))
    await expect(probeLocalAgent({ baseUrl: "http://127.0.0.1:8765", token: "t".repeat(24) })).resolves.toBeUndefined()
  })

  it("turns opaque fetch failures into an actionable Origin diagnostic", async () => {
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:4173" } })
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))
    await expect(probeLocalAgent({ baseUrl: "http://127.0.0.1:8765", token: "t".repeat(24) }))
      .rejects.toThrow("--origin http://127.0.0.1:4173")
  })
})
