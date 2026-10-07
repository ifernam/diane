from __future__ import annotations

import datetime
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import (
    ClassVar,
    Literal,
    NamedTuple,
    overload,
    override,
)

import frontmatter
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from diane.chrono import Timestamp
from diane.entry import Entry, EntryData, TimestampedEntry
from diane.listr import LiStr
from diane.storage import EntriesRegister, EntriesRegisterConfig, Slice

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

    backend: Literal["markdown"] = "markdown"
    path: Path = Path("daily_notes")
    daily_note_name_format: str = "%Y-%m-%d"
    daily_note_template_path: Path | None = None

    @field_validator("daily_note_template_path")
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

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

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
        entry (DailyNoteEntry): A daily notes date and name.
        data (DailyNoteData): A daily note's data.
        content (str): A daily note's Markdown content.
    """

    entry: DailyNoteEntry
    data: DailyNoteData
    content: str


def yaml_to_entry(
    note_name: str, yaml_data: EntryYAMLData
) -> TimestampedEntry:
    """Convert raw YAML entry data to a timestamped entry representation.

    Args:
        note_name (str): A daily note's name.
        yaml_data (EntryYAMLData): Raw entry data from daily note YAML.

    Returns:
        TimestampedEntry: An entry paired with its timestamp.

    Raises:
        InvalidISOFormatError: If `yaml_data.time` is not a valid ISO 8601
            string.
        InvalidTimezoneError: If `yaml_data.timezone` is invalid or does not
            match the offset in `yaml_data.time`.
        ValidationError: If the resulting timestamp could not be validated.
        NonExistentTimeError: If the provided local time does not exist in the
            specified IANA time zone.
    """
    iso = f'{note_name}T{yaml_data.time}'
    return TimestampedEntry(
        timestamp=Timestamp.from_iso_iana(iso, yaml_data.timezone),
        entry=Entry(EntryData(tags=yaml_data.tags, text=yaml_data.text)),
    )


def note_to_entries(note: DailyNote) -> list[TimestampedEntry]:
    """Convert a daily note to a list of its timestamped entries.

    Args:
        note (DailyNote): A daily note.

    Returns:
        list[TimestampedEntry]: The daily note's text entries paired
            with their timestamps.

    Raises:
        InvalidISOFormatError: If an entry's `time` is not a valid ISO 8601
            string.
        InvalidTimezoneError: If an entry's `timezone` is invalid or does not
            match the offset in `time`.
        ValidationError: If a resulting timestamp could not be validated.
        NonExistentTimeError: If a provided local time does not exist in the
            specified IANA time zone.
    """
    return [yaml_to_entry(note.entry.name, y) for y in note.data.diane_entries]


class MarkdownEntriesRegister(EntriesRegister[MarkdownEntriesRegisterConfig]):
    """Represents a Markdown entries register.

    Enables the user's text entries stored in daily notes to be worked
    with.
    """

    # How far daily notes are searched around a date an entry is looked
    # up for, since one and the same moment in time can fall
    # on different calendar days in different time zones.
    _DATE_MARGIN_DAYS: ClassVar[int] = 2

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
        end: datetime.date | None = None,
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
        for p in self.path.glob("*.md"):
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
        end: datetime.date | None = None,
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

    def _load_note(self, entry: DailyNoteEntry) -> DailyNote:
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
        daily_note_path = self.path / f"{entry.name}.md"

        if not daily_note_path.is_file():
            raise DailyNoteNotFoundError(
                f"The daily note '{entry.name}' could not be found."
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
                entry,
                DailyNoteData.model_validate(note.metadata),
                note.content
            )
        except ValidationError as exc:
            raise InvalidDailyNoteDataError(
                f"The daily note '{daily_note_path}' has invalid format."
            ) from exc

    def _search_span(
        self, day: datetime.date
    ) -> tuple[datetime.date, datetime.date]:
        """Return `day` widened by the date margin on both sides,
        clamped to the representable date range.

        Args:
            day (datetime.date): A date to widen.

        Returns:
            tuple[datetime.date, datetime.date]: The lower and upper
                bounds, both included.
        """
        lower_ordinal = max(
            day.toordinal() - self._DATE_MARGIN_DAYS,
            datetime.date.min.toordinal(),
        )
        upper_ordinal = min(
            day.toordinal() + self._DATE_MARGIN_DAYS,
            datetime.date.max.toordinal(),
        )
        return (
            datetime.date.fromordinal(lower_ordinal),
            datetime.date.fromordinal(upper_ordinal),
        )

    def _matching_entries(
        self,
        start: datetime.date | None,
        end: datetime.date | None,
        keep: Callable[[TimestampedEntry], bool],
    ) -> list[TimestampedEntry]:
        """Collect unique entries of daily notes within a date range.

        Args:
            start (datetime.date | None): A start date, included.
            end (datetime.date | None): An end date, included.
            keep (Callable[[TimestampedEntry], bool]): A predicate
                selecting the entries to return.

        Returns:
            list[TimestampedEntry]: The matching unique entries in
                chronological order.
        """
        entries: list[TimestampedEntry] = []
        seen: set[TimestampedEntry] = set()

        for dne in self._daily_notes_chrono(start, end):
            for e in note_to_entries(self._load_note(dne)):
                if keep(e) and e not in seen:
                    seen.add(e)
                    entries.append(e)

        return sorted(entries, key=lambda e: e.timestamp)

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

    @overload
    def __getitem__(self, key: Timestamp) -> list[TimestampedEntry]: ...

    @overload
    def __getitem__(self, key: Slice) -> list[TimestampedEntry]: ...

    @overload
    def __getitem__(self, key: datetime.date) -> list[TimestampedEntry]: ...

    @override
    def __getitem__(
        self, key: Timestamp | Slice | datetime.date
    ) -> list[TimestampedEntry]:
        """Return a list of entries relating to the specified moment
        in time or time range, in chronological order.

        An entry is returned only once even if it occurs in several
        daily notes.

        Args:
            key (Timestamp | slice | datetime.date): A timestamp, slice
                of timestamps or a date. The upper bound of a slice
                is not included.

        Returns:
            list[TimestampedEntry]: A list of entries relating
                to the specified moment in time or time range,
                in chronological order.

        Raises:
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
            InvalidISOFormatError: If an entry's `time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If an entry's `timezone` is invalid
                or does not match the offset in `time`.
            ValidationError: If a resulting timestamp could not
                be validated.
            NonExistentTimeError: If a provided local time does not
                exist in the specified IANA time zone.
            ValueError: If a slice step is not `None`.
            TypeError: If a key is of an unknown type.
        """
        if isinstance(key, Timestamp):
            # The same entry can have different calendar dates
            # in different time zones.
            start, end = self._search_span(key.datetime.date())
            return self._matching_entries(
                start, end, lambda e: e.timestamp == key
            )

        elif isinstance(key, slice):
            if key.step is not None:
                raise ValueError("Slice steps are not supported.")

            start, _ = (
                self._search_span(key.start.datetime.date())
                if key.start is not None
                else (None, None)
            )
            _, end = (
                self._search_span(key.stop.datetime.date())
                if key.stop is not None
                else (None, None)
            )

            return self._matching_entries(
                start,
                end,
                lambda e: (
                    (key.start is None or e.timestamp >= key.start)
                    and (key.stop is None or e.timestamp < key.stop)
                ),
            )

        elif isinstance(key, datetime.datetime):
            raise TypeError(
                "A `datetime.datetime` object is ambiguous. "
                "Use a `Timestamp` for a moment in time "
                "or a `datetime.date` for a daily note."
            )

        elif isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            key, datetime.date
        ):
            return self._matching_entries(key, key, lambda e: True)

        else:
            raise TypeError(  # pyright: ignore[reportUnreachable]
                "Expected `Timestamp`, `Slice` or `datetime.date`. "
                f"Got `{type(key)}`."
            )

    @override
    def __setitem__(
        self, key: Timestamp, value: list[TimestampedEntry]
    ) -> None:
        """Record a list of entries relating to the specified moment
        in time.

        The timestamps of all entries must match the key.

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
