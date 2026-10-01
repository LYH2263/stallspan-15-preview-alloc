<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchRunById, fetchRuns, type AllocEnvelope, type RunSummary } from '../api'

const props = defineProps<{ latestData: AllocEnvelope | null }>()
const emit = defineEmits<{ (e: 'refresh'): void }>()

const open = ref(false)
const rows = ref<RunSummary[]>([])
const detail = ref<AllocEnvelope | null>(null)
const detailError = ref('')
const selectedId = ref<number | null>(null)
const loadingDetail = ref(false)

async function loadRuns() {
  rows.value = await fetchRuns(1)
}

watch(open, async (v) => {
  if (!v) return
  await loadRuns()
  selectedId.value = props.latestData?.id ?? null
  detail.value = props.latestData
  detailError.value = ''
})

// A fresh confirm replaces the latest run: keep the open drawer aligned.
watch(() => props.latestData, async (d) => {
  if (!open.value || !d) return
  await loadRuns()
  selectedId.value = d.id
  detail.value = d
})

async function selectRun(r: RunSummary) {
  selectedId.value = r.id
  detailError.value = ''
  if (props.latestData && r.id === props.latestData.id) {
    // Single source of truth: the latest run detail IS what the map shows.
    detail.value = props.latestData
    return
  }
  loadingDetail.value = true
  try {
    detail.value = await fetchRunById(r.id)
  } catch (e: any) {
    detail.value = null
    detailError.value = e?.message || '加载失败'
  } finally {
    loadingDetail.value = false
  }
}

function scopeLabel(d: AllocEnvelope | null): string {
  if (!d) return ''
  if (!d.gap) return '整段'
  return `${d.gap.left_label} – ${d.gap.right_label} · ${d.gap.width_m} m 空档`
}
</script>
<template>
  <button class="btn btn-ghost ss-drawer-toggle" @click="open = !open">运行抽屉</button>

  <div v-if="open" class="ss-drawer-backdrop" @click="open = false"></div>
  <aside v-if="open" class="ss-drawer open">
    <div class="ss-drawer-head">
      <strong>开间运行记录</strong>
      <div>
        <button class="ss-mini-btn" @click="emit('refresh'); loadRuns()">刷新</button>
        <button class="ss-mini-btn" @click="open = false">关闭</button>
      </div>
    </div>

    <ul class="ss-run-list">
      <li v-for="r in rows" :key="r.id"
          class="ss-run-item"
          :class="{ active: r.id === selectedId }"
          @click="selectRun(r)">
        <div><strong>#{{ r.id }}</strong>
          <span class="badge" :class="r.scope_type === 'gap' ? 'badge-warn' : 'badge-ok'">
            {{ r.scope_label }}
          </span>
        </div>
        <div class="muted ss-run-meta">{{ r.created_at }} · 放得下 {{ r.placed_count }} · 放不下 {{ r.rejected_count }}</div>
      </li>
      <li v-if="!rows.length" class="muted">尚无已入库运行</li>
    </ul>

    <div class="ss-run-detail" v-if="detail">
      <div class="ss-drawer-head">
        <span class="badge badge-ok">已入库</span>
        <span class="muted">#{{ detail.id }} · {{ scopeLabel(detail) }}</span>
      </div>
      <table>
        <thead><tr><th>摊主</th><th>起</th><th>止</th></tr></thead>
        <tbody>
          <tr v-for="p in detail.placements" :key="p.vendor_id">
            <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!detail.placements.length" class="muted">无放置</p>
      <table class="ss-run-rejects">
        <thead><tr><th>放不下</th><th>宽度</th></tr></thead>
        <tbody>
          <tr v-for="x in detail.rejected" :key="x.vendor_id">
            <td>{{ x.vendor_name }}</td><td>{{ x.width_m }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!detail.rejected.length" class="muted">全部放下</p>
    </div>
    <p v-else-if="loadingDetail" class="muted">加载中…</p>
    <p v-else-if="detailError" class="badge badge-bad">{{ detailError }}</p>
  </aside>
</template>
