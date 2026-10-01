<script setup lang="ts">
import type { AllocEnvelope } from '../api'
const props = defineProps<{ data: AllocEnvelope; busy?: boolean }>()
const emit = defineEmits<{ (e: 'confirm'): void; (e: 'cancel'): void }>()
const gapLabel = (d: AllocEnvelope) =>
  d.gap ? `${d.gap.left_label} – ${d.gap.right_label} · ${d.gap.width_m} m 空档` : ''
</script>
<template>
  <div class="card ss-trial-panel">
    <div class="ss-trial-head">
      <span class="badge badge-warn">试摆 · 未入库</span>
      <strong>{{ gapLabel(props.data) }}</strong>
    </div>
    <p class="muted ss-trial-note">以下结论仅限该空档内按优先序从左填空，运行表未新增任何行。</p>

    <h3 class="ss-trial-title">放得下（{{ props.data.placements.length }}）</h3>
    <table>
      <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
      <tbody>
        <tr v-for="p in props.data.placements" :key="p.vendor_id">
          <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!props.data.placements.length" class="muted">该空档内一个都放不下</p>

    <h3 class="ss-trial-title ss-bad-title">
      放不下（{{ props.data.rejected.length }}）
    </h3>
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因（限该空档）</th></tr></thead>
      <tbody>
        <tr v-for="r in props.data.rejected" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!props.data.rejected.length" class="muted">全部放下</p>

    <div class="ss-trial-actions">
      <button class="btn btn-ok" :disabled="props.busy" @click="emit('confirm')">
        {{ props.busy ? '确认中…' : '确认入库' }}
      </button>
      <button class="btn btn-ghost" :disabled="props.busy" @click="emit('cancel')">取消</button>
    </div>
  </div>
</template>
