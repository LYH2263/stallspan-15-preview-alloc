<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import TrialSidebar from '../components/TrialSidebar.vue'
import RunDrawer from '../components/RunDrawer.vue'
import {
  api, confirmGap, fetchGaps, fetchLatest, rerunSegment, trialGap,
  type AllocEnvelope, type GapDesc,
} from '../api'

const SEGMENT_ID = 1
const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
const colorOf = (vendorId: number) => colors[(vendorId - 1) % colors.length]

const gaps = ref<GapDesc[]>([])
const pillars = ref<any[]>([])
const vendors = ref<any[]>([])
const committedData = ref<AllocEnvelope | null>(null)
const trialData = ref<AllocEnvelope | null>(null)
const selectedGapIndex = ref<number | null>(null)
const busyTrial = ref(false)
const busyConfirm = ref(false)
const busyRerun = ref(false)
const errorMsg = ref('')
const okMsg = ref('')

const widthM = computed(() => committedData.value?.segment?.width_m ?? 30)
const pct = (m: number) => ((m / widthM.value) * 100).toFixed(4) + '%'
const selectedGap = computed(() =>
  selectedGapIndex.value === null ? null : gaps.value.find(g => g.index === selectedGapIndex.value) || null)

onMounted(load)

async function load() {
  const [gs, ps, vs] = await Promise.all([
    fetchGaps(SEGMENT_ID),
    api<any[]>('/pillars'),
    api<any[]>('/vendors'),
  ])
  gaps.value = gs
  pillars.value = ps.filter((p: any) => p.segment_id === SEGMENT_ID)
  vendors.value = vs
  committedData.value = await fetchLatest(SEGMENT_ID)
}

// Shared by BOTH 试摆 and 确认 — same client-side gate, same wording as the
// backend 400 ("未选空档", never "空档不够").
function validateGap(): boolean {
  if (selectedGapIndex.value === null) {
    errorMsg.value = '请先点选一个柱间空档'
    okMsg.value = ''
    return false
  }
  return true
}

function clickGap(g: GapDesc) {
  if (selectedGapIndex.value === g.index) {
    selectedGapIndex.value = null   // toggle off
  } else {
    selectedGapIndex.value = g.index
    trialData.value = null          // a trial belongs to exactly one gap
  }
  errorMsg.value = ''
  okMsg.value = ''
}

async function doTrial() {
  if (!validateGap() || busyTrial.value) return
  busyTrial.value = true
  errorMsg.value = ''
  try {
    // Atomic replace: a failed request never touches prior/committed results.
    trialData.value = await trialGap(selectedGapIndex.value as number, SEGMENT_ID)
  } catch (e: any) {
    errorMsg.value = e?.message || '试摆失败'
  } finally {
    busyTrial.value = false
  }
}

async function doConfirm() {
  if (!validateGap() || busyConfirm.value) return
  busyConfirm.value = true
  errorMsg.value = ''
  try {
    const resp = await confirmGap(selectedGapIndex.value as number, SEGMENT_ID)
    committedData.value = resp
    trialData.value = null
    selectedGapIndex.value = null
    okMsg.value = `已确认入库 #${resp.id}：主图、运行抽屉与放不下页均为该空档内结果`
  } catch (e: any) {
    errorMsg.value = e?.message || '确认失败'
  } finally {
    busyConfirm.value = false
  }
}

