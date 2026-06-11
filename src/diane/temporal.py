from __future__ import annotations
from dataclasses import dataclass, field
from functools import total_ordering
from typing import overload, Iterator
from enum import Enum, auto
import datetime
import zoneinfo
import tzlocal
import sys
import warnings
import bisect
import math



@dataclass(frozen=True, slots=True)
@total_ordering
class Timestamp:
    '''Local date and time along with the time zone.

    Contains an aware `datetime` timestamp with a `ZoneInfo` time zone.

    Requirements:
    - `tzinfo` must be `zoneinfo.ZoneInfo`.

    Notes:
    - This class strictly stores `tzinfo` as `zoneinfo.ZoneInfo`
      instances (IANA names).
    - Dependency: `tzlocal` (for detecting local IANA zone name).
    '''


    _UTC = zoneinfo.ZoneInfo('Etc/UTC')    # UTC time zone.


    _dt: datetime.datetime
    _dt_utc: datetime.datetime = field(init=False)
    _hash: int = field(init=False)
    

    @staticmethod
    def _validate_dt(dt: datetime.datetime) -> None:
        '''Validate that the `datetime` has a valid `ZoneInfo` timezone.

        Args:
            `dt`: The `datetime` to validate.

        Raises:
            `ValueError`: If the `datetime` is naive, has no UTC offset,
                or its timezone is not a `ZoneInfo` instance.
        '''

        if dt.tzinfo is None:
            raise ValueError(f'No time zone has been specified for the timestamp: \'{dt}\'.')
        
        try:
            utc_off = dt.utcoffset()
        except Exception as e:
            raise ValueError(f'Failed to get UTC offset for \'{dt}\'. {e}') from e
        
        if utc_off is None:
            raise ValueError(f'UTC offset is None for \'{dt}\' (invalid value).')

        if not isinstance(dt.tzinfo, zoneinfo.ZoneInfo):
            raise ValueError(
                f'Timezone must be a \'ZoneInfo\' instance, got \'{type(dt.tzinfo).__name__}\' '
                f'for \'{dt}\'.'
            )


    def __post_init__(self) -> None:

        object.__setattr__(self, '_dt_utc', self._dt.astimezone(Timestamp._UTC))
        
        try:
            Timestamp._validate_dt(self._dt)
            Timestamp._validate_dt(self._dt_utc)
        except ValueError as e:
            raise ValueError(f'The timestamp \'{self}\' has been set incorrectly. {e}') from e
        
        object.__setattr__(self, '_hash', hash(self._dt_utc))
    

    def __hash__(self) -> int:
        '''Return the hash value based on the UTC moment
        of the timestamp.
        
        Don't take time zones into account.
        '''

        return self._hash
        
    
    def __str__(self) -> str:
        '''Return the user-readable string representation of this
        timestamp.
        
        Returns:
            `str`: String representation of the timestamp.
        '''

        dt_local = self._dt.replace(microsecond=0)
        date_part = dt_local.strftime(r'%Y.%m.%d %H:%M:%S')
        offset = dt_local.utcoffset()
        if offset is None:
            tz_str = ''
        elif offset == datetime.timedelta():
            tz_str = 'UTC'
        else:
            sign = '+' if offset.total_seconds() >= 0 else '-'
            total_seconds = abs(offset.total_seconds())
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            if minutes == 0:
                tz_str = f'UTC{sign}{hours}'
            else:
                tz_str = f'UTC{sign}{hours}:{minutes:02d}'
        return f'{date_part} {tz_str}'.strip()
    

    @property
    def datetime(self) -> datetime.datetime:
        '''Return the `datetime` object of this timestamp.

        Returns:
            `datetime.datetime`: The `datetime` object.
        '''

        return self._dt
    

    @property
    def datetime_iso(self) -> str:
        '''Return the timestamp in ISO 8601 format in the time zone
        in which it was recorded.
        
        Returns:
            ISO 8601 formatted string
            (e.g., '2026-03-13T15:30:00+02:00').
        '''
        
        return self._dt.isoformat()


    @property
    def date_iso(self) -> str:
        '''Return the date in ISO 8601 format in the time zone in which
        it was recorded.
        
        Returns:
            ISO 8601 formatted date string (e.g., '2026-03-13').
        '''

        return self._dt.date().isoformat()
    

    def time_iso(self, allow_24_midnight: bool = False, offset: bool = True) -> str:
        '''Return the time in ISO 8601 format in the time zone
        in which it was recorded.

        Args:
            `allow_24_midnight` (`bool`): If `True` and the time
                is exactly  midnight ('00:00:00'), represent it
                as '24:00:00'. Defaults to `True`.
            `offset` (`bool`): If `True`, include the UTC offset.
                Defaults to `True`.

        Returns:
            `str`: ISO 8601 formatted string (e.g., '15:30:00+02:00'
            or '24:00:00+02:00').
        '''

        if offset:
            time_str = self._dt.isoformat().partition('T')[2]
        else:
            time_str = self._dt.time().isoformat()
        
        if allow_24_midnight and self.is_midnight:
            time_str = time_str.replace('00:00:00', '24:00:00', 1)
        
        return time_str


    @property
    def date_string(self) -> str:
        '''Return the date in a user-friendly format in the time zone
        in which it was recorded.

        Returns:
            `str`: The date string (e.g., 'March 13, 2026').
        '''

        # Use '%-d' for Unix, '%#d' for Windows, or remove leading zero
        # manually if neither is supported.
        try:
            return self._dt.strftime(r'%B %-d, %Y')
        except ValueError:
            # On Windows, fallback to removing leading zero from '%d'.
            return self._dt.strftime(r'%B %d, %Y').replace(' 0', ' ')
    

    @property
    def utc_iso(self) -> str:
        '''Return the ISO 8601 string representation of this timestamp
        in UTC.

        Returns:
            A string like '2026-03-13T12:00:00Z'.
        '''
    
        return self._dt_utc.replace(tzinfo=None).isoformat() + 'Z'
    

    @property
    def timezone_iana(self) -> str:
        '''Return the IANA time zone name of this timestamp.

        Returns:
            The IANA zone key (e.g., 'America/New_York').

        Raises:
            `ValueError`: If the stored time zone is not a `ZoneInfo`
                instance (should never happen).
        '''

        if not isinstance(self._dt.tzinfo, zoneinfo.ZoneInfo):
            raise ValueError('The time zone has been set incorrectly.')

        return self._dt.tzinfo.key
    

    def is_midnight(self) -> bool:
        '''Return `True` if this timestamp represents midnight.'''

        return self._dt.time() == datetime.time.min
    

    def to_timezone(self, timezone_iana: str) -> Timestamp:
        '''Convert this timestamp to the specified IANA time zone.

        Args:
            `timezone_iana`: IANA time zone name
            (e.g., 'America/New_York').

        Returns:
            A new `Timestamp` representing the same moment
            in the specified zone.

        Raises:
            `ValueError`: If the IANA zone name is invalid.
        '''

        try:
            tz = zoneinfo.ZoneInfo(timezone_iana)
        except zoneinfo.ZoneInfoNotFoundError as e:
            raise ValueError(f'Invalid IANA time zone: \'{timezone_iana}\'.') from e

        dt = self._dt.astimezone(tz)
        return Timestamp(dt)


    def to_utc(self) -> Timestamp:
        '''Convert this timestamp to UTC.

        Returns:
            A new `Timestamp` representing the same moment in UTC.
        '''
        
        return Timestamp(self._dt_utc)
    

    def round_to_second(self) -> Timestamp:
        '''Return a new `Timestamp` rounded to the nearest second.
        
        Returns:
            `Timestamp`: A new `Timestamp` with the time rounded
            to the nearest second.
        '''

        if self._dt.microsecond < 500_000:
            return Timestamp(self._dt.replace(microsecond=0))
        else:
            dt_rounded = self._dt + datetime.timedelta(seconds=1)
            return Timestamp(dt_rounded.replace(microsecond=0))
            
    

    def __eq__(self, other: object) -> bool:
        '''Return `True` if this timestamp represents the same moment
        in time as another one (based on UTC).
        
        Don't take time zones into account.
        '''

        if not isinstance(other, Timestamp):
            return NotImplemented

        return self._dt_utc == other._dt_utc
    

    def __lt__(self, other: object) -> bool:
        '''Return `True` if this timestamp is earlier than another one
        in absolute (UTC) time.'''
    
        if not isinstance(other, Timestamp):
            return NotImplemented

        return self._dt_utc < other._dt_utc
    

    def __add__(self, other: datetime.timedelta) -> Timestamp:
        '''Return a new `Timestamp` shifted forward by the given
        `timedelta`.

        Args:
            `other`: The `timedelta` to add.

        Returns:
            A new `Timestamp` representing the moment `other` later than
            this one.
        '''

        if not isinstance(other, datetime.timedelta):
            return NotImplemented

        dt_utc_new = self._dt_utc + other
        tz = self._dt.tzinfo
        dt_new = dt_utc_new.astimezone(tz)
        return Timestamp(dt_new)
    

    @overload
    def __sub__(self, other: datetime.timedelta) -> Timestamp: ...


    @overload
    def __sub__(self, other: Timestamp) -> datetime.timedelta: ...
    

    def __sub__(self, other: datetime.timedelta | Timestamp) -> Timestamp | datetime.timedelta:
        '''Return the difference between two timestamps
        or a shifted timestamp.

        - If `other` is a `timedelta`, return a new `Timestamp` shifted
            backward by that amount.
        - If `other` is a `Timestamp`, return the `timedelta` between
            this and the other timestamp (`self - other`).

        Return `NotImplemented` for unsupported types.

        Args:
            `other`: A `timedelta` or another `Timestamp`.

        Returns:
            `Timestamp` if `other` is `timedelta`, else `timedelta`.
        '''

        if isinstance(other, datetime.timedelta):
            return self + (-other)

        if isinstance(other, Timestamp):
            return self._dt_utc - other._dt_utc

        return NotImplemented
    

    @classmethod
    def from_utc(cls, dt_iso: str) -> Timestamp:
        '''Create a `Timestamp` in UTC from an ISO 8601 string.

        The string may be naive (assumed UTC), end with 'Z', or have
        a zero offset. Non-zero offsets are rejected.

        Accepted examples:
         - '2026-01-20T10:36'         (assumed UTC),
         - '2026-01-20T10:36Z'        (UTC),
         - '2026-01-20T10:36+00:00'   (zero offset).

        Args:
            `dt_iso`: ISO 8601 datetime string.

        Returns:
            A new `Timestamp` representing the given moment in UTC.

        Raises:
            `ValueError`: If the string cannot be parsed,
                or if it contains a non-zero offset.
 
        '''
        
        # Manually replace the suffix 'Z' with zero offset '+00:00'
        # for older versions of Python (< 3.11).
        if sys.version_info < (3, 11) and dt_iso.endswith('Z'):
            dt_iso = dt_iso[:-1] + '+00:00'
        
        try:
            dt = datetime.datetime.fromisoformat(dt_iso)
        except ValueError as e:
            raise ValueError(f'Invalid ISO 8601 datetime string: {dt_iso}') from e

        if dt.tzinfo is None:
            # Naive: interpret as UTC per method contract.
            dt = dt.replace(tzinfo=Timestamp._UTC)
        else:
            # Ensure the moment is UTC (offset zero).
            if dt.utcoffset() != datetime.timedelta(0):
                raise ValueError(f"The timestamp '{dt_iso}' is not in UTC.")
            # Convert to 'ZoneInfo('Etc/UTC')' to satisfy strict storage
            # invariant.
            dt = dt.astimezone(Timestamp._UTC)

        return cls(dt)
    

    @classmethod
    def from_iso_iana(cls, iso_str: str, iana_zone: str) -> Timestamp:
        '''Create a timestamp from an ISO 8601 string with offset
        and an IANA time zone.

        The ISO string must contain an offset
        (e.g., '2026-03-04T15:15+03:00'). The method verifies that
        the offset is consistent with the actual offset of the IANA zone
        at that moment. If they match, the returned timestamp stores
        the local time in the given IANA zone.

        Args:
            `iso_str`: ISO 8601 datetime string that includes an offset
                (or 'Z' for UTC).
            `iana_zone`: IANA time zone name (e.g., 'Europe/Moscow').

        Returns:
            A new `Timestamp` object representing the same moment but
            normalised to the specified IANA zone.

        Raises:
            `ValueError`: If the ISO string cannot be parsed,
                if the IANA zone is unknown, or if the offset in the ISO
                string does not match the zone's offset for that moment.
        '''
        
        # Normalise 'Z' to '+00:00' for Python < 3.11.
        if sys.version_info < (3, 11) and iso_str.endswith('Z'):
            iso_str = iso_str[:-1] + '+00:00'

        # Parse the ISO string (must include offset).
        try:
            dt_iso = datetime.datetime.fromisoformat(iso_str)
        except ValueError as e:
            raise ValueError(f'Invalid ISO 8601 datetime string: \'{iso_str}\'.') from e

        if dt_iso.tzinfo is None:
            raise ValueError('ISO string must contain an offset (e.g., \'+03:00\' or \'Z\').')

        # Convert to UTC to obtain the absolute moment.
        dt_utc = dt_iso.astimezone(cls._UTC)

        # Create the target IANA time zone.
        try:
            tz = zoneinfo.ZoneInfo(iana_zone)
        except zoneinfo.ZoneInfoNotFoundError as e:
            raise ValueError(f'Invalid IANA time zone: \'{iana_zone}\'.') from e

        # Convert the UTC moment to the target zone.
        dt_local = dt_utc.astimezone(tz)

        # Verify that the offset from the ISO string matches the zone's offset.
        if dt_iso.utcoffset() != dt_local.utcoffset():
            raise ValueError(
                f'Offset from ISO string ({dt_iso.utcoffset()}) does not match the offset of zone '
                f'\'{iana_zone}\' ({dt_local.utcoffset()}) at that moment.'
            )

        # Return a new timestamp (the internal datetime is already in the target zone).
        return cls(dt_local)


    @classmethod
    def from_iso(
        cls, iso_str: str, default_date: datetime.date | None = None
    ) -> Timestamp:
        """Create a timestamp from an ISO 8601 string.

        The string must be naive (assumed local). The offset
        and the time zone is determined based on the local time zone.
        If the date is missing, `default_date` is used.
        If the `default_date` is set to `None`, the date defaults
        to today's date.

        Args:
            iso_str (str): ISO 8601 datetime string without an offset
                (e.g., '2026-01-20T10:36', '10:36').
            default_date (datetime.date | None): The date to use
                if the ISO string does not contain a date. Defaults
                to `None` (today's date).

        Returns:
            Timestamp: A new `Timestamp` representing the given local
            time in the local time zone.

        Raises:
            ValueError: If the ISO string cannot be parsed,
                or if it contains an offset (i.e., is not naive).

        TODO: Implement supporting ISO strings with offsets and verify
            that they are consistent with the local time zone.
        """

        try:
            dt_naive = datetime.datetime.fromisoformat(iso_str)
        except ValueError as e:
            try:
                # Try parsing as time only (e.g., '10:36').
                t = datetime.time.fromisoformat(iso_str)

                d = (
                    default_date if default_date is not None
                    else datetime.date.today()
                )
                dt_naive = datetime.datetime.combine(d, t)
            except ValueError as e2:
                raise ValueError(
                    f'Invalid ISO 8601 datetime string: \'{iso_str}\'.'
                ) from e2

        if dt_naive.utcoffset() is not None:
            raise ValueError('ISO string must not contain an offset.')
        if dt_naive.tzinfo is not None:
            raise ValueError('ISO string must be naive (no time zone).')

        local_tz = zoneinfo.ZoneInfo(tzlocal.get_localzone_name())
        dt_local = dt_naive.replace(tzinfo=local_tz)

        return cls(dt_local)


    @classmethod
    def midnight(cls, date: datetime.date, time_zone_iana: str) -> Timestamp:
        '''Create a timestamp representing midnight (start of the day)
        in the specified IANA time zone.

        Args:
            `date` (`datetime.date`): The calendar date.
            `time_zone_iana` (`str`): IANA time zone name
                (e.g., 'America/New_York').

        Returns:
            `Timestamp`: The timestamp set to '00:00:00' on the given
            date in the target zone.

        Raises:
            `ValueError`: If the IANA time zone name is invalid.
        '''
        
        try:
            tz = zoneinfo.ZoneInfo(time_zone_iana)
        except zoneinfo.ZoneInfoNotFoundError as e:
            raise ValueError(f'Invalid IANA time zone: \'{time_zone_iana}\'.') from e
        
        dt = datetime.datetime.combine(date, datetime.time.min, tz)
        ts = Timestamp(dt)
        return ts
    

    @classmethod
    def now(cls) -> Timestamp:
        '''Create a new `Timestamp` representing the current local time.

        Returns:
            A `Timestamp` set to the current date and time in the local
            time zone.

        Raises:
            `RuntimeError`: If the local time zone cannot be determined.
        '''

        try:
            tz = zoneinfo.ZoneInfo(tzlocal.get_localzone_name())
            return cls(datetime.datetime.now(tz))
        except Exception as e:
            raise RuntimeError(
                'Failed to determine local time zone.'
            ) from e
    

    @classmethod
    def now_utc(cls) -> Timestamp:
        '''Create a new `Timestamp` representing the current time
        in UTC.

        Returns:
            A `Timestamp` set to the current date and time in UTC.

        Raises:
            `RuntimeError`: If the UTC time cannot be obtained.
        '''
        
        try:
            return cls(datetime.datetime.now(Timestamp._UTC))
        except Exception as e:
            raise RuntimeError('Failed to determine UTC time.') from e



