from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

from diane.storage import (
    MarkdownActivitiesRegisterConfig,
    MarkdownSessionsRegisterConfig,
)


class RepositoryError(Exception):
    """A general repository error."""
    ...


class NoRepositoryFoundError(RepositoryError):
    """No repository has been found."""
    ...


class RepositoryNotInitialisedError(RepositoryError):
    """A repository has not been initialised."""

    def __init__(self, repo_path: Path | None = None) -> None:
        super().__init__(
            f"The repository at '{repo_path}' has not been initialised."
            if repo_path
            else 'The repository has not been initialised.'
        )


class RepositoryAlreadyInitialisedError(RepositoryError):
    """A repository has already been initialised."""

    def __init__(self, repo_path: Path | None = None) -> None:
        super().__init__(
            f"The repository at '{repo_path}' has already been initialised."
            if repo_path
            else 'The repository has already been initialised.'
        )


class RepositoryConfig(BaseSettings):
    """A repository's configuration.

    Attributes:
        name (str): A repository's name.
        fallback_activity_emoji (str): The fallback activity's Unicode
            emoji. For example, '⚫'.
        activities_register (MarkdownActivitiesRegisterConfig):
            An activities register configuration.
        sessions_register (MarkdownSessionsRegisterConfig): A sessions
            register configuration.
    """

    name: str = 'Repository'
    fallback_activity_emoji: str = '⚫'
    activities_register: MarkdownActivitiesRegisterConfig
    sessions_register: MarkdownSessionsRegisterConfig


class Repository:
    """Represents a repository.

    This abstraction enables you to work with tracked data. There are
    two possible states for a repository: initialised
    or not initialised. A newly created repository is not initialised.
    Set the configuration to initialise.

    - Does not load a configuration. Use the `Configurator`
      to initialise a repository.
    - Does not handle user data (activities, sessions, etc.) directly.
      This is the responsibility of the `StorageEngine`.

    Attributes:
        _path (Path): A path to a repository in the file system.
        _config (RepositoryConfig | None): A repository configuration.

    Args:
        path (Path | str): A path to a repository in the file system.
    """

    # Contains a repository's metadata.
    _diane_subdir: Path = Path('.diane')

    _path: Path
    _config: RepositoryConfig | None

    def __init__(self, path: Path | str) -> None:
        """Create a repository."""
        self._path = Path(path)
        self._config = None

    def initialise(self, config: RepositoryConfig) -> None:
        """Initialise the repository.

        Initialises the repository with a supplied configuration.

        Args:
           config (RepositoryConfig): A configuration to apply.

        Raises:
            RepositoryAlreadyInitialisedError: The repository has
                already been initialised.
        """
        if self._config is not None:
            raise RepositoryAlreadyInitialisedError()
        self._config = config

    @property
    def diane_dir(self) -> Path:
        """Return the Diane directory of the repository.

        This directory contains the repository's metadata.

        Returns:
            Path: The repository's Diane directory.
        """
        return self.path / self._diane_subdir

    @property
    def path(self) -> Path:
        """Return the path to the repository in the file system.

        Returns:
            Path: The path to the repository.
        """
        return self._path

    @property
    def initialised(self) -> bool:
        """Check whether the repository has been initialised.

        Returns:
            bool: `True` if the repository has been initialised.
        """
        return self._config is not None

    @property
    def config(self) -> RepositoryConfig:
        """Return a copy of the current repository configuration.

        Returns:
            RepositoryConfig: A copy of the current repository
                configuration.

        Raises:
            RepositoryNotInitialisedError: If the repository has not
                been initialised.
        """
        if self._config is None:
            raise RepositoryNotInitialisedError(self.path)
        return self._config.model_copy()
