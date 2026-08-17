from __future__ import annotations

import portion

from diane.chrono.timestamp import Timestamp, TimezoneConversionError


class TimeIntervalSetError(Exception):
    """A general time interval set error."""
    ...


class NormalisationError(TimeIntervalSetError):
    """A time interval set could not be normalised."""
    ...


class UndefinedEndpointError(TimeIntervalSetError):
    """An endpoint of a time interval set is undefined."""
    ...


class TimeIntervalSet:
    """Represents a finite bounded disjoint union of time intervals.

    - Finiteness means that a time interval set has a finite number
      of connected components in the topological sense.
    - The term 'boundedness' is also used in the mathematical sense.
    - All endpoints are in the same time zone (normalised).

    Attributes:
        _interval_set (portion.Interval[Timestamp]): A  `portion`
            `Interval`. All endpoints are `Timestamp` instances
            in the same time zone.
    """

    _interval_set: portion.Interval[Timestamp]

    def __init__(
        self,
        interval_set: portion.Interval[Timestamp]
    ) -> None:
        """Create a time interval set.

        All endpoints are converted to the time zone of the earliest
        endpoint (normalised).

        Args:
            interval_set (portion.Interval[Timestamp]): A `portion`
                `Interval` with `Timestamp` endpoints.

        Raises:
            NormalisationError: If failed to normalise a time interval
                set.
        """
        if not interval_set.empty:
            tz = interval_set.lower.iana
            norm_components: list[portion.Interval[Timestamp]] = []
            for c in interval_set:
                try:
                    norm_c = c.replace(
                        lower=c.lower.to_timezone(tz),
                        upper=c.upper.to_timezone(tz)
                    )
                except TimezoneConversionError as exc:
                    raise NormalisationError(
                        'Failed to normalise the time interval set.'
                    ) from exc
                norm_components.append(norm_c)
            interval_set = portion.Interval(*norm_components)

        self._interval_set = interval_set

    @classmethod
    def empty(cls) -> TimeIntervalSet:
        """Create an empty time interval set.

        Returns:
            TimeIntervalSet: An empty time interval set.
        """
        return cls(portion.empty())

    @classmethod
    def point(cls, timestamp: Timestamp) -> TimeIntervalSet:
        """Create a time interval set containing a single point.

        It corresponds to an instantaneous event.

        Args:
            timestamp (Timestamp): A timestamp.

        Returns:
            TimeIntervalSet: A time interval set containing a single
                point.
        """
        return cls(portion.singleton(timestamp))

    @classmethod
    def open(cls, start: Timestamp, end: Timestamp) -> TimeIntervalSet:
        """Create an open bounded time interval.

        If `start >= end`, an empty interval will be created.

        Args:
            start (Timestamp): The left endpoint of an interval.
            end (Timestamp): The right endpoint of an interval.

        Returns:
            TimeIntervalSet: An open time interval.
        """
        return cls(portion.open(start, end))

    @classmethod
    def closed(cls, start: Timestamp, end: Timestamp) -> TimeIntervalSet:
        """Create a closed bounded time interval.

        If `start > end`, an empty interval will be created.

        Args:
            start (Timestamp): The left endpoint of an interval.
            end (Timestamp): The right endpoint of an interval.

        Returns:
            TimeIntervalSet: A closed time interval.
        """
        return cls(portion.closed(start, end))

    @classmethod
    def closedopen(cls, start: Timestamp, end: Timestamp) -> TimeIntervalSet:
        """Create a half-open (closed-open) bounded time interval.

        If `start >= end`, an empty interval will be created.

        Args:
            start (Timestamp): The left endpoint of an interval.
            end (Timestamp): The right endpoint of an interval.

        Returns:
            TimeIntervalSet: A closed-open time interval.
        """
        return cls(portion.closedopen(start, end))

    @classmethod
    def openclosed(cls, start: Timestamp, end: Timestamp) -> TimeIntervalSet:
        """Create a half-open (open-closed) bounded time interval.

        If `start >= end`, an empty interval will be created.

        Args:
            start (Timestamp): The left endpoint of an interval.
            end (Timestamp): The right endpoint of an interval.

        Returns:
            TimeIntervalSet: An open-closed time interval.
        """
        return cls(portion.openclosed(start, end))

    def __and__(self, other: object) -> TimeIntervalSet:
        """Return the intersection of this time interval set and
        another temporal object.

        Args:
            other (object): A temporal object (e.g. `TimeIntervalSet`)
                to intersect with.

        Returns:
            TimeIntervalSet: The intersection.

        Raises:
            NormalisationError: If failed to normalise a time interval
                set.
        """
        if isinstance(other, TimeIntervalSet):
            return TimeIntervalSet(self._interval_set & other._interval_set)

        return NotImplemented

    def __or__(self, other: object) -> TimeIntervalSet:
        """Return the union of this time interval set and another
        temporal object.

        Args:
            other (object): A temporal object (e.g. `TimeIntervalSet`)
                to unite with.

        Returns:
            TimeIntervalSet: The union.

        Raises:
            NormalisationError: If failed to normalise a time interval
                set.
        """
        if isinstance(other, TimeIntervalSet):
            return TimeIntervalSet(self._interval_set | other._interval_set)

        return NotImplemented

    def __sub__(self, other: object) -> TimeIntervalSet:
        """Return the difference between this time interval set and
        another temporal object.

        Args:
            other (object): A temporal object (e.g. `TimeIntervalSet`)
                to be subtracted.

        Returns:
            TimeIntervalSet: The difference.

        Raises:
            NormalisationError: If failed to normalise a time interval
                set.
        """
        if isinstance(other, TimeIntervalSet):
            return TimeIntervalSet(self._interval_set - other._interval_set)

        return NotImplemented

    @property
    def is_empty(self) -> bool:
        """Check whether the time interval set is empty.

        Returns:
            bool: `True` if the time interval set is empty.
        """
        return self._interval_set.empty

    @property
    def start(self) -> Timestamp:
        """Return the start of the time interval set.

        Returns:
            Timestamp: The start of the time interval set.

        Raises:
            UndefinedEndpointError: If the time interval set is empty.
        """
        if self.is_empty:
            raise UndefinedEndpointError(
                'An empty time interval set has no defined left endpoint.'
            )
        return self._interval_set.lower

    @property
    def end(self) -> Timestamp:
        """Return the end of the time interval set.

        Returns:
            Timestamp: The end of the time interval set.

        Raises:
            UndefinedEndpointError: If the time interval set is empty.
        """
        if self.is_empty:
            raise UndefinedEndpointError(
                'An empty time interval set has no defined right endpoint.'
            )
        return self._interval_set.upper
