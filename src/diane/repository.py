from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import MutableSet
from sortedcontainers import SortedList
import warnings


from diane.temporal import Timestamp, Endpoint, TimeInterval, TimeSet
from diane.activities import Activity, Activities
from diane.sessions import Session



class RepositoryError(Exception):
    '''The base exception for all repository errors.'''
    pass


class ActivitiesNotInRegistryError(RepositoryError):
    '''The session contains activities that are not contained
    in the registry.'''
    pass



@dataclass
class Repository(MutableSet[Session]):
    '''Represents repository of sessions.
    
    Stores sessions and activities registry.'''

    _activities: Activities = field(default_factory=Activities)
    _sessions: set[Session] = field(default_factory=set)

    _starts: SortedList = field(default_factory=SortedList)
    _ends: SortedList = field(default_factory=SortedList)
    _start_to_sessions: dict[Endpoint, set[Session]] = field(default_factory=dict)
    _end_to_sessions: dict[Endpoint, set[Session]] = field(default_factory=dict)


    def _validate_activities(self, activities: Activities) -> None:
        ''' Checks that all session activities are in the given activity
        registry.'''

        for s in self._sessions:
            if not s.activities <= activities:
                raise ActivitiesNotInRegistryError(
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
    

    def _add_to_index(self, value: Session) -> None:
        start = value.timeset.start
        if start not in self._start_to_sessions:
            self._start_to_sessions[start] = set()
            self._starts.add(start)
        self._start_to_sessions[start].add(value)

        end = value.timeset.end
        if end not in self._end_to_sessions:
            self._end_to_sessions[end] = set()
            self._ends.add(end)
        self._end_to_sessions[end].add(value)


    def _remove_from_index(self, value: Session) -> None:
        start = value.timeset.start
        sessions_set = self._start_to_sessions.get(start)
        if sessions_set:
            sessions_set.discard(value)
            if not sessions_set:
                del self._start_to_sessions[start]
                try:
                    self._starts.remove(start)
                except ValueError:
                    # Inconsistency.
                    pass

        end = value.timeset.end
        sessions_set = self._end_to_sessions.get(end)
        if sessions_set:
            sessions_set.discard(value)
            if not sessions_set:
                del self._end_to_sessions[end]
                try:
                    self._ends.remove(end)
                except ValueError:
                    # Inconsistency.
                    pass


    def add(self, value: Session) -> None:
        '''Add the given session to the repository.
        
        Add the session if it is not contained in the repository
        and if it only contains activities that are in the registry.
        '''

        if value not in self:
            if not value.activities <= self._activities:
                raise ActivitiesNotInRegistryError(
                    f'The session {value} cannot be added to the repository because it contains '
                    f'activities that are not in the registry.'
                )
            
            self._sessions.add(value)
            self._add_to_index(value)
            

    def add_from_dict(self, session_data: dict, date_iso: str = '') -> None:
        '''Create a session from the dictionary and add it to this
        repository.'''

        if not isinstance(session_data, dict):
            raise TypeError('\'session_data\' must be a dictionary.')
        
        # Check for extra keys in the dictionary.
        allowed_keys = {'intervals', 'activities', 'comment'}
        extra_keys = set(session_data) - allowed_keys
        if extra_keys:
            extra_keys_str = ', '.join(f'\'{k}\'' for k in sorted(extra_keys))
            warnings.warn(
                f'The session dictionary contains unknown fields: {extra_keys_str}.',
                stacklevel=2
            )

        # Get time set.
        try:
            intervals_data = session_data['intervals']
        except KeyError:
            raise ValueError(
                f'The session dictionary is missing the required \'intervals\' key.'
            )
        if not isinstance(intervals_data, list):
            raise TypeError(
                f'The value of the \'intervals\' key must be a list, got '
                f'\'{type(intervals_data).__name__}\'.')
        intervals = [TimeInterval.from_dict(i, date_iso) for i in intervals_data]
        timeset =  TimeSet(*intervals)

        # Get activities.
        try:
            activities_data = session_data['activities']
        except KeyError:
            raise ValueError(
                f'The session dictionary is missing the required \'activities\' key.'
            )
        if not isinstance(activities_data, list):
            raise TypeError(
                f'The value of the \'activities\' key must be a list, got '
                f'\'{type(activities_data).__name__}\'.')
        activities = set()
        for a in activities_data:
            if not isinstance(a, str):
                raise TypeError(
                    f'The activity slug must be a string, got '
                    f'\'{type(activities_data).__name__}\'.')
            Activity._validate_slug(a)
            activities.add(self._activities.activity_by_slug(a))
        
        # Get comment.
        comment = session_data.get('comment', '')
        if not isinstance(comment, str):
            raise TypeError(
                f'The value of the \'comment\' key must be a string, got '
                f'\'{type(comment).__name__}\'.')

        session = Session(timeset, activities, comment)

        self.add(session)


    def discard(self, value: Session) -> None:
        '''Discard the given session from the registry.'''

        if value not in self._sessions:
            return
        self._remove_from_index(value)
        self._sessions.discard(value)

    
    def remove(self, value: Session) -> None:
        '''Remove the given session from the registry.
        
        Raises:
            KeyError: If the given session is not in the repository.
        '''

        if value not in self._sessions:
            raise KeyError(f'The session {value} is not in the repository.')
        self._remove_from_index(value)
        self._sessions.remove(value)
    

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

        return {s for s in self._sessions if s.timeset in timeset}
    

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
        
        return max(up_to_present, key=(lambda s: s.timeset.end))


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