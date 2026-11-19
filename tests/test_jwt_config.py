"""Configuration regression tests; never read a deployment .env."""
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

CONFIG = Path(__file__).resolve().parents[1] / "backend" / "config.py"


class JWTConfigTests(unittest.TestCase):
    def load_config(self, secret=None, dotenv_secret=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "config.py"
            shutil.copyfile(CONFIG, target)
            if dotenv_secret is not None:
                (root / ".env").write_text("JWT_SECRET=" + dotenv_secret + "\n")
            env = {"DATA_DIR": str(root / "data")}
            if secret is not None:
                env["JWT_SECRET"] = secret
            with patch.dict(os.environ, env, clear=True):
                return runpy.run_path(str(target))

    def test_missing_blank_default_and_short_fail(self):
        for value in (None, "", "   ", "change-me-in-production", "a" * 31):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                    self.load_config(value)

    def test_explicit_secret(self):
        value = "test-only-not-a-production-secret-0123456789"
        self.assertEqual(self.load_config(value)["JWT_SECRET"], value)

    def test_dotenv_and_environment_precedence(self):
        value = "dotenv-test-only-not-a-production-secret-1234"
        self.assertEqual(self.load_config(dotenv_secret=value)["JWT_SECRET"], value)
        override = "environment-test-only-not-a-production-secret"
        self.assertEqual(self.load_config(override, value)["JWT_SECRET"], override)
        with self.assertRaises(RuntimeError):
            self.load_config("", value)


if __name__ == "__main__":
    unittest.main()
