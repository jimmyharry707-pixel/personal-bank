import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personalbank.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_budget_alert_thresholds_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir)
            config_file = app_dir / "settings.json"
            with patch("personalbank.config.APP_DIR", app_dir), patch(
                "personalbank.config.CONFIG_FILE", config_file
            ):
                config = AppConfig()
                config.update(budget_warning_percent=85, budget_critical_percent=125)
                loaded = AppConfig.load()

        self.assertEqual(loaded.budget_warning_percent, 85)
        self.assertEqual(loaded.budget_critical_percent, 125)


if __name__ == "__main__":
    unittest.main()