from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class RepositoryError(Exception):
    """A general repository error."""


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
        activities_subdir (Path): A subdirectory within a repository's
            directory where activity notes are stored. For example,
            'diane_activities'.
        default_activity_emoji (str): The default activity's Unicode
            emoji. For example, '⚫'.
        daily_notes_subdir (Path): A subdirectory within a repository's
            directory where daily notes are stored. For example,
            'daily_notes'.
        daily_note_title_format (str): A daily note's title `strftime`
            format. For example, '%Y-%m-%d'.
        daily_note_template_path (Path | None): An optional relative
            path to a daily note's template in a repository.
            For example, 'templates/daily_note_template'.
    """
    name: str

    activities_subdir: Path
    default_activity_emoji: str

    daily_notes_subdir: Path
    daily_note_title_format: str
    daily_note_template_path: Path | None


class Repository:
    """Represents a repository.

    This abstraction enables you to work with tracked data. There are
    two possible states for a repository: initialised
    or not initialised. A newly created repository is not initialised.
    Set the configuration to initialise.

    - Does not load a configuration. Use the `ConfigurationManager`
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

        Initialises the repository with the supplied configuration.

        Args:
           config (RepositoryConfig): The given configuration to set.
        """
        if self._config is not None:
            raise RepositoryAlreadyInitialisedError()
        self._config = config

    @property
    def diane_subdir(self) -> Path:
        """Return a Diane directory of the repository.

        This directory contains the repository's metadata.

        Returns:
            Path: The repository's Diane directory.
        """
        return self.path / self._diane_subdir

    @property
    def path(self) -> Path:
        """Return a path to the repository in the file system.

        Returns:
            Path: A path to the repository.
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
        """Return a copy of the current repository's configuration.

        Returns:
            RepositoryConfig: A copy of the current repository's
            configuration.
        """
        if self._config is None:
            raise RepositoryNotInitialisedError(self.path)
        return self._config.model_copy()
