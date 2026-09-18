#!/usr/bin/env python3
"""
Vistas / controlador web (rutas Flask)
=======================================
Un solo controlador compartido por las dos versiones (Telnet y SSH).
La unica diferencia real entre versiones es el transporte, así que este
modulo recibe como parametros:
  - 'ejecutar': la funcion que ejecuta comandos en la OLT
                (transporte_telnet.ejecutar_por_telnet o .ejecutar_por_ssh)
  - 'template': plantilla a renderizar (index.html / index_ssh.html)
  - 'conectar': si la version tiene la accion "conectar" (solo SSH)
  - 'modelos':  si la version actualiza la lista de modelos desde la OLT
                (ambas versiones)
  - 'modelos_validos': conjunto fijo de modelos o None para aceptar
                cualquier modelo seguro

Uso en app.py / app_ssh.py:
    vistas.registrar(app, ejecutar, "index.html", modelos=True)
"""

import re

from flask import request, render_template

from comandos import (
    validar_puerto, validar_onu_id, validar_sn, validar_opciones,
    construir_comandos_alta,
)
from parsers import (
    MODELOS_ONU,
    parsear_modelos, guardar_modelos,
    parsear_interfaces, comandos_escanear_interfaces,
    mostrar_onus_ocupadas, verificar_aplicacion,
)


