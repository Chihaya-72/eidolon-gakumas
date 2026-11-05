"""Password entry and administrator access controls, enforced for every business API."""

import re
import secrets
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SecretStr, StrictBool

from eidolon.access import ACCESS_COOKIE, BROWSER_COOKIE, LIFETIME, client_ip
from eidolon.admin_api import Admin
from eidolon.sessions import origin_allowed

if TYPE_CHECKING:
    from eidolon.assembly import Backend

_VISITOR = re.compile(r"[A-Za-z0-9_-]{32,80}\Z")


class PasswordInput(BaseModel):
    password: SecretStr


class AccessSettingsInput(BaseModel):
    enabled: StrictBool
    password: SecretStr | None = None


def add_access_routes(app: FastAPI, backend: "Backend") -> None:
    gate, settings = backend.access, backend.settings

    def visitor(request: Request, response: Response) -> str:
        value = request.cookies.get(BROWSER_COOKIE, "")
        if not _VISITOR.fullmatch(value):
            value = secrets.token_urlsafe(32)
            response.set_cookie(
                BROWSER_COOKIE, value, max_age=365 * 86400, httponly=True,
                secure=settings.domain is not None, samesite="lax", path="/",
            )
        return value

    def grant(response: Response, token: str | None) -> None:
        if token:
            response.set_cookie(
                ACCESS_COOKIE, token, max_age=int(LIFETIME.total_seconds()), httponly=True,
                secure=settings.domain is not None, samesite="lax", path="/",
            )
        else:
            response.delete_cookie(
                ACCESS_COOKIE, httponly=True, secure=settings.domain is not None,
                samesite="lax", path="/",
            )

    @app.middleware("http")
    async def access_middleware(request: Request, call_next):
        path = request.url.path
        if path in {"/api/health", "/api/access/status", "/api/access/verify"}:
            return await call_next(request)
        state = await gate.state(
            request.cookies.get(BROWSER_COOKIE, ""), client_ip(request, settings),
            request.cookies.get(ACCESS_COOKIE),
        )
        if not state["passed"]:
            return JSONResponse(
                {"detail": "访问已被封禁，请联系管理员" if state["banned"] else "请先输入网站访问密码",
                 "code": "access_banned" if state["banned"] else "access_required"},
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        return await call_next(request)

    @app.get("/api/access/status")
    async def status(request: Request, response: Response) -> dict:
        browser = visitor(request, response)
        response.headers["Cache-Control"] = "no-store"
        return await gate.state(browser, client_ip(request, settings), request.cookies.get(ACCESS_COOKIE))

    @app.post("/api/access/verify")
    async def verify(body: PasswordInput, request: Request, response: Response) -> dict:
        if not origin_allowed(request.headers.get("origin"), True, settings):
            raise HTTPException(403, "请求来自其他网站，已拒绝")
        browser = visitor(request, response)
        password = body.password.get_secret_value()
        if len(password) > 128:
            password = ""  # bounded hashing cost; still one failed attempt
        state, token = await gate.verify(password, browser, client_ip(request, settings))
        if token:
            grant(response, token)
        response.headers["Cache-Control"] = "no-store"
        if not state["passed"]:
            response.status_code = 403 if state["banned"] else 409 if state.get("changed") else 401
            state["detail"] = (
                "访问已被封禁，请联系管理员" if state["banned"] else
                "访问密码已修改，请重试" if state.get("changed") else "访问密码不正确"
            )
        return state

    @app.get("/api/admin/access")
    async def admin_settings(_: Admin) -> dict:
        return await gate.settings()

    @app.put("/api/admin/access")
    async def save(body: AccessSettingsInput, request: Request, response: Response, _: Admin) -> dict:
        browser = visitor(request, response)
        try:
            state, token = await gate.save(
                body.enabled, body.password.get_secret_value() if body.password is not None else None,
                browser,
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        grant(response, token)
        response.headers["Cache-Control"] = "no-store"
        return state

    @app.get("/api/admin/access/bans")
    async def bans(_: Admin) -> list[dict]:
        return await gate.bans()

    @app.delete("/api/admin/access/bans/{ban_id}", status_code=204)
    async def unban(ban_id: str, _: Admin) -> None:
        await gate.unban(ban_id)
