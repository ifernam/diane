import datetime
from collections.abc import Collection
from operator import itemgetter
from enum import Enum
import typer
from pathlib import Path
import yaml
import click
import os
from collections import defaultdict
import plotext as plt
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.console import Group
from rich import box
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from sortedcontainers import SortedList

from diane.temporal import Timestamp, TimeInterval, TimeSet
from diane.activities import Activity
from diane.sessions import Session
from diane.repository import UnknownActivityError
from diane.repository_manager import (
    RepositoryManager,
    NoActivitiesProvided,
    ActivityAlreadyTracked,
    AncestorActivities,
    AncestorActivitiesTracked
)



class NoRepositoryError(Exception):
    '''The repository was not found.'''
    pass



class SessionsPeriod(str, Enum):
    yesterday = 'yesterday'
    today = 'today'
    week = 'week'
    month = 'month'
    year = 'year'
    all = 'all'



app = typer.Typer()
console = Console(force_terminal=True)



def _find_repo_root() -> Path | None:
    '''Return the nearest ancestor directory containing `.diane/`.

    Returns `None` when the current working directory is not inside
    a Diane repository.
    '''

    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / '.diane').is_dir():
            return parent
    return None


def _load_yaml_mapping(path: Path) -> dict:
    '''Load a YAML file as a mapping.

    Returns an empty dictionary if the file is missing, unreadable,
    invalid YAML, or contains a top-level value other than a mapping.
    '''

    if not path.exists():
        return {}

    try:
        with path.open(encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


def _defined_activity_slugs(repo_root: Path) -> set[str]:
    '''Return activity slugs declared
    in `.diane/data/activities.yaml`.'''

    data = _load_yaml_mapping(repo_root / '.diane' / 'data' / 'activities.yaml')
    activities = data.get('activities', {})
    if not isinstance(activities, dict):
        return set()
    return set(activities.keys())


def _tracked_activity_slugs(repo_root: Path) -> set[str]:
    '''Return activity slugs present in `.diane/tracking.yaml`.'''

    data = _load_yaml_mapping(repo_root / '.diane' / 'tracking.yaml')
    tracking = data.get('tracking', {})
    if not isinstance(tracking, dict):
        return set()
    return set(tracking.keys())


def complete_activity_slugs_start(incomplete: str) -> list[str]:
    '''Return completion candidates for `start` and `do`.

    Suggestions include defined activity slugs that are not currently
    tracked. If the repository metadata cannot be read, an empty list
    is returned.
    '''

    repo_root = _find_repo_root()
    if repo_root is None:
        return []

    available_slugs = _defined_activity_slugs(repo_root) - _tracked_activity_slugs(repo_root)
    return sorted(s for s in available_slugs if s.startswith(incomplete))


def complete_activity_slugs_stop(incomplete: str) -> list[str]:
    '''Return completion candidates for `cancel` and `stop`.

    Suggestions include currently tracked activity slugs that are still
    defined in the repository. If the repository metadata cannot be
    read, an empty list is returned.
    '''

    repo_root = _find_repo_root()
    if repo_root is None:
        return []

    tracked_slugs = _tracked_activity_slugs(repo_root) & _defined_activity_slugs(repo_root)
    return sorted(s for s in tracked_slugs if s.startswith(incomplete))


def get_repo(
    repo_dir: Path | str | None = None,
    load_sessions: bool = True,
    first_day: datetime.date | None = None,
    last_day: datetime.date | None = None
) -> RepositoryManager:
    """Helper to find the Diane repository for the current directory.

    Searches the current directory for the '.diane/' subdirectory.
    If found, returns a `RepositoryManager` for that directory.

    Args:
        repo_dir (Path | str | None): The directory of the repository.
            If `None`, the current working directory is used.
        load_sessions (bool): If `True`, load sessions from
            the repository. `True` by default.
        first_day (datetime.date | None): The first day to load sessions
            from. If `None`, the first day is the earliest day with
            sessions. Only taken into account if `load_sessions`
            is `True`.
        last_day (datetime.date | None): The last day to load sessions
            for. If `None`, the last day is the latest day with
            sessions. Only taken into account if `load_sessions`
            is `True`.

    Raises:
        `NoRepositoryError`: If no repository is found.
    """

    if repo_dir is None:
        repo_dir = Path.cwd()
    elif not isinstance(repo_dir, Path):
        repo_dir = Path(repo_dir)

    if (repo_dir / '.diane').exists():
        return RepositoryManager(
            repo_dir,
            load_sessions=load_sessions,
            first_day=first_day,
            last_day=last_day
        )

    raise NoRepositoryError


def complete_message(
    ctx: click.Context,
    incomplete: str
) -> list[str]:

    repo = get_repo()

    # Determine specified activities.
    activity_args = ctx.params.get('activities') or []
    if not activity_args:
        activity_args = [a for a in ctx.args if not a.startswith('-')]
    specified_activity_slugs = [a for a in activity_args if a in repo._activities]

    # If there is no incomplete input, return last message.
    if not incomplete:
        try:
            return [repo.last(None, *specified_activity_slugs).message]
        except KeyError:
            return []

    messages = set()
    for s in repo.iter_from_last(None, *specified_activity_slugs):
        if s.message and s.message.startswith(incomplete):
            messages.add(s.message)

    return sorted(messages)


def _timestamp_text(timestamp: Timestamp, date: bool = True) -> Text:

    elements = []
    if date:
        date_text = Text(timestamp.date_string, style='default')
        elements.append(date_text)
    time_text = Text(timestamp.time_iso(offset=False), style='bright_yellow')
    elements.append(time_text)
    ts_text = Text(' ').join(elements)

    return ts_text


def _timeset_text(timeset: TimeSet) -> Text:

    sep = Text(' ')

    start_date_text = Text(timeset.start.timestamp.date_string)
    start_time_text = Text(timeset.start.timestamp.time_iso(offset=False), style='bright_yellow')

    ts_text = Text.assemble(start_date_text, sep, start_time_text)

    if not timeset.is_point:
        start_end_sep = Text(' → ', style='default')
        ts_text.append(start_end_sep)

        if timeset.last_day != timeset.first_day:
            end_date_text = Text(timeset.end.timestamp.date_string)
            ts_text.append(end_date_text + sep)

        end_time_text = Text(
            timeset.end.timestamp.time_iso(offset=False), style='bright_yellow'
        )

        ts_text.append(end_time_text)

    return ts_text


def _session_panel(session: Session) -> Panel:

    header = _timeset_text(session.timeset)

    # Left panel.
    left_elements = []

    duration = session.timeset.duration

    if duration:
        duration_text = Text.assemble(
            Text('Duration:', style='grey62'),
            ' ',
            Text(str(duration), style='bright_yellow')
        )
        percentage_density = round(100 * session.timeset.density)
        density_text = Text.assemble(
            Text('Density:', style='grey62'),
            ' ',
            Text(f'{percentage_density}%', style='bright_yellow'),
        )

        left_elements.append(duration_text)
        left_elements.append(density_text)
        left_elements.append(Text())
    left_elements.extend([
        Text('Activities:', style='grey62'),
        *[Text(f'• {a.title}', style='italic #cdbef4')
            for a in sorted(session._activities, key=lambda a: a.title)]
    ])

    right_elements = []
    if session.message:
        right_elements.extend([
            Panel(
                Markdown(session.message),
                title=Text('Message', style='grey62'),
                title_align='left',
                border_style='grey42'
            )
        ])

    left = Group(*left_elements)
    right = Group(*right_elements)

    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row(left, right)

    return Panel(table, title=header, title_align='right', border_style='dim')


def _error_panel(content: Group, title: Text, padding=(0, 1)) -> Panel:
    return Panel(
        content, title=title, title_align='left', border_style='#fa5252',
        expand=True, padding=padding
    )


def _message_panel(content: Group, title: Text, padding=(0, 1)) -> Panel:
    return Panel(
        content, title=title, title_align='left', border_style='dim',
        expand=True, padding=padding
    )


def _unknown_activity_group(
    unknown_activity_slugs: Collection[str],
    recognised_activities: Collection[Activity],
    ask: bool = True
) -> Group:

    elements = []

    n = len(unknown_activity_slugs)
    if unknown_activity_slugs:
        if n == 1:
            elements.append(Text.from_markup(
                f'The provided activity slug '
                f'[#cdbef4]{next(iter(unknown_activity_slugs))}[/] '
                f'is [#fa5252]unknown[/].'
            ))
        else:
            elements.append(Text.from_markup(
                'Some provided activity slugs are [#fa5252]unknown[/]:'
            ))
            for i, slug in enumerate(unknown_activity_slugs):
                elements.append(Text.assemble(
                    Text(f'• {slug}', style='#cdbef4'),
                    Text('.') if i == n - 1 else Text(',')
                ))

    m = len(recognised_activities)
    if recognised_activities:
        elements.append(Text())
        if m == 1:
            activity = next(iter(recognised_activities))
            elements.append(Text.from_markup(
                'The activity '
                f'[#cdbef4]{activity.title}[/] '
                f'[grey62]({activity.slug})[/] '
                'have been [#5dae3c]recognised[/].'
            ))
        else:
            elements.append(Text.from_markup(
                'The following activities have been [#5dae3c]recognised[/]:'
            ))
            for i, activity in enumerate(recognised_activities):
                elements.append(Text.assemble(
                    Text(f'• {activity.title}', style='italic #cdbef4'),
                    Text(' '),
                    Text(f'({activity.slug})', style='grey62'),
                    Text('.') if i == m - 1 else Text(',')
                ))

        if ask:
            elements.append(Text())
            elements.append(Text.from_markup(
                'Do you want to start tracking the [#5dae3c]recognised[/]'
                f' activities?',
                style='bold'
            ))

    return Group(*elements)


def _already_tracked_group(
    provided_activities: Collection[Activity],
    already_tracked_data: dict[Activity, Timestamp],
    new_activities: Collection[Activity],
    ask: bool = True
) -> Group:

    elements = []

    n = len(already_tracked_data)
    # Inform the user about already tracked activities.
    if already_tracked_data:
        if n < len(provided_activities):
            if n == 1:
                activity = next(iter(already_tracked_data))
                elements.append(Text.from_markup(
                    f'The provided activity '
                    f'[italic #cdbef4]{activity.title}[/] '
                    f'[grey62]({activity.slug})[/] '
                    f'is [#fa5252]already being tracked[/].'
                ))
            else:
                elements.append(Text.from_markup(
                    'Some of the provided activities '
                    'are [#fa5252]already being tracked[/]:'
                ))
                for i, a in enumerate(sorted(already_tracked_data)):
                    ending = '.' if i == n - 1 else ','
                    elements.append(Text.from_markup(
                        f'• [italic #cdbef4]{a.title}[/] '
                        f'[grey62]({a.slug})[/]{ending}'
                    ))
        else:
            if n == 1:
                activity = next(iter(already_tracked_data))
                elements.append(Text.from_markup(
                    f'The provided activity '
                    f'[italic #cdbef4]{activity.title}[/] '
                    f'[grey62]({activity.slug})[/] is already being tracked.'
                ))
            else:
                elements.append(Text.from_markup(
                    'All of the provided activities are '
                    '[#fa5252]already being tracked[/].'
                ))

    # Inform the user about new activities that can be started.
    if new_activities:
        m = len(new_activities)

        # Add separator if there are already tracked activities.
        if already_tracked_data:
            elements.append(Text())

        if m == 1:
            activity = next(iter(new_activities))
            elements.append(Text.from_markup(
                f'The provided activity [italic #cdbef4]{activity.title}[/] '
                'is not yet being tracked and [#5dae3c]can be started[/].'
            ))

            if ask:
                elements.append(Text())
                elements.append(Text.from_markup(
                    'Do you want [#5dae3c]to start[/] tracking '
                    'the new activity?',
                    style='bold'
                ))
        else:
            elements.append(Text.from_markup(
                'The following activities have not yet been tracked '
                'and [#5dae3c]can be started[/]:'
            ))
            for i, a in enumerate(new_activities):
                ending = '.' if i == m - 1 else ','
                elements.append(Text.from_markup(
                    f'• [italic #cdbef4]{a.title}[/] '
                    f'[grey62]({a.slug})[/]{ending}'
                ))

            if ask:
                elements.append(Text())
                elements.append(Text.from_markup(
                    'Do you want [#5dae3c]to start[/] tracking '
                    'the new activities?',
                    style='bold'
                ))

    return Group(*elements)


def _already_tracked_panel(
    provided_activities: Collection[Activity],
    already_tracked_data: dict[Activity, Timestamp],
    new_activities: Collection[Activity]
) -> Panel:
    if already_tracked_data:
        if len(already_tracked_data) == 1:
            title = Text('The provided activity is already being tracked')
        else:
            title = Text(
                f'The {len(already_tracked_data)} activities provided '
                'are already being tracked'
            )
        return _error_panel(
            content=_already_tracked_group(
                provided_activities, already_tracked_data, new_activities
            ),
            title=title
        )
    else:
        return _message_panel(
            content=_already_tracked_group(
                provided_activities, already_tracked_data, new_activities
            ),
            title=Text('No activities are already being tracked')
        )


def _ancestor_activities_group(
    ancestor_to_descendants: dict[Activity, set[Activity]],
    ask: bool = True
) -> Group:
    """Create a `Group` of `Renderable` elements describing the ancestor
    activities.

    Args:
        ancestor_to_descendants (dict[Activity, set[Activity]]):
            A mapping from ancestor activities their descendant
            activities among the provided activities. Sorted by ancestor
            activity slugs and descendant activity slugs.
        ask (bool, optional): Whether to ask for confirmation before
            starting tracking. `True` by default.

    Returns:
        A `Group` of `Renderable` elements describing the ancestor
        activities.
    """

    elements = []

    if ancestor_to_descendants:
        if len(ancestor_to_descendants) == 1:
            # One ancestor activity.
            ancestor = next(iter(ancestor_to_descendants))
            if len(ancestor_to_descendants[ancestor]) == 1:
                # The ancestor activity has one descendant.
                descendant = next(iter(ancestor_to_descendants[ancestor]))
                elements.append(Text.from_markup(
                    f'The activity [italic #cdbef4]{ancestor.title}[/] is '
                    f'the [#fa5252]ancestor[/] of another provided activity '
                    f'[italic #cdbef4]{descendant.title}[/].',
                ))
            else:
                elements.append(Text.from_markup(
                    f'The activity [italic #fa5252]{ancestor.title}[/] is '
                    f'the [#fa5252]ancestor[/] of several other provided '
                    f'activities:'
                ))
                n = len(ancestor_to_descendants[ancestor])
                for i, descendant in enumerate(sorted(
                        ancestor_to_descendants[ancestor]
                )):
                    ending = '.' if i == n - 1 else ','
                    elements.append(Text.from_markup(
                        f'• [italic #cdbef4]{descendant.title}[/] '
                        f'[grey62]({descendant.slug})[/]{ending}'
                    ))
        else:
            elements.append(Text.from_markup(
                'Some of the provided activities '
                'are the [#fa5252]ancestors[/] of other provided ones.'
            ))
            elements.append(Text())

            # Create a table of ancestor activities and their
            # descendants.
            ancestors_table = Table(
                box=None, border_style='dim', expand=True
            )
            ancestors_table.add_column(
                Text('Ancestor', style='grey62'),
                style='italic #cdbef4', no_wrap=True
            )
            ancestors_table.add_column(
                Text('Descendants', style='grey62'),
                style='italic #cdbef4', no_wrap=True
            )
            ancestors_table.add_row('', '', '')
            n = len(ancestor_to_descendants)
            for i, (a, dd) in enumerate(ancestor_to_descendants.items()):
                for j, d in enumerate(dd):
                    ancestors_table.add_row(
                        Text.from_markup(f'{a.title} [grey62]({a.slug})[/]')
                            if j == 0 else Text(),
                        Text.from_markup(f'{d.title} [grey62]({d.slug})[/]'),
                    )
                if i != n - 1:
                    ancestors_table.add_row('', '', '')

            elements.append(ancestors_table)

        if ask:
            elements.append(Text())
            elements.append(Text(
                'Do you want to start tracking the provided ancestor '
                'activities instead their descendants?',
                style='bold'
            ))
    else:
        elements.append(Text(
            'No provided activities are ancestors of other provided ones.'
        ))

    return Group(*elements)


def _ancestor_activities_panel(
    ancestor_to_descendants: dict[Activity, set[Activity]], ask: bool = True
) -> Panel:
    """Create a `Panel` describing the ancestor activities.

    Args:
        ancestor_to_descendants (dict[Activity, set[Activity]]):
            A mapping from ancestor activities their descendant
            activities among the provided activities. Sorted by ancestor
            activity slugs and descendant activity slugs.
        ask (bool, optional): Whether to ask for confirmation before
            starting tracking. `True` by default.

    Returns:
        A `Panel` describing the ancestor activities.
    """

    if ancestor_to_descendants:
        if len(ancestor_to_descendants) == 1:
            title = Text('One ancestor activity among the provided activities')
        else:
            title = Text(
                f'{len(ancestor_to_descendants)} ancestor activities among '
                f'the provided activities'
            )
        return _error_panel(
            content=_ancestor_activities_group(ancestor_to_descendants, ask),
            title=title
        )
    else:
        return _message_panel(
            content=_ancestor_activities_group(ancestor_to_descendants, ask),
            title=Text('No ancestor activities among the provided activities')
        )


def _ancestor_activities_tracked_group(
    ancestor_to_descendants: dict[Activity, set[Activity]],
    descendant_to_ancestors: dict[Activity, set[Activity]],
    ask: bool = True
) -> Group:
    """Create a `Group` of `Renderable` elements describing
    the provided activities that are ancestors or descendants
    of already tracked activities.

    Args:
        ancestor_to_descendants (dict[Activity, set[Activity]]):
            The dictionary mapping each provided ancestor activities
            to the set of its descendant activities that have already
            been tracked. Sorted by ancestor activity slug.
        descendant_to_ancestors (dict[Activity, set[Activity]]):
            The dictionary mapping each provided descendant activities
            to the set of its ancestor activities that have already
            been tracked. Sorted by descendant activity slug.
        ask (bool, optional): Whether to ask for confirmation before
            starting tracking. `True` by default.

    Returns:
        A `Group` of `Renderable` elements describing the ancestor
        activities.
    """

    elements = []

    if ancestor_to_descendants or descendant_to_ancestors:
        if ancestor_to_descendants:
            n = len(ancestor_to_descendants)
            if n == 1:
                # One provided activity is an ancestor of already tracked
                # activities.
                ancestor = next(iter(ancestor_to_descendants))
                m = len(ancestor_to_descendants[ancestor])
                if m == 1:
                    # The ancestor activity has one already tracked
                    # descendant.
                    descendant = next(iter(ancestor_to_descendants[ancestor]))
                    elements.append(Text.from_markup(
                        f'The provided activity '
                        f'[italic #cdbef4]{ancestor.title}[/] '
                        f'is the [#fa5252]ancestor[/] '
                        f'of the already tracked activity '
                        f'[italic #cdbef4]{descendant.title}[/].',
                    ))
                else:
                    elements.append(Text.from_markup(
                        f'The provided activity '
                        f'[italic #fa5252]{ancestor.title}[/] '
                        f'is the [#fa5252]ancestor[/] '
                        f'of several already tracked activities:'
                    ))
                    for i, descendant in enumerate(sorted(
                            ancestor_to_descendants[ancestor]
                    )):
                        ending = '.' if i == m - 1 else ','
                        elements.append(Text.from_markup(
                            f'• [italic #cdbef4]{descendant.title}[/] '
                            f'[grey62]({descendant.slug})[/]{ending}'
                        ))
            else:
                elements.append(Text.from_markup(
                    'Some of the provided activities '
                    'are the [#fa5252]ancestors[/] of already tracked ones.'
                ))
                elements.append(Text())

                # Create a table of ancestor activities and their
                # descendants.
                ancestors_table = Table(
                    box=None, border_style='dim', expand=True
                )
                ancestors_table.add_column(
                    Text('Ancestor', style='grey62'),
                    style='italic #cdbef4', no_wrap=True
                )
                ancestors_table.add_column(
                    Text('Descendants', style='grey62'),
                    style='italic #cdbef4', no_wrap=True
                )
                ancestors_table.add_row('', '', '')
                for i, (a, dd) in enumerate(ancestor_to_descendants.items()):
                    for j, d in enumerate(dd):
                        ancestors_table.add_row(
                            Text.from_markup(f'{a.title} [grey62]({a.slug})[/]')
                                if j == 0 else Text(),
                            Text.from_markup(f'{d.title} [grey62]({d.slug})[/]'),
                        )
                    if i != n - 1:
                        ancestors_table.add_row('', '', '')

                elements.append(ancestors_table)

        if descendant_to_ancestors:
            # Add separator if there are also provided activities that
            # are ancestors of already tracked activities.
            if ancestor_to_descendants:
                elements.append(Text())

            n = len(descendant_to_ancestors)
            if n == 1:
                # One provided activity is a descendant of already tracked
                # activities.
                descendant = next(iter(descendant_to_ancestors))
                m = len(descendant_to_ancestors[descendant])
                if m == 1:
                    # The descendant activity has one already tracked
                    # ancestor.
                    ancestor = next(iter(descendant_to_ancestors[descendant]))
                    elements.append(Text.from_markup(
                        f'The provided activity '
                        f'[italic #cdbef4]{descendant.title}[/] '
                        f'is the [#fa5252]descendant[/] '
                        f'of the already tracked activity '
                        f'[italic #cdbef4]{ancestor.title}[/].',
                    ))
                else:
                    elements.append(Text.from_markup(
                        f'The provided activity '
                        f'[italic #cdbef4]{descendant.title}[/] '
                        f'is the [#fa5252]descendant[/] '
                        f'of several already tracked activities:'
                    ))
                    for i, ancestor in enumerate(sorted(
                            descendant_to_ancestors[descendant]
                    )):
                        ending = '.' if i == m - 1 else ','
                        elements.append(Text.from_markup(
                            f'• [italic #cdbef4]{ancestor.title}[/] '
                            f'[grey62]({ancestor.slug})[/]{ending}'
                        ))
            else:
                elements.append(Text.from_markup(
                    'Some of the provided activities '
                    'are the [#fa5252]descendants[/] of already tracked ones.'
                ))
                elements.append(Text())

                # Create a table of descendant activities and their
                # ancestors.
                descendants_table = Table(
                    box=None, border_style='dim', expand=True
                )
                descendants_table.add_column(
                    Text('Descendant', style='grey62'),
                    style='italic #cdbef4', no_wrap=True
                )
                descendants_table.add_column(
                    Text('Ancestors', style='grey62'),
                    style='italic #cdbef4', no_wrap=True
                )
                descendants_table.add_row('', '', '')
                for i, (d, aa) in enumerate(descendant_to_ancestors.items()):
                    for j, a in enumerate(aa):
                        descendants_table.add_row(
                            Text.from_markup(f'{d.title} [grey62]({d.slug})[/]')
                                if j == 0 else Text(),
                            Text.from_markup(f'{a.title} [grey62]({a.slug})[/]'),
                        )
                    if i != n - 1:
                        descendants_table.add_row('', '', '')

                elements.append(descendants_table)

        if ask:
            elements.append(Text())
            elements.append(Text(
                'Do you want to start tracking only the provided activities '
                'that are not ancestors or descendants of already tracked '
                'ones?',
                style='bold'
            ))
    else:
        elements.append(Text(
            'No provided activities are ancestors or descendants of already '
            'tracked ones.'
        ))

    return Group(*elements)


def ancestor_activities_tracked_panel(
    ancestor_to_descendants: dict[Activity, set[Activity]],
    descendant_to_ancestors: dict[Activity, set[Activity]],
    ask: bool = True
) -> Panel:
    if ancestor_to_descendants or descendant_to_ancestors:
        title = Text(
            'Some provided activities are ancestors or descendants of already '
            'tracked activities'
        )
        return _error_panel(
            content=_ancestor_activities_tracked_group(
                ancestor_to_descendants, descendant_to_ancestors, ask
            ),
            title=title
        )
    else:
        return _message_panel(
            content=_ancestor_activities_tracked_group(
                ancestor_to_descendants, descendant_to_ancestors, ask
            ),
            title=Text(
                'No provided activities are ancestors or descendants '
                'of already tracked activities'
            )
        )


def _start_group(start_result: RepositoryManager.StartResult) -> Group:

    elements = []

    if start_result.activities:
        n = len(start_result.activities)
        if n == 1:
            activity = next(iter(start_result.activities))
            elements.append(Text.from_markup(
                f'The activity [italic #cdbef4]{activity.title}[/] '
                f'[grey62]({activity.slug})[/] has started being tracked '
                'at [bright_yellow]'
                f'{start_result.timestamp.time_iso(offset=False)}'
                '[/] '
                f'on {start_result.timestamp.date_string}.',
            ))
        else:
            elements.append(Text('The activities'))
            for i, a in enumerate(sorted(
                    start_result.activities, key=lambda ac: ac.title
            )):
                ending = '' if i == n - 1 else ','
                elements.append(Text.from_markup(
                    f'• [italic #cdbef4]{a.title}[/] '
                    f'[grey62]({a.slug})[/]{ending}'
                ))
            elements.append(Text.from_markup(
                f'began to be tracked at [bright_yellow]'
                f'{start_result.timestamp.time_iso(offset=False)}'
                f'[/] on {start_result.timestamp.date_string}.'
            ))
    else:
        elements.append(Text('No activities have started being tracked.'))

    return Group(*elements)


def _start_panel(start_result: RepositoryManager.StartResult) -> Panel:
    if not start_result.activities:
        title = Text('No activities started')
    elif len(start_result.activities) == 1:
        title = Text.from_markup('Started tracking one activity')
    else:
        title = Text(
            f'Started tracking {len(start_result.activities)} activities'
        )
    return Panel(
        _start_group(start_result),
        title=title,
        title_align='left',
        border_style='dim',
        expand=True
    )


@app.command()
def init():
    """Initialise a new Diane repository.

    Creates:
    - the '.diane/' directory in the current working directory (means
      that the repository is initialised);
    - activities subdirectory with Markdown activities notes;
    - empty '.diane/tracking.yaml' file.
    """

    # Determine paths.
    package_dir = Path(__file__).parent
    repo_dir = Path.cwd()
    diane_dir = repo_dir / '.diane'

    # Check if already initialised. Create '.diane/' if not, otherwise
    # exit with message.
    try:
        get_repo(repo_dir)
        console.print(_message_panel(
            Group(Text('The repository has already been initialized.')),
            Text('Already initialized')
        ))
        return
    except NoRepositoryError as e:
        # Initialise a new repository.
        # Create Diane ('.diane') subdirectory.
        diane_dir.mkdir(exist_ok=True)

        # Create activity notes from template.
        activities = RepositoryManager.read_activities_from_yaml(
            package_dir / 'data' / 'activities.yaml'
        )
        activities_dir = repo_dir / 'diane_activities'
        RepositoryManager.save_activity_notes_to(activities, activities_dir)


        # Create 'tracking.yaml'.
        diane_dir.joinpath('tracking.yaml').write_text('tracking: {}\n')

        console.print(_message_panel(
            Group(Text('A new empty repository has been initialized.')),
            Text('Initialised new empty repository.')
        ))


@app.command()
def status() -> None:
    """Show currently tracked activities.

    Shows currently tracked activities with their start timestamp
    and duration.
    """

    repo = get_repo(load_sessions=False)
    tracking_state = repo.tracking_state
    n = len(tracking_state)

    if not tracking_state:
        console.print(_message_panel(
            content=Group(Text('No activities are currently being tracked.')),
            title=Text('No activities tracked'),
        ))
        return

    tracking_activities_table = Table(
        box=None, border_style='dim', expand=True
    )
    tracking_activities_table.add_column(
        Text('Activity', style='grey62'),
        style='italic #cdbef4', no_wrap=True
    )
    tracking_activities_table.add_column(
        Text('Started', style='grey62'),
        style='bright_yellow', justify='right', no_wrap=True
    )
    tracking_activities_table.add_column(
        Text('Duration', style='grey62'),
        style='bright_yellow', justify='right', no_wrap=True
    )

    tracking_activities_table.add_row('', '', '')

    # Group tracking activities by start timestamps.
    grouped_tracked_activities = defaultdict(SortedList)
    for a, t in sorted(repo.tracking_state.items(), key=itemgetter(1)):
        grouped_tracked_activities[t].add(a)
    m = len(grouped_tracked_activities)

    now = Timestamp.now().round_to_second()

    # Add activities to table.
    for i, (t, aa) in enumerate(grouped_tracked_activities.items()):
        duration = now - t
        start_text = _timestamp_text(
            t, date=(t.datetime.date() != now.datetime.date())
        )
        duration_text = Text(str(duration))
        for j, a in enumerate(aa):
            title_text = Text.assemble(
                Text(a.title),
                Text(' '),
                Text(f'({a.slug})',style='not italic grey62')
            )
            tracking_activities_table.add_row(
                title_text,
                start_text if j == 0 else Text(),
                duration_text if j == 0 else Text()
            )
        if m < n and i != m - 1:
            tracking_activities_table.add_row('', '', '')

    console.print(_message_panel(
        content=Group(tracking_activities_table),
        title=Text('Tracking activities'),
        padding=0
    ))


@app.command()
def start(
    activities: list[str] = typer.Argument(
        ...,
        help='Activity slugs to start tracking.',
        autocompletion=complete_activity_slugs_start
    ),
    at: str | None = typer.Option(
        None,
        '--at',
        help=(
            'Specify the start time for tracking the activities. '
            'If not provided, the current time is used. The time '
            'should be in ISO format (e.g., \'2024-06-01T14:30:00\', '
            '\'14:30\').'
        )
    )
) -> None:
    """Start tracking the given activities from the current time.

    To improve performance, sessions haven't been loaded.

    Args:
        activities (list[str]): The slugs of the activities to start
            tracking.
        at (str | None): The start time for tracking the activities.
            If left unspecified, the current time is used.
    """

    def _try_start(
        *activity_slugs: str, timestamp: Timestamp
    ) -> RepositoryManager.StartResult:
        try:
            manager = get_repo(load_sessions=False)
        except NoRepositoryError:
            console.print(_error_panel(
                content=Group(Text('No Diane repository has been found.')),
                title=Text('No repository')
            ))
            return RepositoryManager.StartResult([], timestamp)

        try:
            return manager.start(*activity_slugs, timestamp=timestamp)
        except NoActivitiesProvided:
            console.print(_error_panel(
                content=Group(Text('No activities provided to start.')),
                title=Text('No activities')
            ))
            return RepositoryManager.StartResult([], timestamp)
        except UnknownActivityError as e:
            if e.recognised_activities:
                console.print(_error_panel(
                    _unknown_activity_group(
                        e.unknown_slugs, e.recognised_activities),
                    Text('Unknown activities')
                ))
                if Confirm.ask(default=True, console=console):
                    return _try_start(
                        *(a.slug for a in e.recognised_activities),
                        timestamp=timestamp
                    )
                else:
                    return RepositoryManager.StartResult([], timestamp)
            else:
                if len(e.provided_slugs) == 1:
                    console.print(_error_panel(
                        Group(Text.from_markup(
                            'The provided activity slug '
                            f'[#cdbef4]{next(iter(e.provided_slugs))}[/] '
                            'was [#fa5252]not recognized[/].')),
                        Text('Unknown activity')
                    ))
                else:
                    console.print(_error_panel(
                        Group(Text.from_markup(
                            '[#fa5252]None[/] of the provided activity slugs '
                            'are [#fa5252]recognised[/].'
                        )),
                        Text('Unknown activities')
                    ))
                return RepositoryManager.StartResult([], timestamp)
        except ActivityAlreadyTracked as e:
            # Inform the user about already tracked activities.
            console.print(_already_tracked_panel(
                e.provided_activities, e.already_tracked_data, e.new_activities
            ))

            # If there are new activities that can be started, ask
            # the user if they want to start them.
            if e.new_activities:
                if Confirm.ask(default=True, console=console):
                    return _try_start(
                        *(a.slug for a in e.new_activities),
                        timestamp=timestamp
                    )

            return RepositoryManager.StartResult([], timestamp)
        except AncestorActivities as e:
            console.print(_ancestor_activities_panel(
                e.ancestor_to_descendants
            ))

            # If there are ancestor activities, ask the user if they
            # want to start tracking them instead of their descendants.
            if e.ancestor_to_descendants:
                if Confirm.ask(default=True, console=console):
                    descendants = (
                        manager._activities.descendants(*e.provided_activities)
                    )
                    slugs = (
                        a.slug for a in e.provided_activities
                        if a not in descendants
                    )
                    return _try_start(*slugs, timestamp=timestamp)

            return RepositoryManager.StartResult([], Timestamp.now())
        except AncestorActivitiesTracked as e:
            console.print(ancestor_activities_tracked_panel(
                e.ancestor_to_descendants, e.descendant_to_ancestors
            ))

            # If there are provided activities that are ancestors
            # or descendants of already tracked activities, ask the user
            # if they want to start tracking only the provided
            # activities that are not ancestors or descendants
            # of already tracked ones.
            if e.ancestor_to_descendants or e.descendant_to_ancestors:
                if Confirm.ask(default=True, console=console):
                    ancestor_descendant_activities = (
                            set(e.ancestor_to_descendants)
                            | set(e.descendant_to_ancestors)
                    )
                    slugs = (
                        a.slug for a in e.provided_activities
                        if a not in ancestor_descendant_activities
                    )
                    return _try_start(*slugs, timestamp=timestamp)

            return RepositoryManager.StartResult([], timestamp)
        except Exception as e:
            raise click.ClickException(
                f'Error starting activities. {e}'
            ) from e

    if at is not None:
        try:
            ts = Timestamp.from_iso(at)
        except ValueError:
            console.print(_error_panel(
                content=Group(Text.from_markup(
                    'The provided time is not in a valid ISO format. '
                    'Please provide the time in ISO format '
                    '(e.g., \'2024-06-01T14:30:00\', \'14:30\').'
                )),
                title=Text('Invalid time format')
            ))
            return
    else:
        ts = Timestamp.now().round_to_second()

    start_result = _try_start(*activities, timestamp=ts)
    if start_result.activities:
        console.print(_start_panel(start_result))


@app.command()
def cancel(
    activities: list[str] | None = typer.Argument(
        None,
        help='Activities to cancel.',
        autocompletion=complete_activity_slugs_stop
    ),
    all_: bool = typer.Option(
        False,
        '-a', '--all',
        help='Cancel all currently tracked activities.'
    )
) -> None:
    """Cancel tracking the given activities.

    To improve performance, sessions haven't been loaded.

    Args:
        activities (list[str] | None): The slugs of the activities
            to cancel.
        all_ (bool): If the '-a'/'--all' flag is used, all currently
            tracked activities are cancelled, regardless
            of the 'activities' argument. Uses a trailing underscore
            to avoid shadowing the built-in `all`.
    """

    repo = get_repo(load_sessions=False)

    if not all_ and not activities:
        raise typer.BadParameter(
            'specify at least one activity to cancel or use -a/--all.',
            param_hint='ACTIVITIES'
        )

    try:
        cancelled = repo.cancel(*(activities or []), all=all_)
        if cancelled:
            header = Text.assemble(
                Text(f'Cancelled ('),
                Text(f'{len(cancelled)}', style='#cdbef4'),
                Text(')')
            )
            elements = []
            for a in sorted(cancelled, key=lambda a: a.title):
                elements.append(Text(f'• {a.title}', style='italic #cdbef4'))

            console.print(
                Panel(
                    Group(*elements), title=header, title_align='left', style='dim', expand=True
                )
            )

        else:
            if not repo._tracking_state:
                raise click.ClickException('No activities are currently being tracked.')
            else:
                raise typer.BadParameter(
                    'no matching activities to cancel.',
                    param_hint='ACTIVITIES'
                )
    except ValueError as e:
        raise click.ClickException(f'Error cancelling activities. {e}')


@app.command()
def stop(
    activities: list[str] | None = typer.Argument(
        None,
        help='Activity slugs to stop tracking.',
        autocompletion=complete_activity_slugs_stop
    ),
    at: str | None = typer.Option(
        None,
        '--at',
        help=(
            'Specify the end time for stopping tracking the activities. '
            'If not provided, the current time is used. The time '
            'should be in ISO format (e.g., \'2024-06-01T14:30:00\', '
            '\'14:30\').'
        )
    ),
    all_: bool = typer.Option(
        False, '-a', '--all', help='Stop all tracked activities.'
    ),
    message: str = typer.Option(
        '', '-m', '--message',
        help='Optional message to attach to the session(s).',
        autocompletion=complete_message
    )
) -> None:
    """Stop tracking activities.

    Stops tracking the specified activities.

    - If the '--all' flag is used, all currently tracked activities
      are stopped, regardless of the 'activities' argument.
    """

    if at is not None:
        try:
            ts = Timestamp.from_iso(at)
        except ValueError:
            console.print(_error_panel(
                content=Group(Text.from_markup(
                    'The provided time is not in a valid ISO format. '
                    'Please provide the time in ISO format '
                    '(e.g., \'2024-06-01T14:30:00\', \'14:30\').'
                )),
                title=Text('Invalid time format')
            ))
            return
    else:
        ts = Timestamp.now().round_to_second()
    current_day = ts.datetime.date()
    first_day = current_day - datetime.timedelta(days=1)
    last_day = current_day + datetime.timedelta(days=1)

    repo = get_repo(first_day=first_day, last_day=last_day)

    try:
        ss = repo.stop(
            *(activities or []), timestamp=ts, all=all_, message=message
        )
    except ValueError as e:
        raise click.ClickException(f'Error stopping activities. {e}')

    if not ss:
        console.print(Panel(
            Text('No sessions were recorded.'),
            border_style='dim',
            expand=True
        ))
        return

    console.print(Text(f'Recorded ({len(ss)}):'))
    elements = []
    for s in ss:
        elements.append(_session_panel(s))
    console.print(Group(*elements))


@app.command()
def do(
    activities: list[str] = typer.Argument(
        ...,
        help='Activity slugs to start.',
        autocompletion=complete_activity_slugs_start
    ),
    at: str | None = typer.Option(
        None,
        '--at',
        help=(
            'Specify the activities time. If not provided, the current '
            'time is used. The time should be in ISO format '
            '(e.g., \'2024-06-01T14:30:00\', \'14:30\').'
        )
    ),
    message: str = typer.Option(
        '', '-m', '--message',
        help='Optional message to attach to the session.',
        autocompletion=complete_message
    )
) -> None:
    """Create a point session with the given activities.

    Args:
        activities: List of activity slugs to include in the session.
        at: Use the option '--at' to specify the time at which to create
            the session. If not provided, the current time is used.
        message: Use the option '-m'/'--message' to specify an optional
            message to attach to the session. If not provided, an empty
            message will be attached.
    """

    if at is not None:
        try:
            t = Timestamp.from_iso(at)
        except ValueError:
            console.print(_error_panel(
                content=Group(Text.from_markup(
                    'The provided time is not in a valid ISO format. '
                    'Please provide the time in ISO format '
                    '(e.g., \'2024-06-01T14:30:00\', \'14:30\').'
                )),
                title=Text('Invalid time format')
            ))
            return
    else:
        t = Timestamp.now().round_to_second()
    d = t.datetime.date()

    repo = get_repo(first_day=d, last_day=d)

    try:
        session = repo.do(*activities, timestamp=t, message=message)
    except ValueError as e:
        console.print(_error_panel(
            content=Group(Text.from_markup(f'Error doing activities. {e}')),
            title=Text('Error')
        ))
        return

    header = Text.assemble(
        Text(f'Done ('),
        Text(f'{len(session.activities)}', style='#cdbef4'),
        Text(')')
    )
    elements = []
    for a in sorted(session.activities, key=lambda a: a.title):
        elements.append(Text(f'• {a.title}', style='italic #cdbef4'))

    console.print(
        Panel(
            Group(*elements), title=header,
            title_align='left', border_style='dim', expand=True
        )
    )


@app.command()
def activities() -> None:
    """Show available activities."""

    repo = get_repo()

    for i, activity in enumerate(
        sorted(repo.activities, key=lambda a: a.title)
    ):
        console.print(Text.from_markup(
            f'{i + 1}) [italic #cdbef4]{activity.title}[/] '
            f'[grey62]({activity.slug})[/].')
        )


@app.command()
def sessions(
    today: bool = typer.Option(False, '-t', '--today', help='Show today\'s sessions.'),
    yesterday: bool = typer.Option(False, '--yesterday', help='Show yesterday\'s sessions.'),
    week: bool = typer.Option(False, '-w', '--week', help='Show this week\'s sessions.'),
    month: bool = typer.Option(False, '-m', '--month', help='Show this month\'s sessions.'),
    year: bool = typer.Option(False, '-y', '--year', help='Show this year\'s sessions.'),
    all_: bool = typer.Option(False, '-a', '--all', help='Show all sessions.'),
    gantt: bool = typer.Option(False, '-g', '--gantt', help='Show gantt diagram.')
):
    '''Show recorded sessions.'''

    repo = get_repo()

    # Determine target.
    periods = [
        period
        for period, enabled in {
            SessionsPeriod.today: today,
            SessionsPeriod.yesterday: yesterday,
            SessionsPeriod.week: week,
            SessionsPeriod.month: month,
            SessionsPeriod.year: year,
            SessionsPeriod.all: all_
        }.items()
        if enabled
    ]
    if not periods:
        periods = [SessionsPeriod.all]
    interval_by_period = {
        SessionsPeriod.today: TimeInterval.today(),
        SessionsPeriod.yesterday: TimeInterval.yesterday(),
        SessionsPeriod.week: TimeInterval.week(),
        SessionsPeriod.month: TimeInterval.month(),
        SessionsPeriod.year: TimeInterval.year(),
        SessionsPeriod.all: TimeInterval.timeline()
    }
    target = TimeSet.union(*(interval_by_period[p] for p in periods))
    sessions_to_show = sorted(repo.iter_overlapping(target), key=lambda s: s.timeset.end, reverse=True)

    if gantt:
        pass
    else:
        os.environ.setdefault('PAGER', 'less -R')
        with console.pager(styles=True):
            for s in sessions_to_show:
                console.print(_session_panel(s))


@app.command()
def stats(
    today: bool = typer.Option(False, '-t', '--today', help='Show today\'s sessions.'),
    yesterday: bool = typer.Option(False, '--yesterday', help='Show yesterday\'s sessions.'),
    week: bool = typer.Option(False, '-w', '--week', help='Show this week\'s sessions.'),
    month: bool = typer.Option(False, '-m', '--month', help='Show this month\'s sessions.'),
    year: bool = typer.Option(False, '-y', '--year', help='Show this year\'s sessions.'),
    all_: bool = typer.Option(False, '-a', '--all', help='Show all sessions.')
) -> None:

    repo = get_repo()

    # Determine target.
    periods = [
        period
        for period, enabled in {
            SessionsPeriod.today: today,
            SessionsPeriod.yesterday: yesterday,
            SessionsPeriod.week: week,
            SessionsPeriod.month: month,
            SessionsPeriod.year: year,
            SessionsPeriod.all: all_
        }.items()
        if enabled
    ]
    if not periods:
        periods = [SessionsPeriod.all]
    interval_by_period = {
        SessionsPeriod.today: TimeInterval.today(),
        SessionsPeriod.yesterday: TimeInterval.yesterday(),
        SessionsPeriod.week: TimeInterval.week(),
        SessionsPeriod.month: TimeInterval.month(),
        SessionsPeriod.year: TimeInterval.year(),
        SessionsPeriod.all: TimeInterval.timeline()
    }
    target = TimeSet.union(*(interval_by_period[p] for p in periods))

    activity_to_timesets = defaultdict(set)
    main_activities = set()
    ancestor_activities = set()
    for s in repo.find_overlapping(target):
        clipped = s.timeset & target

        if clipped:
            main_activities_in_sessions = s.activities
            main_activities.update(main_activities_in_sessions)
            ancestor_activities_in_sessions = repo._activities.ancestors(*main_activities_in_sessions)
            ancestor_activities.update(ancestor_activities_in_sessions)
            for a in main_activities_in_sessions | ancestor_activities_in_sessions:
                activity_to_timesets[a].add(clipped)

    not_main_activities = ancestor_activities - main_activities

    activity_to_duration = {}
    activity_to_times = {}
    activity_to_longest_timeset = {}
    for a in main_activities | ancestor_activities:
        activity_timeset = TimeSet.union(*activity_to_timesets[a])
        activity_to_duration[a] = activity_timeset.duration
        activity_to_times[a] = activity_timeset.components_number
        activity_to_longest_timeset[a] = max(activity_to_timesets[a], key=lambda ts: ts.duration)

    main_activities_table = Table(border_style='dim', box=box.ROUNDED, expand=True)
    main_activities_table.add_column(
        Text('Activity', style='grey62'),
        style='italic #cdbef4', no_wrap=True, overflow='ellipsis', ratio=25
    )
    main_activities_table.add_column(
        Text('Total duration', style='grey62'),
        style='bright_yellow', justify='right', no_wrap=True, overflow='ellipsis', ratio=20
    )
    main_activities_table.add_column(
        Text('Times', style='grey62'),
        justify='right', no_wrap=True, overflow='ellipsis', ratio=10,
    )
    main_activities_table.add_column(
        Text('Longest session', style='grey62'),
        justify='right', no_wrap=True, overflow='ellipsis', ratio=50
    )

    for a in sorted(main_activities, key=lambda a: activity_to_duration[a], reverse=True):
        main_activities_table.add_row(
            a.title,
            str(activity_to_duration[a]),
            str(activity_to_times[a]),
            Text.assemble(_timeset_text(
                activity_to_longest_timeset[a]),
                Text(' ('),
                Text(str(activity_to_longest_timeset[a].duration), style='bright_yellow'),
                Text(')'),
            )
        )
    main_activities_table.add_section()
    for a in sorted(not_main_activities, key=lambda a: activity_to_duration[a], reverse=True):
        main_activities_table.add_row(
            Text(a.title, style='italic #8f81b4'),
            str(activity_to_duration[a]),
            str(activity_to_times[a]),
            Text.assemble(_timeset_text(
                activity_to_longest_timeset[a]),
                Text(' ('),
                Text(str(activity_to_longest_timeset[a].duration), style='bright_yellow'),
                Text(')'),
            )
        )

    os.environ.setdefault('PAGER', 'less -R')
    with console.pager(styles=True):
        console.print(main_activities_table)


@app.command()
def habits():
    try:
        repo = get_repo()
    except NoRepositoryError as e:
        console.print(_error_panel(
            content=Group(Text('No Diane repository has been found.')),
            title=Text('No repository')
        ))
        return

    mean_regularity_index = repo.habits()

    habits_table = Table(
        box=None, border_style='dim', expand=True
    )
    habits_table.add_column(
        Text('Activity', style='grey62'),
        style='italic #cdbef4', no_wrap=True
    )
    habits_table.add_column(
        Text('Regularity', style='grey62'),
        style='', no_wrap=True
    )

    habits_table.add_row('', '')

    # Add activities to table.
    n = len(mean_regularity_index)
    grouped_activities = any(len(aa) > 1 for aa in mean_regularity_index)
    for i, (aa, r) in enumerate(mean_regularity_index.items()):
        for j, a in enumerate(sorted(aa, key=lambda a: a.title)):
            title_text = Text.assemble(
                Text(a.title),
                Text(' '),
                Text(f'({a.slug})', style='not italic grey62')
            )
            p = round(100 * r)
            regularity_index_text = Text(f'{p}%') if j == 0 else Text()
            habits_table.add_row(
                title_text,
                regularity_index_text
            )
        if grouped_activities and i != n - 1:
            habits_table.add_row('', '')

    console.print(_message_panel(
        content=Group(habits_table),
        title=Text('Habits'),
        padding=0
    ))


@app.command()
def regularity(
    activities: list[str] = typer.Argument(
        ...,
        help='Plot a graph of the given activities regularity index.'
    )
):
    repo = get_repo()

    plt.clf()

    plot = repo.regularity_plot(*activities)

    plt.plot(
        plot.x,
        [plot.habit_threshold] * len(plot.x),
        color='gray',
        marker='dot',
        )

    plt.plot(
        plot.x,
        plot.y,
        color='blue',
        # fillx=True
    )

    plt.xticks(
        plot.tick_positions,
        plot.tick_labels,
    )

    plt.show()



if __name__ == '__main__':
    app()
