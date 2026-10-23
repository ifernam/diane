from diane.app_session import AppSession
from diane.config import Configurator
from diane.repo import Repository
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
            NoRepositoryFoundError: If no repository has been found.
                The presence of a Diane subdirectory indicates
                the existence of a repository.
            ConfigurationParseError: If a repository configuration TOML
                file contains invalid syntax.
            ConfigurationIOError: If a repository configuration file
                could not be read.
            InvalidConfigurationError: If a merged configuration
                does not match the `RepositoryConfig` schema.
            AssertionError: If the backend of an activities or entries
                register's configuration hasn't been recognised.
        """
        return Workspace(self.app_session, repo)
