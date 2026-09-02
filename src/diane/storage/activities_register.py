from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from pathlib import Path

from pydantic import BaseModel

from diane.activity import Activity


class ActivitiesRegisterConfig(BaseModel):
    """An activities register configuration.

    Attributes:
        path (Path): A relative path where activities are stored.
        fallback_emoji (str): The fallback activity's Unicode emoji.
            '⚫' by default.
    """

    path: Path
    fallback_emoji: str = '⚫'


class ActivitiesRegister[ConfigT: ActivitiesRegisterConfig](
    MutableMapping[str, Activity], ABC
):
    """Represents an activities register.

    This abstraction enables activities stored on disk to be worked
    with.

    Attributes:
        _storage_path (Path): A path to an activities and sessions
            storage.
        _config (ConfigT): An activities register configuration.
    """

    _storage_path: Path
    _config: ConfigT

    def __init__(self, storage_path: Path, config: ConfigT) -> None:
        """Create a new activities register representation.

        Args:
            storage_path (Path): A path to an activities and sessions
                storage.
            config (ConfigT): An activities register configuration.
        """
        self._storage_path = storage_path
        self._config = config

    @property
    def path(self) -> Path:
        """Return the path to the activities register.

        Returns:
            Path: The path to the activities register.
        """
        return self._storage_path / self._config.path

    @abstractmethod
    def parents(self, *slugs: str) -> set[str]:
        """Return the parents of the given activities.

        Args:
            *slugs (str): Activity slugs.

        Returns:
            set[str]: A set of all direct parents of the given
                activities.
        """
        ...
