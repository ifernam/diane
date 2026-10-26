"""Graphical user interface entry point and application controller."""

import sys

from PySide6.QtWidgets import QApplication

from diane.app import App
from diane.gui.tray_icon import TrayIcon


class GUIController:
    """Coordinates the GUI and its shared application instance.

    The controller owns the domain `App` instance and the tray icon,
    keeping them available for the lifetime of the GUI event loop.

    Attributes:
        qt_app (QApplication): The Qt application.
        app (App): The shared Diane application instance.
        tray_icon (TrayIcon): The system-tray icon.
    """

    qt_app: QApplication
    app: App
    tray_icon: TrayIcon

    def __init__(self, qt_app: QApplication) -> None:
        """Create the controller and its application components.

        Args:
            qt_app (QApplication): The Qt application to control.
        """
        self.qt_app = qt_app
        self.app = App()
        self.tray_icon = TrayIcon(qt_app)

    def start(self) -> int:
        """Show the tray icon and run Qt's event loop.

        Returns:
            int: The exit code returned by the Qt event loop.
        """
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.tray_icon.show()
        return self.qt_app.exec()


def main() -> int:
    """Create the Qt application and launch the Diane GUI.

    Returns:
        int: The exit code returned by the Qt event loop.
    """
    qt_app = QApplication(sys.argv)
    controller = GUIController(qt_app)
    return controller.start()


if __name__ == "__main__":
    raise SystemExit(main())
