"""Deployment-wide password gate, independent of sign-in and account bans.

Only password hashes and hashed browser/IP identifiers are kept. All failed-attempt
updates and bans are made in one writer transaction, including concurrent attempts.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import secrets
import sqlite3
from datetime import timedelta

from fastapi import Request

from eidolon.clock import Clock
from eidolon.config import Settings
from eidolon.data_access import Database

BROWSER_COOKIE = "eidolon_visitor"
ACCESS_COOKIE = "eidolon_access"
LIFETIME = timedelta(days=30)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    password_hash TEXT,
    version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS access_attempts (
    scope TEXT NOT NULL,
    identifier TEXT NOT NULL,
    failures INTEGER NOT NULL,
    PRIMARY KEY (scope, identifier)
);
CREATE TABLE IF NOT EXISTS access_bans (
    id TEXT PRIMARY KEY,
    browser_key TEXT NOT NULL,
    ip_key TEXT NOT NULL,
    banned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS access_bans_browser ON access_bans(browser_key);
CREATE INDEX IF NOT EXISTS access_bans_ip ON access_bans(ip_key);
CREATE TABLE IF NOT EXISTS access_grants (
    token_hash TEXT PRIMARY KEY,
    browser_key TEXT NOT NULL,
    version TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


def client_ip(request: Request, settings: Settings) -> str:
    """Only loopback proxies on a public deployment may supply Caddy's overwritten header."""
    peer = request.client.host if request.client else "127.0.0.1"
    try:
        trusted = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        trusted = False
    forwarded = request.headers.get("x-eidolon-client-ip")
    if settings.domain and trusted and forwarded:
        try:
            return ipaddress.ip_address(forwarded).compressed
        except ValueError:
            pass
    try:
        return ipaddress.ip_address(peer).compressed
    except ValueError:
        # ASGI tests may use a named host; do not trust arbitrary forwarding headers.
        return peer


def _digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=67108864)


