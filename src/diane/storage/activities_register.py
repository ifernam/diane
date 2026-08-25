from abc import ABC
from collections.abc import MutableMapping
from pathlib import Path

from pydantic import BaseModel

from diane.activity import Activity


class ActivitiesRegisterConfig(BaseModel):
    """An activities register configuration.

    Attributes:
        path (Path): A relative path where activity notes are stored.
    """
    path: Path


class ActivitiesRegister(MutableMapping[str, Activity], ABC):
    """Represents an activities register.

    This abstraction enables activities stored on disk to be worked
    with.

    Attributes:
        _storage_path (Path): A path to an activities and sessions
            storage.
        _config (ActivitiesRegisterConfig): An activities register
            configuration.
    """

    _storage_path: Path
    _config: ActivitiesRegisterConfig

    def __init__(
        self, storage_path: Path, config: ActivitiesRegisterConfig
    ) -> None:
        self._storage_path = storage_path
        self._config = config
