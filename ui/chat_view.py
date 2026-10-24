"""Vista de conversación: burbujas, streaming agregado y markdown ligero."""
import html
import logging
import re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QTextBrowser

log = logging.getLogger(__name__)


class ChatView(QTextBrowser):
    """Muestra la conversación como burbujas; también frases sueltas ('solo')."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setAccessibleName("Conversación con el robot")
        self.messages: list[dict] = []
        self.status_text: str | None = None
        self.solo_text: str | None = None
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(120)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self.render)

    # ---- API de alto nivel ----

    def append_message(self, role: str, text: str):
        self.messages.append({"role": role, "text": text})
        if len(self.messages) > 60:
            self.messages = self.messages[-60:]
        self.render()

    def show_single(self, text: str):
        """Reemplaza la conversación visible por un único mensaje del sistema."""
        self.messages = [{"role": "system", "text": text}]
        self.status_text = None
        self.solo_text = None
        self.render()

    def set_solo(self, text: str | None):
        self.solo_text = text
        self.render()

    def set_status(self, text: str | None):
        self.status_text = text
        self.render()

    def last_message_text(self) -> str:
        if self.solo_text:
            return self.solo_text
        if self.status_text:
            return self.status_text
        if self.messages:
            return self.messages[-1]["text"]
        return ""

    def copy_last_answer(self) -> str | None:
        for message in reversed(self.messages):
            if message["role"] == "assistant":
                QApplication.clipboard().setText(message["text"])
                return message["text"]
        return None

    def mark_last_answer(self, extra: str):
        """Añade un texto (p. ej. un error de voz) a la última respuesta."""
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages[-1]["text"] += "\n" + extra

    # ---- Render ----

    def render(self):
        if self.solo_text:
            self.setHtml(self._message_html("quip", self.solo_text))
            self._scroll_bottom()
            return
        parts = [self._message_html(m["role"], m["text"]) for m in self.messages]
        if self.status_text:
            parts.append(self._message_html("system", self.status_text))
        self.setHtml("".join(parts) or "&nbsp;")
        self._scroll_bottom()

    def render_soon(self):
        if not self._render_timer.isActive():
            self._render_timer.start()

    def update_partial(self, text: str):
        """Texto parcial de streaming: actualiza o crea la respuesta en curso."""
        self.status_text = None
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages[-1]["text"] = text
        else:
            self.messages.append({"role": "assistant", "text": text})
        self.render_soon()

    @staticmethod
    def _md_to_html(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        return escaped.replace("\n", "<br>")

    def _message_html(self, role: str, text: str) -> str:
        body = self._md_to_html(text)
        if role == "user":
            return (
                '<table width="100%" cellspacing="0" cellpadding="3"><tr>'
                '<td align="right"><span style="background-color:#0E3A46; color:#BFF7FF;">'
                f"&nbsp;{body}&nbsp;</span></td></tr></table>"
            )
        if role == "quip":
            return f'<i style="color:#8FF7FF;">{body}</i>'
        if role == "system":
            return f'<i style="color:#7E93A9;">{body}</i><br>'
        return (
            '<table width="100%" cellspacing="0" cellpadding="3"><tr>'
            '<td align="left"><span style="background-color:#101B2E; color:#8FF7FF;">'
            f"&nbsp;{body}&nbsp;</span></td></tr></table>"
        )

    def _scroll_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
