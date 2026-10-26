from pathlib import Path

from diane.app_session import AppSession
from diane.clock import Clock
from diane.config import Configurator
from diane.entry import Entry, EntryData, TimestampedEntry
from diane.listr import LiStr
from diane.repo import Repository
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
            repo (Repository): An initialised repository.

        Raises:
            RepositoryNotInitialisedError: If the repository has not
                been initialised.
            AssertionError: If the backend of an activities or entries
                register's configuration hasn't been recognised.
        """
        # Set up the clock and working repository.
        self._clock = Clock(app_session.config.timezone)
        self._repo = repo

        # Setup the user's data registers.
        self._activities_register = Configurator.activities_register(repo)
        # self.sessions_register = Configurator.sessions_register(repo)
        self._entries_register = Configurator.entries_register(repo)

    @property
    def path(self) -> Path:
        """Return the working repository's path.

        Returns:
            Path: Return the working repository's path.
        """
        return self._repo.path

    def write_entry(self, tags: LiStr, text: str) -> None:
        """Write a new entry.

        Args:
            tags (LiStr): Tags.
            text (str): A text.

        Raises:
            InvalidDefaultTimezoneError: If the configured time zone
                is invalid.
            LocalTimezoneDetectionError: If the local time zone
                could not be determined.
            DailyNoteNotFoundError: If a daily note could not be found,
                including a configured template.
            DailyNoteReadError: If a daily note could not be read.
            InvalidDailyNoteDataError: If a daily note has invalid
                format.
            InvalidISOFormatError: If an existing entry's `time` is not
                a valid ISO 8601 string.
            InvalidTimezoneError: If an existing entry's `timezone`
                is invalid or does not match the offset in `time`.
            ValidationError: If an existing entry's timestamp could not
                be validated.
            NonExistentTimeError: If an existing entry's local time
                does not exist in the specified IANA time zone.
            DateMatchError: If the new entry's local date does not match
                the date of its daily note.
            DailyNoteWriteError: If the daily note could not be written.
        """
        now = self._clock.now()
        entry = TimestampedEntry(now, Entry(EntryData(tags=tags, text=text)))
        self._entries_register.add(entry)
