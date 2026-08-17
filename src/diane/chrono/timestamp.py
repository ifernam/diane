from __future__ import annotations

import datetime
import zoneinfo
from enum import Enum
from functools import total_ordering
from string import Template
from typing import ClassVar, cast, overload, override


class TimeError(Exception):
    """A general time error."""
    ...


class ValidationError(TimeError):
    """A time value could not be validated."""
    ...


class InvalidTimezoneError(TimeError):
    """An invalid time zone."""
    ...


class NonExistentTimeError(ValidationError):
    """A non-existent time."""
    ...


class InvalidISOFormatError(TimeError):
    """An invalid ISO 8601 format."""
    ...


class ShiftError(TimeError):
    """Failed to shift a timestamp."""
    ...


class DateFormattingError(TimeError):
    """A date formatting error."""
    ...


class OffsetFormattingError(TimeError):
    """An offset formatting error."""
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


class DateStrTemplate(Template):
    """Represents a template for advanced formatting of `date`
    objects."""

    delimiter: ClassVar[str] = '%'

    def format(
        self,
        d: datetime.date,
        t: datetime.time | None = None,
        midnight24: bool = False
    ) -> str:
        """Format a `date` object according to a specified template.

        The template can represent midnight as part of the previous day
        when requested. It is necessary to specify a time for this.

        Args:
            d (datetime.date): A `date` object.
            t (datetime.time): A `time` object. Required to handle
                midnight.
            midnight24 (bool): If `True`, midnight is considered
                to be part of the previous day. `False` by default.
                A time is required.

        Returns:
            str: A formatted `date` object.

        Raises:
            DateFormattingError: If a date could not be formatted
                (e.g., rolling back to the previous day would exceed
                `datetime.date.min`).
        """
        if midnight24:
            if t is None:
                raise DateFormattingError(
                    'Provide a time for midnight formatting.'
                )
            if t == datetime.time.min:
                try:
                    previous_day = d - datetime.timedelta(days=1)
                except OverflowError as exc:
                    raise DateFormattingError(
                        'Failed to format the date.'
                    ) from exc
                return previous_day.strftime(self.template)

        return d.strftime(self.template)


