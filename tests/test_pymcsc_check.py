import subprocess
import sys
import unittest
from unittest import mock

from mcsc_gui import _pymcsc_check as check


class EnsurePymcscTests(unittest.TestCase):
    def test_working_library_is_left_alone(self):
        with mock.patch.object(check.subprocess, "check_call") as pip:
            check.ensure_pymcsc()
        pip.assert_not_called()

    def test_broken_library_is_reinstalled_with_same_version(self):
        with mock.patch.object(check, "pymcsc_available", side_effect=[False, True]), \
                mock.patch.object(check, "_forget_mcsc_modules") as forget, \
                mock.patch.object(check.importlib.metadata, "version", return_value="0.1.0"), \
                mock.patch.object(check.subprocess, "check_call") as pip:
            check.ensure_pymcsc()

        pip.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", "pymcsc==0.1.0"]
        )
        forget.assert_called_once()

    def test_failed_reinstall_explains_the_manual_fix(self):
        error = subprocess.CalledProcessError(1, "pip")
        with mock.patch.object(check, "pymcsc_available", return_value=False), \
                mock.patch.object(check.subprocess, "check_call", side_effect=error):
            with self.assertRaises(RuntimeError) as ctx:
                check.ensure_pymcsc()
        self.assertIn(check.REPAIR_HINT, str(ctx.exception))

    def test_still_broken_after_reinstall(self):
        with mock.patch.object(check, "pymcsc_available", return_value=False), \
                mock.patch.object(check, "_forget_mcsc_modules"), \
                mock.patch.object(check.subprocess, "check_call"):
            with self.assertRaises(RuntimeError):
                check.ensure_pymcsc()


if __name__ == "__main__":
    unittest.main()
