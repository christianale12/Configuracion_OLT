"""Cliente SSH basado en paramiko.

paramiko es una dependencia opcional: si no está instalada, la app arranca igual
y Telnet sigue funcionando; al intentar conectar por SSH se informa cómo instalarla
(``pip install paramiko``).
"""

from __future__ import annotations

import logging
import socket

from ..core.errors import (
    AuthFailedError,
    ConnectFailedError,
    ConnectTimeoutError,
    DependencyMissingError,
    HostInvalidError,
    HostKeyError,
    PortClosedError,
    ProtocolError,
)
from ..core.logging_setup import APP_DIR
from .base import BaseConnection

log = logging.getLogger(__name__)

try:
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:  # se resuelve con: pip install paramiko
    paramiko = None
    PARAMIKO_AVAILABLE = False

KNOWN_HOSTS = APP_DIR / "known_hosts"


class SshConnection(BaseConnection):
    name = "ssh"
    default_newline = "\n"

    def __init__(
        self,
        host: str,
        port: int = 22,
        *,
        username: str = "",
        password: str = "",
        connect_timeout: float = 10.0,
        trust_new_host_key: bool = False,
    ):
        super().__init__(host, port, connect_timeout=connect_timeout)
        self.username = username
        self._password = password  # solo en memoria; nunca se persiste ni se loguea
        self.trust_new_host_key = trust_new_host_key
        self._client = None
        self._chan = None

    def connect(self) -> None:
        if not PARAMIKO_AVAILABLE:
            raise DependencyMissingError(
                "paramiko no está instalado",
                user_message="SSH requiere 'paramiko'. Instalalo con:  pip install paramiko",
            )

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if KNOWN_HOSTS.exists():
            client.load_host_keys(str(KNOWN_HOSTS))

        if self.trust_new_host_key:
            # EXCEPCIÓN DOCUMENTADA (v1): TOFU (trust on first use). La primera vez
            # se acepta la host key desconocida, se PERSISTE en ~/.network_terminal/
            # known_hosts y se registra un WARNING. En conexiones posteriores la
            # clave ya queda validada. Sin esta opción, la política es RejectPolicy.
            APP_DIR.mkdir(parents=True, exist_ok=True)
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            log.warning(
                "ssh: TOFU activado; se confiará y guardará la host key de %s", self.host
            )
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self._password,
                timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout,
                allow_agent=False,
                look_for_keys=False,
            )
        except paramiko.AuthenticationException as exc:
            raise AuthFailedError(str(exc)) from exc
        except paramiko.BadHostKeyException as exc:
            raise HostKeyError(f"host key inválida: {exc}") from exc
        except paramiko.SSHException as exc:
            msg = str(exc).lower()
            if "known_hosts" in msg or "no host key" in msg:
                raise HostKeyError(str(exc)) from exc
            if "timed out" in msg:
                raise ConnectTimeoutError(str(exc)) from exc
            raise ProtocolError(str(exc)) from exc
        except socket.gaierror as exc:
            raise HostInvalidError(str(exc)) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ConnectTimeoutError(str(exc)) from exc
        except ConnectionRefusedError as exc:
            raise PortClosedError(str(exc)) from exc
        except OSError as exc:
            raise ConnectFailedError(str(exc)) from exc

        if self.trust_new_host_key:
            try:
                client.save_host_keys(str(KNOWN_HOSTS))
            except OSError:
                log.warning("ssh: no se pudo persistir known_hosts")

        self._client = client
        self._chan = client.invoke_shell(width=200, height=50)
        self._chan.settimeout(0.0)
        log.info(
            "ssh: sesión interactiva abierta con %s:%s (usuario=%s)",
            self.host,
            self.port,
            self.username or "(vacío)",
        )

    def send(self, data: str) -> None:
        if not self._chan:
            raise ConnectFailedError("canal SSH no inicializado")
        try:
            self._chan.send(data)
        except OSError as exc:
            raise ConnectFailedError(str(exc)) from exc

    def read(self) -> str:
        if not self._chan:
            return ""
        try:
            if self._chan.recv_ready():
                return self._chan.recv(65535).decode("utf-8", "replace")
        except (socket.timeout, BlockingIOError):
            return ""
        except OSError:
            return ""
        return ""

    def is_alive(self) -> bool:
        return self._chan is not None and not self._chan.closed

    def close(self) -> None:
        if self._chan:
            try:
                self._chan.close()
            except OSError:
                pass
            self._chan = None
        if self._client:
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None
        self._password = ""  # se descarta de memoria al cerrar
        log.info("ssh: conexión cerrada (%s:%s)", self.host, self.port)
