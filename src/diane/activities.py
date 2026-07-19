from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import MutableSet, Iterable
import networkx as nx
import yaml
from pathlib import Path
import re
import warnings



@dataclass(slots=True)
class Activity:
    """Represents a human activity.
    
    Attributes:
        slug: The unique string identifier for an activity. Cannot
            be changed. Format: lowercase letters, digits,
            and underscores (non-consecutive, not leading/trailing).
            Must contain at least one letter.
            
        title: The human-readable name of the activity. Can
            be changed.
        
        description: The activity description string. Can be changed.
            This may be empty if the activity is clearly understood from
            its name.
    """


    _SLUG_PATTERN = re.compile(r'^(?=.*[a-z])[a-z0-9]+(_[a-z0-9]+)*$')

    
    _slug: str
    title: str
    description: str = ''
    tags: list = field(default_factory=list)


    @classmethod
    def _validate_slug(cls, slug: str) -> None:
        if not cls._SLUG_PATTERN.fullmatch(slug):
            raise ValueError(f'Incorrect slug format: \'{slug}\'.')
        
    
    def _validate(self) -> None:
        Activity._validate_slug(self._slug)


    def __post_init__(self) -> None:
        self._validate()


    def __hash__(self) -> int:
        return hash(self._slug)
    

    def __eq__(self, other: object) -> bool:

        if not isinstance(other, Activity):
            return NotImplemented
        
        return self._slug == other._slug


    def __lt__(self, other: object) -> bool:

        if not isinstance(other, Activity):
            return NotImplemented

        return self._slug < other.slug
    

    def __str__(self) -> str:
        return self._slug
    

    @property
    def slug(self) -> str:
        """Return the unique string identifier (slug)
        of the activity.

        Returns:
            str: The unique string identifier (slug) of the activity.
        """

        return self._slug
    

    @classmethod
    def from_dict(cls, slug: str, data: dict) -> Activity:
        """Construct an activity from the dictionary.

        Slug must be specified as a separate argument.

        Args:
            slug (str): The unique identifier for the activity.
            data (dict): A dictionary containing the activity data.
                Expected keys:
                - 'title' (str, required): the human-readable name;
                - 'description' (str, optional): the description,
                    defaults to '';
                - 'tags' (list, optional): the tags for the activity;
                - 'parents' (list, optional): ignored, but may
                    be present.

        Returns:
            Activity: The newly created activity.

        Raises:
            ValueError: If the slug is invalid, or if the 'title' field
                is missing.
            TypeError: If 'title' or 'description' is not a string.

        Example:
            >>> Activity.from_dict('studying_algebra', {
            ... {
            ...    'title': 'Studying algebra',
            ...    'description': '',
            ...    'tags': ['diane_activity', 'logged'],
            ...    'parents': ['studying_math', 'studying']
            ... })

            >>> Activity.from_dict(
            ...     'listening_to_podcast',
            ...     {'title': 'Listening to a podcast'}
            ... )
        """

        # Check for extra fields in the activity dictionary.
        allowed_keys = {'title', 'description', 'tags', 'parents'}
        extra_keys = set(data) - allowed_keys
        if extra_keys:
            quoted_extra_keys = [f'\'{str(k)}\'' for k in sorted(extra_keys)]
            extra_keys_string = ', '.join(quoted_extra_keys)
            # TODO: log 'Activity dictionary corresponding to the slug
            # TODO: \'{slug}\' contains unknown fields:
            # TODO: {extra_keys_string}.',

        # Read the activity title.
        try:
            title = data['title']
        except KeyError as e:
            raise ValueError(
                f'Activity \'{slug}\' is missing required field \'title\'.'
            ) from e
        if not isinstance(title, str):
            raise TypeError(
                f'Field \'title\' of activity \'{slug}\' must be a string.'
            )

        # Read the activity description.
        description = data.get('description', '')
        if not isinstance(description, str):
            raise TypeError(
                f'Field \'description\' of activity \'{slug}\' must be '
                f'a string.'
            )

        # Read the activity tags.
        tags = data.get('tags', [])
        if isinstance(tags, str):
            tags = [tags]
        if not isinstance(tags, list):
            raise TypeError(
                f'Field \'tags\' of activity \'{slug}\' must be a list.'
            )

        return cls(
            _slug=slug,
            title=title,
            description=description,
            tags=tags
        )
    


