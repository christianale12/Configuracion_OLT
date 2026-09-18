#!/usr/bin/env python3
"""
Comandos y validaciones de la OLT ZTE ZXAN (GPON)
==================================================
Parte 1 del antiguo nucleo.py. Contiene:
  - Armado de los comandos de alta de ONU (construir_comandos_alta)
  - Validacion de los datos del formulario (anti inyeccion de comandos)
  - Listas fijas y expresiones regulares de validacion

Lo usado junto con parsers.py (la otra mitad, que lee las salidas de la OLT).
"""

import re

# ---------------------------------------------------------------------------
# Logica de armado de comandos (misma que el script de linea de comandos)
# ---------------------------------------------------------------------------
def nombre_traffic_profile(plan):
    sufijo = plan.replace("plan-", "").upper()
    return f"DOWN-{sufijo}"


def construir_comandos_alta(puerto, onu_id, modelo, sn, plan, modo, servicios_extra=False):
    interfaz_olt = f"gpon-olt_{puerto}"
    interfaz_onu = f"gpon-onu_{puerto}:{onu_id}"
    plan_norm = plan if plan.startswith("plan-") else f"plan-{plan}"
    traffic = nombre_traffic_profile(plan_norm)

    comandos = ["configure terminal", f"interface {interfaz_olt}",
                f"onu {onu_id} type {modelo} sn {sn}", "exit"]

    comandos += [f"interface {interfaz_onu}", "sn-bind enable sn",
                 f"tcont 1 name internet profile {plan_norm}",
                 "gemport 1 name internet tcont 1",
                 f"gemport 1 traffic-limit downstream {traffic}",
                 "switchport mode hybrid vport 1",
                 "service-port 1 vport 1 user-vlan 200 vlan 200"]

    if servicios_extra:
        comandos += ["switchport mode hybrid vport 2",
                     "switchport mode hybrid vport 3",
                     "service-port 2 vport 2 user-vlan 300 vlan 300",
                     "service-port 3 vport 3 user-vlan 400 vlan 400"]

    comandos.append("exit")
    comandos.append(f"pon-onu-mng {interfaz_onu}")
    comandos.append("service 1 gemport 1 vlan 200")
    if servicios_extra:
        comandos += ["service 2 gemport 1 vlan 300",
                     "service 3 gemport 1 vlan 400"]

    if modo == "router":
        comandos.append("wan-ip 1 mode dhcp vlan-profile HSI-200 host 1")

    for n in (1, 2, 3, 4):
        comandos.append(f"vlan port eth_0/{n} mode tag vlan 200")
        if servicios_extra:
            comandos.append(f"vlan port eth_0/{n} mode tag vlan 300")
            comandos.append(f"vlan port eth_0/{n} mode tag vlan 400")

    comandos += ["exit", "end", f"show gpon onu state {interfaz_olt}"]
    return comandos


# ---------------------------------------------------------------------------
# Validacion de datos del formulario (evita inyeccion de comandos)
# ---------------------------------------------------------------------------
# Lista fija que usa la validacion (definida aca porque es de validacion).
MODELOS_VALIDOS = {"generic-F670", "ZTEG-F670", "ZTEG-F670L", "generic-F601"}
PLANES_VALIDOS = {"100m", "300m", "600m", "1g",
                  "plan-100m", "plan-300m", "plan-600m", "plan-1g"}

RE_PUERTO = re.compile(r"^\d+(?:/\d+){1,3}$")
RE_SN = re.compile(r"^[A-Za-z0-9]{12}$")
RE_MODELO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def validar_puerto(puerto):
    if not RE_PUERTO.match(puerto):
        raise ValueError("Puerto invalido (formato esperado: 1/13/4).")


def validar_onu_id(onu_id):
    if not onu_id.isdigit() or not (1 <= int(onu_id) <= 128):
        raise ValueError("El numero de ONU debe ser un entero entre 1 y 128.")


def validar_sn(sn):
    if not RE_SN.match(sn):
        raise ValueError("El SN debe tener exactamente 12 caracteres alfanumericos.")


def validar_opciones(modelo, plan, modo, modelos_validos=None):
    """
    Valida modelo/plan/modo. Si 'modelos_validos' es un conjunto, el modelo
    debe estar en el; si es None, se acepta cualquier nombre de modelo seguro
    (para las dos versiones, que actualizan la lista desde la OLT).
    """
    if modelos_validos is not None:
        if modelo not in modelos_validos:
            raise ValueError(f"Modelo no soportado: {modelo}")
    elif not RE_MODELO.match(modelo):
        raise ValueError(f"Modelo invalido: {modelo}")
    plan_norm = plan if plan.startswith("plan-") else f"plan-{plan}"
    if plan_norm not in PLANES_VALIDOS:
        raise ValueError(f"Plan no soportado: {plan}")
    if modo not in ("router", "bridge"):
        raise ValueError(f"Modo no soportado: {modo}")