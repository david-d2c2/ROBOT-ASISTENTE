"""Habilidades locales: respuestas instantáneas declaradas en JSON.

Cada archivo skills/*.json declara disparadores y una respuesta; el robot
responde sin llamar al proveedor de IA (útil para frases fijas, modos demo,
atajos de personalidad...). Formato:

{
  "name": "modo demo",
  "triggers": ["modo demo", "demo"],
  "response": "Habilidad local activada.",
  "say": true
}
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def skills_dir() -> Path:
    return Path.cwd() / "skills"


def load_skills() -> list[dict]:
    directory = skills_dir()
    if not directory.exists():
        return []
    skills = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("Habilidad inválida: %s", path)
            continue
        triggers = [str(t).lower().strip() for t in data.get("triggers", []) if str(t).strip()]
        response = data.get("response")
        if not triggers or not response:
            log.warning("Habilidad sin triggers o response: %s", path)
            continue
        skills.append({
            "name": str(data.get("name", path.stem)),
            "triggers": triggers,
            "response": str(response),
            "say": bool(data.get("say", False)),
        })
    return skills


def match_skill(text: str, skills: list[dict] | None = None) -> dict | None:
    """Devuelve la habilidad cuyo disparador inicia el texto (o None)."""
    cleaned = (text or "").lower().strip()
    if not cleaned:
        return None
    for skill in (skills if skills is not None else load_skills()):
        for trigger in skill["triggers"]:
            if cleaned == trigger or cleaned.startswith(trigger + " ") or cleaned.startswith(trigger + ","):
                return skill
    return None
