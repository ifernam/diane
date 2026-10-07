import datetime
from collections.abc import Iterator
from typing import Literal, override

from diane.chrono import Timestamp
from diane.entry import TimestampedEntry
from diane.storage import EntriesRegister, EntriesRegisterConfig, Slice


class SQLiteEntriesRegisterConfig(EntriesRegisterConfig):
    """An SQLite entries register configuration.

    Attributes:
        backend (Literal['sqlite']): An SQLite backend literal.
        path (Path): A relative path where entries are stored.
    """

    backend: Literal["sqlite"] = "sqlite"


class SQLiteEntriesRegister(EntriesRegister[SQLiteEntriesRegisterConfig]):
    """Represents an SQLite entries register.

    Enables the user's text entries stored in an SQLite database
    to be worked with.
    """

    @override
    def __iter__(self) -> Iterator[Timestamp]:
        """Iterate over entries timestamps in chronological order.

        Yields:
            Timestamp: An entry's timestamp.
        """
        raise NotImplementedError

    @override
    def __len__(self) -> int:
        """Return the number of entries timestamps in the register.

        Note that this number may be smaller than the number of entries,
        as several entries may refer to the same moment in time.

        Returns:
            int: The number of entries timestamps in the register.
        """
        raise NotImplementedError

    @override
    def __getitem__(
        self, key: Timestamp | Slice | datetime.date
    ) -> list[TimestampedEntry]:
        """Return a list of entries relating to the specified moment
        in time or time range, in chronological order.

        Args:
            key (Timestamp | slice | datetime.date): A timestamp, slice
                of timestamps or a date. The upper bound of a slice
                is not included.

        Returns:
            list[TimestampedEntry]: A list of entries relating
                to the specified moment in time or time range,
                in chronological order.
        """
        raise NotImplementedError

    @override
    def __setitem__(
        self, key: Timestamp, value: list[TimestampedEntry]
    ) -> None:
        """Record a list of entries relating to the specified moment
        in time.

        Args:
            key (Timestamp): A timestamp.
            value (list[TimestampedEntry]): A list of entries.
        """
        raise NotImplementedError

    @override
    def __delitem__(self, key: Timestamp) -> None:
        """Remove a list of entries relating to the specified moment
        in time.

        Args:
            key (Timestamp): A timestamp.
        """
        raise NotImplementedError
