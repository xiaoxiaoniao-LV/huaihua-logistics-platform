/** 价格展示：统一为 `¥88.00/天`，避免出现 `¥88.00/元/天` 这类货币符号与单位重复。 */
export function fmtPrice(price: number | string | null | undefined, unit?: string | null): string {
  if (price === null || price === undefined || price === '') return '-'
  const u = (unit || '天').trim().replace(/^[元￥¥]\s*\/\s*/, '').replace(/^\//, '')
  return `¥${price}/${u || '天'}`
}
