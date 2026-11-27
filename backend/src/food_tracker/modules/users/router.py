from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, field_validator

from food_tracker.core.errors import ApiError, DomainError
from food_tracker.modules.auth.router import Service
from food_tracker.modules.auth.schemas import ApiModel
from food_tracker.modules.users.models import User


class MealTimes(ApiModel):
    breakfast: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    lunch: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    dinner: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    snack: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class UserResponse(ApiModel):
    id: UUID
    email: str
    email_verified_at: datetime
    role: Literal["USER", "ADMIN"]
    display_name: str
    timezone: str
    meal_times: MealTimes
    revision: int


bearer = HTTPBearer(auto_error=False)
router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    responses={status: {"model": ApiError} for status in (401, 403, 412, 422, 428, 503)},
)


async def get_current_user(
    service: Service, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise DomainError(401, "UNAUTHENTICATED", "Войдите в аккаунт")
    return await service.current_user(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser, response: Response):
    response.headers["ETag"] = f'"profile-{user.revision}"'
    return UserResponse.model_validate(user, from_attributes=True)


class ProfileRequest(ApiModel):
    display_name: Annotated[str, Field(max_length=100)]
    timezone: Annotated[str, Field(max_length=100)]
    meal_times: MealTimes

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use an IANA timezone") from error
        return value


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: ProfileRequest,
    response: Response,
    user: CurrentUser,
    service: Service,
    if_match: Annotated[str | None, Header()] = None,
):
    if not if_match:
        raise DomainError(428, "REVISION_REQUIRED", "Загрузите актуальный профиль")
    user_id = user.id
    await service.db.rollback()
    async with service.db.begin():
        current = await service.db.get(User, user_id, with_for_update=True)
        if if_match != f'"profile-{current.revision}"':
            raise DomainError(
                412,
                "PROFILE_REVISION_CONFLICT",
                "Профиль изменён в другом окне",
                {"currentRevision": current.revision},
            )
        current.display_name = body.display_name.strip()
        current.timezone = body.timezone
        current.meal_times = body.meal_times.model_dump()
        current.revision += 1
        current.updated_at = service.clock()
        dto = UserResponse.model_validate(current, from_attributes=True)
    response.headers["ETag"] = f'"profile-{dto.revision}"'
    return dto
