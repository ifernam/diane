from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
import yaml
import warnings

from temporal import Timestamp, TimeInterval, TimeSet
from activities import Activity, Activities
from sessions import Session
from assisted_repository import AssistedRepository



class RepositoryManager(AssistedRepository):
    '''Represents the repository manager.'''

    _datadir: Path
    _tracking_state: dict[Activity, Timestamp]


    def __init__(self, datadir: str) -> None:
        self._datadir = Path(datadir)
        self._tracking_state = {}
        activities = Activities.from_yaml(self._datadir / '.diane/activities.yaml')
        super().__init__(activities)
        self._update_state()


    def _update_state(self) -> None:

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
                raise ValueError(f'Missing required field in tracking entry for \'{slug}\': {e}.') from e
            except ValueError as e:
                raise ValueError(f'Invalid timestamp data for \'{slug}\': {e}.') from e

            tracking_state[activity] = ts
                
            
        self._tracking_state = tracking_state


    def _save_state(self) -> None:

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

        if not activities:
            raise ValueError('Specify at least one activity for tracking.')
        
        # Remove duplicates, preserving order.
        unique_slugs = list(dict.fromkeys(activities))
        activities_to_start = [self._activities.activity_by_slug(slug) for slug in unique_slugs]

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
