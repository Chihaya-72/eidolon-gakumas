"""First-user privilege is atomic, migrates once and is shared by all admin surfaces."""

import asyncio
import sqlite3
from dataclasses import replace
from pathlib import Path

from eidolon.accounts import is_admin
from eidolon.config import Settings
from eidolon.data_access import Database
from eidolon.store import SignInMethod, Store


async def test_concurrent_registration_grants_only_one_persisted_administrator(tmp_path: Path, settings: Settings):
    db = Database(tmp_path / "users.db")
    try:
        store = Store(db)
        users = await asyncio.gather(*(
            store.create_user_signing_in_with(str(i), SignInMethod("google", str(i), str(i), None, str(i)))
            for i in range(8)
        ))
        assert sum(bool(user.is_admin) for user in users) == 1
        assert users[0].is_admin
        assert await is_admin(store, settings, users[0].id)
        assert not await is_admin(store, settings, users[1].id)
        listed = replace(settings, admins=frozenset({("google", "1")}))
        assert await is_admin(store, listed, users[1].id)
        await store.delete_user(users[0].id)
        assert not (await store.create_user("later")).is_admin
    finally:
        await db.close()


async def test_old_database_promotes_earliest_once_and_does_not_repromote_on_open(tmp_path: Path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as legacy:
        legacy.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)")
        legacy.executemany("INSERT INTO users VALUES (?, ?, ?)", [("later", "Later", "2025-02-01"), ("first", "First", "2025-01-01")])
    db = Database(path)
    try:
        store = Store(db)
        assert (await store.get_user("first")).is_admin
        assert not (await store.get_user("later")).is_admin
        await db.write(lambda connection: connection.execute("UPDATE users SET is_admin = 0"))
        reopened = Store(db)
        assert not (await reopened.get_user("first")).is_admin
    finally:
        await db.close()
