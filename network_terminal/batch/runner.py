"""Descarga masiva de configuraciones: varias IP/host -> un archivo por equipo.

Reutiliza las capas existentes (connection / devices / backup). Aísla los fallos:
un equipo que falla no detiene al resto. Concurrencia acotada por un pool de hilos.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from ..backup.manager import BackupManager, get_desktop_dir
from ..connection.ssh_client import SshConnection
from ..connection.telnet_client import TelnetConnection
from ..core.errors import TerminalError
from ..core.validation import validate_host
from ..devices.facts import collect_device_facts
from ..devices.registry import DEFAULT_DEVICE_TYPE, create_device

OUTPUT_CHOICES = ("config", "yaml", "both")

log = logging.getLogger(__name__)

_SEPARATORS = str.maketrans({",": "\n", ";": "\n", " ": "\n", "\t": "\n", "\r": "\n"})


def parse_targets(raw: str) -> tuple[list[str], list[str]]:
    """Divide el texto en hosts. Separadores: salto de línea, coma, ';', espacio, tab.
    Ignora líneas vacías y las que empiezan con '#'. Quita duplicados (sin distinguir
    mayúsculas) conservando el orden. Devuelve ``(validos, invalidos)``.
    """
    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[str] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):  # línea de comentario completa
            continue
        for token in line.translate(_SEPARATORS).split("\n"):
            item = token.strip()
            if not item or item.startswith("#"):
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                valid.append(validate_host(item))
            except TerminalError:
                invalid.append(item)
    return valid, invalid


@dataclass
class BulkConfig:
    username: str = ""
    password: str = ""  # solo en memoria
    protocol: str = "ssh"  # "ssh" | "telnet"
    port: int = 22
    device_type: str = DEFAULT_DEVICE_TYPE
    trust_new_host_key: bool = False
    connect_timeout: float = 10.0
    max_workers: int = 5
    read_quiet: float = 2.0
    read_timeout: float = 60.0
    output: str = "config"  # "config" (.txt) | "yaml" (estructurado) | "both"
    include_raw: bool = True  # incluir el texto crudo en el YAML


@dataclass
class HostResult:
    host: str
    ok: bool = False
    path: Path | None = None  # primer archivo guardado (compatibilidad)
    paths: list = field(default_factory=list)  # todos los archivos guardados
    chars: int = 0
    error: str = ""  # mensaje para el usuario
    detail: str = ""  # técnico (sin secretos)
    duration: float = 0.0

    @property
    def status(self) -> str:
        return "OK" if self.ok else "ERROR"

    @property
    def filenames(self) -> str:
        return ", ".join(p.name for p in self.paths)


def _default_connection_factory(host: str, cfg: BulkConfig):
    if cfg.protocol == "ssh":
        return SshConnection(
            host,
            cfg.port,
            username=cfg.username,
            password=cfg.password,
            connect_timeout=cfg.connect_timeout,
            trust_new_host_key=cfg.trust_new_host_key,
        )
    if cfg.protocol == "telnet":
        return TelnetConnection(host, cfg.port, connect_timeout=cfg.connect_timeout)
    raise TerminalError(
        f"protocolo no soportado: {cfg.protocol!r}",
        user_message="Protocolo no soportado.",
    )


def _capture(device, cfg: BulkConfig) -> str:
    for prep in device.prepare_commands():
        device.execute(prep, quiet_after=0.5, overall_timeout=10.0)
    return device.execute(
        device.running_config_command(),
        quiet_after=cfg.read_quiet,
        overall_timeout=cfg.read_timeout,
    )


def download_configs(
    hosts,
    cfg: BulkConfig,
    *,
    backup_dir=None,
    backup_manager=None,
    connection_factory=None,
    cancel_event=None,
    on_result=None,
    on_progress=None,
) -> list[HostResult]:
    """Descarga la running-config de cada host y la guarda en un archivo.

    ``on_result(HostResult)`` y ``on_progress(hechos, total)`` se llaman a medida
    que terminan los equipos (desde hilos del pool: la GUI debe reencolar con
    ``after()``). Devuelve la lista de resultados en el orden original de ``hosts``.
    """
    factory = connection_factory or _default_connection_factory
    manager = backup_manager or BackupManager(
        Path(backup_dir) if backup_dir else get_desktop_dir()
    )
    cancel_event = cancel_event or threading.Event()
    save_lock = threading.Lock()
    hosts = list(hosts)
    total = len(hosts)
    order = {h: i for i, h in enumerate(hosts)}
    results: list[HostResult] = []
    done = 0

    log.info(
        "descarga masiva: %d equipo(s), protocolo=%s, concurrencia=%d",
        total,
        cfg.protocol,
        cfg.max_workers,
    )

    def one(host: str) -> HostResult:
        start = time.monotonic()
        if cancel_event.is_set():
            return HostResult(
                host, ok=False, error="Cancelado", detail="cancelado por el usuario"
            )
        conn = None
        try:
            conn = factory(host, cfg)
            conn.connect()
            login = getattr(conn, "login", None)
            if callable(login) and (cfg.username or cfg.password):
                login(cfg.username, cfg.password)
            device = create_device(cfg.device_type, conn)

            saved: list = []
            chars = 0
            if cfg.output in ("config", "both"):
                text = _capture(device, cfg)
                if not text or not text.strip():
                    raise TerminalError(
                        "salida vacía", user_message="La configuración vino vacía."
                    )
                chars = len(text)
                with save_lock:
                    saved.append(manager.save_config(text, host))
            if cfg.output in ("yaml", "both"):
                facts = collect_device_facts(
                    device,
                    lambda c: device.execute(
                        c,
                        quiet_after=cfg.read_quiet,
                        overall_timeout=cfg.read_timeout,
                    ),
                    host=host,
                    protocol=cfg.protocol,
                    include_raw=cfg.include_raw,
                )
                with save_lock:
                    saved.append(manager.save_yaml(facts, host))

            dur = time.monotonic() - start
            log.info(
                "descarga masiva: %s OK -> %s (%.1fs)",
                host,
                ", ".join(p.name for p in saved),
                dur,
            )
            return HostResult(
                host,
                ok=True,
                path=saved[0] if saved else None,
                paths=saved,
                chars=chars,
                duration=dur,
            )
        except TerminalError as exc:
            dur = time.monotonic() - start
            log.warning(
                "descarga masiva: %s ERROR: %s | %s", host, exc.user_message, exc.detail
            )
            return HostResult(
                host, ok=False, error=exc.user_message, detail=exc.detail, duration=dur
            )
        except Exception as exc:  # un equipo no debe frenar al resto
            dur = time.monotonic() - start
            log.exception("descarga masiva: %s error inesperado", host)
            return HostResult(
                host, ok=False, error="Error inesperado.", detail=str(exc), duration=dur
            )
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if total:
        with ThreadPoolExecutor(max_workers=max(1, cfg.max_workers)) as pool:
            futures = [pool.submit(one, h) for h in hosts]
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                done += 1
                if on_result:
                    on_result(res)
                if on_progress:
                    on_progress(done, total)

    results.sort(key=lambda r: order.get(r.host, 0))
    ok = sum(1 for r in results if r.ok)
    log.info("descarga masiva finalizada: %d OK, %d con error", ok, len(results) - ok)
    return results