@dataclass(frozen=True, slots=True)
@total_ordering
class Endpoint:
    '''Represents an endpoint of a time interval or of a time set.'''
    

    class Kind(Enum):
        '''Represents an endpoint kind (finite/infinite).'''

        FINITE = 0    # A finite endpoint.
        INFINITE = 1  # An endpoint lies at infinity.


    class Side(Enum):
        '''Represents a side (start/end) of an endpoint.'''

        LEFT = -1  # An endpoint is the start of an interval or a time
                   # set.
        RIGHT = 1  # An endpoint is the end of an interval or a time
                   # set.
        

        def opposite(self) -> Endpoint.Side:
            '''Return the endpoint side opposite to this.

            Returns:
                `Endpoint.Side`: The opposite endpoint side.

            Raises:
                `AssertionError`: If the side is unknown.
            '''

            match self:
                case Endpoint.Side.LEFT:
                    return Endpoint.Side.RIGHT
                case Endpoint.Side.RIGHT:
                    return Endpoint.Side.LEFT
                case _:
                    raise AssertionError(f'The unknown endpoint side: \'{self}\'.')
    

    _kind: Kind                   # `FINITE`/`INFINITE`.
    _timestamp: Timestamp | None  # `Timestamp` for the `FINITE` kind,
                                  # `None` for `INFINITE`.
    _side: Side                   # `LEFT`/`RIGHT`.
    _included: bool | None        # `True`/`False` for the `FINITE`
                                  # kind, `None` for `INFINITE`.
    

    def _validate(self) -> None:
        '''Check that the endpoint has been set correctly.
        
        Raises:
            `ValueError`: If the endpoint has been set incorrectly.
        '''

        # Validate timestamp.
        if self._kind is Endpoint.Kind.FINITE and self._timestamp is None:
            raise ValueError(
                'The endpoint of the finite kind must have an explicitly specified timestamp.'
            )
        if self._kind is not Endpoint.Kind.FINITE and self._timestamp is not None:
            raise ValueError(
                'The endpoint of the infinite kind must not have an explicitly specified '
                'timestamp. It must be \'None\'.'
            )
        
        # Validate including option.
        if self._kind is Endpoint.Kind.INFINITE and self._included is not None:
            raise ValueError(
                'A time interval or a time set cannot include or exclude the endpoint '
                'at infinity. \'included\' must be \'None\'.'
            )
    

    def _key(self):
        '''Return the sorting key for this endpoint for comparison with
        another endpoint.'''

        kind_key = self.side.value*self._kind.value
        timestamp_key = self._timestamp
        included_key = 0 if self._included else -self._side.value

        return (kind_key, timestamp_key, included_key)
    

    @staticmethod
    def _key_for_timestamps(point: Endpoint | Timestamp):
        '''Return the sorting key for the endpoint or timestamp
        for comparison with a timestamp.
        
        Args:
            `point` (`Endpoint | Timestamp`): The endpoint or timestamp
                for comparison.
        '''

        if isinstance(point, Endpoint):
            kind_key = point.side.value*point._kind.value
            timestamp_key = point._timestamp
            included_key = 0 if point._included is True else -1
            if point._side is Endpoint.Side.LEFT:
                included_key = -included_key

        elif isinstance(point, Timestamp):
            kind_key = Endpoint.Kind.FINITE.value
            timestamp_key = point
            included_key = 0

        else:
            return NotImplemented

        return (kind_key, timestamp_key, included_key)
        

    def __post_init__(self) -> None:
        try:
            self._validate()
        except ValueError as e:
            raise ValueError(f'The endpoint has been set incorrectly. {e}') from e
        
    
    @property
    def kind(self) -> Endpoint.Kind:
        '''Return the kind of this endpoint.

        It can either be finite and associated with a timestamp, or lie
        at infinity.
        
        Returns:
            `Endpoint.Kind`: Kind of the endpoint: `FINITE`/`INFINITE`.
        '''

        return self._kind
    

    @property
    def is_finite(self) -> bool:
        '''Return `True` if this endpoint is of the finite kind.
        
        Returns:
            `bool`: `True` if finite, otherwise `False`.
        '''

        return self._kind is Endpoint.Kind.FINITE
    
    
    @property
    def is_infinite(self) -> bool:
        '''Return `True` if this endpoint is of the infinite kind,
        i.e. lies at infinity (negative or positive).
        
        Returns:
            `bool`: `True` if infinite, otherwise `False`.
        '''

        return self._kind is Endpoint.Kind.INFINITE
    

    @property
    def timestamp(self) -> Timestamp:
        '''Return the timestamp if it is specified.
        
        Returns:
            `Timestamp`: The timestamp.

        Raises:
            `ValueError`: If the endpoint lies at infinity.
        '''

        if self._timestamp is None:
            raise ValueError('This endpoint lies at infinity and has no specified timestamp.')
        
        return self._timestamp
    

    @property
    def side(self) -> Endpoint.Side:
        '''Return the side of this endpoint (left/right).
        
        Returns:
            `Endpoint.Side`: Side of the endpoint:
                `LEFT`/`RIGHT`.
        '''

        return self._side
    

    @property
    def is_left(self) -> bool:
        '''Return `True` if this endpoint is on the left side of a time
        interval or time set.
        
        Returns:
            `bool`: `True` if on the left, otherwise `False`.
        '''

        return self.side is Endpoint.Side.LEFT
    

    @property
    def is_right(self) -> bool:
        '''Return `True` if this endpoint is on the right side of a time
        interval or time set.
        
        Returns:
            `bool`: `True` if on the right, otherwise `False`.
        '''

        return self.side is Endpoint.Side.RIGHT
    

    @property
    def is_included(self) -> bool:
        '''Return `True` if this endpoint is included in a time interval
        or time set.
        
        Returns:
            `bool`: `True` if this endpoint is included, otherwise
                `False`.

        Raises:
            `ValueError`: If this endpoint lies at infinity.
        '''

        if self._included is None:
            raise ValueError(
                'A time interval or a time set cannot include or exclude the endpoint at infinity.'
            )
        
        return self._included
        
    
    def __str__(self) -> str:
        '''Return the string representation of this endpoint.
        
        Returns:
            `str`: The string representation of the endpoint. '-∞'/'+∞'
                for infinite kinds.
        '''
     
        match self._kind:
            case Endpoint.Kind.FINITE:
                return str(self._timestamp)
            
            case Endpoint.Kind.INFINITE:
                # Return '-∞' or '+∞'.
                sign = '+' if self.side is Endpoint.Side.RIGHT else '-'
                return  sign + '\u221E'
        
        raise AssertionError(f'The unknown endpoint kind: \'{self._kind}\'.')
    

    def to_timezone(self, timezone_iana: str) -> Endpoint:
        '''Convert this endpoint to the specified IANA time zone.

        Args:
            `timezone_iana`: IANA time zone name
            (e.g., 'America/New_York').

        Returns:
            `Endpoint`: A new `Endpoint` representing the same moment
                in the specified zone.

        Raises:
            `ValueError`: If the IANA zone name is invalid.
        '''

        if self.is_infinite:
            return self
        
        return Endpoint(
            _kind=Endpoint.Kind.FINITE,
            _timestamp=self.timestamp.to_timezone(timezone_iana),
            _side=self.side,
            _included=self.is_included
        )
        

    def opposite(self) -> Endpoint:
        '''Return the endpoint opposite to this.
        
        The side and inclusion kind of the endpoint are reversed.
        
        Returns:
            `Endpoint`: The reversed endpoint.

        Raises:
            `ValueError`: If the endpoint cannot be reversed
                (e.g., it lies at infinity).
        '''

        if self.kind is Endpoint.Kind.INFINITE:
            raise ValueError('The endpoint at infinity cannot be reversed.')

        return Endpoint(
            _kind=Endpoint.Kind.FINITE,
            _timestamp=self.timestamp,
            _side=self.side.opposite(),
            _included=(not self.is_included)
        )
    

    def include(self) -> Endpoint:
        '''Return the included endpoint with the same timestamp
        and side.
        
        Returns:
            `Endpoint`: The included endpoint.

        Raises:
            `ValueError`: An endpoint at infinity cannot be included.
        '''

        if self.kind is Endpoint.Kind.INFINITE:
            raise ValueError('The endpoint at infinity cannot be included.')

        return Endpoint(
            _kind=Endpoint.Kind.FINITE,
            _timestamp=self.timestamp,
            _side=self.side,
            _included=True
        )
    

    def exclude(self) -> Endpoint:
        '''Return the excluded endpoint with the same timestamp
        and side.
        
        Returns:
            `Endpoint`: The excluded endpoint.

        Raises:
            `ValueError`: An endpoint at infinity cannot be included
                or excluded.
        '''

        if self.kind is Endpoint.Kind.INFINITE:
            raise ValueError('The endpoint at infinity cannot be included or excluded.')

        return Endpoint(
            _kind=Endpoint.Kind.FINITE,
            _timestamp=self.timestamp,
            _side=self.side,
            _included=False
        )


    def __eq__(self, other: object) -> bool:
        '''Return `True` if this endpoint represents the same moment
        in time (based on UTC) as another one and the same border kind
        (finite/infinite, left/right, included/excluded).
        
        If another object is a timestamp representing the same moment
        in time as this endpoint, return `True` only if this timestamp
        belongs to an interval or time set.

        Args:
            `other` (`Endpoint | Timestamp`): Another `Endpoint`
                or a timestamp.

        Returns:
            `bool`: `True` if the objects represent the same moment
                in time (and border kind).
        '''

        if isinstance(other, Endpoint):
            return self._key() == other._key()
        
        if isinstance(other, Timestamp):
            return Endpoint._key_for_timestamps(self) == Endpoint._key_for_timestamps(other)
    
        return NotImplemented
    

    def __lt__(self, other: object) -> bool:
        '''Return `True` if this endpoint is earlier than another one
        or another timestamp according to the ordering key.
        
        Args:
            `other` (`Endpoint | Timestamp`): Another `Endpoint`
                or a timestamp.

        Returns:
            `bool`: `True` if this object represents a moment in time
                earlier than another one.
        '''

        if isinstance(other, Endpoint):
            return self._key() < other._key()
        
        if isinstance(other, Timestamp):
            return Endpoint._key_for_timestamps(self) < Endpoint._key_for_timestamps(other)
    
        return NotImplemented
    

    def __sub__(self, other: Endpoint | Timestamp) -> Duration:
        '''Calculate the time difference between this endpoint
        and another endpoint or timestamp.
        
        Args:
            `other` (`Endpoint | Timestamp`): The endpoint
                or the timestamp.

        Returns:
            `Duration`: The calculated time difference. May be finite,
            infinite, or undefined.
        '''

        if isinstance(other, Endpoint):
            infinity_key = self.side.value*self.kind.value - other.side.value*other.kind.value

            if infinity_key > 0:
                return Duration.pos_inf()
            elif infinity_key < 0:
                return Duration.neg_inf()
            else:
                if self.is_infinite:
                    # The difference between infinities is not defined.
                    return Duration.undefined()
                
                delta = self.timestamp - other.timestamp
                return Duration(_kind=Duration.Kind.FINITE, _value=delta)
        
        if isinstance(other, Timestamp):
            if self.is_infinite:
                if self.is_right:
                    return Duration.pos_inf()
                else:
                    return Duration.neg_inf()
            else:
                delta = self.timestamp - other
                return Duration(_kind=Duration.Kind.FINITE, _value=delta)
        
        return NotImplemented
    

    def __rsub__(self, other: Timestamp) -> Duration:
        '''Calculate the time difference between this endpoint
        and the timestamp.
        
        Args:
            `other` (`Timestamp`): The timestamp.

        Returns:
            `Duration`: The calculated time difference. May be infinite.
        '''
        
        if isinstance(other, Timestamp):
            if self.is_infinite:
                if self.is_right:
                    return Duration.neg_inf()
                else:
                    return Duration.pos_inf()
            else:
                delta = other - self.timestamp
                return Duration(_kind=Duration.Kind.FINITE, _value=delta)
        
        return NotImplemented
    
    
    @classmethod
    def left_finite(cls, timestamp: Timestamp, included: bool=True) -> Endpoint:
        '''Create a left-sided finite endpoint.
        
        Args:
            `timestamp` (`Timestamp`): The timestamp.
            `included` (`bool`): The `True`/`False` option specifies
                whether the endpoint is included in or excluded from
                the interval or the time set. Defaults to `True`
                (included).

        Returns:
            `Endpoint`: New endpoint.
        '''

        return cls(
            _kind=Endpoint.Kind.FINITE,
            _timestamp=timestamp,
            _side=Endpoint.Side.LEFT,
            _included=included
        )
    
    @classmethod
    def right_finite(cls, timestamp: Timestamp, included: bool=False) -> Endpoint:
        '''Create a right-sided finite endpoint.
        
        Args:
            `timestamp` (`Timestamp`): The timestamp.
            `included` (`bool`): The `True`/`False` option specifies
                whether the endpoint is included in or excluded from
                the interval or the time set. Defaults to `False`
                (excluded).

        Returns:
            `Endpoint`: New endpoint.
        '''

        return cls(
            _kind=Endpoint.Kind.FINITE,
            _timestamp=timestamp,
            _side=Endpoint.Side.RIGHT,
            _included=included
        )
        
    
    @classmethod
    def left_infinite(cls) -> Endpoint:
        '''Create a left-sided endpoint at infinity.
        
        Returns:
            `Endpoint`: New endpoint.
        '''

        return cls(
            _kind=Endpoint.Kind.INFINITE,
            _timestamp=None,
            _side=Endpoint.Side.LEFT,
            _included=None
        )
    

    @classmethod
    def right_infinite(cls) -> Endpoint:
        '''Create a right-sided endpoint at infinity.
        
        Returns:
            `Endpoint`: New endpoint.
        '''

        return cls(
            _kind=Endpoint.Kind.INFINITE,
            _timestamp=None,
            _side=Endpoint.Side.RIGHT,
            _included=None
        )



