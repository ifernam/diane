import datetime
import textwrap
from pathlib import Path
from typing import ClassVar, NamedTuple

import frontmatter
import yaml
from frontmatter.default_handlers import YAMLHandler
from pydantic import BaseModel, ConfigDict, ValidationError

from diane.chrono import Timestamp
from diane.entry import Entry, EntryData, TimestampedEntry
from diane.listr import LiStr


class DailyNoteError(Exception):
    """A general daily note error."""

    ...


class DailyNoteNotFoundError(DailyNoteError):
    """A daily note could not be found."""

    ...


class DailyNoteReadError(DailyNoteError):
    """A daily note could not be read."""

    ...


class InvalidDailyNoteDataError(DailyNoteError):
    """An invalid data format in a daily note."""

    ...


class DailyNoteWriteError(DailyNoteError):
    """A daily note could not be written."""

    ...


class EntriesNotFound(DailyNoteError):
    """No entries have been found."""

    ...


class DateMatchError(DailyNoteError):
    """The local date of an entry does not match the date of a daily
    note."""

    ...


class DailyNoteRef(NamedTuple):
    """Stores a daily note's date and path.

    Attributes:
        date (datetime.date): A daily note's date.
        path (Path): A daily note's path.
    """

    date: datetime.date
    path: Path

    @property
    def name(self) -> str:
        """Return the daily note's name.

        Returns:
            str: The daily note's name.
        """
        return self.path.stem


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


