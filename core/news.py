"""Noticias: RSS público → novedades deduplicadas → guion para el resumen.

Solo lógica sin Qt (fácil de probar): descarga y parseo de feeds RSS/Atom,
filtrado de lo ya visto (persistente) y construcción del prompt de resumen.
"""
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import requests

from PyQt6.QtCore import QStandardPaths

log = logging.getLogger(__name__)

# Feeds públicos en español por defecto (se sustituyen con NEWS_FEEDS o ajustes).
DEFAULT_FEEDS = [
    "https://www.rtve.es/rss/noticias.xml",
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "https://www.xataka.com/index.xml",
]

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
FETCH_TIMEOUT = 10
SEEN_DAYS = 7


@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    summary: str


def strip_html(text: str) -> str:
    """Título/resumen legibles: sin etiquetas ni entidades HTML."""
    cleaned = TAG_RE.sub(" ", html_unescape(str(text or "")))
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def html_unescape(text: str) -> str:
    from html import unescape
    return unescape(unescape(text))


def item_key(item: NewsItem) -> str:
    """Identidad estable de una noticia: su titular normalizado (los enlaces
    cambian con parámetros de seguimiento)."""
    normalized = WHITESPACE_RE.sub(" ", item.title.lower()).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def parse_feed(xml_text: str, source: str = "") -> list[NewsItem]:
    """Parsea un feed RSS (<item>) o Atom (<entry>) tolerante a campos que falten."""
    items: list[NewsItem] = []
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ElementTree.ParseError:
        log.warning("Feed con XML inválido: %s", source)
        return []

    def local_name(tag: str) -> str:
        return tag.rpartition("}")[2] if "}" in tag else tag

    for entry in root.iter():
        name = local_name(entry.tag)
        if name not in ("item", "entry"):
            continue
        title = strip_html(_child_text(entry, "title"))
        if not title:
            continue
        if name == "item":
            link, summary_tag = _child_text(entry, "link").strip(), "description"
        else:  # Atom: el enlace va en atributos href
            link = ""
            for candidate in entry.iter():
                if local_name(candidate.tag) == "link":
                    link = (candidate.get("href") or candidate.text or "").strip()
                    if link:
                        break
            summary_tag = "summary"
        items.append(NewsItem(
            source=source,
            title=title,
            url=link,
            summary=strip_html(_child_text(entry, summary_tag))[:280],
        ))
    return items


def _child_text(entry, tag: str) -> str:
    for node in entry:
        name = node.tag.rpartition("}")[2] if "}" in node.tag else node.tag
        if name == tag and node.text:
            return node.text.strip()
    return ""


def fetch_items(feeds: list[str], fetch=None) -> list[NewsItem]:
    """Descarga todos los feeds; un feed caído no tira del resto."""
    fetch = fetch or _http_get
    items: list[NewsItem] = []
    for url in feeds:
        url = url.strip()
        if not url:
            continue
        try:
            items.extend(parse_feed(fetch(url), source=feed_name(url)))
        except Exception:
            log.warning("Feed inaccesible: %s", url, exc_info=True)
    return items


def _http_get(url: str) -> str:
    response = requests.get(url, timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def feed_name(url: str) -> str:
    """Nombre humano del medio a partir de su URL (www.xataka.com → xataka)."""
    match = re.search(r"//(?:www\.)?([^/]+)\.", url)
    return match.group(1) if match else url


def seen_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    directory = Path(base) / "RobotAsistente"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "noticias_vistas.json"


class SeenStore:
    """Titulares ya contados, persistentes; se limpian los de hace más de una semana."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): float(v) for k, v in raw.items()}
        except (OSError, ValueError):
            pass
        return {}

    def filter_new(self, items: list[NewsItem]) -> list[NewsItem]:
        return [item for item in items if item_key(item) not in self._data]

    def mark(self, items: list[NewsItem], now: float | None = None):
        moment = now if now is not None else time.time()
        for item in items:
            self._data[item_key(item)] = moment
        self._prune(moment)
        try:
            self.path.write_text(json.dumps(self._data), encoding="utf-8")
        except OSError:
            log.warning("No se pudo guardar el registro de noticias vistas")

    def _prune(self, now: float):
        limite = now - SEEN_DAYS * 86_400
        self._data = {k: v for k, v in self._data.items() if v >= limite}


def build_digest_prompt(items: list[NewsItem]) -> str:
    """Guion para el resumen hablado: breve, sin markdown, con cierre que invita."""
    lineas = [f"- [{item.source}] {item.title}" for item in items]
    return (
        "Vas a hablar en voz alta al usuario sobre las últimas noticias. Con estos "
        "titulares, escribe un resumen de máximo 120 palabras, en español, sin markdown "
        "ni listas, como lo contaría una radio: agrupa por temas si procede y di la "
        "fuente al mencionar cada una. Termina preguntando si quiere que profundice "
        "en alguna. Titulares:\n" + "\n".join(lineas)
    )


def in_active_hours(hour: int, start: int = 9, end: int = 21) -> bool:
    """Horario en el que el robot puede interrumpir; end exclusivo. Si start==end,
    no hay restricción (24 h)."""
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # franja nocturna (p. ej. 22 → 6)
