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

    _session_id: uuid.UUID = field(default_factory=uuid.uuid4, init=False)
    _timeset: TimeSet
    _activities: set[Activity]
    comment: str = ''


    def _validate(self) -> None:

        if self._timeset.is_empty:
            raise ValueError('The session must be associated with a non-empty time set.')
        
        if not self._activities:
            raise ValueError('The session must contain at least one activity.')
        

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
    

    def __setattr__(self, name, value) -> None:
        if name == '_session_id' and hasattr(self, '_session_id'):
            raise AttributeError('Session ID is immutable.')
        super().__setattr__(name, value)


    @property
    def session_id(self) -> uuid.UUID:
        '''Returns the session's ID.'''

        return self._session_id


    @property
    def timeset(self) -> TimeSet:
        '''Returns the session's 'TimeSet'.'''

        return self._timeset
    

    @timeset.setter
    def timeset(self, timeset: TimeSet) -> None:
        '''Sets the session's 'TimeSet'.

        An empty 'TimeSet' is not permitted.
        
        Raises:
            ValueError: if 'TimeSet' is empty.'''

        if timeset.is_empty:
            raise ValueError('The session must be associated with a non-empty time set.')

        self._timeset = timeset


    @property
    def activities(self) -> frozenset[Activity]:
        '''Returns activities set.'''

        return frozenset(self._activities)
    

    @activities.setter
    def activities(self, activities: set[Activity]) -> None:
        '''Sets session activities.
        
        Set of activities must be non-empty.
        
        Raises:
            ValueError: if we try to set an empty set of activities.'''

        if not activities:
            raise ValueError('Set of activities must be non-empty.')
        
        self._activities = activities.copy()

    

    def add_activity(self, activity: Activity) -> None:
        '''Adds activity to the session.'''

        self._activities.add(activity)


    def remove_activity(self, activity: Activity) -> None:
        '''Removes activity from the session.
        
        Raises:
            ValueError: if we try to remove the last activity.'''

        if len(self._activities) == 1:
            raise ValueError('Session must contain at least one activity.')

        self._activities.remove(activity)


    @classmethod
    def merge(cls, *sessions: Session) -> Session:
        '''Merges sessions with the same set of activities.

        If sessions have same activities, a new session will be created
        that unites the time sets and comments of the original ones.

        Raises:
            ValueError: if sessions have different sets
            of activities.'''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        first_activities = sessions[0].activities
        if any(s.activities != first_activities for s in sessions[1:]):
                raise ValueError(
                    f'Sessions are not mergeable as they have different activies.'
                )

        # Unite time sets.
        timesets = [s.timeset for s in sessions]
        timeset = TimeSet.union(*timesets)

        # As activities are same, we can take them from one session.
        activities = set(sessions[0].activities)

        # Concatenate of comments from given sessions via line breaks.
        comment = '\n'.join(s.comment for s in sessions if s.comment)

        return Session(timeset, activities, comment)