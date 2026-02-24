from __future__ import annotations
from dataclasses import dataclass, field
import uuid
from temporal import Timestamp, TimeInterval, TimeSet
from activities import Activity


@dataclass
class Session:
    '''Represents session.
    
    Attributes:
        _session_id: The unique integer identifier for a session. Cannot
            be changed.
        _timeset: Time of session.
        _activities: Set of activities.
        comment: The session comment string. Can be changed. This may
            be empty. It should start with a capital letter and finish
            with a dot.'''

    _timeset: TimeSet
    _activities: set[Activity]
    comment: str = ''
    _session_id: uuid.UUID = field(default_factory=uuid.uuid4)


    def _validate(self) -> None:
        if self._timeset.is_empty:
            raise ValueError('The session must be associated with a non-empty time set.')
        

    def __post_init__(self) -> None:
        self._activities = self._activities.copy()
        self._validate()


    def __eq__(self, other: object) -> bool:

        if not isinstance(other, Session):
            return NotImplemented
        
        return self._session_id == other._session_id


    def __hash__(self) -> int:
        return hash(self._session_id)
    

    def __str__(self) -> str:
        return str(self._session_id)
    

    def __setattr__(self, name, value):
        if name == '_session_id' and hasattr(self, '_session_id'):
            raise AttributeError('Session ID is immutable.')
        super().__setattr__(name, value)


    @property
    def session_id(self) -> uuid.UUID:
        '''Returns the session's ID.'''

        return self._session_id


    @property
    def timeset(self):
        '''Returns the session's 'TimeSet'.'''

        return self._timeset
    

    @timeset.setter
    def timeset(self, timeset: TimeSet):
        '''Sets the session's 'TimeSet'.

        An empty 'TimeSet' is not permitted.
        
        Raises:
            ValueError: if 'TimeSet' is empty.'''

        if timeset.is_empty:
            raise ValueError('The activity must be associated with a non-empty time set.')

        self._timeset = timeset


    @property
    def activities(self):
        '''Returns activities set.'''

        return frozenset(self._activities)
    

    def add_activity(self, activity: Activity):
        '''Adds activity to the session.'''

        self._activities.add(activity)


    def remove_activity(self, activity: Activity):
        '''Removes activity from the session.'''

        self._activities.remove(activity)


    @classmethod
    def merge(cls, *sessions: Session) -> Session:
        '''Combines sessions with the same set of activities.

        Raises:
            ValueError: if sessions have different sets
            of activities.'''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        for f, s in zip(sessions, sessions[1:]):
            if f.activities != s.activities:
                raise ValueError(
                    f'Sessions {f} and {s} are not mergeable as they have different activity sets.'
                )

        timesets = [s.timeset for s in sessions]
        timeset = TimeSet.union(*timesets)

        activities = set(sessions[0].activities)

        for f, s in zip(sessions, sessions[1:]):
            if f.comment != s.comment:
                comment = ''
                break
        else:
            comment = sessions[0].comment

        return Session(timeset, activities, comment)

