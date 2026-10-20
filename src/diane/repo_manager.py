import tomllib
from pathlib import Path

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
        raise NotImplementedError

    @classmethod
    def _uncache(cls, app_session: AppSession, repo: Repository) -> None:
        raise NotImplementedError

    @classmethod
    def _clear_cache(cls, app_session: AppSession) -> None:
        raise NotImplementedError

    @classmethod
    def _update_cache(cls, app_session: AppSession) -> None:
        raise NotImplementedError

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
        cache_path = app_session.programme_dir / "cache" / "recent_repos.toml"
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
                f"The TOML syntax in the '{cache_path}' file is invalid. "
                f"{exc}"
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
    def last(cls):
        raise NotImplementedError

    @classmethod
    def initialise(cls, app_session: AppSession, repo: Repository) -> None:
        Configurator.initialise_repo(app_session, repo)
        cls._cache(app_session, repo)

    @classmethod
    def create(cls, app_session: AppSession, repo: Repository):
        raise NotImplementedError

    @classmethod
    def delete(cls, app_session: AppSession, repo: Repository):
        raise NotImplementedError
