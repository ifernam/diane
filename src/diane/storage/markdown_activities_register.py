import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, NamedTuple, override

import frontmatter
import yaml
from pydantic import BaseModel, ValidationError

from diane.activity import Activity, ActivityData
from diane.storage.activities_register import (
    ActivitiesRegister,
    ActivitiesRegisterConfig,
)


class MarkdownActivitiesRegisterError(Exception):
    """A general Markdown activities register error."""
    ...


class ActivityNotFoundError(MarkdownActivitiesRegisterError):
    """An activity could not be found."""
    ...


class ActivityNoteReadError(MarkdownActivitiesRegisterError):
    """An activity note could not be read."""
    ...


class InvalidActivityNoteDataError(MarkdownActivitiesRegisterError):
    """An invalid data format in a Markdown activity note."""
    ...


class InvalidActivityLinkError(MarkdownActivitiesRegisterError):
    """An activity link has invalid format."""
    ...


class ActivityNoteWriteError(MarkdownActivitiesRegisterError):
    """An activity note could not be written."""
    ...


class SlugKeyMatchError(MarkdownActivitiesRegisterError):
    """An activity slug does not match its key."""
    ...


class MarkdownActivitiesRegisterConfig(ActivitiesRegisterConfig):
    """A Markdown activities register configuration."""

    backend: Literal['markdown'] = 'markdown'
    path: Path = Path('diane_activities')


class ActivityNoteData(BaseModel):
    """Stores activity data from Markdown activity note's YAML front
    matter as it is.

    Attributes:
        tags (list[str] | str): Tags for an activity. Optional.
        name (str): A human-readable title.
        description (str): An optional description.
        emoji (str | None): An optional Unicode emoji.
        parents (list[str] | str): An optional list of links to parents.
    """

    tags: list[str] | str = []
    name: str
    description: str = ''
    emoji: str | None = None
    parents: list[str] | str = []


class ActivityNote(NamedTuple):
    """Represents an activity note.

    Attributes:
        data (ActivityNoteData): An activity note's data.
        content (str): An activity note's Markdown content.
    """

    data: ActivityNoteData
    content: str


