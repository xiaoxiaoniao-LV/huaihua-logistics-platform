<script setup lang="ts">
import { useMatchStore } from '@/stores/match'
import { fmtPrice } from '@/utils/format'
import { RESOURCE_TYPE_LABEL } from '@/utils/labels'

const match = useMatchStore()

const barWidth = (score: number) => `${Math.min(100, (score / 120) * 100)}%`
</script>

<template>
  <div class="panel panel--secondary panel--grow">
    <div class="panel-title">智能撮合推荐 TOP5</div>
    <div class="panel-body">
      <div v-if="!match.results.length" class="empty">暂无可用资源可推荐</div>
      <div v-else class="match-list">
        <div v-for="(r, i) in match.results" :key="r.resource_id" class="match-item">
          <div class="match-head">
            <span class="rank">#{{ i + 1 }}</span>
            <span class="name">{{ r.name }}</span>
            <span class="score">{{ r.match_score.toFixed(1) }}</span>
          </div>
          <div class="match-score-bar">
            <div class="bar-inner" :style="{ '--w': barWidth(r.match_score) }"></div>
          </div>
          <div class="match-meta">
            <span class="type-tag">{{ RESOURCE_TYPE_LABEL[r.type] || r.type }}</span>
            <span v-if="r.price != null" class="price-tag">{{ fmtPrice(r.price, r.price_unit) }}</span>
          </div>
          <div v-if="r.reasons?.length" class="reasons">
            <span v-for="reason in r.reasons" :key="reason" class="reason">{{ reason }}</span>
          </div>
          <div v-if="r.score_breakdown" class="breakdown">
            <span class="bd-item"><i class="dot dot-price"></i>价格 {{ r.score_breakdown.price_score.toFixed(1) }}<em>/30</em></span>
            <span class="bd-item"><i class="dot dot-credit"></i>信用 {{ r.score_breakdown.credit_score.toFixed(1) }}<em>/20</em></span>
            <span class="bd-item"><i class="dot dot-window"></i>窗口 {{ r.score_breakdown.window_score.toFixed(1) }}<em>/20</em></span>
            <span class="bd-item"><i class="dot dot-type"></i>类型 {{ r.score_breakdown.type_match.toFixed(0) }}<em>/10</em></span>
            <span class="bd-item"><i class="dot dot-rating"></i>口碑 {{ r.score_breakdown.rating_score.toFixed(1) }}<em>/15</em></span>
            <span class="bd-item"><i class="dot dot-hot"></i>热度 {{ r.score_breakdown.hotness_score.toFixed(1) }}<em>/10</em></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.match-list { display: flex; flex-direction: column; gap: var(--space-2); }
.match-item {
  padding: var(--space-2) 10px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: rgba(0, 229, 255, 0.04);
  transition: border-color 0.2s, background 0.2s;
}
.match-item:hover { border-color: var(--border-glow); background: rgba(0, 229, 255, 0.08); }
.match-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
.rank {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent));
  color: var(--bg-primary);
  font-weight: 700;
  font-size: var(--fs-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.name {
  flex: 1;
  color: var(--text-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.score {
  color: var(--accent-cyan);
  font-family: var(--font-mono);
  font-size: var(--fs-md);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.match-score-bar {
  height: 4px;
  margin: 6px 0 var(--space-1);
  background: rgba(64, 158, 255, 0.15);
  border-radius: 2px;
  overflow: hidden;
}
/* 匹配度条从 0 过渡到目标宽度，进程感更强 */
.bar-inner {
  height: 100%;
  width: var(--w);
  background: linear-gradient(90deg, var(--accent-violet), var(--accent-cyan));
  border-radius: 2px;
  animation: bar-grow 0.9s cubic-bezier(0.22, 0.8, 0.3, 1) both;
  transition: width 0.6s ease;
}
@keyframes bar-grow {
  from { width: 0; }
  to   { width: var(--w); }
}
.match-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.type-tag {
  padding: 1px 6px;
  border-radius: 2px;
  background: rgba(64, 158, 255, 0.15);
  color: var(--accent);
  font-size: var(--fs-xs);
}
.price-tag { color: var(--accent-orange); font-variant-numeric: tabular-nums; }
.reasons { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: 5px; }
.reason {
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(0, 255, 136, 0.12);
  color: var(--accent-green);
  font-size: var(--fs-xs);
}
.breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 6px var(--space-3);
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--border-soft);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.bd-item { display: inline-flex; align-items: center; gap: var(--space-1); }
.bd-item em { font-style: normal; opacity: 0.5; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex: none; }
.dot-price { background: var(--accent); }
.dot-credit { background: var(--accent-cyan); }
.dot-window { background: var(--accent-green); }
.dot-type { background: var(--accent-orange); }
.dot-rating { background: var(--accent-violet); }
.dot-hot { background: var(--status-pending); }
.empty { text-align: center; color: var(--text-muted); padding: 20px; font-size: var(--fs-sm); }
</style>
