import tomllib
from pathlib import Path
from typing import NamedTuple

import tomlkit
from pydantic import BaseModel, ValidationError

from diane.app_session import AppSession
from diane.config import (
    ConfigurationIOError,
    ConfigurationParseError,
    Configurator,
    InvalidConfigurationError,
)
from diane.repo import NoRepositoryFoundError, Repository


class RepoManagerError(Exception):
    """A general repository manager error."""

    ...


class RecentReposParseError(RepoManagerError):
    """An error occurred while parsing a cache file with recent
    repositories."""

    ...


class RecentReposIOError(RepoManagerError):
    """An I/O error occurred while reading a cache file with recent
    repositories."""

    ...


class InvalidRecentReposError(RepoManagerError):
    """An invalid cache file."""

    ...


class RecentReposCache(BaseModel):
    paths: list[Path]


class RecentRepoItem(NamedTuple):
    repo: Repository
    error: Exception | None


class RepoManager:
    @classmethod
    def _cache(cls, app_session: AppSession, repo: Repository) -> None:
        """Add a repository path to the recent-repositories cache.

        The most recently cached repository is placed first. If the
        repository is already in the cache, its previous entry is moved
        to the front.

        Raises:
            RecentReposParseError: If the TOML content in the cache file
                is invalid.
            RecentReposIOError: If the cache file could not be read or
                written.
            InvalidRecentReposError: If data in the file does not match
                the schema.
        """
        cache_path = app_session.app_dir / "cache" / "recent_repos.toml"
        paths = [p for p in cls._recent_paths(app_session) if p != repo.path]
        paths.insert(0, repo.path)

        cache = RecentReposCache(paths=paths)
        content = tomlkit.dumps(cache.model_dump(mode="json"))

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            _ = cache_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise RecentReposIOError(
                f"Failed to write the cache file '{cache_path}'. {exc}"
            ) from exc

    @classmethod
    def _uncache(cls, app_session: AppSession, repo: Repository) -> None:
        """Remove a repository path from the recent-repositories cache.

        All occurrences of the repository path are removed.

        Raises:
            RecentReposParseError: If the TOML content in the cache file
                is invalid.
            RecentReposIOError: If the cache file could not be read
                or written.
            InvalidRecentReposError: If data in the file does not match
                the schema.
        """
        cache_path = app_session.app_dir / "cache" / "recent_repos.toml"
        paths = [p for p in cls._recent_paths(app_session) if p != repo.path]

        cache = RecentReposCache(paths=paths)
        content = tomlkit.dumps(cache.model_dump(mode="json"))

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            _ = cache_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise RecentReposIOError(
                f"Failed to write the cache file '{cache_path}'. {exc}"
            ) from exc

    @classmethod
    def _clear_cache(cls, app_session: AppSession) -> None:
        """Remove all repository paths from the recent-repositories
        cache.

        Create the cache file with an empty list if it does not exist.

        Raises:
            RecentReposIOError: If the cache file could not be written.
        """
        cache_path = app_session.app_dir / "cache" / "recent_repos.toml"
        cache = RecentReposCache(paths=[])
        content = tomlkit.dumps(cache.model_dump(mode="json"))

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            _ = cache_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise RecentReposIOError(
                f"Failed to write the cache file '{cache_path}'. {exc}"
            ) from exc

    @classmethod
    def _recent_paths(cls, app_session: AppSession) -> list[Path]:
        """Return recently used repository paths.

        Args:
            app_session (AppSession): A programme session providing
                the path to the cache file.

        Returns:
            list[Path]: Recently used repository path.

        Raises:
            RecentReposParseError: If the TOML content in the cache file
                is invalid.
            RecentReposIOError: If the cache file could not be read.
            InvalidRecentReposError: If data in the file does not match
                the schema.
        """
        cache_path = app_session.app_dir / "cache" / "recent_repos.toml"
        try:
            content = cache_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise RecentReposIOError(
                f"Failed to read the cache file '{cache_path}'. {exc}"
            ) from exc

        try:
            cache = RecentReposCache.model_validate(tomllib.loads(content))
        except tomllib.TOMLDecodeError as exc:
            raise RecentReposParseError(
                f"The TOML syntax in the '{cache_path}' file is invalid. {exc}"
            ) from exc
        except ValidationError as exc:
            raise InvalidRecentReposError(
                f"The cache file '{cache_path}' is invalid. {exc}"
            ) from exc

        return cache.paths

    @classmethod
    def recent(cls, app_session: AppSession) -> list[RecentRepoItem]:
        """Return recently used repositories, attempting to configure
        each one.

        A repository that cannot be found or configured is still
        included in the result; its error is stored in the corresponding
        `RecentRepoItem.error` field. Successfully configured
        repositories have `error` set to `None`.

        Args:
            app_session (AppSession): A programme session providing
                the path to the cache file.

        Returns:
            list[RecentRepoItem]: Recently used repositories.

        Raises:
            RecentReposParseError: If the TOML content in the cache file
                is invalid.
            RecentReposIOError: If the cache file could not be read.
            InvalidRecentReposError: If data in the file does not match
                the schema.
        """
        repos: list[RecentRepoItem] = []
        for p in cls._recent_paths(app_session):
            repo = Repository(p)
            error = None
            try:
                Configurator.configure_repo(app_session, repo)
            except (
                NoRepositoryFoundError,
                ConfigurationParseError,
                ConfigurationIOError,
                InvalidConfigurationError,
            ) as exc:
                error = exc
            repos.append(RecentRepoItem(repo, error))

        return repos

    @classmethod
    def configure(cls, app_session: AppSession, repo: Repository) -> None:
        """Configure a repository and add it to the recent-repositories
        cache.

        Load and apply the repository configuration using
        the programme's defaults, then move the repository to the front
        of the recent-repositories cache.

        Args:
            app_session (AppSession): The programme session providing
                the default repository configuration and cache location.
            repo (Repository): A repository to configure.

        Raises:
            NoRepositoryFoundError: If a repository's Diane directory
                does not exist.
            ConfigurationParseError: If a repository configuration file
                contains invalid TOML.
            ConfigurationIOError: If a repository configuration file
                cannot be read.
            InvalidConfigurationError: If the merged configuration
                does not match the repository configuration schema.
            RecentReposParseError: If the TOML content
                in the recent-repositories cache is invalid.
            RecentReposIOError: If the cache file cannot be read
                or written.
            InvalidRecentReposError: If data in the cache file does not
                match its schema.
        """
        Configurator.configure_repo(app_session, repo)
        cls._cache(app_session, repo)

    @classmethod
    def create(cls, app_session: AppSession, repo: Repository):
        raise NotImplementedError

    @classmethod
    def delete(cls, app_session: AppSession, repo: Repository):
        raise NotImplementedError
