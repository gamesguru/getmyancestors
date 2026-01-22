"""Test package installation and basic functionality."""

import os
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path


class TestInstallation(unittest.TestCase):
    """Test that the package can be installed and basic commands work."""

    project_root: Path

    @classmethod
    def setUpClass(cls):
        """Get the project root directory."""
        # Go up 2 levels from tests directory: tests -> .
        cls.project_root = Path(__file__).parent.parent.absolute()
        print(f"Project root: {cls.project_root}")

    def test_clean_installation(self):
        """Test installing the package in a clean virtual environment."""
        # Skip on CI if it takes too long
        if os.environ.get("CI") == "true" and os.environ.get("SKIP_LONG_TESTS"):
            self.skipTest("Skipping long-running installation test in CI")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a clean virtual environment
            venv_dir = tmpdir_path / "venv"
            print(f"Creating virtual environment at: {venv_dir}")
            venv.create(venv_dir, with_pip=True, clear=True)

            # Get paths to pip and python in the virtual environment
            if sys.platform == "win32":
                python_path = venv_dir / "Scripts" / "python.exe"
            else:
                python_path = venv_dir / "bin" / "python"

            # Install the package from the project directory
            print(f"Installing package from: {self.project_root}")

            # Install WITHOUT dev dependencies for speed (we only test import/CLI)
            # Use --no-user to prevent "Can not perform a '--user' install" errors
            # which occur if PIP_USER=1 is set in the environment or config
            subprocess.run(
                [
                    str(python_path),
                    "-m",
                    "pip",
                    "install",
                    "--no-user",
                    f"{self.project_root}",
                ],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                check=True,
                timeout=300,  # 5 minute timeout
            )

            # Test that the package can be imported
            print("Testing package import...")
            result = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    "import getmyancestors; print(getmyancestors.__version__)",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"Package import failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
            )

            # Test that CLI commands can be imported (check entry points)
            # Only test getmyanc and mergemyanc - these don't require Tkinter
            # fstogedcom requires Tkinter which is not installed in clean test environments
            print(
                "Testing CLI command imports (skipping fstogedcom - requires Tkinter)..."
            )
            for module in [
                "getmyancestors.getmyanc",
                "getmyancestors.mergemyanc",
            ]:
                result = subprocess.run(
                    [
                        str(python_path),
                        "-c",
                        f"from {module} import main; print('{module} import successful')",
                    ],
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"Failed to import {module}:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
