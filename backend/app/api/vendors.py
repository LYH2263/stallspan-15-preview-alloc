from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Vendor

router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorPatch(BaseModel):
    stall_width_m: float | None = None
    priority: int | None = None


@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
             "stall_width_m": r.stall_width_m, "priority": r.priority}
            for r in db.scalars(select(Vendor).order_by(Vendor.priority, Vendor.id)).all()]


@router.patch("/{vendor_id}")
def patch_vendor(vendor_id: int, patch: VendorPatch, db: Session = Depends(get_db)):
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "摊主不存在")
    if patch.stall_width_m is not None:
        if patch.stall_width_m <= 0:
            raise HTTPException(400, "摊宽必须为正数")
        v.stall_width_m = float(patch.stall_width_m)
    if patch.priority is not None:
        v.priority = int(patch.priority)
    db.commit()
    db.refresh(v)
    return {"id": v.id, "market_day_id": v.market_day_id, "name": v.name,
            "stall_width_m": v.stall_width_m, "priority": v.priority}
