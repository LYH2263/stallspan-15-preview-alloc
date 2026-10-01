<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const SEGMENT_ID = 1
const PREVIEW_KEY = 'ss_preview_v1'

const committed = ref<any>(null)   // 已入库运行（latest 或抽屉选中的 run）
const vendors = ref<any[]>([])
const spans = ref<any[]>([])
const pillars = ref<any[]>([])
const selectedSpan = ref<number | null>(null)
const preview = ref<any | null>(null)  // 试摆结论：绝不写运行表
const runs = ref<any[]>([])
const drawerOpen = ref(false)
const loadedRunId = ref<number | null>(null)  // 抽屉载入的 run；null 表示 latest
const busy = ref(false)
const error = ref('')
const notice = ref('')

const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
const trialColor = '#ffd166'

async function loadSpans() {
  const data = await api(`/allocate/spans?segment_id=${SEGMENT_ID}`)
  pillars.value = data.pillars || []
  spans.value = data.spans || []
}
async function loadLatest() {
  const data = await api(`/allocate/latest?segment_id=${SEGMENT_ID}`)
  committed.value = data
  loadedRunId.value = data.id ?? null
  if (data.spans?.length) spans.value = data.spans
  if (data.pillars?.length) pillars.value = data.pillars
}
async function loadRuns() { runs.value = await api(`/allocate/runs?segment_id=${SEGMENT_ID}`) }

onMounted(async () => {
  vendors.value = await api('/vendors')
  await loadLatest()
  await loadSpans()
  await loadRuns()
  restorePreview()
})

// ---- 试摆态持久化（仅 sessionStorage，不是运行表），供「放不下」页展示 ----
function savePreview(p: any) {
  sessionStorage.setItem(PREVIEW_KEY, JSON.stringify({ ...p, baseline_run_id: committed.value?.id ?? null }))
}
function clearPreview() {
  preview.value = null
  sessionStorage.removeItem(PREVIEW_KEY)
}
function restorePreview() {
  const raw = sessionStorage.getItem(PREVIEW_KEY)
  if (!raw) return
  try {
    const p = JSON.parse(raw)
    // 已出现更新的已入库运行（说明已确认过），试摆结论过期，不得再当结论展示
    if (p.baseline_run_id !== (committed.value?.id ?? null)) { sessionStorage.removeItem(PREVIEW_KEY); return }
    if (spans.value.some(s => s.index === p.span_index)) { preview.value = p; selectedSpan.value = p.span_index }
  } catch { sessionStorage.removeItem(PREVIEW_KEY) }
}

function pickSpan(i: number) {
  selectedSpan.value = i
  error.value = ''
  // 切换空档后旧试摆结论作废，避免“空档A的结论”被看成“空档B的”
  if (preview.value && preview.value.span_index !== i) clearPreview()
}

async function doPreview() {
  error.value = ''; notice.value = ''
  if (selectedSpan.value === null) {
    // 未选空档就试摆：明确拒绝，不得写成“空档不够”
    error.value = '未选空档：请先在分配图上点选东街段的一个柱间空档，再试摆。'
    return
  }
  if (busy.value) return  // 连点第二次：直接忽略，禁止半成功
  busy.value = true
  try {
    // 每次都重新拉摊主宽度：改摊宽后不得沿用旧宽结果
    vendors.value = await api('/vendors')
    const r = await api('/allocate/preview', {
      method: 'POST',
      body: JSON.stringify({ segment_id: SEGMENT_ID, span_index: selectedSpan.value }),
    })
    preview.value = r
    savePreview(r)
    notice.value = `试摆完成（空档#${r.span_index}）：结果尚未入库，运行表 0 新增；确认后才落库。`
  } catch (e: any) {
    // 非法空档编号等失败：保留已入库运行与已有试摆视图，不把失败记成成功
    error.value = extractError(e)
  } finally { busy.value = false }
}

