from app.models.models import AllocationRun


def _run_count(db) -> int:
    return db.query(AllocationRun).count()


def test_gaps_seed(client):
    res = client.get("/api/segments/1/gaps")
    assert res.status_code == 200
    gaps = res.json()
    assert [g["index"] for g in gaps] == [0, 1, 2]
    assert [g["width_m"] for g in gaps] == [9.75, 9.5, 9.75]
    assert gaps[1]["left_label"] == "灯柱A" and gaps[1]["right_label"] == "灯柱B"


def test_gaps_missing_segment(client):
    assert client.get("/api/segments/999/gaps").status_code == 404


def test_trial_without_gap_selected_is_400_and_no_rows(client, db_session):
    before = _run_count(db_session)
    res = client.post("/api/allocate/trial", json={"segment_id": 1})
    assert res.status_code == 400
    assert res.json()["detail"] == "请先点选一个柱间空档"
    db_session.expire_all()
    assert _run_count(db_session) == before


def test_confirm_without_gap_selected_is_400_and_no_rows(client, db_session):
    before = _run_count(db_session)
    res = client.post("/api/allocate/confirm", json={"segment_id": 1})
    assert res.status_code == 400
    assert res.json()["detail"] == "请先点选一个柱间空档"
    db_session.expire_all()
    assert _run_count(db_session) == before


def test_double_trial_adds_zero_rows_and_matches_seed(client, db_session):
    payload = {"segment_id": 1, "gap_index": 1}
    responses = []
    for _ in range(3):  # double (and triple) clicking trial
        res = client.post("/api/allocate/trial", json=payload)
        assert res.status_code == 200
        responses.append(res.json())
    db_session.expire_all()
    assert _run_count(db_session) == 0  # 开间运行表一行都不许新增

    for body in responses:
        assert body["trial"] is True and body["id"] is None and body["created_at"] is None
        assert {p["vendor_id"] for p in body["placements"]} == {1, 2, 4}
        coords = {(p["start_m"], p["end_m"]) for p in body["placements"]}
        assert coords == {(10.25, 14.25), (14.25, 17.25), (17.25, 19.75)}
        assert {x["vendor_id"] for x in body["rejected"]} == {3, 5, 6, 7}
        assert [x["vendor_id"] for x in body["rejected"]] == [5, 3, 6, 7]
        stage = next(x for x in body["rejected"] if x["vendor_id"] == 7)
        assert stage["vendor_name"] == "巨型舞台车"
        assert "所选柱间空档" in stage["reason"]
        # nothing placed outside the chosen gap
        assert all(10.25 <= p["start_m"] < p["end_m"] <= 19.75 for p in body["placements"])


def test_confirm_matches_trial_and_adds_exactly_one_row(client, db_session):
    trial = client.post("/api/allocate/trial", json={"segment_id": 1, "gap_index": 1}).json()
    assert _run_count(db_session) == 0

    res = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_index": 1})
    assert res.status_code == 200
    confirm = res.json()
    db_session.expire_all()
    assert _run_count(db_session) == 1  # 再确认一次行数才允许加一

    assert confirm["trial"] is False and isinstance(confirm["id"], int)
    # 试摆与确认对「该空档内」的放置与拒绝集合必须一致
    assert [(p["vendor_id"], p["start_m"], p["end_m"]) for p in confirm["placements"]] == \
           [(p["vendor_id"], p["start_m"], p["end_m"]) for p in trial["placements"]]
    assert [(x["vendor_id"], x["reason"]) for x in confirm["rejected"]] == \
           [(x["vendor_id"], x["reason"]) for x in trial["rejected"]]

    latest = client.get("/api/allocate/latest?segment_id=1")
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["id"] == confirm["id"]
    assert latest_body["gap"]["index"] == 1
    assert {p["vendor_id"] for p in latest_body["placements"]} == {1, 2, 4}
    assert {x["vendor_id"] for x in latest_body["rejected"]} == {3, 5, 6, 7}

    runs = client.get("/api/allocate/runs?segment_id=1").json()
    assert len(runs) == 1
    summary = runs[0]
    assert summary["scope_type"] == "gap" and summary["gap_index"] == 1
    assert summary["placed_count"] == 3 and summary["rejected_count"] == 4
    assert "灯柱A" in summary["scope_label"] and "灯柱B" in summary["scope_label"]

    detail = client.get(f"/api/allocate/runs/{confirm['id']}").json()
    assert detail["trial"] is False and detail["gap"]["left_label"] == "灯柱A"
    assert {p["vendor_id"] for p in detail["placements"]} == {1, 2, 4}


