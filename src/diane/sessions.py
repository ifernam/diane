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
    of activities, and an optional comment. Instances are immutable
    and hashable based on the time set and activities (the comment
    is not part of the equality/hash).

    Attributes:
        `_timeset`: `TimeSet` of the session.
        `_activities`: `frozenset` of `Activity` objects.
        `comment`: Free-form text comment (may be empty).
    '''

    _timeset: TimeSet
    _activities: frozenset[Activity]
    comment: str
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
        comment: str = ''
    ) -> None:
        '''Initialize a `Session`.

        Args:
            `timeset` (`TimeSet`): The time set representing
                the session's time. The time zones must be normalized.
            `activities`: Iterable of `Activity` objects. Must
                not be empty.
            `comment`: Optional comment string. Defaults to empty
                string.

        Raises:
            `ValueError`: If timeset is empty or activities iterable
                is empty.
        '''

        object.__setattr__(self, '_timeset', timeset.normalize_time_zones())
        object.__setattr__(self, '_activities', frozenset(activities))
        object.__setattr__(self, 'comment', comment)

        self._validate()
        
        object.__setattr__(self, '_hash', hash((self._timeset, self._activities)))


    def __eq__(self, other: object) -> bool:
        '''Return `True` if this session equals another based on time
        set and activities.'''

        if not isinstance(other, Session):
            return NotImplemented
        
        return (
            self._timeset == other._timeset
            and self._activities == other._activities
        )


    def __hash__(self) -> int:
        '''Return a hash based on the time set and activities.'''

        return self._hash
    

    def __str__(self) -> str:
        '''Return the human-readable string representation
        of this session.'''

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
        '''Return the session's time set.

        Returns:
            `TimeSet`: The time interval(s) during which the session
                takes place.
        '''

        return self._timeset


    @property
    def activities(self) -> frozenset[Activity]:
        '''Return the set of activities performed during the session.

        Returns:
            `frozenset[Activity]`: An immutable set of `Activity`
                instances.
        '''

        return self._activities
    

    def split_into_days(self) -> list[Session]:
        '''Split this session into separate sessions per calendar day.

        - The time set is divided into daily closed-open intervals.
        - Each resulting session inherits the same activities
        as the original session.
        - The comment is **only attached to the first daily session**.
        This design avoids duplication when the sessions are later read
        and merged back (the merge operation concatenates comments).

        Returns:
            `list[Session]`: The list of sessions, each contained
            in a single calendar day, ordered chronologically. The first
            session retains the original comment; all others have
            an empty comment.

        Raises:
            `ValueError`: If the session is time-unbounded because
            splitting into days would produce an infinite list.
        '''

        if self.timeset.is_unbounded:
            raise ValueError('\'split_into_days\' is only supported for time-bounded sessions.')

        timesets_by_day = self.timeset.split_into_days()
        if not timesets_by_day:
            return []
        
        session_by_day = [Session(timesets_by_day[0], self.activities, self.comment)]
        for ts in timesets_by_day[1:]:
            session_by_day.append(Session(ts, self.activities))

        return session_by_day
    

    def to_dict(self) -> dict:
        '''Convert this session to the dictionary.
        
        Raises:
            `ValueError`: If the session is unbounded by time.
        '''

        if self.timeset.is_unbounded:
            raise ValueError('A dictionary can only be created for a time-bounded session.')

        timeset = self.timeset.normalize_time_zones()
        time_zone_iana = timeset.start.timestamp.timezone_iana
        intervals_data = []
        for i in timeset.components:
            start_iso = i.start.timestamp.datetime_iso
            end_iso = i.end.timestamp.datetime_iso
            intervals_data.append({'start': start_iso, 'end': end_iso})
        session_data = {
            'time_zone': time_zone_iana,
            'intervals': intervals_data,
            'activities': [a.slug for a in self.activities],
        }
        if self.comment:
            session_data['comment'] = self.comment
        return session_data


    @classmethod
    def merge(cls, *sessions: Session) -> Session:
        '''Merge multiple sessions with identical activities.

        Create a new session that combines the time sets and comments
        of all provided sessions. The resulting time set is the union
        of all individual time sets. Comments are concatenated
        in the order of the input sessions, separated by a newline
        character. Empty comments are ignored.

        Args:
            `*sessions`: Variable number of `Session` objects to merge.

        Returns:
            `Session`: A new `Session` instance with the united time
            set, the common activities, and the concatenated comments.

        Raises:
            `ValueError`: If no sessions are provided,
                or if the sessions have different sets of activities.
        '''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        first_activities = sessions[0].activities
        if any(s.activities != first_activities for s in sessions[1:]):
                raise ValueError(
                    'Sessions are not mergeable as they have different activities.'
                )

        # Unite time sets.
        timeset = TimeSet.union(*(s.timeset for s in sessions))

        # As activities are same, take them from the first session.
        activities = sessions[0].activities

        # Concatenate the comments from the given sessions via line
        # breaks.
        comment = '\n'.join(s.comment for s in sessions if s.comment)

        return Session(timeset, activities, comment)