"""The data doctor's page: GET /api/doctor (doctorlib.py does the checking)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import ViewStore
from ..doctorlib import check
from .deps import get_store

router = APIRouter()


@router.get("/api/doctor")
def doctor(store: ViewStore = Depends(get_store)) -> dict:
    """fsck for a data root made of files: every source the dashboard reads,
    examined, and what is wrong with it named. Read-only."""
    return check(store)
