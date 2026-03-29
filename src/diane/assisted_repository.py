from __future__ import annotations
from dataclasses import dataclass, field

from diane.sessions import Session
from diane.repository import Repository



class AssistedRepository(Repository):
    '''Smart wrapper to the 'Repository'.'''


    @staticmethod
    def is_good(session: Session) -> bool:
        '''Return `True` if the given session is 'good'.
        
        Assess how 'good' the session is according to certain criteria.
        'Goodness' usually means that the pauses between activity
        intervals are not too long.
        '''

        return session.timeset.max_gap_duration <= session.timeset.min_component_duration
    

    def merge_if_good(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) and return the merged session if it's 'good'.

        The sessions are merged only if they have identical activity
        sets and the result is 'good'. A new session unites the time
        sets and comments of the original ones. The original sessions
        are removed from the repository and the merged session is added.

        Raises:
            `KeyError`: If at least one of the given sessions
                is not contained in the repository.
            `ValueError`: If sessions cannot be merged or the resulting
                session is not 'good'.
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
            raise ValueError(f'Sessions cannot be merged: {e}.') from e
        
        if not AssistedRepository.is_good(merged):
            raise ValueError(f'The sessions were not merged because the result was not good.')
        
        for s in sessions:
            self.discard(s)
        self.add(merged)

        return merged
    

    def add_and_merge(self, session: Session) -> Session:
        '''Add the given session to the repository and repeatedly
        merge it with the closest session in time until no further merge
        is possible.

        Args:
            `session` (`Session`): The session to add.

        Return:
            `Session`: The final merged session.
        '''

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