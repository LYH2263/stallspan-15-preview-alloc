<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, patchVendorWidth } from '../api'
const rows = ref<any[]>([])
const editingId = ref<number | null>(null)
const draftWidth = ref<number>(0)
const savingId = ref<number | null>(null)
const rowError = ref<Record<number, string>>({})

onMounted(async () => { rows.value = await api('/vendors') })

function startEdit(r: any) {
  editingId.value = r.id
  draftWidth.value = r.stall_width_m
  rowError.value = {}
}
function cancelEdit() { editingId.value = null }

async function save(r: any) {
  savingId.value = r.id
  rowError.value = {}
  const w = Number(draftWidth.value)
  if (!Number.isFinite(w) || w <= 0) {
    rowError.value = { [r.id]: '宽度必须为大于 0 的数字' }
    savingId.value = null
    return
  }
  try {
    const updated = await patchVendorWidth(r.id, w)
    const i = rows.value.findIndex(x => x.id === r.id)
    if (i >= 0) rows.value[i] = updated
    editingId.value = null
  } catch (e: any) {
    rowError.value = { [r.id]: e?.message || '保存失败' }
  } finally {
    savingId.value = null
  }
}
</script>
<template>
  <div class="ss-street-wrap">
    <h1>摊主</h1>
    <p class="sub">改摊宽后回到分配图重新试摆，结果按刚保存的宽度计算</p>
    <div class="ss-vendor-queue">
      <div v-for="v in rows" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>摊主</th><th>宽度(m)</th><th>优先级</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.name }}</td>
            <td>
              <template v-if="editingId === r.id">
                <input v-model.number="draftWidth" type="number" min="0.01" step="0.1" class="ss-num-input" />
              </template>
              <template v-else>{{ r.stall_width_m }}</template>
            </td>
            <td>{{ r.priority }}</td>
            <td>
              <template v-if="editingId === r.id">
                <button class="ss-mini-btn btn-ok-mini" :disabled="savingId === r.id" @click="save(r)">
                  {{ savingId === r.id ? '保存中' : '保存' }}
                </button>
                <button class="ss-mini-btn" :disabled="savingId === r.id" @click="cancelEdit">取消</button>
              </template>
              <button v-else class="ss-mini-btn" @click="startEdit(r)">编辑</button>
              <span v-if="rowError[r.id]" class="badge badge-bad ss-row-err">{{ rowError[r.id] }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
