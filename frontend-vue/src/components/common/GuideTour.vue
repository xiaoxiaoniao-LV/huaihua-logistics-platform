<script setup lang="ts">
/**
 * 新手引导：跨页面逐步高亮关键区域。
 *
 * - 首次登录自动播放一次（localStorage 记录），右下角「使用指引」可随时重播；
 * - 步骤按角色裁剪：管理员多看一步「运营统计与结算」；
 * - 遮罩只拦截点击，不阻断阅读；目标元素按 `data-guide` 选择器定位。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

interface GuideStep {
  route: string
  target: string
  title: string
  desc: string
}

const SEEN_KEY = 'hhlg_guide_seen_v1'

const store = useAuthStore()
const route = useRoute()
const router = useRouter()

const steps = computed<GuideStep[]>(() => {
  const list: GuideStep[] = [
    {
      route: '/workbench',
      target: '[data-guide="top-nav"]',
      title: '顶部导航',
      desc: '一条导航串起全部业务：资源市场、发布、订单履约、告警、设备与统计，管理员还会多出审核与孪生配置。',
    },
    {
      route: '/workbench',
      target: '[data-guide="quick-start"]',
      title: '工作台快捷入口',
      desc: '工作台汇总关键指标与待办，快捷入口可以一键跳到最常用的模块。',
    },
    {
      route: '/market',
      target: '[data-guide="market-toolbar"]',
      title: '资源市场与智能撮合',
      desc: '按类型、价格筛选冷链资源；「智能推荐」按价格、信用、可租窗口等维度给出匹配度与原因。',
    },
    {
      route: '/orders',
      target: '[data-guide="orders-panel"]',
      title: '订单履约',
      desc: '需求方下单后，供给方在此确认、开始、完成；支付与结算状态与履约状态分开跟踪。',
    },
    {
      route: '/alerts',
      target: '[data-guide="alerts-panel"]',
      title: '告警处置',
      desc: '温度越界、设备离线会自动生成告警，确认与关闭操作全程留痕。',
    },
  ]
  if (store.isAdmin) {
    list.push({
      route: '/stats',
      target: '[data-guide="settlement-panel"]',
      title: '运营统计与结算',
      desc: '管理员在此对账、推进结算状态，可下载结算凭证并查看按供给方聚合的租户分账。',
    })
  }
  return list
})

const active = ref(false)
const index = ref(0)
const rect = ref<{ top: number; left: number; width: number; height: number } | null>(null)
const tipPos = ref({ top: 0, left: 0 })
const tipEl = ref<HTMLElement | null>(null)

const step = computed(() => steps.value[index.value] || null)

let seq = 0
let autoStarted = false

function locate(selector: string): HTMLElement | null {
  return document.querySelector(selector) as HTMLElement | null
}

function waitForTarget(selector: string, timeout = 1600): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now()
    const tick = () => {
      if (locate(selector) || Date.now() - start > timeout) return resolve()
      window.setTimeout(tick, 80)
    }
    tick()
  })
}

function placeTip(r: DOMRect) {
  const h = tipEl.value?.offsetHeight || 190
  const w = tipEl.value?.offsetWidth || 340
  const below = r.bottom + 14
  let top = below + h < window.innerHeight - 12 ? below : r.top - h - 14
  top = Math.min(Math.max(12, top), Math.max(12, window.innerHeight - h - 12))
  const left = Math.min(Math.max(12, r.left + r.width / 2 - w / 2), Math.max(12, window.innerWidth - w - 12))
  tipPos.value = { top, left }
}

function measure() {
  const s = step.value
  if (!s || !active.value) return
  const el = locate(s.target)
  if (!el) {
    rect.value = null
    const mid = window.innerHeight / 2
    placeTip({
      top: mid, bottom: mid, left: window.innerWidth / 2, width: 0, height: 0,
    } as unknown as DOMRect)
    return
  }
  const r = el.getBoundingClientRect()
  rect.value = { top: r.top, left: r.left, width: r.width, height: r.height }
  placeTip(r)
}

async function go(i: number) {
  if (i < 0 || i >= steps.value.length) return
  const token = ++seq
  index.value = i
  const s = steps.value[i]
  if (route.path !== s.route) {
    await router.push(s.route)
  }
  await nextTick()
  await waitForTarget(s.target)
  if (token !== seq || !active.value) return
  measure()
  await nextTick()
  measure()
}

function start() {
  if (!store.user) return
  localStorage.setItem(SEEN_KEY, '1')
  active.value = true
  index.value = 0
  go(0)
}

function close() {
  active.value = false
  rect.value = null
  seq++
}

function onKey(e: KeyboardEvent) {
  if (!active.value) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowRight') {
    if (index.value < steps.value.length - 1) go(index.value + 1)
    else close()
  } else if (e.key === 'ArrowLeft') go(index.value - 1)
}

function onLayout() {
  if (active.value) measure()
}

watch(() => steps.value.length, () => {
  if (active.value && index.value >= steps.value.length) close()
})

watch(() => store.user, (u) => {
  if (u && !autoStarted && !localStorage.getItem(SEEN_KEY)) {
    autoStarted = true
    window.setTimeout(start, 700)
  }
}, { immediate: true })

onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('resize', onLayout)
  window.addEventListener('scroll', onLayout, true)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', onLayout)
  window.removeEventListener('scroll', onLayout, true)
})
</script>

<template>
  <button v-if="store.user && !active" class="guide-fab" type="button" @click="start">
    使用指引
  </button>

  <Teleport to="body">
    <div v-if="active" class="guide-mask">
      <div
        v-if="rect"
        class="guide-spot"
        :style="{
          top: `${rect.top - 6}px`,
          left: `${rect.left - 6}px`,
          width: `${rect.width + 12}px`,
          height: `${rect.height + 12}px`,
        }"
      />
      <div ref="tipEl" class="guide-tip" :style="{ top: `${tipPos.top}px`, left: `${tipPos.left}px` }">
        <div class="tip-head">
          <span class="tip-step">{{ index + 1 }} / {{ steps.length }}</span>
          <button class="tip-close" type="button" aria-label="关闭" @click="close">✕</button>
        </div>
        <h3>{{ step?.title }}</h3>
        <p>{{ step?.desc }}</p>
        <div class="tip-actions">
          <button class="btn btn-ghost btn-sm" type="button" @click="close">跳过</button>
          <span class="spacer" />
          <button class="btn btn-ghost btn-sm" type="button" :disabled="index === 0" @click="go(index - 1)">
            上一步
          </button>
          <button
            class="btn btn-sm"
            type="button"
            @click="index === steps.length - 1 ? close() : go(index + 1)"
          >
            {{ index === steps.length - 1 ? '完成' : '下一步' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.guide-fab {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 1500;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid var(--border-glow);
  background: rgba(8, 20, 40, 0.9);
  color: var(--accent-cyan);
  font-size: 12px;
  letter-spacing: 1px;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
}
.guide-fab:hover { border-color: var(--accent-cyan); }

.guide-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
}
.guide-spot {
  position: fixed;
  border-radius: 8px;
  border: 1px solid var(--accent-cyan);
  box-shadow: 0 0 0 9999px rgba(2, 8, 20, 0.72), 0 0 18px rgba(0, 229, 255, 0.45);
  pointer-events: none;
}
.guide-tip {
  position: fixed;
  z-index: 2001;
  width: 340px;
  padding: 16px 18px;
  border-radius: 10px;
  border: 1px solid var(--border-glow);
  background: rgba(8, 20, 40, 0.98);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.55);
  color: var(--text-primary);
}
.tip-head { display: flex; align-items: center; justify-content: space-between; }
.tip-step { font-size: 12px; color: var(--accent-cyan); letter-spacing: 1px; }
.tip-close {
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.tip-close:hover { color: var(--text-primary); }
.guide-tip h3 { margin: 8px 0 6px; font-size: 16px; }
.guide-tip p { margin: 0 0 14px; font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.tip-actions { display: flex; align-items: center; }
.spacer { flex: 1; }
</style>
