"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars."""
from __future__ import annotations

from dataclasses import asdict, dataclass

EPS = 1e-9


class InvalidSpanError(ValueError):
    """Raised when a pillar-to-pillar free span index does not exist."""


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


@dataclass
class SpanResult:
    """Result of filling exactly one pillar-to-pillar free span, left to right."""
    span_index: int
    span_start_m: float
    span_end_m: float
    placements: list[Placement]
    rejected: list[Rejected]
    free_span: tuple[float, float] | None


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


def _ordered_vendors(vendors: list[dict]) -> list[dict]:
    return sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))


def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span (no pillar cross)."""
    spans = free_spans_from_pillars(width_m, pillars)
    # mutable remaining capacity per span
    remain = [[a, b] for a, b in spans]
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in _ordered_vendors(vendors):
        need = float(v["stall_width_m"])
        placed = False
        for span in remain:
            avail = span[1] - span[0]
            if avail + EPS >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)


def allocate_in_span(width_m: float, vendors: list[dict], pillars: list[dict],
                     span_index: int) -> SpanResult:
    """Fill ONLY the pillar-to-pillar free span ``span_index``.

    Vendors are taken in priority order (then id) and packed from the left
    edge of the chosen span; a vendor that does not fit in the span's
    remaining room is rejected for this span (later, smaller vendors still
    get a chance at the leftover). Preview and confirm share this exact
    function, so the placement/rejection sets inside the span cannot
    diverge between a trial placement and its confirmation.
    """
    spans = free_spans_from_pillars(width_m, pillars)
    if not isinstance(span_index, int) or span_index < 0 or span_index >= len(spans):
        raise InvalidSpanError(
            f"空档编号无效：{span_index!r}，当前街段只有 {len(spans)} 个柱间空档（0–{len(spans) - 1}）"
        )
    lo, hi = spans[span_index]
    cursor = lo
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in _ordered_vendors(vendors):
        need = float(v["stall_width_m"])
        if cursor + need <= hi + EPS:
            end = cursor + need
            placements.append(Placement(v["id"], v["name"], round(cursor, 3), round(end, 3), need))
            cursor = end
        else:
            remain = max(0.0, round(hi - cursor, 3))
            rejected.append(Rejected(
                v["id"], v["name"], need,
                f"柱间空档#{span_index}（{lo:g}–{hi:g} m）剩余 {remain:g} m，放不下 {need:g} m 且不可跨越挡柱",
            ))
    free_span = (round(cursor, 3), hi) if hi - cursor > 1e-6 else None
    return SpanResult(span_index, lo, hi, placements, rejected, free_span)


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }


def span_result_to_dict(r: SpanResult) -> dict:
    return {
        "scope": "span",
        "span_index": r.span_index,
        "span": {"index": r.span_index, "start_m": r.span_start_m, "end_m": r.span_end_m},
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": ([{"start_m": r.free_span[0], "end_m": r.free_span[1]}]
                       if r.free_span else []),
    }
