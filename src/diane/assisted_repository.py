from __future__ import annotations
from dataclasses import dataclass, field

from sessions import Session
from repository import Repository



class AssistedRepository(Repository):
    '''Smart add-on to sessions repository.'''


    @staticmethod
    def is_good(session: Session) -> bool:
        '''Assesses how 'good' a session is according to certain
        criteria.

        'Goodness' usually means that the pauses between activity
        intervals are not too long.'''

        if session.timeset.min_component_duration is None:
            return False

        return session.timeset.max_gap_duration <= session.timeset.min_component_duration
    

    def merge_if_good(self, *sessions: Session) -> Session:
        '''Merges sessions contained in the repository with the same set
        of activities and returns the result if it's 'good'.

        If sessions have same activities and the 'goodness' criterion
        is met for a possible new session, a new session will be created
        that unites the time sets and comments of the original ones.
        As a result, a new session appears in the repository,
        and the old ones are removed.

        Raises:
            KeyError: if at least one of the given sessions
                is not contained in the repository.
            ValueError: if sessions cannot be merged or the resulting
                session is not 'good'''
        
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
        
        if not AssistedRepository.is_good(merged):
            raise ValueError(f'The sessions were not merged because the result was not good.')
        
        self.add(merged)
        for s in sessions:
            self.discard(s)

        return merged
    

    def add_and_merge(self, session: Session) -> Session:
        '''Adds a session to the repository and repeatedly merges it
        with the closest session in time until no further merge
        is possible.

        Returns the final merged session.'''

        self.add(session)
        while True:
            try:
                closest = self.find_closest_in_time_to(session)
            except KeyError:
                # No other sessions left to merge with.
                return session
            
            try:
                session = self.merge_if_good(session, closest)
            except ValueError:
                # Cannot merge with this closest session; stop.
                return session