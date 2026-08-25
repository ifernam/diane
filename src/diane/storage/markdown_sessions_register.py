from pathlib import Path

from diane.storage.sessions_register import SessionsRegisterConfig


class MarkdownSessionsRegisterConfig(SessionsRegisterConfig):
    """A Markdown sessions register configuration.

    Attributes:
        daily_note_name_format (str): A daily note's name `strftime`
            format. For example, '%Y-%m-%d'.
        daily_note_template_path (Path | None): An optional relative
            path to a daily note's template in a repository.
            For example, 'templates/daily_note_template'.
    """

    path: Path = Path('daily_notes')
    daily_note_name_format: str = '%Y-%m-%d'
    daily_note_template_path: Path | None = None