def registrar(app, ejecutar, template,
              conectar=False, modelos=False, modelos_validos=None):
    """Define la ruta '/' de 'app' con el controlador compartido."""

    @app.route("/", methods=["GET", "POST"])
    def index():
        f = dict(request.form)
        salida = None
        error = None
        comandos_previos = None
        confirm_accion = None
        confirmado = False
        verificacion_ok = None
        verificacion_notas = None
        interfaces_up = None
        interfaces_down = None

        if request.method == "POST":
            host = f.get("host", "").strip()
            user = f.get("user", "").strip()
            password = f.get("password", "")
            puerto = f.get("puerto", "").strip()
            accion = f.get("accion")

            try:
                if accion == "volver":
                    pass

                elif conectar and accion == "conectar":
                    salida = ejecutar(host, user, password, ["show version"])
                    if "%" in salida and any(
                            k in salida.lower() for k in ("invalid", "syntax", "unknown")):
                        raise RuntimeError(
                            "El login fue correcto, pero la OLT no reconocio "
                            "el comando 'show version'.")

                elif modelos and accion == "modelos":
                    salida_run = ejecutar(
                        host, user, password, ["show running-config"])
                    encontrados = parsear_modelos(salida_run)
                    nuevos = []
                    for nombre, desc in encontrados.items():
                        if nombre not in MODELOS_ONU:
                            MODELOS_ONU[nombre] = desc
                            nuevos.append(nombre)
                        elif desc and not MODELOS_ONU[nombre]:
                            MODELOS_ONU[nombre] = desc
                    if not encontrados:
                        salida = ("No se encontraron modelos 'onu-type' en la "
                                  "OLT; se mantiene la lista actual.")
                    elif nuevos:
                        guardar_modelos()
                        salida = ("Se agregaron %d modelo(s) nuevo(s) desde la OLT: "
                                  "%s.\n\nLista completa (%d):\n%s" %
                                  (len(nuevos), ", ".join(nuevos), len(MODELOS_ONU),
                                   "\n".join("  " + m for m in MODELOS_ONU)))
                    else:
                        salida = ("La lista ya estaba al dia (%d modelos):\n%s" %
                                  (len(MODELOS_ONU),
                                   "\n".join("  " + m for m in MODELOS_ONU)))

                elif accion == "autocompletar":
                    validar_puerto(puerto)
                    cmds_uncfg = [f"show gpon onu uncfg gpon-olt_{puerto}"]
                    salida_uncfg = ejecutar(host, user, password, cmds_uncfg)
                    match_sn = re.search(r"\b([A-Za-z0-9]{12})\b", salida_uncfg)

                    if not match_sn:
                        error = "No se detecto ninguna ONU pendiente en este puerto."
                        f['onu_id'] = ""
                        f['sn'] = ""
                    else:
                        cmds_run = [f"show running-config interface gpon-olt_{puerto}"]
                        salida_run = ejecutar(host, user, password, cmds_run)
                        ocupados = set(int(m) for m in re.findall(
                            r"onu (\d+) type", salida_run))

                        id_libre = 1
                        while id_libre in ocupados and id_libre <= 128:
                            id_libre += 1

                        if id_libre > 128:
                            error = ("El puerto esta lleno. No hay IDs "
                                     "disponibles (limite 128).")
                        else:
                            f['onu_id'] = str(id_libre)
                            f['sn'] = match_sn.group(1)
                            salida = ("Exito: Se detecto el SN %s y se asigno "
                                      "el ID libre %s." % (f['sn'], id_libre))

                elif accion == "uncfg":
                    validar_puerto(puerto)
                    cmds = [f"show gpon onu uncfg gpon-olt_{puerto}"]
                    salida = ejecutar(host, user, password, cmds)

                elif accion == "estado":
                    validar_puerto(puerto)
                    cmds = [f"show gpon onu state gpon-olt_{puerto}"]
                    salida = ejecutar(host, user, password, cmds)

                elif accion in ("interfaz_on", "interfaz_off",
                                "interfaz_on_confirmar", "interfaz_off_confirmar"):
                    validar_puerto(puerto)
                    apagar = accion.startswith("interfaz_off")
                    cmds = ["configure terminal", f"interface gpon-olt_{puerto}",
                            "shutdown" if apagar else "no shutdown",
                            "exit", "end",
                            f"show running-config interface gpon-olt_{puerto}"]
                    comandos_previos = "\n".join(cmds)
                    if accion in ("interfaz_on_confirmar", "interfaz_off_confirmar"):
                        confirmado = True
                        salida = ejecutar(host, user, password, cmds)
                    else:
                        confirm_accion = accion + "_confirmar"

                elif accion == "interfaces":
                    validar_puerto(puerto)
                    salida_if = ejecutar(
                        host, user, password, comandos_escanear_interfaces(puerto))
                    interfaces_up, interfaces_down = parsear_interfaces(salida_if)
                    salida = ("Interfaces en %s: %d prendidas y %d apagadas. "
                              "Elegi de los desplegables de abajo." %
                              ("/".join(puerto.split("/")[:2]),
                               len(interfaces_up), len(interfaces_down)))

                elif accion == "interfaz_sel":
                    if_sel = f.get("if_sel", "").strip()
                    if_accion = f.get("if_accion", "").strip()
                    validar_puerto(if_sel)
                    if if_accion not in ("prender", "apagar"):
                        raise ValueError("Accion de interfaz invalida.")
                    apagar = if_accion == "apagar"
                    cmds = ["configure terminal", f"interface gpon-olt_{if_sel}",
                            "shutdown" if apagar else "no shutdown", "exit", "end"]
                    comandos_previos = "\n".join(cmds)
                    confirm_accion = "interfaz_sel_confirmar"

                elif accion == "interfaz_sel_confirmar":
                    if_sel = f.get("if_sel", "").strip()
                    if_accion = f.get("if_accion", "").strip()
                    validar_puerto(if_sel)
                    if if_accion not in ("prender", "apagar"):
                        raise ValueError("Accion de interfaz invalida.")
                    apagar = if_accion == "apagar"
                    cmds = ["configure terminal", f"interface gpon-olt_{if_sel}",
                            "shutdown" if apagar else "no shutdown", "exit", "end"]
                    confirmado = True
                    comandos_previos = "\n".join(cmds)
                    ejecutar(host, user, password, cmds)
                    salida = ("gpon-olt_%s %s correctamente." %
                              (if_sel, "apagada" if apagar else "prendida"))
                    if puerto:
                        validar_puerto(puerto)
                        salida_if = ejecutar(
                            host, user, password,
                            comandos_escanear_interfaces(puerto))
                        interfaces_up, interfaces_down = parsear_interfaces(salida_if)

                elif accion == "ocupadas":
                    validar_puerto(puerto)
                    salida_run = ejecutar(
                        host, user, password,
                        [f"show running-config interface gpon-olt_{puerto}"])
                    salida_state = ejecutar(
                        host, user, password,
                        [f"show gpon onu state gpon-olt_{puerto}"])
                    salida = mostrar_onus_ocupadas(salida_run, salida_state)

                elif accion in ("eliminar", "eliminar_confirmar"):
                    validar_puerto(puerto)
                    onu_id = f.get("onu_id", "").strip()
                    if not onu_id:
                        raise RuntimeError(
                            "Escribi el ONU-ID que queres eliminar en el campo "
                            "'Numero de ONU' (elegilo de la lista 'Ver ONU-ID "
                            "ocupados').")
                    validar_onu_id(onu_id)
                    cmds = ["configure terminal", f"interface gpon-olt_{puerto}",
                            f"no onu {onu_id}", "exit", "end",
                            f"show running-config interface gpon-olt_{puerto}"]
                    comandos_previos = "\n".join(cmds)
                    if accion == "eliminar_confirmar":
                        confirmado = True
                        salida = ejecutar(host, user, password, cmds)
                    else:
                        confirm_accion = "eliminar_confirmar"

                elif accion in ("provisionar", "provisionar_confirmar"):
                    validar_puerto(puerto)
                    onu_id = f.get("onu_id", "").strip()
                    sn = f.get("sn", "").strip()
                    modelo = f.get("modelo", "").strip()
                    plan = f.get("plan", "").strip()
                    modo = f.get("modo", "router")
                    servicios_extra = f.get("servicios_extra") == "on"
                    validar_onu_id(onu_id)
                    validar_sn(sn)
                    validar_opciones(modelo, plan, modo, modelos_validos)
                    if servicios_extra and modo != "bridge":
                        raise ValueError(
                            "IPTV/VoIP (VLAN 300/400) solo se habilita en modo bridge.")
                    cmds = construir_comandos_alta(
                        puerto=puerto, onu_id=onu_id, modelo=modelo, sn=sn,
                        plan=plan, modo=modo, servicios_extra=servicios_extra,
                    )
                    comandos_previos = "\n".join(cmds)
                    if accion == "provisionar_confirmar":
                        confirmado = True
                        salida = ejecutar(host, user, password, cmds)
                        verif_cmds = [
                            f"show running-config interface gpon-onu_{puerto}:{onu_id}",
                            f"show pon-onu-mng gpon-onu_{puerto}:{onu_id}",
                        ]
                        salida2 = ejecutar(host, user, password, verif_cmds)
                        salida = (salida + "\n\n" + "=" * 40
                                  + " VERIFICACION " + "=" * 40 + "\n" + salida2)
                        verificacion_ok, verificacion_notas = verificar_aplicacion(
                            salida, onu_id, servicios_extra)
                    else:
                        confirm_accion = "provisionar_confirmar"

            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

        return render_template(
            template, f=f, salida=salida, error=error,
            comandos_previos=comandos_previos,
            confirm_accion=confirm_accion, confirmado=confirmado,
            verificacion_ok=verificacion_ok,
            verificacion_notas=verificacion_notas,
            interfaces_up=interfaces_up,
            interfaces_down=interfaces_down,
            modelos=MODELOS_ONU)