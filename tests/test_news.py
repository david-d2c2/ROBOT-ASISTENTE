import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import news
from core.news import NewsItem, SeenStore, build_digest_prompt, fetch_items, in_active_hours, item_key, parse_feed, strip_html

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title><![CDATA[La IA <b>generativa</b> llega a las aulas &amp; m&aacute;s]]></title>
    <link>https://ejemplo.com/noticia-ia?utm=rs</link>
    <description>&lt;p&gt;Resumen de la noticia.&lt;/p&gt;</description>
  </item>
  <item><link>https://ejemplo.com/sin-titulo</link></item>
  <item>
    <title>Otra noticia de hoy</title>
    <link>https://ejemplo.com/otra</link>
    <description>Breve.</description>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Noticia de un blog</title>
    <link href="https://blog.ejemplo.com/entrada"/>
    <summary>Lo que cuenta el blog.</summary>
  </entry>
</feed>"""


class ParseTests(unittest.TestCase):
    def test_parse_rss_strips_html_and_skips_titleless(self):
        items = parse_feed(RSS, source="prueba")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "La IA generativa llega a las aulas & más")
        self.assertEqual(items[0].summary, "Resumen de la noticia.")
        self.assertEqual(items[1].title, "Otra noticia de hoy")

    def test_parse_atom_entries(self):
        items = parse_feed(ATOM, source="blog")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://blog.ejemplo.com/entrada")

    def test_invalid_xml_returns_empty(self):
        self.assertEqual(parse_feed("esto no es xml", source="x"), [])

    def test_strip_html(self):
        self.assertEqual(strip_html("  hola <b>mundo</b>  &amp; adiós "), "hola mundo & adiós")


class DedupTests(unittest.TestCase):
    def test_same_title_different_tracking_is_duplicate(self):
        primera = NewsItem("a", "Noticia importante", "https://x.com/1", "")
        repetida = NewsItem("b", "  noticia   IMPORTANTE ", "https://x.com/1?utm=rs", "")
        self.assertEqual(item_key(primera), item_key(repetida))

    def test_seen_store_filters_marks_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vistas.json"
            store = SeenStore(path)
            item = NewsItem("a", "Noticia importante", "https://x.com/1", "")
            self.assertEqual(store.filter_new([item]), [item])
            store.mark([item], now=1_000_000.0)
            # nueva instancia: sigue viéndola (persistente)
            self.assertEqual(SeenStore(path).filter_new([item]), [])

    def test_seen_store_prunes_week_old_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SeenStore(Path(tmp) / "vistas.json")
            vieja = NewsItem("a", "Noticia vieja", "https://x.com/v", "")
            store.mark([vieja], now=1_000_000.0)
            store.mark([], now=1_000_000.0 + 8 * 86_400)  # una semana después
            self.assertEqual(store.filter_new([vieja]), [vieja])


class FetchTests(unittest.TestCase):
    def test_fetch_tolerates_broken_feed(self):
        def fake_fetch(url):
            if "roto" in url:
                raise ConnectionError("caído")
            return RSS
        items = fetch_items(["https://roto.com/feed", "https://bien.com/rss"], fetch=fake_fetch)
        self.assertEqual(len(items), 2)  # solo el feed sano

    def test_feed_name_extracts_domain(self):
        self.assertEqual(news.feed_name("https://www.xataka.com/index.xml"), "xataka")


class DigestTests(unittest.TestCase):
    def test_prompt_contains_sources_and_titles(self):
        items = [NewsItem("rtve", "Sube el pan", "https://a", ""),
                 NewsItem("xataka", "Nuevo chip", "https://b", "")]
        prompt = build_digest_prompt(items)
        self.assertIn("[rtve] Sube el pan", prompt)
        self.assertIn("[xataka] Nuevo chip", prompt)
        self.assertIn("120 palabras", prompt)


class ActiveHoursTests(unittest.TestCase):
    def test_day_window(self):
        self.assertTrue(in_active_hours(9, 9, 21))
        self.assertTrue(in_active_hours(20, 9, 21))
        self.assertFalse(in_active_hours(21, 9, 21))
        self.assertFalse(in_active_hours(8, 9, 21))

    def test_overnight_window(self):
        self.assertTrue(in_active_hours(23, 22, 6))
        self.assertTrue(in_active_hours(5, 22, 6))
        self.assertFalse(in_active_hours(12, 22, 6))

    def test_same_start_end_means_always(self):
        self.assertTrue(in_active_hours(3, 0, 0))


class NewsAgentTests(unittest.TestCase):
    """El ciclo solo arranca con noticias activadas y dentro del horario."""

    def setUp(self):
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        from core.news_agent import NewsAgent
        self.agent = NewsAgent(first_delay_ms=3_600_000)  # sin arranque automático
        self.addCleanup(self.agent.shutdown)

    def test_tick_skips_when_disabled(self):
        with patch("core.news_agent.app_settings.value", return_value=False), \
             patch("core.news_agent._DigestWorker") as worker:
            self.agent._tick(hour=12)
        worker.assert_not_called()

    def test_tick_skips_outside_active_hours(self):
        with patch("core.news_agent.app_settings.value", return_value=True), \
             patch("core.news_agent.app_settings.env", side_effect=lambda n, d="": d), \
             patch("core.news_agent._DigestWorker") as worker:
            self.agent._tick(hour=3)  # fuera de 9-21
        worker.assert_not_called()

    def test_tick_fetches_when_enabled_and_in_time(self):
        with patch("core.news_agent.app_settings.value", return_value=True), \
             patch("core.news_agent.app_settings.env", side_effect=lambda n, d="": d), \
             patch("core.news_agent._DigestWorker") as worker:
            self.agent._tick(hour=12)
        worker.assert_called_once()
        worker.return_value.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
