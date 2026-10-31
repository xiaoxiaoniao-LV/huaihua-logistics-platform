<script setup lang="ts">
import { useMatchStore } from '@/stores/match'

const match = useMatchStore()
</script>

<template>
  <div class="panel">
    <div class="panel-title">智能撮合推荐 TOP5</div>
    <div class="panel-body">
      <div v-if="!match.results.length" class="empty">暂无 available 资源可推荐</div>
      <div v-else class="match-list">
        <div v-for="(r, i) in match.results" :key="r.resource_id" class="match-item">
          <div class="match-head">
            <span class="rank">#{{ i + 1 }}</span>
            <span class="name">{{ r.name }}</span>
            <span class="score">{{ r.match_score.toFixed(1) }}</span>
          </div>
          <div class="match-score-bar">
            <div class="bar-inner" :style="{ width: `${Math.min(100, r.match_score)}%` }"></div>
          </div>
          <div class="match-meta">
            <span class="type-tag">{{ r.type }}</span>
            <span v-if="r.price != null" class="price-tag">¥{{ r.price }}/{{ r.price_unit || '天' }}</span>
          </div>
          <div v-if="r.score_breakdown" class="breakdown">
            <span class="bd-item"><i class="dot dot-price"></i>价格 {{ r.score_breakdown.price_score.toFixed(1) }}<em>/30</em></span>
            <span class="bd-item"><i class="dot dot-credit"></i>信用 {{ r.score_breakdown.credit_score.toFixed(1) }}<em>/20</em></span>
            <span class="bd-item"><i class="dot dot-window"></i>窗口 {{ r.score_breakdown.window_score.toFixed(1) }}<em>/20</em></span>
            <span class="bd-item"><i class="dot dot-type"></i>类型 {{ r.score_breakdown.type_match.toFixed(0) }}<em>/10</em></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.match-list { display: flex; flex-direction: column; gap: 8px; }
.match-item {
  padding: 8px 10px;
  border: 1px solid var(--border-glow);
  border-radius: 4px;
  background: rgba(0, 229, 255, 0.04);
}
.match-head {
  display: flex; align-items: center; gap: 8px; font-size: 12px;
}
.rank {
  width: 20px; height: 20px; border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent));
  color: var(--bg-primary); font-weight: 700; font-size: 11px;
  display: flex; align-items: center; justify-content: center;
}
.name { flex: 1; color: var(--text-primary); font-weight: 600; }
.score { color: var(--accent-cyan); font-family: 'Consolas', monospace; font-size: 14px; font-weight: 700; }

.match-score-bar {
  height: 3px; margin: 6px 0 4px;
  background: rgba(64, 158, 255, 0.15);
  border-radius: 2px; overflow: hidden;
}
.bar-inner {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-orange), var(--accent-cyan));
  border-radius: 2px; transition: width 0.5s;
}
.match-meta {
  display: flex; gap: 10px; align-items: center;
  font-size: 10px; color: var(--text-muted); font-family: 'Consolas', monospace;
}
.type-tag {
  padding: 1px 6px; border-radius: 2px;
  background: rgba(64,158,255,0.15); color: var(--accent); font-size: 10px;
}
.price-tag { color: var(--accent-orange); }
.breakdown {
  display: flex; flex-wrap: wrap; gap: 6px 12px;
  margin-top: 6px; padding-top: 6px;
  border-top: 1px dashed rgba(64,158,255,0.15);
  font-size: 10px; color: var(--text-muted); font-family: 'Consolas', monospace;
}
.bd-item { display: inline-flex; align-items: center; gap: 4px; }
.bd-item em { font-style: normal; opacity: 0.5; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.dot-price { background: #409eff; }
.dot-credit { background: #00e5ff; }
.dot-window { background: #67c23a; }
.dot-type { background: #ff9f43; }
.empty { text-align: center; color: var(--text-muted); padding: 20px; font-size: 12px; }
</style>
