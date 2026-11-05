"""Signing up and in with a user name and a password (`EIDOLON_PASSWORD_LOGIN=1`).

A name is letters and digits of any script and `_`, nothing else, so it cannot pretend to
be something else on a page: compared after NFKC and case folding (`username_key`), so
that `Ａlice` and `alice` are one name. One exception, only as a name is signed up: the
suffix `+admin` asks for the deployment's one claim of admin (`admin_bootstrap`, GLOSSARY.md
「注册方式」). It is not part of the name, and once claimed it is refused as any other `+` is.

Passwords are kept only as scrypt hashes. Hashing runs off the event loop, a few at a time,
as it takes 32 MiB and most of 100 ms. An unknown name costs what a wrong password does, and
gets the same answer. Failures are counted per address and name in memory (`AttemptLimit`),
as the server is one process; a restart forgets them.
"""

import asyncio
import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from eidolon.clock import Clock

ADMIN_SUFFIX = "+admin"
MIN_NAME = 2
MAX_NAME = 20
MIN_PASSWORD = 8
MAX_PASSWORD = 128
NAME_RULE = f"名称要 {MIN_NAME} 到 {MAX_NAME} 个字，只能用文字、数字和下划线"
PASSWORD_RULE = f"密码要 {MIN_PASSWORD} 到 {MAX_PASSWORD} 个字符，并且不能和名称相同"
RESERVED_NAMES = frozenset(
    {"admin", "administrator", "root", "system", "guest", "管理员", "官方", "游客"}
)
"""Names only the one claiming admin may take: no one else can pose as the deployer."""

_N, _R, _P = 32768, 8, 1
_MAXMEM = 67108864


class BadName(Exception):
    """The name breaks `NAME_RULE`."""


@dataclass(frozen=True)
class WantedName:
    name: str
    """As shown, without the suffix."""
    key: str
    """What makes it unique."""
    claims_admin: bool


def username_key(name: str) -> str:
    return unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", name).casefold())


def _checked(name: str) -> str:
    if not MIN_NAME <= len(name) <= MAX_NAME or not all(c.isalnum() or c == "_" for c in name):
        raise BadName(NAME_RULE)
    return name


def wanted_name(raw: str) -> WantedName:
    """The name someone signs up with. Raises BadName."""
    claims_admin = raw.endswith(ADMIN_SUFFIX)
    name = unicodedata.normalize("NFKC", raw.removesuffix(ADMIN_SUFFIX))
    key = username_key(_checked(name))
    if key in RESERVED_NAMES and not claims_admin:
        raise BadName("这个名称不能使用")
    return WantedName(name, key, claims_admin)


def signing_in_key(raw: str) -> str | None:
    """The key of the name someone signs in with, the suffix forgiven, as the one who claimed
    admin may well type it again; None if it could never have been signed up with."""
    try:
        return username_key(_checked(unicodedata.normalize("NFKC", raw.removesuffix(ADMIN_SUFFIX))))
    except BadName:
        return None


def password_problem(password: str, key: str) -> str | None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD or username_key(password) == key:
        return PASSWORD_RULE
    return None


def _digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM)


def _hashed(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{_digest(password, salt).hex()}"


_NO_USER = f"{'0' * 32}:{'0' * 128}"
"""Compared against for a name no one has: nothing hashes to it."""


def _matches(password: str, encoded: str | None) -> bool:
    salt, digest = (encoded or _NO_USER).split(":")
    return hmac.compare_digest(_digest(password, bytes.fromhex(salt)).hex(), digest) and (
        encoded is not None
    )


class Hasher:
    """Hashes off the event loop, at most `AT_ONCE` at a time so that a flood of sign-ins
    cannot take the server's memory."""

    AT_ONCE = 2

    def __init__(self) -> None:
        self._hashing = asyncio.Semaphore(self.AT_ONCE)

    async def hashed(self, password: str) -> str:
        async with self._hashing:
            return await asyncio.to_thread(_hashed, password)

    async def matches(self, password: str, encoded: str | None) -> bool:
        async with self._hashing:
            return await asyncio.to_thread(_matches, password, encoded)


class AttemptLimit:
    """How many times each key may count within `window`; kept in memory."""

    MAX_KEYS = 50_000

    def __init__(self, clock: Clock, times: int, window: timedelta) -> None:
        self._clock, self._times, self._window = clock, times, window
        self._seen: dict[str, list[datetime]] = {}

    def _recent(self, key: str) -> list[datetime]:
        now = self._clock()
        recent = [t for t in self._seen.get(key, []) if now - t < self._window]
        if recent:
            self._seen[key] = recent
        else:
            self._seen.pop(key, None)
        return recent

    def wait(self, key: str) -> int | None:
        """In how many seconds `key` may try again; None if it may now."""
        recent = self._recent(key)
        if len(recent) < self._times:
            return None
        return max(1, int((recent[0] + self._window - self._clock()).total_seconds()) + 1)

    def count(self, key: str) -> None:
        if len(self._seen) >= self.MAX_KEYS:
            for old in list(self._seen):
                self._recent(old)
            if len(self._seen) >= self.MAX_KEYS:
                self._seen.clear()
        self._seen.setdefault(key, []).append(self._clock())

    def forget(self, key: str) -> None:
        self._seen.pop(key, None)
