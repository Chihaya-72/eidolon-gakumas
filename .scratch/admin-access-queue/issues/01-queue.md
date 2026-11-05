# Backend fair service queue
Status: done

Read docs/agents/implementing.md. User explicitly forbids Git staging, commits, pushes or PRs. Preserve all pre-existing modifications. Implement backend fair service queue from approved plan. Own backend/src/eidolon/service_queue.py (new), queue_api.py (new), admission.py, call.py, bar.py, read_aloud.py, photos.py and queue tests. Do not edit app.py, assembly.py, accounts.py, store.py, config.py, admin APIs, frontend or deployment files; send precise integration instructions for root.

Queue requirements: single shared operation at once across deployment admin APIs; admin first, rolling six-hour admitted operation count ascending, stable FIFO. Recompute priorities at dispatch, never preempt. Counts persisted separate from hourly quota (no new count while only queued, canceled, refused; upstream failure after start counts). Use main services source: text/bar own LLM skip; call requires own llm/stt/tts all to skip; read aloud own tts skip; photo own image skip. Auxiliary judge/retrieval do not affect skip. Whole call holds lease until settlement; each bar generation takes/releases (not idle drink time); async photos independently queue after parent text/call releases (no deadlock). Revalidate user active, cooldown/availability/limits before service. Add secure user/operation/resource-bound queue ticket API POST /api/queue, GET/DELETE /api/queue/{id}, optional X-Queue-Ticket consumed on actual operation after verifying request sourcing; no ticket fallback must queue server-side. Browser polls two seconds, waiting ticket TTL60s renewed on poll, ready reservation TTL15s; cleanup on disconnect, cancellation, timeout, shutdown. No secrets in ticket. Ticket claims may only skip queue when actual keys validate. Add integration hooks not cyclic imports: accept callbacks for admin/user validation and DB. Root handles central lifecycle registration.

Tell root early exact frontend/API contract and injection signatures. Write unit/integration tests for ordering, six-hour boundary, persistence, cancellation/exceptions, lease release, stale/replayed/mismatched ticket, BYOK and core paths. Do not run heavy full tests/build; targeted tests okay. Keep issue Comments updated; user wants full implementation not just plan.

## Comments

### 实现说明（票 01）

Implemented ServiceQueue with SQLite service_queue_uses, admin/rolling-six-hour/FIFO dynamic priority, 60-second waiting heartbeat and 15-second ready reservation, idempotent start/release, user and session revalidation, disconnect/cancellation/shutdown cleanup. Queue HTTP API binds owner/kind/exact path and call conversation target, consumes X-Queue-Ticket through middleware context, and validates actual main-service key source in operation methods. Unticketed requests use the same scheduler.

Admissions carries text/call leases to settlement, bar detaches first-entry lease and releases each reply independently, read-aloud releases in finally, photos explicitly ignore inherited parent tickets and wait independently. Deferred photos receive the normal 90-second upstream budget after shared-slot acquisition; dropped photos skip before usage is taken. Existing bar visits continue after new-entry feature switch is disabled, preserving existing behavior.

Validation: 39 passed in queue/admission/read-aloud batch. Final focused batch 28 passed (18 core + 7 HTTP + shared/own-image concurrency + existing bar-disable behavior). Added one additional deleted-user role race core case after that batch for central affected-tests. Ruff and focused Pyright on all queue-owned modules/tests passed. Earlier broad batch 45 passed with obsolete photo concurrency expectation and bar-disable regression both corrected; remaining RTC sandbox test is confirmed passing with network permission by root. No Git staging, commits, pushes or PRs performed. Root is performing central affected-tests and independent code review.

### 审查后的修复（票 01）

Fixed both review findings: bar replacement/drawing/first-call setup is covered by new-admission cleanup on ordinary error and cancellation, including removal from active visits, quota refund and queue-lease release. Initial visit admission now reserves only; the six-hour use is recorded by _called after bar validation and replacement succeeds. Added three regressions covering replacement error, replacement cancellation and disabling the bar while waiting.

Adjusted obsolete concurrency expectations: photo-service FIFO and prompt tests use BYOK parents where they need independent model/image progress; per-image-key timeout still tests its own queue; canceled shared photos now assert no generation/quota use, while an already-started shared photo from a BYOK parent remains charged after its parent disconnects. Added explicit shared-call photo deferral coverage, retained immediate photo status/failure tests on fully BYOK call services, and preserved own-image behavior. The leave_turn ASGI helper accepts optional own_keys to drive these source-specific cases. Concurrent-call monkeypatch forwards the new optional admission keyword hooks.

Validation after review: test_bar_queue + test_photo_failures + test_photo_limits: 28 passed in 4.41s; test_call_photos + test_concurrent_calls with local loopback permission: 11 passed in 5.07s. Ruff and focused Pyright for every changed source/test passed (0 errors/warnings). No remaining known queue regressions from the central failure list assigned to this ticket. Git remains unstaged and uncommitted.

### 最终取消回归接缝

The canceled-call records test blocked before actual admission and therefore expected an activity record for a request now correctly canceled before queue service. Moved its synchronization barrier after durable admission, retaining the intended guarantee that a canceled admitted call settles its existing activity/quota. Isolated WebRTC-loopback test passed in 0.25s; Ruff/Pyright clean. The separate canceled-while-queued tests still assert no use is started.

### 通话容量与服务队列

Shared-key calls no longer fail the concurrency preflight while another shared call occupies the queue. Duplicate placement by the same user still fails immediately; true call capacity is rechecked after the fair queue admits the operation. _Placing.admitted distinguishes callers actually admitted from callers only waiting, so pending queue requests cannot exhaust the hard cap. Fully self-funded calls retain immediate hard-cap rejection. Adapted the old cap tests to fully self-funded calls and added a real WebRTC regression proving a shared call waits and then connects with concurrent_calls=1.

Focused final verification (concurrent_calls, admission, core queue, queue HTTP and the canceled-admitted-call case): 45 passed in 2.09s with loopback permission. Ruff and focused Pyright clean. No further code edits pending.
