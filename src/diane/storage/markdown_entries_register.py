from __future__ import annotations

import datetime
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import (
    ClassVar,
    Literal,
    overload,
    override,
)

from pydantic import field_validator

from diane.chrono import Timestamp
from diane.entry import TimestampedEntry
from diane.storage import EntriesRegister, EntriesRegisterConfig, Slice
from diane.storage.daily_note import (
    DailyNote,
    DailyNoteNotFoundError,
    DailyNoteRef,
    EntriesNotFound,
)

from .entries_register import (
    EntriesRegisterError,
    NotRelativePathError,
    TimeSliceTypeError,
    TimeSliceValueError,
)


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


class TimeKeyTypeError(MarkdownEntriesRegisterError, TypeError):
    """A time key of unknown type."""

    ...


class TimeKeyMatchError(MarkdownEntriesRegisterError):
    """An entry timestamp does not match its key."""

    ...


class DailyNoteTemplateNotSetError(MarkdownEntriesRegisterError, ValueError):
    """A template for a daily note has not been set up."""

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


class MarkdownEntriesRegister(EntriesRegister[MarkdownEntriesRegisterConfig]):
    """Represents a Markdown entries register.

    Enables the user's text entries stored in daily notes to be worked
    with.
    """

    # How far daily notes are searched around a date an entry is looked
    # up for, since one and the same moment in time can fall
    # on different calendar days in different time zones.
    _DATE_MARGIN_DAYS: ClassVar[int] = 2

    @property
    def daily_note_template_path(self) -> Path:
        """Return the path to a daily note's template.

        Returns:
            Path: The path to a daily note's template.

        Raises:
            DailyNoteTemplateNotSetError: If a path to a template
                for a daily note has not been configured.
        """
        if self._config.daily_note_template_path is None:
            raise DailyNoteTemplateNotSetError(
                "A path to a template for a daily note "
                "has not been configured."
            )
        return self._storage_path / self._config.daily_note_template_path

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

    def _date_to_name(self, date: datetime.date) -> str:
        """Convert a date to a daily note's name.

        Args:
            date (datetime.date): A date.

        Returns:
            str: A daily note's name.
        """
        name_format = self._config.daily_note_name_format
        return date.strftime(name_format)

    def _daily_notes(
        self,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ) -> Iterator[DailyNoteRef]:
        """Iterate over daily notes relating to the specified date
        range.

        The start and end dates are included in the specified range.
        The order is arbitrary.

        Args:
            start (datetime.date | None): A start date, included.
            end (datetime.date | None): An end date, included.

        Yields:
            DailyNoteRef: A daily note's reference.
        """
        for p in self.path.glob("*.md"):
            if p.is_file():
                try:
                    date = self._name_to_date(p.stem)

                    if start is not None and date < start:
                        continue
                    if end is not None and date > end:
                        continue

                    yield DailyNoteRef(date, p)
                except DailyNoteNameError:
                    pass

    def _daily_notes_chrono(
        self,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ) -> list[DailyNoteRef]:
        """Return a list of daily notes relating to the specified date
        range, in chronological order.

        The start and end dates are included in the specified range.

        Args:
            start (datetime.date | None): A start date, included.
            end (datetime.date | None): An end date, included.

        Returns:
            list[DailyNoteRef]: Daily notes references in chronological
                order.
        """
        return sorted(self._daily_notes(start, end), key=lambda e: e.date)

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

        Raises:
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
            InvalidISOFormatError: If an entry's `time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If an entry's `timezone` is invalid
                or does not match the offset in `time`.
            ValidationError: If a resulting timestamp could not be
                validated.
            NonExistentTimeError: If a provided local time does not
                exist in the specified IANA time zone.
        """
        entries: list[TimestampedEntry] = []
        seen: set[TimestampedEntry] = set()

        for dne in self._daily_notes_chrono(start, end):
            for e in DailyNote.load(dne).entries:
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
        entries = self._matching_entries(None, None, lambda _: True)
        return iter(dict.fromkeys(entry.timestamp for entry in entries))

    @override
    def __len__(self) -> int:
        """Return the number of entries timestamps in the register.

        Note that this number may be smaller than the number of entries,
        as several entries may refer to the same moment in time.

        Returns:
            int: The number of entries timestamps in the register.
        """
        return sum(1 for _ in self)

    @override
    def __contains__(self, key: object) -> bool:
        """Check whether an entry with the given timestamp
        is listed in the register.

        Args:
            key (object): The key to check.

        Returns:
            bool: `True` if the timestamp is listed; `False` for other
                key types or if it is not listed.
        """
        if isinstance(key, Timestamp):
            start, end = self._search_span(key.datetime.date())
            return bool(
                self._matching_entries(
                    start, end, lambda e: e.timestamp == key
                )
            )

        return False

    @overload
    def __getitem__(self, key: Timestamp) -> list[TimestampedEntry]: ...

    @overload
    def __getitem__(self, key: Slice[Timestamp]) -> list[TimestampedEntry]: ...

    @overload
    def __getitem__(
        self, key: Slice[datetime.date]
    ) -> list[TimestampedEntry]: ...

    @overload
    def __getitem__(self, key: datetime.date) -> list[TimestampedEntry]: ...

    @override
    def __getitem__(
        self, key: Timestamp | Slice[Timestamp | datetime.date] | datetime.date
    ) -> list[TimestampedEntry]:
        """Return a list of entries relating to the specified moment
        in time or time range, in chronological order.

        An entry is returned only once even if it occurs in several
        daily notes.

        Args:
            key (Timestamp | slice | datetime.date): A time slice.
                If the endpoints are timestamps the upper bound
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
            TimeSliceValueError: If a slice step is not `None`.
            TimeSliceTypeError: If a slice endpoint has an unsupported
                or ambiguous type.
            TimeKeyTypeError: If a key has an unsupported or ambiguous
                type.
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
                raise TimeSliceValueError("Slice steps are not supported.")

            def start_picker(
                e: TimestampedEntry,  # pyright: ignore[reportUnusedParameter]
            ) -> bool:
                return True

            def stop_picker(
                e: TimestampedEntry,  # pyright: ignore[reportUnusedParameter]
            ) -> bool:
                return True

            if isinstance(key.start, Timestamp):
                start, _ = self._search_span(key.start.datetime.date())

                def start_picker(e: TimestampedEntry) -> bool:
                    return e.timestamp >= key.start

            elif isinstance(key.start, datetime.datetime):
                raise TimeSliceTypeError(
                    "A `datetime.datetime` object "
                    "is ambiguous as a slice start. "
                    "Use a `Timestamp` for a moment in time "
                    "or a `datetime.date` for a daily note."
                )

            elif isinstance(key.start, datetime.date):
                start = key.start
            elif key.start is None:
                start = None
            else:
                raise TimeSliceTypeError(
                    "The start of the slice is of unknown type: "
                    f"'{type(key.start)}'."
                )

            if isinstance(key.stop, Timestamp):
                _, end = self._search_span(key.stop.datetime.date())

                def stop_picker(e: TimestampedEntry) -> bool:
                    return e.timestamp < key.stop

            elif isinstance(key.stop, datetime.datetime):
                raise TimeSliceTypeError(
                    "A `datetime.datetime` object "
                    "is ambiguous as a slice end. "
                    "Use a `Timestamp` for a moment in time "
                    "or a `datetime.date` for a daily note."
                )

            elif isinstance(key.stop, datetime.date):
                end = key.stop
            elif key.stop is None:
                end = None
            else:
                raise TimeSliceTypeError(
                    "The end of the slice is of unknown type:"
                    f"'{type(key.stop)}'."
                )

            return self._matching_entries(
                start, end, lambda e: start_picker(e) and stop_picker(e)
            )

        elif isinstance(key, datetime.datetime):
            raise TimeKeyTypeError(
                "A `datetime.datetime` object is ambiguous. "
                "Use a `Timestamp` for a moment in time "
                "or a `datetime.date` for a daily note."
            )

        elif isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            key, datetime.date
        ):
            return self._matching_entries(key, key, lambda e: True)

        else:
            raise TimeKeyTypeError(  # pyright: ignore[reportUnreachable]
                "Expected `Timestamp`, `Slice` or `datetime.date`. "
                f"Got `{type(key)}`."
            )

    @override
    def __setitem__(
        self, key: Timestamp, value: list[TimestampedEntry]
    ) -> None:
        """Rewrite the entries relating to the specified moment in time.

        The timestamps of all entries must match the key.

        Args:
            key (Timestamp): A timestamp.
            value (list[TimestampedEntry]): New entries.

        Raises:
            TimeKeyMatchError: If an entry timestamp does not match its
                key.
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
            InvalidISOFormatError: If `yaml_data.time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If `yaml_data.timezone` is invalid
                or does not match the offset in `yaml_data.time`.
            ValidationError: If the resulting timestamp could not
                be validated.
            NonExistentTimeError: If the provided local time does not
                exist in the specified IANA time zone.
            DailyNoteWriteError: If a daily note could not be written.
            DateMatchError: If the local date of an entry does not match
                the date of the daily note.
        """
        # Check that entries timestamps match the key.
        for e in value:
            if key != e.timestamp:
                raise TimeKeyMatchError(
                    f"The entry timestamp {e.timestamp} "
                    f"does not match its key {key}."
                )

        # Terminate after removing existing entries if no replacements
        # were specified.
        if not value:
            del self[key]
            return

        date = key.datetime.date()
        try:
            # Try loading the daily note for the specified date.
            note = DailyNote.load(next(self._daily_notes(date, date)))
        except (StopIteration, DailyNoteNotFoundError):
            try:
                # Try loading the daily note template.
                ref = DailyNoteRef(date, self.daily_note_template_path)
                note = DailyNote.load(ref)
                note.ref.path = (
                    self.path / f"{self._date_to_name(date)}.md"
                )
            except DailyNoteTemplateNotSetError:
                # Create a new daily note representation.
                ref = DailyNoteRef(
                    date,
                    self.path / f"{self._date_to_name(date)}.md",
                )
                note = DailyNote(ref)

        # Prepare and validate the replacement in memory before modifying
        # any stored daily notes.
        retained_entries = [
            entry for entry in note.entries if entry.timestamp != key
        ]
        note.entries = retained_entries
        note.update_entries(value)

        # Once the replacement is valid, remove old copies and save it.
        del self[key]
        note.save()

    @override
    def __delitem__(self, key: Timestamp) -> None:
        """Remove all entries relating to the specified moment in time.

        If there are no entries relating to the specified timestamp,
        terminates silently.

        Args:
            key (Timestamp): A timestamp.

        Raises:
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
            InvalidISOFormatError: If `yaml_data.time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If `yaml_data.timezone` is invalid
                or does not match the offset in `yaml_data.time`.
            ValidationError: If the resulting timestamp could not
                be validated.
            NonExistentTimeError: If the provided local time does not
                exist in the specified IANA time zone.
            DailyNoteWriteError: If a daily note could not be written.
        """
        start, end = self._search_span(key.datetime.date())
        for r in self._daily_notes(start, end):
            note = DailyNote.load(r)
            try:
                note.remove_entries_by_time(key)
            except EntriesNotFound:
                continue
            note.save()