@dataclass(frozen=True, slots=True)
@total_ordering
class Duration:

    class Kind(Enum):
        '''Represents a duration kind (finite/infinite).'''

        UNDEFINED = -2
        NEG_INF = -1
        FINITE = 0 
        POS_INF = 1


    _INFINITE_KINDS = {
        Kind.NEG_INF,
        Kind.POS_INF
    }


    _kind: Kind = Kind.FINITE

    # `None` for andefined and infinite kinds.
    _value: datetime.timedelta | None = datetime.timedelta()


    def _validate(self) -> None:

        if self._kind is Duration.Kind.FINITE and self._value is None:
            raise ValueError(
                'The duration of the finite kind must have an explicitly specified value.'
            )
        if (
            (self._kind is Duration.Kind.UNDEFINED or self._kind in Duration._INFINITE_KINDS)
            and self._value is not None
        ):
            raise ValueError(
                'The duration of the undefined or infinite kind must not have an explicitly specified '
                'value. It must be \'None\'.'
            )


    def __post_init__(self) -> None:

        self._validate()


    def __bool__(self) -> bool:
        '''Return `True` if duration is defined and non-zero.'''

        return self._kind is not Duration.Kind.UNDEFINED and (self._kind is not Duration.Kind.FINITE or bool(self._value))


    def __str__(self) -> str:
        match self._kind:
            case Duration.Kind.UNDEFINED:
                return '?'
            case Duration.Kind.NEG_INF:
                # Return '-∞'.
                return '-\u221E'
            case Duration.Kind.FINITE:
                return str(self._value)
            case Duration.Kind.POS_INF:
                # Return '+∞'.
                return '+\u221E'
            case _:
                raise AssertionError(f'The unknown duration kind: \'{self._kind}\'.')


    def _key(self) -> tuple[int, datetime.timedelta | None]:
        '''Return the key for sorting endpoints.

        Undefined values are considered to be less than all others.'''

        return (self._kind.value, self._value)

    
    def __eq__(self, other: object) -> bool:

        if isinstance(other, Duration):
            return self._key() == other._key()

        if isinstance(other, datetime.timedelta):
            return self._key() == (Duration.Kind.FINITE.value, other)
        
        return NotImplemented
    

    def __lt__(self, other: object) -> bool:

        if isinstance(other, Duration):
            return self._key() < other._key()
        
        if isinstance(other, datetime.timedelta):
            return self._key() < (Duration.Kind.FINITE.value, other)
        
        return NotImplemented


    @property
    def is_defined(self) -> bool:
        return self._kind is not Duration.Kind.UNDEFINED
    

    @property
    def is_undefined(self) -> bool:
        return self._kind is Duration.Kind.UNDEFINED
    

    @property
    def is_finite(self) -> bool:
        return self._kind is Duration.Kind.FINITE


    @property
    def is_infinite(self) -> bool:
        return self._kind in Duration._INFINITE_KINDS
    

    @property
    def value(self) -> datetime.timedelta:

        if self._value is None:
            raise ValueError('The duration has no specified finite value.')

        return self._value
    

    def __neg__(self) -> Duration:

        if self._kind is Duration.Kind.UNDEFINED:
            return self

        return Duration(
            _kind=Duration.Kind(-self._kind.value),
            _value=(-self._value if self._value is not None else None)
        )
    

    def __abs__(self) -> Duration:

        if self._kind is Duration.Kind.UNDEFINED:
            return self
        
        return Duration(
            _kind=Duration.Kind(abs(self._kind.value)),
            _value=(abs(self._value) if self._value is not None else None)
        )
    

    def __add__(self, other: object) -> Duration:

        if isinstance(other, Duration):

            if self.is_undefined or other.is_undefined:
                return Duration.undefined()
            

            if self.is_finite and other.is_finite:
                return Duration(
                    _kind=Duration.Kind.FINITE, 
                    _value=(self.value + other.value)
                )

            if self.is_finite and other.is_infinite:
                return other

            if self.is_infinite and other.is_finite:
                return self
            
            if self.is_infinite and other.is_infinite:
                
                if self._kind is Duration.Kind.POS_INF and other._kind is Duration.Kind.POS_INF:
                    return Duration.pos_inf()
                
                if self._kind is Duration.Kind.NEG_INF and other._kind is Duration.Kind.NEG_INF:
                    return Duration.neg_inf()
                
                raise ValueError(
                    'The sum of positive and negative infinity is undefined.'
                )

        if isinstance(other, datetime.timedelta):
            if self.is_undefined:
                return Duration.undefined()

            if self.is_infinite:
                return self
            
            return Duration(_kind=Duration.Kind.FINITE, _value=(self.value + other))
        
        return NotImplemented
    

    __radd__ = __add__


    def __sub__(self, other: object) -> Duration:
        
        if isinstance(other, Duration | datetime.timedelta):
            if self.is_undefined:
                return Duration.undefined()

            return self + -other
        
        return NotImplemented
    
    
    def __rsub__(self, other: object) -> Duration:

        if isinstance(other, datetime.timedelta):
            if self.is_undefined:
                return Duration.undefined()

            if self.is_finite:
                return Duration(_kind=Duration.Kind.FINITE, _value=(other - self.value))
            else:
                return -self
            
        return NotImplemented
    

    def __truediv__(self, other: object) -> float:
        '''Divide this duration by another one, returning a float.

        Returns:
            `float`: The ratio of the two durations.
                - `math.nan` if either operand is `UNDEFINED`,
                  or if division is indeterminate (0/0, inf/inf,
                  -inf/inf, etc.).
                - `float('inf')` or `-float('inf')` for division by zero
                  with non-zero numerator, or infinite numerator divided
                  by finite denominator.
        '''

        if not isinstance(other, Duration):
            return NotImplemented

        # Undefined.
        if self._kind is Duration.Kind.UNDEFINED or other._kind is Duration.Kind.UNDEFINED:
            return math.nan
        # Both defined.

        # Both finite.
        if self._value is not None and other._value is not None:
            num = self._value.total_seconds()
            den = other._value.total_seconds()
            if den == 0.:
                if num == 0.:
                    return math.nan  # 0 / 0.
                # Finite divided by 0.
                return float('inf') if num > 0 else -float('inf')
            return num / den

        # `self` finite, `other` infinite.
        if self.is_finite and other.is_infinite:
            # Finite divided by infinity equals 0.
            return 0.

        # `self` infinite, `other` finite.
        if self.is_infinite and other._value is not None:
            den = other._value.total_seconds()
            if den == 0.:
                # Infinity divided by 0 equals infinity with the same
                # sign as `self`.
                return float('inf') if self._kind is Duration.Kind.POS_INF else -float('inf')
            # Resul sign: `sign(self) * sign(den)`.
            sign = (1 if self._kind is Duration.Kind.POS_INF else -1) * (1 if den > 0 else -1)
            return float('inf') if sign > 0 else -float('inf')

        # Both infinite.
        if self.is_infinite and other.is_infinite:
            return math.nan

        return math.nan
    

    @classmethod
    def undefined(cls) -> Duration:
        return cls(_kind=Duration.Kind.UNDEFINED, _value=None) 
    

    @classmethod
    def neg_inf(cls) -> Duration:
        return cls(_kind=Duration.Kind.NEG_INF, _value=None)


    @classmethod
    def pos_inf(cls) -> Duration:
        return cls(_kind=Duration.Kind.POS_INF, _value=None)



