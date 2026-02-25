from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import MutableSet
import uuid
from activities import Activity, Activities
from sessions import Session


@dataclass
class Repository(MutableSet[Session]):
    '''Represents repository of sessions.'''

    _activities: Activities = field(default_factory=Activities)
    _id_to_session: dict[uuid.UUID, Session] = field(default_factory=dict)


    def _validate(self) -> None:

        for session_id, session in self._id_to_session.items():
            if not session.activities <= self._activities:
                raise ValueError(
                    f'The session {session_id} contains activities that are not in the registry.'
                )
    

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