class DailyNote:
    """Represents a daily note.

    Attributes:
        ref (DailyNoteRef): A daily notes date and path.
        data (DailyNoteData): A daily note's data.
        content (str): A daily note's Markdown content.
    """

    ref: DailyNoteRef
    data: DailyNoteData
    content: str

    def __init__(
        self,
        ref: DailyNoteRef,
        data: DailyNoteData | None = None,
        content: str = "",
    ) -> None:
        """Create a new daily note representation with the user's
        entries.

        Args:
            ref (DailyNoteRef): A daily notes date and path.
            data (DailyNoteData | None): A daily note's data. Empty
                by default.
            content (str): A daily note's Markdown content. Empty
                by default.
        """
        self.ref = ref
        self.data = DailyNoteData() if data is None else data
        self.content = content

    def _yaml_to_entry(self, yaml_data: EntryYAMLData) -> TimestampedEntry:
        """Convert raw YAML entry data to a timestamped entry
        representation.

        Args:
            yaml_data (EntryYAMLData): Raw entry data from daily note
                YAML.

        Returns:
            TimestampedEntry: An entry paired with its timestamp.

        Raises:
            InvalidISOFormatError: If `yaml_data.time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If `yaml_data.timezone` is invalid
                or does not match the offset in `yaml_data.time`.
            ValidationError: If the resulting timestamp could not
                be validated.
            NonExistentTimeError: If the provided local time does not
                exist in the specified IANA time zone.
        """
        iso = f"{self.ref.date.isoformat()}T{yaml_data.time}"
        return TimestampedEntry(
            timestamp=Timestamp.from_iso_iana(iso, yaml_data.timezone),
            entry=Entry(EntryData(tags=yaml_data.tags, text=yaml_data.text)),
        )

    def _entry_to_yaml(self, entry: TimestampedEntry) -> EntryYAMLData:
        """Convert a timestamped entry to YAML.

        Args:
            entry (TimestampedEntry): A timestamped entry.

        Returns:
            EntryYAMLData: Entry YAML data.
        """
        t = entry.timestamp
        time_offset_iso = f"{t.time_iso()}{t.offset_iso()}"
        return EntryYAMLData(
            time=time_offset_iso,
            timezone=t.iana,
            tags=entry.entry.data.tags,
            text=entry.entry.data.text,
        )

    @property
    def entries(self) -> list[TimestampedEntry]:
        """Return timestamped entries in the daily note.

        Returns:
            list[TimestampedEntry]: The daily note's text entries paired
                with their timestamps.

        Raises:
            InvalidISOFormatError: If an entry's `time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If an entry's `timezone` is invalid
                or does not match the offset in `time`.
            ValidationError: If a resulting timestamp could not
                be validated.
            NonExistentTimeError: If a provided local time does not
                exist in the specified IANA time zone.
        """
        return [self._yaml_to_entry(y) for y in self.data.diane_entries]

    @entries.setter
    def entries(self, entries: list[TimestampedEntry]) -> None:
        """Rewrite all entries in the daily note.

        Args:
            entries (list[TimestampedEntry]): New entries.

        Raises:
            DateMatchError: If the local date of an entry does not match
                the date of the daily note.
        """
        for e in entries:
            entry_date = e.timestamp.datetime.date()
            if entry_date != self.ref.date:
                shorten_text = textwrap.shorten(
                    e.entry.data.text, width=40, placeholder="…"
                )
                raise DateMatchError(
                    f"The local date {entry_date} of the entry "
                    f"'{shorten_text}' does not match the date "
                    f"{self.ref.date} of the daily note '{self.ref.name}'."
                )

        self.data.diane_entries = [self._entry_to_yaml(e) for e in entries]

    def add_entry(self, entry: TimestampedEntry) -> None:
        """Add an entry to the daily note if it is not already present.

        Args:
            entry (TimestampedEntry): A new entry.

        Raises:
            InvalidISOFormatError: If an existing entry's `time`
                is not a valid ISO 8601 string.
            InvalidTimezoneError: If an existing entry's `timezone`
                is invalid or does not match the offset in `time`.
            ValidationError: If an existing entry's timestamp could not
                be validated.
            NonExistentTimeError: If an existing entry's local time
                does not exist in the specified IANA time zone.
            DateMatchError: If the local date of the entry does not
                match the date of the daily note.
        """
        entries = self.entries
        if entry not in entries:
            self.entries = [*entries, entry]

    def update_entries(
        self, entries: list[TimestampedEntry]
    ) -> None:
        """Add entries to the daily note, skipping duplicates.

        Args:
            entries (list[TimestampedEntry]): New entries.

        Raises:
            InvalidISOFormatError: If an existing entry's `time`
                is not a valid ISO 8601 string.
            InvalidTimezoneError: If an existing entry's `timezone`
                is invalid or does not match the offset in `time`.
            ValidationError: If an existing entry's timestamp could not
                be validated.
            NonExistentTimeError: If an existing entry's local time
                does not exist in the specified IANA time zone.
            DateMatchError: If the local date of an entry does not
                match the date of the daily note.
        """
        updated_entries = self.entries
        changed = False
        for entry in entries:
            if entry not in updated_entries:
                updated_entries.append(entry)
                changed = True

        if changed:
            self.entries = updated_entries

    def remove_entries(self, timestamp: Timestamp) -> None:
        """Remove entries related to the specified timestamp.

        All entries whose timestamps represent the same moment in time
        are removed.

        Args:
            timestamp (Timestamp): A timestamp.

        Raises:
            InvalidISOFormatError: If `yaml_data.time` is not a valid
                ISO 8601 string.
            InvalidTimezoneError: If `yaml_data.timezone` is invalid
                or does not match the offset in `yaml_data.time`.
            ValidationError: If the resulting timestamp could not
                be validated.
            NonExistentTimeError: If the provided local time does not
                exist in the specified IANA time zone.
            EntriesNotFound: If no entries related to the specified
                timestamp have been found in the daily note.
        """
        remaining_entries: list[EntryYAMLData] = []
        found = False
        for yaml_data in self.data.diane_entries:
            entry_timestamp = self._yaml_to_entry(yaml_data).timestamp
            if entry_timestamp == timestamp:
                found = True
            else:
                remaining_entries.append(yaml_data)

        if not found:
            raise EntriesNotFound(
                f"No entries related to '{timestamp}' have been found "
                f"in the daily note '{self.ref.name}'."
            )

        self.data.diane_entries = remaining_entries

    @classmethod
    def load(cls, ref: DailyNoteRef) -> DailyNote:
        """Load a daily note by its name.

        Args:
            ref (DailyNoteRef): A daily note's date and path.

        Returns:
            DailyNote: A daily note.

        Raises:
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
        """
        path = ref.path

        if not path.is_file():
            raise DailyNoteNotFoundError(
                f"The daily note '{ref.name}' could not be found."
            )

        try:
            note = frontmatter.load(path)
        except FileNotFoundError as exc:
            raise DailyNoteReadError(
                f"The daily note '{path}' could not be found."
            ) from exc
        except PermissionError as exc:
            raise DailyNoteReadError(f"Permission denied: '{path}'.") from exc
        except OSError as exc:
            raise DailyNoteReadError(
                f"An I/O error occurred while reading '{path}'. {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise DailyNoteReadError(
                f"An encoding error in '{path}'. Try a different "
                f"encoding. {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise DailyNoteReadError(
                f"A YAML syntax error in '{path}'. {exc}"
            ) from exc
        except ValueError as exc:
            raise DailyNoteReadError(
                f"'{path}' is not a file that can be opened. {exc}"
            ) from exc
        except TypeError as exc:
            raise DailyNoteReadError(
                f"An invalid input type for '{path}'. {exc}"
            ) from exc

        try:
            return DailyNote(
                ref,
                DailyNoteData.model_validate(note.metadata),
                note.content,
            )
        except ValidationError as exc:
            raise InvalidDailyNoteDataError(
                f"The daily note '{path}' has invalid format."
            ) from exc

    def save(self) -> None:
        """Save the daily note.

        Args:
            note (DailyNote): A daily note.

        Raises:
            DailyNoteWriteError: If a daily note could not be written.
        """
        # Prepare data.
        path = self.ref.path
        data: dict[str, object] = self.data.model_dump(exclude_defaults=True)

        post = frontmatter.Post(self.content, handler=None, **data)

        # Save the note.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            frontmatter.dump(
                post,
                path,
                handler=YAMLHandler(),
                Dumper=yaml.SafeDumper,
                sort_keys=False,
            )
        except PermissionError as exc:
            raise DailyNoteWriteError(f"Permission denied: '{path}'.") from exc
        except OSError as exc:
            raise DailyNoteWriteError(
                f"An I/O error occurred while writing '{path}'. {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise DailyNoteWriteError(
                f"A YAML serialization error for '{path}'. {exc}"
            ) from exc
