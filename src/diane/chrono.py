from __future__ import annotations
import datetime
import zoneinfo
import tzlocal


class TimeError(Exception):
    """A general time error."""
    ...


class InvalidTimezoneError(TimeError):
    """An invalid time zone."""
    ...


class Timestamp:
    """Represents a timestamp with a time zone specified in the IANA
    format.

    Attributes:
        _dt (datetime.datetime): An aware `datetime` object with
            a `ZoneInfo` time zone.

    Args:
        dt (datetime.datetime): An aware `datetime` object with
            a `ZoneInfo` time zone.
    """

    # UTC time zone.
    _UTC: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo('Etc/UTC')

    _dt: datetime.datetime

    @staticmethod
    def _validate_timezone(dt: datetime.datetime) -> None:
        """Check whether a `datetime` object is aware and has
        a `ZoneInfo` time zone.

        Args:
            dt (datetime.datetime): A `datetime` object to validate.

        Raises:
            InvalidTimezoneError: If a `datetime` object is naive
                or its time zone is not a `ZoneInfo` instance.
        """
        if dt.tzinfo is None:
            raise InvalidTimezoneError(
                f"No time zone has been specified for '{dt.isoformat()}'.")

        try:
            utc_off = dt.utcoffset()
        except Exception as exc:
            raise InvalidTimezoneError(
                f"Failed to obtain a UTC offset for '{dt.isoformat()}'. {exc}"
            ) from exc

        if utc_off is None:
            raise InvalidTimezoneError(
                f"The UTC offset is `None` for '{dt.isoformat()}'."
            )

        if not isinstance(dt.tzinfo, zoneinfo.ZoneInfo):
            raise InvalidTimezoneError(
                f"Time zone must be a `ZoneInfo` instance, got "
                f"'{type(dt.tzinfo).__name__}' for '{dt.isoformat()}'."
            )

    def __init__(self, dt: datetime.datetime) -> None:
        """Create a timestamp.

        Args:
            dt (datetime.datetime): An aware `datetime` object with
                a `ZoneInfo` time zone.

        Raises:
            InvalidTimezoneError: If a `datetime` object is naive
                or its time zone is not a `ZoneInfo` instance.
        """
        self._validate_timezone(dt)
        self._dt = dt
