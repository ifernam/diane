import datetime
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar, Literal, NamedTuple, override

import frontmatter
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from diane.chrono import Timestamp
from diane.entry import Entry
from diane.listr import LiStr
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


class DailyNoteNotFoundError(MarkdownEntriesRegisterError):
    """A daily note could not be found."""
    ...


class DailyNoteReadError(MarkdownEntriesRegisterError):
    """A daily note could not be read."""
    ...


class InvalidDailyNoteDataError(MarkdownEntriesRegisterError):
    """An invalid data format in a daily note."""
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


class EntryYAMLData(BaseModel):
    """Stores entry data from daily note's YAML front matter as it is.

    Attributes:
        time (str): An ISO 8601 time string with a UTC offset.
        timezone (str): An IANA time zone.
        tags (LiStr): An entry's tags. Optional.
        text (str): An entry's Markdown text.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

    time: str
    timezone: str
    tags: LiStr = []
    text: str


class DailyNoteData(BaseModel):
    """Stores a daily note's data from a YAML front matter.

    Attributes:
        tags (LiStr): A daily note's tags. Optional.
        diane_entries (list[EntryYAMLData]): The user's text entries.
    """

    tags: LiStr = []
    diane_entries: list[EntryYAMLData] = []


class DailyNote(NamedTuple):
    """Represents a daily note.

    Attributes:
        data (DailyNoteData): A daily note's data.
        content (str): A daily note's Markdown content.
    """

    data: DailyNoteData
    content: str


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

    def _load_note(self, name: str) -> DailyNote:
        """Load a daily note by its name.

        Args:
            name (str): A daily note's name.

        Returns:
            DailyNote: A daily note.

        Raises:
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
        """
        daily_note_path = self.path / f'{name}.md'

        if not daily_note_path.is_file():
            raise DailyNoteNotFoundError(
                f"The daily note '{name}' could not be found."
            )

        try:
            note = frontmatter.load(daily_note_path)
        except FileNotFoundError as exc:
            raise DailyNoteReadError(
                f"The daily note '{daily_note_path}' could not be found."
            ) from exc
        except PermissionError as exc:
            raise DailyNoteReadError(
                f"Permission denied: '{daily_note_path}'."
            ) from exc
        except OSError as exc:
            raise DailyNoteReadError(
                f"An I/O error occurred while reading '{daily_note_path}'. "
                f"{exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise DailyNoteReadError(
                f"An encoding error in '{daily_note_path}'. Try a different "
                f"encoding. {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise DailyNoteReadError(
                f"A YAML syntax error in '{daily_note_path}'. {exc}"
            ) from exc
        except ValueError as exc:
            raise DailyNoteReadError(
                f"'{daily_note_path}' is not a file that can be opened. {exc}"
            ) from exc
        except TypeError as exc:
            raise DailyNoteReadError(
                f"An invalid input type for '{daily_note_path}'. {exc}"
            ) from exc

        try:
            return DailyNote(
                DailyNoteData.model_validate(note.metadata),
                note.content
            )
        except ValidationError as exc:
            raise InvalidDailyNoteDataError(
                f"The daily note '{daily_note_path}' has invalid format."
            ) from exc

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
