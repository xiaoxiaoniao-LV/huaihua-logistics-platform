import { defineStore } from 'pinia'
import { listOrders, type Order } from '@/api/orders'

interface State {
  items: Order[]
  loading: boolean
}

export const useOrdersStore = defineStore('orders', {
  state: (): State => ({ items: [], loading: false }),
  actions: {
    async fetch(params?: { mine?: 'demander' | 'supplier'; page?: number; page_size?: number }) {
      this.loading = true
      try {
        const { data } = await listOrders({ page_size: 50, ...params })
        this.items = data
      } finally {
        this.loading = false
      }
    },
    /** WebSocket order_status_changed / order_created 事件触发 */
    onRealtime(data: any) {
      const idx = this.items.findIndex((o) => o.id === data.order_id)
      if (idx >= 0 && data.new_status) {
        this.items[idx].status = data.new_status
      }
    },
  },
})
