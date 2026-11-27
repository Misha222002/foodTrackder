import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from food_tracker.api.health import router as health_router
from food_tracker.core.clock import utc_now
from food_tracker.core.config import Settings
from food_tracker.core.errors import DomainError
from food_tracker.db.session import create_engine
from food_tracker.modules.auth.mail import SmtpMailer, mail_worker
from food_tracker.modules.auth.router import router as auth_router
from food_tracker.modules.users.router import router as users_router


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(config)
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        task = None
        if config.mail_worker_enabled and config.mail_encryption_key:
            task = asyncio.create_task(
                mail_worker(app.state.session_factory, config, app.state.mailer, app.state.clock)
            )
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await engine.dispose()

    app = FastAPI(title="Ем по плану API", version="0.1.0", lifespan=lifespan)

    app.state.settings = config
    app.state.clock = utc_now
    app.state.mailer = SmtpMailer(config)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        headers = {}
        if error.status == 429:
            headers["Retry-After"] = str(error.details.get("retryAfterSeconds", 60))
        response = JSONResponse(
            status_code=error.status,
            headers=headers,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "requestId": request.state.request_id,
            },
        )

        if error.status == 401 and request.url.path == "/api/v1/auth/refresh":
            response.delete_cookie(
                "ft_refresh", path="/api/v1/auth", secure=True, httponly=True, samesite="lax"
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Never serialize Pydantic input: it can contain a password/code/token.
        fields = [
            {
                "path": ".".join(str(v) for v in e["loc"][1:]),
                "message": "Проверьте значение поля",
                "type": e["type"],
            }
            for e in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Проверьте поля формы",
                "details": {"fields": fields},
                "requestId": request.state.request_id,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return JSONResponse(
            status_code=503,
            content={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Сервис временно недоступен",
                "details": {},
                "requestId": request.state.request_id,
            },
        )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        started = time.monotonic()
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/auth"):
            response.headers["Cache-Control"] = "no-store"
            if request.method == "POST":
                await asyncio.sleep(
                    max(0, config.auth_min_response_seconds - (time.monotonic() - started))
                )
        elif request.url.path.startswith("/api/v1/users"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    return app


app = create_app()
