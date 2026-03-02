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
        ''' Checks that all session activities are in the given activity
        registry.'''

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
            raise KeyError(f'Unknown session: {session_id}.') from e
    

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
        
        self._validate_activities(activities)
        self._activities = activities.copy()
    

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
        '''Finds sessions in the repository that are contained
        in a given time set.'''

        if isinstance(timeset, TimeInterval):
            timeset = TimeSet(timeset)

        contained_sessions = set()
        for session in self._id_to_session.values():
            if session.timeset.is_contained_in(timeset):
                contained_sessions.add(session)

        return contained_sessions
    

    def find_closest_in_time_to(self, session: uuid.UUID | Session) -> Session:
        '''Returns the session closest in time to the given one.
        
        Raises:
            KeyError: if no other sessions in the repository.'''

        session = self._resolve_session(session)

        def closest_key(s: Session):
            dist = TimeSet.dist(session.timeset, s.timeset)
            return dist is None, dist

        considered_sessions  = {s for s in self._id_to_session.values() if s != session}
        if not considered_sessions:
            raise KeyError('No other sessions in the repository.')
        
        closest = min(considered_sessions, key=closest_key)

        return closest
    

    def last(self) -> Session:
        '''Returns the last completed session.
        
        Raises:
            KeyError: if there are no sessions completed up to present
            in the repository.'''

        up_to_present = self.find_contained_in(TimeInterval.leftclosed(Timestamp.now()))

        if not up_to_present:
            raise KeyError('There are no sessions completed up to present in the repository.')

        def last_key(s: Session):
            return (
                s.timeset.end is None,
                s.timeset.end,
                s.timeset.is_end_included)
        
        return max(up_to_present, key=last_key)


    def merge(self, *sessions: Session | uuid.UUID) -> Session:
        '''Merges sessions with the same set of activities and returns
        the result.

        If sessions have same activities, a new session will be created
        that unites the time sets and comments of the original ones.
        As a result, a new session appears in the repository,
        and the old ones are removed.

        Raises:
            ValueError: if sessions cannot be merged.'''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        resolved_sessions = [self._resolve_session(s) for s in sessions]

        # Remove duplicates by ID, leaving only the first occurrence
        # of each session.
        sessions_to_merge = list(dict.fromkeys(resolved_sessions))

        try:
            merged = Session.merge(*sessions_to_merge)
        except ValueError as e:
            raise ValueError(f'Sessions cannot be merged: {e}.') from e
        
        self.add(merged)
        for s in sessions:
            self.discard(s)

        return merged