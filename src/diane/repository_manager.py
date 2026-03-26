from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import warnings
import re

from diane.temporal import Timestamp, TimeInterval, TimeSet
from diane.activities import Activity, Activities
from diane.sessions import Session
from diane.assisted_repository import AssistedRepository



class RepositoryManager(AssistedRepository):
    '''Represents the repository manager.'''

    _datadir: Path
    _tracking_state: dict[Activity, Timestamp]


    def __init__(self, datadir: str) -> None:

        # Set repository directory.
        self._datadir = Path(datadir)

        # Load and set activities registry.
        activities_path = self._datadir / '.diane/data/activities.yaml'
        activities = Activities.from_yaml(activities_path)
        super().__init__(activities)

        # Update tracking activities.
        self._load_state()

        # Load sessions.
        sessions_path = self._datadir / 'daily_notes'
        filename_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}\.md$')
        block_pattern = re.compile(
            r'(?m)^\s*---\s*$\n(.*?)\n^\s*---\s*$',
            re.DOTALL
        )

        for file_path in sessions_path.glob('*.md'):
            if not filename_pattern.match(file_path.name):
                continue

            date_str = file_path.stem  # YYYY-MM-DD.

            try:
                with file_path.open('r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                print(f'Error reading \'{file_path.name}\'. {e}')
                continue

            # Find all YAML blocks.
            for match in block_pattern.finditer(content):
                yaml_block = match.group(1).strip()
                if not yaml_block:
                    continue

                try:
                    data = yaml.safe_load(yaml_block)
                except yaml.YAMLError:
                    continue

                if not isinstance(data, dict):
                    continue

                sessions_data = data.get('diane')
                if not isinstance(sessions_data, list):
                    continue
                
                for session_dict in sessions_data:
                    if not isinstance(session_dict, dict):
                        continue
                    try:
                        self.add_from_dict(session_dict, date_iso=date_str)
                    except Exception as e:
                        print(f'Error adding session from \'{file_path.name}\'. {e}')
                        continue

        self._merge_touching()


    def _load_state(self) -> None:
        '''Load the tracking state from the YAML file.'''

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

    
    def start(self, *activities: str) -> None:
        '''Start tracking one or more activities.

        The activities are marked as being tracked from the current
        moment. If an activity is already being tracked, a warning
        is issued and it is not started again. Unknown activity slugs
        cause a `ValueError` with a list of all unrecognised slugs.

        Args:
            *activities: One or more activity slugs to start tracking.
                Duplicates are ignored (only the first occurrence
                is considered).

        Raises:
            ValueError: If no activities are provided, or if any
                of the slugs are not found in the activities
                registry.'''

        if not activities:
            raise ValueError('Specify at least one activity for tracking.')
        
        # Remove duplicates, preserving order.
        unique_slugs = list(dict.fromkeys(activities))
        
        activities_to_start = []
        unknown_slugs = []

        for slug in unique_slugs:
            try:
                activities_to_start.append(self._activities.activity_by_slug(slug))
            except KeyError:
                unknown_slugs.append(slug)

        if unknown_slugs:
            if len(unknown_slugs) == 1:
                raise ValueError(f'Unknown activity: \'{unknown_slugs[0]}\'.')
            else:
                quoted = ', '.join(f'\'{s}\'' for s in unknown_slugs)
                raise ValueError(f'Unknown activities: {quoted}.')
        
        now = Timestamp.now()
        changed = False

        for a in activities_to_start:
            if a in self._tracking_state:
                warnings.warn(
                    f'The activity \'{a}\' is already being tracked.',
                    stacklevel=2
                )
            else:
                self._tracking_state[a] = now
                changed = True

        if changed:
            self._save_state()


    def stop(self, *activities: str, all: bool = False, comment: str = '') -> list[Session]:
        '''For each distinct start time among the stopped activities,
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
            *activities: Activity slugs to stop tracking. Ignored
                if `all=True`.
            all: If `True`, stop all tracked activities instead
                of a specific list.
            comment: Optional comment to attach to every session
                created.

        Returns:
            A list of the final merged sessions (as returned
            by `add_and_merge`), one per distinct start time group.

        Raises:
            ValueError: If `all=False` and no activities are provided,
                or if any of the given slugs are not found
                in the activities registry.'''

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

        now = Timestamp.now()
        created_sessions = []

        for start_time, acts in groups.items():
            interval = TimeInterval.closedopen(start_time, now)
            timeset = TimeSet(interval)
            session = Session(timeset, acts, comment)
            merged = self.add_and_merge(session)
            created_sessions.append(merged)

        # Remove stopped activities from those being tracked.
        for act in tracked:
            del self._tracking_state[act]
        self._save_state()

        return created_sessions
