from __future__ import annotations
from dataclasses import dataclass, field
import uuid
from activities import Activity, Activities
from sessions import Session


@dataclass
class Repository:
    '''Represents repository of sessions.'''

    _activities: Activities = field(default_factory=Activities)
    _sessions_by_id: dict[uuid.UUID, Session] = field(default_factory=dict)


    def _validate(self) -> None:

        for session_id, session in self._sessions_by_id.items():
            if not session.activities <= self._activities:
                raise ValueError(
                    f'The session {session_id} contains activities that are not in the registry.'
                )
    

    def __post_init__(self) -> None:
        self._validate()
