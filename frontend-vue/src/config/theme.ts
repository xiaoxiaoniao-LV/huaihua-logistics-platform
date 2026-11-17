/**大屏视觉令牌单一来源。
 *
 * JS（Three / ECharts）与 CSS 都从这里取值：启动时 applyTheme() 把令牌写入
 * document.documentElement 的 CSS 变量，组件样式只引用变量，不再各自写色值。
 * style.css 中的 :root 保留同值兜底，避免脚本执行前闪烁。
 */

export const theme = {
  color: {
    bg: {
      page: '#050d1f',
      deep: '#030a17',
      panel: 'rgba(10, 26, 54, 0.85)',
      panelSoft: 'rgba(10, 26, 54, 0.6)',
      panelHover: 'rgba(20, 46, 84, 0.85)',
      inset: 'rgba(5, 13, 31, 0.7)',
    },
    border: {
      base: 'rgba(64, 158, 255, 0.35)',
      soft: 'rgba(64, 158, 255, 0.14)',
      strong: 'rgba(0, 229, 255, 0.55)',
    },
    text: {
      primary: '#f0f5ff',
      secondary: 'rgba(240, 245, 255, 0.72)',
      muted: 'rgba(240, 245, 255, 0.45)',
    },
    accent: {
      blue: '#409eff',
      cyan: '#00e5ff',
      green: '#00ff88',
      violet: '#7c6cff',
      amber: '#ff9f43',
      red: '#ff4757',
    },
    /** 资源状态：与告警色彻底分离（橙/红只保留给告警） */
    status: {
      available: '#00e5ff',
      booked: '#7c6cff',
      pending: '#8fa3b8',
      offline: '#4a5a6a',
    },
    /** 告警分级 */
    alert: {
      critical: '#ff4757',
      warn: '#ff9f43',
      info: '#409eff',
    },
  },
  /** 字号阶（最小 11px，兼顾 1080p 与 2K/4K 远距离观看） */
  font: {
    xs: 11,
    sm: 12,
    base: 13,
    md: 14,
    lg: 16,
    xl: 20,
    display: 28,
  },
  /** 间距阶 */
  space: { x1: 4, x2: 8, x3: 12, x4: 16, x5: 24 },
  radius: { sm: 4, md: 6, lg: 8 },
  shadow: {
    panel: '0 10px 36px rgba(0, 229, 255, 0.10)',
    glow: '0 0 16px rgba(0, 229, 255, 0.28)',
  },
  fontFamily: {
    sans: "'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    mono: "'Consolas', 'Monaco', 'Courier New', monospace",
  },
} as const

/** CSS 变量名 → 值，供 applyTheme 批量注入 */
function buildVars(): Record<string, string> {
  const c = theme.color
  const vars: Record<string, string> = {
    '--bg-primary': c.bg.page,
    '--bg-deep': c.bg.deep,
    '--bg-secondary': '#0a1a36',
    '--bg-card': c.bg.panel,
    '--bg-card-soft': c.bg.panelSoft,
    '--bg-card-hover': c.bg.panelHover,
    '--bg-inset': c.bg.inset,
    '--border-glow': c.border.base,
    '--border-soft': c.border.soft,
    '--border-strong': c.border.strong,
    '--text-primary': c.text.primary,
    '--text-secondary': c.text.secondary,
    '--text-muted': c.text.muted,
    '--accent': c.accent.blue,
    '--accent-cyan': c.accent.cyan,
    '--accent-green': c.accent.green,
    '--accent-violet': c.accent.violet,
    '--accent-orange': c.accent.amber,
    '--accent-red': c.accent.red,
    '--status-available': c.status.available,
    '--status-booked': c.status.booked,
    '--status-pending': c.status.pending,
    '--status-offline': c.status.offline,
    '--alert-critical': c.alert.critical,
    '--alert-warn': c.alert.warn,
    '--alert-info': c.alert.info,
    '--font-sans': theme.fontFamily.sans,
    '--font-mono': theme.fontFamily.mono,
    '--shadow-panel': theme.shadow.panel,
    '--shadow-glow': theme.shadow.glow,
  }
  Object.entries(theme.font).forEach(([k, v]) => (vars[`--fs-${k}`] = `${v}px`))
  Object.entries(theme.space).forEach(([k, v]) => (vars[`--space-${k.replace('x', '')}`] = `${v}px`))
  Object.entries(theme.radius).forEach(([k, v]) => (vars[`--radius-${k}`] = `${v}px`))
  return vars
}

/** 把主题令牌写入根元素（main 入口启动时调用一次） */
export function applyTheme() {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  Object.entries(buildVars()).forEach(([k, v]) => root.style.setProperty(k, v))
}

/** '#00e5ff' → 0x00e5ff，供 Three.js 材质使用 */
export function hexToNumber(hex: string): number {
  return parseInt(hex.replace('#', ''), 16)
}
