from __future__ import annotations

from operator import itemgetter
from pathlib import Path
import yaml
import warnings
import re
import datetime
from collections import defaultdict, namedtuple
from collections.abc import Collection
from itertools import chain

from diane.temporal import Timestamp, TimeInterval, TimeSet
from diane.activities import Activity, Activities
from diane.sessions import Session
from diane.repository import UnknownActivityError
from diane.assisted_repository import AssistedRepository, AssistedRepositoryError



class RepositoryManagerError(AssistedRepositoryError):
    """The base exception for all assisted repository manager errors."""
    pass



class ActivityReadError(RepositoryManagerError):
    """An error occurred while reading activity data."""



class ActivityReadFromMarkdownNoteError(RepositoryManagerError):
    """An error occurred while reading activity data from a Markdown
    activity note."""



class ActivitiesReadFromYAMLError(RepositoryManagerError):
    """An error occurred while reading activities data from a YAML file."""



class NoActivitiesProvided(RepositoryManagerError):
    """No activities have been provided."""
    pass



class ActivityAlreadyTracked(RepositoryManagerError):
    """Some of the provided activities are already being tracked.

    Args:
        provided_activities (Collection[Activity]): The collection
            of provided activities.
        already_tracked_data (dict[Activity, Timestamp]): The dictionary
            of already tracked activities with their start timestamps.
        message (str | None): The exception message. If it remains
            to `None`, it will be generated automatically.

    Attributes:
        message (str): The exception message.
        provided_activities (list[Activity]): The list of provided
            activities sorted by their slugs.
        already_tracked_data (dict[Activity, Timestamp]): The dictionary
            of already tracked activities with their start timestamps.
            Sorted by start timestamps.
    """
    
    message: str
    provided_activities: list[Activity]
    already_tracked_data: dict[Activity, Timestamp]

    
    def __init__(
        self,
        provided_activities: Collection[Activity],
        already_tracked_data: dict[Activity, Timestamp],
        message: str | None = None
    ) -> None:

        # Sort provided activities.
        self.provided_activities = sorted(provided_activities)

        # Sort already tracked data.
        self.already_tracked_data = dict(sorted(
            already_tracked_data.items(), key=itemgetter(1)
        ))

        # Set message.
        if message is None:
            if self.already_tracked_data:
                preamble = (
                    'Some of the provided activities are already being '
                    'tracked: '
                )
                quoted_slugs = ', '.join(
                    f'\'{a.slug}\'' for a in self.already_tracked_data
                )
                ending = '.'
                message = f'{preamble}{quoted_slugs}{ending}'
        self.message = message

        super().__init__(message)


    def __str__(self) -> str:
        return self.message


    @property
    def new_activities(self) -> list[Activity]:
        """Return the list of provided activities that are not already
        being tracked.

        Returns:
            list[Activity]: The list of provided activities that are not
            already being tracked, sorted by their slugs.
        """

        return [
            a for a in self.provided_activities
            if a not in self.already_tracked_data
        ]



class AncestorActivities(RepositoryManagerError):
    """Some of the provided activities are ancestors of the other
    provided ones.

    Args:
        provided_activities (Collection[Activity]): The collection of
            provided activities.
        ancestors_data (dict[Activity, set[Activity]]): The dictionary
            mapping each ancestor activity to the set of its descendant
            activities among the provided ones.
        message (str | None): The exception message. If it remains
            to `None`, it will be generated automatically.

    Attributes:
        message (str): The exception message.
        provided_activities (list[Activity]): The list of provided
            activities sorted by their slugs.
        ancestor_to_descendants (dict[Activity, set[Activity]]):
            The dictionary mapping each ancestor activity to the set
            of its descendant activities among the provided ones. Sorted
            by ancestor slug and then by descendant slug.
    """
    
    message: str
    provided_activities: list[Activity]
    ancestor_to_descendants: dict[Activity, set[Activity]]

    def __init__(
        self,
        provided_activities: Collection[Activity],
        ancestors_data: dict[Activity, set[Activity]],
        message: str | None = None

    ) -> None:

        # Set message.
        self.message = (
            message
            if message is not None
            else 'Some of provided activities are ancestors of others.'
        )

        # Set provided activities sorted by slug.
        self.provided_activities = sorted(provided_activities)

        # Set ancestor to activity mapping sorted by ancestor slug
        # and then by descendant slug.
        self.ancestor_to_descendants = dict(sorted(ancestors_data.items()))

        super().__init__(message)


    def __str__(self) -> str:
        return self.message



class AncestorActivitiesTracked(RepositoryManagerError):
    """Some of provided activities are ancestors or descendants
    of activities that are already being tracked.

    Attributes:
        message (str): The exception message.
        provided_activities (list[Activity]): The list of provided
            activities sorted by slug.
        ancestor_to_descendants (dict[Activity, set[Activity]]):
            The dictionary mapping each provided ancestor activity
            to the set of its descendant activities that have already
            been tracked. Sorted by ancestor slug.
        descendant_to_ancestors (dict[Activity, set[Activity]]):
            The dictionary mapping each provided descendant activity
            to the set of its ancestor activities that have already
            been tracked. Sorted by descendant slug.

    Args:
        provided_activities (Collection[Activity]): The collection
            of provided activities.
        ancestor_to_descendants (dict[Activity, set[Activity]]):
            The dictionary mapping each provided ancestor activity
            to the set of its descendant activities that have already
            been tracked.
        descendant_to_ancestors (dict[Activity, set[Activity]]):
            The dictionary mapping each provided descendant activity
            to the set of its ancestor activities that have already
            been tracked.
        message (str | None): The exception message. If it remains
            to `None`, it will be generated automatically.
    """

    message: str
    provided_activities: list[Activity]
    ancestor_to_descendants: dict[Activity, set[Activity]]
    descendant_to_ancestors: dict[Activity, set[Activity]]


    def __init__(
        self,
        provided_activities: Collection[Activity],
        ancestor_to_descendants: dict[Activity, set[Activity]],
        descendant_to_ancestors: dict[Activity, set[Activity]],
        message: str | None = None
    ) -> None:

        # Set message.
        self.message = (
            message if message is not None
            else (
                'Some of provided activities are ancestors or descendants '
                'of activities that are already being tracked.'
            )
        )

        # Set provided activities sorted by slug.
        self.provided_activities = sorted(provided_activities)

        # Set ancestor to descendant mapping.
        self.ancestor_to_descendants = dict(sorted(
            ancestor_to_descendants.items())
        )

        # Set descendant to ancestor mapping.
        self.descendant_to_ancestors = dict(sorted(
            descendant_to_ancestors.items())
        )

        super().__init__(message)


    def __str__(self) -> str:
        return self.message



