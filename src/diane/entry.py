from typing import ClassVar, override

from pydantic import BaseModel, ConfigDict

from diane.listr import LiStr


class EntryData(BaseModel):
    """An entry's data.

    Attributes:
        tags (LiStr): An entry's tags.
        text (str): A text entry in Markdown format.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

    tags: LiStr = []
    text: str


class Entry:
    """Represents a user's text entry.

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

    @property
    def data(self) -> EntryData:
        """Return a copy of the entry's data.

        Returns:
            EntryData: A copy of the entry's data.
        """
        return self._data.model_copy(deep=True)
