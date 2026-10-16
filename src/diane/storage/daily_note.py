import datetime
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


class DailyNoteEntry(NamedTuple):
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
        entry (DailyNoteEntry): A daily notes date and path.
        data (DailyNoteData): A daily note's data.
        content (str): A daily note's Markdown content.
    """

    entry: DailyNoteEntry
    data: DailyNoteData
    content: str

    def __init__(
        self,
        entry: DailyNoteEntry,
        data: DailyNoteData | None = None,
        content: str = "",
    ) -> None:
        """Create a new daily note representation with the user's
        entries.

        Args:
            entry (DailyNoteEntry): A daily notes date and path.
            data (DailyNoteData | None): A daily note's data. Empty
                by default.
            content (str): A daily note's Markdown content. Empty
                by default.
        """
        self.entry = entry
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
        iso = f"{self.entry.name}T{yaml_data.time}"
        return TimestampedEntry(
            timestamp=Timestamp.from_iso_iana(iso, yaml_data.timezone),
            entry=Entry(EntryData(tags=yaml_data.tags, text=yaml_data.text)),
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

    @classmethod
    def load(cls, entry: DailyNoteEntry) -> DailyNote:
        """Load a daily note by its name.

        Args:
            entry (DailyNoteEntry): A daily note's date and path.

        Returns:
            DailyNote: A daily note.

        Raises:
            DailyNoteNotFoundError: If a daily note could not be found.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
        """
        path = entry.path

        if not path.is_file():
            raise DailyNoteNotFoundError(
                f"The daily note '{entry.name}' could not be found."
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
                entry,
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
        path = self.entry.path
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