async function doConfirm() {
  error.value = ''; notice.value = ''
  if (selectedSpan.value === null) {
    // 未选空档：与试摆同一条拒绝路径（绿仓一致）
    error.value = '未选空档：请先在分配图上点选东街段的一个柱间空档，再确认落库。'
    return
  }
  if (busy.value) return
  busy.value = true
  try {
    const r = await api('/allocate/confirm', {
      method: 'POST',
      body: JSON.stringify({ segment_id: SEGMENT_ID, span_index: selectedSpan.value }),
    })
    // 试摆与确认对「该空档内」结果必须一致；后端同一引擎，前端再核一遍
    if (preview.value && preview.value.span_index === r.span_index) {
      const a = new Set(preview.value.placements.map((p: any) => `${p.vendor_id}@${p.start_m}-${p.end_m}`))
      const b = new Set(r.placements.map((p: any) => `${p.vendor_id}@${p.start_m}-${p.end_m}`))
      const same = a.size === b.size && [...a].every(x => b.has(x))
      if (!same) { error.value = '试摆与确认结果不一致，已阻止刷新，请重试。'; return }
    }
    clearPreview()
    await loadLatest()
    await loadRuns()
    notice.value = `已落库为运行 #${r.id}：空档#${r.span_index} 内放置 ${r.placements.length} 个、放不下 ${r.rejected.length} 个。主图、抽屉、放不下页均对应该运行。`
  } catch (e: any) {
    error.value = extractError(e)
  } finally { busy.value = false }
}

async function loadRun(id: number) {
  // 看已入库运行就退出试摆草稿，保证主图与抽屉里是同一条 run 的同一套结果
  clearPreview()
  selectedSpan.value = null
  const r = await api(`/allocate/run/${id}`)
  committed.value = r
  loadedRunId.value = r.id
  if (r.spans?.length) spans.value = r.spans
  if (r.pillars?.length) pillars.value = r.pillars
  drawerOpen.value = false
  notice.value = `正在查看已入库运行 #${r.id}${r.scope === 'span' ? `（空档#${r.span_index}）` : '（整段）'}。`
}
async function backToLatest() {
  clearPreview()
  selectedSpan.value = null
  await loadLatest()
  notice.value = '已回到最新已入库运行。'
}

async function saveVendorWidth(v: any) {
  const raw = v._editWidth ?? String(v.stall_width_m)
  const w = parseFloat(raw)
  if (!Number.isFinite(w) || w <= 0) { error.value = '摊宽须为正数'; return }
  if (w === v.stall_width_m) { v._editWidth = undefined; return }
  busy.value = true
  try {
    await api(`/vendors/${v.id}`, { method: 'PATCH', body: JSON.stringify({ stall_width_m: w }) })
    vendors.value = await api('/vendors')
    notice.value = `已把「${v.name}」摊宽改为 ${w} m。`
    // 改摊宽后若正看着某空档试摆，立即按新宽重算，不得沿用旧宽
    busy.value = false
    if (selectedSpan.value !== null) await doPreview()
  } catch (e: any) {
    error.value = extractError(e)
  } finally { busy.value = false }
}

function extractError(e: any): string {
  try { const j = JSON.parse(e.message); if (j.detail) return j.detail } catch { /* plain text */ }
  return e?.message || '请求失败'
}

const segWidth = computed(() => committed.value?.segment?.width_m || 30)

// 主图单元：试摆时，选中空档内用试摆放置替换已入库放置；其余空档保留已入库（淡化）
const cells = computed(() => {
  const width = segWidth.value
  const out: any[] = []
  for (const p of pillars.value) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m / 2, w: p.thickness_m, label: p.label || '挡柱' })
  }
  const cp = committed.value?.placements || []
  const trial = preview.value
  let stalls: any[] = []
  if (trial) {
    const lo = trial.span.start_m, hi = trial.span.end_m
    for (const p of cp) {
      const inside = p.start_m + 1e-6 >= lo && p.end_m <= hi + 1e-6
      if (!inside) stalls.push({ ...p, dimmed: true })
    }
    for (const [i, p] of trial.placements.entries()) {
      stalls.push({ ...p, trial: true, color: trialColor, colorIx: i })
    }
  } else {
    stalls = cp.map((p: any, i: number) => ({ ...p, colorIx: i }))
  }
  for (const c of stalls) {
    out.push({ type: 'stall', start: c.start_m, w: c.width_m, label: c.vendor_name,
               color: c.trial ? trialColor : colors[(c.colorIx ?? 0) % colors.length],
               trial: !!c.trial, dimmed: !!c.dimmed })
  }
  return out.sort((a, b) => a.start - b.start)
    .map(c => ({ ...c, pct: Math.max((c.w / width) * 100, c.type === 'pillar' ? 1 : 0.6) }))
})

