import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import skills


def write_skill(root: Path, name: str, data):
    (root / name).write_text(json.dumps(data), encoding="utf-8")


class SkillLoadingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_loads_valid_skills_and_normalizes_triggers(self):
        write_skill(self.root, "saludo.json", {
            "name": "saludo", "triggers": ["  Hola "], "response": "¡Hola!", "say": True,
        })
        with patch.object(skills, "skills_dir", return_value=self.root):
            found = skills.load_skills()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["triggers"], ["hola"])
        self.assertTrue(found[0]["say"])

    def test_skips_invalid_json_and_incomplete_skills(self):
        (self.root / "roto.json").write_text("{no soy json", encoding="utf-8")
        write_skill(self.root, "sin_respuesta.json", {"triggers": ["x"]})
        write_skill(self.root, "sin_triggers.json", {"response": "y"})
        with patch.object(skills, "skills_dir", return_value=self.root):
            self.assertEqual(skills.load_skills(), [])

    def test_missing_directory_returns_empty(self):
        with patch.object(skills, "skills_dir", return_value=self.root / "no-existe"):
            self.assertEqual(skills.load_skills(), [])


class SkillMatchingTests(unittest.TestCase):
    def setUp(self):
        self.skill = {"name": "demo", "triggers": ["modo demo", "demo"], "response": "ok", "say": False}

    def test_matches_exact_trigger_case_insensitively(self):
        self.assertIs(skills.match_skill("DEMO", [self.skill]), self.skill)

    def test_matches_trigger_followed_by_comma_or_more_words(self):
        self.assertIs(skills.match_skill("modo demo, por favor", [self.skill]), self.skill)

    def test_does_not_match_trigger_inside_a_word(self):
        self.assertIsNone(skills.match_skill("demonio", [self.skill]))

    def test_no_match_on_empty_or_unrelated_text(self):
        self.assertIsNone(skills.match_skill("", [self.skill]))
        self.assertIsNone(skills.match_skill("hola que tal", [self.skill]))
        self.assertIsNone(skills.match_skill("demo", []))


if __name__ == "__main__":
    unittest.main()
