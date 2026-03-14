from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Iterable

from diane.temporal import TimeSet
from diane.activities import Activity



@dataclass(frozen=True, init=False)
class Session:
    '''Represents session.
    
    Attributes:
        _timeset: Time of session.
        _activities: Set of activities.
        comment: The session comment string. This may be empty.
        '''

    _timeset: TimeSet
    _activities: frozenset[Activity]
    comment: str = ''


    def _validate(self) -> None:

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
        object.__setattr__(self, '_timeset', timeset)
        object.__setattr__(self, '_activities', frozenset(activities))
        object.__setattr__(self, 'comment', comment)

        self._validate()


    def __eq__(self, other: object) -> bool:

        if not isinstance(other, Session):
            return NotImplemented
        
        return (
            self._timeset == other._timeset
            and self._activities == other._activities
        )


    def __hash__(self) -> int:
        return hash((self._timeset, self._activities))
    

    def __str__(self) -> str:
        activities_string = ', '.join(f'\'{a.slug}\'' for a in self._activities)
        return f'{self._timeset} -> {activities_string}'


    @property
    def timeset(self) -> TimeSet:
        '''Returns the session's 'TimeSet'.'''

        return self._timeset


    @property
    def activities(self) -> frozenset[Activity]:
        '''Returns activities set.'''

        return self._activities


    @classmethod
    def merge(cls, *sessions: Session) -> Session:
        '''Merge sessions with the same activities.

        If sessions have the same activities, create a new session that
        unites the time sets and comments of the original ones.

        Raises:
            `ValueError`: If no sessions are given or if sessions have
                different sets of activities.
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