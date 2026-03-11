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



@dataclass(frozen=True)
@total_ordering
class Timestamp:
    '''Local date and time along with the time zone.

    Contains an aware datetime timestamp with a 'ZoneInfo' time zone.

    Requirements:
    - 'tzinfo' must be 'zoneinfo.ZoneInfo'.

    Notes:
    - This class strictly stores 'tzinfo' as 'zoneinfo.ZoneInfo'
      instances (IANA names).
    - Dependency: 'tzlocal' (for detecting local IANA zone name).'''


    _UTC = zoneinfo.ZoneInfo('Etc/UTC')    # UTC time zone.


    _dt: datetime.datetime
    

    @staticmethod
    def _is_valid_dt(dt: datetime.datetime) -> bool:
        '''Checks that the 'datetime' variable contains a valid
        'ZoneInfo' time zone.'''

        if dt.tzinfo is None:
            return False
        try:
            utc_off = dt.tzinfo.utcoffset(dt)
        except Exception:
            return False
        return utc_off is not None and isinstance(dt.tzinfo, zoneinfo.ZoneInfo)


    def __post_init__(self) -> None:
        if not Timestamp._is_valid_dt(self._dt):
            raise ValueError('The time zone has been set incorrectly.')
        
    
    def __str__(self) -> str:
        return f'{self.datetime_iso}'
    

    def __eq__(self, other: object) -> bool:
        '''Compares two timestamps in UTC.'''

        if not isinstance(other, Timestamp):
            return NotImplemented
        
        return self._dt.astimezone(Timestamp._UTC) == other._dt.astimezone(Timestamp._UTC)
    

    def __hash__(self) -> int:
        dt_utc = self._dt.astimezone(Timestamp._UTC)
        return hash(dt_utc)
    

    def __lt__(self, other: object) -> bool:
        '''Less-than comparison based on absolute (UTC) time.'''
    
        if not isinstance(other, Timestamp):
            return NotImplemented
        
        return self._dt.astimezone(Timestamp._UTC) < other._dt.astimezone(Timestamp._UTC)
    

    def __add__(self, other: datetime.timedelta) -> Timestamp:
        '''Time shift by a specified interval.'''

        if not isinstance(other, datetime.timedelta):
            return NotImplemented

        tz = self._dt.tzinfo
        dt_utc = self._dt.astimezone(Timestamp._UTC)
        dt_utc_new = dt_utc + other
        dt_new = dt_utc_new.astimezone(tz)
        return Timestamp(dt_new)
    

    @overload
    def __sub__(self, other: datetime.timedelta) -> Timestamp: ...


    @overload
    def __sub__(self, other: Timestamp) -> datetime.timedelta: ...
    

    def __sub__(self, other: datetime.timedelta | Timestamp) -> Timestamp | datetime.timedelta:
        '''The offset of a timestamp by a specified interval,
        or the difference between two timestamps.'''

        if isinstance(other, datetime.timedelta):
            return self + (-other)

        if isinstance(other, Timestamp):
            self_dt_utc = self._dt.astimezone(Timestamp._UTC)
            other_dt_utc = other._dt.astimezone(Timestamp._UTC)
            return self_dt_utc - other_dt_utc    # 'timedelta'.

        return NotImplemented
    

    @classmethod
    def from_utc(cls, dt_iso: str) -> Timestamp:
        '''Parse an ISO 8601 string and return a 'Timestamp' in UTC.

        Any strings containing timestamps with a non-zero offset are rejected.

        Accepted examples:
         - '2026-01-20T10:36'         (assumed UTC),
         - '2026-01-20T10:36Z'        (UTC),
         - '2026-01-20T10:36+00:00'   (zero offset).'''
        
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
        '''Creates a timestamp from an ISO 8601 string with offset
        and an IANA time zone.

        The ISO string must contain an offset (e.g.,
        '2026-03-04T15:15+03:00'). The method verifies that the offset
        is consistent with the actual offset of the IANA zone at that
        moment. If they match, the returned timestamp stores the local
        time in the given IANA zone.

        Args:
            iso_str: ISO 8601 datetime string that includes an offset
                (or 'Z' for UTC).
            iana_zone: IANA time zone name (e.g., 'Europe/Moscow').

        Returns:
            A new 'Timestamp' object representing the same moment but
            normalised to the specified IANA zone.

        Raises:
            ValueError: If the ISO string cannot be parsed, if the IANA
                zone is unknown, or if the offset in the ISO string
                does not match the zone's offset for that moment.'''
        
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
        except Exception as e:
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
    def now(cls) -> Timestamp:
        '''Creates a new timestamp with the current local time.'''

        try:
            tz = zoneinfo.ZoneInfo(tzlocal.get_localzone_name())
            return cls(datetime.datetime.now(tz))
        except Exception as e:
            raise RuntimeError(
                'Failed to determine local time zone.'
            ) from e
    

    @classmethod
    def now_utc(cls) -> Timestamp:
        '''Creates a new timestamp with the current time in UTC.'''
        
        try:
            return cls(datetime.datetime.now(Timestamp._UTC))
        except Exception as e:
            raise RuntimeError('Failed to determine UTC time.') from e
    

    @property
    def datetime(self) -> datetime.datetime:
        return self._dt
    

    @property
    def datetime_iso(self) -> str:
        '''Returns the timestamp in ISO 8601 format in the time zone
        in which it was recorded.'''
        
        return self._dt.isoformat()
    

    @property
    def timezone_iana(self) -> str:
        '''Returns the time zone of this timestamp in IANA format.'''

        if not isinstance(self._dt.tzinfo, zoneinfo.ZoneInfo):
            raise ValueError('The time zone has been set incorrectly.')

        return self._dt.tzinfo.key
    

    def to_timezone(self, timezone_iana: str) -> Timestamp:
        '''Creates a new timestamp by converting the given one to
        the specified time zone.'''

        try:
            tz = zoneinfo.ZoneInfo(timezone_iana)
        except Exception as e:
            # 'ZoneInfo' raises 'ZoneInfoNotFoundError' (subclass
            # of Exception) on bad names.
            raise ValueError(f'Invalid IANA time zone: {timezone_iana}') from e

        dt = self._dt.astimezone(tz)
        return Timestamp(dt)


    def to_utc(self) -> Timestamp:
        '''Creates a new timestamp by converting the given one
        to UTC.'''
        
        dt_utc = self._dt.astimezone(Timestamp._UTC)
        return Timestamp(dt_utc)
    

    @property
    def utc_iso(self) -> str:
        '''Returns an ISO 8601 string in UTC.'''
    
        dt_utc = self._dt.astimezone(Timestamp._UTC)
        return dt_utc.replace(tzinfo=None).isoformat() + 'Z'



