import re
from typing import ClassVar, override

from pydantic import BaseModel, ConfigDict


class ActivityError(Exception):
    """A general activity error."""
    ...


class InvalidSlugError(ActivityError):
    """An invalid activity slug."""
    ...


class ActivityData(BaseModel):
    """An activity's data.

    Attributes:
        name (str): A human-readable name.
        description (str): An activity's description. May be empty
            if an activity is clearly understood from its name.
        tags (list[str]): An activity's tags.
        emoji (str): An emoji for visualising activity.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

    name: str
    description: str = ''
    tags: list[str] = []
    emoji: str


class Activity:
    """Represents a human activity.

    Attributes:
        _slug: The unique string identifier for an activity. Cannot
            be changed. Format: lowercase letters, digits,
            and underscores (non-consecutive, not leading/trailing).
            Must contain at least one letter.
        _data: Information about an activity (e.g. a human-readable
            name).
    """

    _SLUG_PATTERN: re.Pattern[str] = re.compile(
        r'^(?=.*[a-z])[a-z0-9]+(?:_[a-z0-9]+)*$'
    )

    _slug: str
    _data: ActivityData

    @classmethod
    def _validate_slug(cls, slug: str) -> None:
        """Check whether a slug matches `_SLUG_PATTERN`.

        Args:
            slug (str): A slug.

        Raises:
            InvalidSlugError: If a slug does not match the pattern.
        """
        if not cls._SLUG_PATTERN.match(slug):
            raise InvalidSlugError(f"The slug '{slug}' is invalid.")

    def __init__(self, slug: str, data: ActivityData) -> None:
        """Create a new activity.

        Args:
            slug (str): An activity's slug.
            data (ActivityData): An activity's information.

        Raises:
            InvalidSlugError: If a slug is invalid.
        """
        self._validate_slug(slug)
        self._slug = slug
        self._data = data

    @override
    def __str__(self) -> str:
        """Return the string representation for the activity.

        Returns the activity's slug.

        Returns:
            str: The string representation.
        """
        return self._slug

    @property
    def slug(self) -> str:
        """Return the unique string identifier (slug) of the activity.

        Returns:
            str: The unique string identifier (slug) of the activity.
        """
        return self._slug

    @property
    def data(self) -> ActivityData:
        """Return a copy of the activity's data.

        Returns:
            ActivityData: A copy of the activity's data.
        """
        return self._data.model_copy()
