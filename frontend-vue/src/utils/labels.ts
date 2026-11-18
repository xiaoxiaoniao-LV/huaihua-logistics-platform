/**业务枚举的中文展示与样式映射（大屏只显示中文，不出现英文枚举）。 */

export const RESOURCE_TYPE_LABEL: Record<string, string> = {
  warehouse: '冷库',
  cold_box: '冷链箱位',
  vehicle: '冷藏运输',
  equipment: '温控设备',
}

export const RESOURCE_STATUS_LABEL: Record<string, string> = {
  available: '可预约',
  booked: '已预约',
  pending: '待审核',
  offline: '已下架',
}

/** 资源状态标签样式：青 / 蓝紫 / 灰 / 暗灰，避开告警橙红 */
export const RESOURCE_STATUS_CLASS: Record<string, string> = {
  available: 'tag-available',
  booked: 'tag-booked',
  pending: 'tag-pending',
  offline: 'tag-offline',
}

export const ORDER_STATUS_LABEL: Record<string, string> = {
  pending: '待确认',
  confirmed: '已确认',
  ongoing: '进行中',
  finished: '已完成',
  cancelled: '已取消',
}

export const ORDER_STATUS_CLASS: Record<string, string> = {
  pending: 'tag-pending',
  confirmed: 'tag-available',
  ongoing: 'tag-info',
  finished: 'tag-available',
  cancelled: 'tag-offline',
}

export const ALERT_LEVEL_LABEL: Record<string, string> = {
  critical: '严重',
  warn: '警告',
  info: '提示',
}

/** 告警等级 → 容器样式（红底呼吸 / 琥珀左边框 / 蓝左边框） */
export const ALERT_LEVEL_CLASS: Record<string, string> = {
  critical: 'alert-critical',
  warn: 'alert-warn',
  info: 'alert-info',
}

/** 货位锚点 → 货位编号：Anchor_Slot_R01C03L2S1 → 01-03-2左（排-列-层-面） */
export function slotCode(anchor?: string | null): string {
  const m = /^Anchor_Slot_R(\d{2})C(\d{2})L(\d)S(\d)$/.exec(anchor || '')
  if (!m) return ''
  return `${m[1]}-${m[2]}-${m[3]}${m[4] === '1' ? '左' : '右'}`
}

/** 货位锚点 → 排号：Anchor_Slot_R03C01L1S1 → 03 */
export function slotRow(anchor?: string | null): string {
  const m = /^Anchor_Slot_R(\d{2})/.exec(anchor || '')
  return m ? m[1] : ''
}
