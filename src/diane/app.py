from diane.app_session import AppSession
from diane.config import Configurator
from diane.repo import Repository
from diane.repo_manager import RecentRepoItem, RepoManager
from diane.workspace import Workspace


class AppError(Exception):
    """A general app error."""

    ...


class WorkspaceAlreadyCreated(AppError):
    """A workspace has already been created for the specified
    repository."""

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

    def workspace(self, repo: Repository) -> Workspace:
        """Create a new workspace for working with the given repository
        add it to the list of current workspaces.

        Args:
            repo (Repository): A repository.

        Returns:
            Workspace: A workspace for the repository.

        Raises:
            WorkspaceAlreadyCreated: If a workspace has already been
                created for the given repository.
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
            raise WorkspaceAlreadyCreated(
                "A workspace has already been created "
                f"for the '{repo.path}' repository."
            )

        RepoManager.configure(self._app_session, repo)
        workspace = Workspace(self._app_session, repo)
        self._workspace.append(workspace)
        return workspace
