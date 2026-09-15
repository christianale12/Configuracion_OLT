"""Jerarquía de errores con mensajes aptos para el usuario final.

Cada error lleva:
- ``user_message``: texto corto y claro para mostrar en la interfaz.
- ``detail``: información técnica para el log (nunca debe contener secretos).
"""

from __future__ import annotations


class TerminalError(Exception):
    user_message = "Ocurrió un error."

    def __init__(self, detail: str = "", *, user_message: str | None = None):
        super().__init__(detail or self.__class__.user_message)
        self.detail = detail
        if user_message:
            self.user_message = user_message


class HostInvalidError(TerminalError):
    user_message = "Host inválido."


class ConnectFailedError(TerminalError):
    user_message = "No se pudo conectar con el equipo."


class ConnectTimeoutError(TerminalError):
    user_message = "Tiempo de espera agotado."


class AuthFailedError(TerminalError):
    user_message = "Autenticación fallida."


class PortClosedError(TerminalError):
    user_message = "No se pudo establecer conexión en el puerto indicado."


class ProtocolError(TerminalError):
    user_message = "No se pudo negociar la conexión (protocolo rechazado)."


class HostKeyError(TerminalError):
    user_message = (
        "La clave del host no está en la lista de confianza. "
        "Verificá el equipo o activá 'Confiar en host key'."
    )


class DependencyMissingError(TerminalError):
    user_message = "Falta una dependencia requerida para esta operación."
