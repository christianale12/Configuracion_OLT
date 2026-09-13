from __future__ import annotations

from .base import Device


class GenericDevice(Device):
    name = "Genérico"

    def __init__(self, connection=None, config_command: str = "show running-config"):
        super().__init__(connection)
        self._config_command = config_command

    def running_config_command(self) -> str:
        return self._config_command
