import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from database import get_db
from sync_runs import service as sync_runs
from user_data.service import delete_all, export_rows, to_csv, to_json
from utils.timeutil import utc_now

router = APIRouter()


class DeleteAllRequest(BaseModel):
    confirm: Literal["DELETE"]


class DeletedResponse(BaseModel):
    deleted: bool


def _download(content: str, media_type: str, extension: str) -> Response:
    filename = f"job-applications-{utc_now():%Y-%m-%d}.{extension}"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
    })


@router.get("/export/applications.csv", response_class=Response,
            responses={200: {"content": {"text/csv": {}}}})
async def export_csv(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    return _download(to_csv(await export_rows(db, user)), "text/csv; charset=utf-8", "csv")


@router.get("/export/applications.json", response_class=Response,
            responses={200: {"content": {"application/json": {}}}})
async def export_json(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    body = json.dumps(jsonable_encoder(to_json(await export_rows(db, user))), ensure_ascii=False, indent=1)
    return _download(body, "application/json", "json")


@router.post("/delete-all", response_model=DeletedResponse)
async def delete_everything(
    body: DeleteAllRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> DeletedResponse:
    if await sync_runs.get_running(db, user) is not None:
        raise HTTPException(status_code=409, detail="A sync is running. Wait for it to finish, then try again.")
    await delete_all(db, user)
    return DeletedResponse(deleted=True)
