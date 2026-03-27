from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Iterable
import itertools
import warnings

from diane.temporal import TimeInterval, TimeSet
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
            `timeset`: `TimeSet` representing the session's time.
            `activities`: Iterable of `Activity` objects. Must
                not be empty.
            `comment`: Optional comment string. Defaults to empty
                string.

        Raises:
            `ValueError`: If timeset is empty or activities iterable
                is empty.
        '''

        object.__setattr__(self, '_timeset', timeset)
        object.__setattr__(self, '_activities', frozenset(activities))
        object.__setattr__(self, 'comment', comment)

        self._validate()
        
        object.__setattr__(self, '_hash', hash((timeset, self._activities)))


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
        of the session.'''

        main_str = f'{self.timeset.start.timestamp} \u2192 {self.timeset.end.timestamp} (activity duration: {self.timeset.duration.value})'
        activities_str = '    Activities:\n' + '\n'.join(f'    \u2022 {a.title}' for a in self._activities)
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