from textwrap import indent

from enum import Enum
import math
import typer
from pathlib import Path
import yaml
import click
import os
from collections import defaultdict
from itertools import chain
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.console import Group
from rich import box
from rich.rule import Rule
from rich.padding import Padding
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.table import Table
from rich.pager import SystemPager
import plotext as plt

from diane.temporal import Timestamp, Duration, TimeInterval, TimeSet
from diane.sessions import Session
from diane.repository_manager import RepositoryManager



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


def _matching_completions(slugs: set[str], incomplete: str) -> list[str]:
    '''Return sorted completion candidates matching `incomplete`.'''

    if incomplete:
        return sorted(slug for slug in slugs if slug.startswith(incomplete))
    return sorted(slugs)


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
    return _matching_completions(available_slugs, incomplete)


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
    return _matching_completions(tracked_slugs, incomplete)


def get_repo() -> RepositoryManager:
    '''Helper to find the Diane repository for the current directory.
    
    Searches the current directory and its parents for the '.diane/'
    directory. If found, returns a 'RepositoryManager' for that
    directory. If not found, prints an error message and exits with
    code 1.
    '''

    current = Path.cwd()
    for directory in [current, *current.parents]:
        if (directory / '.diane').exists():
            return RepositoryManager(str(directory))
    typer.echo('Error: not a Diane repository (no .diane/ found).')
    raise typer.Exit(code=1)


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


@app.command()
def init():
    '''Initialize a new Diane repository.
    
    Creates the '.diane/' directory in the current working directory,
    along with a 'data/activities.yaml' file initialized from
    the package template (if it exists) or as empty. Also creates
    the empty 'tracking.yaml' file.
    '''

    # Determine paths.
    package_dir = Path(__file__).parent
    diane_dir = Path.cwd() / '.diane'

    # Check if already initialized. Create '.diane/' if not, otherwise
    # exit with message.
    if diane_dir.exists():
        typer.echo('Already initialized.')
        return
    diane_dir.mkdir()

    # Initialize 'activities.yaml' with template if it doesn't exist,
    # otherwise reset to empty.
    repo_activities = Path(diane_dir / 'data' / 'activities.yaml')
    repo_activities.parent.mkdir(parents=True, exist_ok=True)
    template_activities = Path(package_dir / 'data' / 'activities.yaml')
    if template_activities.exists():
        repo_activities.write_text(template_activities.read_text())
    else:
        repo_activities.write_text('activities: []\n')

    # Initialize 'tracking.yaml' as empty.
    diane_dir.joinpath('tracking.yaml').write_text('tracking: {}\n')
    typer.echo('Initialized empty diane repository.')


@app.command()
def status():
    '''Show currently tracked activities.'''

    repo = get_repo()

    if not repo._tracking_state:
        console.print(Panel(
            Text('No activities are currently being tracked.'),
            border_style='dim',
            expand=True
        ))
        return

    tracking_activities_table = Table(border_style='dim', box=box.ROUNDED, expand=True)
    tracking_activities_table.add_column(
        Text('Activity', style='grey62'),
        style='italic #cdbef4', no_wrap=True, overflow='ellipsis'
    )
    tracking_activities_table.add_column(
        Text('Started', style='grey62'),
        style='bright_yellow', justify='right', no_wrap=True, overflow='ellipsis'
    )
    tracking_activities_table.add_column(
        Text('Duration', style='grey62'),
        style='bright_yellow', justify='right', no_wrap=True, overflow='ellipsis'
    )

    now = Timestamp.now().round_to_second()
    for a, t in sorted(repo._tracking_state.items(), key=lambda pair: pair[1]):
        duration = now - t
        title_text = Text.assemble(
            Text(a.title), ' ', Text(f'({a.slug})', style='not italic grey62')
        )
        tracking_activities_table.add_row(
            title_text,
            _timestamp_text(t, t.datetime.date()!=now.datetime.date()),
            str(duration)

        )

    console.print(tracking_activities_table)


@app.command()
def start(
    activities: list[str] = typer.Argument(
        ...,
        help='Activity slugs to start tracking.',
        autocompletion=complete_activity_slugs_start
    )
) -> None:
    '''Start tracking activities.
    
    Starts tracking the specified activities from the current time.
    If an activity is already being tracked, it is ignored. If any
    specified activities are not defined in the repository, an error
    message is printed and the command exits with code 1. Otherwise,
    a success message is printed listing the activities that were
    started.
    '''

    manager = get_repo()
    
    try:
        started_activities = manager.start(*activities)
    except ValueError as e:
        raise click.ClickException(f'Error starting activities. {e}')
    
    if not started_activities:
        console.print(Panel(
            Text('No activities to start tracking.'),
            border_style='dim',
            expand=True
        ))
        return
    
    header = Text.assemble(
        Text(f'Started ('),
        Text(f'{len(started_activities)}', style='#cdbef4'),
        Text(')')
    )
    elements = []
    for a in sorted(started_activities, key=lambda a: a.title):
        elements.append(Text(f'• {a.title}', style='italic #cdbef4'))
    
    console.print(Panel(
        Group(*elements), title=header, title_align='left', border_style='dim', expand=True
    ))
    

@app.command()
def cancel(
    activities: list[str] | None = typer.Argument(
        None, help='Activities to cancel.', autocompletion=complete_activity_slugs_stop
    ),
    all_: bool = typer.Option(
        False, '-a', '--all', help='Cancel all currently tracked activities.'
    )
) -> None:
    '''Cancel tracking the specified activities.

    Note:
        The parameter `all_` uses a trailing underscore to avoid
        shadowing the built-in `all`.

    - If the '-a'/'--all' flag is used, all currently tracked activities
      are cancelled, regardless of the 'activities' argument.
    '''

    repo = get_repo()

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
        None, help='Activity slugs to stop tracking.',
        autocompletion=complete_activity_slugs_stop
    ),
    all_: bool = typer.Option(False, '-a', '--all', help='Stop all tracked activities.'),
    message: str = typer.Option(
        '', '-m', '--message', help='Optional message to attach to the session(s).'
    )
) -> None:
    '''Stop tracking activities.
    
    Stops tracking the specified activities.

    - If the '--all' flag is used, all currently tracked activities
      are stopped, regardless of the 'activities' argument.
    '''

    repo = get_repo()
    try:
        sessions = repo.stop(*(activities or []), all=all_, message=message)
    except ValueError as e:
        raise click.ClickException(f'Error stopping activities. {e}')
    
    if not sessions:
        console.print(Panel(
            Text('No sessions were recorded.'),
            border_style='dim',
            expand=True
        ))
        return

    console.print(Text(f'Recorded ({len(sessions)}):'))
    elements = []
    for s in sessions:
        elements.append(_session_panel(s))
    console.print(Group(*elements))
    
    

@app.command()
def do(activities: list[str] = typer.Argument(
        ...,
        help='Activity slugs to start.',
        autocompletion=complete_activity_slugs_start
    ),
    message: str = typer.Option(
        '', '-m', '--message', help='Optional message to attach to the session.'
    )

) -> None:
    
    repo = get_repo()

    try:
        session = repo.do(*activities, message=message)
    except ValueError as e:
        raise click.ClickException(f'Error doing activities. {e}')
    
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
            Group(*elements), title=header, title_align='left', border_style='dim', expand=True
        )
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
def update() -> None:
    '''Update all the tracked activities notes. Remove unnecessary.'''
    
    repo = get_repo()
    
    repo.update_activities_notes()



if __name__ == '__main__':
    app()
