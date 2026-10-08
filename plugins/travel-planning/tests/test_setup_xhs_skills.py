from __future__ import annotations

import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "xiaohongshu" / "scripts" / "setup.py"
SPEC = importlib.util.spec_from_file_location("setup_xhs_mcp", MODULE_PATH)
assert SPEC and SPEC.loader
setup_xhs_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_xhs_mcp)


class SetupXhsMcpTest(unittest.TestCase):
    def test_status_reports_verified_pinned_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid_file = root / "service.pid"
            with (
                patch.object(setup_xhs_mcp, "PID_FILE", pid_file),
                patch.object(setup_xhs_mcp, "DATA_ROOT", root),
                patch.object(setup_xhs_mcp, "STATE_DIR", root),
                patch.object(setup_xhs_mcp, "COOKIE_FILE", root / "cookies.json"),
                patch.object(setup_xhs_mcp, "LOG_FILE", root / "service.log"),
                patch.object(setup_xhs_mcp, "_verify_binary", return_value=True),
                patch.object(setup_xhs_mcp, "_health", return_value=False),
            ):
                result = setup_xhs_mcp.status(Namespace())
        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["provider"], "xpzouying/xiaohongshu-mcp")
        self.assertEqual(result["version"], "v2.5.2")
        self.assertEqual(result["commit"], setup_xhs_mcp.UPSTREAM_COMMIT)
        self.assertTrue(result["assets_verified"]["server"])
        self.assertFalse(result["service"]["healthy"])

    def test_download_rejects_digest_mismatch(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self, _: int) -> bytes:
                if getattr(self, "done", False):
                    return b""
                self.done = True
                return b"unexpected"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "binary"
            with patch.object(setup_xhs_mcp, "urlopen", return_value=Response()):
                with self.assertRaises(setup_xhs_mcp.SetupError):
                    setup_xhs_mcp._download("binary", "0" * 64, destination)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".download").exists())


if __name__ == "__main__":
    unittest.main()
