from diane.app_session import AppSession
from diane.clock import Clock
from diane.config import Configurator
from diane.entry import Entry, EntryData, TimestampedEntry
from diane.listr import LiStr
from diane.repo import Repository, RepositoryAlreadyInitialisedError
from diane.storage import ActivitiesRegisterUnion, EntriesRegisterUnion


class Workspace:
    """A workspace for working with a repository.

    Attributes:
        _clock (Clock): A clock.
        _repo (Repository): A working repository.
        _activities_register (ActivitiesRegisterUnion): An activities
            register.
        _entries_register (EntriesRegisterUnion): An entries register.
    """

    _clock: Clock
    _repo: Repository
    _activities_register: ActivitiesRegisterUnion
    # _sessions_register: SessionsRegisterUnion
    _entries_register: EntriesRegisterUnion

    def __init__(self, app_session: AppSession, repo: Repository):
        """Create a new workspace for the given repository.

        Args:
            app_session (AppSession): The programme's session.
            repo (Repository): A repository.

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
        # Set up the clock.
        self._clock = Clock(app_session.config.timezone)

        # Set up the working repository.
        try:
            Configurator.initialise_repo(app_session, repo)
        except RepositoryAlreadyInitialisedError:
            pass
        self._repo = repo

        # Setup the user's data registers.
        self._activities_register = Configurator.activities_register(repo)
        # self.sessions_register = Configurator.sessions_register(repo)
        self._entries_register = Configurator.entries_register(repo)
