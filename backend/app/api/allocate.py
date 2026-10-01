import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    InvalidSpanError,
    allocate_first_fit,
    allocate_in_span,
    result_to_dict,
    span_result_to_dict,
)

router = APIRouter(prefix="/allocate", tags=["allocate"])


class SpanChoice(BaseModel):
    segment_id: int = 1
    span_index: int | None = None  # None / missing => 未选空档，试摆与确认都必须拒绝


def _load_context(db: Session, segment_id: int) -> tuple[Segment, list[dict], list[dict]]:
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)
                                   .order_by(Pillar.position_m)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               # 每次试摆/确认都现读摊主宽度，改摊宽后不得沿用旧宽
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)
                                   .order_by(Vendor.priority, Vendor.id)).all()]
    return seg, pillars, vendors


def _spans_payload(seg: Segment, pillars: list[dict]) -> list[dict]:
    from app.services.first_fit_engine import free_spans_from_pillars
    return [{"index": i, "start_m": a, "end_m": b, "width_m": round(b - a, 3)}
            for i, (a, b) in enumerate(free_spans_from_pillars(seg.width_m, pillars))]


def _require_span(choice: SpanChoice) -> int:
    if choice.span_index is None:
        # 未选空档就试摆/确认：明确拒绝，不得写成“空档不够”
        raise HTTPException(400, "未选空档：请先在分配图上点选一个柱间空档再试摆")
    return choice.span_index


def _span_snapshot(db: Session, choice: SpanChoice) -> dict:
    span_index = _require_span(choice)
    seg, pillars, vendors = _load_context(db, choice.segment_id)
    try:
        result = allocate_in_span(seg.width_m, vendors, pillars, span_index)
    except InvalidSpanError as exc:
        raise HTTPException(400, str(exc)) from exc
    payload = span_result_to_dict(result)
    payload["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    payload["pillars"] = pillars
    payload["spans"] = _spans_payload(seg, pillars)
    return payload


@router.get("/spans")
def list_spans(segment_id: int = 1, db: Session = Depends(get_db)):
    """柱间空档清单，供分配图点选；只读。"""
    seg, pillars, _ = _load_context(db, segment_id)
    return {"segment": {"id": seg.id, "name": seg.name, "width_m": seg.width_m},
            "pillars": pillars, "spans": _spans_payload(seg, pillars)}


@router.post("/preview")
def preview(choice: SpanChoice, db: Session = Depends(get_db)):
    """试摆：只在所选单个柱间空档内按优先序从左填空。纯计算，绝不写库。"""
    payload = _span_snapshot(db, choice)
    payload["mode"] = "preview"
    payload["committed"] = False
    payload["notice"] = "试摆结果，尚未入库；点「确认落库」才写入运行表"
    return payload


@router.post("/confirm")
def confirm(choice: SpanChoice, db: Session = Depends(get_db)):
    """确认落库：与试摆同一个引擎调用，再把同一份空档内结果写入运行表。

    无需任何会话令牌；未选空档与试摆走同一条拒绝路径。
    """
    payload = _span_snapshot(db, choice)
    span_index = payload["span_index"]
    stored = {k: v for k, v in payload.items()}
    stored["mode"] = "committed"
    run = AllocationRun(segment_id=choice.segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(stored, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "mode": "committed", "committed": True,
            "notice": f"已落库：空档#{span_index} 内 {len(payload['placements'])} 个放置、"
                      f"{len(payload['rejected'])} 个放不下", **payload}


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    """现网整段 first-fit（保留）：从左填空写入运行表。"""
    seg, pillars, vendors = _load_context(db, segment_id)
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["scope"] = "segment"
    result["mode"] = "committed"
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillars
    result["spans"] = _spans_payload(seg, pillars)
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, **result}


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    runs = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                      .order_by(AllocationRun.id.desc())).all()
    out = []
    for r in runs:
        data = json.loads(r.result_json or "{}")
        span = data.get("span")
        out.append({
            "id": r.id,
            "created_at": r.created_at.isoformat(timespec="seconds"),
            "scope": data.get("scope", "segment"),
            "mode": data.get("mode", "committed"),
            "span_index": data.get("span_index"),
            "span": span,
            "placements": len(data.get("placements", [])),
            "rejected": len(data.get("rejected", [])),
        })
    return out


@router.get("/run/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    data = json.loads(run.result_json or "{}")
    return {"id": run.id, "mode": "committed", "committed": True,
            "created_at": run.created_at.isoformat(timespec="seconds"), **data}


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        # 不再隐式新建运行：没有已入库运行时返回空骨架，由前端发起试摆/确认
        seg, pillars, _ = _load_context(db, segment_id)
        return {"id": None, "mode": "empty", "committed": False,
                "scope": "segment",
                "placements": [], "rejected": [], "free_spans": [],
                "segment": {"id": seg.id, "name": seg.name, "width_m": seg.width_m},
                "pillars": pillars, "spans": _spans_payload(seg, pillars)}
    data = json.loads(run.result_json)
    return {"id": run.id, "mode": "committed", "committed": True,
            "created_at": run.created_at.isoformat(timespec="seconds"), **data}
