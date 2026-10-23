from diane.app_session import AppSession
from diane.config import Configurator
from diane.repo import Repository
from diane.repo_manager import RepoManager
from diane.workspace import Workspace


class App:
    """Represents the programme.

    Attributes:
        app_session (AppSession): Holds parameters and a configuration
            required for the programme to function.
    """

    app_session: AppSession

    def __init__(self) -> None:
        """Initialise the programme."""
        self.app_session = Configurator.configure_app()

    def workspace(self, repo: Repository) -> Workspace:
        """Create a new workspace for working with the given repository.

        Args:
            repo (Repository): A repository.

        Returns:
            Workspace: A workspace for the repository.

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
            AssertionError: If the backend of an activities or entries
                register's configuration hasn't been recognised.
        """
        RepoManager.configure(self.app_session, repo)
        return Workspace(self.app_session, repo)
