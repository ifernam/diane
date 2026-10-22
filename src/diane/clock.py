import datetime
import zoneinfo

import tzlocal

from diane.chrono import Timestamp


class ClockError(Exception):
    """A general clock error."""

    ...


class InvalidDefaultTimezoneError(ClockError):
    """The default timezone is invalid."""

    ...


class LocalTimezoneDetectionError(ClockError):
    """Failed to determine the local time zone."""

    ...


class Clock:
    """Represents a clock.

    Allows to find out the current time in the current time zone.

    Attributes:
        timezone (str | None = None): The default IANA time zone.
    """

    timezone: str | None = None

    def __init__(self, timezone: str | None = None) -> None:
        """Create a new clock.

        Args:
            timezone (str | None = None): The default IANA time zone.
                Optional.
        """
        self.timezone = timezone

    def _current_timezone(self) -> zoneinfo.ZoneInfo:
        """Determine the current `ZoneInfo` time zone.

        If the default time zone has been specified, return that time
        zone. Otherwise, return the local time zone.

        Returns:
            zoneinfo.ZoneInfo: The current time zone.

        Raises:
            InvalidDefaultTimezoneError: If the default time zone
                is invalid.
            LocalTimezoneDetectionError: If the local time zone
                could not be determined.
        """
        default_timezone = self.timezone
        if default_timezone is not None:
            try:
                timezone = zoneinfo.ZoneInfo(default_timezone)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
                raise InvalidDefaultTimezoneError(
                    f"The default IANA time zone '{default_timezone}' "
                    "is invalid."
                ) from exc
        else:
            try:
                timezone = tzlocal.get_localzone()
            except Exception as exc:
                raise LocalTimezoneDetectionError(
                    f"Failed to determine the local time zone. {exc}"
                ) from exc

        return timezone

    def current_timezone(self) -> str:
        """Determine the current IANA time zone.

        If the default time zone has been specified, return that time
        zone. Otherwise, return the local time zone.

        Returns:
            str: The current IANA time zone.

        Raises:
            InvalidDefaultTimezoneError: If the default time zone
                is invalid.
            LocalTimezoneDetectionError: If the local time zone
                could not be determined.
        """
        return self._current_timezone().key

    def now(self) -> Timestamp:
        """Create a new timestamp representing the current time.

        If the default time zone has been specified, return the current
        time in that time zone. Otherwise, return the current local
        time.

        Returns:
            Timestamp: A timestamp representing the current time.

        Raises:
            InvalidDefaultTimezoneError: If the default time zone
                is invalid.
            LocalTimezoneDetectionError: If the local time zone
                could not be determined.
        """
        current_timezone = self._current_timezone()
        return Timestamp(datetime.datetime.now(current_timezone))
