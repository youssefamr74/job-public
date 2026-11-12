from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth.dependencies import get_current_user
from auth.models import User
from analytics.service import (
    get_summary,
    get_response_rate,
    get_best_time,
    get_timeline,
    get_role_performance,
    get_weekly_review,
    goal_days_met_this_week,
)
from analytics.overview import AnalyticsOverview, WeeklyReview, build_overview
from analytics.role_groups_service import (
    MergeRequest, RoleGroups, Suggestions, list_groups, load_merges, merge_groups, suggest_merges, unmerge_group,
)
from ai.clients import AIError
from ai.routes import ai_error
from ai.service import ai_configured
from applications.schemas import ApplicationResponse
from applications.service import get_user_applications

router = APIRouter()


@router.get("/summary")
async def summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await get_summary(user=user, db=db)


@router.get("/response-rate")
async def response_rate(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await get_response_rate(user=user, db=db)


@router.get("/best-time")
async def best_time(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await get_best_time(user=user, db=db)


@router.get("/timeline")
async def timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await get_timeline(user=user, db=db)


@router.get("/role-performance")
async def role_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await get_role_performance(user=user, db=db)


@router.get("/weekly-review", response_model=WeeklyReview)
async def weekly_review(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    return await get_weekly_review(user=user, db=db)


@router.get("/overview", response_model=AnalyticsOverview)
async def overview(
    range: Literal["30", "60", "all"] = Query(default="60"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    apps = [ApplicationResponse.model_validate(app) for app in await get_user_applications(user=user, db=db)]
    return build_overview(apps, range, await goal_days_met_this_week(user, db), user.daily_goal or 0,
                          merges=await load_merges(db, user))


@router.get("/role-groups", response_model=RoleGroups)
async def role_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoleGroups:
    return await list_groups(db, user)


@router.post("/role-groups/merge", status_code=204)
async def merge_role_groups(
    body: MergeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """A rule: applications in `source` count in `target`, now and in future syncs."""
    await merge_groups(db, user, body.source, body.target)


@router.delete("/role-groups/merge", status_code=204)
async def undo_role_group_merge(
    source: str = Query(min_length=1, max_length=255),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await unmerge_group(db, user, source)


@router.post("/role-groups/suggest", response_model=Suggestions)
async def suggest_role_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Suggestions:
    """Merges proposed by the configured AI. Nothing is applied until the user accepts one."""
    if not ai_configured():
        raise HTTPException(status_code=409, detail="Set up AI in Settings to get suggestions")
    try:
        return await suggest_merges(db, user)
    except AIError as exc:
        raise ai_error(exc)
