from typing import Literal

from diane.storage.sessions_register import SessionsRegisterConfig


class SQLiteSessionsRegisterConfig(SessionsRegisterConfig):
    """An SQLite sessions register configuration."""

    backend: Literal['sqlite'] = 'sqlite'