async function doRerun() {
  if (busyRerun.value) return
  busyRerun.value = true
  errorMsg.value = ''
  try {
    committedData.value = await rerunSegment(SEGMENT_ID)
    trialData.value = null
    selectedGapIndex.value = null
    okMsg.value = `整段重排已入库 #${committedData.value.id}`
  } catch (e: any) {
    errorMsg.value = e?.message || '重排失败'
  } finally {
    busyRerun.value = false
  }
}
</script>
<template>
  <div class="ss-street-wrap">
    <div class="ss-map-head">
      <div>
        <h1>街段分配图</h1>
        <p class="sub">① 点选一个柱间空档 → ② 试摆（不入库）→ ③ 确认入库（从左填空落库一行）</p>
      </div>
      <RunDrawer :latest-data="committedData" />
    </div>

    <div class="ss-actions">
      <button class="btn" :disabled="busyTrial" @click="doTrial">
        {{ busyTrial ? '试摆中…' : '试摆' }}
      </button>
      <button class="btn btn-ghost" :disabled="busyRerun" @click="doRerun">
        {{ busyRerun ? '重排中…' : '整段重排' }}
      </button>
      <span v-if="errorMsg" class="badge badge-bad">{{ errorMsg }}</span>
      <span v-if="okMsg" class="badge badge-ok">{{ okMsg }}</span>
    </div>

    <div class="ss-band-ruler">
      <span>0 m</span>
      <span>东街段 · {{ widthM }} m</span>
      <span>{{ widthM }} m</span>
    </div>
    <div class="ss-street-band">
      <div class="ss-street-inner ss-layered">
        <!-- layer 1: clickable gaps -->
        <div
          v-for="g in gaps" :key="'gap' + g.index"
          class="ss-gap-hit"
          :class="{ selected: selectedGapIndex === g.index }"
          :style="{ left: pct(g.start_m), width: pct(g.end_m - g.start_m) }"
          :title="`${g.left_label} – ${g.right_label} · ${g.width_m}m 空档（点击点选）`"
          @click="clickGap(g)"
        >
          <span class="ss-gap-label">{{ g.left_label }}–{{ g.right_label }} · {{ g.width_m }}m</span>
        </div>

        <!-- layer 2: committed runs (solid) -->
        <div
          v-for="p in committedData?.placements || []" :key="'c' + p.vendor_id"
          class="ss-stall ss-stall-committed"
          :style="{ left: pct(p.start_m), width: pct(p.end_m - p.start_m), background: colorOf(p.vendor_id) }"
        >{{ p.vendor_name }}</div>

        <!-- layer 3: trial placements (hatched, visually distinct) -->
        <div
          v-for="p in trialData?.placements || []" :key="'t' + p.vendor_id"
          class="ss-stall ss-stall-trial"
          :style="{ left: pct(p.start_m), width: pct(p.end_m - p.start_m), borderColor: colorOf(p.vendor_id) }"
        >{{ p.vendor_name }}</div>

        <!-- layer 4: pillars + selected ring (non-interactive) -->
        <div
          v-for="(p, i) in pillars" :key="'p' + i"
          class="ss-pillar-layer"
          :style="{ left: pct(p.position_m - p.thickness_m / 2), width: pct(p.thickness_m) }"
        >{{ p.label || '挡柱' }}</div>
        <div v-if="selectedGap" class="ss-gap-ring"
             :style="{ left: pct(selectedGap.start_m), width: pct(selectedGap.end_m - selectedGap.start_m) }"></div>
      </div>
    </div>

    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
    </div>

    <div class="ss-trial-layout">
      <div class="ss-trial-side">
        <TrialSidebar v-if="trialData" :data="trialData" :busy="busyConfirm"
                      @confirm="doConfirm" @cancel="trialData = null" />
        <div v-else class="card muted ss-no-trial">
          未试摆：点选上方空档后按「试摆」，结论只在此侧栏显示，绝不写入运行表。
        </div>
      </div>

      <div class="ss-committed-side">
        <div class="card">
          <h2 class="ss-section-title">
            已入库运行（最新 #{{ committedData?.id ?? '—' }}）
            <span v-if="committedData" class="badge badge-ok">
              {{ committedData.gap ? `空档 ${committedData.gap.left_label}–${committedData.gap.right_label}` : '整段' }}
            </span>
          </h2>
          <table v-if="committedData">
            <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
            <tbody>
              <tr v-for="p in committedData.placements" :key="p.vendor_id">
                <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted">尚无已入库运行 · 请点选空档后试摆并确认</p>
        </div>
      </div>
    </div>
  </div>
</template>
