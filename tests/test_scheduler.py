import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import scheduler as scheduler_mod
from core.scheduler import Scheduler, normalize_time


def hora(h, m):
    return time.struct_time((2026, 11, 8, h, m, 0, 6, 312, 0))


class NormalizeTimeTests(unittest.TestCase):
    def test_accepts_and_normalizes(self):
        self.assertEqual(normalize_time("9:5"), "09:05")
        self.assertEqual(normalize_time("09:05"), "09:05")
        self.assertEqual(normalize_time(" 23:59 "), "23:59")

    def test_rejects_garbage_and_out_of_range(self):
        for bad in ("", "mañana", "25:00", "12:60", "12"):
            with self.assertRaises(ValueError):
                normalize_time(bad)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "agenda.json"
        patcher = patch.object(scheduler_mod, "agenda_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.avisos = []
        self.agenda = Scheduler(on_due=self.avisos.append, check_ms=600_000)
        self.addCleanup(self.agenda.stop)

    def test_add_normalizes_and_persists(self):
        self.agenda.add("9:0", "la ropa", "daily")
        self.assertEqual(self.agenda.all()[0]["time"], "09:00")
        recargada = Scheduler(on_due=None)  # nueva instancia: lo carga del JSON
        recargada.stop()
        self.assertEqual(recargada.all()[0]["message"], "la ropa")

    def test_daily_task_fires_once_per_day(self):
        self.agenda.add("09:00", "la ropa")
        self.agenda._check(hora(9, 0))
        self.assertEqual(len(self.avisos), 1)
        self.assertEqual(self.avisos[0]["message"], "la ropa")
        self.agenda._check(hora(9, 0))  # mismo minuto: no repite
        self.agenda._check(hora(9, 30))
        self.assertEqual(len(self.avisos), 1)
        self.assertEqual(len(self.agenda.all()), 1)  # la diaria sigue viva

    def test_once_task_is_removed_after_firing(self):
        self.agenda.add("09:00", "llamar al fontanero", "once")
        self.agenda._check(hora(9, 0))
        self.assertEqual(len(self.avisos), 1)
        self.assertEqual(self.agenda.all(), [])

    def test_no_fire_at_other_times(self):
        self.agenda.add("09:00", "la ropa")
        self.agenda._check(hora(8, 59))
        self.assertEqual(self.avisos, [])

    def test_remove_matching_by_message_and_time(self):
        self.agenda.add("09:00", "la ropa")
        self.agenda.add("22:30", "las plantas")
        self.assertEqual(self.agenda.remove_matching("ropa"), 1)
        self.assertEqual(self.agenda.remove_matching("22:30"), 1)
        self.assertEqual(self.agenda.all(), [])
        self.assertEqual(self.agenda.remove_matching("nada"), 0)


if __name__ == "__main__":
    unittest.main()
