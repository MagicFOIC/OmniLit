import type { TaskProgress } from "@omnilit/shared-schema"

export type Platform = "browser" | "qt-desktop" | "tauri-desktop"
export interface OpenFileOptions { accept?: string[]; multiple?: boolean }
export interface SelectedLocalFile { name: string; size: number; mimeType: string; file: File }
export interface SaveFileOptions { suggestedName: string; data: BlobPart; mimeType?: string }
export interface SaveFileResult { saved: boolean; fileName: string }
export interface AppInfo { name: string; version: string; platform: Platform }
export interface LocalServiceStatus { available: boolean; reason?: string }
export interface TaskProgressEvent { taskId: string; progress: TaskProgress }

export class PlatformCapabilityError extends Error {
  constructor(readonly capability: string, message: string) {
    super(message)
    this.name = "PlatformCapabilityError"
  }
}

export interface PlatformBridge {
  readonly platform: Platform
  openLocalFiles(options?: OpenFileOptions): Promise<SelectedLocalFile[]>
  saveFile(options: SaveFileOptions): Promise<SaveFileResult>
  openExternalUrl(url: string): Promise<void>
  getAppInfo(): Promise<AppInfo>
  revealInFileManager(path: string): Promise<void>
  getLocalServiceStatus(): Promise<LocalServiceStatus>
  subscribeTaskProgress(listener: (event: TaskProgressEvent) => void): () => void
}

interface QtNativeBridge {
  getAppInfo(callback: (value: AppInfo) => void): void
  getLocalServiceStatus(callback: (value: LocalServiceStatus) => void): void
  openExternalUrl(url: string, callback: (opened: boolean) => void): void
}

interface QtWebChannelInstance {
  objects: {
    omnilitDesktopBridge?: QtNativeBridge
    [name: string]: unknown
  }
}

type QtWebChannelConstructor = new (
  transport: unknown,
  ready: (channel: QtWebChannelInstance) => void
) => unknown

declare global {
  interface Window {
    qt?: { webChannelTransport?: unknown }
    QWebChannel?: QtWebChannelConstructor
  }
}

function assertExternalUrl(value: string): URL {
  const url = new URL(value)
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new PlatformCapabilityError("openExternalUrl", "Only HTTP and HTTPS links may be opened.")
  }
  return url
}

export class BrowserPlatformBridge implements PlatformBridge {
  readonly platform = "browser" as const

  constructor(private readonly version = "0.1.0") {}

  openLocalFiles(options: OpenFileOptions = {}): Promise<SelectedLocalFile[]> {
    return new Promise((resolve) => {
      const input = document.createElement("input")
      input.type = "file"
      input.accept = (options.accept ?? []).join(",")
      input.multiple = options.multiple ?? false
      input.onchange = () => resolve(Array.from(input.files ?? []).map((file) => ({
        name: file.name, size: file.size, mimeType: file.type, file
      })))
      input.oncancel = () => resolve([])
      input.click()
    })
  }

