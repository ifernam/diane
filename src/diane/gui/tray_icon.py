"""System-tray icon for the Diane GUI."""

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


class TrayIcon(QSystemTrayIcon):
    """System-tray icon with a Quit context-menu action.

    Right-clicking the icon opens a menu whose Quit action exits the Qt
    application.

    Attributes:
        _menu (QMenu): The tray icon's context menu.
    """

    _menu: QMenu

    def __init__(self, qt_app: QApplication) -> None:
        """Create the tray icon and connect its Quit action.

        Args:
            qt_app (QApplication): The Qt application to quit when
                the user selects Quit.
        """
        icon = QIcon(str(Path(__file__).with_name("tray_icon.png")))
        super().__init__(icon, qt_app)
        self.setToolTip("Diane")

        self._menu = QMenu()
        quit_action = self._menu.addAction("Quit")
        _ = quit_action.triggered.connect(qt_app.quit)
        self.setContextMenu(self._menu)
