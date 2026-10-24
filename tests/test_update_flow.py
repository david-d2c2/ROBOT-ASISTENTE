import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core import updates


def _fake_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("RobotAsistente.exe", b"exe")
        bundle.writestr("_internal/datos.txt", b"datos")
    return buffer.getvalue()


class UpdateDownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work_dir = Path(self.directory.name) / "update"

    def test_download_extracts_and_writes_bat(self):
        fake_response = MagicMock()
        fake_response.__enter__.return_value = fake_response
        fake_response.iter_content.return_value = iter([_fake_zip_bytes()])
        with patch('core.updates.requests.get', return_value=fake_response) as get:
            extract_dir = updates.download_update("9.9.9", self.work_dir)
        self.assertIn("releases/download/v9.9.9/RobotAsistente-win64.zip", get.call_args.args[0])
        self.assertTrue((extract_dir / "RobotAsistente.exe").exists())
        self.assertTrue((extract_dir / "_internal" / "datos.txt").exists())

        install_dir = Path(self.directory.name) / "instalacion"
        bat = updates.write_update_bat(extract_dir, install_dir, self.work_dir / "actualizar.bat")
        content = bat.read_text(encoding="utf-8")
        self.assertIn("robocopy", content)
        self.assertIn("RobotAsistente.exe", content)

    def test_bad_package_raises(self):
        fake_response = MagicMock()
        fake_response.__enter__.return_value = fake_response
        fake_response.iter_content.return_value = iter([b"no-es-un-zip"])
        with patch('core.updates.requests.get', return_value=fake_response):
            with self.assertRaises(RuntimeError):
                updates.download_update("9.9.9", self.work_dir)

    def test_can_self_update_depends_on_freeze(self):
        with patch('core.updates.sys.frozen', True, create=True):
            self.assertTrue(updates.can_self_update())
        with patch('core.updates.sys.frozen', False, create=True):
            self.assertFalse(updates.can_self_update())


if __name__ == "__main__":
    unittest.main()
