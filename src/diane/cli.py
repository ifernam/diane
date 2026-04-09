from textwrap import indent

from enum import Enum
import typer
from pathlib import Path
import yaml
import click

from diane.temporal import TimeInterval, TimeSet
from diane.repository_manager import RepositoryManager



app = typer.Typer()


def complete_activity_slugs(incomplete: str) -> list[str]:
    '''Return a list of activity slugs for autocompletion in the CLI.
    
    Filters the slugs based on the current incomplete input.

    Args:
        `incomplete` (`str`): The current incomplete input from
            the user.
    
    Returns:
        `list[str]`: The list of activity slugs defined
        in the repository.
    '''

    # Search for the repository root by looking for the '.diane/'
    # directory in the current directory and its parents.
    current = Path.cwd()
    repo_root = None
    for parent in [current, *current.parents]:
        if (parent / '.diane').exists():
            repo_root = parent
            break
    if not repo_root:
        return []  # Not in a repository, so no activities to complete.

    activities_yaml = repo_root / '.diane' / 'data' / 'activities.yaml'
    if not activities_yaml.exists():
        return []

    try:
        with activities_yaml.open(encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return []

    if not isinstance(data, dict):
        return []
    activities = data.get('activities', [])
    if not isinstance(activities, dict):
        return []

    slugs = list(activities.keys())

    # Filter slugs based on the incomplete input. If the input is empty,
    # return all slugs.
    if incomplete:
        return [s for s in slugs if s.startswith(incomplete)]
    
    return slugs


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
        typer.echo('No activities are currently being tracked.')
        return
    
    indent = '    '
    bullet = '\u2022'  # Bullet '•'.
    typer.echo('Tracking activities:')
    for activity, start in repo._tracking_state.items():
        typer.echo(f'{indent}{bullet} {activity.title} (started {start})')


class SessionsPeriod(str, Enum):
    all = 'all'
    today = 'today'
    week = 'week'
    month = 'month'
    year = 'year'


@app.command()
def sessions(
    today: bool = typer.Option(False, '-t', '--today', help='Show today\'s sessions.'),
    week: bool = typer.Option(False, '-w', '--week', help='Show this week\'s sessions.'),
    month: bool = typer.Option(False, '-m', '--month', help='Show this month\'s sessions.'),
    year: bool = typer.Option(False, '-y', '--year', help='Show this year\'s sessions.'),
    all: bool = typer.Option(False, '-a', '--all', help='Show all sessions.')
):
    '''Show recorded sessions.'''

    repo = get_repo()

    selected = [
        period
        for period, enabled in {
            SessionsPeriod.today: today,
            SessionsPeriod.week: week,
            SessionsPeriod.month: month,
            SessionsPeriod.year: year,
            SessionsPeriod.all: all
        }.items()
        if enabled
    ]

    if len(selected) > 1:
        typer.echo(
            'Error: use only one of -t/--today, -w/--week, -m/--month, -y/--year, -a/--all.'
        )
        raise typer.Exit(code=1)
    
    period = selected[0] if selected else SessionsPeriod.all

    interval_by_period = {
        SessionsPeriod.today: TimeInterval.today(),
        SessionsPeriod.week: TimeInterval.week(),
        SessionsPeriod.month: TimeInterval.month(),
        SessionsPeriod.year: TimeInterval.year(),
        SessionsPeriod.all: TimeInterval.timeline()
    }

    target = TimeSet(interval_by_period[period])
    
    indent = '    '
    arrow = '\u2192'   # Arrow '→'.
    bullet = '\u2022'  # Bullet '•'.
    gray = (150, 150, 150)
    purple = (200, 150, 250)

    def generate_sessions():
        for s in repo.iter_overlapping(target):
            start_date_str = f'{s.timeset.start.timestamp.date_string} '
            start_time_str = click.style(
                s.timeset.start.timestamp.time_iso(offset=False), fg='bright_yellow', bold=True
            )

            if s.timeset.is_point:
                end_str = ''
            else:
                end_date_str = (
                    '' if s.timeset.last_day == s.timeset.first_day
                    else f'{s.timeset.end.timestamp.date_string} '
                )
                end_time_str = click.style(
                    s.timeset.end.timestamp.time_iso(offset=False), fg='bright_yellow', bold=True
                )

                density = round(100 * (s.timeset.duration / s.timeset.span_duration))
                duration_density_str = f' (duration: {s.timeset.duration}, density: {density}%)'

                end_str = f' {arrow} {end_date_str}{end_time_str}{duration_density_str}'
            
            header = f'{start_date_str}{start_time_str}{end_str}'

            activities_titles = (
                    f'{indent}{bullet} {click.style(a.title, fg=purple, italic=True)}'
                    for a in sorted(s._activities, key=lambda a: a.title)
                )
            activities_titles_string = '\n'.join(activities_titles)
            activities_str = f'{indent}Activities:\n{activities_titles_string}'

            session_str = f'{header}\n{activities_str}'

            if s.message:
                message_text = click.style(s.message, fg=gray, italic=True)
                message_str = f'{indent}Message: {message_text}'
                session_str += f'\n{message_str}'

            yield f'\u276F {session_str}\n'

    click.echo_via_pager(generate_sessions())


@app.command()
def start(
    activities: list[str] = typer.Argument(
        ...,
        help='Activities to start.',
        autocompletion=complete_activity_slugs
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
        typer.echo(f'Started tracking {len(started_activities)} activities.')
        indent = '    '
        bullet = '\u2022'  # Bullet '•'.
        for activity in started_activities:
            typer.echo(f'{indent}{bullet} {activity.title}')
    except ValueError as e:
        typer.echo(f'Error starting activities. {e}')
        raise typer.Exit(code=1)
    

@app.command()
def cancel(
    activities: list[str] | None = typer.Argument(
        None, help='Activities to cancel.', autocompletion=complete_activity_slugs
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

    indent = '    '
    bullet = '\u2022'  # Bullet '•'.
    purple = (200, 150, 250)

    repo = get_repo()

    if not all_ and not activities:
        typer.echo('Specify at least one activity to cancel or use \'-a\'/\'--all\'.')
        raise typer.Exit(code=1)

    try:
        cancelled = repo.cancel(*(activities or []), all=all_)
        if cancelled:
            activities_titles = (
                f'{indent}{bullet} {click.style(a.title, fg=purple, italic=True)}'
                for a in sorted(cancelled, key=lambda a: a.title)
            )
            activities_titles_string = '\n'.join(activities_titles)
            activities_str = (
                'Tracking of the following activities has been cancelled:\n'
                f'{activities_titles_string}'
            )
            typer.echo(activities_str)
        else:
            if not repo._tracking_state:
                typer.echo('No activities are currently being tracked.')
            else:
                typer.echo('No matching activities to cancel.')
    except ValueError as e:
        typer.echo(f'Error cancelling activities. {e}')
        raise typer.Exit(code=1)


@app.command()
def stop(
    activities: list[str] | None = typer.Argument(
        None, help='Activities to stop.',
        autocompletion=complete_activity_slugs
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
        if sessions:
            typer.echo(f'Recorded {len(sessions)} sessions:')
            for s in sessions:
                typer.echo(f'\u276F {s}')
    except ValueError as e:
        typer.echo(f'Error stopping activities. {e}')
        raise typer.Exit(code=1)
    

@app.command()
def do(activities: list[str] = typer.Argument(
        ...,
        help='Activities to start.',
        autocompletion=complete_activity_slugs
    ),
    message: str = typer.Option(
        '', '-m', '--message', help='Optional message to attach to the session.'
    )

) -> None:
    
    repo = get_repo()

    try:
        session = repo.do(*activities, message=message)
        indent = '    '
        bullet = '\u2022'  # Bullet '•'.
        typer.echo(f'Have done activities {len(session.activities)}:')
        for a in session.activities:
            typer.echo(f'{indent}{bullet} {a.title}')
    except ValueError as e:
        typer.echo(f'Error doing activities. {e}')
        raise typer.Exit(code=1)



if __name__ == '__main__':
    app()