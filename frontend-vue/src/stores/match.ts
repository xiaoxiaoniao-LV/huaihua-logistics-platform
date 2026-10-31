import { defineStore } from 'pinia'
import { recommend, type MatchResult } from '@/api/match'

interface State {
  results: MatchResult[]
  loading: boolean
}

export const useMatchStore = defineStore('match', {
  state: (): State => ({ results: [], loading: false }),
  actions: {
    async fetch(params?: { type?: string; max_price?: number; top_n?: number }) {
      this.loading = true
      try {
        const { data } = await recommend({ top_n: 5, ...params })
        this.results = data.results
      } finally {
        this.loading = false
      }
    },
  },
})
