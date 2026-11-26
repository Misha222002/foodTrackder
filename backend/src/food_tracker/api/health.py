from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from food_tracker.core.errors import ApiError
from food_tracker.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


@router.get(
    "/health",
    operation_id="get_health",
    response_model=HealthResponse,
    responses={503: {"model": ApiError, "description": "PostgreSQL is unavailable"}},
    summary="Check API and database readiness",
)
async def get_health(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> HealthResponse | JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        error = ApiError(
            code="DATABASE_UNAVAILABLE",
            message="Сервис временно недоступен. Попробуйте позже.",
            details={},
            requestId=request.state.request_id,
        )
        return JSONResponse(status_code=503, content=error.model_dump())
    return HealthResponse(status="ok", database="ok")
