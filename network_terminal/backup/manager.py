"""Gestión de archivos de backup de configuración."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from ..core.errors import DependencyMissingError
from ..core.validation import sanitize_filename_component

log = logging.getLogger(__name__)

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:  # se resuelve con: pip install pyyaml
    yaml = None
    _YAML_AVAILABLE = False


def get_desktop_dir() -> Path:
    """Escritorio del usuario actual.

    En Windows usa la API de carpetas conocidas (respeta la redirección de
    OneDrive). En otros SO usa XDG o ``~/Desktop``, con ``~`` como último recurso.
    """
    if sys.platform.startswith("win"):
        try:
            buf = ctypes.create_unicode_buffer(260)  # MAX_PATH
            # CSIDL_DESKTOPDIRECTORY = 0x10 ; SHGFP_TYPE_CURRENT = 0
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)
            if buf.value and Path(buf.value).is_dir():
                return Path(buf.value)
        except Exception:
            log.debug("SHGetFolderPathW falló; se usa fallback", exc_info=True)
        for cand in (Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop"):
            if cand.is_dir():
                return cand
        return Path.home()

    xdg = os.environ.get("XDG_DESKTOP_DIR")
    if xdg and Path(xdg).is_dir():
        return Path(xdg)
    cand = Path.home() / "Desktop"
    return cand if cand.is_dir() else Path.home()


def build_backup_filename(
    host: str, when: datetime | None = None, ext: str = ".txt"
) -> str:
    when = when or datetime.now()
    stamp = when.strftime("%Y-%m-%d_%H-%M-%S")
    return f"{sanitize_filename_component(host, fallback='device')}_{stamp}{ext}"


class BackupManager:
    def __init__(self, target_dir: Path | None = None):
        self.target_dir = Path(target_dir) if target_dir else get_desktop_dir()

    def _unique_path(self, name: str) -> Path:
        path = self.target_dir / name
        counter = 1
        while path.exists():  # nunca sobrescribir un archivo previo
            path = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        return path

    def save_config(
        self, content: str, host: str, when: datetime | None = None
    ) -> Path:
        if not content or not content.strip():
            raise ValueError("La configuración está vacía; no se guardó nada.")
        self.target_dir.mkdir(parents=True, exist_ok=True)
        path = self._unique_path(build_backup_filename(host, when, ext=".txt"))
        path.write_text(content, encoding="utf-8")
        log.info("backup creado: %s (%d bytes)", path, path.stat().st_size)
        return path

    def save_yaml(
        self, data: dict, host: str, when: datetime | None = None
    ) -> Path:
        if not _YAML_AVAILABLE:
            raise DependencyMissingError(
                "PyYAML no está instalado",
                user_message="La exportación a YAML requiere PyYAML:  pip install pyyaml",
            )
        if not data:
            raise ValueError("No hay datos para exportar a YAML.")
        self.target_dir.mkdir(parents=True, exist_ok=True)
        path = self._unique_path(build_backup_filename(host, when, ext=".yaml"))
        text = yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=100,
        )
        path.write_text(text, encoding="utf-8")
        log.info("YAML creado: %s (%d bytes)", path, path.stat().st_size)
        return path
