from typing import Any

from pydantic import BaseModel


class GapRequest(BaseModel):
    segment_id: int = 1
    gap_index: int | None = None


class VendorWidthUpdate(BaseModel):
    # Any so invalid values (zero/negative/NaN/string) reach the endpoint and
    # come back as the spec's 400 instead of a framework-level 422.
    stall_width_m: Any
