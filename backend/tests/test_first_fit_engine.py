import pytest

from app.services.first_fit_engine import (
    GAP_REJECT_REASON,
    allocate_first_fit,
    allocate_first_fit_in_gap,
    free_spans_from_pillars,
    gap_descriptors,
)

SEED_PILLARS = [
    {"id": 1, "position_m": 10.0, "thickness_m": 0.5, "label": "灯柱A"},
    {"id": 2, "position_m": 20.0, "thickness_m": 0.5, "label": "灯柱B"},
]

def _seed_vendors():
    return [
        {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
        {"id": 3, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
        {"id": 4, "name": "小美饰品", "stall_width_m": 2.5, "priority": 2},
        {"id": 5, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
        {"id": 6, "name": "手作皮具", "stall_width_m": 3.5, "priority": 3},
        {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
    ]


def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}])
    assert len(spans) == 3
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
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"


def test_seed_whole_segment_golden():
    # Regression guard for the engine refactor: six normal vendors place,
    # only the 12m stage truck is rejected.
    r = allocate_first_fit(30.0, _seed_vendors(), SEED_PILLARS)
    assert {p.vendor_id for p in r.placements} == {1, 2, 3, 4, 5, 6}
    assert [x.vendor_id for x in r.rejected] == [7]


def test_gap_trial_placement_sets_and_coordinates():
    # Gap 1 is [10.25, 19.75] between 灯柱A and 灯柱B (9.5m).
    r = allocate_first_fit_in_gap(30.0, _seed_vendors(), SEED_PILLARS, 1)
    placed = {p.vendor_id: p for p in r.placements}
    assert sorted(placed) == [1, 2, 4]
    assert placed[1].start_m == 10.25 and placed[1].end_m == 14.25  # fill from the gap's LEFT edge
    assert placed[2].start_m == 14.25 and placed[2].end_m == 17.25
    assert placed[4].start_m == 17.25 and placed[4].end_m == 19.75  # exact fit via epsilon
    # every placement is strictly inside the chosen gap
    for p in r.placements:
        assert 10.25 <= p.start_m < p.end_m <= 19.75
    assert [x.vendor_id for x in r.rejected] == [5, 3, 6, 7]  # priority processing order
    assert all(x.reason == GAP_REJECT_REASON for x in r.rejected)
    oversized = next(x for x in r.rejected if x.vendor_id == 7)
    assert oversized.vendor_name == "巨型舞台车" and oversized.width_m == 12.0


def test_gap_trial_other_gaps_intact_and_exact_fit_vanishes():
    untouched = free_spans_from_pillars(30.0, SEED_PILLARS)
    r = allocate_first_fit_in_gap(30.0, _seed_vendors(), SEED_PILLARS, 1)
    # chosen gap filled exactly -> gone; the other two gaps stay byte-identical
    assert r.free_spans == [untouched[0], untouched[2]]


def test_gap_trial_leaves_right_hand_remainder():
    # Only one 4m vendor: chosen gap [10.25,19.75] becomes [14.25,19.75].
    vendors = [{"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1}]
    r = allocate_first_fit_in_gap(30.0, vendors, SEED_PILLARS, 1)
    assert (r.placements[0].start_m, r.placements[0].end_m) == (10.25, 14.25)
    assert (14.25, 19.75) in r.free_spans
    assert (0.0, 9.75) in r.free_spans and (20.25, 30.0) in r.free_spans


def test_gap_index_out_of_range():
    with pytest.raises(ValueError, match="空档编号非法"):
        allocate_first_fit_in_gap(30.0, _seed_vendors(), SEED_PILLARS, 9)
    with pytest.raises(ValueError, match="空档编号非法"):
        allocate_first_fit_in_gap(30.0, _seed_vendors(), SEED_PILLARS, -1)


def test_gap_without_pillars_only_index_zero_valid():
    r = allocate_first_fit_in_gap(30.0, _seed_vendors(), [], 0)
    assert {p.vendor_id for p in r.placements} == {1, 2, 3, 4, 5, 6}
    assert [x.vendor_id for x in r.rejected] == [7]
    assert all(0.0 <= p.start_m < p.end_m <= 30.0 for p in r.placements)
    with pytest.raises(ValueError):
        allocate_first_fit_in_gap(30.0, _seed_vendors(), [], 1)


def test_gap_empty_vendors_leaves_spans_unchanged():
    spans = free_spans_from_pillars(30.0, SEED_PILLARS)
    r = allocate_first_fit_in_gap(30.0, [], SEED_PILLARS, 0)
    assert r.placements == [] and r.rejected == []
    assert r.free_spans == spans


def test_gap_descriptors_seed():
    descs = gap_descriptors(30.0, SEED_PILLARS)
    assert [d["index"] for d in descs] == [0, 1, 2]
    assert [d["width_m"] for d in descs] == [9.75, 9.5, 9.75]
    middle = descs[1]
    assert (middle["start_m"], middle["end_m"]) == (10.25, 19.75)
    assert middle["left_label"] == "灯柱A" and middle["right_label"] == "灯柱B"
    assert descs[0]["left_label"] == "街段起点"
    assert descs[2]["right_label"] == "街段终处"