class RepositoryManager(AssistedRepository):
    """Represents the repository manager.
    
    This is a wrapper around the `AssistedRepository` that allows
    to manage a repository, i.e., to perform operations such as:
    - creating new sessions,
    - loading and saving repository data from/to disk.
    """

    _datadir: Path  # The repository directory.
    _tracking_state: dict[Activity, Timestamp]


    # Configuration for the repository manager.
    _activities_subdir: str = 'diane_activities'
    _daily_notes_subdir: str = 'daily_notes'
    _daily_note_title_format: str = '%Y-%m-%d'
    # TODO: Load from config file.

    _dirty_days: set[datetime.date]  # Days to update.
    _loading: bool
    

    def _link_activity(self, activity_slug: str) -> str:
        """Return the link in the format
        '[[<activity_subdir>/<activity_slug>]]' for the given activity
        slug to save in YAML.
        
        Args:
            activity_slug (str): The slug of the activity.

        Returns:
            str: The link in the format
            '[[<activity_subdir>/<activity_slug>]]'.
        """

        return f'[[{self._activities_subdir}/{activity_slug}]]'


    def _unlink_activity(self, link: str) -> str:
        """Return the activity slug for the given activity link.
        
        Args:
            link (str): The activity link in the format
            '[[<activity_subdir>/<activity_slug>]]'.

        Returns:
            str: The activity slug.

        Raises:
            ValueError: If the link format is invalid.
        """

        pattern = rf'\[\[{self._activities_subdir}/([^\]]+)\]\]'
        match = re.search(pattern, link)
        if match:
            return match.group(1)
        else:
            raise ValueError(f'Invalid activity link: \'{link}\'.')



    ActivityNoteEntry = namedtuple('ActivityNoteEntry', ['slug', 'path'])



    def _activity_notes_list(self) -> list[ActivityNoteEntry]:
        """Return a list of all activity notes in the corresponding
        subdirectory.

        Returns:
            list[ActivityNoteEntry]: A list of all activity notes
            in the repository sorted by slug.
        """

        # Determine activity notes path.
        activities_path = self._datadir / self._activities_subdir
        activity_notes = []

        for file_path in chain(
            activities_path.glob('*.md'),
            activities_path.glob('*.markdown')
        ):
            if file_path.is_file():
                slug = file_path.stem
                activity_notes.append(
                    self.ActivityNoteEntry(slug=slug, path=file_path)
                )

        return sorted(activity_notes, key=lambda n: n.slug)



    DailyNoteEntry = namedtuple('DailyNoteEntry', ['date', 'path'])



    def _daily_notes_list(self) -> list[DailyNoteEntry]:
        """Return a list of all daily notes in the corresponding
        subdirectory.

        Returns:
            list[DailyNoteEntry]: A list of all daily notes
            in the repository sorted by date.
        """

        # Determine daily notes path.
        sessions_path = self._datadir / self._daily_notes_subdir
        daily_notes = []

        for file_path in chain(
            sessions_path.glob('*.md'),
            sessions_path.glob('*.markdown')
        ):
            if file_path.is_file():
                date_str = file_path.stem
                try:
                    date = datetime.datetime.strptime(
                        date_str, self._daily_note_title_format
                    ).date()
                except ValueError:
                    continue
                daily_notes.append(
                    self.DailyNoteEntry(date=date, path=file_path)
                )

        return sorted(daily_notes, key=lambda n: n.date)


    def _read_sessions_from_daily_note(
        self, daily_note_entry: DailyNoteEntry
    ) -> list[Session]:

        try:
            with daily_note_entry.path.open('r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError as e:
            # TODO: log 'File not found: \'{daily_note_entry.path}\'.'
            return []
        except PermissionError as e:
            # TODO: log 'Permission denied:
            # TODO \'{daily_note_entry.path}\'.'
            return []
        except UnicodeDecodeError as e:
            # TODO: log 'The file is not valid UTF-8:
            # TODO: \'{daily_note_entry.path}\'.'
            return []
        except OSError as e:
            # TODO: log 'Input-output error:
            # TODO: \'{daily_note_entry.path}\'.'
            return []

        yaml_front_matter_pattern = re.compile(
            r'(?m)^\s*---\s*$\n(.*?)\n^\s*---\s*$',
            re.DOTALL
        )

        def unlink_activities(session_data: dict) -> dict:
            aa = session_data.get('activities')
            if not isinstance(aa, list):
                raise ValueError("The 'activities' field must be a list.")
            session_data['activities'] = [
                self._unlink_activity(a) for a in aa
            ]
            return session_data

        sessions = []
        for match in yaml_front_matter_pattern.finditer(content):
            yaml_block = match.group(1).strip()
            if not yaml_block:
                continue

            try:
                data = yaml.safe_load(yaml_block)
            except yaml.YAMLError:
                continue

            if not isinstance(data, dict):
                continue

            sessions_data = data.get('diane_sessions')
            if not isinstance(sessions_data, list):
                continue

            for session_dict in sessions_data:
                if not isinstance(session_dict, dict):
                    continue
                try:
                    session = self.session_from_dict(
                        unlink_activities(session_dict),
                        daily_note_entry.date.isoformat()
                    )
                    sessions.append(session)
                except Exception as e:
                    # TODO: log 'Error adding session from
                    # TODO: \'{daily_note_entry.path}\'. {e}',
                    continue

        return sorted(sessions, key=lambda s: s.timeset.start)


    def _load_sessions(
        self,
        first_day: datetime.date | None = None,
        last_day: datetime.date | None = None,
        merge: bool = True
    ) -> None:
        """Load sessions from the repository directory.

        Args:
            first_day (datetime.datetime | None): The first day to load
                sessions from. If `None`, the first day is the earliest
                day with sessions.
            last_day (datetime.datetime | None): The last day to load
                sessions for. If `None`, the last day is the latest
                day with sessions.
            merge (bool): If `True`, merge touching sessions. `True`
                by default.

        Raises:
            RuntimeError: If the repository is not in a loading state.
        """

        if not self._loading:
            raise RuntimeError(
                'Cannot load sessions while not in loading state.'
            )

        # Load sessions from the `first_day` to the `last_day`.
        daily_notes_list = self._daily_notes_list()
        for daily_note_entry in daily_notes_list:
            if first_day and daily_note_entry.date < first_day:
                continue
            if last_day and daily_note_entry.date > last_day:
                break
            new_sessions = self._read_sessions_from_daily_note(
                daily_note_entry
            )
            for s in new_sessions:
                self.add(s)

        # Merge touching sessions if requested.
        if merge:
            self._merge_touching()


    def __init__(
        self,
        repo_dir: Path | str,
        load_sessions: bool = True,
        first_day: datetime.date | None = None,
        last_day: datetime.date | None = None
    ) -> None:
        """Load the repository data from the given directory.

        Args:
            repo_dir (str): The directory of the repository.
            load_sessions (bool): If `True`, load sessions from
                the repository. `True` by default.
            first_day (datetime.date | None): The first day to load
                sessions from. If `None`, the first day is the earliest
                day with sessions. Only taken into account
                if `load_sessions` is `True`.
            last_day (datetime.date | None): The last day to load
                sessions for. If `None`, the last day is the latest day
                with sessions. Only taken into account
                if `load_sessions` is `True`.

        Raises:
            `ValueError`: If the repository data is invalid or cannot
                be loaded.

        Warns:
            `UserWarning`: If any session or activity cannot be loaded.
        """

        # Set loading state to `True`.
        self._loading = True

        # Set repository directory.
        self._datadir = (
            repo_dir if isinstance(repo_dir, Path) else Path(repo_dir)
        )

        # Load activities.
        super().__init__()
        self._load_activities()
        '''activities_path = self._datadir / '.diane/data/activities.yaml'
        activities = Activities.from_yaml(activities_path)
        super().__init__(_activities=activities)'''

        # Update tracking activities.
        self._load_state()

        # No days to update.
        self._dirty_days = set()

        # Load sessions.
        if load_sessions:
            self._load_sessions(first_day=first_day, last_day=last_day)

        self._rebuild_index()
        self._validate()

        # Set loading state to `False`.
        self._loading = False


    @property
    def tracking_state(self) -> dict[Activity, Timestamp]:
        """Return the current tracking state.

        Returns:
            `dict[Activity, Timestamp]`: A copy of the current tracking
            state. Contains activities with tracking start timestamps.
        """

        return self._tracking_state.copy()


    @staticmethod
    def read_activities_from_yaml(path: str | Path) -> Activities:
        """Construct an activities registry from a YAML file.

        The YAML file must contain a top-level mapping with
        an 'activities' key, whose value is a dictionary mapping slugs
        to activity data.

        Args:
            path (str | Path): Path to the YAML file.

        Returns:
            Activities: A new activities registry.
        """

        try:
            path = path if isinstance(path, Path) else Path(path)
            with path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    raise ValueError('YAML root must be a mapping.')
                try:
                    activities_data = data.get('activities')
                except AttributeError:
                    raise ValueError(
                        "Activities data not found in YAML file. "
                        "The file should contain an 'activities' key."
                    )
                if not isinstance(activities_data, dict):
                    raise ValueError("Activities data must be a mapping.")
                return Activities.from_dict(activities_data)
        except FileNotFoundError as e:
            raise ActivitiesReadFromYAMLError(
                f"The activities file '{path}' not found."
            ) from e
        except PermissionError as e:
            raise ActivitiesReadFromYAMLError(
                f"Permission to read the activities file '{path}' denied. {e}"
            ) from e
        except UnicodeDecodeError as e:
            raise ActivitiesReadFromYAMLError(
                f"Unicode decode error while reading activities file "
                f"'{path}'. {e}"
            ) from e
        except OSError as e:
            raise ActivitiesReadFromYAMLError(
                f"Input-output error while reading activities file '{path}'."
                f" {e}"
            ) from e
        except yaml.YAMLError as e:
            raise ActivitiesReadFromYAMLError(
                f"Invalid YAML file '{path}': {e}."
            ) from e


    def _read_activity_from_markdown_note(
        self,
        path: Path | str
    ) -> tuple[Activity, list[str]]:
        """Read an activity from a Markdown note.

        Args:
            path (Path | str): The path to the Markdown note.

        Returns:
            tuple[Activity, list[str]]: The read activity
                and its parents.
        """

        # Normalise the path.
        path = path if isinstance(path, Path) else Path(path)

        # Obtain activity slug.
        slug = path.stem

        # Define YAML front matter pattern.
        yaml_front_matter_pattern = re.compile(
            r'(?m)^\s*---\s*$\n(.*?)\n^\s*---\s*$',
            re.DOTALL
        )

        # Read the activity note content.
        try:
            with path.open('r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError as e:
            # TODO: log.
            raise ActivityReadFromMarkdownNoteError(
                f"The activity note '{path}' not found."
            ) from e
        except PermissionError as e:
            # TODO: log.
            raise ActivityReadFromMarkdownNoteError(
                f"Permission to read the activity note '{path}' denied. {e}"
            ) from e
        except UnicodeDecodeError as e:
            # TODO: log.
            raise ActivityReadFromMarkdownNoteError(
                f"Unicode decode error while reading activity note '{path}'. "
                f"{e}"
            ) from e
        except OSError as e:
            # TODO: log.
            raise ActivityReadFromMarkdownNoteError(
                f"Input-output error while reading activity note '{path}'. {e}"
            ) from e

        # Find the YAML front matter.
        match = yaml_front_matter_pattern.search(content)
        if not match:
            raise ActivityReadFromMarkdownNoteError(
                f"YAML front matter in activity note '{path}' wasn't found."
            )

        # Parse the YAML front matter.
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as e:
            raise ActivityReadFromMarkdownNoteError(
                f"Invalid YAML in front matter of activity note '{path}'. {e}"
            ) from e
        parents = [self._unlink_activity(a) for a in data.get('parents', [])]

        return Activity.from_dict(slug, data), parents


    def _load_activities(self):
        """Load activities from the corresponding subdirectory.

        Loads activities data from Markdown activity notes
        in the '{self._activities_dir}' subdirectory. By default,
        any Markdown file in this subdirectory represents an activity.
        Files with extensions other than '.md' or '.markdown'
        and subdirectories are ignored.

        It is assumed that the activities subdirectory should exist even
        if there are no activities. Therefore, if it does not exist,
        it will be created.
        """

        # Determine the activities directory.
        activities_dir = self._datadir / self._activities_subdir

        activity_note_entries = self._activity_notes_list()
        activities = Activities()
        connections = []
        for ar in activity_note_entries:
            activity, parents = self._read_activity_from_markdown_note(ar.path)
            activities.add(activity)
            connections.extend([(parent, activity) for parent in parents])
        activities.add_connections(connections)
        self.activities = activities


    def _clear_activity_notes(self) -> None:
        """Remove all activity notes.

        Removes all Markdown files from the '{self._activities_subdir}'
        subdirectory. By default, any Markdown file in this subdirectory
        represents an activity. Files with extensions other than '.md'
        or '.markdown' and subdirectories are ignored.

        It is assumed that the activities subdirectory should exist even
        if there are no activities. Therefore, if it does not exist,
        it will be created.
        """

        # Determine the activities subdirectory.
        activities_dir = self._datadir / self._activities_subdir

        # Create activities subdirectory if it doesn't exist.
        if not activities_dir.exists():
            activities_dir.mkdir(parents=True, exist_ok=True)
            return

        # Iterate over all Markdown files in directory (non‑recursive)
        # and delete them.
        for file_path in chain(
                activities_dir.glob('*.md'), activities_dir.glob('*.markdown')
        ):
            try:
                file_path.unlink()
            except OSError as e:
                # TODO: log 'Could not delete the activity note:
                # TODO: \'{file_path}\'.'
                pass


    def _update_diane_block(self, block_content: str, new_block: str) -> str:
        '''Update the 'diane_sessions' field inside a single YAML block.
        
        Args:
            `block_content` (`str`): The YAML content (without 
                the surrounding '---').
            `new_block`: New YAML content for 'diane_sessions' (can
                be empty). If empty, the field is removed.
        
        Returns:
            Updated YAML content (without '---'), or empty string
            if the block becomes empty after removal.
        '''

        # Parse the existing block.
        try:
            data = yaml.safe_load(block_content) or {}
        except yaml.YAMLError:
            # If parsing fails, return the original content unchanged
            return block_content
        
        if not isinstance(data, dict):
            # Not a dictionary, we cannot safely update; return as is.
            return block_content
        
        if not new_block:
            # Remove diane_sessions if present
            if 'diane_sessions' in data:
                del data['diane_sessions']
            # If the dict becomes empty, return empty string (block
            # will be removed)
            if not data:
                return ''
            # Serialize preserving key order.
            return yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )
        
        # Parse the new block to extract the value for 'diane_sessions'.
        try:
            new_data = yaml.safe_load(new_block)
        except yaml.YAMLError:
            new_data = None
        
        if isinstance(new_data, dict) and 'diane_sessions' in new_data:
            new_value = new_data['diane_sessions']
        else:
            # Fallback: treat new_block as the raw value (unlikely).
            new_value = new_block
        
        # Update or add the field.
        data['diane_sessions'] = new_value
        
        # Serialize preserving key order.
        return yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )
    

    def _update_diane_blocks(self, content: str, new_block: str) -> str:
        '''Replace all YAML blocks that contain a 'diane_sessions' key
        with the new block.
        
        Other blocks are left untouched. Returns the modified content.
        
        Args:
            `content`: The given Markdown content.
            `new_block`: YAML content '{diane_sessions: [...]}'
                or empty string.
        Returns:
            `str`: New content.
        '''
        # Pattern for YAML blocks.
        block_pattern = re.compile(
            r'(?m)^\s*---\s*$\n(.*?)\n^\s*---\s*$',
            re.DOTALL
        )
        
        parts = []
        last_end = 0
        diane_block_handled = False
        
        for match in block_pattern.finditer(content):
            start, end = match.span()

            # Text before YAML block.
            parts.append(content[last_end:start])
            
            yaml_block = match.group(1).strip()
            try:
                data = yaml.safe_load(yaml_block)
                has_diane = isinstance(data, dict) and 'diane_sessions' in data
            except yaml.YAMLError:
                has_diane = False
            
            if has_diane:
                # If this is the Diane block, update it
                if not diane_block_handled:
                    # if you haven't already.
                    updated = self._update_diane_block(yaml_block, new_block)
                    if updated:
                        parts.append(f'---\n{updated}---\n')
                    # If updated is empty, the block is removed.
                    diane_block_handled = True
            else:
                parts.append(match.group(0))
            
            last_end = end
        
        parts.append(content[last_end:])
        
        # If no Diane blocks have been encountered and `new_block`
        # is non-empty, a new block must be created.
        
        if not diane_block_handled and new_block:
            last_match = None
            last_span = None
            for match in block_pattern.finditer(content):
                last_match = match
                last_span = match.span()  # Remember the last block's
                                          # position to insert after it.
            if last_match:
                yaml_block = last_match.group(1).strip()
                try:
                    data = yaml.safe_load(yaml_block) or {}
                except yaml.YAMLError:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                try:
                    new_data = yaml.safe_load(new_block)
                    if isinstance(new_data, dict):
                        data.update(new_data)
                    else:
                        data['diane_sessions'] = new_block
                except yaml.YAMLError:
                    data['diane_sessions'] = new_block
                
                new_yaml_str = yaml.safe_dump(
                    data, allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False
                )

                # Replace the last block.
                parts = []
                last_end = 0
                for match in block_pattern.finditer(content):
                    start, end = match.span()
                    parts.append(content[last_end:start])
                    if (start, end) == last_span:   # Compare position.
                        parts.append(f'---\n{new_yaml_str}---\n')
                    else:
                        parts.append(match.group(0))
                    last_end = end
                parts.append(content[last_end:])
        
        return ''.join(parts)


    def _save_dirty_days(self) -> None:
        '''Write all dirty days to files.
        
        Updates only the YAML blocks that belong to Diane.
        '''

        # Find the sessions candidates to be written to disc.
        first_day = min(self._dirty_days) - datetime.timedelta(days=1)
        last_day = max(self._dirty_days) + datetime.timedelta(days=2)
        target_start = Timestamp.midnight(first_day, 'Etc/UTC')
        target_end = Timestamp.midnight(last_day, 'Etc/UTC')
        dirty_zone = TimeInterval.closedopen(target_start, target_end)
        candidates = self.find_overlapping(dirty_zone)

        # Select the sessions by day to be written to disc.
        for_writing = {day: set() for day in self._dirty_days}
        for s in candidates:
            if s.timeset.overlaps_with_days(self._dirty_days):
                split = s.split_into_days()
                for ss in split:
                    if ss.timeset.overlaps_with_days(self._dirty_days):
                        for_writing[ss.timeset.first_day].add(ss)

        # Writing files.
        for day, sessions in for_writing.items():
            file_path = self._datadir / 'daily_notes' / f'{day.isoformat()}.md'

            def link_activities(session_data: dict) -> dict:
                session_data['activities'] = [f'[[diane_activities/{a}]]' for a in session_data['activities']]
                return session_data

            sessions_data = [link_activities(s.to_dict()) for s in sorted(sessions, key=lambda s: s.timeset.start)]

            # Generate new sessions YAML block.
            if sessions_data:
                yaml_str = yaml.safe_dump(
                    {'diane_sessions': sessions_data},
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False
                )
            else:
                yaml_str = ''

            # Process the file.
            if file_path.exists():
                with file_path.open('r', encoding='utf-8') as f:
                    content = f.read()
                new_content = self._update_diane_blocks(content, yaml_str)
                
                with file_path.open('w', encoding='utf-8') as f:
                    f.write(new_content)
            else:
                if yaml_str:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with file_path.open('w', encoding='utf-8') as f:
                        f.write(f'---\n{yaml_str}---\n')
        
        # Clear dirty days.
        self._dirty_days.clear()


    def _save_activity_note(self, activity: Activity) -> None:
        """Save the Markdown note for the given activity to disk.

        Args:
            activity (Activity): The activity for which to save
                the Markdown note.
        """

        # Obtain the activity raw data.
        data = self._activities.activity_to_dict(activity)

        # Prepare activity data for saving:
        # - add the 'diane_activity' tag;
        # - add parent links if the activity has any parents.
        data_for_saving = {
            'tags': 'diane_activity',
            'title': data['title']
        }
        if 'description' in data:
            data_for_saving['description'] = data['description']
        parents = sorted(self._activities.parents(activity), key=lambda a: a.slug)
        if parents:
            data_for_saving['parents'] = [
                self._link_activity(p.slug) for p in parents
            ]

        path = (
            self._datadir / self._activities_subdir / f'{activity.slug}.md'
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        # Helper to merge tag values.
        def merge_tag(existing, new_tags):
            if existing is None:
                return new_tags
            if isinstance(existing, str):
                tags = existing.split()
                if new_tags not in tags:
                    tags.append(new_tags)
                return ' '.join(tags)
            if isinstance(existing, list):
                if new_tags not in existing:
                    existing.append(new_tags)
                return existing
            # Fallback: replace with new_tags (should not happen normally)
            return new_tags

        if not path.exists():
            # Create new file with only the YAML block.
            yaml_str = yaml.safe_dump(
                data_for_saving,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )
            content = f'---\n{yaml_str}---\n'
            with path.open('w', encoding='utf-8') as f:
                f.write(content)
            return
        
        # File exists: read and update.
        with path.open('r', encoding='utf-8') as f:
            content = f.read()

        # Find YAML frontmatter block.
        block_pattern = re.compile(
            r'^---\s*\n(.*?)\n---\s*\n?',
            re.MULTILINE | re.DOTALL
        )
        match = block_pattern.search(content)
        if not match:
            # No YAML block: create one at the beginning.
            yaml_str = yaml.safe_dump(
                data_for_saving,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )
            new_content = f'---\n{yaml_str}---\n' + content
            with path.open('w', encoding='utf-8') as f:
                f.write(new_content)
            return

        # Parse existing YAML block.
        yaml_block = match.group(1).strip()
        try:
            existing_data = yaml.safe_load(yaml_block) or {}
        except yaml.YAMLError:
            existing_data = {}
        if not isinstance(existing_data, dict):
            existing_data = {}

        # We'll collect all YAML blocks and update them.
        blocks = []  # List of `(start, end, data_dict)`.
        updated_fields = set()  # fields that have been updated in any block

        # Process all YAML blocks.
        for m in block_pattern.finditer(content):
            start, end = m.span()
            yaml_content = m.group(1).strip()
            try:
                block_data = yaml.safe_load(yaml_content) or {}
            except yaml.YAMLError:
                block_data = {}
            if not isinstance(block_data, dict):
                block_data = {}
            blocks.append((start, end, block_data))

        # Update each block.
        for i, (start, end, block_data) in enumerate(blocks):
            modified = False
            # Update title
            if 'title' in data_for_saving and block_data.get('title') != data_for_saving['title']:
                block_data['title'] = data_for_saving['title']
                updated_fields.add('title')
                modified = True
            # Update description (only if present in data_for_saving)
            if 'description' in data_for_saving:
                if block_data.get('description') != data_for_saving['description']:
                    block_data['description'] = data_for_saving['description']
                    updated_fields.add('description')
                    modified = True
            # Update parents (only if present)
            if 'parents' in data_for_saving:
                if block_data.get('parents') != data_for_saving['parents']:
                    block_data['parents'] = data_for_saving['parents']
                    updated_fields.add('parents')
                    modified = True
            # Update tag (merge)
            if 'tags' in data_for_saving:
                old_tags = block_data.get('tags')
                new_tags = merge_tag(old_tags, data_for_saving['tags'])
                if old_tags != new_tags:
                    block_data['tags'] = new_tags
                    updated_fields.add('tags')
                    modified = True

            if modified:
                # Replace this block in the list with updated data
                blocks[i] = (start, end, block_data)

        # Add missing fields to the last block
        last_start, last_end, last_data = blocks[-1]
        missing_fields = set(data_for_saving.keys()) - updated_fields
        if missing_fields:
            for field in missing_fields:
                if field == 'tags':
                    # Merge tag with existing
                    old_tags = last_data.get('tags')
                    new_tags = merge_tag(old_tags, data_for_saving['tags'])
                    last_data['tags'] = new_tags
                else:
                    last_data[field] = data_for_saving[field]
            blocks[-1] = (last_start, last_end, last_data)

        # Rebuild content with updated blocks
        new_parts = []
        last_idx = 0
        for start, end, block_data in blocks:
            new_parts.append(content[last_idx:start])
            # Serialize block_data
            yaml_str = yaml.safe_dump(
                block_data,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )
            new_parts.append(f'---\n{yaml_str}---\n')
            last_idx = end
        new_parts.append(content[last_idx:])
        new_content = ''.join(new_parts)

        with path.open('w', encoding='utf-8') as f:
            f.write(new_content)



    def _load_state(self) -> None:
        '''Load the tracking state.

        The tracking state represents the currently tracked activities
        and their start times. It is stored in a YAML file
        '.diane/tracking.yaml' with the following format::

            tracking:
                activity_1_slug:
                    start_time: '2026-04-07T22:09:45+02:00'
                    start_timezone: Europe/Vilnius
                activity_2_slug:
                    start_time: '2026-04-07T22:09:45+02:00'
                    start_timezone: Europe/Vilnius
                ...

        Raises:
            `ValueError`: If the YAML file is invalid or contains
                invalid data.
        '''

        path = self._datadir / '.diane/tracking.yaml'
        if not path.exists():
            self._tracking_state = {}
            return

        try:
            with path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f'Invalid YAML file \'{path}\': {e}.') from e

        if not isinstance(data, dict):
            raise ValueError('YAML root must be a mapping.')

        activities_data = data.get('tracking')
        if activities_data is None:
            self._tracking_state = {}
            return
        if not isinstance(activities_data, dict):
            raise ValueError('\'tracking\' must be a mapping.')
        
        tracking_state = {}
        for slug, item in activities_data.items():
            if not isinstance(item, dict):
                raise ValueError(f'Tracking entry for \'{slug}\' must be a mapping.')
            
            try:
                activity = self._activities.activity_by_slug(slug)
            except KeyError as e:
                raise ValueError(f'Unknown activity slug \'{slug}\' in tracking file.') from e

            if activity in tracking_state:
                raise ValueError(f'Duplicate activity \'{activity}\' in tracking file.')
            
            try:
                start_time_iso = item['start_time']
                start_timezone_iana = item['start_timezone']
                ts = Timestamp.from_iso_iana(start_time_iso, start_timezone_iana)
            except KeyError as e:
                raise ValueError(
                    f'Missing required field in tracking entry for \'{slug}\': {e}.'
                ) from e
            except ValueError as e:
                raise ValueError(f'Invalid timestamp data for \'{slug}\': {e}.') from e

            tracking_state[activity] = ts
                
            
        self._tracking_state = tracking_state


    def _save_state(self) -> None:
        '''Save the tracking state to the YAML file.'''

        path = self._datadir / '.diane/tracking.yaml'
        data = {}
        for activity, ts in self._tracking_state.items():
            data[activity.slug] = {
                'start_time': ts.datetime_iso,
                'start_timezone': ts.timezone_iana
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8') as f:
            yaml.safe_dump({'tracking': data}, f, allow_unicode=True, sort_keys=False)


    def add(self, value: Session) -> None:
        '''Add the given session to the repository and mark its days
        as dirty.
        
        The session is added only if it is not already present and all
        its activities are in the registry.

        Args:
            `value` (`Session`): The session to add.
        '''

        if value not in self._sessions:
            super().add(value)
            if not self._loading:
                self._dirty_days.update(value.timeset.days)
    

    def discard(self, value: Session) -> None:
        '''Discard the given session from the repository and mark
        its days as dirty.
        
        Args:
            `value` (`Session`): The session to discard.
        '''

        if value in self._sessions:
            super().discard(value)
            if not self._loading:
                self._dirty_days.update(value.timeset.days)


    def remove(self, value: Session) -> None:
        '''Remove the given session from the repository and mark
        its days as dirty.

        Args:
            `value` (`Session`): The session to remove.
        '''

        super().remove(value)
        if not self._loading:
                self._dirty_days.update(value.timeset.days)

    
    def merge(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) and return the merged session. Mark changed
        days as dirty.

        The sessions are merged only if they have identical activity
        sets. A new session is created that unites the time sets
        and messages of the original ones. The original sessions
        are removed from the repository and the merged session is added.

        Args:
            `*sessions` (`Session`): The sessions for merging.
        '''

        result = super().merge(*sessions)
        if not self._loading:
            self._dirty_days.update(result.timeset.days)
        return result
    

    def merge_if_good(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) and return the merged session if it's 'good'.
        Mark changed days as dirty.

        The sessions are merged only if they have identical activity
        sets and the result is 'good'. A new session unites the time
        sets and messages of the original ones. The original sessions
        are removed from the repository and the merged session is added.

        Args:
            `*sessions` (`Session`): The sessions for merging.

        Returns:
            `Session`: The merged session.
        '''

        result = super().merge_if_good(*sessions)
        if not self._loading:
            self._dirty_days.update(result.timeset.days)
        return result
    

    def add_and_merge(self, session: Session) -> Session:
        '''Add the given session to the repository and repeatedly
        merge it with the closest session in time until no further merge
        is possible. Mark changed days as dirty.

        Args:
            `session` (`Session`): The session to add.

        Return:
            `Session`: The final merged session.
        '''

        result = super().add_and_merge(session)
        if not self._loading:
            self._dirty_days.update(result.timeset.days)
        return result


    StartResult = namedtuple('StartResult', ['activities', 'timestamp'])


    def start(
            self, *activities: str, timestamp: Timestamp | None = None
    ) -> StartResult:
        """Start tracking one or more activities.

        The activities are marked as being tracked from the current
        moment. If an activity is already being tracked, a warning
        is issued and it is not started again. Unknown activity slugs
        cause a `ValueError` with a list of all unrecognised slugs.

        Args:
            `*activities` (`str`): One or more activity slugs to start
                tracking. Duplicates are ignored (only the first
                occurrence is considered).

        Raises:
            `NoActivitiesProvided`: If no activities are provided.
            `UnknownActivityError`: If any of the activity slugs
                are not found in the activities registry.
            `ActivityAlreadyTracked`: If there is activity that
                is already being tracked.
            `AncestorActivities`: If some of the specified activities
                are the ancestors of others.
            `AncestorActivitiesTracked`: If some of the specified
                activities are ancestors of activities that
                are already being tracked.
        """

        if not activities:
            raise NoActivitiesProvided('Specify at least one activity for tracking.')
        
        # Remove duplicates, preserving order.
        unique_slugs = list(dict.fromkeys(activities))
        
        # Check for any unknown activities.
        activities_to_start: set[Activity] = set()
        unknown_activity_slugs: set[str] = set()
        for slug in unique_slugs:
            try:
                activities_to_start.add(self._activities.activity_by_slug(slug))
            except KeyError:
                unknown_activity_slugs.add(slug)
        if unknown_activity_slugs:
            raise UnknownActivityError(
                provided_slugs=unique_slugs,
                unknown_slugs=unknown_activity_slugs,
                recognised_activities=activities_to_start
            )
        
        # Check whether any activities are already being tracked.
        already_tracked = activities_to_start & set(self._tracking_state)
        if already_tracked:
            already_tracked_data: dict[Activity, Timestamp] = {
                a: self._tracking_state[a] for a in already_tracked if a in self._tracking_state
            }
            raise ActivityAlreadyTracked(
                activities_to_start,
                already_tracked_data
            )
        
        # Check whether any of specified activities are ancestors
        # of others.
        specified_activity_to_ancestors: dict[Activity, set[Activity]] = {}
        for a in activities_to_start:
            specified_activity_to_ancestors[a] = self._activities.ancestors(a)
        ancestor_to_specified_activities: defaultdict[Activity, set[Activity]] = defaultdict(set)
        for possible_ancestor in activities_to_start:
            for activity, ancestors in specified_activity_to_ancestors.items():
                if possible_ancestor in ancestors:
                    ancestor_to_specified_activities[possible_ancestor].add(activity)
        if ancestor_to_specified_activities:
            raise AncestorActivities(activities_to_start, ancestor_to_specified_activities)
        
        # Check whether any of specified activities are ancestors
        # or descendants of activities that are already being tracked.
        provided = activities_to_start
        tracked = set(self._tracking_state)
        ancestors = self._activities.ancestors(*tracked) & provided
        descendants = self._activities.descendants(*tracked) & provided
        if ancestors or descendants:
            ancestors_to_descendants = {}
            for a in ancestors:
                ancestors_to_descendants[a] = (
                    self._activities.descendants(a) & tracked
                )
            descendants_to_ancestors = {}
            for a in descendants:
                descendants_to_ancestors[a] = (
                    self._activities.ancestors(a) & tracked
                )
            raise AncestorActivitiesTracked(
                provided, ancestors_to_descendants, descendants_to_ancestors
            )

        now = (
            Timestamp.now().round_to_second() if timestamp is None
            else timestamp
        )
        started_activities = []

        for a in activities_to_start:
            self._tracking_state[a] = now
            started_activities.append(a)

        if started_activities:
            self._save_state()

        return RepositoryManager.StartResult(started_activities, now)
    

    def cancel(self, *activities: str, all: bool = False) -> set[Activity]:
        '''Cancel tracking the specified activities.
        
        Args:
            `*activities` (`str`): Activity slugs to cancel tracking.
                Ignored if `all=True`.
            `all` (`bool`): If `True`, cancel all tracked activities
                instead of a specific list.

        Returns:
            `set[Activities]`: The cancelled activities.
        '''

        if all:
            if not self._tracking_state:
                warnings.warn('No activities are currently being tracked.')
                return set()
            activities_to_cancel = list(self._tracking_state.keys())
        else:
            if not activities:
                raise ValueError('Specify at least one activity to cancel.')
            unique_slugs = list(dict.fromkeys(activities))
            activities_to_cancel = []
            unknown_slugs = []

            for slug in unique_slugs:
                try:
                    activities_to_cancel.append(self._activities.activity_by_slug(slug))
                except KeyError:
                    unknown_slugs.append(slug)

            if unknown_slugs:
                if len(unknown_slugs) == 1:
                    raise ValueError(f'Unknown activity: \'{unknown_slugs[0]}\'.')
                else:
                    quoted = ', '.join(f'\'{s}\'' for s in unknown_slugs)
                    raise ValueError(f'Unknown activities: {quoted}.')
                
        # We only keep the ones that are actually being tracked.
        tracked = set()
        for a in activities_to_cancel:
            start = self._tracking_state.get(a)
            if start is None:
                warnings.warn(f'Activity \'{a}\' is not being tracked.', stacklevel=2)
            else:
                tracked.add(a)

        if not tracked:
            return set()
        
        # Remove activities from those being tracked.
        for a in tracked:
            del self._tracking_state[a]

        self._save_state()

        # Return cancelled activities.
        return tracked
        

    def stop(
        self,
        *activities: str,
        timestamp: Timestamp | None = None,
        all: bool = False,
        message: str = ''
    ) -> list[Session]:
        """For each distinct start time among the stopped activities,
        a separate session is created covering the interval from that
        start time until now (`[start, now)`). The sessions are added
        to the repository and merged with neighbouring sessions
        if possible (via `add_and_merge`).

        If `all=True`, all currently tracked activities are stopped
        (the `activities` argument is ignored). Otherwise, the given
        activity slugs are resolved; any unknown slugs raise
        a `ValueError`, and any activities that are not currently being
        tracked produce a warning and are skipped.

        After successful creation of all sessions, the stopped
        activities are removed from the tracking state and the state
        is saved to disk.

        Args:
            `*activities` (`str`): Activity slugs to stop tracking.
                Ignored if `all=True`.
            `all` (`bool`): If `True`, stop all tracked activities
                instead of a specific list.
            `message` (`str`): Optional message to attach to every
                session created.

        Returns:
            The list of the final merged sessions (as returned
            by `add_and_merge`), one per distinct start time group.

        Raises:
            `ValueError`: If `all=False` and no activities are provided,
                or if any of the given slugs are not found
                in the activities registry.
        """

        if all:
            if not self._tracking_state:
                warnings.warn('No activities are currently being tracked.')
                return []
            activities_to_stop = list(self._tracking_state.keys())
        else:
            if not activities:
                raise ValueError('Specify at least one activity to stop.')
            unique_slugs = list(dict.fromkeys(activities))
            activities_to_stop = []
            unknown_slugs = []

            for slug in unique_slugs:
                try:
                    activities_to_stop.append(self._activities.activity_by_slug(slug))
                except KeyError:
                    unknown_slugs.append(slug)

            if unknown_slugs:
                if len(unknown_slugs) == 1:
                    raise ValueError(f'Unknown activity: \'{unknown_slugs[0]}\'.')
                else:
                    quoted = ', '.join(f'\'{s}\'' for s in unknown_slugs)
                    raise ValueError(f'Unknown activities: {quoted}.')

        
        # We only keep the ones that are actually being tracked.
        tracked = {}
        for a in activities_to_stop:
            start = self._tracking_state.get(a)
            if start is None:
                warnings.warn(f'Activity \'{a}\' is not being tracked.', stacklevel=2)
            else:
                tracked[a] = start

        if not tracked:
            return []

        # Group activities by start time.
        groups = {}
        for a, start in tracked.items():
            groups.setdefault(start, []).append(a)

        now = (
            Timestamp.now().round_to_second() if timestamp is None
            else timestamp
        )
        created_sessions = []

        for start_time, acts in groups.items():
            interval = TimeInterval.closedopen(start_time, now)
            timeset = TimeSet(interval)
            session = Session(timeset, acts, message)
            merged = self.add_and_merge(session)
            created_sessions.append(merged)

        # Remove stopped activities from those being tracked.
        for a in tracked:
            del self._tracking_state[a]
        self._save_state()

        # Save dirty days for all created sessions.
        self._save_dirty_days()

        # Update activity notes for all involved activities.
        involved_activities = set()
        for s in created_sessions:
            involved_activities.update(s.activities)
        involved_activities_with_ancestors = set()
        for a in involved_activities:
            involved_activities_with_ancestors.add(a)
            involved_activities_with_ancestors.update(self._activities.ancestors(a))
        for a in involved_activities_with_ancestors:
            self._save_activity_note(a)

        return created_sessions
    

    def do(
        self,
        *activities: str,
        timestamp: Timestamp | None = None,
        message: str = ''
    ) -> Session:
        """Create an instantaneous session for the given activities
        at the current time, add it to the repository, and merge
        if possible.
        
        Args:
            *activities (str): Activity slugs to include in the session.
            timestamp (Timestamp | None): The time at which to create
                the session. If `None`, the current time is used.
            message (str): Optional message to attach to the session.
                Empty by default.

        Returns:
            Session: The final merged session.

        Raises:
            ValueError: If no activities are provided, or if any
            of the given slugs are not found in the activities registry.
        """

        if not activities:
            raise ValueError('Specify at least one activity for \'do\'.')
        
        unique_slugs = list(dict.fromkeys(activities))
        resolved_activities = []
        unknown_slugs = []
        for slug in unique_slugs:
            try:
                resolved_activities.append(
                    self._activities.activity_by_slug(slug)
                )
            except KeyError:
                unknown_slugs.append(slug)

        if unknown_slugs:
            if len(unknown_slugs) == 1:
                raise ValueError(f'Unknown activity: \'{unknown_slugs[0]}\'.')
            else:
                quoted = ', '.join(f'\'{s}\'' for s in unknown_slugs)
                raise ValueError(f'Unknown activities: {quoted}.')
            
        t = (
            timestamp if timestamp is not None
            else Timestamp.now().round_to_second()
        )
        point = TimeInterval.point(t)
        timeset = TimeSet(point)

        session = Session(timeset, resolved_activities, message)
        merged = self.add_and_merge(session)

        # Save dirty days for all created sessions.
        self._save_dirty_days()

        # Update activity notes for all involved activities.
        involved_activities = set(merged.activities)
        involved_activities_with_ancestors = set()
        for a in involved_activities:
            involved_activities_with_ancestors.add(a)
            involved_activities_with_ancestors.update(
                self._activities.ancestors(a)
            )
        for a in involved_activities_with_ancestors:
            self._save_activity_note(a)

        return merged