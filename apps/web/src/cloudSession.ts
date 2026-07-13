import type { AuthSession, UserAccount } from "@omnilit/shared-schema"

const STORAGE_KEY = "omnilit.cloud.session.v1"

let memorySession: AuthSession | undefined

function storage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage
  } catch {
    return undefined
  }
}

export function readCloudSession(): AuthSession | undefined {
  if (memorySession) return memorySession
  const raw = storage()?.getItem(STORAGE_KEY)
  if (!raw) return undefined
  try {
    const session = JSON.parse(raw) as AuthSession
    if (!session.accessToken || Date.parse(session.expiresAt) <= Date.now()) {
      storage()?.removeItem(STORAGE_KEY)
      return undefined
    }
    memorySession = session
    return session
  } catch {
    storage()?.removeItem(STORAGE_KEY)
    return undefined
  }
}

export function writeCloudSession(session: AuthSession): void {
  memorySession = session
  storage()?.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function updateCloudSessionUser(user: UserAccount): void {
  const session = readCloudSession()
  if (session) writeCloudSession({ ...session, user })
}

export function clearCloudSession(): void {
  memorySession = undefined
  storage()?.removeItem(STORAGE_KEY)
}

export function cloudAccessToken(): string | undefined {
  return readCloudSession()?.accessToken
}
