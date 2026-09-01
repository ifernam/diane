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
        activity_note_path = self.path / f'{key}.md'

        if not activity_note_path.is_file():
            raise ActivityNotFoundError(
                f"The activity '{key}' could not be found."
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
            note_data = ActivityNoteData.model_validate(activity_note.metadata)
        except ValidationError as exc:
            raise InvalidActivityNoteDataError(
                f"The activity note '{activity_note_path}' has invalid format."
            ) from exc

        emoji = (
            note_data.emoji if note_data.emoji is not None
            else self._config.fallback_emoji
        )
        tags = (
            note_data.tags if isinstance(note_data.tags, list)
            else [note_data.tags]
        )
        data = ActivityData(
            name=note_data.name,
            description=note_data.description,
            tags=tags,
            emoji=emoji
        )

        return Activity(key, data)

    @override
    def __setitem__(self, key: str, value: Activity) -> None:
        raise NotImplementedError

    @override
    def __delitem__(self, key: str) -> None:
        raise NotImplementedError
