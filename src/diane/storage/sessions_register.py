from pathlib import Path

from pydantic import BaseModel


class SessionsRegisterConfig(BaseModel):
    """A sessions register configuration.

    Attributes:
        path (Path): A relative path where sessions are stored.
    """

    path: Path
