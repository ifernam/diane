import datetime
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, NamedTuple, override

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


class DailyNoteNameError(MarkdownEntriesRegisterError):
    """A daily note has an invalid name."""
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


class DailyNoteEntry(NamedTuple):
    """Stores a daily note's date and name.

    Attributes:
        date (datetime.date): A daily note's date.
        name (str): A daily note's name.
    """

    date: datetime.date
    name: str


class MarkdownEntriesRegister(EntriesRegister[MarkdownEntriesRegisterConfig]):
    """Represents a Markdown entries register.

    Enables the user's text entries stored in daily notes to be worked
    with.
    """

    def _name_to_date(self, name: str) -> datetime.date:
        """Convert a daily note's name to the date it relates to.

        Validates a daily note's name.

        Args:
            name (str): A daily note's name.

        Returns:
            datetime.date: A date that a daily note relates to.

        Raises:
            DailyNoteNameError: If a daily note has invalid name.
        """
        name_format = self._config.daily_note_name_format
        try:
            return datetime.date.strptime(name, name_format)
        except ValueError as exc:
            raise DailyNoteNameError(
                f"The name '{name}' of the daily note does not match "
                f"the format '{name_format}'."
            ) from exc

    def _daily_notes(
        self,
        start: datetime.date | None = None,
        end: datetime.date | None = None
    ) -> Iterator[DailyNoteEntry]:
        """Iterate over daily notes relating to the specified date
        range.

        The start and end dates are included in the specified range.
        The order is arbitrary.

        Args:
            start (datetime.date | None): A start date, included.
            end (datetime.date | None): An end date, included.

        Yields:
            DailyNoteEntry: A daily note's entry.
        """
        for p in self.path.glob('*.md'):
            if p.is_file():
                try:
                    date = self._name_to_date(p.stem)

                    if start is not None and date < start:
                        continue
                    if end is not None and date > end:
                        continue

                    yield DailyNoteEntry(date, p.stem)
                except DailyNoteNameError:
                    pass

    def _daily_notes_chrono(
        self,
        start: datetime.date | None = None,
        end: datetime.date | None = None
    ) -> list[DailyNoteEntry]:
        """Return a list of daily notes relating to the specified date
        range, in chronological order.

        The start and end dates are included in the specified range.

        Args:
            start (datetime.date | None): A start date, included.
            end (datetime.date | None): An end date, included.

        Returns:
            list[DailyNoteEntry]: Daily notes entries in chronological
                order.
        """
        return sorted(self._daily_notes(start, end), key=lambda e: e.date)

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
