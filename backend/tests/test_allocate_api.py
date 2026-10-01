"""API 级测试：试摆不落库、确认落库、空档校验、改摊宽实时生效等。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import AllocationRun, MarketDay, Pillar, Segment, Vendor


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    db = TestingSession()
    day = MarketDay(name="周末夜市", day=date(2026, 9, 20))
    db.add(day); db.flush()
    seg = Segment(market_day_id=day.id, name="东街段", width_m=30.0)
    db.add(seg); db.flush()
    db.add(Pillar(segment_id=seg.id, position_m=10.0, thickness_m=0.5, label="灯柱A"))
    db.add(Pillar(segment_id=seg.id, position_m=20.0, thickness_m=0.5, label="灯柱B"))
    vendors = [
        ("阿强烧烤", 4.0, 1), ("林记糖水", 3.0, 1), ("老周水果", 5.0, 2),
        ("小美饰品", 2.5, 2), ("大碗面", 6.0, 1), ("手作皮具", 3.5, 3),
        ("巨型舞台车", 12.0, 9),
    ]
    for name, wdt, pri in vendors:
        db.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt, priority=pri))
    db.commit(); db.close()
    # 不用 with（不触发 lifespan，避免连生产 Postgres）
    yield TestClient(app), TestingSession
    app.dependency_overrides.clear()


def run_count(Session):
    with Session() as db:
        return db.scalar(select(func.count()).select_from(AllocationRun))


def names(payload, key):
    return {x["vendor_name"] for x in payload[key]}


# ---- 未选空档 ----

def test_preview_without_span_rejected_not_shorted(client):
    c, Session = client
    r = c.post("/api/allocate/preview", json={"segment_id": 1})
    assert r.status_code == 400
    assert "未选空档" in r.text
    assert "空档不够" not in r.text
    assert run_count(Session) == 0


def test_confirm_without_span_uses_same_path_as_preview(client):
    """未选空档时确认与试摆走同一拒绝路径（绿仓一致）。"""
    c, Session = client
    r1 = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": None})
    r2 = c.post("/api/allocate/confirm", json={"segment_id": 1})
    assert r1.status_code == r2.status_code == 400
    assert "未选空档" in r1.text and "未选空档" in r2.text
    assert run_count(Session) == 0


# ---- 非法空档编号 ----

def test_illegal_span_preview_keeps_existing_runs(client):
    c, Session = client
    # 先成功确认一条
    ok = c.post("/api/allocate/confirm", json={"segment_id": 1, "span_index": 0})
    assert ok.status_code == 200
    assert run_count(Session) == 1
    # 非法编号试摆失败：不得清掉已成功运行
    bad = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 99})
    assert bad.status_code == 400
    assert "空档编号无效" in bad.text
    assert run_count(Session) == 1


def test_illegal_span_not_recorded_as_success(client):
    c, Session = client
    r = c.post("/api/allocate/confirm", json={"segment_id": 1, "span_index": -3})
    assert r.status_code == 400
    assert run_count(Session) == 0


# ---- 双击试摆不增行 ----

def test_double_preview_adds_zero_runs(client):
    c, Session = client
    r1 = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 1})
    r2 = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 1})
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["mode"] == "preview" and r1.json()["committed"] is False
    assert r2.json()["mode"] == "preview"
    assert run_count(Session) == 0


# ---- 试摆/确认集合一致；种子灯柱A–B场景 ----

def test_seed_giant_truck_preview_then_confirm(client):
    c, Session = client
    prev = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 1}).json()
    # 巨型舞台车 12m 宽于 A–B 空档 9.5m：试摆放不下侧，库行数不变
    assert "巨型舞台车" in names(prev, "rejected")
    assert "巨型舞台车" not in names(prev, "placements")
    assert run_count(Session) == 0
    # 再确认一次行数才允许加一
    conf = c.post("/api/allocate/confirm", json={"segment_id": 1, "span_index": 1})
    assert conf.status_code == 200
    body = conf.json()
    assert run_count(Session) == 1
    # 试摆与确认对「该空档内」的放置/拒绝集合必须一致
    assert names(prev, "placements") == names(body, "placements")
    assert names(prev, "rejected") == names(body, "rejected")
    assert [(p["start_m"], p["end_m"]) for p in prev["placements"]] == \
           [(p["start_m"], p["end_m"]) for p in body["placements"]]
    assert body["mode"] == "committed" and body["committed"] is True
    # 确认只在单空档内，不得扩成整段
    assert all(10.25 <= p["start_m"] and p["end_m"] <= 19.75 for p in body["placements"])
    assert body["scope"] == "span" and body["span_index"] == 1
    # 主图与放不下都能对上同一条已入库运行
    latest = c.get("/api/allocate/latest?segment_id=1").json()
    assert latest["id"] == body["id"]
    assert names(latest, "placements") == names(body, "placements")
    assert names(latest, "rejected") == names(body, "rejected")
    got = c.get(f"/api/allocate/run/{body['id']}").json()
    assert names(got, "rejected") == names(body, "rejected")
    runs = c.get("/api/allocate/runs?segment_id=1").json()
    assert len(runs) == 1 and runs[0]["id"] == body["id"]
    assert runs[0]["scope"] == "span" and runs[0]["span_index"] == 1


def test_preview_is_marked_not_committed(client):
    c, Session = client
    r = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 1}).json()
    # 试摆结论不得写成已入库运行
    assert r["committed"] is False and r["mode"] == "preview"
    assert "尚未入库" in r["notice"]
    assert "id" not in r


# ---- 改摊宽后再试摆按新宽 ----

def test_changed_width_reflected_in_next_preview(client):
    c, Session = client
    # 林记糖水 id=2，宽 3 → 20：A–B 空档放不下
    patched = c.patch("/api/vendors/2", json={"stall_width_m": 20.0})
    assert patched.status_code == 200
    prev = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 1}).json()
    assert "林记糖水" in names(prev, "rejected")
    assert "林记糖水" not in names(prev, "placements")
    # 改回 3 再试摆：不得沿用旧宽结果
    c.patch("/api/vendors/2", json={"stall_width_m": 3.0})
    prev2 = c.post("/api/allocate/preview", json={"segment_id": 1, "span_index": 1}).json()
    assert "林记糖水" in names(prev2, "placements")


def test_invalid_width_patch_rejected(client):
    c, Session = client
    r = c.patch("/api/vendors/2", json={"stall_width_m": 0})
    assert r.status_code == 400


# ---- latest 空库不隐式建运行；确认无需令牌 ----

def test_latest_empty_creates_no_run(client):
    c, Session = client
    r = c.get("/api/allocate/latest?segment_id=1")
    assert r.status_code == 200
    assert r.json()["id"] is None
    assert run_count(Session) == 0


def test_confirm_requires_no_session_token(client):
    c, Session = client
    r = c.post("/api/allocate/confirm", json={"segment_id": 1, "span_index": 0})
    assert r.status_code == 200
    assert r.json()["id"] is not None


def test_spans_listing(client):
    c, Session = client
    r = c.get("/api/allocate/spans?segment_id=1").json()
    assert [s["index"] for s in r["spans"]] == [0, 1, 2]
    assert r["spans"][1] == {"index": 1, "start_m": 10.25, "end_m": 19.75, "width_m": 9.5}
