import unittest

from core.hotkey import parse_hotkey


class HotkeyParsingTests(unittest.TestCase):
    def test_parse_letter_combo(self):
        self.assertEqual(parse_hotkey("Ctrl+Alt+R"), (0x0003, ord("R")))

    def test_parse_case_and_spaces(self):
        self.assertEqual(parse_hotkey("ctrl + shift + F5"), (0x0006, 0x74))

    def test_parse_win_combo(self):
        self.assertEqual(parse_hotkey("Win+A"), (0x0008, ord("A")))

    def test_parse_single_modifier_combo(self):
        self.assertEqual(parse_hotkey("Ctrl+R"), (0x0002, ord("R")))

    def test_invalid_combos_return_none(self):
        for combo in ("", "R", "Ctrl+Ñ", "Ctrl+Alt+R+Shift+Win", "Ctrl+"):
            with self.subTest(combo=combo):
                self.assertIsNone(parse_hotkey(combo))


if __name__ == "__main__":
    unittest.main()
