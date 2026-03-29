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
    '''Represents a repository of sessions.

    Stores sessions and an activities registry.'''

    _activities: Activities = field(default_factory=Activities)
    _sessions: set[Session] = field(default_factory=set)
    
    # Index.
    _starts: SortedList = field(default_factory=SortedList)
    _ends: SortedList = field(default_factory=SortedList)
    _start_to_sessions: dict[Endpoint, set[Session]] = field(default_factory=dict)
    _end_to_sessions: dict[Endpoint, set[Session]] = field(default_factory=dict)
    _activities_index: dict[frozenset[Activity], set[Session]] = field(default_factory=dict)


    def _validate_activities(self, activities: Activities) -> None:
        '''Check that all session activities are in the given activity
        registry.
        
        Args:
            `activities` (`Activities`): The activities registry.

        Raises:
            `ActivitiesNotInRegistryError`: If there are activities
                in the repository that are not listed in the registry.
        '''

        for s in self._sessions:
            if not s.activities <= activities:
                raise ActivitiesNotInRegistryError(
                    f'The session {s} contains activities that are not in the registry.'
                )


    def _validate(self) -> None:
        '''Check that the repository is in the correct state.'''

        self._validate_activities(self._activities)


    def __post_init__(self) -> None:

        self._rebuild_index()
        self._validate()

        self._merge_touching()


    def __contains__(self, item: object) -> bool:
        '''Check that the given session is contained in the repository.
        
        Only the time set and activities set are taken into account.

        Returns:
            `bool`: `True` if the session is present.
        '''

        if not isinstance(item, Session):
            return False
        
        return item in self._sessions


    def __iter__(self):
        return iter(self._sessions)
    

    def __len__(self) -> int:
        '''Return the number of sessions in this repository.

        Returns:
            `int`: The number of sessions.
        '''

        return len(self._sessions)
    

    def _add_to_index_by_activities(self, session: Session) -> None:
        key = frozenset(session.activities)
        if key not in self._activities_index:
            self._activities_index[key] = set()
        self._activities_index[key].add(session)
    

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

        self._add_to_index_by_activities(value)
    

    def _remove_from_index_by_activities(self, session: Session) -> None:
        key = frozenset(session.activities)
        sessions_set = self._activities_index.get(key)
        if sessions_set:
            sessions_set.discard(session)
            if not sessions_set:
                del self._activities_index[key]


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

        self._remove_from_index_by_activities(value)

    
    def _rebuild_activities_index(self) -> None:
        '''Rebuild the entire activities index from current sessions.'''

        self._activities_index.clear()
        for session in self._sessions:
            self._add_to_index_by_activities(session)

    
    def _rebuild_index(self) -> None:
        '''Rebuild the entire index from current sessions.'''

        self._starts.clear()
        self._ends.clear()
        self._start_to_sessions.clear()
        self._end_to_sessions.clear()
        self._activities_index.clear()

        for session in self._sessions:
            self._add_to_index(session)


    def add(self, value: Session) -> None:
        '''Add the given session to the repository.
        
        The session is added only if it is not already present and all
        its activities are in the registry.

        Args:
            `value` (`Session`): The session to add.

        Raises:
            `ActivitiesNotInRegistryError`: If the given session
                contains activities not listed in the registry.
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
        '''Discard the given session from the repository.
        
        Args:
            `value` (`Session`): The session to discard.
        '''

        if value not in self._sessions:
            return
        self._remove_from_index(value)
        self._sessions.discard(value)

    
    def remove(self, value: Session) -> None:
        '''Remove the given session from the repository.

        Args:
            `value` (`Session`): The session to remove.
        
        Raises:
            `KeyError`: If the given session is not in the repository.
        '''

        if value not in self._sessions:
            raise KeyError(f'The session {value} is not in the repository.')
        self._remove_from_index(value)
        self._sessions.remove(value)
    

    @property
    def activities(self) -> Activities:
        '''Return the copy of the activities registry.'''

        return self._activities.copy()
        

    @activities.setter
    def activities(self, activities: Activities) -> None:
        '''Set the activities registry.'''
        
        self._validate_activities(activities)
        self._activities = activities.copy()
        self._rebuild_activities_index()
    

    def find_by_activities(self, activities: set[Activity]) -> set[Session]:
        '''Find sessions that have exactly the given set
        of activities.'''
        
        key = frozenset(activities)
        return self._activities_index.get(key, set()).copy()
    

    def find_overlapping(self, timeset: TimeSet | TimeInterval) -> set[Session]:
        '''Find sessions in the repository that overlap with the given
        time set or time interval.

        Args:
            `timeset` (`TimeSet | TimeInterval`): The time set
                or interval to check for overlap.

        Returns:
            `set[Session]`: The set of sessions that overlap with
                the given time set or interval. If the input is empty,
                returns the empty set.
        '''

        if isinstance(timeset, TimeInterval):
            timeset = TimeSet(timeset)
        
        if timeset.is_empty:
            return set()
        
        target_start = timeset.start
        target_end = timeset.end

        # Candidates by ends: `end >= target_start`.
        if target_start.is_finite:
            candidates_end = set()
            idx = self._ends.bisect_left(target_start)
            for i in range(idx, len(self._ends)):
                end = self._ends[i]
                candidates_end.update(self._end_to_sessions.get(end, set()))
        else:
            candidates_end = self._sessions

        # Candidates by starts: `start <= target_end`.
        if target_end.is_finite:
            candidates_start = set()
            idx = self._starts.bisect_right(target_end)
            for i in range(idx):
                start = self._starts[i]
                candidates_start.update(self._start_to_sessions.get(start, set()))
        else:
            candidates_start = self._sessions

        candidates = candidates_end & candidates_start

        return {s for s in candidates if s.timeset.overlaps(timeset)}
    

    def find_contained_in(self, timeset: TimeSet | TimeInterval) -> set[Session]:
        '''Find sessions in the repository that are contained
        in the given time set or interval.
        
        Args:
            `timeset` (`TimeSet | TimeInterval`): The time set
                or interval that should contain the sessions.

        Returns:
            `set[Session]`: The set of sessions that are completely
                inside the given time set or interval. If the input
                is empty, returns the empty set.
        '''

        if isinstance(timeset, TimeInterval):
            timeset = TimeSet(timeset)
        
        if timeset.is_empty:
            return set()
        
        target_start = timeset.start
        target_end = timeset.end

        if target_start.is_finite:
            # Candidates by starts: `start >= target_start`.
            candidates_start = set()
            idx = self._starts.bisect_left(target_start)
            for i in range(idx, len(self._starts)):
                start = self._starts[i]
                candidates_start.update(self._start_to_sessions.get(start, set()))
        else:
            candidates_start = self._sessions

        # Candidates by ends: `end <= target_end`.
        if target_end.is_finite:
            candidates_end = set()
            idx = self._ends.bisect_right(target_end)
            for i in range(idx):
                end = self._ends[i]
                candidates_end.update(self._end_to_sessions.get(end, set()))
        else:
            candidates_end = self._sessions

        candidates = candidates_start & candidates_end

        return {s for s in candidates if s.timeset in timeset}
    

    def find_closest_in_time_to(self, session: Session) -> Session:
        '''Return the session in the repository closest in time
        to the given one.
        
        Returns:
            `Session`: The closest session.

        Raises:
            `KeyError`: If there are no other sessions
                in the repository.
        '''

        others  = self._sessions - {session}

        if not others:
            raise KeyError('No other sessions in the repository.')
        
        span = session.timeset.span()
        
        # Candidates to the left.
        idx = self._ends.bisect_left(span.start)
        if idx > 0:
            idx -= 1
            end = self._ends[idx]
            candidate_to_the_left = {next(iter(self._end_to_sessions[end]))}
        else:
            candidate_to_the_left = set()
        
        # Candidates to the right.
        idx = self._starts.bisect_right(span.end)
        if idx < len(self._starts):
            start = self._starts[idx]
            candidate_to_the_right = {next(iter(self._start_to_sessions[start]))}
        else:
            candidate_to_the_right = set()

        # Candidates in span.
        candidates_in_span = self.find_overlapping(span)

        candidates = candidate_to_the_left | candidates_in_span | candidate_to_the_right
        candidates -= {session}

        if not candidates:
            return next(iter(others))

        return min(candidates, key=lambda s: TimeSet.dist(session.timeset, s.timeset))
    

    def last(self) -> Session:
        '''Return the last completed session.
        
        Raises:
            `KeyError`: If there are no sessions completed up to present
                in the repository.
        '''

        up_to_present = self.find_contained_in(TimeInterval.leftclosed(Timestamp.now()))

        if not up_to_present:
            raise KeyError('There are no sessions completed up to present in the repository.')
        
        return max(up_to_present, key=(lambda s: s.timeset.end))


    def merge(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) and return the merged session.

        The sessions are merged only if they have identical activity
        sets. A new session is created that unites the time sets
        and comments of the original ones. The original sessions
        are removed from the repository and the merged session is added.

        Raises:
            `KeyError`: If at least one of the given sessions is not in
                the repository.
            `ValueError`: If the sessions cannot be merged
                (e.g., different activity sets).
        '''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        missing = {s for s in sessions if s not in self}
        if len(missing) == 1:
            raise KeyError(f'The session {missing.pop()} is not in the repository.')
        elif len(missing) > 1:
            sessions_string = '; '.join(map(str, missing))
            raise KeyError(f'The sessions {sessions_string} are not in the repository.')

        try:
            merged = Session.merge(*sessions)
        except ValueError as e:
            raise ValueError(f'Sessions cannot be merged. {e}.') from e
        
        for s in sessions:
            self.discard(s)
        self.add(merged)

        return merged
    

    def _merge_touching(self) -> None:
        '''Merge touching sessions with the same activities.

        Sessions that touch (overlap or meet at a boundary) and have
        identical activity sets are merged into a single session.
        '''

        for sessions in tuple(self._activities_index.values()):
            if len(sessions) <= 1:
                continue

            # Sort sessions by start time for sequential scanning.
            sorted_sessions = sorted(sessions, key=lambda s: s.timeset.start)

            # Split into connected components using the 'touches' relation.
            components = []
            current = [sorted_sessions[0]]
            current_union = sorted_sessions[0].timeset

            for s in sorted_sessions[1:]:
                if current_union.touches(s.timeset):
                    current.append(s)
                    current_union = TimeSet.union(current_union, s.timeset)
                else:
                    components.append(current)
                    current = [s]
                    current_union = s.timeset
            components.append(current)

            # Merge each component that contains more than one session.
            for comp in components:
                if len(comp) > 1:
                    merged = Session.merge(*comp)
                    for s in comp:
                        self.discard(s)
                    self.add(merged)