class TimeStrTemplate(Template):
    """Represents a template for advanced formatting of `time`
    objects."""

    delimiter: ClassVar[str] = '%'

    def format(self, t: datetime.time, midnight24: bool = False) -> str:
        """Format a `time` object according to a specified template.

        The template can represent midnight as '24:00' when requested.

        Args:
            t (datetime.time): A `time` object.
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


class OffsetStrTemplate(Template):
    """Represents a template for advanced formatting of the UTC offset
    of `datetime` objects."""

    delimiter: ClassVar[str] = '%'
    idpattern: ClassVar[str] = r'(?a:[_a-z][_a-z0-9]*|:z)'

    def format(
        self,
        dt: datetime.datetime,
        is_utc: bool | None = None,
        utc_z: bool = True,
        iana_timezone: str | None = None
    ) -> str:
        """Format the UTC offset of a `datetime` object according
        to a specified template.

        Args:
            dt (datetime.datetime): A `datetime` object.
            is_utc (bool | None): If `True`, a `datetime` object
                is treated as UTC-based.
            utc_z (bool): If `True`, the UTC offset is represented
                as 'Z'.
            iana_timezone (str): An IANA time zone name to substitute
                for '%iana', if present in the template. Optional.

        Returns:
            str: A formatted UTC offset.

        Raises:
            OffsetFormattingError: If `utc_z` is `True` and `is_utc`
                is not specified.
        """
        substitutions: dict[str, str] = {}

        if utc_z:
            if is_utc is None:
                raise OffsetFormattingError(
                    'Specify whether the `datetime` object is UTC-based.'
                )
            if is_utc:
                substitutions |= {'z': 'Z', ':z': 'Z'}

        if iana_timezone is not None:
            substitutions |= {'iana': iana_timezone}

        return dt.strftime(self.safe_substitute(substitutions))


@total_ordering
class Timestamp:
    """Represents a timestamp whose time zone is identified by an IANA
    time zone name.

    Attributes:
        _dt (datetime.datetime): An aware `datetime` object with
            a `ZoneInfo` time zone.
    """

    _UTC: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo('Etc/UTC')
    _UTC_IANA_NAMES: tuple[str, ...] = (
        'Etc/UCT', 'Etc/UTC', 'Etc/Universal', 'Etc/Zulu',
        'UCT', 'UTC', 'Universal', 'Zulu'
    )

    _READABLE_DATE_SPEC: str = '%Y.%m.%d'
    _DEFAULT_READABLE_TIME_SPEC: TimeSpec = TimeSpec.MINUTES
    _AUTO_READABLE_TIME_SPEC: TimeSpec | None = TimeSpec.MINUTES
    _READABLE_OFFSET_SPEC: str = 'UTC%:z'  # Supports '%iana'.
    _READABLE_UTC_OFFSET_Z: bool = False
    _READABLE_SEP: str = ' '
    _READABLE_OFFSET_SEP: str = ' '

    _ISO_DATE_SPEC: str = '%Y-%m-%d'
    _DEFAULT_ISO_TIME_SPEC: TimeSpec = TimeSpec.MICROSECONDS
    _AUTO_ISO_TIME_SPEC: TimeSpec | None = TimeSpec.MINUTES
    _ISO_OFFSET_SPEC: str = '%:z'
    _ISO_UTC_OFFSET_Z: bool = True
    _ISO_SEP: str = 'T'
    _ISO_OFFSET_SEP: str = ''

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

        Returns:
            str: A human-readable representation of the timestamp.
        """
        return self.readable()

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

    def __add__(self, other: object) -> Timestamp:
        """Shift the timestamp by a time increment.

        The increment is applied to the underlying UTC instant, not
        to the local wall-clock fields. This guarantees the result
        is always a real, existing local time (never a DST gap), but
        means the local time-of-day is not preserved across a DST
        transition (e.g. adding `timedelta(days=1)` may land
        on a different wall-clock hour than the original).

        Args:
            other (object): A time increment
                (e.g. `datetime.timedelta`).

        Returns:
            Timestamp: A shifted timestamp.

        Raises:
            ShiftError: If the timestamp could not be shifted
                by an increment.
        """
        if isinstance(other, datetime.timedelta):
            dt_utc = self._dt.astimezone(self._UTC)
            try:
                dt_utc_shifted = dt_utc + other
                dt_shifted = dt_utc_shifted.astimezone(self._dt.tzinfo)
            except OverflowError as exc:
                raise ShiftError(
                    f"Failed to shift '{self}' by '{other}'."
                ) from exc
            return Timestamp(dt_shifted)

        return NotImplemented

    @overload
    def __sub__(self, other: datetime.timedelta) -> Timestamp:
        ...

    @overload
    def __sub__(self, other: Timestamp) -> datetime.timedelta:
        ...

    def __sub__(self, other: object) -> Timestamp | datetime.timedelta:
        """Shift the timestamp by a time decrement or return
        the difference between two timestamps.

        - The shift operation is implemented using `__add__`.
        - The difference is calculated by comparing the underlying UTC
          instants.

        Args:
            other (object): A time decrement for shifting
                (e.g. `datetime.timedelta`), or another timestamp for
                calculating the difference.

        Returns:
            Timestamp: A shifted timestamp when `other`
                is a `timedelta`.
            datetime.timedelta: The difference between two timestamps
                when `other` is a `Timestamp`.

        Raises:
            ShiftError: If the timestamp could not be shifted
                by a decrement.
        """
        if isinstance(other, datetime.timedelta):
            return self + -other

        if isinstance(other, Timestamp):
            self_dt_utc = self._dt.astimezone(self._UTC)
            other_dt_utc = other._dt.astimezone(self._UTC)
            return self_dt_utc - other_dt_utc

        return NotImplemented

    def date_iso(self, midnight24: bool = False) -> str:
        """Return a string representing the date of the timestamp
        in the ISO 8601 format.

        Args:
            midnight24 (bool): If `True`, midnight is considered
                to be part of the previous day. `False` by default.

        Returns:
            str: An ISO 8601 date string.

        Raises:
            DateFormattingError: If the date could not be formatted
                (e.g., rolling back to the previous day would exceed
                `datetime.date.min`).
        """
        template = DateStrTemplate(self._ISO_DATE_SPEC)
        dt = self._dt
        return template.format(dt.date(), dt.time(), midnight24)

    def date_readable(self, midnight24: bool = False) -> str:
        """Return a string representing the date of the timestamp
        in the human-readable format.

        Args:
            midnight24 (bool): If `True`, midnight is considered
                to be part of the previous day. `False` by default.

        Returns:
            str: A human-readable date string.

        Raises:
            DateFormattingError: If the date could not be formatted
                (e.g., rolling back to the previous day would exceed
                `datetime.date.min`).
        """
        template = DateStrTemplate(self._READABLE_DATE_SPEC)
        dt = self._dt
        return template.format(dt.date(), dt.time(), midnight24)

    def _time_str(
        self,
        default_spec: TimeSpec,
        auto_spec: TimeSpec | None,
        spec: TimeSpec | None = None,
        midnight24: bool = False
    ) -> str:
        """Return a string representing the time of the timestamp
        according to a given specification.

        Args:
            default_spec (TimeSpec): A default specification. Used
                if `spec` and `auto_spec` are not specified.
            auto_spec (TimeSpec | None): Defines a minimal precision
                for the string representation of the timestamp.
            spec (TimeSpec | None): A time specification. If `None`,
                selects the specification automatically according
                to `auto_spec` and the precision of the timestamp.
            midnight24 (bool): If `True`, represents midnight as '24:00'
                rather than '00:00'. `False` by default.

        Returns:
            str: A string representation of the time of the timestamp.
        """
        t = self._dt.time()
        if spec is None:
            if auto_spec is not None:
                if t.microsecond or auto_spec is TimeSpec.MICROSECONDS:
                    spec = TimeSpec.MICROSECONDS
                elif t.second or auto_spec is TimeSpec.SECONDS:
                    spec = TimeSpec.SECONDS
                elif t.minute or auto_spec is TimeSpec.MINUTES:
                    spec = TimeSpec.MINUTES
                else:
                    spec = TimeSpec.HOURS
            else:
                spec = default_spec
        iso_str = TimeStrTemplate(spec.value).format(t, midnight24)
        return iso_str

    def time_iso(
        self, spec: TimeSpec | None = None, midnight24: bool = False
    ) -> str:
        """Return a string representing the time of the timestamp
        in the ISO 8601 format.

        Args:
            spec (TimeSpec | None): A time specification. If `None`,
                selects the specification automatically according
                to `_AUTO_ISO_TIME_SPEC` and the precision
                of the timestamp.
            midnight24 (bool): If `True`, represents midnight as '24:00'
                rather than '00:00'. `False` by default.

        Returns:
            str: An ISO 8601 time string.
        """
        return self._time_str(
            self._DEFAULT_ISO_TIME_SPEC, self._AUTO_ISO_TIME_SPEC,
            spec, midnight24
        )

    def time_readable(
        self, spec: TimeSpec | None = None, midnight24: bool = False
    ) -> str:
        """Return a string representing the time of the timestamp
        in the human-readable format.

        Args:
            spec (TimeSpec | None): A time specification. If `None`,
                selects the specification automatically according
                to `_AUTO_READABLE_TIME_SPEC` and the precision
                of the timestamp.
            midnight24 (bool): If `True`, represents midnight as '24:00'
                rather than '00:00'. `False` by default.

        Returns:
            str: A human-readable time string.
        """
        return self._time_str(
            self._DEFAULT_READABLE_TIME_SPEC, self._AUTO_READABLE_TIME_SPEC,
            spec, midnight24
        )

    def offset_iso(self) -> str:
        """Return a string representing the UTC offset of the timestamp
        in the ISO 8601 format.

        If the timestamp's time zone is one of the UTC aliases defined
        in `_UTC_IANA_NAMES` and `_ISO_UTC_OFFSET_Z` is `True`,
        the offset is formatted as 'Z'.

        Returns:
            str: An ISO 8601 offset string.
        """
        return OffsetStrTemplate(self._ISO_OFFSET_SPEC).format(
            self._dt,
            cast(zoneinfo.ZoneInfo, self._dt.tzinfo).key
                in self._UTC_IANA_NAMES,
            self._ISO_UTC_OFFSET_Z
        )

    def offset_readable(self) -> str:
        """Return a string representing the UTC offset of the timestamp
        in the human-readable format.

        Returns:
            str: A human-readable offset string.
        """
        iana_timezone = cast(zoneinfo.ZoneInfo, self._dt.tzinfo).key
        return OffsetStrTemplate(self._READABLE_OFFSET_SPEC).format(
            self._dt,
            iana_timezone in self._UTC_IANA_NAMES,
            self._READABLE_UTC_OFFSET_Z,
            iana_timezone
        )

    def iso(
        self,
        time_spec: TimeSpec | None = None,
        midnight24: bool = False
    ) -> str:
        """Return a string representing the timestamp in the ISO 8601
        format.

        Args:
            time_spec (TimeSpec | None): A time specification.
                If `None`, selects the specification automatically
                according to `_AUTO_ISO_TIME_SPEC` and the precision
                of the timestamp.
            midnight24 (bool): If `True`, represents midnight as '24:00'
                of the previous day. `False` by default.

        Returns:
            str: An ISO 8601 string.

        Raises:
            DateFormattingError: If the date could not be formatted
                (e.g., rolling back to the previous day would exceed
                `datetime.date.min`).
        """
        d_str = self.date_iso(midnight24)
        t_str = self.time_iso(time_spec, midnight24)
        o_str = self.offset_iso()
        return f'{d_str}{self._ISO_SEP}{t_str}{self._ISO_OFFSET_SEP}{o_str}'

    def readable(
        self,
        time_spec: TimeSpec | None = None,
        midnight24: bool = False
    ) -> str:
        """Return a string representing the timestamp
        in the human-readable format.

        Args:
            time_spec (TimeSpec | None): A time specification.
                If `None`, selects the specification automatically
                according to `_AUTO_READABLE_TIME_SPEC` and
                the precision of the timestamp.
            midnight24 (bool): If `True`, represents midnight as '24:00'
                of the previous day. `False` by default.

        Returns:
            str: A human-readable timestamp representation.

        Raises:
            DateFormattingError: If the date could not be formatted
                (e.g., rolling back to the previous day would exceed
                `datetime.date.min`).
        """
        d_str = self.date_readable(midnight24)
        t_str = self.time_readable(time_spec, midnight24)
        o_str = self.offset_readable()
        return (
            f'{d_str}{self._READABLE_SEP}{t_str}'
            f'{self._READABLE_OFFSET_SEP}{o_str}'
        )

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
