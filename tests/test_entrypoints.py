import importlib
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EntryPointTests(unittest.TestCase):
    def test_package_main_module_exists(self):
        module = importlib.import_module("mcsc_gui.__main__")
        self.assertTrue(callable(getattr(module, "main", None)))

    def test_mcsc_is_the_pymcsc_library(self):
        # The app package was renamed to mcsc_gui so it doesn't shadow pymcsc (imported as mcsc)
        module = importlib.import_module("mcsc")
        self.assertTrue(hasattr(module, "ServerManager"))

    def test_mcsc_command_starts_the_qt_app(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["scripts"], {"mcsc": "mcsc_gui.__main__:main"})
        module = importlib.import_module("mcsc_gui.qt_main")
        self.assertTrue(callable(module.main))

    def test_no_nicegui_left(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        deps = " ".join(project["dependencies"]).lower()
        self.assertNotIn("nicegui", deps)
        self.assertNotIn("pywebview", deps)
        for path in (ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("import nicegui", text, path)
            self.assertNotIn("from nicegui", text, path)

    def test_app_imports_without_nicegui(self):
        code = (
            "import sys\n"
            "import mcsc_gui.qt_main\n"
            "print(','.join(sorted({m.split('.')[0] for m in sys.modules} & {'nicegui', 'webview'})))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                check=True)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
