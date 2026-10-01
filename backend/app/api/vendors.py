import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Vendor
from app.schemas import VendorWidthUpdate
router = APIRouter(prefix="/vendors", tags=["vendors"])


def _vendor_row(r: Vendor) -> dict:
    return {"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
            "stall_width_m": r.stall_width_m, "priority": r.priority}

@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    return [_vendor_row(r)
            for r in db.scalars(select(Vendor).order_by(Vendor.priority, Vendor.id)).all()]

@router.patch("/{vendor_id}")
def update_vendor_width(vendor_id: int, body: VendorWidthUpdate, db: Session = Depends(get_db)):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, "摊主不存在")
    width = body.stall_width_m
    if not isinstance(width, (int, float)) or isinstance(width, bool) or not math.isfinite(width) or width <= 0:
        raise HTTPException(400, "宽度必须为大于 0 的数字")
    vendor.stall_width_m = float(width)
    db.commit(); db.refresh(vendor)
    return _vendor_row(vendor)
