from typing import ClassVar, NamedTuple, override

from pydantic import BaseModel, ConfigDict

from diane.chrono import Timestamp
from diane.listr import LiStr, to_set


class EntryData(BaseModel):
    """An entry's data.

    Attributes:
        tags (LiStr): An entry's tags.
        text (str): A text entry in Markdown format.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", frozen=True
    )

    tags: LiStr = []
    text: str

    def _key(self) -> tuple[frozenset[str], str]:
        """Return a hashable canonical form of the entry's data.

        Returns:
            tuple[frozenset[str], str]: The entry's tags as a set
                and its text.
        """
        return (to_set(self.tags), self.text)

    @override
    def __eq__(self, other: object) -> bool:
        """Compare the entry data treating tags as a set.

        Args:
            other (object): An object to compare against.

        Returns:
            bool: `True` if both data have the same set of tags
                and the same text.
        """
        if isinstance(other, EntryData):
            return self._key() == other._key()
        return NotImplemented

    @override
    def __hash__(self) -> int:
        """Return a hash based on the canonical form of the entry data.

        Returns:
            int: A hash consistent with `__eq__`.
        """
        return hash(self._key())


class Entry:
    """Represents the user's text entry.

    Attributes:
        _data (EntryData): An entry's data.
    """

    _data: EntryData

    def __init__(self, data: EntryData) -> None:
        """Create a new entry.

        Args:
            data (EntryData): An entry's data.
        """
        self._data = data

    @override
    def __str__(self) -> str:
        """Return the entry's text.

        Returns:
            str: The entry's text.
        """
        return self._data.text

    @override
    def __eq__(self, other: object) -> bool:
        """Compare two entries by their data.

        Args:
            other (object): An object to compare against.

        Returns:
            bool: `True` if both entries have equal data.
        """
        if isinstance(other, Entry):
            return self._data == other._data
        return NotImplemented

    @override
    def __hash__(self) -> int:
        """Return a hash based on the entry's data.

        Returns:
            int: A data-based hash.
        """
        return hash(self._data)

    @property
    def data(self) -> EntryData:
        """Return a copy of the entry's data.

        Returns:
            EntryData: A copy of the entry's data.
        """
        return self._data.model_copy(deep=True)


class TimestampedEntry(NamedTuple):
    """Represents the user's text entry with its timestamp.

    Attributes:
        timestamp (Timestamp): An entry's timestamp.
        entry (Entry): An entry.
    """

    timestamp: Timestamp
    entry: Entry
