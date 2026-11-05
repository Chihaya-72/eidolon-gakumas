"""One deployment-wide, non-preemptive queue for user operations on shared API keys.

Tickets and reservations live on the event loop; only six-hour usage survives a restart.
Claiming a ticket reserves the slot, but records no use until the operation has passed
its own quota/availability checks and calls ``Lease.start``; a browser reservation that
reaches the slot and is given up unused counts as one use. A request without a ticket
waits in this very same queue. Browser hints about whose keys are used are never trusted.
"""

import asyncio
import secrets
import sqlite3
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from eidolon.clock import Clock
from eidolon.data_access import Database

QueueKind = Literal["turn", "call", "bar", "read_aloud", "photo"]
QueueState = Literal["waiting", "ready", "running"]
WINDOW = timedelta(hours=6)
WAIT_TTL = timedelta(seconds=60)
READY_TTL = timedelta(seconds=15)
MAX_PENDING_TICKETS = 5
"""Browser tickets one user may have waiting or ready at once, across all operations."""

# Set by the HTTP boundary; background work must explicitly supply its own resource,
# which prevents it from inheriting (and replaying) its parent's ticket.
queue_request: ContextVar[tuple[str | None, str] | None] = ContextVar(
    "queue_request", default=None
)
queue_client_gone: ContextVar[Callable[[], Awaitable[bool]] | None] = ContextVar(
    "queue_client_gone", default=None
)
queue_request_active: ContextVar[Callable[[str], Awaitable[bool]] | None] = ContextVar(
    "queue_request_active", default=None
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS service_queue_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    started_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS service_queue_uses_by_time
    ON service_queue_uses(started_at, user_id);
"""


class QueueError(Exception):
    """A missing, expired, mismatched or canceled ticket, safe to tell its owner."""

    def __init__(self, message: str = "排队已取消或过期，请重新排队", status: int = 410) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class _Ticket:
    id: str
    user_id: str
    kind: QueueKind
    resource: str
    sequence: int
    touched: datetime
    state: QueueState = "waiting"
    ready_at: datetime | None = None
    internal: bool = False
    event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


class Lease:
    """A reserved service slot. Start only after validation, release in a finally block."""

    def __init__(self, queue: "ServiceQueue | None" = None, ticket: _Ticket | None = None):
        self._queue = queue
        self._ticket = ticket
        self._started = False
        self._released = False

    async def start(self) -> None:
        if self._released:
            raise QueueError()
        if not self._started and self._queue is not None and self._ticket is not None:
            await self._queue._start(self._ticket)
        self._started = True

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        if self._queue is not None and self._ticket is not None:
            await self._queue._release(self._ticket)


class ServiceQueue:
    def __init__(
        self, db: Database, clock: Clock,
        is_admin: Callable[[str], Awaitable[bool]],
        active: Callable[[str], Awaitable[bool]],
    ) -> None:
        self._db, self._clock = db, clock
        self._is_admin, self._active = is_admin, active
        self._lock = asyncio.Lock()
        self._tickets: dict[str, _Ticket] = {}
        self._occupied: _Ticket | None = None
        self._sequence = 0
        self._closed = False
        self._sweeper: asyncio.Task | None = None
        db.prepare(lambda db: db.executescript(_SCHEMA))

    def _ensure_sweeper(self) -> None:
        if self._sweeper is None:
            self._sweeper = asyncio.create_task(self._sweep_loop())

    async def enqueue(self, user_id: str, kind: QueueKind, resource: str) -> dict:
        async with self._lock:
            self._ensure_open()
            if not await self._active(user_id):
                raise QueueError("用户已退出或被封禁", 403)
            self._ensure_sweeper()
            await self._dispatch()
            # One pending ticket per user and resource: retries cannot fill the queue.
            for ticket in self._tickets.values():
                if (ticket.user_id, ticket.kind, ticket.resource) == (user_id, kind, resource):
                    if ticket.state != "running":
                        ticket.touched = self._clock()
                        return await self._shown(ticket)
            pending = sum(
                t.user_id == user_id and not t.internal and t.state != "running"
                for t in self._tickets.values()
            )
            if pending >= MAX_PENDING_TICKETS:
                raise QueueError("排队中的操作太多，请稍后再试", 429)
            ticket = self._new(user_id, kind, resource)
            await self._dispatch()
            return await self._shown(ticket)

    async def status(self, ticket_id: str, user_id: str) -> dict:
        async with self._lock:
            await self._dispatch()
            ticket = self._find(ticket_id, user_id)
            if not await self._active(user_id):
                self._drop(ticket)
                await self._dispatch()
                raise QueueError("用户已退出或被封禁", 403)
            ticket.touched = self._clock()
            return await self._shown(ticket)

    async def cancel(self, ticket_id: str, user_id: str) -> None:
        async with self._lock:
            ticket = self._find(ticket_id, user_id)
            if ticket.state == "running":
                raise QueueError("服务已经开始，请在当前操作中结束", 409)
            await self._forfeit(ticket)
            await self._dispatch()

    async def acquire(
        self, user_id: str, kind: QueueKind, *, bypass: bool = False,
        resource: str | None = None, target: str | None = None,
    ) -> Lease:
        """Reserve a real operation. ``bypass`` is derived from its actual parsed keys.
        An explicit resource denotes background work, never the HTTP parent's ticket.
        """
        binding = queue_request.get() if resource is None else None
        ticket_id, bound_resource = binding or (None, resource or kind)
        if target is not None:
            bound_resource = f"{bound_resource}#{target}"
        ticket: _Ticket | None = None
        try:
            async with self._lock:
                self._ensure_open()
                if not await self._authorized(user_id, request=binding is not None):
                    raise QueueError("用户已退出或被封禁", 403)
                await self._dispatch()
                if ticket_id:
                    ticket = self._find(ticket_id, user_id)
                    if ticket.kind != kind or ticket.resource != bound_resource:
                        raise QueueError("排队票据与当前操作不匹配", 409)
                    if ticket.state != "ready":
                        raise QueueError("尚未轮到此操作，或票据已经使用", 409)
                    if bypass:
                        await self._forfeit(ticket)
                        await self._dispatch()
                        return Lease()
                elif bypass:
                    return Lease()
                else:
                    self._ensure_sweeper()
                    ticket = self._new(user_id, kind, bound_resource, internal=True)
                    ticket.task = asyncio.current_task()
                    await self._dispatch()
            assert ticket is not None
            while ticket.state != "ready":
                try:
                    await asyncio.wait_for(ticket.event.wait(), timeout=1)
                except TimeoutError:
                    disconnected = queue_client_gone.get() if binding else None
                    if disconnected is not None and await disconnected():
                        raise QueueError("排队已取消")
                async with self._lock:
                    if self._tickets.get(ticket.id) is not ticket:
                        raise QueueError()
            async with self._lock:
                if self._tickets.get(ticket.id) is not ticket or self._occupied is not ticket:
                    raise QueueError()
                if not await self._authorized(user_id, request=binding is not None):
                    raise QueueError("用户已退出或被封禁", 403)
                # Claimed: reservation TTL no longer applies; service code owns release.
                ticket.state = "running"
                return Lease(self, ticket)
        except BaseException:
            if ticket is not None and ticket.state != "running":
                async with self._lock:
                    await self._forfeit(ticket)
                    await self._dispatch()
            raise

    async def cancel_waiter(self, task: asyncio.Task) -> None:
        """Admissions shield database writes, but canceled queued requests must not linger."""
        async with self._lock:
            for ticket in list(self._tickets.values()):
                if ticket.task is task and ticket.state != "running":
                    self._drop(ticket)
            await self._dispatch()

    async def counts(self) -> dict[str, int]:
        return await self._db.read(_counts, (self._clock() - WINDOW).timestamp())

    async def _authorized(self, user_id: str, *, request: bool = True) -> bool:
        check_request = queue_request_active.get() if request else None
        return await self._active(user_id) and (
            check_request is None or await check_request(user_id)
        )

    async def _start(self, ticket: _Ticket) -> None:
        async with self._lock:
            if self._tickets.get(ticket.id) is not ticket or ticket.state != "running":
                raise QueueError()
            if not await self._authorized(ticket.user_id, request=ticket.kind != "photo"):
                raise QueueError("用户已退出或被封禁", 403)
            await self._db.write(_count, ticket.user_id, ticket.kind, self._clock().timestamp())

    async def _release(self, ticket: _Ticket) -> None:
        async with self._lock:
            self._drop(ticket)
            await self._dispatch()

    def _ensure_open(self) -> None:
        if self._closed:
            raise QueueError("服务正在重启，请稍后重新排队", 503)

    def _new(self, user_id: str, kind: QueueKind, resource: str, internal: bool = False) -> _Ticket:
        self._sequence += 1
        ticket = _Ticket(
            secrets.token_urlsafe(24), user_id, kind, resource, self._sequence,
            self._clock(), internal=internal,
        )
        self._tickets[ticket.id] = ticket
        return ticket

    def _find(self, ticket_id: str, user_id: str) -> _Ticket:
        ticket = self._tickets.get(ticket_id)
        if ticket is not None and ticket.user_id != user_id:
            raise QueueError("没有这张排队票据", 404)
        if ticket is None:
            raise QueueError()
        return ticket

    def _drop(self, ticket: _Ticket) -> None:
        if self._tickets.get(ticket.id) is ticket:
            del self._tickets[ticket.id]
        if self._occupied is ticket:
            self._occupied = None
        ticket.event.set()

    async def _forfeit(self, ticket: _Ticket) -> None:
        """Give a ticket up. A browser reservation that held the only slot and went unused
        counts as a use, so that reserving again and again cannot keep someone first."""
        held = ticket.state == "ready" and not ticket.internal
        current = self._tickets.get(ticket.id) is ticket
        self._drop(ticket)
        if held and current and await self._active(ticket.user_id):
            await self._db.write(_count, ticket.user_id, ticket.kind, self._clock().timestamp())

    async def _ordered(self) -> list[_Ticket]:
        counts = await self.counts()
        priorities = {}
        for ticket in list(self._tickets.values()):
            if ticket.state == "waiting":
                if not await self._active(ticket.user_id):
                    self._drop(ticket)
                    continue
                try:
                    admin = await self._is_admin(ticket.user_id)
                except LookupError:  # deleted between the active check and role lookup
                    self._drop(ticket)
                    continue
                priorities[ticket.id] = (
                    not admin,
                    counts.get(ticket.user_id, 0), ticket.sequence,
                )
        return sorted(
            (t for t in self._tickets.values() if t.state == "waiting"),
            key=lambda t: priorities[t.id],
        )

    async def _dispatch(self) -> None:
        now = self._clock()
        for ticket in list(self._tickets.values()):
            expired = (
                ticket.state == "waiting" and not ticket.internal and now - ticket.touched >= WAIT_TTL
            ) or (
                ticket.state == "ready" and not ticket.internal
                and ticket.ready_at is not None and now - ticket.ready_at >= READY_TTL
            )
            if expired:
                await self._forfeit(ticket)
            elif ticket.state != "running" and not await self._active(ticket.user_id):
                self._drop(ticket)
        if self._occupied is not None or self._closed:
            return
        for ticket in await self._ordered():
            if not await self._active(ticket.user_id):
                self._drop(ticket)
                continue
            ticket.state, ticket.ready_at = "ready", now
            self._occupied = ticket
            ticket.event.set()
            return

    async def _shown(self, ticket: _Ticket) -> dict:
        if self._tickets.get(ticket.id) is not ticket:
            raise QueueError()
        position = 0
        if ticket.state == "waiting":
            ordered = await self._ordered()
            found = next((i + 1 for i, t in enumerate(ordered) if t is ticket), None)
            if found is None:
                raise QueueError()
            position = found
        remaining = (
            READY_TTL - (self._clock() - (ticket.ready_at or self._clock()))
            if ticket.state == "ready" else WAIT_TTL
        )
        return {"id": ticket.id, "state": ticket.state, "position": position,
                "expires_in": max(0, int(remaining.total_seconds()))}

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(1)
                async with self._lock:
                    await self._dispatch()
        except asyncio.CancelledError:
            pass

    async def aclose(self) -> None:
        self._closed = True
        if self._sweeper is not None:
            self._sweeper.cancel()
            await self._sweeper
        async with self._lock:
            for ticket in list(self._tickets.values()):
                self._drop(ticket)


def _counts(db: sqlite3.Connection, since: float) -> dict[str, int]:
    return dict(db.execute(
        "SELECT user_id, COUNT(*) FROM service_queue_uses WHERE started_at > ? GROUP BY user_id",
        (since,),
    ))


def _count(db: sqlite3.Connection, user_id: str, kind: str, at: float) -> None:
    db.execute("DELETE FROM service_queue_uses WHERE started_at <= ?", (at - WINDOW.total_seconds(),))
    db.execute(
        "INSERT INTO service_queue_uses(user_id, kind, started_at) VALUES (?, ?, ?)",
        (user_id, kind, at),
    )
