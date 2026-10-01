<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const SEGMENT_ID = 1
const PREVIEW_KEY = 'ss_preview_v1'

const run = ref<any>(null)
const preview = ref<any | null>(null)

onMounted(async () => {
  const latest = await api(`/allocate/latest?segment_id=${SEGMENT_ID}`)
  run.value = latest
  const raw = sessionStorage.getItem(PREVIEW_KEY)
  if (raw) {
    try {
      const p = JSON.parse(raw)
      // 只有「基于当前最新已入库运行」的试摆结论才可展示；确认后基线变化即作废
      if (p.baseline_run_id === (latest.id ?? null)) preview.value = p
    } catch { /* ignore */ }
  }
})
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">无法在所选柱间空档内安置且不跨越挡柱的摊位</p>

  <!-- 试摆结论：独立分区，视觉上与已入库运行一眼可分，绝不写成已入库 -->
  <div v-if="preview" class="card ss-preview-card">
    <h2><span class="badge badge-trial">试摆结论 · 未入库</span> 空档#{{ preview.span_index }}</h2>
    <p class="ss-mini muted">
      以下为「试摆」在空档#{{ preview.span_index }}（{{ preview.span.start_m }}–{{ preview.span.end_m }} m）内算出的放不下名单，
      <strong>尚未写入开间运行表</strong>；确认落库后才会并入已入库运行，且放置/放不下集合与试摆完全一致。
    </p>
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="r in preview.rejected" :key="'p' + r.vendor_id" class="ss-row-trial">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
        <tr v-if="!preview.rejected.length"><td colspan="3" class="muted">该空档内全部放下</td></tr>
      </tbody>
    </table>
  </div>

  <!-- 已入库运行的放不下：对得上分配图与运行抽屉里同一条 run -->
  <div class="card">
    <h2>
      已入库运行
      <template v-if="run?.id">
        #{{ run.id }}<span class="muted ss-mini">（{{ run.scope === 'span' ? '空档#' + run.span_index + ' 内结果' : '整段结果' }}）</span>
      </template>
      <span v-else class="badge badge-warn">尚无已入库运行</span>
    </h2>
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="r in run?.rejected || []" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
        <tr v-if="run?.id && !run.rejected?.length"><td colspan="3" class="muted">该运行全部放下</td></tr>
        <tr v-if="!run?.id"><td colspan="3" class="muted">请先在分配图选空档并「确认落库」。</td></tr>
      </tbody>
    </table>
  </div>
</template>
