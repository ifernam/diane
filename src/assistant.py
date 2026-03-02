from __future__ import annotations
from dataclasses import dataclass, field
import uuid
import datetime
from sessions import Session
from repository import Repository



class Assistant(Repository):
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
    

    def merge_if_good(self, *sessions: Session | uuid.UUID) -> Session:
        '''Merges sessions with the same set of activities and returns
        the result if it's 'good'.

        If sessions have same activities and the 'goodness' criterion
        is met for a possible new session, a new session will be created
        that unites the time sets and comments of the original ones.
        As a result, a new session appears in the repository,
        and the old ones are removed.

        Raises:
            ValueError: if sessions cannot be merged or the resulting
                session is not 'good'''
        
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
        
        if not Assistant.is_good(merged):
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