from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Iterable

from diane.temporal import TimeSet
from diane.activities import Activity



@dataclass(frozen=True, init=False, slots=True)
class Session:
    '''Represents a session --- a time interval(s) during which
    activities occur.

    A session is defined by a non-empty time set, a non-empty set
    of activities, and an optional message. Instances are immutable
    and hashable based on the time set and activities (the message
    is not part of the equality/hash).

    Attributes:
        `timeset` (`TimeSet`): The non-empty time set representing
            the session's time. The time zones are normalized.
        `activities` (`frozenset[Activity]`): The activities that have
            been tracked during the session.
        `message` (`str`): Free-form brief text providing further
            details about user activity (may be empty).
    '''

    _timeset: TimeSet
    _activities: frozenset[Activity]
    message: str

    _hash: int


    def _validate(self) -> None:
        '''Validate the session's internal state.

        The session must have a non-empty time set and contain at least
        one activity.

        Raises:
            `ValueError`: If the time set is empty or the activities set
                is empty.
        '''

        if self._timeset.is_empty:
            raise ValueError('The session must be associated with a non-empty time set.')
        
        if not self._activities:
            raise ValueError('The session must contain at least one activity.')
    

    def __init__(
        self,
        timeset: TimeSet,
        activities: Iterable[Activity],
        message: str = ''
    ) -> None:
        '''Initialize a `Session`.

        Args:
            `timeset` (`TimeSet`): The time set representing
                the session's time. Must be non-empty.
            `activities`: Iterable of `Activity` objects. Must
                be non-empty.
            `message`: Optional message string. Defaults to empty.

        Raises:
            `ValueError`: If timeset is empty or activities iterable
                is empty.
        '''

        object.__setattr__(self, '_timeset', timeset.normalize_time_zones())
        object.__setattr__(self, '_activities', frozenset(activities))
        object.__setattr__(self, 'message', message)

        self._validate()
        
        object.__setattr__(self, '_hash', hash((self._timeset, self._activities)))


    def __eq__(self, other: object) -> bool:
        '''Return `True` if this session equals another based on time
        sets and activities.
        
        Args:
            `other` (`object`): The object to compare with.

        Returns:
            `bool`: `True` if `other` is a `Session` with the same
            time set and activities; `False` otherwise.
        '''

        if not isinstance(other, Session):
            return NotImplemented
        
        return (
            self._timeset == other._timeset
            and self._activities == other._activities
        )


    def __hash__(self) -> int:
        '''Return a hash based on the time set and activities.
        
        Returns:
            `int`: The hash value of this session.
        '''

        return self._hash
    

    def __str__(self) -> str:
        '''Return the human-readable string representation of this
        session.
        
        Only the most important information is included
        for quick understanding:
        - the start time,
        - end time,
        - strict duration (without pauses),
        - list of activities.
        The message is not included. String is formatted in multiple
        lines for better readability.
        
        Returns:
            `str`: The string representation of this session. Includes
            the start time, end time, duration, and list of activities.
        '''

        indent = '    '
        arrow = '\u2192'   # Arrow '→'.
        bullet = '\u2022'  # Bullet '•'.

        main_str = (
            f'{self.timeset.start.timestamp} {arrow} {self.timeset.end.timestamp} '
            f'(activity duration: {self.timeset.duration.value})'
        )
        activities_titles = '\n'.join(f'{indent}{bullet} {a.title}' for a in self._activities)
        activities_str = f'{indent}Activities:\n{activities_titles}'
        return f'{main_str}\n{activities_str}'


    @property
    def timeset(self) -> TimeSet:
        '''Return this session's time set.

        Returns:
            `TimeSet`: The time set associated with this session.
            The time zones are normalized.
        '''

        return self._timeset


    @property
    def activities(self) -> frozenset[Activity]:
        '''Return the set of activities performed during the session.

        Returns:
            `frozenset[Activity]`: The immutable set of activities
            associated with this session.
        '''

        return self._activities
    

    def split_into_days(self) -> list[Session]:
        '''Split this session into separate sessions each one taking
        place in a single calendar day.

        - The time set is divided into daily closed-open intervals.
        - Each resulting session inherits the same activities
        as the original session.
        - The message is **only attached to the first daily session**.
        This design avoids duplication when the sessions are later read
        and merged back (the merge operation concatenates messages).

        Returns:
            `list[Session]`: The list of sessions, each contained
            in a single calendar day, ordered chronologically. The first
            session retains the original message; all others have
            the empty message.

        Raises:
            `ValueError`: If the session is time-unbounded because
            splitting into days would produce an infinite list.
        '''

        if self.timeset.is_unbounded:
            raise ValueError('\'split_into_days\' is only supported for time-bounded sessions.')

        timesets_by_day = self.timeset.split_into_days()
        if not timesets_by_day:
            return []
        
        session_by_day = [Session(timesets_by_day[0], self.activities, self.message)]
        for ts in timesets_by_day[1:]:
            session_by_day.append(Session(ts, self.activities))

        return session_by_day
    

    def to_dict(self) -> dict:
        '''Convert this session to the dictionary.

        Works only for sessions with normalized time zones, bounded
        in time, and **spanning no more than one day**.

        The resulting dictionary contains the following keys:
        - `time_zone`: The IANA time zone name of the session's time.
        - `intervals`: The list of dictionaries, each with `start` and
          `end` keys representing the ISO 8601 strings of the start
          and end times of the session's time intervals. If an interval
          is a point in time, the `end` value is the same as the `start`
          value.
        - `activities`: The list of activity slugs associated with this
          session.
        - `message`: The optional message associated with the session.

        Raises:
            `ValueError`: If the session is unnormalised, unbounded
            in time, or spans more than one day.
        '''

        if not self.timeset.is_normalized:
            raise ValueError(
                'A dictionary can only be created for a session with a normalized time set.'
            )
        if self.timeset.is_unbounded:
            raise ValueError('A dictionary can only be created for a time-bounded session.')
        if len(self.timeset.days) > 1:
            raise ValueError(
                'A dictionary can only be created for a session that spans no more than one day.'
            )

        time_zone_iana = self.timeset.start.timestamp.timezone_iana
        intervals_data = []
        for i in self.timeset.components:
            start_iso = i.start.timestamp.time_iso(allow_24_midnight=False)
            end_iso = i.end.timestamp.time_iso(allow_24_midnight=not i.is_point)
            intervals_data.append({'start': start_iso, 'end': end_iso})
        session_data = {
            'time_zone': time_zone_iana,
            'intervals': intervals_data,
            'activities': sorted([a.slug for a in self.activities]),
        }
        if self.message:
            session_data['message'] = self.message

        return session_data


    @classmethod
    def merge(cls, *sessions: Session) -> Session:
        '''Merge multiple sessions with the **same set of activities**.

        Create a new session that combines the time sets and messages
        of all provided sessions.
        
        - The resulting time set is the union of all individual time
          sets. 
        - The activities of the resulting session are the same
          as the activities of the input sessions (which must
          be identical).
        - Messages are concatenated in chronological order according
          to their input sessions, with a newline character separating
          each message. Empty messages are ignored.

        Args:
            `*sessions` (`Session`): The sessions to merge. Must have
                the same set of activities.

        Returns:
            `Session`: A new session with the united time set,
            the common activities, and the concatenated messages.

        Raises:
            `ValueError`: If no sessions are provided,
                or if the sessions have different sets of activities.
        '''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        # Sort sessions by start time.
        sorted_sessions = sorted(sessions, key=lambda s: s.timeset.start)
        
        first_activities = sorted_sessions[0].activities
        if any(s.activities != first_activities for s in sorted_sessions[1:]):
                raise ValueError(
                    'Sessions are not mergeable as they have different activities.'
                )

        # Unite time sets.
        timeset = TimeSet.union(*(s.timeset for s in sorted_sessions))

        # As activities are same, take them from the first session.
        activities = sorted_sessions[0].activities

        # Concatenate the messages from the given sessions
        # in chronological order via line breaks.
        message = ' '.join(s.message for s in sorted_sessions if s.message)

        return Session(timeset, activities, message)