import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, override

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

    def _load_note_data(self, slug: str) -> ActivityNoteData:
        """Load an activity note's data from the register
            by an activity's slug.

        Args:
            slug (str): An activity slug.

        Returns:
            ActivityNoteData: An activity note's data.

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
            activity_note = frontmatter.load(activity_note_path)
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
            return ActivityNoteData.model_validate(activity_note.metadata)
        except ValidationError as exc:
            raise InvalidActivityNoteDataError(
                f"The activity note '{activity_note_path}' has invalid format."
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

        # Normalise tags.
        tags = (
            note_data.tags if isinstance(note_data.tags, list)
            else [note_data.tags]
        )

        return ActivityData(
            name=note_data.name,
            description=note_data.description,
            tags=tags,
            emoji=emoji
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
        note_data = self._load_note_data(key)
        activity_data = self._note_data_to_activity_data(note_data)
        return Activity(key, activity_data)

    @override
    def __setitem__(self, key: str, value: Activity) -> None:
        raise NotImplementedError

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
            activity_note_data = self._load_note_data(s)
            raw = activity_note_data.parents
            links = raw if isinstance(raw, list) else [raw]
            parents.update(self._unlink_activity(p) for p in links)

        return parents