const spanHotspots = computed(() => spans.value.map(s => ({
  ...s,
  leftPct: (s.start_m / segWidth.value) * 100,
  widthPct: ((s.end_m - s.start_m) / segWidth.value) * 100,
})))

const shownPlacements = computed(() => preview.value ? preview.value.placements : (committed.value?.placements || []))
const shownRejected = computed(() => preview.value ? preview.value.rejected : (committed.value?.rejected || []))
const selectedSpanInfo = computed(() => spans.value.find(s => s.index === selectedSpan.value) || null)
</script>

<template>
  <div class="ss-street-wrap">
    <div class="ss-map-head">
      <div>
        <h1>街段分配带</h1>
        <p class="sub">点选柱间空档 → 试摆（不写运行表）→ 确认落库；挡柱不可跨越</p>
      </div>
      <div class="ss-head-actions">
        <button class="btn btn-ghost" @click="drawerOpen = !drawerOpen">运行抽屉（{{ runs.length }}）</button>
      </div>
    </div>

    <div class="ss-modebar">
      <span v-if="preview" class="badge badge-trial">试摆态 · 空档#{{ preview.span_index }} · 未入库（运行表不增行）</span>
      <span v-else-if="committed?.id" class="badge badge-ok">已入库运行 #{{ committed.id }}<template v-if="committed.scope === 'span'"> · 空档#{{ committed.span_index }}</template></span>
      <span v-else class="badge badge-warn">尚无已入库运行</span>
      <button v-if="runs.length && committed?.id !== runs[0].id" class="btn btn-mini" @click="backToLatest">回到最新</button>
    </div>

    <p v-if="error" class="ss-error">⛔ {{ error }}</p>
    <p v-if="notice" class="ss-notice">ℹ️ {{ notice }}</p>

    <div class="ss-band-ruler" v-if="committed">
      <span>0 m</span>
      <span>{{ committed.segment.name }} · {{ committed.segment.width_m }} m</span>
      <span>{{ committed.segment.width_m }} m</span>
    </div>

    <div class="ss-street-band ss-band-selectable">
      <div class="ss-street-inner">
        <div
          v-for="(c, i) in cells" :key="i"
          class="ss-band-cell"
          :class="{ 'ss-pillar': c.type === 'pillar', 'ss-trial': c.trial, 'ss-dimmed': c.dimmed }"
          :style="{ width: c.pct + '%', background: c.type === 'pillar' ? undefined : c.color, flex: '0 0 ' + c.pct + '%' }"
        >
          <span v-if="c.trial" class="ss-trial-tag">试摆</span>{{ c.label }}
        </div>
      </div>
      <!-- 柱间空档点击热区 -->
      <div class="ss-span-layer">
        <button
          v-for="s in spanHotspots" :key="s.index"
          type="button"
          class="ss-span-hit"
          :class="{ active: selectedSpan === s.index }"
          :style="{ left: s.leftPct + '%', width: s.widthPct + '%' }"
          :title="`柱间空档#${s.index}：${s.start_m}–${s.end_m} m（宽 ${s.width_m} m），点选后试摆`"
          @click="pickSpan(s.index)"
        >
          <span class="ss-span-tag">空档#{{ s.index }} · {{ s.width_m }}m</span>
        </button>
      </div>
    </div>

    <div class="ss-map-grid">
      <!-- 试摆侧栏 -->
      <aside class="card ss-trial-panel">
        <h2>试摆侧栏</h2>
        <div class="ss-span-picker">
          <p class="muted ss-mini">柱间空档（点图或此处选择）：</p>
          <div class="ss-span-chips">
            <button
              v-for="s in spans" :key="s.index" type="button"
              class="ss-span-chip" :class="{ active: selectedSpan === s.index }"
              @click="pickSpan(s.index)"
            >#{{ s.index }}｜{{ s.start_m }}–{{ s.end_m }}m</button>
          </div>
          <p v-if="selectedSpanInfo" class="ss-mini muted">
            已选：空档#{{ selectedSpanInfo.index }}，宽 {{ selectedSpanInfo.width_m }} m，只在此空档内按优先序从左填空。
          </p>
        </div>

        <div class="ss-trial-actions">
          <button class="btn" :disabled="busy" @click="doPreview">{{ busy ? '计算中…' : '试摆' }}</button>
          <button class="btn btn-primary" :disabled="busy" @click="doConfirm">确认落库</button>
        </div>

        <div v-if="preview" class="ss-trial-result">
          <p class="badge badge-trial">以下为试摆结论 · 未写入运行表</p>
          <table>
            <thead><tr><th>试摆放置</th><th>起–止</th><th>宽</th></tr></thead>
            <tbody>
              <tr v-for="p in preview.placements" :key="'tp' + p.vendor_id">
                <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}–{{ p.end_m }}</td><td>{{ p.width_m }}</td>
              </tr>
              <tr v-if="!preview.placements.length"><td colspan="3" class="muted">该空档内无放置</td></tr>
            </tbody>
          </table>
          <table class="ss-rej-mini">
            <thead><tr><th>试摆放不下（未入库）</th><th>宽</th></tr></thead>
            <tbody>
              <tr v-for="r in preview.rejected" :key="'tr' + r.vendor_id">
                <td>{{ r.vendor_name }} <span class="muted ss-mini">{{ r.reason }}</span></td><td>{{ r.width_m }}</td>
              </tr>
              <tr v-if="!preview.rejected.length"><td colspan="2" class="muted">该空档内全部放下</td></tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted ss-mini">选空档后点「试摆」，这里只显示该空档内的放置与放不下；任何结论都不会写成已入库运行。</p>
      </aside>

      <!-- 主图对应的运行明细表 -->
      <section class="card ss-run-panel">
        <h2>
          {{ preview ? '试摆明细（未落库）' : `已入库运行${committed?.id ? ' #' + committed.id : ''} 的开间运行表` }}
        </h2>
        <table>
          <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="p in shownPlacements" :key="p.vendor_id" :class="{ 'ss-row-trial': preview }">
              <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
              <td><span :class="preview ? 'badge badge-trial' : 'badge badge-ok'">{{ preview ? '试摆·未入库' : '已入库' }}</span></td>
            </tr>
            <tr v-if="!shownPlacements.length"><td colspan="5" class="muted">无放置</td></tr>
          </tbody>
        </table>
        <h3>放不下（{{ shownRejected.length }}）</h3>
        <table>
          <thead><tr><th>摊主</th><th>宽度</th><th>原因</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="r in shownRejected" :key="r.vendor_id" :class="{ 'ss-row-trial': preview }">
              <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
              <td><span :class="preview ? 'badge badge-trial' : 'badge badge-bad'">{{ preview ? '试摆·未入库' : '已入库拒绝' }}</span></td>
            </tr>
            <tr v-if="!shownRejected.length"><td colspan="4" class="muted">全部放下</td></tr>
          </tbody>
        </table>
      </section>
    </div>

    <h2 class="ss-queue-title">摊主排队（可直接改摊宽，保存后按新宽试摆）</h2>
    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>优先 {{ v.priority }}</span>
        <label class="ss-width-edit">
          宽
          <input
            :value="v._editWidth ?? v.stall_width_m"
            type="number" step="0.5" min="0.5"
            @input="v._editWidth = ($event.target as HTMLInputElement).value"
          /> m
        </label>
        <button class="btn btn-mini" :disabled="busy" @click="saveVendorWidth(v)">改宽</button>
      </div>
    </div>

    <!-- 运行抽屉 -->
    <transition name="ss-drawer">
      <aside v-if="drawerOpen" class="ss-drawer">
        <div class="ss-drawer-head">
          <h2>开间运行抽屉</h2>
          <button class="btn btn-mini" @click="drawerOpen = false">收起</button>
        </div>
        <p class="muted ss-mini">仅此处列出的才是已入库运行；试摆不会在这增行。</p>
        <table>
          <thead><tr><th>#</th><th>时间</th><th>范围</th><th>放置</th><th>放不下</th></tr></thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id"
                :class="{ 'ss-row-current': r.id === committed?.id && !preview }">
              <td><a href="#" @click.prevent="loadRun(r.id)">{{ r.id }}</a></td>
              <td>{{ r.created_at }}</td>
              <td>{{ r.scope === 'span' ? `空档#${r.span_index}` : '整段' }}</td>
              <td>{{ r.placements }}</td><td>{{ r.rejected }}</td>
            </tr>
            <tr v-if="!runs.length"><td colspan="5" class="muted">暂无已入库运行——选空档并确认后才会出现一行。</td></tr>
          </tbody>
        </table>
      </aside>
    </transition>
  </div>
</template>
