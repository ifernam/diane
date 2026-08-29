from typing import Annotated

from pydantic import Field

from .activities_register import ActivitiesRegister, ActivitiesRegisterConfig
from .markdown_activities_register import (
    MarkdownActivitiesRegister,
    MarkdownActivitiesRegisterConfig,
)
from .markdown_sessions_register import MarkdownSessionsRegisterConfig
from .sessions_register import SessionsRegisterConfig
from .sqlite_activities_register import (
    SQLiteActivitiesRegister,
    SQLiteActivitiesRegisterConfig,
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
    'ActivitiesRegister',
    'ActivitiesRegisterConfig',
    'SessionsRegisterConfig',
    'MarkdownActivitiesRegister',
    'MarkdownActivitiesRegisterConfig',
    'MarkdownSessionsRegisterConfig',
    'SQLiteActivitiesRegister',
    'SQLiteActivitiesRegisterConfig',
    'SQLiteSessionsRegisterConfig',
    'ActivitiesRegisterConfigUnion',
    'SessionsRegisterConfigUnion',
    'ActivitiesRegisterUnion',
]
