from collections.abc import Iterator
from pathlib import Path
from typing import Literal, override

from pydantic import field_validator

from diane.chrono import Timestamp
from diane.entry import Entry
from diane.storage import EntriesRegister, EntriesRegisterConfig

from .entries_register import EntriesRegisterError, NotRelativePathError


class MarkdownEntriesRegisterError(EntriesRegisterError):
    """A general Markdown entries register error."""
    ...


class DailyNoteTemplateNotRelativePathError(
    MarkdownEntriesRegisterError, NotRelativePathError
):
    """A path to a daily note's template is not relative.

    For Pydantic's validation.
    """
    ...


class MarkdownEntriesRegisterConfig(EntriesRegisterConfig):
    """A Markdown entries register configuration.

    Attributes:
        backend (Literal['markdown']): A markdown backend literal.
        path (Path): A daily notes subdirectory.
        daily_note_name_format (str): A daily note's name `strftime`
            format. For example, '%Y-%m-%d'.
        daily_note_template_path (Path | None): An optional relative
            path to a daily note's template in a repository.
            For example, 'templates/daily_note_template'.
    """

    backend: Literal['markdown'] = 'markdown'
    path: Path = Path('daily_notes')
    daily_note_name_format: str = '%Y-%m-%d'
    daily_note_template_path: Path | None = None

    @field_validator('daily_note_template_path')
    @classmethod
    def _check_daily_note_template_path(cls, v: Path | None) -> Path | None:
        """Validate a daily note template path.

        Args:
            v (Path | None): A path to a daily note template.

        Returns:
            Path | None: The validated path.

        Raises:
            DailyNoteTemplateNotRelativePathError: If a path to a daily
                note template is not relative.
        """
        if v is not None and v.is_absolute():
            raise DailyNoteTemplateNotRelativePathError(
                f"'daily_note_template_path' must be relative, got '{v}'."
            )
        return v


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
