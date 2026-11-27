import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from food_tracker.core.errors import ApiError, DomainError
from food_tracker.core.security import create_csrf, valid_csrf
from food_tracker.db.session import get_session
from food_tracker.modules.auth.schemas import (
    ChallengeResponse,
    CodeRequest,
    CsrfResponse,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordResetResponse,
    RegisterRequest,
    ResendRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerificationRequired,
)
from food_tracker.modules.auth.service import AuthService

COOKIE_PATH = "/api/v1/auth"
COOKIE_REFRESH = "ft_refresh"
COOKIE_CSRF = "ft_csrf"
router = APIRouter(
    prefix=COOKIE_PATH,
    tags=["auth"],
    responses={status: {"model": ApiError} for status in (400, 401, 403, 422, 429, 503)},
)


def get_service(request: Request, session: Annotated[AsyncSession, Depends(get_session)]):
    return AuthService(session, request.app.state.settings, request.app.state.clock)


Service = Annotated[AuthService, Depends(get_service)]


def request_ip(request: Request):
    # Trust the socket peer only. Forwarded headers must be sanitized by a trusted proxy.
    return request.client.host if request.client else "unknown"


def require_csrf(
    request: Request,
    origin: Annotated[str | None, Header()] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
):
    settings = request.app.state.settings
    if origin not in settings.auth_allowed_origins:
        raise DomainError(403, "ORIGIN_FORBIDDEN", "Источник запроса не разрешён")
    cookie, header = request.cookies.get(COOKIE_CSRF, ""), (x_csrf_token or "")
    if (
        len(cookie) > 512
        or len(header) > 512
        or not cookie.isascii()
        or not header.isascii()
        or not cookie
        or not hmac.compare_digest(cookie, header)
        or not valid_csrf(settings, cookie, request.app.state.clock())
    ):
        raise DomainError(403, "CSRF_INVALID", "Обновите страницу и повторите запрос")


def cookie(response, name, value, max_age):
    response.set_cookie(
        name, value, max_age=max_age, httponly=True, secure=True, samesite="lax", path=COOKIE_PATH
    )
    response.headers["Cache-Control"] = "no-store"


def token_response(response, request, result):
    dto, refresh, expiry = result
    cookie(
        response,
        COOKIE_REFRESH,
        refresh,
        max(0, int((expiry - request.app.state.clock()).total_seconds())),
    )
    return dto


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(request: Request, response: Response, service: Service):
    old = request.cookies.get(COOKIE_CSRF, "")
    now = service.clock()
    token = old if valid_csrf(service.settings, old, now) else create_csrf(service.settings, now)
    cookie(response, COOKIE_CSRF, token, service.settings.csrf_ttl_seconds)
    return CsrfResponse(csrf_token=token)


@router.post(
    "/register",
    response_model=ChallengeResponse,
    status_code=202,
    responses={409: {"model": ApiError}},
    dependencies=[Depends(require_csrf)],
)
async def register(body: RegisterRequest, request: Request, service: Service):
    return await service.register(body.email, body.password.get_secret_value(), request_ip(request))


@router.post("/verify-email", response_model=TokenResponse, dependencies=[Depends(require_csrf)])
async def verify_email(body: CodeRequest, request: Request, response: Response, service: Service):
    result = await service.verify_email(body.challenge_id, body.code, request_ip(request))
    return token_response(response, request, result)


@router.post(
    "/verification/resend", response_model=ChallengeResponse, dependencies=[Depends(require_csrf)]
)
async def resend(body: ResendRequest, request: Request, service: Service):
    return await service.resend(body.challenge_id, request_ip(request))


@router.post(
    "/login",
    response_model=TokenResponse | VerificationRequired,
    dependencies=[Depends(require_csrf)],
)
async def login(body: LoginRequest, request: Request, response: Response, service: Service):
    result = await service.login(body.email, body.password.get_secret_value(), request_ip(request))
    return token_response(response, request, result) if isinstance(result, tuple) else result


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(require_csrf)])
async def refresh(request: Request, response: Response, service: Service):
    result = await service.refresh(request.cookies.get(COOKIE_REFRESH), request_ip(request))
    return token_response(response, request, result)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(request: Request, response: Response, service: Service):
    await service.logout(request.cookies.get(COOKIE_REFRESH), request_ip(request))
    response.delete_cookie(
        COOKIE_REFRESH, path=COOKIE_PATH, secure=True, httponly=True, samesite="lax"
    )


@router.post(
    "/password/forgot",
    response_model=ChallengeResponse,
    status_code=202,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    dependencies=[Depends(require_csrf)],
)
async def forgot_password(body: ForgotPasswordRequest, request: Request, service: Service):
    return await service.forgot_password(body.email, request_ip(request))


@router.post(
    "/password/reset", response_model=PasswordResetResponse, dependencies=[Depends(require_csrf)]
)
async def reset_password(
    body: ResetPasswordRequest, request: Request, response: Response, service: Service
):
    await service.reset_password(
        body.challenge_id, body.code, body.new_password.get_secret_value(), request_ip(request)
    )
    response.delete_cookie(
        COOKIE_REFRESH, path=COOKIE_PATH, secure=True, httponly=True, samesite="lax"
    )
    return PasswordResetResponse()
