from collections.abc import Iterator
from pathlib import Path
from typing import Literal, override

from diane.chrono import Timestamp
from diane.entry import Entry
from diane.storage import EntriesRegister, EntriesRegisterConfig


class MarkdownEntriesRegisterConfig(EntriesRegisterConfig):
    """A Markdown entries register configuration.

    Attributes:
        backend (Literal['markdown']): A markdown backend literal.
        path (Path): A daily notes subdirectory.
    """

    backend: Literal['markdown'] = 'markdown'
    path: Path = Path('daily_notes')


class MarkdownEntriesRegister(EntriesRegister[MarkdownEntriesRegisterConfig]):
    """Represents a Markdown entries register.

    Enables the user's text entries stored in daily notes to be worked
    with.
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
    def __getitem__(self, key: Timestamp) -> list[Entry]:
        """Return a list of entries relating to the specified moment
        in time.

        Args:
            key (Timestamp): A timestamp.

        Returns:
            list[Entry]: A list of entries relating to the specified
                moment in time.
        """
        raise NotImplementedError

    @override
    def __setitem__(self, key: Timestamp, value: list[Entry]) -> None:
        """Record a list of entries relating to the specified moment
        in time.

        Args:
            key (Timestamp): A timestamp.
            value (list[Entry]): A list of entries.
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
