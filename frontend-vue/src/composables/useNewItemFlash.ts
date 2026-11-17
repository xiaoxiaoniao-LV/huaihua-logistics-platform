/**新条目高亮：列表里新出现的行闪一下（1.5s 后自动消失）。 */
import { onUnmounted, ref, watch } from 'vue'

export function useNewItemFlash(ids: () => (string | number)[], hold = 1500) {
  const flashing = ref<Set<string>>(new Set())
  let known: Set<string> | null = null
  const timers = new Set<number>()

  const mark = (id: string, on: boolean) => {
    const next = new Set(flashing.value)
    on ? next.add(id) : next.delete(id)
    flashing.value = next
  }

  const run = () => {
    const next = new Set(ids().map(String))
    if (known) {
      next.forEach((id) => {
        if (known!.has(id)) return
        mark(id, true)
        const t = window.setTimeout(() => {
          mark(id, false)
          timers.delete(t)
        }, hold)
        timers.add(t)
      })
    }
    known = next
  }

  watch(ids, run, { immediate: true, deep: true })
  onUnmounted(() => {
    timers.forEach((t) => clearTimeout(t))
    timers.clear()
  })

  return flashing
}