  async saveFile(options: SaveFileOptions): Promise<SaveFileResult> {
    const blob = new Blob([options.data], { type: options.mimeType ?? "application/octet-stream" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = options.suggestedName
    anchor.click()
    URL.revokeObjectURL(url)
    return { saved: true, fileName: options.suggestedName }
  }

  async openExternalUrl(value: string): Promise<void> {
    const url = assertExternalUrl(value)
    window.open(url, "_blank", "noopener,noreferrer")
  }

  async getAppInfo(): Promise<AppInfo> {
    return { name: "OmniLit Web", version: this.version, platform: this.platform }
  }

  async revealInFileManager(_path: string): Promise<void> {
    throw new PlatformCapabilityError("revealInFileManager", "File-manager reveal is unavailable in a browser.")
  }

  async getLocalServiceStatus(): Promise<LocalServiceStatus> {
    return { available: false, reason: "Local Agent is not configured for this browser session." }
  }

  subscribeTaskProgress(_listener: (event: TaskProgressEvent) => void): () => void {
    return () => undefined
  }
}

function loadQtWebChannel(): Promise<QtNativeBridge> {
  if (typeof window === "undefined" || !window.qt?.webChannelTransport) {
    return Promise.reject(new PlatformCapabilityError("qtWebChannel", "Qt WebChannel transport is unavailable."))
  }
  const connect = (): Promise<QtNativeBridge> => new Promise((resolve, reject) => {
    const Constructor = window.QWebChannel
    if (!Constructor) {
      reject(new PlatformCapabilityError("qtWebChannel", "Qt WebChannel runtime did not load."))
      return
    }
    new Constructor(window.qt?.webChannelTransport, (channel) => {
      const bridge = channel.objects.omnilitDesktopBridge
      if (bridge) resolve(bridge)
      else reject(new PlatformCapabilityError("qtWebChannel", "OmniLit desktop bridge is unavailable."))
    })
  })
  if (window.QWebChannel) return connect()
  return new Promise((resolve, reject) => {
    const script = document.createElement("script")
    script.src = "qrc:///qtwebchannel/qwebchannel.js"
    script.onload = () => connect().then(resolve, reject)
    script.onerror = () => reject(new PlatformCapabilityError("qtWebChannel", "Qt WebChannel runtime could not be loaded."))
    document.head.appendChild(script)
  })
}

export class QtWebChannelPlatformBridge implements PlatformBridge {
  readonly platform = "qt-desktop" as const
  #native: Promise<QtNativeBridge> | undefined

  constructor(private readonly version = "0.1.0", private readonly connect: () => Promise<QtNativeBridge> = loadQtWebChannel) {}

  private native(): Promise<QtNativeBridge> {
    this.#native ??= this.connect()
    return this.#native
  }

  async openLocalFiles(): Promise<SelectedLocalFile[]> {
    throw new PlatformCapabilityError("openLocalFiles", "Native file selection is not exposed by this migration bridge.")
  }

  async saveFile(_options: SaveFileOptions): Promise<SaveFileResult> {
    throw new PlatformCapabilityError("saveFile", "Native file saving is not exposed by this migration bridge.")
  }

  async openExternalUrl(value: string): Promise<void> {
    const url = assertExternalUrl(value)
    const native = await this.native()
    const opened = await new Promise<boolean>((resolve) => native.openExternalUrl(url.toString(), resolve))
    if (!opened) throw new PlatformCapabilityError("openExternalUrl", "The desktop shell rejected the external URL.")
  }

  async getAppInfo(): Promise<AppInfo> {
    const native = await this.native()
    return new Promise((resolve) => native.getAppInfo(resolve))
  }

  async revealInFileManager(_path: string): Promise<void> {
    throw new PlatformCapabilityError("revealInFileManager", "File-manager reveal is not exposed by this migration bridge.")
  }

  async getLocalServiceStatus(): Promise<LocalServiceStatus> {
    const native = await this.native()
    return new Promise((resolve) => native.getLocalServiceStatus(resolve))
  }

  subscribeTaskProgress(_listener: (event: TaskProgressEvent) => void): () => void {
    return () => undefined
  }

  async fallbackAppInfo(): Promise<AppInfo> {
    try {
      return await this.getAppInfo()
    } catch {
      return { name: "OmniLit", version: this.version, platform: this.platform }
    }
  }
}

export function createPlatformBridge(version = "0.1.0", qtEmbedded = false): PlatformBridge {
  return qtEmbedded ? new QtWebChannelPlatformBridge(version) : new BrowserPlatformBridge(version)
}

export interface MockBridgeOptions {
  files?: SelectedLocalFile[]
  localService?: LocalServiceStatus
  appInfo?: AppInfo
}

export class MockPlatformBridge implements PlatformBridge {
  readonly platform = "browser" as const
  readonly openedUrls: string[] = []
  readonly savedFiles: SaveFileOptions[] = []
  readonly #listeners = new Set<(event: TaskProgressEvent) => void>()

  constructor(private readonly options: MockBridgeOptions = {}) {}

  async openLocalFiles(): Promise<SelectedLocalFile[]> { return this.options.files ?? [] }
  async saveFile(options: SaveFileOptions): Promise<SaveFileResult> {
    this.savedFiles.push(options)
    return { saved: true, fileName: options.suggestedName }
  }
  async openExternalUrl(value: string): Promise<void> { this.openedUrls.push(assertExternalUrl(value).toString()) }
  async getAppInfo(): Promise<AppInfo> { return this.options.appInfo ?? { name: "OmniLit Mock", version: "test", platform: this.platform } }
  async revealInFileManager(_path: string): Promise<void> { throw new PlatformCapabilityError("revealInFileManager", "Unavailable in mock browser mode.") }
  async getLocalServiceStatus(): Promise<LocalServiceStatus> { return this.options.localService ?? { available: false, reason: "Mock offline" } }
  subscribeTaskProgress(listener: (event: TaskProgressEvent) => void): () => void {
    this.#listeners.add(listener)
    return () => this.#listeners.delete(listener)
  }
  emitTaskProgress(event: TaskProgressEvent): void { this.#listeners.forEach((listener) => listener(event)) }
}
