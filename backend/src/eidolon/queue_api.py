"""Browser queue tickets; keys are checked only by the operation that consumes one."""

import re
from typing import TYPE_CHECKING, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from eidolon.service_queue import (
    QueueError, QueueKind, queue_client_gone, queue_request, queue_request_active,
)
from eidolon.sessions import UserId, session_user

if TYPE_CHECKING:
    from eidolon.assembly import Backend

_RESOURCES: dict[str, str] = {
    "turn": r"/api/conversations/[^/]+/turns",
    "call": r"/api/offer",
    "bar": r"/api/bar/visits(?:/[^/]+/(?:serves|retry))?",
    "read_aloud": r"/api/conversations/[^/]+/(?:messages|reach-outs)/[^/]+/read-aloud",
}


class QueueInput(BaseModel):
    kind: Literal["turn", "call", "bar", "read_aloud"]
    resource: str = Field(min_length=1, max_length=500)
    target: str | None = Field(None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _resource(self) -> "QueueInput":
        if not re.fullmatch(_RESOURCES[self.kind], self.resource):
            raise ValueError("排队目标与操作不匹配")
        if (self.kind == "call") != (self.target is not None):
            raise ValueError("语音排队必须指定对话，其他操作通过地址指定目标")
        return self


def add_queue_routes(app: FastAPI, backend: "Backend") -> None:
    queue = backend.queue

    @app.exception_handler(QueueError)
    async def refused(_: Request, error: QueueError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(error), "code": "queue_expired" if error.status == 410 else "queue"},
            status_code=error.status,
        )

    @app.middleware("http")
    async def bind_ticket(request: Request, call_next):
        binding = queue_request.set((request.headers.get("x-queue-ticket"), request.url.path))
        disconnected = queue_client_gone.set(request.is_disconnected)
        async def authenticated(user_id: str) -> bool:
            user = await session_user(request)
            return (
                user is not None and user.id == user_id and user.consented_at is not None
                and user.banned_at is None
            )
        active = queue_request_active.set(authenticated)
        try:
            return await call_next(request)
        finally:
            queue_request_active.reset(active)
            queue_client_gone.reset(disconnected)
            queue_request.reset(binding)

    async def owned(body: QueueInput, user_id: str) -> None:
        # Turn/read-aloud resources include a conversation; don't reserve service for
        # resources the requester cannot use. Calls are bound further by actual body.
        if body.kind in ("turn", "read_aloud", "call"):
            conversation_id = body.target if body.kind == "call" else body.resource.split("/")[3]
            assert conversation_id is not None
            from eidolon.store import NotFound
            try:
                conversation = await backend.store.get_conversation(conversation_id)
            except NotFound:
                raise HTTPException(404) from None
            if conversation is None or conversation.user_id != user_id:
                raise HTTPException(404)

    @app.post("/api/queue")
    async def enqueue(body: QueueInput, user_id: UserId) -> dict:
        await owned(body, user_id)
        kind: QueueKind = body.kind
        resource = f"{body.resource}#{body.target}" if body.target is not None else body.resource
        return await queue.enqueue(user_id, kind, resource)

    @app.get("/api/queue/{ticket_id}")
    async def status(ticket_id: str, user_id: UserId) -> dict:
        return await queue.status(ticket_id, user_id)

    @app.delete("/api/queue/{ticket_id}", status_code=204)
    async def cancel(ticket_id: str, user_id: UserId) -> Response:
        await queue.cancel(ticket_id, user_id)
        return Response(status_code=204)
