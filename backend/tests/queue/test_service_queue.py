"""Deterministic scheduler tests using SQLite, a fake clock and no external services."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from eidolon.data_access import Database
from eidolon.service_queue import (
    MAX_PENDING_TICKETS, QueueError, QueueKind, ServiceQueue, queue_request, queue_request_active,
)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 4, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **delta: float):
        self.now += timedelta(**delta)


class Deployment:
    def __init__(self, path: Path):
        self.db = Database(path)
        self.db.prepare(lambda db: db.execute("CREATE TABLE users(id TEXT PRIMARY KEY)"))
        self.db.prepare(lambda db: db.executemany(
            "INSERT INTO users VALUES (?)", [(u,) for u in ("admin", "a", "b", "c")]
        ))
        self.clock = Clock()
        self.admins = {"admin"}
        self.active = {"admin", "a", "b", "c"}
        self.queue = self.new_queue()

    def new_queue(self):
        async def admin(user: str):
            return user in self.admins

        async def active(user: str):
            return user in self.active

        return ServiceQueue(self.db, self.clock, admin, active)

    async def seed(self, user: str, count: int):
        for _ in range(count):
            lease = await self.queue.acquire(user, "turn")
            await lease.start()
            await lease.release()

    async def claim(
        self, shown: dict, user: str, kind: QueueKind = "turn", resource="/api/x", **kwargs
    ):
        token = queue_request.set((shown["id"], resource))
        try:
            return await self.queue.acquire(user, kind, **kwargs)
        finally:
            queue_request.reset(token)


@pytest.fixture
async def deployment(tmp_path: Path):
    deployment = Deployment(tmp_path / "queue.db")
    yield deployment
    await deployment.queue.aclose()
    await deployment.db.close()


async def test_low_usage_arrival_inserts_ahead_of_existing_waiter(deployment: Deployment):
    d = deployment
    await d.seed("a", 3)
    held = await d.queue.acquire("c", "call")
    high = await d.queue.enqueue("a", "turn", "/api/x")
    low = await d.queue.enqueue("b", "turn", "/api/x")
    assert (await d.queue.status(low["id"], "b"))["position"] == 1
    assert (await d.queue.status(high["id"], "a"))["position"] == 2
    await held.release()
    assert (await d.queue.status(low["id"], "b"))["state"] == "ready"
    assert (await d.queue.status(high["id"], "a"))["state"] == "waiting"


async def test_admin_is_first_even_with_more_recent_uses(deployment: Deployment):
    d = deployment
    await d.seed("admin", 5)
    held = await d.queue.acquire("c", "turn")
    regular = await d.queue.enqueue("a", "turn", "/api/x")
    admin = await d.queue.enqueue("admin", "turn", "/api/x")
    await held.release()
    assert (await d.queue.status(admin["id"], "admin"))["state"] == "ready"
    assert (await d.queue.status(regular["id"], "a"))["state"] == "waiting"


async def test_equal_usage_is_fifo_and_active_operation_is_never_preempted(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    await held.start()
    first = await d.queue.enqueue("a", "turn", "/api/x")
    second = await d.queue.enqueue("b", "turn", "/api/x")
    assert first["state"] == second["state"] == "waiting"
    assert (await d.queue.status(first["id"], "a"))["position"] == 1
    assert (await d.queue.status(second["id"], "b"))["position"] == 2
    assert await d.queue.counts() == {"c": 1}
    await held.release()
    assert (await d.queue.status(first["id"], "a"))["state"] == "ready"


async def test_uses_expire_at_exactly_six_hours_and_survive_a_restart(deployment: Deployment):
    d = deployment
    await d.seed("a", 2)
    await d.queue.aclose()
    d.queue = d.new_queue()
    assert await d.queue.counts() == {"a": 2}
    d.clock.advance(hours=6)
    assert await d.queue.counts() == {}


async def test_reserving_canceling_and_being_refused_records_no_use(deployment: Deployment):
    d = deployment
    ticket = await d.queue.enqueue("a", "turn", "/api/x")
    lease = await d.claim(ticket, "a")
    await lease.release()  # failed validation before upstream service began
    assert await d.queue.counts() == {}
    held = await d.queue.acquire("c", "turn")
    ticket = await d.queue.enqueue("b", "turn", "/api/x")
    assert ticket["state"] == "waiting"
    await d.queue.cancel(ticket["id"], "b")
    assert await d.queue.counts() == {}
    await held.release()


async def test_start_and_release_are_idempotent_and_upstream_failure_keeps_use(deployment: Deployment):
    d = deployment
    lease = await d.queue.acquire("a", "turn")
    await lease.start()
    await lease.start()
    try:
        raise RuntimeError("upstream failed")
    except RuntimeError:
        await lease.release()
        await lease.release()
    assert await d.queue.counts() == {"a": 1}
    assert (await d.queue.enqueue("b", "turn", "/api/x"))["state"] == "ready"


async def test_own_keys_do_not_wait_or_count_while_shared_call_is_running(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "call")
    own = await d.queue.acquire("a", "turn", bypass=True)
    await own.start()
    await own.release()
    assert await d.queue.counts() == {}
    assert (await d.queue.enqueue("b", "turn", "/api/x"))["state"] == "waiting"
    await held.release()


async def test_canceled_internal_waiter_cannot_later_run_or_hold_slot(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    waiting = asyncio.create_task(d.queue.acquire("a", "turn"))
    await asyncio.sleep(0.01)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    next_ticket = await d.queue.enqueue("b", "turn", "/api/x")
    await held.release()
    assert (await d.queue.status(next_ticket["id"], "b"))["state"] == "ready"
    assert await d.queue.counts() == {}


async def test_ready_reservation_expires_after_fifteen_seconds(deployment: Deployment):
    d = deployment
    expired = await d.queue.enqueue("a", "turn", "/api/x")
    next_ticket = await d.queue.enqueue("b", "turn", "/api/x")
    d.clock.advance(seconds=15)
    assert (await d.queue.status(next_ticket["id"], "b"))["state"] == "ready"
    with pytest.raises(QueueError) as error:
        await d.queue.status(expired["id"], "a")
    assert error.value.status == 410


async def test_waiting_ticket_needs_a_heartbeat_and_polling_renews_it(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    renewed = await d.queue.enqueue("a", "turn", "/api/x")
    expired = await d.queue.enqueue("b", "turn", "/api/x")
    d.clock.advance(seconds=40)
    await d.queue.status(renewed["id"], "a")
    d.clock.advance(seconds=20)
    await d.queue.status(renewed["id"], "a")
    with pytest.raises(QueueError):
        await d.queue.status(expired["id"], "b")
    await held.release()


async def test_tickets_are_bound_to_owner_kind_path_and_call_target(deployment: Deployment):
    d = deployment
    ticket = await d.queue.enqueue("a", "turn", "/api/x")
    with pytest.raises(QueueError) as error:
        await d.claim(ticket, "b")
    assert error.value.status == 404
    # A foreign claim never discards the legitimate owner's reservation.
    lease = await d.claim(ticket, "a")
    await lease.release()
    ticket = await d.queue.enqueue("a", "turn", "/api/x")
    with pytest.raises(QueueError) as error:
        await d.claim(ticket, "a", resource="/api/other")
    assert error.value.status == 409
    ticket = await d.queue.enqueue("a", "call", "/api/offer#conversation-1")
    with pytest.raises(QueueError):
        await d.claim(ticket, "a", "call", "/api/offer", target="conversation-2")


async def test_replayed_ticket_cannot_release_a_running_operation(deployment: Deployment):
    d = deployment
    ticket = await d.queue.enqueue("a", "turn", "/api/x")
    lease = await d.claim(ticket, "a")
    await lease.start()
    with pytest.raises(QueueError):
        await d.claim(ticket, "a")
    assert (await d.queue.enqueue("b", "turn", "/api/x"))["state"] == "waiting"
    await lease.release()


async def test_banned_while_waiting_is_discarded_and_never_counted(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    banned = await d.queue.enqueue("a", "turn", "/api/x")
    next_ticket = await d.queue.enqueue("b", "turn", "/api/x")
    d.active.remove("a")
    await held.release()
    assert (await d.queue.status(next_ticket["id"], "b"))["state"] == "ready"
    with pytest.raises(QueueError):
        await d.queue.status(banned["id"], "a")
    assert await d.queue.counts() == {}


async def test_shutdown_wakes_pending_internal_waiters_and_rejects_new_requests(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    waiting = asyncio.create_task(d.queue.acquire("a", "turn"))
    await asyncio.sleep(0.01)
    await d.queue.aclose()
    with pytest.raises(QueueError):
        await waiting
    with pytest.raises(QueueError) as error:
        await d.queue.enqueue("a", "turn", "/api/x")
    assert error.value.status == 503
    await held.release()


async def test_an_async_photo_ignores_its_parents_consumed_ticket_and_does_not_deadlock(
    deployment: Deployment,
):
    d = deployment
    ticket = await d.queue.enqueue("a", "turn", "/api/x")
    parent = await d.claim(ticket, "a")
    await parent.start()
    binding = queue_request.set((ticket["id"], "/api/x"))
    try:
        photo = asyncio.create_task(d.queue.acquire("a", "photo", resource="photo-1"))
    finally:
        queue_request.reset(binding)
    await asyncio.sleep(0.01)
    assert not photo.done()
    await parent.release()
    image = await asyncio.wait_for(photo, timeout=1)
    await image.start()
    await image.release()
    assert await d.queue.counts() == {"a": 2}


async def test_logout_after_enqueue_is_rechecked_before_claim_and_before_start(deployment: Deployment):
    d = deployment
    ticket = await d.queue.enqueue("a", "turn", "/api/x")
    authenticated = True

    async def signed_in(user: str):
        return authenticated

    active = queue_request_active.set(signed_in)
    try:
        lease = await d.claim(ticket, "a")
        authenticated = False
        with pytest.raises(QueueError) as error:
            await lease.start()
        assert error.value.status == 403
        await lease.release()
        assert await d.queue.counts() == {}
    finally:
        queue_request_active.reset(active)


async def test_canceling_a_shielded_admission_wakes_its_waiter_without_taking_a_use(
    deployment: Deployment,
):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    pending = asyncio.create_task(d.queue.acquire("a", "turn"))
    await asyncio.sleep(0.01)
    await d.queue.cancel_waiter(pending)
    with pytest.raises(QueueError):
        await pending
    await held.release()
    assert await d.queue.counts() == {}


async def test_six_hour_priority_is_recomputed_when_a_use_ages_out(deployment: Deployment):
    d = deployment
    await d.seed("a", 2)
    d.clock.advance(hours=5, minutes=59, seconds=59)
    held = await d.queue.acquire("c", "call")
    first = await d.queue.enqueue("a", "turn", "/api/x")
    second = await d.queue.enqueue("b", "turn", "/api/x")
    assert (await d.queue.status(second["id"], "b"))["position"] == 1
    d.clock.advance(seconds=1)
    assert (await d.queue.status(first["id"], "a"))["position"] == 1
    await held.release()
    assert (await d.queue.status(first["id"], "a"))["state"] == "ready"


async def test_deleted_user_role_lookup_cannot_break_dispatch_or_release(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    deleted = await d.queue.enqueue("a", "turn", "/api/x")
    next_ticket = await d.queue.enqueue("b", "turn", "/api/x")

    async def role_after_deletion(user: str):
        if user == "a":
            raise LookupError("deleted between active check and role lookup")
        return False

    d.queue._is_admin = role_after_deletion
    await held.release()
    assert (await d.queue.status(next_ticket["id"], "b"))["state"] == "ready"
    with pytest.raises(QueueError):
        await d.queue.status(deleted["id"], "a")


async def test_a_reservation_given_up_after_reaching_the_slot_counts_as_a_use(
    deployment: Deployment,
):
    d = deployment
    expired = await d.queue.enqueue("a", "turn", "/api/x")
    assert expired["state"] == "ready"
    d.clock.advance(seconds=15)
    canceled = await d.queue.enqueue("b", "turn", "/api/x")
    assert canceled["state"] == "ready"
    assert await d.queue.counts() == {"a": 1}
    await d.queue.cancel(canceled["id"], "b")
    assert await d.queue.counts() == {"a": 1, "b": 1}
    bypassed = await d.queue.enqueue("c", "turn", "/api/x")
    await d.claim(bypassed, "c", bypass=True)
    assert await d.queue.counts() == {"a": 1, "b": 1, "c": 1}
    mismatched = await d.queue.enqueue("admin", "turn", "/api/x")
    with pytest.raises(QueueError):
        await d.claim(mismatched, "admin", resource="/api/other")
    assert (await d.queue.counts())["admin"] == 1


async def test_repeatedly_abandoning_reservations_loses_priority(deployment: Deployment):
    d = deployment
    first = await d.queue.enqueue("a", "turn", "/api/x")
    assert first["state"] == "ready"
    d.clock.advance(seconds=15)
    held = await d.queue.acquire("c", "turn")
    # "a" abandoned one reservation, so "b" goes first though it arrived later.
    again = await d.queue.enqueue("a", "turn", "/api/x")
    honest = await d.queue.enqueue("b", "turn", "/api/x")
    assert (await d.queue.status(honest["id"], "b"))["position"] == 1
    assert (await d.queue.status(again["id"], "a"))["position"] == 2
    await held.release()


async def test_one_user_cannot_hold_more_than_the_pending_ticket_limit(deployment: Deployment):
    d = deployment
    held = await d.queue.acquire("c", "turn")
    tickets = [
        await d.queue.enqueue("a", "bar", f"/api/bar/visits/{i}/serves")
        for i in range(MAX_PENDING_TICKETS)
    ]
    # Retrying a pending resource is no new ticket; a new resource over the limit is refused.
    assert (await d.queue.enqueue("a", "bar", "/api/bar/visits/0/serves"))["id"] == tickets[0]["id"]
    with pytest.raises(QueueError) as error:
        await d.queue.enqueue("a", "bar", "/api/bar/visits/over/serves")
    assert error.value.status == 429
    assert (await d.queue.enqueue("b", "turn", "/api/x"))["state"] == "waiting"
    await d.queue.cancel(tickets[0]["id"], "a")
    assert (await d.queue.enqueue("a", "bar", "/api/bar/visits/over/serves"))["state"] == "waiting"
    await held.release()


async def test_a_deleted_users_expired_reservation_records_nothing(deployment: Deployment):
    d = deployment
    expired = await d.queue.enqueue("a", "turn", "/api/x")
    assert expired["state"] == "ready"
    d.active.discard("a")
    d.clock.advance(seconds=15)
    assert (await d.queue.enqueue("b", "turn", "/api/x"))["state"] == "ready"
    assert await d.queue.counts() == {}
