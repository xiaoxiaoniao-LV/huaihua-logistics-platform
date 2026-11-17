/**3D 场景配置：模型路径、颜色映射、性能预算。
 *
 * 模型根路径可通过 VITE_3D_MODEL_BASE 环境变量覆盖，默认 /models。
 * 资源类型 → 模型相对路径的映射独立为对象，基路径变化时仅改此处。
 * 颜色一律取自 theme.ts，避免与 CSS / ECharts 出现两套色。
 */
import { hexToNumber, theme } from './theme'

// 模型根路径（可由环境变量覆盖，部署时仅改这一处）
export const MODEL_BASE = (import.meta.env.VITE_3D_MODEL_BASE as string) || '/models'

/** 资源类型 → GLB 模型相对路径（相对于 MODEL_BASE） */
export const MODEL_PATH_MAP: Record<string, string> = {
  warehouse: '/warehouse.glb',       // 仓库主体
  cold_box: '/cold_box.glb',         // 冷链箱
  shelf: '/shelf.glb',               // 货架
  vehicle: '/vehicle.glb',           // 运力（货车）
  equipment: '/equipment.glb',       // 设备
}

/** 资源状态 → 颜色映射（冷链箱/设备高亮色）：青 / 蓝紫 / 灰 / 暗灰 */
export const STATUS_COLOR: Record<string, number> = {
  available: hexToNumber(theme.color.status.available),
  booked: hexToNumber(theme.color.status.booked),
  pending: hexToNumber(theme.color.status.pending),
  offline: hexToNumber(theme.color.status.offline),
}

/** 设备异常 → 颜色映射（覆盖资源状态色）：只有告警才用橙 / 红 */
export const ALERT_COLOR: Record<string, number> = {
  critical: hexToNumber(theme.color.alert.critical),
  warn: hexToNumber(theme.color.alert.warn),
  info: hexToNumber(theme.color.alert.info),
}

/** 场景基础色 */
export const SCENE_COLOR = {
  background: hexToNumber(theme.color.bg.deep),
  grid: hexToNumber(theme.color.accent.blue),
  accent: hexToNumber(theme.color.accent.cyan),
}

/** 性能预算 */
export const PERF_BUDGET = {
  maxColdBoxes: 64,      // 最多渲染冷链箱数量
  pixelRatio: 2,         // 渲染像素比上限
  enableShadow: true,    // 是否开启阴影（设备性能不足时关）
  bloom: {
    enabled: true,       // UnrealBloom 泛光提亮（低端设备自动降级关闭）
    strength: 0.45,
    radius: 0.55,
    threshold: 0.72,
  },
}

/** 按设备能力收敛性能预算：核数过低或超宽画布时关 Bloom、降像素比 */
export function resolvePerfBudget() {
  const cores = (typeof navigator !== 'undefined' && navigator.hardwareConcurrency) || 4
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
  const cssWidth = typeof window !== 'undefined' ? window.innerWidth : 1920
  const wideCanvas = cssWidth * dpr > 3840
  const lowEnd = cores < 4

  return {
    ...PERF_BUDGET,
    pixelRatio: wideCanvas || lowEnd ? 1.5 : PERF_BUDGET.pixelRatio,
    bloom: {
      ...PERF_BUDGET.bloom,
      enabled: PERF_BUDGET.bloom.enabled && !lowEnd,
    },
  }
}

/** 默认相机位置（适配 24 x 16 x 8 米的仓库模型，俯视以看清库内布局） */
export const DEFAULT_CAMERA = {
  position: [16, 28, 30] as [number, number, number],
  target: [0, 1, 0] as [number, number, number],
}
