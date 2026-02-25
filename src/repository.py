from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import MutableSet
import uuid
from temporal import Timestamp, TimeInterval, TimeSet
from activities import Activity, Activities
from sessions import Session


@dataclass
class Repository(MutableSet[Session]):
    '''Represents repository of sessions.'''

    _activities: Activities = field(default_factory=Activities)
    _id_to_session: dict[uuid.UUID, Session] = field(default_factory=dict)


    def _validate_activities(self, activities: Activities) -> None:
        for session_id, session in self._id_to_session.items():
            if not session.activities <= activities:
                raise ValueError(
                    f'The session {session_id} contains activities that are not in the registry.'
                )


    def _validate(self) -> None:
        self._validate_activities(self._activities)


    def __post_init__(self) -> None:
        self._validate()


    def __contains__(self, item: object) -> bool:
        '''Checks whether the session is contained in the repository.
        
        Only takes the ID into account.'''

        if isinstance(item, Session):
            return item.session_id in self._id_to_session
        
        if isinstance(item, uuid.UUID):
            return item in self._id_to_session
        
        return False


    def __iter__(self):
        return iter(self._id_to_session.values())
    

    def __len__(self) -> int:
        '''Size of sessions repository.'''

        return len(self._id_to_session)
    

    def _resolve_session(self, obj: Session | uuid.UUID) -> Session:
        '''Checks for session in the repository. If session is found,
        restores session according to the ID.'''

        if isinstance(obj, Session):
            session_id = obj.session_id
        elif isinstance(obj, uuid.UUID):
            session_id = obj
        else:
            raise TypeError(f'\'obj\' must be \'Session\' or \'uuid.UUID\'.')
        
        try:
            return self._id_to_session[session_id]
        except KeyError as e:
            raise KeyError(f'Unknown session: \'{session_id}\'.') from e
    

    def add(self, value: Session) -> None:
        '''Adds session to the repository.
        
        Adds a session if it is not contained in the repository
        and if it only contains activities that are in the registry.'''

        if value not in self:
            if value.activities <= self._activities:
                self._id_to_session[value.session_id] = value
            else:
                raise ValueError(
                    f'The session {value} cannot be added to the repository because it contains '
                    f'activities that are not in the registry.'
                )


    def discard(self, value: uuid.UUID | Session) -> None:
        '''Removes session from the registry.'''

        try:
            session = self._resolve_session(value)
            del self._id_to_session[session.session_id]
        except KeyError:
            pass

    
    def remove(self, value: uuid.UUID | Session) -> None:
        '''Removes session from the registry.
        
        Raises:
            KeyError: if the session is not in the repository.'''

        try:
            session = self._resolve_session(value)
            del self._id_to_session[session.session_id]
        except KeyError as e:
            raise KeyError(f'The session {value} is not in the repository.') from e
    

    @property
    def activities(self) -> Activities:
        '''Returns copy of the activities registry.'''

        return self._activities.copy()
        

    @activities.setter
    def activities(self, activities: Activities) -> None:
        '''Sets the activities registry.'''
        
        new_activities = activities.copy()
        self._validate_activities(new_activities)
        self._activities = new_activities
    

    def find_overlapping(self, timeset: TimeSet | TimeInterval) -> set[Session]:
        '''Finds sessions in the repository that overlap with a given
        time set.'''

        if isinstance(timeset, TimeInterval):
            timeset = TimeSet(timeset)

        overlapping_sessions = set()
        for session in self._id_to_session.values():
            if session.timeset.overlaps(timeset):
                overlapping_sessions.add(session)

        return overlapping_sessions
    

    def find_contained_in(self, timeset: TimeSet | TimeInterval) -> set[Session]:
        '''Finds sessions in the repository that contained in a given
        time set.'''

        if isinstance(timeset, TimeInterval):
            timeset = TimeSet(timeset)

        contained_sessions = set()
        for session in self._id_to_session.values():
            if session.timeset.is_contained_in(timeset):
                contained_sessions.add(session)

        return contained_sessions