def _hashed(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{_digest(password, salt).hex()}"


def _matches(password: str, encoded: str | None) -> bool:
    if encoded is None:
        return False
    salt, digest = encoded.split(":")
    return hmac.compare_digest(_digest(password, bytes.fromhex(salt)).hex(), digest)


def _open(db: sqlite3.Connection) -> None:
    db.executescript(_SCHEMA)
    db.execute(
        "INSERT OR IGNORE INTO access_settings (id, version) VALUES (1, ?)",
        (secrets.token_hex(16),),
    )


def _config(db: sqlite3.Connection) -> tuple[bool, str | None, str]:
    enabled, password_hash, version = db.execute(
        "SELECT enabled, password_hash, version FROM access_settings WHERE id = 1"
    ).fetchone()
    return bool(enabled), password_hash, version


def _banned(db: sqlite3.Connection, browser: str, ip: str) -> bool:
    return db.execute(
        "SELECT 1 FROM access_bans WHERE browser_key = ? OR ip_key = ? LIMIT 1", (browser, ip)
    ).fetchone() is not None


class AccessGate:
    def __init__(self, db: Database, clock: Clock, secret_key: str | None = None) -> None:
        self._db, self._clock = db, clock
        self._key = (secret_key or "eidolon access identifiers").encode()
        # A single scrypt at a time bounds memory and protects the shared DB/audio executor.
        self._verifying = asyncio.Semaphore(1)
        db.prepare(_open)

    def identifier(self, scope: str, value: str) -> str:
        return hmac.new(self._key, f"{scope}:{value}".encode(), hashlib.sha256).hexdigest()

    async def state(self, browser: str, ip: str, token: str | None) -> dict:
        return await self._db.read(
            self._state, self.identifier("browser", browser), self.identifier("ip", ip), token,
        )

    def _state(self, db: sqlite3.Connection, browser: str, ip: str, token: str | None) -> dict:
        enabled, _, version = _config(db)
        banned = enabled and _banned(db, browser, ip)
        passed = not enabled
        if enabled and not banned and token:
            passed = db.execute(
                "SELECT 1 FROM access_grants WHERE token_hash = ? AND browser_key = ?"
                " AND version = ? AND expires_at > ?",
                (hashlib.sha256(token.encode()).hexdigest(), browser, version,
                 self._clock().timestamp()),
            ).fetchone() is not None
        return {"enabled": enabled, "passed": passed, "banned": banned}

    async def verify(self, password: str, browser: str, ip: str) -> tuple[dict, str | None]:
        async with self._verifying:
            browser, ip = self.identifier("browser", browser), self.identifier("ip", ip)
            state = await self._db.read(self._state, browser, ip, None)
            if state["banned"] or not state["enabled"]:
                return state, None
            expected = await self._db.read(_config)
            hashing = asyncio.create_task(asyncio.to_thread(_matches, password, expected[1]))
            try:
                matches = await asyncio.shield(hashing)
            except asyncio.CancelledError:
                # A disconnected request cannot release the memory budget while its thread runs.
                await hashing
                raise
            token = secrets.token_urlsafe(32)
            return await self._db.write(self._verify, browser, ip, expected, matches, token)

    def _verify(
        self, db: sqlite3.Connection, browser: str, ip: str,
        expected: tuple[bool, str | None, str], matches: bool, token: str,
    ) -> tuple[dict, str | None]:
        state = self._state(db, browser, ip, None)
        if state["banned"] or not state["enabled"]:
            return state, None
        if _config(db) != expected:
            return state | {"changed": True}, None
        if matches:
            db.execute(
                "DELETE FROM access_attempts WHERE (scope = 'browser' AND identifier = ?)"
                " OR (scope = 'ip' AND identifier = ?)", (browser, ip),
            )
            self._grant(db, browser, token, expected[2])
            return state | {"passed": True}, token
        failures = []
        for scope, identifier in (("browser", browser), ("ip", ip)):
            db.execute(
                "INSERT INTO access_attempts VALUES (?, ?, 1)"
                " ON CONFLICT(scope, identifier) DO UPDATE SET failures = failures + 1",
                (scope, identifier),
            )
            failures.append(db.execute(
                "SELECT failures FROM access_attempts WHERE scope = ? AND identifier = ?",
                (scope, identifier),
            ).fetchone()[0])
        banned = max(failures) >= 3
        if banned:
            db.execute(
                "INSERT INTO access_bans VALUES (?, ?, ?, ?)",
                (secrets.token_hex(16), browser, ip, self._clock().isoformat()),
            )
        return state | {"banned": banned, "remaining": max(0, 3 - max(failures))}, None

    def _grant(self, db: sqlite3.Connection, browser: str, token: str, version: str) -> None:
        db.execute("DELETE FROM access_grants WHERE expires_at <= ?", (self._clock().timestamp(),))
        db.execute(
            "INSERT INTO access_grants VALUES (?, ?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), browser, version,
             (self._clock() + LIFETIME).timestamp()),
        )

    async def settings(self) -> dict:
        enabled, password_hash, _ = await self._db.read(_config)
        return {"enabled": enabled, "password_set": password_hash is not None}

    async def save(self, enabled: bool, password: str | None, browser: str) -> tuple[dict, str | None]:
        if password is not None and not 8 <= len(password) <= 128:
            raise ValueError("访问密码需要 8 至 128 个字符")
        hashed = await asyncio.to_thread(_hashed, password) if password is not None else None
        return await self._db.write(self._save, enabled, hashed, self.identifier("browser", browser))

    def _save(
        self, db: sqlite3.Connection, enabled: bool, hashed: str | None, browser: str,
    ) -> tuple[dict, str | None]:
        _, existing, _ = _config(db)
        hashed = hashed or existing
        if enabled and hashed is None:
            raise ValueError("开启密码访问前请先设置密码")
        version = secrets.token_hex(16)
        db.execute(
            "UPDATE access_settings SET enabled = ?, password_hash = ?, version = ? WHERE id = 1",
            (int(enabled), hashed, version),
        )
        db.execute("DELETE FROM access_grants")
        token = secrets.token_urlsafe(32) if enabled else None
        if token:
            self._grant(db, browser, token, version)
        return {"enabled": enabled, "password_set": hashed is not None}, token

    async def bans(self) -> list[dict]:
        def read(db: sqlite3.Connection) -> list[dict]:
            return [dict(zip(("id", "browser", "ip", "banned_at"), row)) for row in db.execute(
                "SELECT id, substr(browser_key, 1, 12), substr(ip_key, 1, 12), banned_at"
                " FROM access_bans ORDER BY banned_at DESC, rowid DESC"
            )]
        return await self._db.read(read)

    async def unban(self, ban_id: str | None = None) -> None:
        def write(db: sqlite3.Connection) -> None:
            rows = db.execute(
                "SELECT browser_key, ip_key FROM access_bans" + (" WHERE id = ?" if ban_id else ""),
                (ban_id,) if ban_id else (),
            ).fetchall()
            for browser, ip in rows:
                db.execute("DELETE FROM access_bans WHERE browser_key = ? OR ip_key = ?", (browser, ip))
                db.execute(
                    "DELETE FROM access_attempts WHERE (scope = 'browser' AND identifier = ?)"
                    " OR (scope = 'ip' AND identifier = ?)", (browser, ip),
                )
        await self._db.write(write)

    async def disable(self) -> None:
        await self.save(False, None, "server-recovery")
