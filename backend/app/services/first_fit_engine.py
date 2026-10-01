"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars."""
from __future__ import annotations
from dataclasses import asdict, dataclass

SEGMENT_REJECT_REASON = "无连续空档可放下且不跨越挡柱"
GAP_REJECT_REASON = "在所选柱间空档内放不下（不跨越挡柱）"

@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float

@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str

@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]

def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    blocked = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append((lo, hi))
    blocked.sort()
    merged = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    spans = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < width_m:
        spans.append((cursor, width_m))
    return [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]

def _pack_into_spans(spans: list[list[float]], vendors: list[dict], reason: str) -> tuple[list[Placement], list[Rejected]]:
    """Greedy first-fit over the given mutable spans (absolute coordinates).

    Vendors are tried by priority ascending then id; each takes the leftmost
    span with enough room and packs against that span's current left edge.
    """
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        placed = False
        for span in spans:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, reason))
    return placements, rejected

def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span (no pillar cross)."""
    spans = free_spans_from_pillars(width_m, pillars)
    # mutable remaining capacity per span
    remain = [[a, b] for a, b in spans]
    placements, rejected = _pack_into_spans(remain, vendors, SEGMENT_REJECT_REASON)
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)

def allocate_first_fit_in_gap(width_m: float, vendors: list[dict], pillars: list[dict], gap_index: int) -> AllocResult:
    """First-fit restricted to ONE pillar gap; coordinates stay absolute and fill from the gap's left edge.

    Only the chosen span is eligible for placement, so the placement/rejection
    sets describe "within this gap" rather than the whole segment. Other gaps
    are returned untouched in free_spans; the chosen gap becomes its right-hand
    leftover (omitted when filled exactly).
    """
    spans = free_spans_from_pillars(width_m, pillars)
    remain = [[a, b] for a, b in spans]
    if gap_index < 0 or gap_index >= len(remain):
        raise ValueError("空档编号非法")
    placements, rejected = _pack_into_spans([remain[gap_index]], vendors, GAP_REJECT_REASON)
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)

def gap_descriptors(width_m: float, pillars: list[dict]) -> list[dict]:
    """Clickable gap metadata derived from the SAME geometry as free_spans_from_pillars.

    Each item: {index, start_m, end_m, width_m, left_label, right_label}.
    Boundary labels come from the adjacent pillar (matched by its blocked
    interval edge); segment edges fall back to 街段起点 / 街段终处.
    """
    spans = free_spans_from_pillars(width_m, pillars)
    edges: dict[float, str] = {}
    for p in sorted(pillars, key=lambda x: x["position_m"]):
        half = p["thickness_m"] / 2.0
        label = p.get("label") or "挡柱"
        edges[round(max(0.0, p["position_m"] - half), 3)] = label
        edges[round(min(width_m, p["position_m"] + half), 3)] = label

    def label_at(pos: float) -> str:
        if pos in edges:
            return edges[pos]
        if pos <= 0.0:
            return "街段起点"
        if pos >= width_m:
            return "街段终处"
        return "挡柱"

    return [
        {
            "index": i,
            "start_m": a,
            "end_m": b,
            "width_m": round(b - a, 3),
            "left_label": label_at(a),
            "right_label": label_at(b),
        }
        for i, (a, b) in enumerate(spans)
    ]

def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }
