from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Pillar, Segment
from app.services.first_fit_engine import gap_descriptors
router = APIRouter(prefix="/segments", tags=["segments"])

@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m}
            for r in db.scalars(select(Segment).order_by(Segment.id)).all()]

@router.get("/{segment_id}/gaps")
def segment_gaps(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [
        {"id": p.id, "position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
        for p in db.scalars(
            select(Pillar).where(Pillar.segment_id == segment_id).order_by(Pillar.position_m)
        ).all()
    ]
    return gap_descriptors(seg.width_m, pillars)
