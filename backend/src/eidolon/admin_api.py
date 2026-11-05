"""The admin console's API, under `/api/admin`, for admins only (ADR-0013).

Persisted first-user administrators and explicitly listed identities may enter. Every
other visitor receives 404, signed in or not, as though the console did not exist.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request

from eidolon.accounts import is_admin
from eidolon.assembly import Backend
from eidolon.sessions import session_user
from eidolon.store import User


async def admin_user(request: Request) -> User:
    """The signed-in admin, who has agreed to the terms and is not banned; 404 for anyone
    else."""
    backend: Backend = request.app.state.backend
    user = await session_user(request)
    if (
        user is None
        or user.consented_at is None
        or user.banned_at is not None
        or not await is_admin(backend.store, backend.settings, user.id)
    ):
        raise HTTPException(404)
    return user


Admin = Annotated[User, Depends(admin_user)]


def add_admin_routes(app: FastAPI, backend: Backend) -> None:
    @app.get("/api/admin")
    def admin(user: Admin) -> dict:
        """The admin console's front door: who the admin is."""
        return {"name": user.name}
