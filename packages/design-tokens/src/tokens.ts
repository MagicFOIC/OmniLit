export const colors = {
  light: {
    canvas: "#f8fafc",
    canvasTop: "#fbfdff",
    canvasBottom: "#f1f5f9",
    surface: "#ffffff",
    surfaceSoft: "#f5f8fc",
    border: "#e2e8f0",
    borderStrong: "#cbd5e1",
    text: "#0f172a",
    textSecondary: "#475569",
    textMuted: "#64748b",
    accent: "#2563eb",
    success: "#059669",
    warning: "#d97706",
    error: "#dc2626"
  },
  dark: {
    canvas: "#0b1220",
    canvasTop: "#111c30",
    canvasBottom: "#08101d",
    surface: "#172033",
    surfaceSoft: "#111c2e",
    border: "#2b3a51",
    borderStrong: "#40516a",
    text: "#e5eefb",
    textSecondary: "#cbd5e1",
    textMuted: "#9aacbf",
    accent: "#60a5fa",
    success: "#34d399",
    warning: "#fbbf24",
    error: "#f87171"
  }
} as const

export const spacing = { xs: 4, sm: 8, md: 12, lg: 20, xl: 28 } as const
export const radii = { small: 6, medium: 10, large: 16, pill: 999 } as const
export const motion = { fast: 120, normal: 180, expand: 220 } as const
export const layout = { sidebarCollapsed: 72, sidebarExpanded: 208, compactBreakpoint: 1040, narrowBreakpoint: 760 } as const

export const graphColors = {
  paper: "#2563eb",
  author: "#7c3aed",
  institution: "#0891b2",
  topic: "#059669",
  method: "#d97706",
  dataset: "#db2777",
  result: "#dc2626",
  relation: "#64748b"
} as const
