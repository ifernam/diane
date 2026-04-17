from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import MutableSet
from sortedcontainers import SortedList
import warnings
import heapq
from typing import Iterator
from itertools import count


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

class NoActivitiesError(RepositoryError):
    '''The repository contains a session with the empty activities
    set.'''
    pass

class EmptyTimeSetError(RepositoryError):
    '''The repository contains a session with the empty time set.'''
    pass

class UnboundedTimeSetError(RepositoryError):
    '''The repository contains a session with an unbounded time set.'''
    pass



@dataclass
class Repository(MutableSet[Session]):
    '''Represents a repository of sessions.

    Stores sessions and an activities registry.
    '''

    _activities: Activities = field(default_factory=Activities)
    _sessions: set[Session] = field(default_factory=set)
    
    # Index.
    _starts: SortedList = field(default_factory=SortedList, init=False)
    _ends: SortedList = field(default_factory=SortedList, init=False)
    _start_to_sessions: dict[Endpoint, set[Session]] = field(default_factory=dict, init=False)
    _end_to_sessions: dict[Endpoint, set[Session]] = field(default_factory=dict, init=False)
    _activities_index: dict[frozenset[Activity], set[Session]] = field(
        default_factory=dict, init=False
    )


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

        for s in self._sessions:
            if not s.activities:
                raise NoActivitiesError(
                    'The repository contains a session with the empty activities set.'
                )
            if s.timeset.is_empty:
                raise EmptyTimeSetError(
                    'The repository contains a session with the empty time set.'
                )
            if s.timeset.is_unbounded:
                raise UnboundedTimeSetError(
                    'The repository contains a session with an unbounded time set.'
                )


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
                    f'The session cannot be added to the repository because it contains '
                    f'activities that are not in the registry.'
                )
            if not value.activities:
                raise NoActivitiesError('A session must contain at least one activity.')
            if value.timeset.is_empty:
                raise EmptyTimeSetError('A session must be associated with a non-empty time set.')
            if value.timeset.is_unbounded:
                raise UnboundedTimeSetError(
                    'Only sessions with a bounded time set are permitted in the repository.'
                )
            
            self._sessions.add(value)
            self._add_to_index(value)


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


    def iter_from_last(
        self, end: Timestamp | None = None, *activities: Activity | str
    ) -> Iterator[Session]:
        '''Iterate over sessions in the repository in descending order
        of their end time.

        The iteration starts from the latest session whose end time
        is less than or equal to `end` and proceeds backwards in time.

        Args:
            `end` (`Timestamp | None`): The upper bound for session end
                times. If `None`, the iteration starts from the session
                with the latest end time in the repository.
            `*activities` (`Activity | str`): Required exact set
                of activities. If none given, any activity set
                is accepted.

        Returns:
            `Iterator[Session]`: An iterator over sessions ordered
            by decreasing end time. For sessions with the same end time,
            the order is descending by start time.
        '''

        if not self._sessions:
            # No sessions in the repository, so the iteration is empty.
            return
        
        if end is None:
            end = self._ends[-1]  # The latest end time among sessions.

        # Resolve activities.
        specified_activities = set()
        if activities:
            for a in activities:
                if isinstance(a, str):
                    try:
                        specified_activities.add(self._activities.activity_by_slug(a))
                    except KeyError:
                        continue  # Unknown slug.
                
                specified_activities.add(a)

        # Start from the last end time that is `<= end`.
        idx = self._ends.bisect_right(end) - 1 
        while idx >= 0:
            end_time = self._ends[idx]
            
            # Iterate sessions with this end time in reverse order
            # of start time.
            sessions_with_end = sorted(
                self._end_to_sessions[end_time],
                key=lambda s: s.timeset.start,
                reverse=True
            )
            
            for s in sessions_with_end:
                # Check if the session is completed by `end`.
                if s.timeset.end <= end:
                    # Yield the last session completed by `end`.

                    # If activities specified, only return session
                    # if it has activities as specified.
                    if specified_activities:
                        if s.activities == specified_activities:
                            yield s
                    else:
                        yield s

            # Move to the previous end time.    
            idx -= 1


    def iter_overlapping(self, target: TimeSet | TimeInterval) -> Iterator[Session]:
        '''Iterate over sessions that overlap within the given time set
        or interval.

        The iteration proceeds in reverse chronological order of session
        end times.

        Args:
            `target` (`TimeSet | TimeInterval`): The time set
                or interval that must overlap within the sessions.
                An empty target yields no sessions.

        Returns:
            `Iterator[Session]`: The iterator over sessions that overlap
            within target, ordered by decreasing end time. For sessions
            with the same end time, the order is descending by start
            time.
        '''

        if not self._sessions:
            # No sessions in the repository, so the iteration is empty.
            return

        if isinstance(target, TimeInterval):
            target = TimeSet(target)
        
        if target.is_empty:
            # Empty target cannot overlap.
            return
        
        start = target.start

        for s in self.iter_from_last():
            
            # Ends earlier than target starts.
            if s.timeset.end < start:
                # All remaining sessions end even earlier, so none can
                # overlap.
                return

            # Does not overlap within target.
            if not s.timeset.overlaps(target):
                continue

            yield s


    def iter_contained_in(self, target: TimeSet | TimeInterval) -> Iterator[Session]:
        '''Iterate over sessions that are completely contained within
        the given time set or interval.

        The iteration proceeds in reverse chronological order of session
        end times.

        Args:
            `target` (`TimeSet | TimeInterval`): The time set
                or interval that must fully contain the sessions.
                An empty target yields no sessions.

        Returns:
            `Iterator[Session]`: The iterator over sessions fully
                contained in target, ordered by decreasing end time.
                For sessions with the same end time, the order
                is descending by start time.
        '''

        if not self._sessions:
            # No sessions in the repository, so the iteration is empty.
            return

        if isinstance(target, TimeInterval):
            target = TimeSet(target)
        
        if target.is_empty:
            # Empty target contains nothing.
            return
        
        end = target.end.timestamp if target.is_right_bounded else None  # Timestamp.
        start = target.start                                             # Endpoint.

        for s in self.iter_from_last(end):
            
            # Ends earlier than target starts.
            if s.timeset.end < start:
                # All remaining sessions end even earlier, so none can
                # be contained.
                return

            # Not contained in target.
            if s.timeset not in target:
                continue

            yield s


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

        Args:
            `session` (`Session`): The session to find the closest one.
        
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
    

    def iter_closest_in_time_to(self, session: Session) -> Iterator[Session]:
        '''Iterate the sessions in the repository closest in time
        to the given one.

        Args:
            `session` (`Session`): The session to find the closest ones.
        
        Returns:
            `Iterator[Session]`: The closest sessions.
        '''

        span = session.timeset.span()
        visited = {session}

        queue = []         # Initialise heap.
        counter = count()  # Initialise counter.

        # Sessions overlapping span.
        for s in self.find_overlapping(span):
            if s not in visited:
                dist = TimeSet.dist(session.timeset, s.timeset)
                heapq.heappush(queue, (dist, next(counter), s, 'C', None))
                visited.add(s)

        # Initialise indices for left and right sessions.
        l_idx = self._ends.bisect_left(span.start) - 1
        r_idx = self._starts.bisect_right(span.end)

        def push_from_left(idx):
            if idx >= 0:
                end_val = self._ends[idx]
                for s in self._end_to_sessions[end_val]:
                    if s not in visited:
                        dist = TimeSet.dist(session.timeset, s.timeset)
                        heapq.heappush(queue, (dist, next(counter), s, 'L', idx))
                        visited.add(s)

        def push_from_right(idx):
            if idx < len(self._starts):
                start_val = self._starts[idx]
                for s in self._start_to_sessions[start_val]:
                    if s not in visited:
                        dist = TimeSet.dist(session.timeset, s.timeset)
                        heapq.heappush(queue, (dist, next(counter), s, 'R', idx))
                        visited.add(s)

        push_from_left(l_idx)
        push_from_right(r_idx)

        # Main extraction cycle.
        while queue:
            _, _, s, direction, _ = heapq.heappop(queue)
            yield s

            # Expand the search to the left (for 'L') or right (for 'R').
            if direction == 'L':
                l_idx -= 1
                push_from_left(l_idx)
            elif direction == 'R':
                r_idx += 1
                push_from_right(r_idx)
            # Do nothing for 'C'.
    

    def last(self, end: Timestamp | None = None, *activities: Activity | str) -> Session:
        '''Return the last session (by end time) that matches
        the criteria.

        Args:
            `end` (`Timestamp | None`): The upper bound for session end
                times. If `None`, the latest end time in the repository
                is used.
            `*activities` (`Activity | str`): Required exact set
                of activities. If none given, any activity set
                is accepted.

        Returns:
            `Session`: The first session from 
            `iter_from_last(end, *activities)`.

        Raises:
            `KeyError`: If no session satisfies the conditions.
        '''
        
        if end is None:
            end = self._ends[-1]  # The latest end time among sessions.
        try:
            return next(self.iter_from_last(end, *activities))
        except StopIteration:
            raise KeyError('No sessions found matching the criteria.')


    def merge(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) and add the merged session to the repository.

        The sessions are merged only if they have **identical activity
        sets**. A new session is created with the same activities that
        unites the time sets and messages of the original ones.
        The original sessions are removed from the repository
        and the merged session is added.

        Args:
            `*sessions` (`Session`): The sessions for merging.

        Returns:
            `Session`: The merged session.

        Raises:
            `KeyError`: If at least one of the given sessions
                is not in the repository.
            `ValueError`: If no sessions are provided,
                or if the sessions cannot be merged (e.g., different
                activity sets).
        '''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        missing = {s for s in sessions if s not in self}
        if len(missing) == 1:
            raise KeyError('One session is missing from the repository.')
        elif len(missing) > 1:
            raise KeyError(f'There are {len(missing)} sessions missing from the repository')

        try:
            merged = Session.merge(*sessions)
        except ValueError as e:
            raise ValueError(f'Unable to merge the sessions. {e}.') from e
        
        for s in sessions:
            self.discard(s)
        self.add(merged)

        return merged
    

    def _merge_touching(self) -> None:
        '''Merge all touching sessions with the same activities
        in the repository.

        Sessions that touch (overlap by time or meet at a boundary)
        and have identical activity sets are merged.
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
                    current_union = current_union | s.timeset
                else:
                    components.append(current)
                    current = [s]
                    current_union = s.timeset
            components.append(current)

            # Merge each component that contains more than one session.
            for comp in components:
                self.merge(*comp)


    def session_from_dict(self, session_data: dict, date_iso: str = '') -> Session:
        '''Construct a session from the dictionary.
        
        The dictionary must contain the following keys:
        - `time_zone` (`str`): The IANA time zone name for the session.
        - `intervals` (`list`): The list of time intervals, where each
          interval is represented as a dictionary with keys `start`
          and `end` (both ISO 8601 strings).
        - `activities` (`list`): The list of activity slugs (strings)
          corresponding to activities in the repository's registry.
        - `message` (`str`): The optional message for the session.
          If not provided, defaults to the empty string.

        Args:
            `session_data` (`dict`): The dictionary containing session
                data.
            `date_iso` (`str`): The ISO 8601 date string.

        Returns:
            `Session`: The constructed session.

        Raises:
            `TypeError`: If the input data is of incorrect type.
            `ValueError`: If the input data is missing required keys
                or contains invalid values.

        Warns:
            `UserWarning`: If the input dictionary contains extra keys
                not used for session construction. The warning message
                lists the extra keys.
        '''

        if not isinstance(session_data, dict):
            raise TypeError('\'session_data\' must be a dictionary.')
        
        # Check for extra keys in the dictionary.
        allowed_keys = {'time_zone', 'intervals', 'activities', 'message'}
        extra_keys = set(session_data) - allowed_keys
        if extra_keys:
            extra_keys_str = ', '.join(f'\'{k}\'' for k in sorted(extra_keys))
            warnings.warn(
                f'The session dictionary contains unknown keys: {extra_keys_str}.',
                stacklevel=2
            )

        # Get time set.
        try:
            time_zone_iana = session_data['time_zone']
        except KeyError:
            raise ValueError(
                f'The session dictionary is missing the required \'time_zone\' key.'
            )
        if not isinstance(time_zone_iana, str):
            raise TypeError(
                f'Value \'time_zone\' must be a string, got \'{type(time_zone_iana).__name__}\'.'
            )
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
        intervals = [TimeInterval.from_dict(i, time_zone_iana, date_iso) for i in intervals_data]
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
        
        # Get message.
        message = session_data.get('message', '')
        if not isinstance(message, str):
            raise TypeError(
                f'The value of the \'message\' key must be a string, got '
                f'\'{type(message).__name__}\'.')

        session = Session(timeset, activities, message)

        return session