def test_illegal_gap_index_failure_keeps_existing_runs(client, db_session):
    # one committed run exists first
    client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_index": 1})
    db_session.expire_all()
    assert _run_count(db_session) == 1
    existing = client.get("/api/allocate/runs?segment_id=1").json()

    for idx in (9, -1):
        res = client.post("/api/allocate/trial", json={"segment_id": 1, "gap_index": idx})
        assert res.status_code == 400
        assert res.json()["detail"] == "空档编号非法"
    db_session.expire_all()
    assert _run_count(db_session) == 1  # failure must not clear successful runs
    assert client.get("/api/allocate/runs?segment_id=1").json() == existing


def test_latest_404_when_no_runs_and_no_side_effect(client, db_session):
    assert _run_count(db_session) == 0
    res = client.get("/api/allocate/latest?segment_id=1")
    assert res.status_code == 404
    assert res.json()["detail"] == "尚无已入库运行"
    db_session.expire_all()
    assert _run_count(db_session) == 0  # GET must not auto-create a run anymore


def test_missing_segment_trial_and_confirm(client):
    body = {"segment_id": 999, "gap_index": 0}
    assert client.post("/api/allocate/trial", json=body).status_code == 404
    assert client.post("/api/allocate/confirm", json=body).status_code == 404


def test_patch_width_then_retrial_uses_new_width(client, db_session):
    # Make the 2.5m leftover (after 阿强4 + 林记3) unavailable to 小美饰品 by
    # widening her to 3.0m -> she is rejected; then shrink the 12m stage truck
    # to 2.5m and it takes that exact leftover in the chosen gap.
    assert client.patch("/api/vendors/4", json={"stall_width_m": 3.0}).status_code == 200
    assert client.patch("/api/vendors/7", json={"stall_width_m": 2.5}).status_code == 200

    trial = client.post("/api/allocate/trial", json={"segment_id": 1, "gap_index": 1}).json()
    rejected_ids = {x["vendor_id"] for x in trial["rejected"]}
    assert 4 in rejected_ids  # 小美饰品 now too wide for the leftover
    placed = {p["vendor_id"]: p for p in trial["placements"]}
    assert 7 in placed  # 改摊宽后再试摆须按刚改的宽度
    assert placed[7]["start_m"] == 17.25 and placed[7]["end_m"] == 19.75
    assert _run_count(db_session) == 0


def test_patch_width_invalid(client):
    for bad in (0, -3, "abc"):
        res = client.patch("/api/vendors/7", json={"stall_width_m": bad})
        assert res.status_code == 400
        assert res.json()["detail"] == "宽度必须为大于 0 的数字"
    res = client.request("PATCH", "/api/vendors/7",
                         content='{"stall_width_m": NaN}',
                         headers={"Content-Type": "application/json"})
    assert res.status_code == 400
    assert res.json()["detail"] == "宽度必须为大于 0 的数字"


def test_patch_width_missing_vendor(client):
    assert client.patch("/api/vendors/999", json={"stall_width_m": 3}).status_code == 404


def test_whole_segment_run_marked_segment_scope(client, db_session):
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 200
    body = res.json()
    assert body["gap"] is None and body["trial"] is False
    assert {p["vendor_id"] for p in body["placements"]} == {1, 2, 3, 4, 5, 6}
    runs = client.get("/api/allocate/runs?segment_id=1").json()
    assert runs[0]["scope_type"] == "segment" and runs[0]["scope_label"] == "整段"
