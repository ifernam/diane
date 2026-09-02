from collections.abc import Iterator
from typing import Literal, override

from diane.activity import Activity
from diane.storage.activities_register import (
    ActivitiesRegister,
    ActivitiesRegisterConfig,
)


class SQLiteActivitiesRegisterConfig(ActivitiesRegisterConfig):
    """An SQLite activities register configuration."""

    backend: Literal['sqlite'] = 'sqlite'


class SQLiteActivitiesRegister(
    ActivitiesRegister[SQLiteActivitiesRegisterConfig]
):
    """Represents an SQLite activities register.

    Enables to work with activities that are stored in an SQLite
    database.
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

    @override
    def parents(self, *slug: str) -> set[str]:
        """Return the parents of the given activities.

        Args:
            *slug (str): Activity slugs.

        Returns:
            set[str]: A set of all direct parents of the given
                activities.
        """
        raise NotImplementedError
