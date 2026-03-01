from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Iterable
import uuid
from temporal import TimeSet
from activities import Activity



@dataclass(frozen=True, init=False)
class Session:
    '''Represents session.
    
    Attributes:
        _session_id: The unique 'UUID' identifier for a session.
        _timeset: Time of session.
        _activities: Set of activities.
        comment: The session comment string. This may be empty.'''

    _session_id: uuid.UUID = field(default_factory=uuid.uuid4, init=False)
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
        object.__setattr__(self, '_session_id', uuid.uuid4())
        object.__setattr__(self, '_timeset', timeset)
        object.__setattr__(self, '_activities', frozenset(activities))
        object.__setattr__(self, 'comment', comment)

        self._validate()


    def __eq__(self, other: object) -> bool:

        if not isinstance(other, Session):
            return NotImplemented
        
        return self._session_id == other._session_id


    def __hash__(self) -> int:
        return hash(self._session_id)
    

    def __str__(self) -> str:
        return str(self._session_id)


    @property
    def session_id(self) -> uuid.UUID:
        '''Returns the session's ID.'''

        return self._session_id


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
        '''Merges sessions with the same set of activities.

        If sessions have same activities, a new session will be created
        that unites the time sets and comments of the original ones.
        Ignores duplicates by ID, leaving only the first occurrence
        of each session.

        Raises:
            ValueError: if sessions have different sets
            of activities or if no sessions are given.'''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        # Remove duplicates by ID, leaving only the first occurrence
        # of each session.
        unique_sessions = list(dict.fromkeys(sessions))
        
        first_activities = unique_sessions[0].activities
        if any(s.activities != first_activities for s in unique_sessions[1:]):
                raise ValueError(
                    'Sessions are not mergeable as they have different activities.'
                )

        # Unite time sets.
        timesets = [s.timeset for s in unique_sessions]
        timeset = TimeSet.union(*timesets)

        # As activities are same, we can take them from one session.
        activities = unique_sessions[0].activities

        # Concatenate of comments from given sessions via line breaks.
        comment = '\n'.join(s.comment for s in unique_sessions if s.comment)

        return Session(timeset, activities, comment)