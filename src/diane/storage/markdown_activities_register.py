from collections.abc import Iterator
from pathlib import Path
from typing import Literal, override

from diane.activity import Activity
from diane.storage.activities_register import (
    ActivitiesRegister,
    ActivitiesRegisterConfig,
)


class MarkdownActivitiesRegisterConfig(ActivitiesRegisterConfig):
    """A Markdown activities register configuration."""

    backend: Literal['markdown'] = 'markdown'
    path: Path = Path('diane_activities')


class MarkdownActivitiesRegister(
    ActivitiesRegister[MarkdownActivitiesRegisterConfig]
):
    """Represents a Markdown activities register.

    Enables to work with activities that are stored in Markdown notes.
    """

    @override
    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError

    @override
    def __len__(self) -> int:
        raise NotImplementedError

    @override
    def __getitem__(self, key: str) -> Activity:
        raise NotImplementedError

    @override
    def __setitem__(self, key: str, value: Activity) -> None:
        raise NotImplementedError

    @override
    def __delitem__(self, key: str) -> None:
        raise NotImplementedError
