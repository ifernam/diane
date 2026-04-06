import typer
from pathlib import Path
import yaml

from diane.repository_manager import RepositoryManager



app = typer.Typer()


def complete_activity_slugs(incomplete: str) -> list[str]:
    '''Return a list of activity slugs for autocompletion in the CLI.
    
    Filters the slugs based on the current incomplete input.

    Args:
        `incomplete` (str): The current incomplete input from the user.
    
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


@app.command()
def sessions():
    '''Show all recorded sessions.'''

    repo = get_repo()
    for s in repo._sessions:
        typer.echo(f'\u276F {s}')


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
def stop(
    activities: list[str] | None = typer.Argument(
        None, help='Activities to stop.',
        autocompletion=complete_activity_slugs
    ),
    all: bool = typer.Option(False, '-a', '--all', help='Stop all tracked activities.')
) -> None:
    '''Stop tracking activities.
    
    Stops tracking the specified activities.

    - If the '--all' flag is used, all currently tracked activities
      are stopped, regardless of the 'activities' argument.
    '''

    repo = get_repo()
    try:
        sessions = repo.stop(*(activities or []), all=all)
        if sessions:
            typer.echo(f'Recorded {len(sessions)} sessions:')
            for s in sessions:
                typer.echo(f'\u276F {s}')
    except ValueError as e:
        typer.echo(f'Error stopping activities. {e}')
        raise typer.Exit(code=1)



if __name__ == '__main__':
    app()