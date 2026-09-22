from typing import Annotated

from pydantic import Field

from .activities_register import ActivitiesRegister, ActivitiesRegisterConfig
from .entries_register import EntriesRegister, EntriesRegisterConfig
from .markdown_activities_register import (
    MarkdownActivitiesRegister,
    MarkdownActivitiesRegisterConfig,
)
from .markdown_entries_register import (
    MarkdownEntriesRegister,
    MarkdownEntriesRegisterConfig,
)
from .markdown_sessions_register import MarkdownSessionsRegisterConfig
from .sessions_register import SessionsRegisterConfig
from .sqlite_activities_register import (
    SQLiteActivitiesRegister,
    SQLiteActivitiesRegisterConfig,
)
from .sqlite_entries_register import (
    SQLiteEntriesRegister,
    SQLiteEntriesRegisterConfig,
)
from .sqlite_sessions_register import SQLiteSessionsRegisterConfig

ActivitiesRegisterConfigUnion = Annotated[
    MarkdownActivitiesRegisterConfig | SQLiteActivitiesRegisterConfig,
    Field(discriminator='backend'),
]

SessionsRegisterConfigUnion = Annotated[
    MarkdownSessionsRegisterConfig | SQLiteSessionsRegisterConfig,
    Field(discriminator='backend'),
]

ActivitiesRegisterUnion = MarkdownActivitiesRegister | SQLiteActivitiesRegister

__all__ = [
    # Activities register.
    'ActivitiesRegister',
    'ActivitiesRegisterConfig',
    'MarkdownActivitiesRegister',
    'MarkdownActivitiesRegisterConfig',
    'SQLiteActivitiesRegister',
    'SQLiteActivitiesRegisterConfig',
    'ActivitiesRegisterUnion',
    'ActivitiesRegisterConfigUnion',

    # Sessions register.
    'SessionsRegisterConfig',
    'MarkdownSessionsRegisterConfig',
    'SQLiteSessionsRegisterConfig',
    'SessionsRegisterConfigUnion',

    # Entries register.
    'EntriesRegister',
    'EntriesRegisterConfig',
    'MarkdownEntriesRegister',
    'MarkdownEntriesRegisterConfig',
    'SQLiteEntriesRegister',
    'SQLiteEntriesRegisterConfig',
]
