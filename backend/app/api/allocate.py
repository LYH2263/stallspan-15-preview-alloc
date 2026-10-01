import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.schemas import GapRequest
from app.services.first_fit_engine import (
    allocate_first_fit,
    allocate_first_fit_in_gap,
    gap_descriptors,
    result_to_dict,
)
router = APIRouter(prefix="/allocate", tags=["allocate"])


def _load_pillars(db: Session, segment_id: int) -> list[dict]:
    return [
        {"id": p.id, "segment_id": p.segment_id,
         "position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
        for p in db.scalars(
            select(Pillar).where(Pillar.segment_id == segment_id).order_by(Pillar.position_m)
        ).all()
    ]


def _load_vendors(db: Session, market_day_id: int) -> list[dict]:
    # Always read live from the DB: width edits take effect on the next call.
    return [
        {"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
        for v in db.scalars(select(Vendor).where(Vendor.market_day_id == market_day_id)).all()
    ]


def _compute_gap(db: Session, req: GapRequest) -> tuple[Segment, dict, dict]:
    """Shared, write-free computation for BOTH trial and confirm.

    Returns (segment, result_dict, gap_descriptor). Never mutates the DB, which
    structurally guarantees trial adds no run row and that confirm cannot
    silently expand to a whole-segment allocation.
    """
    seg = db.get(Segment, req.segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = _load_pillars(db, req.segment_id)
    vendors = _load_vendors(db, seg.market_day_id)
    if req.gap_index is None:
        raise HTTPException(400, "请先点选一个柱间空档")
    descs = gap_descriptors(seg.width_m, pillars)
    if req.gap_index < 0 or req.gap_index >= len(descs):
        raise HTTPException(400, "空档编号非法")
    gap = descs[req.gap_index]
    result = result_to_dict(
        allocate_first_fit_in_gap(seg.width_m, vendors, pillars, req.gap_index)
    )
    return seg, result, gap


def _gap_envelope(seg: Segment, result: dict, gap: dict, *, trial: bool,
                  run_id: int | None = None, created_at: datetime | None = None) -> dict:
    return {
        "id": run_id,
        "trial": trial,
        "created_at": created_at.isoformat() if created_at else None,
        "segment": {"id": seg.id, "name": seg.name, "width_m": seg.width_m},
        "gap": gap,
        "placements": result["placements"],
        "rejected": result["rejected"],
        "free_spans": result["free_spans"],
    }


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg: raise HTTPException(404, "街段不存在")
    pillars = _load_pillars(db, segment_id)
    vendors = _load_vendors(db, seg.market_day_id)
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["scope"] = {"type": "segment"}
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillars
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, "trial": False, "created_at": run.created_at.isoformat(),
            "gap": None, **result}


@router.post("/trial")
def trial_allocate(req: GapRequest, db: Session = Depends(get_db)):
    seg, result, gap = _compute_gap(db, req)
    return _gap_envelope(seg, result, gap, trial=True)


@router.post("/confirm")
def confirm_allocate(req: GapRequest, db: Session = Depends(get_db)):
    seg, result, gap = _compute_gap(db, req)
    stored = {
        "scope": {"type": "gap", "segment_id": seg.id, "gap_index": gap["index"],
                  "start_m": gap["start_m"], "end_m": gap["end_m"],
                  "width_m": gap["width_m"],
                  "left_label": gap["left_label"], "right_label": gap["right_label"]},
        "segment": {"id": seg.id, "name": seg.name, "width_m": seg.width_m},
        "placements": result["placements"],
        "rejected": result["rejected"],
        "free_spans": result["free_spans"],
    }
    run = AllocationRun(segment_id=seg.id, created_at=datetime.utcnow(),
                        result_json=json.dumps(stored, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return _gap_envelope(seg, result, gap, trial=False,
                         run_id=run.id, created_at=run.created_at)


def _run_summary(run: AllocationRun) -> dict:
    data = json.loads(run.result_json)
    scope = data.get("scope") or {}
    if scope.get("type") == "gap":
        scope_type = "gap"
        gap_index = scope.get("gap_index")
        scope_label = (f"{scope.get('left_label')} – {scope.get('right_label')}"
                       f" · {scope.get('width_m')}m 空档")
    else:
        scope_type = "segment"
        gap_index = None
        scope_label = "整段"
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "segment_id": run.segment_id,
        "scope_type": scope_type,
        "gap_index": gap_index,
        "scope_label": scope_label,
        "placed_count": len(data.get("placements", [])),
        "rejected_count": len(data.get("rejected", [])),
    }


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AllocationRun)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).all()
    return [_run_summary(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    data = json.loads(run.result_json)
    scope = data.get("scope") or {}
    gap = None
    if scope.get("type") == "gap":
        gap = {"index": scope.get("gap_index"),
               "start_m": scope.get("start_m"), "end_m": scope.get("end_m"),
               "width_m": scope.get("width_m"),
               "left_label": scope.get("left_label"), "right_label": scope.get("right_label")}
    return {
        "id": run.id,
        "trial": False,
        "created_at": run.created_at.isoformat(),
        "segment": data.get("segment"),
        "gap": gap,
        "placements": data.get("placements", []),
        "rejected": data.get("rejected", []),
        "free_spans": data.get("free_spans", []),
    }


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        raise HTTPException(404, "尚无已入库运行")
    data = json.loads(run.result_json)
    scope = data.get("scope") or {}
    gap = None
    if scope.get("type") == "gap":
        gap = {"index": scope.get("gap_index"),
               "start_m": scope.get("start_m"), "end_m": scope.get("end_m"),
               "width_m": scope.get("width_m"),
               "left_label": scope.get("left_label"), "right_label": scope.get("right_label")}
    return {
        "id": run.id,
        "trial": False,
        "created_at": run.created_at.isoformat(),
        "segment": data.get("segment"),
        "gap": gap,
        "placements": data.get("placements", []),
        "rejected": data.get("rejected", []),
        "free_spans": data.get("free_spans", []),
    }
