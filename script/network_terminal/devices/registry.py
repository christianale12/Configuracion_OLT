"""Registro de tipos de dispositivo. Agregar un fabricante = agregar una clase aquí."""

from __future__ import annotations

from .cisco import CiscoDevice
from .generic import GenericDevice
from .mikrotik import MikroTikDevice
from .zte_olt import ZteOltDevice
from .zte_onu import ZteOnuDevice

DEVICE_TYPES = {
    MikroTikDevice.name: MikroTikDevice,
    CiscoDevice.name: CiscoDevice,
    ZteOltDevice.name: ZteOltDevice,
    ZteOnuDevice.name: ZteOnuDevice,
    GenericDevice.name: GenericDevice,
}
DEFAULT_DEVICE_TYPE = MikroTikDevice.name


def create_device(type_name: str, connection=None, **kwargs):
    try:
        cls = DEVICE_TYPES[type_name]
    except KeyError:
        raise ValueError(f"tipo de dispositivo desconocido: {type_name!r}")
    if cls is GenericDevice:
        return cls(connection, **kwargs)
    return cls(connection)
