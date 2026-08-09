from __future__ import annotations

import datetime
import zoneinfo
from functools import total_ordering
from typing import override


class TimeError(Exception):
    """A general time error."""
    ...


class InvalidTimezoneError(TimeError):
    """An invalid time zone."""
    ...


class NonExistentTimeError(TimeError):
    """A non-existent time."""
    ...


class RoundingError(TimeError):
    """A rounding error."""
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
    def _validate(dt: datetime.datetime) -> None:
        """Check whether a `datetime` object is aware, uses a `ZoneInfo`
        time zone and represents an existing time.

        Args:
            dt (datetime.datetime): A `datetime` object to validate.

        Raises:
            InvalidTimezoneError: If a `datetime` object is naive or its
                time zone is not a `ZoneInfo` instance.
            NonExistentTimeError: If a `datetime` object represents
                a non-existent time.
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

        dt_utc = dt.astimezone(Timestamp._UTC)
        dt_roundtripped = dt_utc.astimezone(dt.tzinfo)
        if dt_roundtripped != dt:
            raise NonExistentTimeError(
                f"The `datetime` object '{dt.isoformat()} {dt.tzinfo.key}' "
                "represents a non-existent time."
            )

    def __init__(self, dt: datetime.datetime) -> None:
        """Create a timestamp.

        Args:
            dt (datetime.datetime): An aware `datetime` object with
                a `ZoneInfo` time zone.

        Raises:
            InvalidTimezoneError: If a `datetime` object is naive
                or its time zone is not a `ZoneInfo` instance.
            NonExistentTimeError: If a `datetime` object represents
                a non-existent time.
        """
        self._validate(dt)
        self._dt = dt

    @classmethod
    def now(cls, timezone: str) -> Timestamp:
        """Create a new timestamp representing the current time
        in the provided time zone.

        Args:
            timezone (str): An IANA time zone.

        Returns:
            Timestamp: A timestamp representing the current time.

        Raises:
            InvalidTimezoneError: If the provided IANA time zone
                is invalid.
        """
        try:
            tz = zoneinfo.ZoneInfo(timezone)
            return cls(datetime.datetime.now(tz))
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise InvalidTimezoneError(
                f"The IANA time zone '{timezone}' is invalid."
            ) from exc

    @classmethod
    def now_utc(cls) -> Timestamp:
        """Create a new timestamp representing the current time in UTC.

        Returns:
            Timestamp: A timestamp representing the current UTC time.
        """
        return cls(datetime.datetime.now(cls._UTC))

    @override
    def __hash__(self) -> int:
        """Return a hash based on the UTC moment.

        Returns:
            int: A UTC-based hash.
        """
        return hash(self._dt)

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

    def floor_second(self) -> Timestamp:
        """Return a new timestamp with the fractional second removed.

        Any fractional second is discarded.

        Returns:
            Timestamp: A new timestamp at the start of the second.

        Raises:
            RoundingError: If the timestamp could not be rounded down
                to the nearest second.
        """
        try:
            dt_utc = self._dt.astimezone(self._UTC)
        except OverflowError as exc:
            raise RoundingError(
                f"Failed to round '{self}' down to the nearest second."
            ) from exc
        dt_utc_floor = dt_utc.replace(microsecond=0)
        try:
            dt_floor = dt_utc_floor.astimezone(self._dt.tzinfo)
        except OverflowError as exc:
            raise RoundingError(
                f"Failed to round '{self}' down to the nearest second."
            ) from exc
        return Timestamp(dt_floor)

    def ceil_second(self) -> Timestamp:
        """Return a new timestamp rounded up to the nearest second.

        Return the timestamp unchanged if it is already at the start
        of a second; otherwise, round it up to the next second.

        Returns:
            Timestamp: A new timestamp at the start of a second.

        Raises:
            RoundingError: If the timestamp could not be rounded up
                to the nearest second.
        """
        try:
            dt_utc = self._dt.astimezone(self._UTC)
        except OverflowError as exc:
            raise RoundingError(
                f"Failed to round '{self}' up to the nearest second."
            ) from exc
        dt_utc_ceil = dt_utc.replace(microsecond=0)
        if dt_utc.microsecond:
            try:
                dt_utc_ceil += datetime.timedelta(seconds=1)
            except OverflowError as exc:
                raise RoundingError(
                    f"Failed to round '{self}' up to the nearest second."
                ) from exc
        try:
            dt_ceil = dt_utc_ceil.astimezone(self._dt.tzinfo)
        except OverflowError as exc:
            raise RoundingError(
                f"Failed to round '{self}' up to the nearest second."
            ) from exc
        return Timestamp(dt_ceil)

    def round_second(self) -> Timestamp:
        """Return a new timestamp rounded to the nearest second.

        Use half-up rounding: round up when the fractional second is
        at least 0.5 seconds.

        Returns:
            Timestamp: A new timestamp rounded to a whole second.

        Raises:
            RoundingError: If the timestamp could not be rounded
                to the nearest second.
        """
        try:
            dt_utc = self._dt.astimezone(self._UTC)
        except OverflowError as exc:
            raise RoundingError(
                f"Failed to round '{self}' to the nearest second."
            ) from exc
        dt_utc_rounded = dt_utc.replace(microsecond=0)
        if dt_utc.microsecond >= 500:
            try:
                dt_utc_rounded += datetime.timedelta(seconds=1)
            except OverflowError as exc:
                raise RoundingError(
                    f"Failed to round '{self}' to the nearest second."
                ) from exc
        try:
            dt_rounded = dt_utc_rounded.astimezone(self._dt.tzinfo)
        except OverflowError as exc:
            raise RoundingError(
                f"Failed to round '{self}' to the nearest second."
            ) from exc
        return Timestamp(dt_rounded)
