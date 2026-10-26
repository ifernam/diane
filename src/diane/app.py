from diane.app_session import AppSession
from diane.config import Configurator
from diane.listr import LiStr
from diane.repo import Repository
from diane.repo_manager import RecentRepoItem, RepoManager
from diane.workspace import Workspace


class AppError(Exception):
    """A general app error."""

    ...


class WorkspaceAlreadyCreatedError(AppError):
    """A workspace has already been created for the specified
    repository."""

    ...


class NoWorkspaceSpecifiedError(AppError):
    """No workspace has been specified."""

    ...


class App:
    """Represents the programme.

    Attributes:
        _app_session (AppSession): Holds parameters and a configuration
            required for the programme to function.
        _workspace (list[Workspace]): The list of current workspaces.
    """

    _app_session: AppSession
    _workspace: list[Workspace]

    def __init__(self) -> None:
        """Initialise the programme."""
        self._app_session = Configurator.configure_app()
        self._workspace = []

    def recent_repos(self) -> list[RecentRepoItem]:
        """Return recently used repositories, attempting to configure
        each one.

        A repository that cannot be found or configured is still
        included in the result; its error is stored in the corresponding
        `RecentRepoItem.error` field. Successfully configured
        repositories have `error` set to `None`.

        Returns:
            list[RecentRepoItem]: Recently used repositories.

        Raises:
            RecentReposParseError: If the TOML content in the cache file
                is invalid.
            RecentReposIOError: If the cache file could not be read.
            InvalidRecentReposError: If data in the file does not match
                the schema.
        """
        return RepoManager.recent(self._app_session)

    @property
    def workspaces(self) -> list[Workspace]:
        """Return current workspaces.

        Returns:
            list[Workspace]: Current workspaces.
        """
        return self._workspace.copy()

    def create_workspace(self, repo: Repository) -> Workspace:
        """Create a new workspace for working with the given repository
        add it to the list of current workspaces.

        Args:
            repo (Repository): A repository.

        Returns:
            Workspace: A workspace for the repository.

        Raises:
            WorkspaceAlreadyCreatedError: If a workspace has already
                been created for the given repository.
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
            AssertionError: If the backend of an activities or entries
                register's configuration hasn't been recognised.
        """
        if any(w.path == repo.path for w in self._workspace):
            raise WorkspaceAlreadyCreatedError(
                "A workspace has already been created "
                f"for the '{repo.path}' repository."
            )

        RepoManager.configure(self._app_session, repo)
        workspace = Workspace(self._app_session, repo)
        self._workspace.append(workspace)
        return workspace

    def write_entry(
        self, tags: LiStr, text: str, *workspaces: Workspace
    ) -> None:
        """Write a new entry in the specified workspaces.

        Args:
            tags (LiStr): Tags.
            text (str): A text.
            *workspaces (Workspace): Workspaces for writing.

        Raises:
            NoWorkspaceSpecifiedError: If no workspaces are provided.
            ExceptionGroup: If one or more workspace writes fail.
                The group contains the exceptions raised by those
                writes; successful writes are not rolled back.
                The contained exceptions may include:
                - `InvalidDefaultTimezoneError`: if the configured time
                  zone is invalid;
                - `LocalTimezoneDetectionError`: if the local time zone
                  could not be determined;
                - `DailyNoteNotFoundError`: if a daily note could not
                  be found, including a configured template;
                - `DailyNoteReadError`: if a daily note could not
                  be read;
                - `InvalidDailyNoteDataError`: if a daily note has
                  invalid format;
                - `InvalidISOFormatError`: if an existing entry's `time`
                  is not a valid ISO 8601 string;
                - `InvalidTimezoneError`: if an existing entry's
                  `timezone` is invalid or does not match the offset
                  in `time`;
                - `ValidationError`: if an existing entry's timestamp
                  could not be validated;
                - `NonExistentTimeError`: if an existing entry's local
                  time does not exist in the specified IANA time zone;
                - `DateMatchError`: if the new entry's local date
                  does not match the date of its daily note;
                - `DailyNoteWriteError`: if the daily note could not
                  be written.
        """
        if not workspaces:
            raise NoWorkspaceSpecifiedError("No workspace has been specified.")

        errors: list[Exception] = []

        for w in workspaces:
            try:
                w.write_entry(tags, text)
            except Exception as exc:
                exc.add_note(f"Workspace: '{w.path}'.")
                errors.append(exc)

        if errors:
            raise ExceptionGroup(
                "Failed to write the entry in one or more workspaces.", errors
            )