@dataclass(frozen=True)
class TimeInterval:
    '''A time interval representing a connected subset of the time line.

    The interval may be:
        - empty,
        - a single point,
        - a bounded open, closed, or half-open interval,
        - a left or right unbounded ray,
        - the entire time line.

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


    _kind: Kind = Kind.EMPTY
    _start: Timestamp | None = None
    _end: Timestamp | None = None


    def _is_valid(self) -> bool:
        '''Check that the time interval is set correctly.'''

        match self._kind:
            case TimeInterval.Kind.EMPTY:
                return self._start is None and self._end is None

            case TimeInterval.Kind.POINT:
                return (
                    self._start is not None
                    and self._end is not None
                    and self._start == self._end
                )

            case (
                TimeInterval.Kind.OPEN |
                TimeInterval.Kind.CLOSED |    # Not a point.
                TimeInterval.Kind.CLOSED_OPEN |
                TimeInterval.Kind.OPEN_CLOSED
            ):
                return (
                    self._start is not None
                    and self._end is not None
                    and self._start < self._end
                )
            
            case TimeInterval.Kind.RIGHT_OPEN | TimeInterval.Kind.RIGHT_CLOSED:
                return self._start is not None and self._end is None
            
            case TimeInterval.Kind.LEFT_OPEN | TimeInterval.Kind.LEFT_CLOSED:
                return self._start is None and self._end is not None

            case TimeInterval.Kind.TIMELINE:
                return self._start is None and self._end is None

        return False

    
    def __post_init__(self) -> None:

        if not self._is_valid():
            raise ValueError('The time interval has been set incorrectly.')
        

    def __str__(self) -> str:

        match self._kind:
            case TimeInterval.Kind.EMPTY:
                # Returns the empty set symbol. 
                return '\u2205'

            case TimeInterval.Kind.POINT:
                return f'{{{self._start}}}'

            case TimeInterval.Kind.OPEN:
                return f'({self._start}; {self._end})'

            case TimeInterval.Kind.CLOSED:
                return f'[{self._start}; {self._end}]'
            
            case TimeInterval.Kind.CLOSED_OPEN:
                return f'[{self._start}; {self._end})'

            case TimeInterval.Kind.OPEN_CLOSED:
                return f'({self._start}; {self._end}]'
            
            case TimeInterval.Kind.RIGHT_OPEN:
                return f'({self._start}; +\u221E)'

            case TimeInterval.Kind.RIGHT_CLOSED:
                return f'[{self._start}; +\u221E)'

            case TimeInterval.Kind.LEFT_OPEN:
                return f'(-\u221E; {self._end})'

            case TimeInterval.Kind.LEFT_CLOSED:
                return f'(-\u221E; {self._end}]'
            
            case TimeInterval.Kind.TIMELINE:
                return '(-\u221E; +\u221E)'

        raise AssertionError(f'Unhandled \'TimeInterval.Kind\': {self._kind}.')

        
    
    def __bool__(self) -> bool:
        '''Check that the interval is non-empty.'''

        return self._kind is not TimeInterval.Kind.EMPTY
    

    def __contains__(self, other: object) -> bool:
        
        if isinstance(other, Timestamp | TimeInterval):
            return self.contains(other)
        else:
            return False
    

    def __and__(self, other: TimeInterval) -> TimeInterval:
        '''Create the intersection of two time intervals.'''

        # Quick checks for empty/timeline.
        if self.is_empty or other.is_empty:
            # An intersection with an empty interval is empty.
            return TimeInterval.empty()
        if self.is_timeline:
            return other
        if other.is_timeline:
            return self
        # From this point onwards, intervals are considered to be
        # non-empty and not to be the entire timeline.

        # Calculating the start of the intersection.
        if self.is_start_specified and other.is_start_specified:
            # The start of each interval is explicitly specified
            # (neither lies at infinity).

            # Calculating the start of the intersection.
            assert self.start is not None
            assert other.start is not None
            new_start = max(self.start, other.start)

            # Calculating whether or not the start is included
            # in the intersection.
            assert self.is_start_included is not None
            assert other.is_start_included is not None
            if self.start < other.start:
                new_start_included = other.is_start_included
            elif self.start > other.start:
                new_start_included = self.is_start_included
            else:
                new_start_included = self.is_start_included and other.is_start_included
        elif not self.is_start_specified and not other.is_start_specified:
            # The start of each interval is not specified (they lie
            # at infinity).
            
            new_start = None
            new_start_included = None
        else:
            # Only the start of one of the intervals is specified
            # (it doesn't lie at infinity).

            # Calculating the start of the intersection.
            new_start = self.start or other.start

            # Calculating whether or not the start is included
            # in the intersection.
            new_start_included = (
                self.is_start_included
                if self.is_start_specified
                else other.is_start_included
            )        

        # Calculating the end of the intersection.
        if self.is_end_specified and other.is_end_specified:
            # The end of each interval is explicitly specified
            # (neither lies at infinity).

            # Calculating the end of the intersection.
            assert self.end is not None
            assert other.end is not None
            new_end = min(self.end, other.end)

            # Calculating whether or not the end is included
            # in the intersection.
            assert self.is_end_included is not None
            assert other.is_end_included is not None
            if self.end < other.end:
                new_end_included = self.is_end_included
            elif self.end > other.end:
                new_end_included = other.is_end_included
            else:
                new_end_included = self.is_end_included and other.is_end_included
        elif not self.is_end_specified and not other.is_end_specified:
            # The end of each interval is not specified (they lie
            # at infinity).
            
            new_end = None
            new_end_included = None
        else:
            # Only the end of one of the intervals is specified
            # (it doesn't lie at infinity).

            # Calculating the end of the intersection.
            new_end = self.end or other.end

            # Calculating whether or not the end is included
            # in the intersection.
            new_end_included = (
                self.is_end_included
                if self.is_end_specified
                else other.is_end_included
            )  

        # Checking the resulting intersection for emptiness.
        if new_start is not None and new_end is not None:
            # The start and end of the intersection are clearly
            # specified, i.e. they do not lie at infinity.
            if new_start_included is True and new_end_included is True:
                # Both intersection boundaries are included.
                if new_start > new_end:
                    return TimeInterval.empty()
            else:
                # At least one intersection boundary is not included.
                if new_start >= new_end:
                    return TimeInterval.empty()
                
        return TimeInterval.from_boundaries(
            start=new_start,
            end=new_end,
            start_included=new_start_included,
            end_included=new_end_included
        )
    

    @classmethod
    def empty(cls) -> TimeInterval:
        '''Create the empty time interval.'''

        return cls(_kind=TimeInterval.Kind.EMPTY, _start=None, _end=None)


    @classmethod
    def point(cls, moment: Timestamp) -> TimeInterval:
        '''Create a point. It corresponds to an instantaneous event.'''

        return cls(_kind=TimeInterval.Kind.POINT, _start=moment, _end=moment)
    

    @classmethod
    def open(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty open bounded time interval.'''

        if start >= end:
            raise ValueError(
                'The start of the interval is either simultaneous with its end or occurs later, '
                'which is not correct.'
            )

        return cls(_kind=TimeInterval.Kind.OPEN, _start=start, _end=end)
    

    @classmethod
    def closed(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty closed bounded time interval, not a point.
        
        To create a point use the 'point' constructor.
        '''

        if start >= end:
            raise ValueError(
                'Either the start of the interval occurs after its end, which is incorrect, '
                'or it\'s a point.'
            )

        return cls(_kind=TimeInterval.Kind.CLOSED, _start=start, _end=end)
    

    @classmethod
    def closedopen(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty bounded closed-open interval.'''

        if start >= end:
            raise ValueError(
                'The start of the interval is either simultaneous with its end or occurs later, '
                'which is not correct.'
            )

        return cls(_kind=TimeInterval.Kind.CLOSED_OPEN, _start=start, _end=end)
    

    @classmethod
    def openclosed(cls, start: Timestamp, end: Timestamp) -> TimeInterval:
        '''Create a non-empty bounded open-closed interval.'''

        if start >= end:
            raise ValueError(
                'The start of the interval is either simultaneous with its end or occurs later, '
                'which is not correct.'
            )

        return cls(_kind=TimeInterval.Kind.OPEN_CLOSED, _start=start, _end=end)
    

    @classmethod
    def rightclosed(cls, start: Timestamp) -> TimeInterval:
        '''Create a closed right-ray.'''

        return cls(_kind=TimeInterval.Kind.RIGHT_CLOSED, _start=start)
    

    @classmethod
    def rightopen(cls, start: Timestamp) -> TimeInterval:
        '''Create an open right-ray.'''

        return cls(_kind=TimeInterval.Kind.RIGHT_OPEN, _start=start)
    

    @classmethod
    def right_ray(cls, start: Timestamp, start_included: bool) -> TimeInterval:
        '''Create a right-ray with a specified left boundary kind.'''

        if start_included:
            return cls(_kind=TimeInterval.Kind.RIGHT_CLOSED, _start=start)
        else:
            return cls(_kind=TimeInterval.Kind.RIGHT_OPEN, _start=start)
    

    @classmethod
    def leftclosed(cls, end: Timestamp) -> TimeInterval:
        '''Create a closed left ray.'''

        return cls(_kind=TimeInterval.Kind.LEFT_CLOSED, _end=end)
    

    @classmethod
    def leftopen(cls, end: Timestamp) -> TimeInterval:
        '''Create an open left ray.'''

        return cls(_kind=TimeInterval.Kind.LEFT_OPEN, _end=end)
    

    @classmethod
    def left_ray(cls, end: Timestamp, end_included: bool) -> TimeInterval:
        '''Create a left-ray with a specified right boundary kind.'''

        if end_included:
            return cls(_kind=TimeInterval.Kind.LEFT_CLOSED, _end=end)
        else:
            return cls(_kind=TimeInterval.Kind.LEFT_OPEN, _end=end)
    

    @classmethod
    def timeline(cls) -> TimeInterval:
        '''Create the entire timeline.'''

        return cls(_kind=TimeInterval.Kind.TIMELINE)
    

    @classmethod
    def from_boundaries(
        cls,
        start: Timestamp | None, end: Timestamp | None,
        start_included: bool | None, end_included: bool | None
    ) -> TimeInterval:
        '''Create a time interval from its boundaries.

        Construct a time interval by explicitly providing the start
        and end points, along with flags indicating whether each
        boundary is included. If neither boundary is specified,
        the resulting interval is the entire timeline. An empty interval
        cannot be created with this method; use the `empty()`
        constructor instead.

        Args:
            `start`: The left boundary of the interval, or `None`
                if the interval is unbounded on the left.
            `end`: The right boundary of the interval, or `None`
                if the interval is unbounded on the right.
            `start_included`: `True` if the left boundary is included,
                `False` if excluded. Must be `None` if `start`
                is `None`.
            `end_included`: `True` if the right boundary is included,
                `False` if excluded. Must be `None` if `end` is `None`.

        Returns:
            A new `TimeInterval` instance representing the specified set
            of points.

        Raises:
            `ValueError`: If any combination of arguments is invalid,
            e.g.:
                - both boundaries are specified but `start` > `end`;
                - boundaries are specified but inclusion flags
                    are `None`;
                - boundary is not specified but the corresponding
                    inclusion flag is not `None`.
        '''
        
        if start is not None and end is not None:
            # Both boundaries of the interval are specified. This is
            # a (non-empty) bounded interval.

            if start_included is None or end_included is None:
                raise ValueError(
                    'The interval is set incorrectly. If the boundaries are specified, they '
                    'must be included or excluded. The values \'start_included\' '
                    'and \'end_included\' must be \'True\' or \'False\'.'
                )

            if start_included and end_included:
                # Both the start and end of the interval are included.
                # This is a closed (non-empty, bounded) interval. This
                # may be the point.

                if start > end:
                    raise ValueError(
                        'The interval is set incorrectly. The start of the interval cannot occur '
                        'later than the end.'
                    )
                
                if start == end:
                    # The interval is a point.
                    return TimeInterval.point(start)
                
                return TimeInterval.closed(start, end)
            
            elif start_included and not end_included:
                # The start of the interval is included, but the end
                # is not. This is a closed-open (non-empty, bounded)
                # interval.

                if start >= end:
                    raise ValueError(
                        'The interval is set incorrectly. The start of the closed-open interval '
                        'cannot occur after the end, or coincide with it.'
                    )

                return TimeInterval.closedopen(start, end)
            
            elif not start_included and end_included:
                # The start of the interval is not included, but the end
                # is included. This is an open-closed (non-empty,
                # bounded) interval.

                if start >= end:
                    raise ValueError(
                        'The interval is set incorrectly. The start of the open-closed interval '
                        'cannot occur after the end, or coincide with it.'
                    )

                return TimeInterval.openclosed(start, end)
            
            else:
                # Both the start and end of the interval
                # are not included. This is an open (non-empty, bounded)
                # interval.

                if start >= end:
                    raise ValueError(
                        'The interval is set incorrectly. The start of the open interval cannot '
                        'occur after the end, or coincide with it.'
                    )

                return TimeInterval.open(start, end)
                
        elif start is not None and end is None:
            # The start of the interval is specified, but not the end.
            # This is the right-ray.

            if end_included is not None:
                raise ValueError(
                    'The interval is set incorrectly. If the end is not specified, it cannot be '
                    'included or excluded. The value \'end_included\' must be \'None\'.'
                )
            
            if start_included:
                # The start of the interval is included. This is a right
                # closed ray.

                return TimeInterval.rightclosed(start)
            else:
                # The start of the interval is not included. This is
                # a right open ray.
                
                return TimeInterval.rightopen(start)
            
        elif start is None and end is not None:
            # The start of the interval is not specified, but
            # its end is. This is the left ray.

            if start_included is not None:
                raise ValueError(
                    'The interval is set incorrectly. If the start is not specified, it cannot be '
                    'included or excluded. The value \'start_included\' must be \'None\'.'
                )
            
            if end_included:
                # The end of the interval is included. This is a left
                # closed ray.

                return TimeInterval.leftclosed(end)
            else:
                # The end of the interval is not included. This is
                # a left open ray.
                
                return TimeInterval.leftopen(end)
            
        else:
            # The start and end of the interval are not specified.

            if start_included is not None or end_included is not None:
                raise ValueError(
                    'The interval is set incorrectly. If the boundaries are not specified, they '
                    'cannot be included or excluded. The values \'start_included\' '
                    'and \'end_included\' must be \'None\'.'
                )
            
            # If both boundaries are not specified, the interval
            # is considered to be the entire timeline.
            return TimeInterval.timeline()
    

    @classmethod
    def from_dict(cls, time_data: dict, date_iso: str = '') -> TimeInterval:
        '''Create a closed-open interval or a point from a dictionary.

        The dictionary must contain:
            - `start_time` / `end_time`: ISO time strings including
                offset, e.g. '10:30+03:00');
            - `start_timezone` / `end_timezone` : IANA zone names
                (e.g. 'Europe/Moscow').

        If `date_iso` is provided (YYYY-MM-DD), it is combined with
        the time strings to form full ISO datetimes. In this mode,
        if `end_time` starts with '24:', it is interpreted as the end
        of that day (validated, then replaced with '00:' and the date
        advanced). If `date_iso` is omitted, `start_time` and `end_time`
        must be complete ISO datetime strings including date and offset.

        Args:
            `time_data`: Dictionary with the four required keys.
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
            ...     'start_time': '09:00+03:00',
            ...     'start_timezone': 'Europe/Moscow',
            ...     'end_time': '18:00+03:00',
            ...     'end_timezone': 'Europe/Moscow'
            ... }, '2026-03-09')
            [2026-03-09T09:00:00+03:00; 2026-03-09T18:00:00+03:00)

            Using '24:00' to denote the end of the day:
            >>> TimeInterval.from_dict({
            ...     'start_time': '09:00Z',
            ...     'start_timezone': 'UTC',
            ...     'end_time': '24:00Z',
            ...     'end_timezone': 'UTC'
            ... }, 2026-03-09')
            [2026-03-09T09:00:00+00:00; 2026-03-10T00:00:00+00:00)

            Without a common date (full ISO strings expected):
            >>> TimeInterval.from_dict({
            ...     'start_time': '2026-03-09T09:00+03:00',
            ...     'start_timezone': 'Europe/Moscow',
            ...     'end_time': '2026-03-10T18:00+03:00',
            ...     'end_timezone': 'Europe/Moscow'
            ... })
            [2026-03-09T09:00:00+03:00; 2026-03-10T18:00:00+03:00)
        '''

        if not isinstance(time_data, dict):
            raise TypeError('\'time_data\' must be a dict.')
        
        # Checking for extra keys in the dictionary.
        allowed_keys = {'start_time', 'start_timezone', 'end_time', 'end_timezone'}
        extra_keys = set(time_data) - allowed_keys
        if extra_keys:
            extra_keys_str = ', '.join(f'\'{k}\'' for k in sorted(extra_keys))
            warnings.warn(
                f'Time interval dictionary contains unknown fields: {extra_keys_str}.',
                stacklevel=2
            )
        
        # Helper to fetch required string values.
        def get_str(key: str) -> str:
            try:
                value = time_data[key]
            except KeyError:
                raise ValueError(f'Time interval dictionary missing required key \'{key}\'.')
            if not isinstance(value, str):
                raise TypeError(f'Value \'{key}\' must be a string, got \'{type(value).__name__}\'.')
            return value

        start_time_iso = get_str('start_time')
        start_timezone_iana = get_str('start_timezone')
        end_time_iso = get_str('end_time')
        end_timezone_iana = get_str('end_timezone')

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
            start_ts = Timestamp.from_iso_iana(start_datetime_iso, start_timezone_iana)
        except ValueError as e:
            raise ValueError(f'Incorrect start time format. {e}') from e
        
        try:
            end_ts = Timestamp.from_iso_iana(end_datetime_iso, end_timezone_iana)
        except ValueError as e:
            raise ValueError(f'Incorrect end time format. {e}') from e

        if start_ts < end_ts:
            return TimeInterval.closedopen(start_ts, end_ts)
        elif start_ts == end_ts:
            return TimeInterval.point(start_ts)
        else:
            raise ValueError('The start of a time interval cannot be later than its end.')
    

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

        Raises:
            `ValueError`: If the constructed interval would be invalid
                (e.g., the combined boundaries produce an inconsistent
                interval). This should not happen under normal
                circumstances.
        '''

        # Remove empty intervals.
        nonempty_intervals = [i for i in intervals if not i.is_empty]

        # If there are no non-empty intervals, then the cover is empty.
        if not nonempty_intervals:
            return cls.empty()

        # Find the left boundary, i.e. minimal start. ('None'
        # is considered the smallest because it denotes a boundary that
        # lies at infinity.)
        def start_key(i: TimeInterval):
            return (i.start is not None, i.start)

        leftmost = min(nonempty_intervals, key=start_key)

        start = leftmost.start

        # The start is included if it is included in at least one
        # of the intervals.
        start_included = (
            None if start is None
            else any(
                i.start == start and i.is_start_included
                for i in nonempty_intervals
            )
        )

        # Find the right boundary, i.e. maximal end. ('None'
        # is considered the largest because it denotes a boundary that
        # lies at infinity.)
        def end_key(i: TimeInterval):
            return (i.end is None, i.end)

        rightmost = max(nonempty_intervals, key=end_key)

        end = rightmost.end

        # The end is included if it is included in at least one
        # of the intervals.
        end_included = (
            None if end is None
            else any(
                i.end == end and i.is_end_included
                for i in nonempty_intervals
            )
        )

        # Construct the covering interval.
        return cls.from_boundaries(
            start=start,
            end=end,
            start_included=start_included,
            end_included=end_included
        )
    

    def to_the_right(self) -> TimeInterval:
        '''Create the interval consisting of all points to the right
        of this interval.

        The new interval contains every point that lies strictly
        to the right of every point in the current interval.
        If the current interval is empty, the result is the entire
        timeline.

        Returns:
            A new `TimeInterval` representing the open or closed right
            ray starting just after the current interval's end.
            The boundary inclusion is the opposite of the current
            interval's right-end inclusion.
        '''

        if self.is_empty:
            return TimeInterval.timeline()
        # From this point onwards, the interval is considered
        # to be non-empty.

        if self.end is None:
            # The interval is unbounded on the right.
            return TimeInterval.empty()
        else:
            # The interval is bounded on the right.
            return TimeInterval.right_ray(self.end, not self.is_end_included)
    

    def to_the_left(self) -> TimeInterval:
        '''Create the interval consisting of all points to the left
        of this interval.

        The new interval contains every point that lies strictly
        to the left ofevery point in the current interval.
        If the current interval is empty, the result is the entire
        timeline.

        Returns:
            A new `TimeInterval` representing the open or closed left
            ray ending just before the current interval's start.
            The boundary inclusion is the opposite of the current
            interval's left-end inclusion.
        '''

        if self.is_empty:
            return TimeInterval.timeline()
        # From this point onwards, the interval is considered
        # to be non-empty.

        if self.start is None:
            # The interval is unbounded on the left.
            return TimeInterval.empty()
        else:
            # The interval is bounded on the left.
            return TimeInterval.left_ray(self.start, not self.is_start_included)
    

    @classmethod
    def between(cls, first: TimeInterval, second: TimeInterval) -> TimeInterval:
        '''Create the interval that lies strictly between two intervals.

        The resulting interval consists of all points that are
        to the right of the first time interval and to the left
        of the second time interval. The order of the arguments matters.
        Empty intervals are allowed.

        Args:
            `first`: The left-hand interval.
            `second`: The right-hand interval.

        Returns:
            A new `TimeInterval` representing the space between
            the two intervals. If the intervals touch or overlap,
            an empty interval is returned. If both intervals are empty,
            the entire timeline is returned. If only one interval
            is empty, the result is the corresponding ray.
        '''

        if not first.is_left_of(second):
            return TimeInterval.empty()
        # From this point onwards, the first interval is considered
        # to lie to the left of the second.

        if first.is_empty and second.is_empty:
            return TimeInterval.timeline()
        elif first.is_nonempty and second.is_empty:
            return first.to_the_right()
        elif first.is_empty and second.is_nonempty:
            return second.to_the_left()
        else:
            # Both intervals are non-empty.

            if first.end is None or second.start is None:
                # The first interval is unbound on the right
                # or the second is unbound on the left.

                return TimeInterval.empty()
            else:
                # The first interval is bounded on the right
                # and the second interval is bounded on the left.

                if first.end > second.start:
                    return TimeInterval.empty()
                elif first.end == second.start:
                    if first.is_end_included or second.is_start_included:
                        return TimeInterval.empty()
                    else:
                        return TimeInterval.point(first.end)
                else:
                    return TimeInterval.from_boundaries(
                        start=first.end,
                        end=second.start,
                        start_included=not first.is_end_included,
                        end_included=not second.is_start_included
                    )
    

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

        match self._kind:
            case (
                TimeInterval.Kind.OPEN |
                TimeInterval.Kind.CLOSED_OPEN |
                TimeInterval.Kind.OPEN_CLOSED
            ):
                return TimeInterval(
                    _kind=TimeInterval.Kind.CLOSED,
                    _start=self.start,
                    _end=self.end
                )
            case TimeInterval.Kind.RIGHT_OPEN:
                return TimeInterval(
                    _kind=TimeInterval.Kind.RIGHT_CLOSED,
                    _start=self.start
                )
            case TimeInterval.Kind.LEFT_OPEN:
                return TimeInterval(
                    _kind=TimeInterval.Kind.LEFT_CLOSED,
                    _end=self.end
                )
            case _:
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

        match self._kind:
            case TimeInterval.Kind.POINT:
                return TimeInterval.empty()
            case (
                TimeInterval.Kind.CLOSED |
                TimeInterval.Kind.CLOSED_OPEN |
                TimeInterval.Kind.OPEN_CLOSED
            ):
                return TimeInterval(
                    _kind=TimeInterval.Kind.OPEN,
                    _start=self.start,
                    _end=self.end
                )
            case TimeInterval.Kind.RIGHT_CLOSED:
                return TimeInterval(
                    _kind=TimeInterval.Kind.RIGHT_OPEN,
                    _start=self.start
                )
            case TimeInterval.Kind.LEFT_CLOSED:
                return TimeInterval(
                    _kind=TimeInterval.Kind.LEFT_OPEN,
                    _end=self.end
                )
            case _:
                return self


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
        Therefore the empty interval is considered to be bounded.'''

        return self._kind in TimeInterval._BOUNDED_KINDS
    

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
    def start(self) -> Timestamp | None:
        '''Return the start of this time interval. If it is not defined,
        when the interval is empty or unbounded on the left, return
        `None`.'''

        return self._start
    

    @property
    def end(self) -> Timestamp | None:
        '''Return the end of this time interval. If it is not defined,
        when the interval is empty or unbounded on the right, return
        `None`.'''

        return self._end


    @property
    def is_start_specified(self) -> bool:
        '''Return `True` if the start of this interval is specified.'''

        return self._kind in TimeInterval._START_SPECIFIED_KINDS


    @property
    def is_end_specified(self) -> bool:
        '''Return `True` if the end of this interval is specified.'''

        return self._kind in TimeInterval._END_SPECIFIED_KINDS


    @property
    def is_start_included(self) -> bool | None:
        '''If the start of this interval is specified, return `True`
        if it is included in the interval. If the start
        is not specified, return `None`.'''

        if self._kind in TimeInterval._START_SPECIFIED_KINDS:
            return self._kind in TimeInterval._START_INCLUDED_KINDS
        else:
            return None
    

    @property
    def is_end_included(self) -> bool | None:
        '''If the end of this interval is specified, return `True`
        if it is included in the interval. If the end
        is not specified, return `None`.'''

        if self._kind in TimeInterval._END_SPECIFIED_KINDS:
            return self._kind in TimeInterval._END_INCLUDED_KINDS
        else:
            return None


    @property
    def inf(self) -> Timestamp | None:
        '''Return the infimum of this time interval. If it is
        not defined, when the interval is empty or unbounded
        on the left, return `None`.'''

        return self._start
    

    @property
    def sup(self) -> Timestamp | None:
        '''Return the supremum of this time interval. If it is
        not defined, when the interval is empty or unbounded
        on the right, return `None`.'''
        
        return self._end
    

    @property
    def duration(self) -> datetime.timedelta | None:
        '''Return the duration of the time interval.

        If the duration is not defined (in the case of an unbounded
        interval), return `None`. The duration of the empty interval
        is zero.'''

        if self.is_bounded:
            # The interval is bounded.
            if self.is_empty:
                # The interval is empty.
                return datetime.timedelta()
            else:
                # The interval is bounded and non-empty.
                if self._start is None or self._end is None:
                    # At least one of the interval boundaries has not
                    # been specified, which contradicts its boundedness.
                    raise ValueError(
                        'It is impossible to determine the start or end of the time interval.'
                    )

                return self._end - self._start
        else:
            return None


    def contains_timestamp(self, moment: Timestamp) -> bool:
        '''Return `True` if the given moment in time falls within
        the time interval.
        
        Args:
            `moment`: The `Timestamp` to test.

        Returns:
            `True` if `moment` lies inside the interval (taking boundary
            inclusion into account), otherwise `False`. For an empty
            interval, always `False`
        '''

        if not isinstance(moment, Timestamp):
            return False

        if self.is_empty:
            return False

        if self.is_timeline:
            return True
        # From this point onwards, the interval is considered to be
        # non-empty, but not the entire timeline.
        
        left_ok = True
        right_ok = True

        if self.start is not None:
            if self.is_start_included:
                left_ok = moment >= self.start
            else:
                left_ok = moment > self.start

        if self.end is not None:
            if self.is_end_included:
                right_ok = moment <= self.end
            else:
                right_ok = moment < self.end
            
        return left_ok and right_ok
    

    def contains_timeinterval(self, interval: TimeInterval) -> bool:
        '''Return `True` if this interval contains another one.
        
        An interval A contains interval B if every point of B is also
        a point of A. An empty interval is contained in any interval.

        Args:
            `interval`: The `TimeInterval` to test.

        Returns:
            `True` if `interval` is entirely within this interval,
            otherwise `False`.
        '''

        # Any contains an empty interval.
        if interval.is_empty:
            return True
        # From this point onwards, we will consider 'other' to be
        # non-empty. An empty interval cannot contain a non-empty one.

        if self.is_empty:
            return False

        # Checking the left boundary.
        if interval.start is not None:
            # 'other' is bounded on the left.
            if self.start is None:
                # 'self' is unbounded on the left.
                left_ok = True
            else:
                # 'self' is bounded on the left.

                if self.start < interval.start:
                    left_ok = True
                elif self.start == interval.start:
                    left_ok = (
                        self.is_start_included
                        or not interval.is_start_included
                    )
                else:
                    left_ok = False
        else:
            # 'other' is unbounded on the left.
            left_ok = self.start is None

        if not left_ok:
            return False

        # Checking the right boundary.
        if interval.end is not None:
            # 'other' is bounded on the right.
            if self.end is None:
                # 'self' is unbounded on the right.
                right_ok = True
            else:
                # 'self' is bounded on the right.

                if self.end > interval.end:
                    right_ok = True
                elif self.end == interval.end:
                    right_ok = (
                        self.is_end_included
                        or not interval.is_end_included
                    )
                else:
                    right_ok = False
        else:
            # 'other' is unbounded on the right.
            right_ok = self.end is None

        return right_ok


    def contains(self, other: Timestamp | TimeInterval) -> bool:
        '''Return `True` if this interval contains a timestamp 
        or another time interval.

        Args:
            `other`: A `Timestamp` or a `TimeInterval` to test
            for containment.

        Returns:
            `True` if `other` is contained in this interval, otherwise
            `False`.

        Raises:
            `TypeError`: If `other` is neither a `Timestamp`
            nor a `TimeInterval`.
        '''

        if isinstance(other, Timestamp):
            return self.contains_timestamp(other)
        elif isinstance(other, TimeInterval):
            return self.contains_timeinterval(other)
        else:
            return NotImplemented
        

    def is_contained_in(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval is contained in another
        one.

        Equivalent to `other.contains(self)`.

        Args:
            `other`: The `TimeInterval` that might contain this one.

        Returns:
            `True` if this interval is entirely inside `other`,
            otherwise `False`.
        '''

        return other.contains(self)
    

    def is_left_of(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the left
        of another one and does not overlap with it.
        
        The interval is considered to lie to the left if all its points
        are before all points of another one and the two intervals
        do not overlap. If either interval is empty, the condition
        is true.

        Args:
            `other`: The `TimeInterval` to compare with.

        Returns:
            `True` if this interval is completely to the left of `other`
            without touching or overlapping, otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return True
        # From this point onwards, both intervals are considered
        # to be non-empty.

        if self.end is not None and other.start is not None:
            # 'self' is bounded on the right and 'other' is bounded
            # on the left.

            if self.end < other.start:
                return True
            if self.end == other.start:
                return self.is_end_included is False or other.is_start_included is False
            
        return False
    

    def is_right_of(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the right
        of another one and does not overlap with it.
        
        The interval is considered to lie to the right if all its points
        are after all points of another one and the two intervals
        do not overlap. If either interval is empty, the condition
        is true.

        Args:
            `other`: The `TimeInterval` to compare with.

        Returns:
            `True` if this interval is completely to the right
            of `other` without touching or overlapping, otherwise
            `False`.
        '''

        if self.is_empty or other.is_empty:
            return True
        # From this point onwards, both intervals are considered
        # to be non-empty.

        if other.end is not None and self.start is not None:
            # 'other' is bounded on the right and 'self' is bounded
            # on the left.

            if other.end < self.start:
                return True
            if other.end == self.start:
                return other.is_end_included is False or self.is_start_included is False
            
        return False
    

    def is_left_of_disconnectedly(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval lies strictly to the left
        of another one, does not overlap with it and their union
        will be a disconnected set.

        This is a stronger condition than `is_left_of`: it requires that
        there is at least one point between the intervals, i.e., they
        do not touch. If either interval is empty, the result is `False`
        because a disconnected union cannot be formed with an empty set.
        
        Args:
            `other`: The `TimeInterval` to compare with.

        Returns:
            `True` if this interval lies completely to the left
            of `other` and there is a non-empty gap between them,
            otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return False
        # From this point onwards, both intervals are considered
        # to be non-empty.
        
        if self.end is not None and other.start is not None:
            # 'self' is bounded on the right and 'other' is bounded
            # on the left.

            if self.end < other.start:
                return True
            if self.end == other.start:
                return self.is_end_included is False and other.is_start_included is False
            
        return False
    

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
            `other`: The `TimeInterval` to compare with.

        Returns:
            `True` if this interval lies completely to the right
            of `other` and there is a non-empty gap between them,
            otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return False
        # From this point onwards, both intervals are considered
        # to be non-empty.
        
        if other.end is not None and self.start is not None:
            # 'other' is bounded on the right and 'self' is bounded
            # on the left.

            if other.end < self.start:
                return True
            if other.end == self.start:
                return other.is_end_included is False and self.is_start_included is False
            
        return False
    

    def overlaps(self, other: TimeInterval) -> bool:
        '''Return `True` if this interval overlaps with another one
        (has non-empty intersection).
        
        Two intervals overlap if their intersection is non-empty.
        If either interval is empty, they cannot overlap.

        Args:
            `other`: The `TimeInterval` to test for overlap.

        Returns:
            `True` if the intervals share at least one point, otherwise
            `False`.
        '''
        
        if self.is_empty or other.is_empty:
            return False
        # From this point onwards, both intervals are considered
        # to be non-empty.

        # Check whether 'self' is completely to the left of 'other'.
        if self.is_left_of(other):
            return False

        # Check whether 'other' is completely to the left of 'self'.
        if other.is_left_of(self):
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
            `other`: The `TimeInterval` to test for touching.

        Returns:
            `True` if the intervals are non-empty and their union
            is connected, otherwise `False`.
        '''

        if self.is_empty or other.is_empty:
            return False
        # From this point onwards, both intervals are considered
        # to be non-empty.

        # Check whether 'self' is completely to the left of 'other'
        # and their union is disconnected.
        if self.is_left_of_disconnectedly(other):
            return False

        # Check whether 'other' is completely to the left of 'self'
        # and their union is disconnected.
        if other.is_left_of_disconnectedly(self):
            return False

        return True
    

    @staticmethod
    def dist(first: TimeInterval, second: TimeInterval) -> datetime.timedelta | None:
        '''Calculate the shortest temporal distance between two
        intervals.

        The distance is defined as the length of the smallest gap
        between any point of the first interval and any point
        of the second. If the intervals overlap, the distance is zero.
        If the distance cannot be determined (e.g., because at least one
        interval is empty), the result is `None`.

        Args:
            `first`: The first time interval.
            `second`: The second time interval.

        Returns:
            A `datetime.timedelta` representing the gap between
            the intervals, or `None` if either interval is empty.

        Raises:
            `AssertionError`: If the intervals are non-empty
                and do not overlap, but one of them is not appropriately
                bounded (should not occur under normal conditions,
                indicating a bug in the implementation).
        '''

        if first.is_empty or second.is_empty:
            return None

        if first.is_left_of(second):
            if first.end is None or second.start is None:
                raise AssertionError(
                    'Since the intervals are non-empty and do not intersect, the left interval '
                    'must be bounded on the right and the right interval must be bounded '
                    'on the left.')
            return second.start - first.end
        elif first.is_right_of(second):
            if first.start is None or second.end is None:
                raise AssertionError(
                    'Since the intervals are non-empty and do not intersect, the left interval '
                    'must be bounded on the right and the right interval must be bounded '
                    'on the left.')
            return first.start - second.end
        else:
            # Intervals overlap.
            return datetime.timedelta()



@dataclass(frozen=True)
class TimeSet:
    '''A disjoint union of time intervals that are pairwise disconnected
    and chronologically ordered.
    
    Each component interval must be non-empty and placed
    in chronological order. Intervals must not overlap, and the union
    of any two distinct intervals must be disconnected. In other words,
    each component interval is a connected component of the time set.
    '''

    _intervals: tuple[TimeInterval, ...]


    def _is_valid(self) -> bool:
        '''Check whether the 'TimeSet' is set correctly.'''

        # 'TimeSet' must not contain any empty intervals.
        for i in self._intervals:
            if i.is_empty:
                return False

        # The intervals in 'TimeSet' must be chronologically ordered,
        # and all their pairwise unions must be disconnected.
        for l, r in zip(self._intervals, self._intervals[1:]):
            if not l.is_left_of_disconnectedly(r):
                return False
        
        return True
    

    def __init__(self, *intervals: TimeInterval):
        '''Initialize a `TimeSet` with the provided intervals.
        
        Args:
            `*intervals`: Time intervals that must satisfy
                the invariants (non-empty, chronologically ordered,
                pairwise disconnected).

        Raises:
            `ValueError`: If the intervals do not satisfy
                the invariants.
        '''

        object.__setattr__(self, '_intervals', tuple(intervals))

        if not self._is_valid():
            raise ValueError('The \'TimeSet\' has been set incorrectly.')
    

    def __str__(self) -> str:
        '''Return a string representation of the time set.

        For an empty set, return the empty set symbol '∅'. For
        a non-empty set, return the components joined by the union
        symbol '⊔'.
        '''

        if self.is_empty:
            # Return the empty set symbol.
            return '\u2205'
        else:
            return ' \u2294 '.join(map(str, self._intervals))
    

    def __bool__(self) -> bool:
        '''Return `True` if the time set is non-empty, `False`
        otherwise.'''

        return bool(self._intervals)
    

    def __contains__(self, other: object) -> bool:
        '''Return `True` if the time set contains the given object.

        The object may be a `Timestamp`, a `TimeInterval`, or another
        `TimeSet`.'''

        if isinstance(other, Timestamp | TimeInterval | TimeSet):
            return self.contains(other)
        else:
            return False
    

    def __or__(self, other: TimeInterval | TimeSet) -> TimeSet:
        '''Return the union of this time set with another time set
        or a time interval.'''

        if isinstance(other, TimeInterval):
            return TimeSet.union(*self._intervals, other)
        
        if isinstance(other, TimeSet):
            return TimeSet.union(*self._intervals, *other._intervals)
        
        return NotImplemented
    

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
    

    def contains_timestamp(self, moment: Timestamp) -> bool:
        '''Return `True` if the given moment is contained in the time
        set.'''

        return any(moment in c for c in self.components)
    

    def contains_timeinterval(self, interval: TimeInterval) -> bool:
        '''Return `True` if the given time interval is completely
        contained in the time set.'''

        return any(interval.is_contained_in(c) for c in self.components)
    

    def contains_timeset(self, timeset: TimeSet) -> bool:
        '''Return `True` if this time set contains the given time
        set.'''

        i, j = 0, 0

        while j < timeset.components_number:
            if i >= self.components_number:
                return False

            if self.components[i].contains(timeset.components[j]):
                j += 1
            elif self.components[i].is_left_of(timeset.components[j]):
                i += 1
            else:
                return False

        return True
    

    def contains(self, other: Timestamp | TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set contains the given timestamp,
        time interval, or another time set.'''

        if isinstance(other, Timestamp):
            return self.contains_timestamp(other)
        elif isinstance(other, TimeInterval):
            return self.contains_timeinterval(other)
        elif isinstance(other, TimeSet):
            return self.contains_timeset(other)
        else:
            return NotImplemented


    def is_contained_in(self, other: TimeSet) -> bool:
        '''Return `True` if this time set is contained in the given time
        set.'''

        return other.contains(self)
    

    def is_left_of(self, other: TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set lies strictly to the left
        of the given object with no intersection.

        The object may be a `TimeInterval` or a `TimeSet`. This is
        automatically true if any of the sets are empty.
        '''

        if self.is_empty or other.is_empty:
            return True
        # From this point onwards, both time sets are considered
        # to be non-empty.

        if self.end is not None and other.start is not None:
            # 'self' is bounded on the right and 'other' is bounded
            # on the left.

            if self.end < other.start:
                return True
            if self.end == other.start:
                return self.is_end_included is False or other.is_start_included is False
            
        return False
    

    def is_right_of(self, other: TimeInterval | TimeSet) -> bool:
        '''Return `True` if this time set lies strictly to the right
        of the given object with no intersection.

        The object may be a `TimeInterval` or a `TimeSet`. This is
        automatically true if any of the sets are empty.
        '''

        if self.is_empty or other.is_empty:
            return True
        # From this point onwards, both time sets are considered
        # to be non-empty.

        if other.end is not None and self.start is not None:
            # 'other' is bounded on the right and 'self' is bounded
            # on the left.

            if other.end < self.start:
                return True
            if other.end == self.start:
                return other.is_end_included is False or self.is_start_included is False
            
        return False
    

    def intersection_with_interval(self, other: TimeInterval) -> TimeSet:
        '''Return the intersection of this time set with the given time
        interval.'''

        # The intersection with the empty set is empty.
        if self.is_empty or other.is_empty:
            return TimeSet.empty()
        # From this point onwards, a time set and a time interval
        # are considered to be non-empty.

        intersection_intervals: list[TimeInterval] = []

        for i in self._intervals:
            if i.is_left_of(other):
                continue
            elif i.is_right_of(other):
                break
            else:
                # The intervals overlap.

                intersection_interval = i & other
                if intersection_interval.is_nonempty:
                    intersection_intervals.append(intersection_interval)

        return TimeSet(*intersection_intervals)

    
    def intersection_with_timeset(self, other: TimeSet) -> TimeSet:
        '''Return the intersection of this time set with another time
        set.'''

        # The intersection with the empty set is empty.
        if self.is_empty or other.is_empty:
            return TimeSet.empty()
        # From this point onwards, time sets are considered to be
        # non-empty.

        intersection_intervals: list[TimeInterval] = []
        i, j = 0, 0

        while i < self.components_number and j < other.components_number:
            self_interval = self._intervals[i]
            other_interval = other._intervals[j]

            if self_interval.is_left_of(other_interval):
                i += 1
            elif self_interval.is_right_of(other_interval):
                j += 1
            else:
                # The intervals overlap.

                intersection_interval = self_interval & other_interval
                if not intersection_interval.is_empty:
                    intersection_intervals.append(intersection_interval)

                # Increment the pointer of the interval that ends
                # earlier.
                if (
                    (self_interval.end is None, self_interval.end) <
                    (other_interval.end is None, other_interval.end)
                ):
                    i += 1
                else:
                    j += 1

        return TimeSet(*intersection_intervals)
    

    def overlaps_with_interval(self, interval: TimeInterval) -> bool:
        '''Return `True` if this time set overlaps with the given time
        interval.'''

        # The intersection with the empty set is empty.
        if self.is_empty or interval.is_empty:
            return False
        # From this point onwards, a time set and a time interval
        # are considered to be non-empty.

        for i in self.components:
            if i.is_left_of(interval):
                continue
            elif i.is_right_of(interval):
                break
            else:
                # The intervals overlap.
                return True

        return False
    

    def overlaps_with_timeset(self, timeset: TimeSet) -> bool:
        '''Return `True` if this time set overlaps with another time
        set.'''

        # The intersection with the empty set is empty.
        if self.is_empty or timeset.is_empty:
            return False
        # From this point onwards, time sets are considered to be
        # non-empty.

        i, j = 0, 0

        while i < self.components_number and j < timeset.components_number:
            self_interval = self.components[i]
            other_interval = timeset.components[j]

            if self_interval.is_left_of(other_interval):
                i += 1
            elif self_interval.is_right_of(other_interval):
                j += 1
            else:
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
    

    def complement(self) -> TimeSet:
        '''Create the complement of this time set (all points
        not in the set).'''

        # The complement of empty time set is the entire time line.
        if self.is_empty:
            return TimeSet.timeline()

        new_components: list[TimeInterval] = []

        new_components.append(self.first_component.to_the_left())

        for f, s in zip(self._intervals, self._intervals[1:]):
            new_components.append(TimeInterval.between(f, s))

        new_components.append(self.last_component.to_the_right())

        return TimeSet.union(*new_components)


    @classmethod
    def empty(cls) -> TimeSet:
        '''Return the empty time set.'''

        return cls()
    

    @classmethod
    def timeline(cls) -> TimeSet:
        '''Create a time set representing the entire timeline.'''

        return cls(TimeInterval.timeline())


    @classmethod
    def union(cls, *arg: TimeInterval | TimeSet) -> TimeSet:
        '''Create a `TimeSet` that is the union of the given time
        intervals and time sets.

        Empty components are automatically discarded, and touching
        intervals are merged.
        '''

        # Remove empty intervals.
        nonempty_intervals = [
            i
            for ts in arg
            for i in (ts.components if isinstance(ts, TimeSet) else [ts])
            if i.is_nonempty
        ]

        # If there are no non-empty intervals, then the union is empty.
        if not nonempty_intervals:
            return TimeSet.empty()

        # Sort intervals chronologically.
        def sort_key(i: TimeInterval):
            return (
                i.start is not None, i.start, not i.is_start_included,
                i.end is None, i.end, i.is_end_included
            )

        nonempty_intervals.sort(key=sort_key)

        # Group touching intervals.
        components: list[list[TimeInterval]] = []
        current_group = [nonempty_intervals[0]]

        for interval in nonempty_intervals[1:]:
            if current_group[-1].touches(interval):
                # If the new interval touches the last interval
                # in the group, add it to the group.

                current_group.append(interval)
            else:
                # If the new interval does not touch the last interval
                # in the group, we keep the previous group and create
                # a new one that includes the new interval.

                components.append(current_group)
                current_group = [interval]

        # Keep the last group.
        components.append(current_group)

        # Build minimal covers (connected components).
        merged_intervals = [
            TimeInterval.minimal_cover(*group)
            for group in components
        ]

        # Construct 'TimeSet'.
        return cls(*merged_intervals)
    

    @property
    def is_nonempty(self) -> bool:
        '''Return `True` if the time set is non-empty.'''

        return bool(self._intervals)


    @property
    def is_empty(self) -> bool:
        '''Return `True` if the time set is empty.'''

        return not self._intervals
    

    @property
    def is_bounded(self) -> bool:
        '''Return `True` if the time set is bounded.
        
        Here, boundedness is understood in a mathematical sense.
        Therefore the empty time set is considered to be bounded.
        '''

        if self.is_empty:
            return True
        # From this point onwards, the set is considered
        # to be non-empty.

        # Check the first and last intervals for boundedness.
        return self._intervals[0].is_bounded and self._intervals[-1].is_bounded


    @property
    def is_connected(self) -> bool:
        '''Return `True` if the time set is connected.
        
        A time set is connected if it has no more than one connected 
        component.
        '''

        return len(self._intervals) <= 1
    

    @property
    def is_point(self) -> bool:
        '''Return `True` if the time set consists of a single point.'''

        return len(self._intervals) == 1 and self._intervals[0].is_point
    

    @property
    def is_open(self) -> bool:
        '''Return `True` if the time set is an open set
        (in the topological sense).'''

        if self.is_empty:
            return True
        # From this point onwards, the set is considered
        # to be non-empty.

        return all(i.is_open for i in self._intervals)
    

    @property
    def is_closed(self) -> bool:
        '''Return `True` if the time set is a closed set
        (in the topological sense).'''

        if self.is_empty:
            return True
        # From this point onwards, the set is considered to be
        # non-empty.

        return all(i.is_closed for i in self._intervals)


    @property
    def start(self) -> Timestamp | None:
        '''Return the start of the time set, or `None` if unbounded
        on the left or empty.'''

        if self.is_empty:
            return None
        
        return self.first_component.start
    

    @property
    def end(self) -> Timestamp | None:
        '''Return the end of the time set, or `None` if unbounded
        on the right or empty.'''

        if self.is_empty:
            return None
        
        return self.last_component.end
    

    @property
    def is_start_specified(self) -> bool:
        '''Return `True` if the start of the time set is specified
        (not at infinity).'''

        if self.is_empty:
            return False
        
        return self.first_component.is_start_specified
    

    @property
    def is_end_specified(self) -> bool:
        '''Return `True` if the end of the time set is specified
        (not at infinity).'''

        if self.is_empty:
            return False
        
        return self.last_component.is_end_specified
    

    @property
    def is_start_included(self) -> bool | None:
        '''Return `True` if the start is included, `False` if excluded,
        `None` if unspecified.'''

        if self.is_start_specified:
            return self.first_component.is_start_included
        else:
            return None
    

    @property
    def is_end_included(self) -> bool | None:
        '''Return `True` if the end is included, `False` if excluded,
        `None` if unspecified.'''

        if self.is_end_specified:
            return self.last_component.is_end_included
        else:
            return None
    

    @property
    def inf(self) -> Timestamp | None:
        '''Return the infimum (greatest lower bound) of the time set,
        or `None` if unbounded on the left or empty.'''

        if self.is_empty:
            return None
        
        return self.first_component.start
    

    @property
    def sup(self) -> Timestamp | None:
        '''Return the supremum (least upper bound) of the time set,
        or `None` if unbounded on the right or empty.'''
        
        if self.is_empty:
            return None
        
        return self.last_component.end
    

    @property
    def components_number(self) -> int:
        '''Return the number of connected components.'''

        return len(self._intervals)
    

    @property
    def components(self) -> tuple[TimeInterval, ...]:
        '''Return a tuple of the connected components.'''
        
        return self._intervals


    def component(self, component_number: int) -> TimeInterval:
        '''Return the component at the given index.

        Args:
            `component_number`: Index of the desired component
                (0-based).

        Raises:
            `IndexError`: If the index is out of range.
        '''

        try:
            return self._intervals[component_number]
        except IndexError as e:
            raise IndexError('Incorrect connected component number.') from e
    

    @property
    def first_component(self) -> TimeInterval:
        '''Return the first (leftmost) connected component.

        Raises:
            `IndexError`: If the time set is empty.
        '''

        try:
            return self._intervals[0]
        except IndexError as e:
            raise IndexError('Time set has no connected components.') from e
    

    @property
    def last_component(self) -> TimeInterval:
        '''Return the last (rightmost) connected component.

        Raises:
            `IndexError`: If the time set is empty.
        '''

        try:
            return self._intervals[-1]
        except IndexError as e:
            raise IndexError('Time set has no connected components.') from e
        

    def duration(self) -> datetime.timedelta | None:
        '''Return the total duration of the time set, or `None`
        if the time set is unbounded.

        For an empty time set, return zero.
        '''

        if not self.is_bounded:
            return None

        total = datetime.timedelta()

        for c in self.components:
            d = c.duration
            assert d is not None
            total += d

        return total
    

    def span_duration(self) -> datetime.timedelta | None:
        '''Return the duration of the minimal interval covering
        the whole time set.

        This is the time span from the earliest start to the latest end.
        Return zero for an empty time set, `None` if the time set
        is unbounded.
        '''

        if self.is_empty:
            return datetime.timedelta()
        
        if self.start is None or self.end is None:
            return None
        
        return self.end - self.start
    

    def _component_duration_extreme(self, func):
        return func(
            (c.duration for c in self.components),
            key=lambda d: (d is None, d),
            default=None
        )
    

    @property
    def min_component_duration(self) -> datetime.timedelta | None:
        '''Return the minimal duration among the components.

        Compute the minimal duration of all components in the time set.
        Unbounded components have duration `None` and are ignored when
        a finite duration exists.

        Return `None` if the time set has no components or if all
        components are unbounded.
        '''

        return self._component_duration_extreme(min)
    

    @property
    def max_component_duration(self) -> datetime.timedelta | None:
        '''Return the maximal duration among the components.

        Compute the maximal duration of all components in the time set.
        Unbounded components have duration `None` and dominate any
        finite duration.

        Return `None` if the time set has no components or if at least
        one component is unbounded.
        '''

        return self._component_duration_extreme(max)
    

    def _gaps(self) -> Iterator[datetime.timedelta]:
        '''Generate durations of gaps between consecutive components.'''

        for f, s in zip(self.components, self.components[1:]):
            start, end = f.end, s.start
            
            if start is None or end is None:
                raise AssertionError(
                    '\'TimeSet\' state is incorrect: any non-last component should be bounded '
                    'on the right and any non-first component on the left.'
                )
            
            yield end - start
    

    @property
    def max_gap_duration(self) -> datetime.timedelta:
        '''Return the maximum gap duration between components.
    
        If there are no gaps (less than two components), return zero
        duration.
        '''

        return max(self._gaps(), default=datetime.timedelta())
    

    @property
    def min_gap_duration(self) -> datetime.timedelta:
        '''Return the minimum gap duration between components.

        If there are no gaps (less than two components), return zero
        duration.
        '''

        return min(self._gaps(), default=datetime.timedelta())
    

    def closure(self) -> TimeSet:
        '''Create the topological closure of this time set.'''

        return TimeSet.union(*map(TimeInterval.closure, self.components))
    

    def interior(self) -> TimeSet:
        '''Create the topological interior of this time set.'''

        return TimeSet.union(*map(TimeInterval.interior, self.components))
    

    @staticmethod
    def dist(
        first: TimeInterval | TimeSet, 
        second: TimeInterval | TimeSet
    ) -> datetime.timedelta | None:
        '''Calculate the distance between two time sets or time
        intervals.
        
        If the sets overlap, return zero.
        If the distance is undefined (e.g., one of them is empty),
        return `None`.
        '''

        if first.is_empty or second.is_empty:
            return None
        
        if isinstance(first, TimeInterval):
            first = TimeSet(first)

        if isinstance(second, TimeInterval):
            second = TimeSet(second)

        if first.is_left_of(second):
            if first.end is None or second.start is None:
                raise AssertionError(
                    'Since the time sets are non-empty, the left time set must be bounded '
                    'on the right and the right time set must be bounded on the left.'
                )
            return second.start - first.end
        elif first.is_right_of(second):
            if first.start is None or second.end is None:
                raise AssertionError(
                    'Since the time sets are non-empty, the left time set must be bounded '
                    'on the right and the right time set must be bounded on the left.'
                )
            return first.start - second.end
        else:
            # Find the minimum distance between the components.
            i, j = 0, 0
            first_is_left_of_second = None
            dist = None

            def dist_key(dist: datetime.timedelta | None):
                return (dist is None, dist)

            while i < first.components_number and j < second.components_number:
                if first.components[i].is_left_of(second.components[j]):
                    
                    if first_is_left_of_second is False:
                        components_dist = TimeInterval.dist(
                            first.components[i],
                            second.components[j - 1]
                        )
                        dist = min(dist, components_dist, key=dist_key)

                    first_is_left_of_second = True
                    i += 1
                elif first.components[i].is_right_of(second.components[j]):

                    if first_is_left_of_second is True:
                        components_dist = TimeInterval.dist(
                            first.components[i - 1],
                            second.components[j]
                        )
                        dist = min(dist, components_dist, key=dist_key)
                    
                    first_is_left_of_second = False
                    j += 1
                else:
                    # Components overlap.
                    return datetime.timedelta()
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
                dist = min(dist, components_dist, key=dist_key)

            return dist