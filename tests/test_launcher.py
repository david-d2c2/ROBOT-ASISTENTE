from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_windows_launcher_assets_are_complete(self):
        icon = ROOT / "assets" / "robot-assistant.ico"
        script = (ROOT / "crear_acceso_directo.ps1").read_text(encoding="utf-8")
        main = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertEqual(struct.unpack("<HHH", icon.read_bytes()[:6]), (0, 1, 7))
        self.assertIn('"Robot Asistente.lnk"', script)
        self.assertIn("$shortcut.TargetPath = $pythonw", script)
        self.assertIn("$shortcut.Arguments = '\"' + $main + '\"'", script)
        self.assertIn("$shortcut.WorkingDirectory = $projectDir", script)
        self.assertIn("$shortcut.IconLocation = $icon + \",0\"", script)
        self.assertIn('app.setWindowIcon(QIcon(', main)
        self.assertIn('"robot-assistant.ico"', main)
