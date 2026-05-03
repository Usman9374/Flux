from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Lead
from ..schemas import LeadCreate, LeadList, LeadOut

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadList)
def list_leads(
    db: Session = Depends(get_db),
    niche: str | None = Query(default=None, description="Filter by niche (case-insensitive contains)."),
    location: str | None = Query(default=None, description="Filter by location (case-insensitive contains)."),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    filters = []
    if niche:
        filters.append(Lead.niche.ilike(f"%{niche}%"))
    if location:
        filters.append(Lead.location.ilike(f"%{location}%"))

    count_stmt = select(func.count()).select_from(Lead)
    list_stmt = select(Lead).order_by(Lead.created_at.desc())
    for f in filters:
        count_stmt = count_stmt.where(f)
        list_stmt = list_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    items = db.scalars(list_stmt.limit(limit).offset(offset)).all()
    return LeadList(items=[LeadOut.model_validate(i) for i in items], count=total)


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead
