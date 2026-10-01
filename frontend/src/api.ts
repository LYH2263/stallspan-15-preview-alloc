export interface GapDesc {
  index: number
  start_m: number
  end_m: number
  width_m: number
  left_label: string
  right_label: string
}

export interface Placement {
  vendor_id: number
  vendor_name: string
  start_m: number
  end_m: number
  width_m: number
}

export interface Rejected {
  vendor_id: number
  vendor_name: string
  width_m: number
  reason: string
}

export interface AllocEnvelope {
  id: number | null
  trial: boolean
  created_at: string | null
  segment: { id: number; name: string; width_m: number }
  gap: GapDesc | null
  placements: Placement[]
  rejected: Rejected[]
  free_spans: { start_m: number; end_m: number }[]
}

export interface RunSummary {
  id: number
  created_at: string
  segment_id: number
  scope_type: 'gap' | 'segment'
  gap_index: number | null
  scope_label: string
  placed_count: number
  rejected_count: number
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body)
    } catch {
      message = (await res.text().catch(() => '')) || res.statusText
    }
    const err = new Error(message) as Error & { status?: number }
    err.status = res.status
    throw err
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const fetchGaps = (segmentId = 1) =>
  api<GapDesc[]>(`/segments/${segmentId}/gaps`)

export const fetchRuns = (segmentId = 1) =>
  api<RunSummary[]>(`/allocate/runs?segment_id=${segmentId}`)

export const fetchRunById = (runId: number) =>
  api<AllocEnvelope>(`/allocate/runs/${runId}`)

export const fetchLatest = async (segmentId = 1): Promise<AllocEnvelope | null> => {
  try {
    return await api<AllocEnvelope>(`/allocate/latest?segment_id=${segmentId}`)
  } catch (e: any) {
    if (e?.status === 404) return null
    throw e
  }
}

export const trialGap = (gapIndex: number, segmentId = 1) =>
  api<AllocEnvelope>('/allocate/trial', {
    method: 'POST',
    body: JSON.stringify({ segment_id: segmentId, gap_index: gapIndex }),
  })

export const confirmGap = (gapIndex: number, segmentId = 1) =>
  api<AllocEnvelope>('/allocate/confirm', {
    method: 'POST',
    body: JSON.stringify({ segment_id: segmentId, gap_index: gapIndex }),
  })

export const rerunSegment = (segmentId = 1) =>
  api<AllocEnvelope>(`/allocate/run?segment_id=${segmentId}`, { method: 'POST' })

export const patchVendorWidth = (vendorId: number, stallWidth: number) =>
  api<any>(`/vendors/${vendorId}`, {
    method: 'PATCH',
    body: JSON.stringify({ stall_width_m: stallWidth }),
  })