@dataclass(frozen=True, init=False, slots=True)
class TimeInterval:
    '''A time interval representing a connected subset of the timeline.

    The interval may be:
        - empty,
        - a single point,
        - a bounded open, closed, or half-open interval,
        - a left or right unbounded ray,
        - the entire timeline.

    Interval boundaries are represented by `Timestamp` objects.
    '''


    class Kind(Enum):
        '''Specifies the mathematical type of the interval.
        
        Here, openness and closedness are understood in a strict
        mathematical (topological) sense. Therefore, for example,
        an empty set is both open and closed.
        '''

        EMPTY = auto()           # The empty set.

        POINT = auto()           # A point.

        OPEN = auto()            # A non-empty bounded open interval.

        CLOSED = auto()          # A non-empty bounded closed interval.
                                 # Not a point.

        CLOSED_OPEN = auto()     # A non-empty bounded half-open
                                 # interval that includes the start but
                                 # not the end.

        OPEN_CLOSED = auto()     # A non-empty bounded half-open
                                 # interval that doesn't include
                                 # the start but includes the end.

        RIGHT_OPEN = auto()      # An open right-ray.

        RIGHT_CLOSED = auto()    # A closed right-ray.
        
        LEFT_OPEN = auto()       # An open left-ray.

        LEFT_CLOSED = auto()     # A closed left-ray.

        TIMELINE = auto()        # The entire timeline.
    

    _BOUNDED_KINDS = {
        Kind.EMPTY,
        Kind.POINT,
        Kind.OPEN,
        Kind.CLOSED,
        Kind.CLOSED_OPEN,
        Kind.OPEN_CLOSED,
    }

    _RIGHT_RAY_KINDS = {
        Kind.RIGHT_OPEN,
        Kind.RIGHT_CLOSED
    }

    _LEFT_RAY_KINDS = {
        Kind.LEFT_OPEN,
        Kind.LEFT_CLOSED
    }

    _UNBOUNDED_KINDS = {
        Kind.RIGHT_OPEN,
        Kind.RIGHT_CLOSED,
        Kind.LEFT_OPEN,
        Kind.LEFT_CLOSED,
        Kind.TIMELINE
    }

    _LEFT_BOUNDED_KINDS = {
        Kind.EMPTY,
        Kind.POINT,
        Kind.OPEN,
        Kind.CLOSED,
        Kind.CLOSED_OPEN,
        Kind.OPEN_CLOSED,
        Kind.RIGHT_OPEN,
        Kind.RIGHT_CLOSED
    }

    _RIGHT_BOUNDED_KINDS = {
        Kind.EMPTY,
        Kind.POINT,
        Kind.OPEN,
        Kind.CLOSED,
        Kind.CLOSED_OPEN,
        Kind.OPEN_CLOSED,
        Kind.LEFT_OPEN,
        Kind.LEFT_CLOSED
    }

    _OPEN_KINDS = {
        Kind.EMPTY,
        Kind.OPEN,
        Kind.RIGHT_OPEN,
        Kind.LEFT_OPEN,
        Kind.TIMELINE
    }

    # In a mathematical sense, non-openness does not mean closedness.
    _CLOSED_KINDS = {
        Kind.EMPTY,
        Kind.POINT,
        Kind.CLOSED,
        Kind.RIGHT_CLOSED,
        Kind.LEFT_CLOSED,
        Kind.TIMELINE
    }

    _START_SPECIFIED_KINDS = {
        Kind.POINT,
        Kind.OPEN,
        Kind.CLOSED,
        Kind.CLOSED_OPEN,
        Kind.OPEN_CLOSED,
        Kind.RIGHT_OPEN,
        Kind.RIGHT_CLOSED
    }

    _END_SPECIFIED_KINDS = {
        Kind.POINT,
        Kind.OPEN,
        Kind.CLOSED,
        Kind.CLOSED_OPEN,
        Kind.OPEN_CLOSED,
        Kind.LEFT_OPEN,
        Kind.LEFT_CLOSED
    }

    _START_INCLUDED_KINDS = {
        Kind.POINT,
        Kind.CLOSED,
        Kind.CLOSED_OPEN,
        Kind.RIGHT_CLOSED
    }

    _END_INCLUDED_KINDS = {
        Kind.POINT,
        Kind.CLOSED,
        Kind.OPEN_CLOSED,
        Kind.LEFT_CLOSED
    }


    _start: Endpoint | None
    _end: Endpoint | None

    _kind: Kind        # Cached interval kind.
    _normalized: bool  # Cached normalized flag.


    def __init__(self, start: Endpoint | None = None, end: Endpoint | None = None) -> None:
        '''Create a time interval by its endpoints.

        Construct the time interval by explicitly providing the start
        and end points taking boundaries inclusion into account.
        To create the empty interval leave the boundaries unspecified
        or use the `empty()` constructor instead.

        Args:
            `start` (`Endpoint | None`): The left boundary
                of the interval or `None` for empty.
            `end` (`Endpoint | None`): The right boundary
                of the interval or `None` for empty.

        Raises:
            `ValueError`: If the endpoints are specified incorrectly,
                (e.g. `start > end`).
        '''
        
        if start is None or end is None:
            if start is None and end is None:
                # The interval is empty
                object.__setattr__(self, '_kind', TimeInterval.Kind.EMPTY)
            else:
                raise ValueError(
                    'The endpoints of the interval must be specified either both or neither.'
                )
            
        else:
            if start.side is not Endpoint.Side.LEFT:
                raise ValueError('The start must be on the left side.')
            if end.side is not Endpoint.Side.RIGHT:
                raise ValueError('The end must be on the right side.')
            if start > end:
                raise ValueError(
                    'The interval is set incorrectly. The start of the interval cannot occur later '
                    'than the end.'
                )

            if start == end:
                # The point.
                object.__setattr__(self, '_kind', TimeInterval.Kind.POINT)

            elif start.kind == Endpoint.Kind.FINITE and end.kind == Endpoint.Kind.FINITE:
                # The (non-empty) bounded interval.

                if start.is_included and end.is_included:
                    # Both the start and end of the interval are included.
                    # This is a closed (non-empty, bounded) interval,
                    # not a point.
                    
                    object.__setattr__(self, '_kind', TimeInterval.Kind.CLOSED)
                
                elif start.is_included and not end.is_included:
                    # The start of the interval is included, but the end
                    # is not. This is a closed-open (non-empty, bounded)
                    # interval.

                    object.__setattr__(self, '_kind', TimeInterval.Kind.CLOSED_OPEN)
                
                elif not start.is_included and end.is_included:
                    # The start of the interval is not included, but the end
                    # is included. This is an open-closed (non-empty,
                    # bounded) interval.

                    object.__setattr__(self, '_kind', TimeInterval.Kind.OPEN_CLOSED)
                
                else:
                    # Both the start and end of the interval
                    # are not included. This is an open (non-empty, bounded)
                    # interval.

                    object.__setattr__(self, '_kind', TimeInterval.Kind.OPEN)
                    
            elif start.kind is Endpoint.Kind.FINITE and end.kind is Endpoint.Kind.INFINITE:
                # The start of the interval is of the finite kind, but
                # not the end. This is the right-ray.
                
                if start.is_included:
                    # The start of the interval is included. This is
                    # the right closed ray.

                    object.__setattr__(self, '_kind', TimeInterval.Kind.RIGHT_CLOSED)
                else:
                    # The start of the interval is not included. This is
                    # the right open ray.
                    
                    object.__setattr__(self, '_kind', TimeInterval.Kind.RIGHT_OPEN)
                
            elif start.kind is Endpoint.Kind.INFINITE and end.kind is Endpoint.Kind.FINITE:
                # The start of the interval lies at infinity, but its end
                # is of the finite kind. This is the left ray.
                
                if end.is_included:
                    # The end of the interval is included. This is the left
                    # closed ray.

                    object.__setattr__(self, '_kind', TimeInterval.Kind.LEFT_CLOSED)
                else:
                    # The end of the interval is not included. This is
                    # the left open ray.
                    
                    object.__setattr__(self, '_kind', TimeInterval.Kind.LEFT_OPEN)
                
            else:
                # The start and end of the interval lie at infinity. This is
                # the entire timeline.
                
                object.__setattr__(self, '_kind', TimeInterval.Kind.TIMELINE)

        object.__setattr__(self, '_start', start)
        object.__setattr__(self, '_end', end)
        self._set_normalized()
        

    def __str__(self) -> str:

        match self._kind:
            case TimeInterval.Kind.EMPTY:
                # Return the empty set symbol '∅'. 
                return '\u2205'

            case TimeInterval.Kind.POINT:
                return f'{{{self._start}}}'

            case _:
                if self._start is None or self._end is None:
                    raise AssertionError(
                        'Any non-empty interval must have a specified start and end.'
                    )
                
                opening_bracket = '[' if self._start._included else '('
                closing_bracket = ']' if self._end._included else ')'
                return f'{opening_bracket}{self._start}; {self._end}{closing_bracket}'
        
    
    def __bool__(self) -> bool:
        '''Return `True` if this interval is non-empty.'''

        return self._kind is not TimeInterval.Kind.EMPTY
    

    @property
    def is_nonempty(self) -> bool:
        '''Return `True` if this time interval is non-empty.'''

        return self._kind is not TimeInterval.Kind.EMPTY


    @property
    def is_empty(self) -> bool:
        '''Return `True` if this time interval is empty.'''

        return self._kind is TimeInterval.Kind.EMPTY
    

    @property
    def is_bounded(self) -> bool:
        '''Return `True` if this interval is bounded.
        
        Here, boundedness is understood in a mathematical sense.
        Therefore the empty interval is considered to be bounded.
        '''

        return self._kind in TimeInterval._BOUNDED_KINDS
    

    @property
    def is_unbounded(self) -> bool:
        '''Return `True` if this interval is unbounded.
        
        Here, (un)boundedness is understood in a mathematical sense.
        Therefore the empty interval is considered to be bounded.
        '''

        return self._kind in TimeInterval._UNBOUNDED_KINDS
    

    @property
    def is_left_bounded(self) -> bool:
        '''Return `True` if this time interval is bounded
        on the left.'''

        return self._kind in TimeInterval._LEFT_BOUNDED_KINDS
    

    @property
    def is_right_bounded(self) -> bool:
        '''Return `True` if this time interval is bounded
        on the right.'''

        return self._kind in TimeInterval._RIGHT_BOUNDED_KINDS
    

    @property
    def is_point(self) -> bool:
        '''Return `True` if this time interval is a point.'''

        return self._kind is TimeInterval.Kind.POINT
    

    @property
    def is_right_ray(self) -> bool:
        '''Return `True` if this interval is a right ray.'''

        return self._kind in TimeInterval._RIGHT_RAY_KINDS
    

    @property
    def is_left_ray(self) -> bool:
        '''Return `True` if this interval is a left ray.'''

        return self._kind in TimeInterval._LEFT_RAY_KINDS
    

    @property
    def is_timeline(self) -> bool:
        '''Return `True` if this time interval is the entire
        timeline.'''

        return self._kind is TimeInterval.Kind.TIMELINE
    

    @property
    def is_open(self) -> bool:
        '''Return `True` if this time interval is open.
        
        Here, openness is understood in a mathematical sense. Therefore,
        the empty interval, a bounded open interval, an open ray
        and the entire timeline are all considered to be open sets.'''

        return self._kind in TimeInterval._OPEN_KINDS
    

    @property
    def is_closed(self) -> bool:
        '''Return `True` if this time interval is closed.

        Here, closeness is understood in a mathematical sense.
        Therefore, the empty interval, a bounded closed interval,
        a closed ray and the entire timeline are all considered
        to be closed sets.'''

        return self._kind in TimeInterval._CLOSED_KINDS
    

    @property
    def start(self) -> Endpoint:
        '''Return the start of this time interval.

        Returns:
            `Endpoint`: The start of this interval.
        
        Raises:
            `KeyError`: If the interval is empty.
        '''

        if self._start is None:
            raise KeyError(
                'The empty interval cannot have a defined start.'
            )

        return self._start
    

    @property
    def end(self) -> Endpoint:
        '''Return the end of this time interval.

        Returns:
            `Endpoint`: The end of this interval.
        
        Raises:
            `KeyError`: If the interval is empty.
        '''

        if self._end is None:
            raise KeyError(
                'The empty interval cannot have a defined end.'
            )

        return self._end
    

    @property
    def first_day(self) -> datetime.date:
        '''Return the calendar date of the left boundary of this time
        interval.

        Returns:
            `datetime.date`: The date (year-month-day) of the left
            boundary.

        Raises:
            `ValueError`: If the interval is not normalized, empty,
                or not left-bounded (i.e., left endpoint is -∞).
        '''
                
        if not self.is_normalized:
            raise ValueError('\'first_day\' is only supported for normalized intervals.')
        if self.is_empty or not self.is_left_bounded:
            raise ValueError(
                '\'first_day\' is only supported for non-empty left-bounded intervals.'
            )
        
        return self.start.timestamp.datetime.date()
    

    @property
    def last_day(self) -> datetime.date:
        '''Return the calendar date of the right boundary of this time
        interval.

        If the right endpoint is excluded and its time is exactly
        midnight, the previous day is returned. Otherwise, returns
        the date of the right endpoint.

        Returns:
            `datetime.date`: The date (year-month-day) of the right
            boundary (or the previous day for excluded midnight
            boundaries).

        Raises:
            `ValueError`: If the interval is not normalized, empty,
                or not right-bounded (i.e., right endpoint is +∞).
        '''
            
        if not self.is_normalized:
            raise ValueError('\'last_day\' is only supported for normalized intervals.')
        if self.is_empty or not self.is_right_bounded:
            raise ValueError(
                '\'last_day\' is only supported for non-empty right-bounded intervals.'
            )
        
        end_dt = self.end.timestamp.datetime
        last_day = end_dt.date()
        if end_dt.time() == datetime.time.min and not self.end.is_included:
            last_day -= datetime.timedelta(days=1)

        return last_day
    

    @property
    def days(self) -> tuple[datetime.date, ...]:
        '''Return the set of calendar days that intersect this time
        interval.

        For a bounded interval:
            - The day containing the left endpoint is always included,
            regardless of whether the endpoint itself is included.
            - The day containing the right endpoint is included
            if the right endpoint is included or if its time
            is not exactly midnight; if the right endpoint is excluded
            and its time is midnight, that day is excluded (the last
            point belongs to the previous day).
        For the empty interval, the empty set is returned.
        For an unbounded interval, a `ValueError` is raised because
        the set would be infinite.

        Returns:
            A set of `datetime.date` objects representing all days that
            intersect the interval.

        Raises:
            `ValueError`: If the interval is unnormalized or unbounded.

        Examples:
            >>> t1 = Timestamp.from_iso_iana(
            ...     '2024-01-01T12:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> t2 = Timestamp.from_iso_iana(
            ...     '2024-01-02T12:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> interval_1 = TimeInterval.closedopen(t1, t2)
            >>> interval_1.days
            {datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)}

            >>> t3 = Timestamp.from_iso_iana(
            ...     '2024-01-01T23:59+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> t4 = Timestamp.from_iso_iana(
            ...     '2024-01-02T00:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> interval_2 = TimeInterval.closedopen(t3, t4)
            >>> interval_2.days
            {datetime.date(2024, 1, 1)}
        '''

        if not self.is_normalized:
            raise ValueError('\'days\' is only supported for normalized intervals.')
        if self.is_unbounded:
            raise ValueError('\'days\' is only supported for bounded intervals.')
        
        if self.is_empty:
            return ()
        
        result = []
        current = self.first_day
        while current <= self.last_day:
            result.append(current)
            current += datetime.timedelta(days=1)

        return tuple(result)
    

    @property
    def duration(self) -> Duration:
        '''Return the duration of this time interval.'''

        if self.is_empty:
            return Duration()
        
        return self.end - self.start
    

    def _set_normalized(self) -> None:
        '''Set normalized flag.'''

        if self.is_empty:
            object.__setattr__(self, '_normalized', True)
            return

        time_zones = set()
        if self.start.is_finite:
            time_zones.add(self.start.timestamp.timezone_iana)
        if self.end.is_finite:
            time_zones.add(self.end.timestamp.timezone_iana)
        object.__setattr__(self, '_normalized', len(time_zones) <= 1)
    

    @property
    def is_normalized(self) -> bool:
        '''Check whether the interval's endpoints are already
        in a single time zone.

        An interval is considered normalized if:
            - it is empty, or
            - at least one endpoint is infinite (unbounded), or
            - both endpoints are finite and use the same IANA time zone.

        Returns:
            `bool`: `True` if the interval is normalized, `False` otherwise.

        Examples:
            >>> ts1 = Timestamp.from_iso_iana('2024-01-01T12:00+02:00', 'Europe/Vilnius')
            >>> ts2 = Timestamp.from_iso_iana('2024-01-02T12:00+02:00', 'Europe/Vilnius')
            >>> interval = TimeInterval.closedopen(ts1, ts2)
            >>> interval.is_normalized
            True

            >>> ts3 = Timestamp.from_iso_iana('2024-01-01T12:00-05:00', 'America/New_York')
            >>> interval_mixed = TimeInterval.closedopen(ts1, ts3)  # Moscow vs New York.
            >>> interval_mixed.is_normalized
            False

            >>> interval_inf = TimeInterval.rightopen(ts1)  # Left finite, right infinite.
            >>> interval_inf.is_normalized
            True
        '''

        return self._normalized
    

    def to_timezone(self, timezone_iana: str) -> TimeInterval:
        '''Convert both endpoints of this time interval to the specified
        IANA time zone.

        Leave empty intervals unchanged. For intervals with infinite
        endpoints, only apply the conversion to the finite endpoints.
        Leave the infinite endpoints unchanged.

        Args:
            `timezone_iana`: IANA time zone name
                (e.g., 'America/New_York').

        Returns:
            `TimeInterval`: A new time interval with endpoints converted
                to the target zone.

        Raises:
            `ValueError`: If the IANA zone name is invalid.
        '''
        
        if self.is_empty:
            return self
        
        start = self.start.to_timezone(timezone_iana)
        end = self.end.to_timezone(timezone_iana)
        return TimeInterval(start, end)
    

    def normalize_time_zones(self) -> TimeInterval:
        '''Convert the interval to a single time zone using the time
        zone of the left finite endpoint.

        Leave the interval unchanged if it is empty or contains at least
        one infinite endpoint. Otherwise, convert both endpoints
        to the time zone of the left endpoint.

        Returns:
            `TimeInterval`: A new time interval with both endpoints
                in the same time zone.
        '''

        if self.is_empty:
            return self

        if self.start.is_infinite or self.end.is_infinite:
            return self
        
        start_tz_iana = self.start.timestamp.timezone_iana
        return self.to_timezone(start_tz_iana)


    def closure(self) -> TimeInterval:
        '''Return the topological closure of this interval.

        The closure includes all limit points of the interval.
        For an open or half-open bounded interval, this adds the missing
        endpoint(s). For rays, it converts an open ray to a closed one.
        The empty set, a point, a closed bounded interval, a closed ray,
        and the entire timeline are already closed and are returned
        unchanged.

        Returns:
            A new `TimeInterval` that is the smallest closed set
            containing the original interval.
        '''

        if not self.is_closed:
            start = self.start.include() if self.start.is_finite else self.start
            end = self.end.include() if self.end.is_finite else self.end
            return TimeInterval(start, end)
        else:
            return self
    

    def interior(self) -> TimeInterval:
        '''Return the topological interior of this interval.

        The interior consists of all points that have a neighbourhood
        entirely contained in the interval. For a closed or half-open
        bounded interval, this removes the included endpoint(s).
        For a closed ray, it converts it to an open ray. A point becomes
        empty. The empty set, an open bounded interval, an open ray,
        and the entire timeline are already open and are returned
        unchanged.

        Returns:
            A new `TimeInterval` that is the largest open set contained
            in the original interval.
        '''

        if not self.is_open:
            start = self.start.exclude() if self.start.is_finite else self.start
            end = self.end.exclude() if self.end.is_finite else self.end

            if start > end:
                return TimeInterval.empty()

            return TimeInterval(start, end)
        else:
            return self
    

    def to_the_right(self) -> TimeInterval:
        '''Create the interval consisting of all points to the right
        of this interval.

        The new interval contains every point that lies strictly
        to the right of every point in the current interval.
        If the current interval is empty, the result is the entire
        timeline.

        Returns:
            `TimeInterval`: A new time interval representing the open
                or closed right ray starting just after the current
                interval's end. The boundary inclusion is the opposite
                of the current interval's right-end inclusion.
        '''

        if self.is_empty:
            return TimeInterval.timeline()
        
        # This interval is non-empty.
        if self.end.kind is Endpoint.Kind.INFINITE:
            # The interval is unbounded on the right.
            return TimeInterval.empty()
        else:
            # The interval is bounded on the right.
            return TimeInterval(self.end.opposite(), Endpoint.right_infinite())
    

    def to_the_left(self) -> TimeInterval:
        '''Create the interval consisting of all points to the left
        of this interval.

        The new interval contains every point that lies strictly
        to the left of every point in the current interval.
        If the current interval is empty, the result is the entire
        timeline.

        Returns:
            `TimeInterval`: A new time interval representing the open
                or closed left ray ending just before the current
                interval's start. The boundary inclusion is the opposite
                of the current interval's left-start inclusion.
        '''

        if self.is_empty:
            return TimeInterval.timeline()
        
        # This interval is non-empty.
        if self.start.kind is Endpoint.Kind.INFINITE:
            # The interval is unbounded on the left.
            return TimeInterval.empty()
        else:
            # The interval is bounded on the left.
            return TimeInterval(Endpoint.left_infinite(), self.start.opposite())
    

    def __contains__(self, other: object) -> bool:
        '''Return `True` if this interval contains the timestamp 
        or another time interval.

        An interval A contains interval B if every point of B is also
        a point of A. An empty interval is contained in any interval.

        Args:
            `other` (`Timestamp | TimeInterval`): The timestamp or time
            interval to test for containment.

        Returns:
            `True` if the timestamp or time interval lies inside this
            interval (taking boundaries inclusion into account),
            otherwise `False`. For an empty interval, always `False`.
        '''
        
        if isinstance(other, Timestamp):
            if self.is_empty:
                return False
                
            return other >= self.start and other <= self.end
        
        elif isinstance(other, TimeInterval):
            if other.is_empty:
                # Any contains the empty interval.
                return True
            
            # `other` is non-empty.
            if self.is_empty:
                # The empty interval cannot contain a non-empty one.
                return False

            return other.start >= self.start and other.end <= self.end
        
        else:
            return NotImplemented
        

    def is_left_of(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the left
        of another one and does not overlap with it.
        
        The interval is considered to lie to the left if all its points
        are before all points of another one and the two intervals
        do not overlap. If either interval is empty, the condition
        is true.

        Args:
            `other` (`TimeInterval`): The time interval to compare with.

        Returns:
            `True` if this interval is completely to the left of another
            one without overlapping, otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return True
        
        return self.end < other.start
    

    def is_right_of(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the right
        of another one and does not overlap with it.
        
        The interval is considered to lie to the right if all its points
        are after all points of another one and the two intervals
        do not overlap. If either interval is empty, the condition
        is true.

        Args:
            `other` (`TimeInterval`): The time interval to compare with.

        Returns:
            `True` if this interval is completely to the right
            of `other` without overlapping, otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return True
            
        return other.end < self.start
    

    def is_left_of_disconnectedly(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the left
        of another one, does not overlap with it and their union
        will be a disconnected set.

        This is a stronger condition than `is_left_of`: it requires that
        there is at least one point between the intervals, i.e., they
        do not touch. If either interval is empty, the result is `False`
        because a disconnected union cannot be formed with an empty set.
        
        Args:
            `other` (`TimeInterval`): The time interval to compare with.

        Returns:
            `True` if this interval lies completely to the left
            of `other` and there is a non-empty gap between them,
            otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return False

        if self.end.is_infinite:
            return False
        
        return self.end.opposite() < other.start
    

    def is_right_of_disconnectedly(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the right
        of another one, does not overlap with it and their union
        will be a disconnected set.
        
        This is a stronger condition than `is_right_of`: it requires
        that there is at least one point between the intervals, i.e.,
        they do not touch. If either interval is empty, the result
        is `False` because a disconnected union cannot be formed with
        an empty set.

        Args:
            `other` (`TimeInterval`): The time interval to compare with.

        Returns:
            `True` if this interval lies completely to the right
            of `other` and there is a non-empty gap between them,
            otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return False

        if self.start.is_infinite:
            return False

        return other.end < self.start.opposite()
    

    def overlaps(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval overlaps with another one
        (has non-empty intersection).
        
        Two intervals overlap if their intersection is non-empty.
        If either interval is empty, they cannot overlap.

        Args:
            `other` (`TimeInterval`): The time interval to test
                for overlap.

        Returns:
            `True` if the intervals share at least one point, otherwise
                `False`.
        '''
        
        if self.is_empty or other.is_empty:
            return False
        # The intervals are non-empty.

        # Check whether `self` is completely to the left of `other`.
        if self.is_left_of(other):
            return False

        # Check whether `self` is completely to the right of `other`.
        if self.is_right_of(other):
            return False

        return True
    

    def overlaps_with_days(self, days: set[datetime.date]) -> bool:
        '''Return `True` if this time interval overlaps with the given
        set of calendar days.
        
        Args:
            `days` (`set[datetime.date]`). The set of calendar days
                to test for overlap.
        
        Returns:
            `True` if overlaps, otherwise `False`.
        
        Raises:
            `ValueError`: If the time interval is unnormalized.
        '''

        if not self.is_normalized:
            raise ValueError(
                '\'overlaps_with_days\' is only supported for normalized time interval.'
            )

        if self.is_empty or not days:
            return False
        # Sets of days are non-empty.
        
        min_day = min(days)
        max_day = max(days)

        if self.is_left_bounded and max_day < self.first_day:
            return False
        
        if self.is_right_bounded and min_day > self.last_day:
            return False
        
        return True
    

    def touches(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval touches another one.
        
        Two intervals touch if they are non-empty and their union
        is connected, i.e., they either overlap or meet at a common
        endpoint (with appropriate inclusion). An endpoint meeting
        is considered touching if the shared point is included
        in at least one of the intervals.

        Args:
            `other` (`TimeInterval`): The time interval to test
                for touching.

        Returns:
            `True` if the intervals are non-empty and their union
            is connected, otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return False
        # The intervals are non-empty.

        # Check whether `self` is completely to the left of `other`
        # and their union is disconnected.
        if self.is_left_of_disconnectedly(other):
            return False

        # Check whether `self` is completely to the right of `self`
        # and their union is disconnected.
        if self.is_right_of_disconnectedly(other):
            return False

        return True
    

    def __and__(self, other: TimeInterval) -> TimeInterval:
        '''Create the intersection this time interval with another
        one.'''

        if self.is_empty or other.is_empty:
            # An intersection with the empty interval is empty.
            return TimeInterval.empty()

        start = max(self.start, other.start)
        end = min(self.end, other.end)

        if start > end:
            return TimeInterval.empty()
                
        return TimeInterval(start, end)
    

    @classmethod
    def empty(cls) -> TimeInterval:
        '''Create the empty time interval.'''

        return cls()


    @classmethod
    def point(cls, timestamp: Timestamp) -> TimeInterval:
        '''Create a point. It corresponds to an instantaneous event.'''

        s = Endpoint.left_finite(timestamp, included=True)
        e = Endpoint.right_finite(timestamp, included=True)
        return cls(s, e)
    

    @classmethod
    def open(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty open bounded time interval.'''

        if start >= end:
            raise ValueError(
                'The start of the interval is either simultaneous with its end or occurs later, '
                'which is not correct.'
            )
        s = Endpoint.left_finite(start, included=False)
        e = Endpoint.right_finite(end, included=False)
        return cls(s, e)
    

    @classmethod
    def closed(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty closed bounded time interval, not a point.
        
        To create a point use the `point()` constructor.
        '''

        if start >= end:
            raise ValueError(
                'Either the start of the interval occurs after its end, which is incorrect, '
                'or it\'s a point.'
            )
        s = Endpoint.left_finite(start, included=True)
        e = Endpoint.right_finite(end, included=True)
        return cls(s, e)
    

    @classmethod
    def closedopen(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty bounded closed-open interval.'''

        if start >= end:
            raise ValueError(
                'The start of the interval is either simultaneous with its end or occurs later, '
                'which is not correct.'
            )
        s = Endpoint.left_finite(start, included=True)
        e = Endpoint.right_finite(end, included=False)
        return cls(s, e)
    

    @classmethod
    def openclosed(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty bounded open-closed interval.'''

        if start >= end:
            raise ValueError(
                'The start of the interval is either simultaneous with its end or occurs later, '
                'which is not correct.'
            )
        s = Endpoint.left_finite(start, included=False)
        e = Endpoint.right_finite(end, included=True)
        return cls(s, e)
    

    @classmethod
    def rightclosed(cls, start: Timestamp) -> TimeInterval:
        '''Create a closed right-ray.'''

        s = Endpoint.left_finite(start, included=True)
        e = Endpoint.right_infinite()
        return cls(s, e)
    

    @classmethod
    def rightopen(cls, start: Timestamp) -> TimeInterval:
        '''Create an open right-ray.'''

        s = Endpoint.left_finite(start, included=False)
        e = Endpoint.right_infinite()
        return cls(s, e)
    

    @classmethod
    def right_ray(cls, start: Timestamp, start_included: bool = True) -> TimeInterval:
        '''Create a right-ray with a specified left boundary kind.'''

        s = Endpoint.left_finite(start, included=start_included)
        e = Endpoint.right_infinite()
        return cls(s, e)
    

    @classmethod
    def leftclosed(cls, end: Timestamp) -> TimeInterval:
        '''Create a closed left ray.'''

        s = Endpoint.left_infinite()
        e = Endpoint.right_finite(end, included=True)
        return cls(s, e)
    

    @classmethod
    def leftopen(cls, end: Timestamp) -> TimeInterval:
        '''Create an open left ray.'''

        s = Endpoint.left_infinite()
        e = Endpoint.right_finite(end, included=False)
        return cls(s, e)
    

    @classmethod
    def left_ray(cls, end: Timestamp, end_included: bool = False) -> TimeInterval:
        '''Create a left-ray with a specified right boundary kind.'''

        s = Endpoint.left_infinite()
        e = Endpoint.right_finite(end, included=end_included)
        return cls(s, e)
    

    @classmethod
    def timeline(cls) -> TimeInterval:
        '''Create the entire timeline.'''

        s = Endpoint.left_infinite()
        e = Endpoint.right_infinite()
        return cls(s, e)
    

    @classmethod
    def today(cls) -> TimeInterval:
        '''Create a closed-open interval representing the current day
        in the local time zone.

        The interval starts at midnight (00:00:00) of the current local
        date and ends at midnight of the following day. The left
        endpoint is included, the right endpoint is excluded, producing
        a half-open interval `[start_of_today, start_of_tomorrow)`.

        Returns:
            `TimeInterval`: The closed-open interval covering exactly
                the current calendar day.
        '''

        now = Timestamp.now()
        tz_iana = now.timezone_iana
        today_date = now.datetime.date()
        start = Timestamp.midnight(today_date, tz_iana)
        end = start + datetime.timedelta(days=1)
        return cls.closedopen(start, end)


    @classmethod
    def yesterday(cls) -> TimeInterval:
        '''Create a closed-open interval representing the previous
        calendar day in the local time zone.

        The interval starts at midnight (00:00:00) of the previous local
        date and ends at midnight of the current day. The left endpoint
        is included, the right endpoint is excluded, producing
        a half-open interval `[start_of_yesterday, start_of_today)`.

        Returns:
            `TimeInterval`: The closed-open interval covering exactly
                the previous calendar day.
        '''

        now = Timestamp.now()
        tz_iana = now.timezone_iana
        today_date = now.datetime.date()
        yesterday_date = today_date - datetime.timedelta(days=1)
        start = Timestamp.midnight(yesterday_date, tz_iana)
        end = Timestamp.midnight(today_date, tz_iana)
        return cls.closedopen(start, end)
    

    @classmethod
    def week(cls) -> TimeInterval:
        '''Create a closed-open interval representing the current week
        (Monday to Sunday) in the local time zone.

        The interval starts at midnight (00:00:00) of the Monday
        of the current week and ends at midnight of the following Monday.
        The left endpoint is included, the right endpoint is excluded,
        producing a half-open interval
        `[start_of_week, start_of_next_week)`.

        Returns:
            `TimeInterval`: The closed-open interval covering exactly
            the current calendar week.
        '''

        now = Timestamp.now()
        tz_iana = now.timezone_iana
        today = now.datetime.date()
        monday = today - datetime.timedelta(days=today.weekday())
        start = Timestamp.midnight(monday, tz_iana)
        end = start + datetime.timedelta(days=7)
        return cls.closedopen(start, end)

    
    @classmethod
    def month(cls) -> TimeInterval:
        '''Create a closed-open interval representing the current month
        in the local time zone.

        The interval starts at midnight (00:00:00) of the first day
        of the current month and ends at midnight of the first day
        of the following month. The left endpoint is included, the right
        endpoint is excluded, producing a half-open interval
        `[start_of_month, start_of_next_month)`.

        Returns:
            `TimeInterval`: The closed-open interval covering exactly
                the current calendar month.
        '''

        now = Timestamp.now()
        tz_iana = now.timezone_iana
        today = now.datetime.date()
        first_of_month = today.replace(day=1)

        # Compute first day of next month.
        if first_of_month.month == 12:
            next_month = first_of_month.replace(year=first_of_month.year + 1, month=1)
        else:
            next_month = first_of_month.replace(month=first_of_month.month + 1)
        
        start = Timestamp.midnight(first_of_month, tz_iana)
        end = Timestamp.midnight(next_month, tz_iana)
        return cls.closedopen(start, end)
    

    @classmethod
    def year(cls) -> TimeInterval:
        '''Create a closed-open interval representing the current year
        in the local time zone.

        The interval starts at midnight (00:00:00) of January 1st
        of the current year and ends at midnight of January 1st
        of the following year. The left endpoint is included, the right
        endpoint is excluded, producing a half-open interval
        `[start_of_year, start_of_next_year)`.

        Returns:
            `TimeInterval`: The closed-open interval covering exactly
            the current calendar year.
        '''
        
        now = Timestamp.now()
        tz_iana = now.timezone_iana
        today = now.datetime.date()
        first_of_year = today.replace(month=1, day=1)
        next_year = first_of_year.replace(year=first_of_year.year + 1)
        start = Timestamp.midnight(first_of_year, tz_iana)
        end = Timestamp.midnight(next_year, tz_iana)
        return cls.closedopen(start, end)
    

    @classmethod
    def from_dict(cls, time_data: dict, time_zone_iana: str, date_iso: str = '') -> TimeInterval:
        '''Create a closed-open interval or a point from a dictionary.

        The dictionary must contain:
            - `start_time` / `end_time`: ISO time strings including
                offset, e.g. '10:30+03:00').

        If `date_iso` is provided (YYYY-MM-DD), it is combined with
        the time strings to form full ISO datetimes. In this mode,
        if `end_time` starts with '24:', it is interpreted as the end
        of that day (validated, then replaced with '00:' and the date
        advanced). If `date_iso` is omitted, `start_time` and `end_time`
        must be complete ISO datetime strings including date and offset.

        Args:
            `time_data`: Dictionary with the four required keys.
            `time_zone_iana`: The time zone common for both endpoints.
                It must be in IANA format (e.g. 'Europe/Moscow').
            `date_iso`: Optional common date in YYYY-MM-DD format.
                If provided, the time strings are interpreted as times
                of that day, and '24:' in end_time is handled specially.
                If omitted, start_time and end_time must be full ISO
                datetime strings.
            

        Returns:
            `TimeInterval`: closed-open interval or point.

        Raises:
            `ValueError`: if any key is missing, values are invalid,
                offsets mismatch, or start > end.

        Example:
            >>> TimeInterval.from_dict({
            ...     'start': '08:00:00-04:00',
            ...     'end': '09:00:00-04:00'
            ... }, 'America/New_York', '2026-03-30')
            [2026.03.30 08:00:00 UTC-4; 2026.03.30 09:00:00 UTC-4)

            Using '24:00' to denote the end of the day:
            >>> TimeInterval.from_dict({
            ...     'start': '09:00:00Z',
            ...     'end': '24:00:00Z'
            ... }, 'Etc/UTC', 2026-03-09')
            [2026.03.09 09:00:00 UTC; 2026.03.10 00:00:00 UTC)

            Without a common date (full ISO strings expected):
            >>> TimeInterval.from_dict({
            ...     'start': '2026-03-09T09:00+03:00',
            ...     'end': '2026-03-10T18:00+03:00'
            ... }, 'Europe/Moscow')
            [2026-03-09T09:00:00+03:00; 2026-03-10T18:00:00+03:00)
        '''

        if not isinstance(time_data, dict):
            raise TypeError('\'time_data\' must be a dictionaty.')
        
        # Check for extra keys in the dictionary.
        allowed_keys = {'start', 'end'}
        extra_keys = set(time_data) - allowed_keys
        if extra_keys:
            extra_keys_str = ', '.join(f'\'{k}\'' for k in sorted(extra_keys))
            warnings.warn(
                f'The time interval dictionary contains unknown fields: {extra_keys_str}.',
                stacklevel=2
            )
        
        # Helper to fetch required string values.
        def get_str(key: str) -> str:
            try:
                value = time_data[key]
            except KeyError:
                raise ValueError(f'The time interval dictionary missing required key \'{key}\'.')
            if not isinstance(value, str):
                raise TypeError(f'Value \'{key}\' must be a string, got \'{type(value).__name__}\'.')
            return value

        start_time_iso = get_str('start')
        end_time_iso = get_str('end')

        if date_iso:
            # Parse the base date.
            try:
                date = datetime.date.fromisoformat(date_iso)
            except ValueError as e:
                raise ValueError(f'Invalid date format \'{date_iso}\'. Expected \'YYYY-MM-DD\'.') from e
        
            start_date = date
            end_date = date

            if start_time_iso.startswith('24:'):
                raise ValueError('24:00 is only allowed for \'end_time\'.')
            
            def split_time_and_offset(ts: str):
                pos = max(ts.rfind('+'), ts.rfind('-'))

                if pos != -1:
                    return ts[:pos], ts[pos:]

                if ts.endswith('Z'):
                    return ts[:-1], 'Z'

                return ts, ''
        
            # Handle 24:00 end time.
            if end_time_iso.startswith('24:'):
                time_part, offset_part = split_time_and_offset(end_time_iso)

                if not offset_part:
                    raise ValueError(f'End time \'{end_time_iso}\' must include UTC offset.')

                # Validate that `time_part` is midnight.
                try:
                    # Temporarily replace '24' with '00' to parse the time part.
                    fake_time_part = '00' + time_part[2:]
                    parsed = datetime.time.fromisoformat(fake_time_part)
                    if parsed != datetime.time.min:
                        raise ValueError('Time part after \'24:\' is not midnight.')
                except ValueError as e:
                    raise ValueError(f'Invalid end time \'{end_time_iso}\': if hour is 24, minutes/seconds must be zero.') from e
                
                # Adjust: replace '24' with '00' in time part, keep offset.
                end_time_iso = '00' + time_part[2:] + offset_part
                end_date += datetime.timedelta(days=1)

            # Build full ISO datetime strings.
            start_datetime_iso = f'{start_date.isoformat()}T{start_time_iso}'
            end_datetime_iso = f'{end_date.isoformat()}T{end_time_iso}'
        else:
            start_datetime_iso = start_time_iso
            end_datetime_iso = end_time_iso

        # Create timestamps using the existing factory that checks offset vs IANA zone.
        try:
            start_ts = Timestamp.from_iso_iana(start_datetime_iso, time_zone_iana)
        except ValueError as e:
            raise ValueError(f'Incorrect start time format. {e}') from e
        
        try:
            end_ts = Timestamp.from_iso_iana(end_datetime_iso, time_zone_iana)
        except ValueError as e:
            raise ValueError(f'Incorrect end time format. {e}') from e

        if start_ts < end_ts:
            return TimeInterval.closedopen(start_ts, end_ts)
        elif start_ts == end_ts:
            return TimeInterval.point(start_ts)
        else:
            raise ValueError('The start of a time interval cannot be later than its end.')
    

    @classmethod
    def between(cls, first: TimeInterval, second: TimeInterval) -> TimeInterval:
        '''Create the interval that lies strictly between two intervals.

        The resulting interval consists of all points that are
        to the right of the first time interval and to the left
        of the second time interval. The order of the arguments matters.
        Empty intervals are allowed.

        Args:
            `first` (`TimeInterval`): The left-hand interval.
            `second` (`TimeInterval`): The right-hand interval.

        Returns:
            A new `TimeInterval` representing the space between
            the two intervals. If the intervals touch or overlap,
            an empty interval is returned. If both intervals are empty,
            the entire timeline is returned. If only one interval
            is empty, the result is the corresponding ray.
        '''

        if not first.is_left_of(second):
            return TimeInterval.empty()
        # The first interval is to the left of the second.

        if first.is_empty and second.is_empty:
            return TimeInterval.timeline()
        elif first.is_nonempty and second.is_empty:
            return first.to_the_right()
        elif first.is_empty and second.is_nonempty:
            return second.to_the_left()
        else:
            # Both intervals are non-empty.

            start = first.end.opposite()
            end = second.start.opposite()

            if start > end:
                return TimeInterval.empty()
    
            return TimeInterval(start, end)

    @classmethod
    def minimal_cover(cls, *intervals: TimeInterval) -> TimeInterval:
        '''Create the smallest interval that contains all the given
        intervals.

        The resulting interval spans from the earliest start
        to the latest end among the provided intervals. This operation
        does **not** produce a topological cover in the strict sense
        because the result is a single interval, not a union.

        Args:
            `*intervals`: Variable number of `TimeInterval` objects.
                Empty intervals are ignored.

        Returns:
            A new `TimeInterval` that contains every point of every
            input interval. If all input intervals are empty, an empty
            interval is returned.
        '''

        # Remove empty intervals.
        nonempty_intervals = [i for i in intervals if not i.is_empty]

        # The cover is empty if there are no non-empty intervals. 
        if not nonempty_intervals:
            return cls.empty()

        start = min(i.start for i in nonempty_intervals)
        end = max(i.end for i in nonempty_intervals)

        # Construct the covering interval.
        return cls(start, end)
    

    @staticmethod
    def dist(first: TimeInterval, second: TimeInterval) -> Duration:
        '''Calculate the shortest temporal distance between two
        intervals.

        The distance is defined as the length of the smallest gap
        between any point of the first interval and any point
        of the second. If the intervals overlap, the distance is zero.

        Args:
            `first` (`TimeInterval`): The first time interval.
            `second` (`TimeInterval`): The second time interval.

        Returns:
            The `Duration` representing the gap between
            the intervals, or `None` if either interval is empty.
        '''

        if first.is_empty or second.is_empty:
            return Duration.undefined()

        if first.is_left_of(second):
            return second.start - first.end
        
        if first.is_right_of(second):
            return first.start - second.end
        
        # Intervals overlap.
        return Duration()



@dataclass(frozen=True, init=False, slots=True)
class TimeSet:
    '''A disjoint union of time intervals that are pairwise disconnected
    and chronologically ordered.
    
    Each component interval must be non-empty and placed
    in chronological order. Intervals must not overlap, and the union
    of any two distinct intervals must be disconnected. In other words,
    each component interval is a connected component of the time set.
    '''

    _components: tuple[TimeInterval, ...]

    _starts: tuple[Endpoint, ...]  # Cached starts of components.
    _ends: tuple[Endpoint, ...]    # Cached end of components.
    _normalized: bool  # Cached normalized flag.


    @staticmethod
    def _validate_components(*intervals: TimeInterval) -> None:
        '''Check that the given intervals correctly define a time set.
        
        Raises:
            `ValueError`: If the given intervals doesn't correctly
                define a time set (e.g. there is the empty interval,
                they are not chronologically ordered or disconnected).
        '''

        for i in intervals:
            if i.is_empty:
                raise ValueError('The time set has an empty component.')

        for f, s in zip(intervals, intervals[1:]):
            if not f.is_left_of_disconnectedly(s):
                raise ValueError(
                    'The intervals in the time set are not chronologically ordered or not all '
                    'their pairwise unions are disconnected.'
                )


    def _validate(self) -> None:
        '''Check that the time set has been set correctly.
        
        Raises:
            `ValueError`: If the time set has been set incorrectly
                (e.g. it has an empty component, it's components
                are not chronologically ordered or disconnected).
        '''

        try:
            TimeSet._validate_components(*self._components)
        except ValueError as e:
            raise ValueError(f'The time set {self} has been set incorrectly. {e}')
    

    def __init__(self, *intervals: TimeInterval):
        '''Initialize a time set with the provided intervals.
        
        Args:
            `*intervals`: Time intervals that must satisfy
                the invariants (non-empty, chronologically ordered,
                pairwise disconnected).

        Raises:
            `ValueError`: If the intervals do not satisfy
                the invariants.
        '''

        object.__setattr__(self, '_components', tuple(intervals))
        object.__setattr__(self, '_starts', tuple(i.start for i in intervals))
        object.__setattr__(self, '_ends', tuple(i.end for i in intervals))
        self._set_normalized()

        self._validate()
    

    def __str__(self) -> str:
        '''Return the string representation of the time set.

        For an empty set, return the empty set symbol '∅'.
        For a non-empty set, return the components joined by the union
        symbol '⊔'.

        Returns:
            `str`: The string representation of the time set.
        '''

        if self.is_empty:
            # Return the empty set symbol '∅'.
            return '\u2205'
        else:
            return ' \u2294 '.join(str(c) for c in self._components)
    

    def __bool__(self) -> bool:
        '''Return `True` if the time set is non-empty, `False`
        otherwise.

        Returns:
            `bool`: `True` for non-empty, `False` otherwise.
        '''

        return bool(self._components)


    @property
    def is_nonempty(self) -> bool:
        '''Return `True` if the time set is non-empty.'''

        return bool(self._components)


    @property
    def is_empty(self) -> bool:
        '''Return `True` if the time set is empty.'''

        return not self._components


    @property
    def is_point(self) -> bool:
        '''Return `True` if the time set consists of a single point.'''

        return len(self._components) == 1 and self._components[0].is_point
        

    @property
    def is_timeline(self) -> bool:
        '''Return `True` if this time set is the entire timeline.'''

        return len(self._components) == 1 and self._components[0].is_timeline
    

    @property
    def is_bounded(self) -> bool:
        '''Return `True` if this time set is bounded.
        
        Here, boundedness is understood in a mathematical sense.
        Therefore the empty time set is considered to be bounded.
        '''

        if self.is_empty:
            return True
        # Time set is non-empty.

        # Check the first and last components for boundedness.
        return self._components[0].is_bounded and self._components[-1].is_bounded
    

    @property
    def is_left_bounded(self) -> bool:
        '''Return `True` if this time set is left-bounded.'''

        if self.is_empty:
            return True
        # Time set is non-empty.

        # Check the first component for left-boundedness.
        return self._components[0].is_left_bounded
    

    @property
    def is_right_bounded(self) -> bool:
        '''Return `True` if this time set is right-bounded.'''

        if self.is_empty:
            return True
        # Time set is non-empty.

        # Check the last component for right-boundedness.
        return self._components[-1].is_right_bounded
    

    @property
    def is_unbounded(self) -> bool:
        '''Return `True` if this time set is unbounded.
        
        Here, (un)boundedness is understood in a mathematical sense.
        Therefore the empty time set is considered to be bounded.
        '''

        if self.is_empty:
            return False
        # Time set is non-empty.

        # Check the first and last components for unboundedness.
        return self._components[0].is_unbounded or self._components[-1].is_unbounded
    

    @property
    def is_open(self) -> bool:
        '''Return `True` if this time set is an open set
        (in the topological sense).'''

        if self.is_empty:
            return True

        return all(i.is_open for i in self._components)
    

    @property
    def is_closed(self) -> bool:
        '''Return `True` if this time set is a closed set
        (in the topological sense).'''

        if self.is_empty:
            return True

        return all(i.is_closed for i in self._components)


    @property
    def is_connected(self) -> bool:
        '''Return `True` if this time set is connected.
        
        A time set is connected if it has no more than one connected 
        component.
        '''

        return len(self._components) <= 1
    

    @property
    def start(self) -> Endpoint:
        '''Return the start of this time set.

        Returns:
            `Endpoint`: The start of this time set.
        
        Raises:
            `KeyError`: If this time set is empty.
        '''

        if self.is_empty:
            raise KeyError('The empty time set has no specified start.')
        
        return self.first_component.start
    

    @property
    def end(self) -> Endpoint:
        '''Return the end of this time set.

        Returns:
            `Endpoint`: The end of this time set.
        
        Raises:
            `KeyError`: If this time set is empty.
        '''

        if self.is_empty:
            raise KeyError('The empty time set has no specified end.')
        
        return self.last_component.end
    

    @property
    def first_day(self) -> datetime.date:
        '''Return the calendar date of the left boundary of this time
        set.

        Returns:
            `datetime.date`: The date (year-month-day) of the left
            boundary.

        Raises:
            `ValueError`: If the time set is not normalized, empty,
                or not left-bounded (i.e., left endpoint is -∞).
        '''
                
        if not self.is_normalized:
            raise ValueError('\'first_day\' is only supported for normalized time sets.')
        if self.is_empty or not self.is_left_bounded:
            raise ValueError(
                '\'first_day\' is only supported for non-empty left-bounded time sets.'
            )
        
        return self.first_component.first_day
    

    @property
    def last_day(self) -> datetime.date:
        '''Return the calendar date of the right boundary of this time
        set.

        If the right endpoint is excluded and its time is exactly
        midnight, the previous day is returned. Otherwise, returns
        the date of the right endpoint.

        Returns:
            `datetime.date`: The date (year-month-day) of the right
            boundary (or the previous day for excluded midnight
            boundaries).

        Raises:
            `ValueError`: If the time set is not normalized, empty,
                or not right-bounded (i.e., right endpoint is +∞).
        '''

        if not self.is_normalized:
            raise ValueError('\'last_day\' is only supported for normalized time sets.')
        if self.is_empty or not self.is_right_bounded:
            raise ValueError(
                '\'last_day\' is only supported for non-empty right-bounded time sets.'
            )
        
        return self.last_component.last_day


    @property
    def days(self) -> tuple[datetime.date, ...]:
        '''Return the set of calendar days that intersect this time set.

        For a bounded time set:
            - The days are collected from each connected component.
            - The day containing the leftmost point is always included.
            - The day containing the rightmost point is included
            according to the rules of `TimeInterval.days`
            (i.e., included if the endpoint is included or its time
            is not exactly midnight).
        For the empty time set, the empty set is returned.
        For an unbounded time set, a `ValueError` is raised because
        the set of days would be infinite.

        Returns:
            The set of `datetime.date` objects representing all days
            that intersect the time set.

        Raises:
            `ValueError`: If the time set is unnormalized or unbounded.

        Examples:
            >>> t1 = Timestamp.from_iso_iana(
            ...     '2024-01-01T12:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> t2 = Timestamp.from_iso_iana(
            ...     '2024-01-02T12:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> interval_1 = TimeInterval.closedopen(t1, t2)
            >>> t3 = Timestamp.from_iso_iana(
            ...     '2024-01-05T12:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> t4 = Timestamp.from_iso_iana(
            ...     '2024-01-06T12:00+03:00',
            ...     'Europe/Moscow'
            ... )
            >>> interval_2 = TimeInterval.closedopen(t3, t4)
            >>> timeset = TimeSet(interval_1, interval_2)
            >>> timeset.days
            {datetime.date(2024, 1, 1), datetime.date(2024, 1, 2),
            datetime.date(2024, 1, 5), datetime.date(2024, 1, 6)}
        '''

        if not self.is_normalized:
            raise ValueError('\'days\' is only supported for normalized time sets.')
        if self.is_unbounded:
            raise ValueError('\'days\' is only supported for bounded time sets.')
        
        if self.is_empty:
            return ()
        
        result = set()
        for i in self.components:
            result.update(i.days)

        return tuple(sorted(result))
    

    @property
    def components_number(self) -> int:
        '''Return the number of connected components of this time
        set.'''

        return len(self._components)
    

    @property
    def components(self) -> tuple[TimeInterval, ...]:
        '''Return the tuple of the connected components of this time
        set.'''
        
        return self._components
    

    @property
    def first_component(self) -> TimeInterval:
        '''Return the first (leftmost) connected component.

        Raises:
            `IndexError`: If the time set is empty.
        '''

        try:
            return self._components[0]
        except IndexError as e:
            raise IndexError('Time set has no connected components.') from e
    

    @property
    def last_component(self) -> TimeInterval:
        '''Return the last (rightmost) connected component.

        Raises:
            `IndexError`: If the time set is empty.
        '''

        try:
            return self._components[-1]
        except IndexError as e:
            raise IndexError('Time set has no connected components.') from e
        
    @property
    def duration(self) -> Duration:
        '''Return the total duration of the time set.

        For an empty time set, return zero.
        '''

        return sum((c.duration for c in self._components), start=Duration())
    

    def _set_normalized(self) -> None:
        '''Set normalized flag.'''

        if self.is_empty:
            object.__setattr__(self, '_normalized', True)
            return

        time_zones = set()
        for c in self.components:
            if c.start.is_finite:
                time_zones.add(c.start.timestamp.timezone_iana)
            if c.end.is_finite:
                time_zones.add(c.end.timestamp.timezone_iana)
        object.__setattr__(self, '_normalized', len(time_zones) <= 1)
    

    @property
    def is_normalized(self) -> bool:
        '''Check whether the time set's endpoints are already
        in a single time zone.

        A time set is considered normalized if:
            - it is empty, or
            - all finite endpoints (left and right boundaries
            of all components) share the same IANA time zone, or
            - there are no finite endpoints at all (e.g., the whole
            timeline).

        Returns:
            `bool`: `True` if the time set is normalized, `False`
            otherwise.

        Examples:
            >>> ts1 = Timestamp.from_iso_iana('2024-01-01T12:00+02:00', 'Europe/Vilnius')
            >>> ts2 = Timestamp.from_iso_iana('2024-01-02T12:00+02:00', 'Europe/Vilnius')
            >>> interval_1 = TimeInterval.closedopen(ts1, ts2)
            >>> ts3 = Timestamp.from_iso_iana('2024-01-05T12:00+02:00', 'Europe/Vilnius')
            >>> ts4 = Timestamp.from_iso_iana('2024-01-06T12:00+02:00', 'Europe/Vilnius')
            >>> interval_2 = TimeInterval.closedopen(ts3, ts4)
            >>> timeset = TimeSet(interval_1, interval_2)
            >>> timeset.is_normalized
            True

            >>> ts_ny = Timestamp.from_iso_iana('2024-01-01T12:00-05:00', 'America/New_York')
            >>> interval_mixed = TimeInterval.closedopen(ts1, ts_ny)
            >>> timeset_mixed = TimeSet(interval_mixed)
            >>> timeset_mixed.is_normalized
            False

            >>> timeset_empty = TimeSet.empty()
            >>> timeset_empty.is_normalized
            True

            >>> timeset_timeline = TimeSet.timeline()
            >>> timeset_timeline.is_normalized
            True
        '''

        return self._normalized
    

    @property
    def span_duration(self) -> Duration:
        '''Return the duration of the minimal interval covering
        the whole time set.

        This is the time span from the earliest start to the latest end.
        Return zero for the empty time set.
        '''

        if self.is_empty:
            return Duration()
        
        return self.end - self.start
    
    
    @property
    def min_component_duration(self) -> Duration:
        '''Return the minimal duration among the components.

        Compute the minimal duration of all components in the time set.
        '''

        return min((c.duration for c in self._components), default=Duration.undefined())
    

    @property
    def max_component_duration(self) -> Duration:
        '''Return the maximal duration among the components.

        Compute the maximal duration of all components in the time set.
        '''

        return max((c.duration for c in self._components), default=Duration.undefined())
    

    @property
    def density(self) -> float:
        '''Return the ratio of the total duration of the set to the span
        duration (from earliest start to latest end).
        
        Returns:
            `float`:  The ratio of the total duration to the span
            duration. `NaN` if the span duration is zero.
        '''

        return self.duration / self.span_duration
    

    def _gaps(self) -> Iterator[Duration]:
        '''Generate durations of gaps between consecutive components.'''

        for f, s in zip(self.components, self.components[1:]):
            start, end = f.end, s.start
            
            yield end - start
    

    @property
    def max_gap_duration(self) -> Duration:
        '''Return the maximum gap duration between components.
    
        If there are no gaps (less than two components), return zero
        duration.
        '''

        return max(self._gaps(), default=Duration())
    

    @property
    def min_gap_duration(self) -> Duration:
        '''Return the minimum gap duration between components.

        If there are no gaps (less than two components), return zero
        duration.
        '''

        return min(self._gaps(), default=Duration())
    

    def to_timezone(self, timezone_iana: str) -> TimeSet:
        '''Convert all endpoints of this time set to the specified
        IANA time zone.

        Leave empty time sets unchanged. For components with infinite
        endpoints, only apply the conversion to the finite endpoints.
        Leave the infinite endpoints unchanged.

        Args:
            `timezone_iana`: IANA time zone name
                (e.g., 'America/New_York').

        Returns:
            `TimeSet`: A new time set with endpoints converted
                to the target zone.

        Raises:
            `ValueError`: If the IANA zone name is invalid.
        '''

        if self.is_empty:
            return self
        
        return TimeSet(*(i.to_timezone(timezone_iana) for i in self.components))
    

    def normalize_time_zones(self) -> TimeSet:
        '''Convert this time set to a single time zone using the time
        zone of the leftmost finite endpoint.

        Returns:
            `TimeSet`: A new time set with all components in the same
                time zone.
        '''

        if self.is_empty or self.is_timeline:
            return self
        
        start_tz_iana = (
            self.start.timestamp.timezone_iana
            if self.start.is_finite
            else self.first_component.end.timestamp.timezone_iana
        )
        return self.to_timezone(start_tz_iana)
    

    def span(self) -> TimeInterval:
        '''Return the minimal interval covering the whole time set.

        Returns:
            `TimeInterval`: The time span from the earliest start
                to the latest end.
        '''

        return TimeInterval.minimal_cover(*self._components)
    

    def split_into_days(self) -> list[TimeSet]:
        '''Split this time set into calendar days.

        Returns:
            `list[TimeSet]`: List of time sets, each contained
            in a single day. Days are considered as closed-open
            intervals.
        '''

        if self.is_unbounded:
            raise ValueError('\'split_into_days\' is only supported for bounded time sets.')

        timeset = self.normalize_time_zones()
        days_set = timeset.days
        if not days_set:
            return []
        
        tz_iana = timeset.first_component.start.timestamp.timezone_iana
        result = []
        for day in sorted(days_set):
            start_ts = Timestamp.midnight(day, tz_iana)
            end_ts = start_ts + datetime.timedelta(days=1)
            day_interval = TimeInterval.closedopen(start_ts, end_ts)
            day_set = timeset & day_interval
            if day_set.is_nonempty:
                result.append(day_set)
        
        return result
    

    def complement(self) -> TimeSet:
        '''Create the complement of this time set (all points
        not in the set).'''

        # The complement of empty time set is the entire timeline.
        if self.is_empty:
            return TimeSet.timeline()

        new_components = []

        new_components.append(self.first_component.to_the_left())

        for f, s in zip(self._components, self._components[1:]):
            new_components.append(TimeInterval.between(f, s))

        new_components.append(self.last_component.to_the_right())

        return TimeSet.union(*new_components)


    def _scan(self, other: TimeSet) -> Iterator[tuple[TimeInterval, TimeInterval]]:
        '''Search for pairs of overlapping intervals in this time set
        and another one.'''

        i, j = 0, 0
        while i < self.components_number and j < other.components_number:
            self_interval = self.components[i]
            other_interval = other.components[j]

            if self_interval.is_left_of(other_interval):
                i += 1
                continue

            if self_interval.is_right_of(other_interval):
                j += 1
                continue
            
            # Intervals overlap.
            yield self_interval, other_interval

            # Increment the pointer of the interval that ends earlier.
            if self_interval.end < other_interval.end:
                i += 1
            else:
                j += 1


    def contains_timestamp(self, timestamp: Timestamp) -> bool:
        '''Return `True` if this time set contains the given
        timestamp.
        
        Args:
            `timestamp` (`Timestamp`): The timestamp to test.

        Returns:
            `bool`: `True` if contains, `False` otherwise.
        '''

        if self.is_empty:
            return False

        pos = bisect.bisect_right(self._starts, timestamp) - 1

        if pos < 0:
            return False

        return timestamp in self._components[pos]
    

    def contains_timeinterval(self, interval: TimeInterval) -> bool:
        '''Return `True` if this time set contains the given time
        interval.

        Args:
            `other` (`TimeInterval`): The time interval to test.
        
        Returns:
            `bool`: `True` if contains, `False` otherwise.
        '''

        if interval.is_empty:
            return True
        
        if self.is_empty:
            return False
        
        pos = bisect.bisect_right(self._starts, interval.start) - 1
        if pos < 0:
            return False
        return interval in self._components[pos]
    

    def contains_timeset(self, other: TimeSet) -> bool:
        '''Return `True` if this time set contains the given time
        set.
        
        Args:
            `other` (`TimeSet`): The time set to test.

        Returns:
            `bool`: `True` if contains, `False` otherwise.
        '''

        if other.is_empty:
            return True
        
        if self.is_empty:
            return False

        i, j = 0, 0
        n, m = self.components_number, other.components_number
        while j < m:
            if i >= n:
                return False

            if other.components[j] in self.components[i]:
                j += 1
            elif self.components[i].is_left_of(other.components[j]):
                i += 1
            else:
                return False

        return True
    

    def __contains__(self, other: object) -> bool:
        '''Return `True` if this time set contains the given object.

        Args:
            `other` (`Timestamp | TimeInterval | TimeSet`): The object
                to test.

        Returns:
            `bool`: `True` if contains, `False` otherwise.
        '''

        if isinstance(other, Timestamp):
            return self.contains_timestamp(other)
        
        if isinstance(other, TimeInterval):
            return self.contains_timeinterval(other)
        
        if isinstance(other, TimeSet):
            return self.contains_timeset(other)
        
        return False
    

    def is_left_of(self, other: TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set lies strictly to the left
        of the given object with no intersection.

        The object may be a `TimeInterval` or a `TimeSet`. This is
        automatically true if any of the sets are empty.
        '''

        if self.is_empty or other.is_empty:
            return True

        return self.end < other.start
    

    def is_right_of(self, other: TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set lies strictly to the right
        of the given object with no intersection.

        The object may be a `TimeInterval` or a `TimeSet`. This is
        automatically true if any of the sets are empty.
        '''

        if self.is_empty or other.is_empty:
            return True

        return other.end < self.start
    

    def overlaps_with_interval(self, other: TimeInterval) -> bool:
        '''Return `True` if this time set overlaps with the given time
        interval.'''

        if self.is_empty or other.is_empty:
            return False
        
        if other.start.is_infinite:
            # The interval is the left ray.
            return self.first_component.overlaps(other)
        
        if other.end.is_infinite:
            # The interval is the right ray.
            return self.last_component.overlaps(other)
        
        pos = bisect.bisect_left(self._starts, other.start)

        if pos > 0 and self._components[pos-1].overlaps(other):
            return True
        
        if pos < len(self._components) and self._components[pos].overlaps(other):
            return True
        
        return False
    

    def overlaps_with_timeset(self, other: TimeSet) -> bool:
        '''Return `True` if this time set overlaps with another time
        set.'''

        return next(self._scan(other), None) is not None
    

    def overlaps_with_days(self, days: set[datetime.date]) -> bool:
        '''Return `True` if this time set overlaps with the given set
        of calendar days.

        The method checks whether at least one of the connected
        components of the time set has any intersection with
        the specified days.

        Args:
            `days` (`set[datetime.date]`): The set of calendar dates
                to test for overlap.

        Returns:
            `bool`: `True` if the time set and the set of days share
            at least one common day, `False` otherwise.

        Raises:
            `ValueError`: If the time set is not normalized.
        '''

        if not self.is_normalized:
            raise ValueError(
                '\'overlaps_with_days\' is only supported for normalized time set.'
            )

        if self.is_empty or not days:
            return False
        # Sets of days are non-empty.

        min_day = min(days)
        max_day = max(days)

        for c in self.components:
            if c.is_right_bounded and c.last_day < min_day:
                continue
            if c.is_left_bounded and c.first_day > max_day:
                break
            if c.overlaps_with_days(days):
                return True
            
        return False
    

    def overlaps(self, other: TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set overlaps with the given time
        interval or another time set.'''

        if isinstance(other, TimeInterval):
            return self.overlaps_with_interval(other)
        elif isinstance(other, TimeSet):
            return self.overlaps_with_timeset(other)
        else:
            return NotImplemented
    

    def touches_interval(self, other: TimeInterval) -> bool:
        '''Return `True` if this time set touches the given time
        interval.'''

        if self.is_empty or other.is_empty:
            return False
        
        if other.start.is_infinite:
            # The interval is the left ray.
            return self.first_component.touches(other)
        
        if other.end.is_infinite:
            # The interval is the right ray.
            return self.last_component.touches(other)
        
        pos = bisect.bisect_left(self._starts, other.start)

        if pos > 0 and self._components[pos-1].touches(other):
            return True
        
        if pos < len(self._components) and self._components[pos].touches(other):
            return True
        
        return False
    

    def touches_timeset(self, other: TimeSet) -> bool:
        '''Return `True` if this time set touches another one.'''

        i, j = 0, 0
        n, m = self.components_number, other.components_number
        while i < n and j < m:
            self_interval = self.components[i]
            other_interval = other.components[j]

            if self_interval.is_left_of_disconnectedly(other_interval):
                i += 1
                continue

            if self_interval.is_right_of_disconnectedly(other_interval):
                j += 1
                continue
            
            # Intervals touch.
            return True
        return False
    

    def touches(self, other: TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set touches the given time set
        or time interval'''

        if isinstance(other, TimeInterval):
            return self.touches_interval(other)
        elif isinstance(other, TimeSet):
            return self.touches_timeset(other)
        else:
            return NotImplemented
    

    def __or__(self, other: TimeInterval | TimeSet) -> TimeSet:
        '''Return the union of this time set with another time set
        or a time interval.'''

        if isinstance(other, TimeInterval):
            return TimeSet.union(*self._components, other)
        
        if isinstance(other, TimeSet):
            return TimeSet.union(*self._components, *other._components)
        
        return NotImplemented
    

    def intersection_with_interval(self, interval: TimeInterval) -> TimeSet:
        '''Return the intersection of this time set with the given time
        interval.'''

        if self.is_empty or interval.is_empty:
            return TimeSet.empty()

        pos = bisect.bisect_left(self._starts, interval.start)

        start_idx = pos
        if pos and self._components[pos - 1].overlaps(interval):
            start_idx -= 1

        result = []

        for comp in self._components[start_idx:]:
            if comp.is_right_of(interval):
                break

            inter = comp & interval
            if inter.is_nonempty:
                result.append(inter)

        return TimeSet(*result)
    

    def intersection_with_timeset(self, other: TimeSet) -> TimeSet:
        '''Return the intersection of this time set with another time
        set.'''

        result = []
        for self_interval, other_interval in self._scan(other):
            intersection = self_interval & other_interval
            result.append(intersection)

        return TimeSet(*result)
    

    def __and__(self, other: TimeInterval | TimeSet) -> TimeSet:
        '''Return the intersection of this time set with another time
        set or a time interval.'''

        if isinstance(other, TimeInterval):
            return self.intersection_with_interval(other)
        
        if isinstance(other, TimeSet):
            return self.intersection_with_timeset(other)
        
        return NotImplemented
    

    def __sub__(self, other: TimeInterval | TimeSet):
        '''Return the difference of this time set and another time set
        or time interval.'''

        if isinstance(other, TimeInterval):
            other = TimeSet(other)

        if not isinstance(other, TimeSet):
            return NotImplemented

        return self & other.complement()


    @classmethod
    def empty(cls) -> TimeSet:
        '''Create the empty time set.'''

        return cls()
    

    @classmethod
    def timeline(cls) -> TimeSet:
        '''Create a time set representing the entire timeline.'''

        return cls(TimeInterval.timeline())


    @classmethod
    def union(cls, *arg: TimeInterval | TimeSet) -> TimeSet:
        '''Create the union of time intervals or time sets.

        The result consists of all time points that belong to at least
        one of the given arguments. It is represented as a `TimeSet`
        whose components are precisely the connected components of that
        union.

        Args:
            `*arg`: Time intervals or time sets whose union is to be
                constructed.

        Returns:
            `TimeSet`: The union of all provided arguments. If every
                argument is empty, the result is the empty time set.
        '''

        # Remove empty intervals.
        intervals = [
            i
            for ts in arg
            for i in (ts.components if isinstance(ts, TimeSet) else [ts])
            if i.is_nonempty
        ]

        # If there are no non-empty intervals, then the union is empty.
        if not intervals:
            return cls.empty()

        # Sort intervals chronologically.
        def sort_key(i: TimeInterval):
            return i.start, i.end

        intervals.sort(key=sort_key)

        # Group touching intervals.
        components = []
        current_component = intervals[0]

        for interval in intervals[1:]:
            if current_component.touches(interval):
                # New interval touches current component. Unite them.

                current_component = TimeInterval.minimal_cover(current_component, interval)
            else:
                # Interval does not touch last component. Keep previous
                # component and create new one.

                components.append(current_component)
                current_component = interval

        # Keep last component.
        components.append(current_component)

        # Construct time set.
        return cls(*components)
    

    def closure(self) -> TimeSet:
        '''Create the topological closure of this time set.'''

        return TimeSet.union(*map(TimeInterval.closure, self.components))
    

    def interior(self) -> TimeSet:
        '''Create the topological interior of this time set.'''

        return TimeSet.union(*map(TimeInterval.interior, self.components))
    

    @staticmethod
    def dist(first: TimeInterval | TimeSet, second: TimeInterval | TimeSet) -> Duration:
        '''Calculate the distance between two time sets or time
        intervals.
        
        If the sets overlap, return zero.
        '''

        if first.is_empty or second.is_empty:
            return Duration.undefined()
        
        if isinstance(first, TimeInterval):
            first = TimeSet(first)

        if isinstance(second, TimeInterval):
            second = TimeSet(second)

        if first.is_left_of(second):
            return second.start - first.end
        elif first.is_right_of(second):
            return first.start - second.end
        else:
            # Find the minimum distance between the components.
            i, j = 0, 0
            first_is_left_of_second = None
            distance = Duration.pos_inf()

            while i < first.components_number and j < second.components_number:
                if first.components[i].is_left_of(second.components[j]):
                    
                    if first_is_left_of_second is False:
                        components_dist = TimeInterval.dist(
                            first.components[i],
                            second.components[j - 1]
                        )

                        if components_dist is None:
                            raise AssertionError(
                                'The distance between two non-empty intervals cannot be \'None\'.'
                                )

                        distance = min(distance, components_dist)

                    first_is_left_of_second = True
                    i += 1
                elif first.components[i].is_right_of(second.components[j]):

                    if first_is_left_of_second is True:
                        components_dist = TimeInterval.dist(
                            first.components[i - 1],
                            second.components[j]
                        )

                        if components_dist is None:
                            raise AssertionError(
                                'The distance between two non-empty intervals cannot be \'None\'.'
                                )

                        distance = min(distance, components_dist)
                    
                    first_is_left_of_second = False
                    j += 1
                else:
                    # Components overlap.
                    return Duration()
            else:
                if first_is_left_of_second is True:
                    components_dist = TimeInterval.dist(
                            first.components[i - 1],
                            second.components[j]
                        )
                else:
                    components_dist = TimeInterval.dist(
                            first.components[i],
                            second.components[j - 1]
                        )
                    
                if components_dist is None:
                            raise AssertionError(
                                'The distance between two non-empty intervals cannot be \'None\'.'
                                )

                distance = min(distance, components_dist)

            return distance
