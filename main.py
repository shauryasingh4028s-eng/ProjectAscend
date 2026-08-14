import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from Modules.app_controller import AppController


def main():
    # Create the Qt application object.
    app = QApplication(sys.argv)
    from PySide6.QtGui import QIcon
    from pathlib import Path
    
    if getattr(sys, "frozen", False):
        icon_path = Path(sys._MEIPASS) / "Assets" / "app.ico"
    else:
        icon_path = Path("Assets") / "app.ico"
    
    app.setWindowIcon(QIcon(str(icon_path)))

    # Create the controller that manages the app windows.
    controller = AppController()

    # Close the database safely when the app exits.
    app.aboutToQuit.connect(controller.close_database)

    # Start with the daytime Dashboard window.
    controller.show_dashboard()

    # Start the desktop app event loop.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()