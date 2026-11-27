from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RegisterRequest(ApiModel):
    email: EmailStr
    password: Annotated[SecretStr, Field(min_length=12, max_length=128)]


class ChallengeResponse(ApiModel):
    challenge_id: UUID
    expires_at: datetime
    resend_available_at: datetime


class CodeRequest(ApiModel):
    challenge_id: UUID
    code: Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class ResendRequest(ApiModel):
    challenge_id: UUID


class TokenResponse(ApiModel):
    status: Literal["authenticated"] = "authenticated"
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    expires_at: datetime
    user_id: UUID


class CsrfResponse(ApiModel):
    csrf_token: str


class LoginRequest(ApiModel):
    email: EmailStr
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class VerificationRequired(ChallengeResponse):
    status: Literal["email_verification_required"] = "email_verification_required"


class ForgotPasswordRequest(ApiModel):
    email: EmailStr


class ResetPasswordRequest(CodeRequest):
    new_password: Annotated[SecretStr, Field(min_length=12, max_length=128)]


class PasswordResetResponse(ApiModel):
    status: Literal["password_reset"] = "password_reset"
