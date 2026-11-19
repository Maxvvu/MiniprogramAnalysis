"""Offline tests for the installer's config stage, without opkg or /opt writes."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "backend/deploy/install-openwrt.sh"
SOURCE = SCRIPT.read_text()
CONFIG_STAGE = SOURCE.split('echo "==> 4/5 初始化配置文件"', 1)[1].split(
    'echo "==> 5/5 安装启动脚本与开机自启"', 1
)[0]


class OpenWrtConfigTests(unittest.TestCase):
    def initialize(self, root):
        subprocess.run(
            ["sh", "-ec", CONFIG_STAGE],
            env={**os.environ, "INSTALL_DIR": str(root)},
            capture_output=True, check=True,
        )

    def test_clean_install_without_example_and_repeated_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.initialize(root)
            config = root / ".env"
            content = config.read_bytes()
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
            for key in ("JWT_SECRET", "WX_APPID", "WX_SECRET", "LLM_API_KEY"):
                self.assertIn((key + "=\n").encode(), content)
            self.assertIn(b"HOST=127.0.0.1\n", content)
            subprocess.run(["sh", "-n", str(config)], check=True)
            self.initialize(root)
            self.assertEqual(config.read_bytes(), content)

    def test_existing_configuration_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / ".env"
            original = b"# operator configuration\nJWT_SECRET=test-only-placeholder\n"
            config.write_bytes(original)
            config.chmod(0o640)
            self.initialize(root)
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o640)

    def test_existing_and_broken_symlinks_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "operator.env"
            config = root / ".env"
            config.symlink_to(target)
            self.initialize(root)
            self.assertTrue(config.is_symlink())
            self.assertFalse(target.exists())
            target.write_text("# unchanged\n")
            self.initialize(root)
            self.assertEqual(target.read_text(), "# unchanged\n")

    def test_noclobber_rejects_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".env"
            config.write_text("# unchanged\n")
            # Simulate a file appearing after the existence check, using the
            # actual guarded creation body from the production script.
            body = CONFIG_STAGE.split("    (\n", 1)[1].split("\n    )", 1)[0]
            result = subprocess.run(
                ["sh", "-ec", body],
                env={**os.environ, "INSTALL_DIR": tmp},
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(config.read_text(), "# unchanged\n")


if __name__ == "__main__":
    unittest.main()
