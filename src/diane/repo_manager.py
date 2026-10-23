import tomllib
from pathlib import Path

import tomlkit
from pydantic import BaseModel, ValidationError

from diane.app_session import AppSession
from diane.config import Configurator
from diane.repo import Repository


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
        paths = [
            recent_repo.path
            for recent_repo in cls.recent(app_session)
            if recent_repo.path != repo.path
        ]
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
        paths = [
            recent_repo.path
            for recent_repo in cls.recent(app_session)
            if recent_repo.path != repo.path
        ]

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
    def recent(cls, app_session: AppSession) -> list[Repository]:
        """Return recently used repositories.

        Repositories are not initialised.

        Args:
            app_session (AppSession): A programme session providing
                the path to the cache file.

        Returns:
            list[Repository]: Recently used repositories.

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

        repos: list[Repository] = []
        for path in cache.paths:
            repo = Repository(path)
            repos.append(repo)

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
