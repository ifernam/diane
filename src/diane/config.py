import tomllib

from pydantic import ValidationError
from pydantic_settings import TomlConfigSettingsSource

from diane.app_session import AppConfig, AppSession


class ConfigurationError(Exception):
    """A general configuration error."""
    ...


class ConfigurationFileNotFoundError(ConfigurationError):
    """No configuration file has been found."""
    ...


class ConfigurationParseError(ConfigurationError):
    """An error occurred while parsing the configuration file."""
    ...

class ConfigurationIOError(ConfigurationError):
    """An I/O error occurred while reading the configuration file."""
    ...


class InvalidConfigurationError(ConfigurationError):
    """An invalid configuration."""
    ...


class Configurator:
    """This is a service that manages configurations and initialises
    objects.
    """

    @classmethod
    def initialise_app(cls, app_session: AppSession) -> None:
        """Load a configuration from
        '<programme directory>/config/config.toml'
        and initialise the programme.

        Args:
            app_session: The programme session to initialise.

        Raises:
            ConfigurationFileNotFoundError: If the programme
                configuration file is missing.
            ConfigurationParseError: If the TOML content is invalid.
            ConfigurationIOError: If the configuration file could not
                be read.
            InvalidConfigurationError: If the configuration data does
                not match the schema.
            AppAlreadyInitialisedError: If the programme has already
                been initialised.

        """
        programme_dir = app_session.programme_dir
        config_path = programme_dir / 'config' / 'config.toml'

        if not config_path.is_file():
            raise ConfigurationFileNotFoundError(
                f"The configuration file '{config_path}' could not be found."
            )

        # Create a TOML settings source pointing to the programme
        # configuration file and parse it into a dictionary.
        try:
            source = TomlConfigSettingsSource(AppConfig, toml_file=config_path)
            config_data = source()
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationParseError(
                f"The TOML syntax in the '{config_path}' file is invalid. "
                f"{exc}"
            ) from exc
        except OSError as exc:
            raise ConfigurationIOError(
                f"Failed to read the configuration file '{config_path}'. {exc}"
            ) from exc

        # Validate the configuration data and instantiate
        # the `AppConfig`.
        try:
            config = AppConfig.model_validate(config_data)
        except ValidationError as exc:
            raise InvalidConfigurationError(
                f"The configuration in the '{config_path}' file is invalid. "
                f"{exc}"
            ) from exc

        # Initialise the session with the loaded config.
        app_session.initialise(config)
