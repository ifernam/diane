from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Iterable
import networkx as nx
import yaml
from pathlib import Path
import re
import warnings




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
    description: str = ''


    @classmethod
    def _validate_slug(cls, slug: str) -> None:
        if not cls._SLUG_PATTERN.fullmatch(slug):
            raise ValueError(f'Incorrect slug format: {slug}.')
        
    
    def _validate(self) -> None:
        Activity._validate_slug(self._slug)


    def __post_init__(self) -> None:
        self._validate()

    
    def __setattr__(self, name, value):
        if name == '_slug' and hasattr(self, '_slug'):
            raise AttributeError("Slug is immutable.")
        super().__setattr__(name, value)


    def __hash__(self) -> int:
        return hash(self._slug)
    

    def __eq__(self, other: object) -> bool:

        if not isinstance(other, Activity):
            return NotImplemented
        
        return self._slug == other._slug
    

    def __str__(self) -> str:
        return self._slug
    

    @property
    def slug(self) -> str:
        '''Returns a unique string identifier of the activity.'''

        return self._slug
    

    @classmethod
    def from_dict(cls, slug: str, data: dict) -> Activity:
        '''Constructs activity from the dictionary.
        
        Ignores parents.'''

        # Show a warning if there are extra fields in the activity
        # dictionary.
        allowed_keys = {'title', 'description', 'parents'}
        extra_keys = set(data) - allowed_keys
        if extra_keys:
            sorted_quoted_extra_keys = [f'\'{str(k)}\'' for k in sorted(extra_keys)]
            extra_keys_string = ', '.join(sorted_quoted_extra_keys)
            warnings.warn(
                f'Activity dictionary corresponding to the slug \'{slug}\' contains unknown '
                f'fields: {extra_keys_string}.',
                stacklevel=2
            )

        try:
            title = data['title']
        except KeyError as e:
            raise ValueError(f'Activity \'{slug}\' is missing required field \'title\'.') from e
        
        if not isinstance(title, str):
            raise TypeError(f'Field \'title\' of activity \'{slug}\' must be a string.')
        
        description = data.get('description', '')

        if not isinstance(description, str):
            raise TypeError(f'Field \'description\' of activity \'{slug}\' must be a string.')

        return cls(
            _slug=slug,
            title=title,
            description=description
        )
    


