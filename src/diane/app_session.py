from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

from diane.repo import RepositoryConfig


class AppConfig(BaseSettings):
    """A programme configuration.

    Attributes:
        locale (str): A locale identifier in the IETF BCP 47 format.
        timezone (str | None): The default IANA time zone. Optional.
        repo_defaults (RepositoryConfig): A default repository
            configuration.
    """

    locale: str = "en-US"
    timezone: str | None = None
    repo_defaults: RepositoryConfig


class AppSession:
    """Represents a programme session.

    Holds parameters and a configuration required for the programme
    to function.

    Attributes:
        _app_dir (Path): The programme's directory.
        _working_dir (Path): A working directory.
        _config (AppConfig): A programme configuration.
    """

    _app_dir: Path
    _working_dir: Path
    _config: AppConfig

    def __init__(
        self, app_dir: Path, working_dir: Path, config: AppConfig
    ) -> None:
        """Create a new programme session.

        Args:
            app_dir (Path): The programme's directory.
            working_dir (Path): A working directory.
            config (AppConfig): A programme configuration.
        """
        self._app_dir = app_dir
        self._working_dir = working_dir
        self._config = config

    @property
    def app_dir(self) -> Path:
        """Return the programme's directory.

        Returns:
            Path: The programme's directory.
        """
        return self._app_dir

    @property
    def working_dir(self) -> Path:
        """Return the working directory.

        Returns:
            Path: The working directory.
        """
        return self._working_dir

    @property
    def config(self) -> AppConfig:
        """Return a copy of the programme's configuration.

        Returns:
            AppConfig: The programme's configuration.
        """
        return self._config.model_copy()