class MarkdownActivitiesRegister(
    ActivitiesRegister[MarkdownActivitiesRegisterConfig]
):
    """Represents a Markdown activities register.

    Enables to work with activities that are stored in Markdown notes.

    Each activity is represented by a file named '<slug>.md'. All
    information relating to the activity can be found in the YAML front
    matter.
    """

    def _slugs(self) -> Iterator[str]:
        """Iterate over activity slugs in the register.

        The order is arbitrary.

        Yields:
            str: An activity slug.
        """
        for p in self.path.glob('*.md'):
            if p.is_file():
                yield p.stem

    @override
    def __iter__(self) -> Iterator[str]:
        """Iterate over activity slugs in the register, in alphabetical
        order.

        Yields:
            str: An activity slug.
        """
        return iter(sorted(self._slugs()))

    def _load_note(self, slug: str) -> ActivityNote:
        """Load an activity note by an activity's slug.

        Args:
            slug (str): An activity slug.

        Returns:
            ActivityNote: An activity note.

        Raises:
            ActivityNotFoundError: If an activity could not be found.
            ActivityNoteReadError: If an activity note could not
                be read.
            InvalidActivityNoteDataError: If an activity note has
                invalid format.
        """
        activity_note_path = self.path / f'{slug}.md'

        if not activity_note_path.is_file():
            raise ActivityNotFoundError(
                f"The activity '{slug}' could not be found."
            )

        try:
            note = frontmatter.load(activity_note_path)
        except FileNotFoundError as exc:
            raise ActivityNoteReadError(
                f"The activity note '{activity_note_path}' could not be found."
            ) from exc
        except PermissionError as exc:
            raise ActivityNoteReadError(
                f"Permission denied: '{activity_note_path}'."
            ) from exc
        except OSError as exc:
            raise ActivityNoteReadError(
                f"An I/O error occurred while reading '{activity_note_path}'. "
                f"{exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise ActivityNoteReadError(
                f"An encoding error in '{activity_note_path}'. Try "
                f"a different encoding. {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise ActivityNoteReadError(
                f"A YAML syntax error in '{activity_note_path}'. {exc}"
            ) from exc
        except ValueError as exc:
            raise ActivityNoteReadError(
                f"'{activity_note_path}' is not a file that can be opened. "
                f"{exc}"
            ) from exc
        except TypeError as exc:
            raise ActivityNoteReadError(
                f"An invalid input type for '{activity_note_path}'. {exc}"
            ) from exc

        try:
            return ActivityNote(
                ActivityNoteData.model_validate(note.metadata),
                note.content
            )
        except ValidationError as exc:
            raise InvalidActivityNoteDataError(
                f"The activity note '{activity_note_path}' has invalid format."
            ) from exc

    def _save_note(self, slug: str, note: ActivityNote) -> None:
        """Save an activity note.

        Args:
            slug (str): An activity slug.
            note (ActivityNote): An activity note.

        Raises:
            ActivityNoteWriteError: If an activity note could not
                be written.
        """
        # Prepare data.
        path = self.path / f'{slug}.md'
        data: dict[str, object] = note.data.model_dump()
        post = frontmatter.Post(note.content, handler=None, **data)

        # Save the note.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            frontmatter.dump(post, path)
        except PermissionError as exc:
            raise ActivityNoteWriteError(
                f"Permission denied: '{path}'."
            ) from exc
        except OSError as exc:
            raise ActivityNoteWriteError(
                f"An I/O error occurred while writing '{path}'. {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise ActivityNoteWriteError(
                f"A YAML serialization error for '{path}'. {exc}"
            ) from exc

    def _note_data_to_activity_data(
        self, note_data: ActivityNoteData
    ) -> ActivityData:
        """Convert an activity note's data to an activity's data.

        - If no emoji is specified in an activity note's data,
          the fallback emoji from the register will be used.
        - Ignores parents.

        Args:
            note_data (ActivityNoteData): An activity note's data.

        Returns:
            ActivityData: An activity's data.
        """
        # Determine the emoji.
        emoji = (
            note_data.emoji if note_data.emoji is not None
            else self._config.fallback_emoji
        )

        return ActivityData(
            name=note_data.name,
            description=note_data.description,
            tags=note_data.tags,
            emoji=emoji
        )

    def _activity_data_to_note_data(
        self,
        activity_data: ActivityData,
        parents: list[str] | str | None = None
    ) -> ActivityNoteData:
        """Convert an activity's data to an activity note's data.

        Parents should be listed separately.

        The single-parent case is always reduced to a bare string.

        Args:
            activity_data (ActivityData): An activity's data.
            parents (list[str] | str | None): Optional parents.

        Returns:
            ActivityNoteData: An activity note's data.
        """
        if parents is None:
            parents = []
        elif isinstance(parents, str):
            parents = [parents]
        parent_links: list[str] | str = (
            self._link_activity(parents[0]) if len(parents) == 1
            else [self._link_activity(p) for p in parents]
        )
        return ActivityNoteData(
            tags=activity_data.tags,
            name=activity_data.name,
            description=activity_data.description,
            emoji=activity_data.emoji,
            parents=parent_links
        )

    @override
    def __len__(self) -> int:
        """Return the number of activities in the register.

        Returns:
            int: The number of activities in the register.
        """
        return sum(1 for _ in self._slugs())

    @override
    def __getitem__(self, key: str) -> Activity:
        """Get an activity from the register by its slug.

        Args:
            key (str): An activity slug.

        Returns:
            Activity: An activity.

        Raises:
            ActivityNotFoundError: If an activity could not be found.
            ActivityNoteReadError: If an activity note could not
                be read.
            InvalidActivityNoteDataError: If an activity note has
                invalid format.
        """
        note_data = self._load_note(key).data
        activity_data = self._note_data_to_activity_data(note_data)
        return Activity(key, activity_data)

    @override
    def __setitem__(self, key: str, value: Activity) -> None:
        """Record an activity in the register.

        Args:
            key (str): An activity slug.
            value (Activity): An activity.

        Raises:
            SlugKeyMatchError: If an activity slug does not match its
                key.
            ActivityNotFoundError: If an activity could not be found.
            ActivityNoteReadError: If an activity note could not
                be read.
            InvalidActivityNoteDataError: If an activity note has
                invalid format.
            InvalidActivityLinkError: If a link format is invalid.
            ActivityNoteWriteError: If an activity note could not
                be written.
        """
        # Check that the activity slug matches the key.
        if key != value.slug:
            raise SlugKeyMatchError(
                f"The activity slug '{value.slug}' "
                f"does not match its key '{key}'."
            )

        raw_parents, content = [], ''
        if key in self:
            note = self._load_note(key)
            raw_parents, content = note.data.parents, note.content

        # Unlink parents.
        parents = (
            self._unlink_activity(raw_parents) if isinstance(raw_parents, str)
            else [self._unlink_activity(p) for p in raw_parents]
        )

        note_data = self._activity_data_to_note_data(value.data, parents)
        note = ActivityNote(note_data, content)
        self._save_note(key, note)

    @override
    def __delitem__(self, key: str) -> None:
        raise NotImplementedError

    @override
    def __contains__(self, key: object) -> bool:
        """Check whether an object is in the register.

        Args:
            key (object): An object to be checked to see if it is listed
                in the register.

        Returns:
            bool: `True` if an object is listed in the register.
        """
        if isinstance(key, str):
            activity_note_path = self.path / f'{key}.md'
            return activity_note_path.is_file()

        return False

    @property
    def _activity_link_pattern(self) -> re.Pattern[str]:
        """Return the activity link pattern.

        The pattern looks like
        '[[<activities subdirectory>/<activity slug>]]'.

        Returns:
            re.Pattern[str]: The activity link pattern.
        """
        return re.compile(
            rf'^\[\[{re.escape(self._config.path.as_posix())}/([^\]]+)\]\]$'
        )

    def _unlink_activity(self, link: str) -> str:
        """Return the activity slug for the given activity note's link.

        Args:
            link (str): A link to an activity note.

        Returns:
            str: An activity slug.

        Raises:
            InvalidActivityLinkError: If a link format is invalid.
        """
        match = self._activity_link_pattern.match(link)

        if not match:
            raise InvalidActivityLinkError(
                f"The activity link '{link}' is invalid."
            )

        return match.group(1)

    def _link_activity(self, slug: str) -> str:
        """Return the activity note's link for the given activity slug.

        Args:
            slug (str): An activity slug.

        Returns:
            str: A link to an activity note.
        """
        return f'[[{self._config.path.as_posix()}/{slug}]]'

    @override
    def parents(self, *slugs: str) -> set[str]:
        """Return the parents of the given activities.

        Args:
            *slugs (str): Activity slugs.

        Returns:
            set[str]: All direct parents of the given activities.

        Raises:
            ActivityNotFoundError: If an activity could not be found.
            ActivityNoteReadError: If an activity note could not
                be read.
            InvalidActivityNoteDataError: If an activity note has
                invalid format.
            InvalidActivityLinkError: If an activity link format
                is invalid.
        """
        parents: set[str] = set()
        for s in set(slugs):
            raw = self._load_note(s).data.parents
            links = raw if isinstance(raw, list) else [raw]
            parents.update(self._unlink_activity(p) for p in links)

        return parents
