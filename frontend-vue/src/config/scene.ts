/**3D 场景配置：模型路径、颜色映射、性能预算。
 *
 * 模型根路径可通过 VITE_3D_MODEL_BASE 环境变量覆盖，默认 /models。
 * 资源类型 → 模型相对路径的映射独立为对象，基路径变化时仅改此处。
 */

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

/** 资源状态 → 颜色映射（冷链箱/设备高亮色） */
export const STATUS_COLOR: Record<string, number> = {
  available: 0x00ff88, // 绿色：可用
  booked: 0xff9f43,    // 橙色：已预约
  offline: 0xff4757,   // 红色：离线
  pending: 0x409eff,   // 蓝色：待审核
}

/** 设备异常 → 颜色映射（覆盖资源状态色） */
export const ALERT_COLOR: Record<string, number> = {
  critical: 0xff2222,  // 严重告警：红
  warn: 0xffaa00,      // 警告：橙黄
}

/** 性能预算 */
export const PERF_BUDGET = {
  maxColdBoxes: 64,      // 最多渲染冷链箱数量
  pixelRatio: 2,         // 渲染像素比上限
  enableShadow: true,    // 是否开启阴影（设备性能不足时关）
}

/** 默认相机位置（适配 24 x 16 x 8 米的仓库模型，俯视以看清库内布局） */
export const DEFAULT_CAMERA = {
  position: [16, 28, 30] as [number, number, number],
  target: [0, 1, 0] as [number, number, number],
}
