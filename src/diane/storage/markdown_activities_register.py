import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, NamedTuple, overload, override

import frontmatter
import yaml
from frontmatter.default_handlers import YAMLHandler
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


class ActivityNoteDeleteError(MarkdownActivitiesRegisterError):
    """An activity note could not be deleted."""
    ...


class SlugKeyMatchError(MarkdownActivitiesRegisterError):
    """An activity slug does not match its key."""
    ...


class ConnectionAlreadyExistsError(MarkdownActivitiesRegisterError):
    """A parent-child connection already exists."""
    ...


class ConnectionNotFoundError(MarkdownActivitiesRegisterError):
    """A parent-child connection could not be found."""
    ...


class PathNotFoundError(MarkdownActivitiesRegisterError):
    """If no path between two activities has been found."""
    ...


class AlreadyInListStrError(Exception):
    """A string is already in `list[str] | str`."""
    ...


class NotInListStrError(Exception):
    """A string is not contained in `list[str] | str`."""
    ...


class ListStrIsEmptyError(Exception):
    """`list[str] | str` is empty."""
    ...


def _add_to_liststr(liststr: list[str] | str, new: str) -> list[str] | str:
    """Add a string to a list of strings or a bare string
    (`list[str] | str`).

    Args:
        liststr (list[str] | str): A list of strings or a bare string.
        new (str): A new string.

    Returns:
        list[str] | str: An updated `list[str] | str`.
    """
    if isinstance(liststr, str):
        # A bare string.
        if new == liststr:
            raise AlreadyInListStrError(
                f"'{new}' is already in the `list[str] | str`."
            )
        return [liststr, new]
    elif not liststr:
        # An empty list.
        return new
    else:
        # A non-empty list.
        if new in liststr:
            raise AlreadyInListStrError(
                f"'{new}' is already in the `list[str] | str`."
            )
        return liststr + [new]


