#!/usr/bin/env python3
"""
Parsers y listado de modelos de la OLT ZTE ZXAN (GPON)
=======================================================
Parte 2 del antiguo nucleo.py. Contiene:
  - Listado dinamico de modelos de ONU (MODELOS_ONU) + persistencia en disco
  - Parsers de salidas de la OLT (onus, interfaces, estado)
  - Verificacion de que la configuracion quedo aplicada

Lo usa vistas.py junto con comandos.py (la otra mitad, que arma los
comandos y valida los datos del formulario).
"""

import json
import os
import re

from comandos import RE_MODELO


# ---------------------------------------------------------------------------
# Listado dinamico de modelos de ONU + persistencia
# ---------------------------------------------------------------------------
# Lista base de modelos; ambas versiones la actualizan desde la OLT con la
# accion "modelos" y la guardan en %APPDATA%.
MODELOS_ONU = {
    "generic-F670": "4GE,2POTS,WIFI",
    "ZTEG-F670": "4GE_1POTS_WIFI",
    "ZTEG-F670L": "4GE_1POTS_WIFI",
    "generic-F601": "1GE",
}


def parsear_modelos(salida):
    """
    Extrae los modelos de ONU registrados en la OLT a partir de la salida de
    'show running-config'. En la config aparecen como:

        onu-type ZTEG-F670 gpon description 4GE_1POTS_WIFI
        onu-type ZTEG-F670 gpon max-tcont 8

    Devuelve un dict {modelo: descripcion} preservando el orden de aparicion.
    """
    modelos = {}
    for ln in salida.splitlines():
        m = re.match(r"\s*onu-type\s+(\S+)\s+gpon"
                     r"(?:\s+description\s+(.+?))?\s*$", ln, re.IGNORECASE)
        if not m:
            continue
        nombre = m.group(1)
        desc = (m.group(2) or "").strip()
        if nombre not in modelos:
            modelos[nombre] = desc
        elif desc and not modelos[nombre]:
            modelos[nombre] = desc
    return modelos


def _ruta_modelos():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    carpeta = os.path.join(base, "AprovisionamientoONU")
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, "modelos_onu.json")


def cargar_modelos():
    """Suma al listado base los modelos guardados de sesiones anteriores."""
    try:
        with open(_ruta_modelos(), "r", encoding="utf-8") as fh:
            guardados = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(guardados, dict):
        return
    for nombre, desc in guardados.items():
        if RE_MODELO.match(nombre) and nombre not in MODELOS_ONU:
            MODELOS_ONU[nombre] = str(desc or "")


