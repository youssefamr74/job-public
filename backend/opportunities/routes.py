import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from applications.schemas import ApplicationResponse
from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from opportunities import service
from opportunities.models import CONVERTED, OPEN, STATUSES
from opportunities.schemas import OpportunityResponse

router = APIRouter()


@router.get("/")
async def get_opportunities(
    status: Optional[str] = Query(default=None, description="open, converted or dismissed"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OpportunityResponse]:
    if status and status not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status. Must be one of: converted, dismissed, open")
    return await service.list_opportunities(db, user, status)


@router.post("/{opportunity_id}/convert", response_model=ApplicationResponse)
async def convert_opportunity(
    opportunity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    opportunity = await service.get_opportunity(db, user, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if opportunity.status == CONVERTED:
        raise HTTPException(status_code=409, detail="Opportunity was already converted")
    return await service.convert(db, user, opportunity)


@router.post("/{opportunity_id}/dismiss", response_model=OpportunityResponse)
async def dismiss_opportunity(
    opportunity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    opportunity = await service.get_opportunity(db, user, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if opportunity.status != OPEN:
        raise HTTPException(status_code=409, detail="Only an open opportunity can be dismissed")
    return await service.dismiss(db, opportunity)
