"""Lectura y actualización del .env preservando comentarios y orden.

Al guardar también actualiza os.environ para que los motores (que ya están
cargados) vean los cambios sin reiniciar.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def env_path() -> Path:
    return Path.cwd() / ".env"


def read_env(path: Path | None = None) -> dict[str, str]:
    path = path or env_path()
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        values[key.strip()] = raw.strip().strip('"').strip("'")
    return values


def update_env(updates: dict[str, str], path: Path | None = None) -> None:
    """Escribe los cambios en .env (preservando el resto) y en os.environ."""
    path = path or env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)

    def format_line(key: str, value: str) -> str:
        return f"{key}={value}" if value else f"{key}="

    replaced_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in pending:
                value = pending.pop(key)
                new_lines.append(format_line(key, value))
                replaced_keys.add(key)
                continue
        new_lines.append(line)

    if pending:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# Añadido desde el panel de ajustes")
        for key, value in pending.items():
            new_lines.append(format_line(key, value))
            replaced_keys.add(key)

    try:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError:
        log.exception("No se pudo escribir %s", path)
        raise
    for key in replaced_keys:
        if updates[key]:
            os.environ[key] = updates[key]
        else:
            os.environ.pop(key, None)
    log.info(".env actualizado (%d claves)", len(replaced_keys))
