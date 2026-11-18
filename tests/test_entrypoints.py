import importlib
import unittest


class EntryPointTests(unittest.TestCase):
    def test_package_main_module_exists(self):
        module = importlib.import_module("mcsc_gui.__main__")
        self.assertTrue(callable(getattr(module, "main", None)))

    def test_mcsc_is_the_pymcsc_library(self):
        # The app package was renamed to mcsc_gui so it doesn't shadow pymcsc (imported as mcsc)
        module = importlib.import_module("mcsc")
        self.assertTrue(hasattr(module, "ServerManager"))

    def test_server_creator_gui_has_run_method(self):
        module = importlib.import_module("mcsc_gui.main")
        self.assertTrue(hasattr(module.ServerCreatorGUI, "run"))


if __name__ == "__main__":
    unittest.main()
