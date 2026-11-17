/**指挥大屏等比缩放：以 1920×1080 为设计基准，整体缩放适配 1080p / 2K / 4K。
 *
 * - scale = min(vw / 1920, vh / 1080)，多出来的方向留黑边，不裁切、不变形
 * - 小屏（手机/窄窗口）不启用缩放，回退到流式单列布局
 */
import { onMounted, onUnmounted, ref } from 'vue'

export const DESIGN_WIDTH = 1920
export const DESIGN_HEIGHT = 1080

/** 低于该视口宽度时视为非大屏，关闭缩放 */
const MIN_SCALED_WIDTH = 1024
const MIN_SCALED_HEIGHT = 600

export function useScreenScale() {
  const scale = ref(1)
  const scaled = ref(false)

  const update = () => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    scaled.value = vw >= MIN_SCALED_WIDTH && vh >= MIN_SCALED_HEIGHT
    scale.value = scaled.value
      ? Math.min(vw / DESIGN_WIDTH, vh / DESIGN_HEIGHT)
      : 1
  }

  update()
  onMounted(() => {
    update()
    window.addEventListener('resize', update)
  })
  onUnmounted(() => window.removeEventListener('resize', update))

  return { scale, scaled }
}
