from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

from diane.repo import RepositoryConfig


class AppSessionError(Exception):
    """A general programme session error."""
    pass


class AppNotInitialisedError(AppSessionError):
    """The programme has not been initialised."""
    pass


class AppAlreadyInitialisedError(AppSessionError):
    """The programme has already been initialised."""
    pass


class AppConfig(BaseSettings):
    """A programme configuration.

    Attributes:
        locale (str): A locale identifier in the IETF BCP 47 format.
        repo_defaults (RepositoryConfig): A default repository
            configuration.
    """
    locale: str = 'en-US'
    repo_defaults: RepositoryConfig


class AppSession:
    """Represents a programme session.

    Holds parameters and a configuration required for the programme
    to function.

    Attributes:
        _programme_dir (Path): The programme's directory.
        _working_dir (Path): A working directory.
        _config (AppConfig | None): A programme configuration.
    """

    _programme_dir: Path
    _working_dir: Path
    _config: AppConfig | None


    def __init__(self) -> None:
        """Create a new programme session."""
        self._programme_dir = Path(__file__).parent
        self._working_dir = Path.cwd()
        self._config = None

    def initialise(self, config: AppConfig) -> None:
        """Initialise the programme."""
        if self._config is not None:
            raise AppAlreadyInitialisedError()
        self._config = config

    @property
    def programme_dir(self) -> Path:
        """Return the programme's directory.

        Returns:
            Path: The programme's directory.
        """
        return self._programme_dir

    @property
    def working_dir(self) -> Path:
        """Return the working directory.

        Returns:
            Path: The working directory.
        """
        return self._working_dir

    @property
    def initialised(self) -> bool:
        """Check whether the programme has been initialised.

        Returns:
            bool: `True` if the programme has been initialised.
        """
        return self._config is not None

    @property
    def config(self) -> AppConfig:
        """Return a copy of the programme's configuration.

        Returns:
            AppConfig: The programme's configuration.
        """
        if self._config is None:
            raise AppNotInitialisedError()
        return self._config.model_copy()
