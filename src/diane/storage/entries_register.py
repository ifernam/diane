from abc import ABC
from collections.abc import MutableMapping
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from diane.chrono import Timestamp
from diane.entry import Entry


class EntriesRegisterError(Exception):
    """A general entries register error."""
    ...


class NotRelativePathError(EntriesRegisterError, ValueError):
    """A path is not relative.

    For Pydantic's validation.
    """
    ...


class EntriesRegisterConfig(BaseModel):
    """An entries register configuration.

    Attributes:
        path (Path): A relative path where entries are stored.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

    path: Path

    @field_validator('path')
    @classmethod
    def _check_relative(cls, v: Path) -> Path:
        """Validate a path.

        Args:
            v (Path): A path to an entries register.

        Returns:
            Path: The validated path.

        Raises:
            NotRelativePathError: If a path is not relative.
        """
        if v.is_absolute():
            raise NotRelativePathError(f"'path' must be relative, got '{v}'.")
        return v


class EntriesRegister[ConfigT: EntriesRegisterConfig](
    MutableMapping[Timestamp, list[Entry]], ABC
):
    """Represents an entries register.

    This abstraction enables user's text entries stored on disk
    to be worked with.

    Attributes:
        _storage_path (Path): A path to the user's data storage.
        _config (ConfigT): An entries register configuration.
    """

    _storage_path: Path
    _config: ConfigT

    def __init__(self, storage_path: Path, config: ConfigT) -> None:
        """Create a new entries register representation.

        Args:
            storage_path (Path): A path to the user's data storage.
            config (ConfigT): An entries register configuration.
        """
        self._storage_path = storage_path
        self._config = config

    @property
    def path(self) -> Path:
        """Return the path to the entries register.

        Returns:
            Path: The path to the entries register.
        """
        return self._storage_path / self._config.path
