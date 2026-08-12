from __future__ import annotations

import datetime
import zoneinfo
from enum import Enum
from functools import total_ordering
from string import Template
from typing import ClassVar, cast, override


class TimeError(Exception):
    """A general time error."""
    ...


class ValidationError(TimeError):
    """A time value could not be validated."""
    ...


class InvalidTimezoneError(ValidationError):
    """An invalid time zone."""
    ...


class NonExistentTimeError(ValidationError):
    """A non-existent time."""
    ...


class InvalidISOFormatError(TimeError):
    """An invalid ISO 8601 format."""
    ...


class TimezoneConversionError(TimeError):
    """Failed to convert a time zone."""
    ...


class RoundingError(TimeError):
    """A rounding error."""
    ...


class TimeSpec(Enum):
    """Specifies the precision of an ISO 8601 time representation."""

    HOURS = '%H'
    MINUTES = '%H:%M'
    SECONDS = '%H:%M:%S'
    MICROSECONDS = '%H:%M:%S.%f'


class TimeStrTemplate(Template):
    """Represents a template for advanced formatting of `time`
    objects."""

    delimiter: ClassVar[str] = '%'

    def format(self, t: datetime.time, midnight24: bool = False) -> str:
        """Format a `time` object according to a specified template.

        The template can represent midnight as '24:00' when requested.

        Args:
            dt (datetime.time): A `time` object.
            midnight24 (bool): If `True` and the `time` object refers
                to midnight, replaces '%H' with '24'.

        Returns:
            str: A formatted `time` object.
        """
        template = (
            self.safe_substitute(H='24')
            if midnight24 and t == datetime.time.min
            else self.template
        )
        return t.strftime(template)

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
    _DEFAULT_ISO_TIME_SPEC: TimeSpec = TimeSpec.MICROSECONDS
    _AUTO_ISO_TIME_SPEC: TimeSpec | None = TimeSpec.MINUTES

    _dt: datetime.datetime

    @staticmethod
    def _validate(dt: datetime.datetime) -> None:
        """Check whether a `datetime` object is aware, uses a `ZoneInfo`
        time zone and represents an existing time.

        Args:
            dt (datetime.datetime): A `datetime` object to validate.

        Raises:
            ValidationError: If a `datetime` object could not
                be validated.
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

        try:
            dt_utc = dt.astimezone(Timestamp._UTC)
            dt_roundtripped = dt_utc.astimezone(dt.tzinfo)
        except OverflowError as exc:
            raise ValidationError(
                f"Failed to validate the `datetime` object '{dt.isoformat()} "
                f"{dt.tzinfo.key}'.") from exc
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
            ValidationError: If a `datetime` object could not
                be validated.
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

    @classmethod
    def from_iso_iana(cls, iso_str: str, timezone: str) -> Timestamp:
        """Create a timestamp from an ISO 8601 string with an offset
        and an IANA time zone.

        The method verifies that the offset is consistent with
        the actual offset of the IANA zone at that moment. If they
        match, the returned timestamp stores the local time in the given
        IANA time zone.

        Args:
            iso_str: An ISO 8601 string that includes an offset
                (e.g., '2026-08-10T19:55Z', '2026-08-10T19:55+00:00',
                '2026-08-10T15:55-04:00').
            timezone: An IANA time zone name (e.g., 'Etc/UTC',
                'America/New_York').

        Returns:
            A timestamp representing the time provided in a specified
            IANA time zone.

        Raises:
            InvalidISOFormatError: If an ISO 8601 string is invalid.
            InvalidTimezoneError: If an IANA time zone is invalid,
                an ISO 8601 string has no offset, or its offset does not
                match the offset of an IANA time zone.
            ValidationError: If a timestamp could not be validated.
            NonExistentTimeError: If an ISO 8601 string with an IANA
                time zone represents a non-existent time.
        """
        try:
            dt_parsed = datetime.datetime.fromisoformat(iso_str)
        except ValueError as exc:
            raise InvalidISOFormatError(
                f"The string '{iso_str}' does not comply with ISO 8601."
            ) from exc

        if dt_parsed.utcoffset() is None:
            raise InvalidTimezoneError(
                f"The ISO 8601 string '{iso_str}' has no offset."
            )

        try:
            tz = zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise InvalidTimezoneError(
                f"The IANA time zone '{timezone}' is invalid."
            ) from exc

        naive_wall = dt_parsed.replace(tzinfo=None)
        # Try `fold=0` first.
        dt_candidate = naive_wall.replace(tzinfo=tz, fold=0)
        if dt_candidate.utcoffset() != dt_parsed.utcoffset():
            # Try `fold=1`.
            dt_candidate = naive_wall.replace(tzinfo=tz, fold=1)
            if dt_candidate.utcoffset() != dt_parsed.utcoffset():
                raise InvalidTimezoneError(
                    f"The offset in '{iso_str}' does not match the IANA zone "
                    f"'{timezone}'."
                )

        return cls(dt_candidate)

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

    def time_iso(
        self, spec: TimeSpec | None = None, midnight24: bool = False
    ) -> str:
        """Return a string representing the time of the timestamp
        in the ISO 8601 format.

        Args:
            spec (TimeSpec | None): A time specification. If `None`,
                select the specification automatically according
                to `_AUTO_ISO_TIME_SPEC` and the precision
                of the timestamp.

            midnight24 (bool): If `True`, represents midnight as '24:00'
                rather than '00:00'. `False` by default.

        Returns:
            str: An ISO 8601 time string.
        """
        t = self._dt.time()
        if spec is None:
            if (auto_spec := self._AUTO_ISO_TIME_SPEC) is not None:
                if t.microsecond or auto_spec is TimeSpec.MICROSECONDS:
                    spec = TimeSpec.MICROSECONDS
                elif t.second or auto_spec is TimeSpec.SECONDS:
                    spec = TimeSpec.SECONDS
                elif t.minute or auto_spec is TimeSpec.MINUTES:
                    spec = TimeSpec.MINUTES
                else:
                    spec = TimeSpec.HOURS
            else:
                spec = self._DEFAULT_ISO_TIME_SPEC
        iso_str = TimeStrTemplate(spec.value).format(t, midnight24)
        return iso_str

    def iso(self) -> str:
        """Return a string representing the timestamp in ISO 8601
        format.

        Returns:
            str: An ISO 8601 string.
        """
        return self._dt.isoformat()

    @property
    def iana(self) -> str:
        """Return the IANA time zone of the timestamp.

        Returns:
            str: The IANA time zone.
        """
        return cast(zoneinfo.ZoneInfo, self._dt.tzinfo).key

    def to_timezone(self, timezone: str) -> Timestamp:
        """Convert this timestamp to an IANA time zone.

        Args:
            timezone (str): An IANA time zone (e.g., 'Europe/London').

        Returns:
            Timestamp: A new timestamp representing the same moment
                in the specified IANA time zone.

        Raises:
            InvalidTimezoneError: If an IANA time zone is invalid.
            TimezoneConversionError: If a time zone could not
                be converted.
        """
        try:
            tz = zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise InvalidTimezoneError(
                f"The IANA time zone '{timezone}' is invalid."
            ) from exc

        try:
            dt = self._dt.astimezone(tz)
        except OverflowError as exc:
            raise TimezoneConversionError(
                f"Failed to convert '{self}' to the time zone '{timezone}'."
            ) from exc
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
        dt_utc = self._dt.astimezone(self._UTC)
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
        dt_utc = self._dt.astimezone(self._UTC)
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
        dt_utc = self._dt.astimezone(self._UTC)
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
