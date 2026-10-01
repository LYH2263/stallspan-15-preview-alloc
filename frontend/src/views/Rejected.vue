<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchLatest } from '../api'
const rows = ref<any[]>([])
const runId = ref<number | null>(null)
const scopeLabel = ref('')
const noRun = ref(false)

onMounted(async () => {
  const data = await fetchLatest(1)
  if (!data) {
    noRun.value = true
    return
  }
  runId.value = data.id
  rows.value = data.rejected || []
  scopeLabel.value = data.gap
    ? `${data.gap.left_label} – ${data.gap.right_label} · ${data.gap.width_m}m 空档`
    : '整段'
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>放不下</h1>
    <p class="sub">已入库运行的放不下清单 · 试摆结论未入库，不会出现在此页</p>
    <div class="card">
      <template v-if="!noRun">
        <p>
          <span class="badge badge-ok">已入库 #{{ runId }}</span>
          <span class="muted"> 范围：{{ scopeLabel }}</span>
        </p>
        <table>
          <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.vendor_id">
              <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!rows.length" class="muted">全部放下</p>
      </template>
      <p v-else class="muted">尚无已入库运行 · 请先在分配图点选空档试摆并确认</p>
    </div>
  </div>
</template>
