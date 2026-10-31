import { defineStore } from 'pinia'
import { listResources, type Resource } from '@/api/resources'

interface State {
  items: Resource[]
  loading: boolean
  lastFetched: number
}

export const useResourcesStore = defineStore('resources', {
  state: (): State => ({ items: [], loading: false, lastFetched: 0 }),
  getters: {
    available: (s) => s.items.filter((r) => r.status === 'available'),
    byType: (s) => {
      const map: Record<string, number> = {}
      s.items.forEach((r) => (map[r.type] = (map[r.type] || 0) + 1))
      return map
    },
  },
  actions: {
    async fetch(params?: { type?: string; status?: string; keyword?: string; page?: number; page_size?: number }) {
      this.loading = true
      try {
        // 大屏与孪生需要全量资源，默认取 200 条
        const { data } = await listResources({ page_size: 200, ...params })
        this.items = data
        this.lastFetched = Date.now()
      } finally {
        this.loading = false
      }
    },
    // WebSocket 推送时局部更新
    upsertResource(r: Resource) {
      const idx = this.items.findIndex((x) => x.id === r.id)
      if (idx >= 0) this.items[idx] = { ...this.items[idx], ...r }
      else this.items.unshift(r)
    },
  },
})
