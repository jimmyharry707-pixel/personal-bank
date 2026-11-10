from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication, QMessageBox

from .config import AppConfig
from .db import Database
from .services import FinanceService
from .ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PersonalBank")
    app.setOrganizationName("PersonalBank")
    config = AppConfig.load()
    database = Database(config.database_path)
    try:
        database.initialize()
        service = FinanceService(database)
        window = MainWindow(service, config)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "PersonalBank could not start", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