def guardar_modelos():
    try:
        with open(_ruta_modelos(), "w", encoding="utf-8") as fh:
            json.dump(MODELOS_ONU, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


cargar_modelos()


# ---------------------------------------------------------------------------
# Validacion de que la configuracion quedo aplicada correctamente
# ---------------------------------------------------------------------------
def verificar_aplicacion(salida, onu_id, servicios_extra):
    problemas = []
    esperados = [
        "sn-bind enable sn",
        "service-port 1 vport 1 user-vlan 200 vlan 200",
        "service 1 gemport 1 vlan 200",
        "vlan port eth_0/1 mode tag vlan 200",
        "vlan port eth_0/4 mode tag vlan 200",
    ]
    if servicios_extra:
        esperados += [
            "service-port 2 vport 2 user-vlan 300 vlan 300",
            "service-port 3 vport 3 user-vlan 400 vlan 400",
            "service 2 gemport 1 vlan 300",
            "service 3 gemport 1 vlan 400",
            "vlan port eth_0/1 mode tag vlan 300",
            "vlan port eth_0/1 mode tag vlan 400",
        ]

    faltantes = [linea for linea in esperados if linea not in salida]
    if faltantes:
        problemas.append("Faltan en la configuracion aplicada: " + ", ".join(faltantes))

    linea_onu = next(
        (ln for ln in salida.splitlines()
         if re.search(rf"(?<![0-9A-Za-z]){re.escape(onu_id)}(?![0-9A-Za-z])", ln)
         and any(p in ln.lower() for p in ("online", "offline", "off-line",
                                           "absent", "state:", "working"))), None)
    if linea_onu is None:
        problemas.append(
            "No se encontro una linea de estado (online/offline/working) "
            "para la ONU %s en el estado del puerto." % onu_id)
    elif not any(estado in linea_onu.lower() for estado in ("online", "working")):
        problemas.append(
            "La ONU %s no figura 'online' ni 'working' (%s)." % (onu_id, linea_onu.strip()))

    return len(problemas) == 0, problemas


# ---------------------------------------------------------------------------
# Parsers de salidas de la OLT
# ---------------------------------------------------------------------------
def parsear_onus_activas(salida):
    """
    Lee la salida de 'show gpon onu state' y devuelve las ONUs del puerto
    con su onu-id y fase/estado (working, online, offline, pause, etc.).
    Devuelve una lista de dicts: [{"id": "2", "fase": "working"}, ...]
    """
    activas = []
    vistos = set()
    for ln in salida.splitlines():
        bajo = ln.lower()
        if "gpon-onu_" not in ln and "onu-index" not in bajo and "index:" not in bajo:
            continue
        m = re.search(
            r":(\d+)\s+.*?(working|online|offline|off-line|los|dying-gasp|absent|pause)",
            bajo)
        if not m:
            continue
        id_onu = m.group(1)
        if id_onu not in vistos:
            vistos.add(id_onu)
            activas.append({"id": id_onu, "fase": m.group(2)})
    return activas


def parsear_onus_config(salida):
    """
    Lee la salida de 'show running-config interface gpon-olt_X' y devuelve
    las ONUs configuradas: [{"id": "2", "modelo": "generic-F670", "sn": "ZTE..."}]
    """
    onus = []
    for m in re.finditer(r"onu (\d+) type (\S+) sn (\S+)", salida):
        # Evita duplicados de la misma onu (puede reconfigurarse)
        if not any(o["id"] == m.group(1) for o in onus):
            onus.append({"id": m.group(1), "modelo": m.group(2), "sn": m.group(3)})
    return onus


def mostrar_onus_ocupadas(salida_run, salida_state):
    """Une running-config + estado del puerto y devuelve un listado legible."""
    config = parsear_onus_config(salida_run)
    estado = {o["id"]: o["fase"] for o in parsear_onus_activas(salida_state)}
    if not config:
        return "No hay ONUs configuradas en este puerto."
    lineas = ["ONU-ID   MODELO         SN           ESTADO"]
    lineas.append("-" * 55)
    orden = sorted(config, key=lambda o: int(o["id"]))
    for onu in orden:
        estado_onu = estado.get(onu["id"], "no informa")
        lineas.append("%-8s %-14s %-13s %s" % (
            onu["id"], onu["modelo"], onu["sn"], estado_onu))
    # ONUs activas sin config (registradas pero sin alta)
    extras = [i for i in estado if i not in {o["id"] for o in config}]
    for i in extras:
        lineas.append("%-8s %-14s %-13s %s" % (i, "-", "-", estado[i]))
    return "\n".join(lineas)


def parsear_interfaces(salida):
    """
    Recorre la salida de 'show running-config interface gpon-olt_...' y separa
    los puertos GPON de la OLT en prendidos y apagados según 'no shutdown' /
    'shutdown'. Devuelve dos listas ordenadas, con la ruta sin prefijo
    (ej: ["1/13/1", "1/13/2"]).
    """
    up, down = [], []
    actual = None
    for ln in salida.splitlines():
        m = re.match(r"\s*interface\s+gpon-olt_(\d+/\d+/\d+)", ln, re.IGNORECASE)
        if m:
            actual = m.group(1)
            continue
        if actual is None:
            continue
        s = ln.strip().lower()
        if s == "shutdown":
            down.append(actual); actual = None
        elif s == "no shutdown":
            up.append(actual); actual = None
        elif s.startswith("interface ") or s == "!":
            up.append(actual); actual = None
    if actual is not None:
        up.append(actual)

    def orden(ruta):
        try:
            return tuple(int(p) for p in ruta.split("/"))
        except ValueError:
            return (999, 999, 999)

    up = sorted(set(up), key=orden)
    down = sorted(set(down), key=orden)
    return up, down


def comandos_escanear_interfaces(puerto):
    """Comandos cortos (uno por puerto) para leer el estado de los 16 puertos
    GPON de la tarjeta a la que pertenece 'puerto' (ej: 1/13/4 -> card 1/13)."""
    base = "/".join(puerto.split("/")[:2])
    return [f"show running-config interface gpon-olt_{base}/{n}"
            for n in range(1, 17)]