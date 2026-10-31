/** 从 axios 错误中提取可读的错误信息（兼容 FastAPI 的字符串 detail 与 422 校验数组）。 */
export function apiError(e: any, fallback = '操作失败'): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('；')
  }
  if (e?.message) return String(e.message)
  return fallback
}
