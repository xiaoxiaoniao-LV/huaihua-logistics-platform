/**数字滚动：指标值变化时从旧值补间到新值，避免大屏数字硬跳。 */
import { onUnmounted, ref, watch } from 'vue'

export function useCountUp(source: () => number, duration = 700) {
  const display = ref(0)
  let raf = 0
  let from = 0
  let to = 0
  let startAt = 0

  const step = (now: number) => {
    const p = Math.min(1, (now - startAt) / duration)
    const eased = 1 - Math.pow(1 - p, 3)
    display.value = from + (to - from) * eased
    if (p < 1) raf = requestAnimationFrame(step)
  }

  const animate = (next: number) => {
    cancelAnimationFrame(raf)
    from = display.value
    to = Number.isFinite(next) ? next : 0
    startAt = performance.now()
    raf = requestAnimationFrame(step)
  }

  watch(source, (v) => animate(Number(v) || 0), { immediate: true })
  onUnmounted(() => cancelAnimationFrame(raf))

  return display
}
