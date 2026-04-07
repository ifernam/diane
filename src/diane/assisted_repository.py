from __future__ import annotations
from dataclasses import dataclass, field

from diane.temporal import TimeSet
from diane.sessions import Session
from diane.repository import Repository



class AssistedRepository(Repository):
    '''Smart wrapper to the 'Repository'.
    
    This provides some 'assisted' features, such as merging
    sessions that are close in time and have the same activities.
    '''


    @staticmethod
    def is_good(session: Session) -> bool:
        '''Return `True` if the given session is 'good'.
        
        Assess how 'good' the session is according to certain criteria.
        'Goodness' usually means that the pauses between activity
        intervals are not too long.

        Returns:
            `bool`: `True` if the session is 'good', `False` otherwise.
        '''

        return session.timeset.max_gap_duration <= session.timeset.min_component_duration
    

    def merge_if_good(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) if the result will be 'good' and add
        the merged session to the repository.

        The sessions are merged only if they have **identical activity
        sets** and **the result will be 'good'**. A new session
        is created with the same activities that unites the time sets
        and messages of the original ones. The original sessions
        are removed from the repository and the merged session is added.

        Args:
            `*sessions` (`Session`): The sessions for merging.

        Returns:
            `Session`: The merged session.

        Raises:
            `KeyError`: If at least one of the given sessions
                is not in the repository.
            `ValueError`: If no sessions are provided,
                or if the sessions cannot be merged (e.g., different
                activity sets or the result won't be 'good').
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
        
        if not AssistedRepository.is_good(merged):
            raise ValueError(f'The sessions won\'t merge because the result won\'t be \'good\'.')
        
        for s in sessions:
            self.discard(s)
        self.add(merged)

        return merged
    

    def add_and_merge(self, session: Session) -> Session:
        '''Add the given session to the repository and repeatedly
        merge it with the closest session in time until no further merge
        is possible. The final merged session is returned.

        Args:
            `session` (`Session`): The session to add and merge.

        Returns:
            `Session`: The final merged session.
        '''

        self.add(session)
        for s in self.iter_closest_in_time_to(session):
            if TimeSet.dist(session.timeset, s.timeset) > session.timeset.min_component_duration:
                # Closest session is too far for merging.
                break

            # Try merge.
            try:
                session = self.merge_if_good(session, s)
            except ValueError:
                # Cannot merge with this session `s`. Try next.
                continue

        return session