@dataclass
class Activities:
    '''Registry of activities'''

    _activities_graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    _slug_to_activity: dict[str, Activity] = field(default_factory=dict)

    
    def _validate(self) -> None:

        if not nx.is_directed_acyclic_graph(self._activities_graph):
            cycle = nx.find_cycle(self._activities_graph)
            activities_in_cycle = [edge[0] for edge in cycle] + [cycle[0][0]]
            activities_slugs_in_cycle = [f'\'{activity}\'' for activity in activities_in_cycle]
            cycle_string = ' -> '.join(activities_slugs_in_cycle)
            raise ValueError(f'Cycle detected: {cycle_string}.')
        
        
    def __post_init__(self) -> None:
        self._validate()
        
    
    def _resolve_activity(self, obj: Activity | str) -> Activity:
        '''Checks for activity in the registry. If activity is found,
        restores activity according to the slug.'''

        if isinstance(obj, Activity):
            slug = obj.slug
        elif isinstance(obj, str):
            slug = obj
        else:
            raise TypeError(f'\'obj\' must be \'Activity\' or \'str\'.')

        try:
            return self._slug_to_activity[slug]
        except KeyError as e:
            raise KeyError(f'Unknown activity: \'{slug}\'.') from e

    
    def __contains__(self, item: object) -> bool:
        '''Checks whether the activity is contained in the registry.
        
        Only takes the slug into account.'''

        if isinstance(item, Activity):
            return item.slug in self._slug_to_activity
        
        if isinstance(item, str):
            return item in self._slug_to_activity
        
        return False
    

    def add_activity(self, activity: Activity) -> None:
        '''Adds activity to the registry.'''

        if activity.slug in self._slug_to_activity:
            raise ValueError(f'Activity {activity.slug} already exists.')

        self._activities_graph.add_node(activity)
        self._slug_to_activity[activity.slug] = activity


    def add_connection(self, parent: Activity | str, child: Activity | str) -> None:
        '''Adds a connection between activities in the registry.

        Securely adds a parent -> child connection with validation.
        It is assumed that the activities themselves are already
        contained in the registry.'''

        parent = self._resolve_activity(parent)
        child = self._resolve_activity(child)

        if parent is child:
            raise ValueError(f'Self-loop is not allowed: {parent}.')

        if self._activities_graph.has_edge(parent, child):
            return    # Connection already exists.

        if nx.has_path(self._activities_graph, child, parent):
            raise ValueError(
                f'Adding connection \'{parent.slug}\' -> \'{child.slug}\' creates a cycle.'
            )

        self._activities_graph.add_edge(parent, child)


    def add_connections(self, connections: Iterable[tuple[str | Activity, str | Activity]]) \
        -> None:

        '''Adds connections between activities in the registry.

        Securely adds parent -> child connection pairs with
        validation. It is assumed that the activities themselves
        are already contained in the registry.'''

        tmp_activities_graph = self._activities_graph.copy()

        for p, c in connections:
            parent = self._resolve_activity(p)
            child = self._resolve_activity(c)
            
            if parent is child:
                raise ValueError(f'Self-loop is not allowed: {parent}.')
            
            if tmp_activities_graph.has_edge(parent, child):
                continue    # Connection already exists.

            tmp_activities_graph.add_edge(parent, child)

        if not nx.is_directed_acyclic_graph(tmp_activities_graph):
            cycle = nx.find_cycle(tmp_activities_graph)
            activities_in_cycle = [edge[0] for edge in cycle] + [cycle[0][0]]
            activities_slugs_in_cycle = [f'\'{activity}\'' for activity in activities_in_cycle]
            cycle_string = ' -> '.join(activities_slugs_in_cycle)
            raise ValueError(f'Cycle detected: {cycle_string}.')
        
        self._activities_graph = tmp_activities_graph



    def activity_by_slug(self, slug: str) -> Activity:
        '''Restores activity by slug.
        
        Raises:
            KeyError: if the activity with the specified slug
                is not found in the registry.'''

        try:
            return self._slug_to_activity[slug]
        except KeyError as e:
            raise KeyError(f'Unknown activity: \'{slug}\'.') from e
        

    def parents(self, *activities: str | Activity) -> set[Activity]:
        '''Returns the parents of the specified activities.'''

        resolved_activities = (self._resolve_activity(a) for a in activities)
        parents = set()
        for a in resolved_activities:
            parents.update(self._activities_graph.predecessors(a))
        return parents
    

    def ancestors(self, *activities: str | Activity) -> set[Activity]:
        '''Returns all ancestors of the specified activities.'''

        resolved_activities = (self._resolve_activity(a) for a in activities)
        ancestors = set()
        for a in resolved_activities:
            ancestors.update(nx.ancestors(self._activities_graph, a))
        return ancestors


    def clear(self) -> None:
        '''Clears all activities data.'''

        self._activities_graph.clear()
        self._slug_to_activity.clear()


    def __len__(self) -> int:
        '''Size of activities registry.'''

        return len(self._slug_to_activity)
    

    @classmethod
    def from_dict(cls, data: dict) -> Activities:
        '''Constructs activities registry from dictionary.'''
        
        activities = cls()

        # Load activities.
        for slug, item in data.items():
            if not isinstance(item, dict):
                raise ValueError('Each activity entry must be a mapping.')

            activity = Activity.from_dict(slug, item)
            activities.add_activity(activity)

        # Load connections.
        connections = []

        for slug, item in data.items():
            parents = item.get('parents', [])
            if parents is None:
                parents = []

            if isinstance(parents, str) or not isinstance(parents, Iterable):
                raise ValueError(f'\'parents\' of \'{slug}\' must be an iterable of strings.')

            child = activities.activity_by_slug(slug)

            for parent_slug in parents:
                if not isinstance(parent_slug, str):
                    raise ValueError(f'The parent slug \'{parent_slug}\' must be a string.')

                parent = activities.activity_by_slug(parent_slug)
                connections.append((parent, child))
            
        activities.add_connections(connections)

        return activities
        

    @classmethod
    def from_yaml(cls, filename: str) -> Activities:
        '''Constructs activities registry from YAML file.
        
        The root of the YAML file must be 'activities'.'''

        try:
            path = Path(filename)

            with path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                raise ValueError('YAML root must be a mapping.')

            activities_data = data.get('activities')
            if not isinstance(activities_data, dict):
                raise ValueError('\'activities\' must be a mapping.')
            
            return Activities.from_dict(activities_data)
        
        except FileNotFoundError as e:
            raise FileNotFoundError(f'File not found: {filename}.') from e
        
        except yaml.YAMLError as e:
            raise ValueError(f'Invalid YAML: {e}.') from e