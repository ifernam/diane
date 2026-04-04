from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import warnings
import re
import datetime

from diane.temporal import Timestamp, TimeInterval, TimeSet
from diane.activities import Activity, Activities
from diane.sessions import Session
from diane.assisted_repository import AssistedRepository



class RepositoryManager(AssistedRepository):
    '''Represents the repository manager.'''

    _datadir: Path
    _tracking_state: dict[Activity, Timestamp]

    _dirty_days: set[datetime.date]  # Days to update.
    _loading: bool


    def __init__(self, datadir: str) -> None:

        # Set loading state to `True`.
        self._loading = True

        # Set repository directory.
        self._datadir = Path(datadir)

        # Load and set activities registry.
        activities_path = self._datadir / '.diane/data/activities.yaml'
        activities = Activities.from_yaml(activities_path)
        super().__init__(_activities=activities)

        # Update tracking activities.
        self._load_state()

        # No days to update.
        self._dirty_days = set()

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

                sessions_data = data.get('diane_sessions')
                if not isinstance(sessions_data, list):
                    continue
                
                for session_dict in sessions_data:
                    if not isinstance(session_dict, dict):
                        continue
                    try:
                        session = self.session_from_dict(session_dict, date_str)
                        super().add(session)
                    except Exception as e:
                        print(f'Error adding session from \'{file_path.name}\'. {e}')
                        continue

        self._merge_touching()

        # Set loading state to `False`.
        self._loading = False
    

    def _replace_diane_blocks(self, content: str, new_block: str) -> str:
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
                # If this is the Diane block, replace it
                if not diane_block_handled:
                    # if you haven't already.
                    if new_block:
                        parts.append(f'---\n{new_block}---\n')
                    diane_block_handled = True
            else:
                parts.append(match.group(0))
            
            last_end = end
        
        parts.append(content[last_end:])
        
        # If no Diane blocks have been encountered and `new_block`
        # is non-empty, a new block must be created.
        
        if not diane_block_handled and new_block:
            last_block_match = None
            for match in block_pattern.finditer(content):
                last_block_match = match
            if last_block_match:
                yaml_content = last_block_match.group(1)
                try:
                    data = yaml.safe_load(yaml_content) or {}
                except yaml.YAMLError:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                try:
                    new_data = yaml.safe_load(new_block)
                    if isinstance(new_data, dict):
                        data.update(new_data)
                    else:
                        data['diane_sessions'] = new_block  # Fallback.
                except yaml.YAMLError:
                    data['diane_sessions'] = new_block
                
                new_yaml_str = yaml.safe_dump(
                    data, allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False
                )

                # Replace last block.
                parts = []
                last_end = 0
                for match in block_pattern.finditer(content):
                    start, end = match.span()
                    parts.append(content[last_end:start])
                    if match == last_block_match:
                        parts.append(f'---\n{new_yaml_str}---\n')
                    else:
                        parts.append(match.group(0))
                    last_end = end
                parts.append(content[last_end:])
                return ''.join(parts)
            else:
                # No YAML blocks.
                if content:
                    content = '\n' + content
                return f'---\n{new_block}---\n' + content
        
        return ''.join(parts)


    def _save_dirty_days(self) -> None:
        '''Write all dirty days to disk.
        
        Update only the YAML blocks that belong to Diane.
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
            sessions_data = [s.to_dict() for s in sorted(sessions, key=lambda s: s.timeset.start)]

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
                new_content = self._replace_diane_blocks(content, yaml_str)
                
                with file_path.open('w', encoding='utf-8') as f:
                    f.write(new_content)
            else:
                if yaml_str:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with file_path.open('w', encoding='utf-8') as f:
                        f.write(f'---\n{yaml_str}---\n')
        
        # Clear dirty days.
        self._dirty_days.clear()
        


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
        and comments of the original ones. The original sessions
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
        sets and comments of the original ones. The original sessions
        are removed from the repository and the merged session is added.
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

        self._save_dirty_days()

        return created_sessions
