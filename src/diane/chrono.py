from __future__ import annotations

import datetime
import zoneinfo
from functools import total_ordering
from typing import override

import tzlocal


class TimeError(Exception):
    """A general time error."""
    ...


class InvalidTimezoneError(TimeError):
    """An invalid time zone."""
    ...


class LocalTimezoneDetectionError(TimeError):
    """Failed to determine the local time zone."""
    ...


@total_ordering
class Timestamp:
    """Represents a timestamp whose time zone is identified by an IANA
    time zone name.

    Attributes:
        _dt (datetime.datetime): An aware `datetime` object with
            a `ZoneInfo` time zone.

    Args:
        dt (datetime.datetime): An aware `datetime` object with
            a `ZoneInfo` time zone.
    """

    _UTC: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo('Etc/UTC')
    _STR_FORMAT: str = '%Y.%m.%d %H:%M:%S.%f %:z %Z'

    _dt: datetime.datetime

    @staticmethod
    def _validate_timezone(dt: datetime.datetime) -> None:
        """Check whether a `datetime` object is aware and uses
        a `ZoneInfo` time zone.

        Args:
            dt (datetime.datetime): A `datetime` object to validate.

        Raises:
            InvalidTimezoneError: If a `datetime` object is naive
                or its time zone is not a `ZoneInfo` instance.
        """
        if dt.tzinfo is None:
            raise InvalidTimezoneError(
                f"No time zone has been specified for '{dt.isoformat()}'.")

        try:
            utc_off = dt.utcoffset()
        except Exception as exc:
            raise InvalidTimezoneError(
                f"Failed to obtain the UTC offset for '{dt.isoformat()}'. "
                f"{exc}"
            ) from exc

        if utc_off is None:
            raise InvalidTimezoneError(
                f"The UTC offset is `None` for '{dt.isoformat()}'."
            )

        if not isinstance(dt.tzinfo, zoneinfo.ZoneInfo):
            raise InvalidTimezoneError(
                "Time zone must be a `ZoneInfo` instance, got "
                f"'{type(dt.tzinfo).__name__}' for '{dt.isoformat()}'."
            )

    def __init__(self, dt: datetime.datetime) -> None:
        """Create a timestamp.

        Args:
            dt (datetime.datetime): An aware `datetime` object with
                a `ZoneInfo` time zone.

        Raises:
            InvalidTimezoneError: If a `datetime` object is naive
                or its time zone is not a `ZoneInfo` instance.
        """
        self._validate_timezone(dt)
        self._dt = dt

    @classmethod
    def now(cls) -> Timestamp:
        """Create a new timestamp representing the current local time.

        Returns:
            Timestamp: A timestamp representing the current local time.

        Raises:
            LocalTimezoneDetectionError: If the local time zone
                could not be determined.
        """
        try:
            tz = tzlocal.get_localzone()
            return cls(datetime.datetime.now(tz))
        except Exception as exc:
            raise LocalTimezoneDetectionError(
                f'Failed to determine the local time zone. {exc}'
            ) from exc

    @classmethod
    def now_utc(cls) -> Timestamp:
        """Create a new timestamp representing the current time in UTC.

        Returns:
            Timestamp: A timestamp representing the current UTC time.
        """
        return cls(datetime.datetime.now(cls._UTC))

    @override
    def __str__(self) -> str:
        """Return a human-readable string representation
        of the timestamp.

        The output format is specified by the class variable
        `_STR_FORMAT`.

        Returns:
            str: A human-readable representation of the timestamp.
        """
        return self._dt.strftime(self._STR_FORMAT)

    @override
    def __eq__(self, other: object) -> bool:
        """Compare the timestamp with another time-based object relative
        to UTC.

        Args:
            other (object): A time-based object to compare against.

        Returns:
            bool: `True` if the timestamp represents the same moment
        in time as another time-based object.
        """
        if isinstance(other, Timestamp):
            return self._dt == other._dt

        if isinstance(other, datetime.datetime):
            try:
                return self._dt == other
            except TypeError:
                # The `other` `datetime` object is naive.
                return NotImplemented

        return NotImplemented

    def __lt__(self, other: object) -> bool:
        """Compare the timestamp with another time-based object relative
        to UTC.

        Args:
            other (object): A time-based object to compare against.

        Returns:
            bool: `True` if the timestamp represents an earlier moment
        than another time-based object.
        """
        if isinstance(other, Timestamp):
            return self._dt < other._dt

        if isinstance(other, datetime.datetime):
            try:
                return self._dt < other
            except TypeError:
                # The `other` `datetime` object is naive.
                return NotImplemented

        return NotImplemented

    def to_timezone(self, timezone: str) -> Timestamp:
        """Convert this timestamp to an IANA time zone.

        Args:
            timezone (str): An IANA time zone (e.g., 'Europe/London').

        Returns:
            Timestamp: A new timestamp representing the same moment
                in the specified IANA time zone.

        Raises:
            InvalidTimezoneError: If an IANA time zone is invalid.
        """
        try:
            tz = zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise InvalidTimezoneError(
                f"The IANA time zone '{timezone}' is invalid."
            ) from exc

        dt = self._dt.astimezone(tz)
        return Timestamp(dt)