class Activities(MutableSet[Activity]):
    """Registry of activities.
    
    In addition to the slugs, the titles of activities should also
    be unique within the registry. This is not a strict requirement, but
    rather a useful recommendation designed to avoid confusion.
    """


    _slug_to_activity: dict[str, Activity]
    _activities_graph: nx.DiGraph
    

    @staticmethod
    def _validate_graph(graph: nx.DiGraph) -> None:
        # Validates activities graph.

        # Check the graph for cycles.
        if not nx.is_directed_acyclic_graph(graph):
            cycle = nx.find_cycle(graph)
            activities_in_cycle = [edge[0] for edge in cycle] + [cycle[0][0]]
            activities_slugs_in_cycle = [f'\'{activity}\'' for activity in activities_in_cycle]
            cycle_string = ' -> '.join(activities_slugs_in_cycle)
            raise ValueError(f'Cycle detected: {cycle_string}.')

    
    def _validate(self) -> None:
        Activities._validate_graph(self._activities_graph)

        # Check for title duplicates.
        seen_titles = set()
        duplicates_titles = set()

        for activity in self._slug_to_activity.values():
            title = activity.title
            if title in seen_titles:
                duplicates_titles.add(title)
            else:
                seen_titles.add(title)

        if duplicates_titles:
            quoted_duplicates_titles = [f'\'{t}\'' for t in duplicates_titles]
            duplicates_string = ', '.join(quoted_duplicates_titles)
            warnings.warn(
                f'Duplicate activity titles detected: {duplicates_string}.',
                stacklevel=2
            )
        
        
    def __init__(self) -> None:
        """Create an empty activities registry."""

        self._slug_to_activity = {}
        self._activities_graph = nx.DiGraph()
        # self._validate()


    def resolve_activity(self, obj: Activity | str) -> Activity:
        """Check for an activity in the registry. If the activity
        is found, retrieves it by its slug.
        
        Raises:
            KeyError: If the activity is not in the registry.
            TypeError: If `obj` is neither an `Activity` nor a `str`.
        """

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
        '''Return `True` if the activity is contained in the registry.
        
        Only takes the slug into account.
        '''

        if isinstance(item, Activity):
            return item.slug in self._slug_to_activity
        
        if isinstance(item, str):
            return item in self._slug_to_activity
        
        return False
    

    def __iter__(self):
        '''Return an iterator over the activities in the registry.

        Returns:
            `iterator`: An iterator over `Activity` objects.
        '''

        return iter(self._slug_to_activity.values())


    def __len__(self) -> int:
        '''Return the size of the activities registry.
        
        Returns:
            `int`: The number of activities.
        '''

        return len(self._slug_to_activity)
    

    def add(self, value: Activity) -> None:
        '''Add the activity to the registry.

        Do nothing if the activity with the same slug already exists.
        Issue a warning if another activity already has the same title.

        Args:
            `value` (`Activity`): The activity to add.

        Warns:
            `UserWarning`: If the title duplicates an existing
                activity's title.
        '''

        if value.slug not in self._slug_to_activity:

            # Check for duplicate titles.
            for a in self._slug_to_activity.values():
                if value.title == a.title:
                    warnings.warn(
                        f'Duplicate activity title detected: \'{value.title}\'.',
                        stacklevel=2
                    )

            self._slug_to_activity[value.slug] = value
            self._activities_graph.add_node(value)
    

    def discard(self, value: Activity | str) -> None:
        '''Remove the activity from the registry if it exists.

        Args:
            `value` (`Activity | str`): The activity or its slug
                to remove.

        If the activity is not present, the method does nothing.
        '''
        
        try:
            activity = self.resolve_activity(value)
            self._activities_graph.remove_node(activity)
            del self._slug_to_activity[activity.slug]
        except KeyError:
            pass


    def remove(self, value: Activity | str) -> None:
        '''Remove the activity from the registry.

        Args:
            `value` (`Activity | str`): The activity or its slug
                to remove.

        Raises:
            `KeyError`: If the activity is not in the registry.
        '''
        
        try:
            activity = self.resolve_activity(value)
            self._activities_graph.remove_node(activity)
            del self._slug_to_activity[activity.slug]
        except KeyError as e:
            raise KeyError(f'The activity \'{value}\' is not in the registry.') from e


    def add_activities(self, activities: Iterable[Activity]) -> None:
        '''Add multiple activities to the registry.

        Args:
            `activities` (`Iterable[Activity]`): An iterable
                of `Activity` instances to add.

        Each activity is added individually; if an activity with
        the same slug already exists, it is silently ignored
        (as per `add` behavior). Duplicate titles will trigger
        a warning.
        '''
        
        for a in activities:
            self.add(a)


    def add_connection(self, parent: Activity | str, child: Activity | str) -> None:
        '''Add a parent -> child connection between activities.

        Safely add the connection validating for cycles. It is assumed
        that the activities themselves are already contained
        in the registry.

        Args:
            `parent` (`Activity | str`): The parent activity or its
                slug.
            `child` (`Activity | str`): The child activity or its slug.

        Raises:
            `KeyError`: If either activity is not found in the registry.
            `ValueError`: If adding the connection would create a cycle,
                or if parent and child are the same.
        '''

        parent = self.resolve_activity(parent)
        child = self.resolve_activity(child)

        if parent is child:
            raise ValueError(f'Self-loop is not allowed: {parent}.')

        if self._activities_graph.has_edge(parent, child):
            return    # Connection already exists.

        if nx.has_path(self._activities_graph, child, parent):
            raise ValueError(
                f'Adding connection \'{parent.slug}\' -> \'{child.slug}\' creates a cycle.'
            )

        self._activities_graph.add_edge(parent, child)


    def remove_connection(self, parent: Activity | str, child: Activity | str) -> None:
        '''Remove the parent -> child connection from the registry.

        Args:
            `parent` (`Activity | str`): The parent activity
                or its slug.
            `child` (`Activity | str`): The child activity or its slug.

        Raises:
            `KeyError`: If either activity is not found in the registry.

        If the connection does not exist, the method does nothing.
        '''

        parent = self.resolve_activity(parent)
        child = self.resolve_activity(child)

        if self._activities_graph.has_edge(parent, child):
            self._activities_graph.remove_edge(parent, child)


    def add_connections(
            self,
            connections: Iterable[tuple[Activity | str, Activity | str]]
        ) -> None:

        '''Add multiple parent-child connections.

        Safely add the collection of parent-child pairs, validating
        for cycles. It is assumed that the activities themselves
        are already contained in the registry.

        Args:
            `connections` \
            (`Iterable[tuple[Activity | str, Activity | str]]`):
                An iterable of `(parent, child)` pairs.

        Raises:
            `KeyError`: If any activity is not found in the registry.
            `ValueError`: If any connection would create a cycle,
                or if a parent and child are the same.
        '''

        tmp_activities_graph = self._activities_graph.copy()

        for p, c in connections:
            parent = self.resolve_activity(p)
            child = self.resolve_activity(c)
            
            if parent is child:
                raise ValueError(f'Self-loop is not allowed: {parent}.')
            
            if tmp_activities_graph.has_edge(parent, child):
                continue    # Connection already exists.

            tmp_activities_graph.add_edge(parent, child)

        Activities._validate_graph(tmp_activities_graph)

        self._activities_graph = tmp_activities_graph



    def activity_by_slug(self, slug: str) -> Activity:
        '''Retrieve an activity by its slug.

        Args:
            `slug` (`str`): The slug of the activity.

        Returns:
            `Activity`: The activity with the given slug.

        Raises:
            `KeyError`: If the activity with the specified slug
                is not found.
        '''

        try:
            return self._slug_to_activity[slug]
        except KeyError as e:
            raise KeyError(f'Unknown activity: \'{slug}\'.') from e
        

    def activity_to_dict(self, activity: Activity | str) -> dict:
        '''Convert the given activity to the dictionary representation.
        
        The resulting dictionary always contains the following key:
        - 'title' (`str`): the activity's title.
        
        The following keys are included only if non-empty:
        - 'description' (`str`): the activity's description, included
          only if it is not empty;
        - 'parents' (`list` of `str`): the slugs of the activity's
          parents, included only if there are any parents.

        Args:
            `activity` (`Activity | str`): The activity or its slug.

        Returns:
            `dict`: The dictionary representation of the activity.
        '''

        activity = self.resolve_activity(activity)
        data = {}
        data['title'] = activity.title
        if activity.description:
            data['description'] = activity.description
        parents = sorted(self.parents(activity), key=lambda a: a.slug)
        if parents:
            data['parents'] = [p.slug for p in parents]
        return data
        

    def parents(self, *activities: Activity | str) -> set[Activity]:
        '''Return the parents of the specified activities.

        Args:
            `*activities` (`Activity | str`): Variable number
                of activities or slugs.

        Returns:
            `set[Activity]`: A set of all direct parents of the given
                activities.
        '''

        resolved_activities = (self.resolve_activity(a) for a in activities)
        parents = set()
        for a in resolved_activities:
            parents.update(self._activities_graph.predecessors(a))
        return parents
    

    def ancestors(self, *activities: Activity | str) -> set[Activity]:
        '''Return all ancestors of the specified activities.

        Args:
            `*activities` (`Activity | str`): Variable number
                of activities or slugs.

        Returns:
            `set[Activity]`: A set of all ancestors (parents,
                grandparents, etc.) of the given activities.
        '''

        resolved_activities = (self.resolve_activity(a) for a in activities)
        ancestors = set()
        for a in resolved_activities:
            ancestors.update(nx.ancestors(self._activities_graph, a))
        return ancestors
    

    def children(self, *activities: Activity | str) -> set[Activity]:
        '''Return all children of the specified activities.

        Args:
            `*activities` (`Activity | str`): Variable number
                of activities or slugs.

        Returns:
            `set[Activity]`: A set of all direct children of the given
                activities.
        '''

        resolved = (self.resolve_activity(a) for a in activities)
        children = set()
        for a in resolved:
            children.update(self._activities_graph.successors(a))
        return children


    def descendants(self, *activities: Activity | str) -> set[Activity]:
        '''Return all descendants of the specified activities.

        Args:
            `*activities` (`Activity | str`): Variable number
                of activities or slugs.

        Returns:
            `set[Activity]`: A set of all descendants (children,
                grandchildren, etc.) of the given activities.
        '''

        resolved = (self.resolve_activity(a) for a in activities)
        descendants = set()
        for a in resolved:
            descendants.update(nx.descendants(self._activities_graph, a))
        return descendants
    

    def root_activities(self) -> set[Activity]:
        '''Return all activities that have no parents (roots).

        Returns:
            `set[Activity]`: A set of activities with in-degree zero.
        '''

        return {a for a in self._activities_graph.nodes
                if self._activities_graph.in_degree(a) == 0}


    def leaf_activities(self) -> set[Activity]:
        '''Return all activities that have no children (leaves).

        Returns:
            `set[Activity]`: A set of activities with out-degree zero.
        '''
        
        return {a for a in self._activities_graph.nodes
                if self._activities_graph.out_degree(a) == 0}


    def isolated_activities(self) -> set[Activity]:
        '''Return all activities that have neither parents nor children
        (isolated).

        Returns:
            `set[Activity]`: A set of activities with both in-degree
                and out-degree zero.
        '''

        return {a for a in self._activities_graph.nodes
                if self._activities_graph.in_degree(a) == 0
                and self._activities_graph.out_degree(a) == 0}


    def clear(self) -> None:
        '''Remove all activities and connections from the registry.'''

        self._activities_graph.clear()
        self._slug_to_activity.clear()
    

    def copy(self) -> Activities:
        """Create a shallow copy of the activities registry.

        Returns:
            Activities: A new `Activities` object containing the same
                activities and connections.
        """

        activities = Activities()
        activities._slug_to_activity = self._slug_to_activity.copy()
        activities._activities_graph = self._activities_graph.copy()
        return activities


    @classmethod
    def _from_iterable(cls, iterable) -> Activities:
        """Construct an Activities instance from an iterable of Activity
        objects.

        This method is used by MutableSet's set operations (`__and__`,
        `__or__`, etc.) to construct a new instance from an iterable.

        Args:
            iterable: An iterable of Activity objects.

        Returns:
            Activities: A new Activities instance containing
            the activities from the iterable.
        """

        activities = cls()
        for activity in iterable:
            activities.add(activity)
        return activities


    @classmethod
    def from_dict(cls, data: dict) -> Activities:
        '''Construct an activities registry from a dictionary.

        The dictionary should map activity slugs to their data
        dictionaries. Each data dictionary **must** contain a `'title'`
        key (`str`) and may optionally contain `'description'` (`str`)
        and `'parents'` (`list` of slugs) keys.

        Args:
            `data` (`dict`): A dictionary with slugs as keys
                and activity data dicts as values.

        Returns:
            `Activities`: A new `Activities` instance populated with
                the activities and connections.

        Raises:
            `ValueError`: If the data is malformed (e.g., missing title,
                invalid parent reference).
            `KeyError`: If a parent references a non-existent activity
                slug.
        '''
        
        activities = cls()

        # Load activities.
        for slug, item in data.items():
            if not isinstance(item, dict):
                raise ValueError('Each activity entry must be a mapping.')

            activity = Activity.from_dict(slug, item)
            activities.add(activity)

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
    def from_yaml(cls, filename: str | Path) -> Activities:
        '''Construct an activities registry from a YAML file.

        The YAML file must contain a top-level mapping with
        an 'activities' key, whose value is a dictionary mapping slugs
        to activity data.

        Args:
            `filename` (`str | Path`): Path to the YAML file.

        Returns:
            `Activities`: A new Activities instance.

        Raises:
            `FileNotFoundError`: If the file does not exist.
            `ValueError`: If the YAML content is invalid or does not
                conform to the expected structure.
            `KeyError`: If a parent references a non-existent activity
                slug.
        '''

        try:
            if isinstance(filename, str):
                path = Path(filename)
            else:
                path = filename

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
            raise ValueError(f'Invalid YAML file \'{filename}\': {e}.') from e