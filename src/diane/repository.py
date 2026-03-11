from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import MutableSet

from temporal import Timestamp, TimeInterval, TimeSet
from activities import Activity, Activities
from sessions import Session



@dataclass
class Repository(MutableSet[Session]):
    '''Represents repository of sessions.
    
    Stores sessions and activities registry.'''

    _activities: Activities = field(default_factory=Activities)
    _sessions: set[Session] = field(default_factory=set)


    def _validate_activities(self, activities: Activities) -> None:
        ''' Checks that all session activities are in the given activity
        registry.'''

        for s in self._sessions:
            if not s.activities <= activities:
                raise ValueError(
                    f'The session {s} contains activities that are not in the registry.'
                )


    def _validate(self) -> None:
        self._validate_activities(self._activities)


    def __post_init__(self) -> None:
        self._validate()


    def __contains__(self, item: object) -> bool:
        '''Checks whether the session is contained in the repository.
        
        Only takes the time set and activities set into account.'''

        if not isinstance(item, Session):
            return False
        
        return item in self._sessions


    def __iter__(self):
        return iter(self._sessions)
    

    def __len__(self) -> int:
        '''Size of sessions repository.'''

        return len(self._sessions)
    

    def add(self, value: Session) -> None:
        '''Adds session to the repository.
        
        Adds a session if it is not contained in the repository
        and if it only contains activities that are in the registry.'''

        if value not in self:
            if value.activities <= self._activities:
                self._sessions.add(value)
            else:
                raise ValueError(
                    f'The session {value} cannot be added to the repository because it contains '
                    f'activities that are not in the registry.'
                )


    def discard(self, value: Session) -> None:
        '''Removes session from the registry.'''

        self._sessions.discard(value)

    
    def remove(self, value: Session) -> None:
        '''Removes session from the registry.
        
        Raises:
            KeyError: if the session is not in the repository.'''

        try:
            self._sessions.remove(value)
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

        return {s for s in self._sessions if s.timeset.overlaps(timeset)}
    

    def find_contained_in(self, timeset: TimeSet | TimeInterval) -> set[Session]:
        '''Finds sessions in the repository that are contained
        in a given time set.'''

        if isinstance(timeset, TimeInterval):
            timeset = TimeSet(timeset)

        return {s for s in self._sessions if s.timeset.is_contained_in(timeset)}
    

    def find_closest_in_time_to(self, session: Session) -> Session:
        '''Returns the session in the repository closest in time
        to the given one.
        
        Raises:
            KeyError: if no other sessions in the repository.'''

        def closest_key(s: Session):
            dist = TimeSet.dist(session.timeset, s.timeset)
            return dist is None, dist

        others  = {s for s in self._sessions if s != session}
        if not others:
            raise KeyError('No other sessions in the repository.')
        
        return min(others, key=closest_key)
    

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


    def merge(self, *sessions: Session) -> Session:
        '''Merges sessions contained in the repository with the same set
        of activities and returns the result.

        If sessions have the same set of activities, a new session
        will be created that unites the time sets and comments
        of the original ones. As a result, a new session appears
        in the repository, and the old ones are removed.

        Raises:
            KeyError: if at least one of the given sessions
                is not contained in the repository.
            ValueError: if sessions cannot be merged.'''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        # Remove duplicates, leaving only the first occurrence
        # of each session.
        unique_sessions = list(dict.fromkeys(sessions))
        
        missing = {s for s in sessions if s not in self}
        if len(missing) == 1:
            raise KeyError(f'The session {missing.pop()} is not in the repository.')
        elif len(missing) > 1:
            sessions_string = '; '.join(map(str, missing))
            raise KeyError(f'The sessions {sessions_string} are not in the repository.')

        try:
            merged = Session.merge(*unique_sessions)
        except ValueError as e:
            raise ValueError(f'Sessions cannot be merged: {e}.') from e
        
        self.add(merged)
        for s in sessions:
            self.discard(s)

        return merged