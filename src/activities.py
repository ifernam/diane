from __future__ import annotations
from dataclasses import dataclass, field
import networkx as nx
import yaml
from pathlib import Path
import re



@dataclass
class Activity:
    '''Represents a human activity.
    
    Attributes:
        _slug: The unique string identifier for an activity. Cannot
            be changed. A slug consists of lowercase letters, digits
            and underscores only. It cannot contain more than one
            consecutive underscore. It must not begin or end with
            an underscore.
            
        title: The human-readable name of the activity. Can be changed.
            It should start with a capital letter and finish without
            a dot.
        
        description: The activity description string. Can be changed.
            This may be empty if the activity is clearly understood from
            its name. It should start with a capital letter and finish
            with a dot.'''


    _SLUG_PATTERN = re.compile(r'[a-z0-9]+(_[a-z0-9]+)*')

    
    _slug: str
    title: str
    description: str = field(default_factory=str)


    @classmethod
    def validate_slug(cls, slug: str) -> None:
        if not cls._SLUG_PATTERN.fullmatch(slug):
            raise ValueError(f'Incorrect slug format: {slug}.')
        
    
    def validate(self) -> None:
        Activity.validate_slug(self._slug)


    def __post_init__(self) -> None:
        self.validate()


    def __hash__(self) -> int:
        return hash(self._slug)
    

    def __eq__(self, other: object) -> bool:

        if not isinstance(other, Activity):
            return NotImplemented
        
        return self.slug == other.slug
    

    @property
    def slug(self) -> str:
        '''Returns a unique string identifier of the activity.'''

        return self._slug
    

    @classmethod
    def from_dict(cls, slug: str, data: dict) -> Activity:
        return cls(
            _slug=slug,
            title=data['title'],
            description=data.get('description', '')
        )
    


@dataclass
class Activities:
    '''All activities.'''

    activities_graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    slug_to_activity: dict[str, Activity] = field(default_factory=dict)

    
    def validate(self) -> None:

        if not nx.is_directed_acyclic_graph(self.activities_graph):
            cycle = nx.find_cycle(self.activities_graph)
            raise ValueError(f'Cycle detected: {cycle}.')
    

    def clear(self) -> None:
        '''Clears all activities data.'''

        self.activities_graph.clear()
        self.slug_to_activity.clear()
        

    def load_from_yaml(self, filename: str) -> None:
        '''Load activities from YAML file.'''

        try:
            path = Path(filename)

            with path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                raise ValueError('YAML root must be a mapping.')

            activities_data = data.get('activities')
            if not isinstance(activities_data, dict):
                raise ValueError('\'activities\' must be a mapping.')

            # Clear old data.
            self.clear()

            # Create activities.
            for slug, item in activities_data.items():
                if not isinstance(item, dict):
                    raise ValueError('Each activity must be a mapping.')

                activity = Activity.from_dict(slug, item)

                if activity.slug in self.slug_to_activity:
                    raise ValueError(f'Duplicate slug: {activity.slug}.')

                self.slug_to_activity[activity.slug] = activity
                self.activities_graph.add_node(activity)

            # Create connections.
            for slug, item in activities_data.items():
                parents = item.get('parents', [])

                if parents is None:
                    parents = []

                if not isinstance(parents, list):
                    raise ValueError(
                        f'\'parents\' of \'{slug}\' must be a list.'
                    )

                child = self.slug_to_activity[slug]

                for parent_slug in parents:
                    if parent_slug not in self.slug_to_activity:
                        raise ValueError(
                            f'Unknown parent \'{parent_slug}\' for activity \'{slug}\'.'
                        )

                    parent = self.slug_to_activity[parent_slug]
                    self.activities_graph.add_edge(parent, child)

            self.validate()
        
        except FileNotFoundError as e:
            raise ValueError(f'File not found: {filename}.') from e
        
        except yaml.YAMLError as e:
            raise ValueError(f'Invalid YAML: {e}.') from e