def _remove_from_liststr(
    liststr: list[str] | str, old: str
) -> list[str] | str:
    """Remove a string from a list of strings or a bare string
    (`list[str] | str`).

    Args:
        liststr (list[str] | str): A list of strings or a bare string.
        old (str): A string to be removed.

    Returns:
        list[str] | str: An updated `list[str] | str`.
    """
    if isinstance(liststr, str):
        # A bare string.
        if old == liststr:
            return []

        raise NotInListStrError(
            f"The string '{old}' is not contained in the `list[str] | str`."
        )
    elif not liststr:
        # An empty list.
        raise ListStrIsEmptyError('The `list[str] | str` is empty.')
    else:
        # A non-empty list.
        if old not in liststr:
            raise NotInListStrError(
                f"The string '{old}' is not contained "
                "in the `list[str] | str`."
            )

        updated = [s for s in liststr if s != old]
        if len(updated) == 1:
            return updated[0]
        else:
            return updated


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
        data: dict[str, object] = note.data.model_dump(exclude_defaults=True)
        post = frontmatter.Post(note.content, handler=None, **data)

        # Save the note.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            frontmatter.dump(
                post,
                path,
                handler=YAMLHandler(),
                Dumper=yaml.SafeDumper,
                sort_keys=False
            )
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

        Args:
            activity_data (ActivityData): An activity's data.
            parents (list[str] | str | None): Optional parents.

        Returns:
            ActivityNoteData: An activity note's data.
        """
        if parents is None:
            parents = []
        return ActivityNoteData(
            tags=activity_data.tags,
            name=activity_data.name,
            description=activity_data.description,
            emoji=activity_data.emoji,
            parents=self._link(parents)
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
            ActivityNoteWriteError: If an activity note could not
                be written.
        """
        # Check that the activity slug matches the key.
        if key != value.slug:
            raise SlugKeyMatchError(
                f"The activity slug '{value.slug}' "
                f"does not match its key '{key}'."
            )

        parents, content = [], ''
        if key in self:
            note = self._load_note(key)
            parents, content = note.data.parents, note.content

        note_data = self._activity_data_to_note_data(value.data)
        note_data.parents = parents
        note = ActivityNote(note_data, content)
        self._save_note(key, note)

    @override
    def __delitem__(self, key: str) -> None:
        """Remove an activity from the register.

        Args:
            key (str): An activity slug.

        Raises:
            ActivityNotFoundError: If an activity could not be found.
            ActivityNoteReadError: If an activity note could not
                be read.
            InvalidActivityNoteDataError: If an activity note has
                invalid format.
            InvalidActivityLinkError: If an activity link format
                is invalid.
            ConnectionNotFoundError: If a parent-child connection
                could not be found.
            ActivityNoteWriteError: If a child note could not
                be written.
            ActivityNoteDeleteError: If an activity note could not
                be deleted.
        """
        if key not in self:
            raise ActivityNotFoundError(
                f"The activity '{key}' could not be found."
            )

        for s in self._slugs():
            if s != key and key in self.parents(s):
                self.remove_connection(key, s)

        path = self.path / f'{key}.md'

        try:
            path.unlink(missing_ok=True)
        except PermissionError as exc:
            raise ActivityNoteDeleteError(
                f"Permission denied: '{path}'."
            ) from exc
        except OSError as exc:
            raise ActivityNoteDeleteError(
                f"An I/O error occurred while deleting '{path}'. {exc}"
            ) from exc

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

    @overload
    def _unlink(self, links: str) -> str:
        ...

    @overload
    def _unlink(self, links: list[str]) -> list[str]:
        ...

    def _unlink(self, links: list[str] | str) -> list[str] | str:
        """Return activity slugs for the given links to activity notes.

        Args:
            links (list[str] | str): Links to activity notes.

        Returns:
            list[str] | str: Activity slugs.

        Raises:
            InvalidActivityLinkError: If a link format is invalid.
        """
        if isinstance(links, str):
            match = self._activity_link_pattern.match(links)

            if not match:
                raise InvalidActivityLinkError(
                    f"The activity link '{links}' is invalid."
                )

            return match.group(1)
        else:
            return [self._unlink(a) for a in links]

    @overload
    def _link(self, slugs: str) -> str:
        ...

    @overload
    def _link(self, slugs: list[str]) -> list[str]:
        ...

    def _link(self, slugs: list[str] | str) -> list[str] | str:
        """Return links to activity notes for the given activity slugs.

        Args:
            slugs (list[str] | str): Activity slugs.

        Returns:
            list[str] | str: Links to activity notes.
        """
        if isinstance(slugs, str):
            return f'[[{self._config.path.as_posix()}/{slugs}]]'
        else:
            return [self._link(a) for a in slugs]

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
            unlinked = self._unlink(self._load_note(s).data.parents)
            normalised = unlinked if isinstance(unlinked, list) else [unlinked]
            parents.update(normalised)

        return parents

    @override
    def add_connection(self, parent: str, child: str) -> None:
        """Add a parent-child connection between activities.

        Args:
            parent (str): A parent slug.
            child (str): A child slug.

        Raises:
            ActivityNotFoundError: If a parent or child could not
                be found.
            ActivityNoteReadError: If a child note could not be read.
            InvalidActivityNoteDataError: If a child note has invalid
                format.
            ConnectionAlreadyExistsError: If a parent-child connection
                already exists.
            ActivityNoteWriteError: If a child note could not
                be written.
        """
        if parent not in self:
            raise ActivityNotFoundError(
                f"The activity '{parent}' could not be found."
            )

        parent_link = self._link(parent)
        note = self._load_note(child)
        try:
            note.data.parents = _add_to_liststr(note.data.parents, parent_link)
        except AlreadyInListStrError as exc:
            raise ConnectionAlreadyExistsError(
                f"The parent-child connection '{parent}'-'{child}' "
                "already exists."
            ) from exc
        self._save_note(child, note)

    @override
    def remove_connection(self, parent: str, child: str) -> None:
        """Remove a parent-child connection from the register.

        Args:
            parent (str): A parent slug.
            child (str): A child slug.

        Raises:
            ActivityNotFoundError: If a parent or child could not
                be found.
            ActivityNoteReadError: If a child note could not be read.
            InvalidActivityNoteDataError: If a child note has invalid
                format.
            ConnectionNotFoundError: If a parent-child connection
                could not be found.
            ActivityNoteWriteError: If a child note could not
                be written.
        """
        if parent not in self:
            raise ActivityNotFoundError(
                f"The activity '{parent}' could not be found."
            )

        parent_link = self._link(parent)
        note = self._load_note(child)
        try:
            note.data.parents = _remove_from_liststr(
                note.data.parents, parent_link
            )
        except (NotInListStrError, ListStrIsEmptyError) as exc:
            raise ConnectionNotFoundError(
                f"The parent-child connection '{parent}'-'{child}' "
                "could not be found."
            ) from exc
        self._save_note(child, note)

    def _find_path(self, start: str, end: str) -> list[str]:
        """Find a path from one activity to another.

        The path follows parent-child relationships from the start
        activity to the end activity. The path found is not guaranteed
        to be the shortest.

        Args:
            start (str): A start activity slug.
            end (str): An end activity slug.

        Returns:
            list[str]: Activity slugs forming a path from `start`
                to `end`.

        Raises:
            ActivityNotFoundError: If an activity could not be found.
            ActivityNoteReadError: If an activity note could not
                be read.
            InvalidActivityNoteDataError: If an activity note has
                invalid format.
            InvalidActivityLinkError: If an activity link format
                is invalid.
            PathNotFoundError: If no path exists from `start` to `end`.
        """
        if start not in self:
            raise ActivityNotFoundError(
                f"The activity '{start}' could not be found."
            )
        if end not in self:
            raise ActivityNotFoundError(
                f"The activity '{end}' could not be found."
            )

        if start == end:
            return [start]

        stack = [end]
        child: dict[str, str | None] = {end: None}
        while stack:
            a = stack.pop()

            if a == start:
                path: list[str] = []
                while a is not None:
                    path.append(a)
                    a = child[a]
                return path

            for p in self.parents(a):
                if p not in child:
                    child[p] = a
                    stack.append(p)

        raise PathNotFoundError(
            f"No path has been found from '{start}' to '{end}'."
        )
