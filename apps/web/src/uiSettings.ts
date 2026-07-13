import type { BusinessSettings } from "@omnilit/shared-schema"

export function applyBusinessSettings(settings: Pick<BusinessSettings, "themeMode" | "density" | "reduceMotion" | "highContrast">): void {
  if (typeof document === "undefined") return
  const root = document.documentElement
  if (settings.themeMode === "system") root.removeAttribute("data-theme")
  else root.dataset.theme = settings.themeMode
  root.dataset.density = settings.density
  root.dataset.reduceMotion = String(settings.reduceMotion)
  root.dataset.highContrast = String(settings.highContrast)
}
