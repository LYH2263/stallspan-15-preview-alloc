import pytest

from app.services.first_fit_engine import (
    InvalidSpanError,
    allocate_first_fit,
    allocate_in_span,
    free_spans_from_pillars,
)

PILLARS_AB = [{"position_m": 10.0, "thickness_m": 0.5, "label": "灯柱A"},
              {"position_m": 20.0, "thickness_m": 0.5, "label": "灯柱B"}]


def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, PILLARS_AB)
    assert spans == [(0.0, 9.75), (10.25, 19.75), (20.25, 30.0)]
    assert spans[0][0] == 0.0


def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert any(p.vendor_name == "A" for p in r.placements)
    # 12m may fit in a free span after first placement depending on remainders
    assert len(r.placements) + len(r.rejected) == 2


def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    r = allocate_first_fit(30.0, vendors, PILLARS_AB)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"


def test_allocate_in_span_only_fills_chosen_span():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 2.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 2.0, "priority": 1},
    ]
    r = allocate_in_span(30.0, vendors, PILLARS_AB, 1)  # 灯柱A–B 之间
    assert r.span_start_m == 10.25 and r.span_end_m == 19.75
    assert {p.vendor_name for p in r.placements} == {"A", "B"}
    assert all(10.25 <= p.start_m and p.end_m <= 19.75 for p in r.placements)
    assert r.placements[0].start_m == 10.25  # 从空档左缘开始填


def test_allocate_in_span_priority_then_id_order():
    vendors = [
        {"id": 9, "name": "LowPri", "stall_width_m": 4.0, "priority": 9},
        {"id": 2, "name": "HiPriB", "stall_width_m": 4.0, "priority": 1},
        {"id": 1, "name": "HiPriA", "stall_width_m": 4.0, "priority": 1},
    ]
    r = allocate_in_span(30.0, vendors, PILLARS_AB, 1)
    names = [p.vendor_name for p in r.placements]
    assert names == ["HiPriA", "HiPriB"]  # 优先序，再按 id
    assert [r.rejected[0].vendor_name] == ["LowPri"]


def test_allocate_in_span_smaller_vendor_uses_leftover():
    # 6m 放不下剩余 3.5m，但后续 3m 的仍应能填进去
    vendors = [
        {"id": 1, "name": "Six", "stall_width_m": 6.0, "priority": 1},
        {"id": 2, "name": "Three", "stall_width_m": 3.0, "priority": 2},
    ]
    r = allocate_in_span(30.0, vendors, PILLARS_AB, 0)  # 0–9.75
    assert {p.vendor_name for p in r.placements} == {"Six", "Three"}
    assert r.free_span is None or r.free_span[1] - r.free_span[0] <= 0.75 + 1e-6


def test_allocate_in_span_invalid_index():
    vendors = [{"id": 1, "name": "A", "stall_width_m": 2.0, "priority": 1}]
    with pytest.raises(InvalidSpanError):
        allocate_in_span(30.0, vendors, PILLARS_AB, 7)
    with pytest.raises(InvalidSpanError):
        allocate_in_span(30.0, vendors, PILLARS_AB, -1)


def test_seed_giant_stage_truck_rejected_between_A_and_B():
    """种子场景：巨型舞台车 12m 宽于灯柱A–B 空档（9.5m），须进试摆放不下侧。"""
    vendors = [
        {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
        {"id": 3, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
        {"id": 4, "name": "小美饰品", "stall_width_m": 2.5, "priority": 2},
        {"id": 5, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
        {"id": 6, "name": "手作皮具", "stall_width_m": 3.5, "priority": 3},
        {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
    ]
    r = allocate_in_span(30.0, vendors, PILLARS_AB, 1)
    placed_names = {p.vendor_name for p in r.placements}
    rejected_names = {x.vendor_name for x in r.rejected}
    assert "巨型舞台车" in rejected_names
    assert "巨型舞台车" not in placed_names
    assert all(10.25 <= p.start_m and p.end_m <= 19.75 for p in r.placements)
