#!/usr/bin/env python3
"""
App web para aprovisionamiento de ONUs en OLT ZTE ZXAN (GPON)
================================================================

Corre un servidor web local con un formulario para:
  - Ver ONUs conectadas y sin configurar en un puerto (show gpon onu uncfg)
  - Dar de alta un cliente nuevo (internet solo o triple play, router o bridge)
  - Ver el estado de las ONUs de un puerto (show gpon onu state)

Requiere:
    pip install flask --break-system-packages
    (usa Telnet nativo de Python, no hace falta paramiko)

Para correrla:
    python3 app.py
    (despues abrir http://localhost:5000 en el navegador)

Si la vas a compartir con otros compañeros de la facultad en la misma red,
correla con host="0.0.0.0" (ya configurado abajo) y que ellos entren a
http://<IP-de-tu-PC>:5000

IMPORTANTE: Telnet no cifra nada, ni la contraseña ni los comandos.
Usar solo dentro de una red cerrada y confiable (ej: laboratorio de la
facultad), nunca sobre internet ni redes compartidas con desconocidos.
"""

import socket
import time
from flask import Flask, request, render_template_string

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Logica de armado de comandos (misma que el script de linea de comandos)
# ---------------------------------------------------------------------------
def nombre_traffic_profile(plan):
    sufijo = plan.replace("plan-", "").upper()
    return f"DOWN-{sufijo}"


def construir_comandos_alta(puerto, onu_id, modelo, sn, plan, servicio, modo):
    interfaz_olt = f"gpon-olt_{puerto}"
    interfaz_onu = f"gpon-onu_{puerto}:{onu_id}"
    plan_norm = plan if plan.startswith("plan-") else f"plan-{plan}"
    traffic = nombre_traffic_profile(plan_norm)

    comandos = ["configure terminal", f"interface {interfaz_olt}",
                f"onu {onu_id} type {modelo} sn {sn}", "exit"]

    comandos += [f"interface {interfaz_onu}", "sn-bind enable sn",
                 f"tcont 1 name internet profile {plan_norm}",
                 "gemport 1 name internet tcont 1",
                 f"gemport 1 traffic-limit downstream {traffic}"]

    if servicio == "triple":
        comandos += ["gemport 2 name iptv tcont 1", "gemport 3 name voz tcont 1",
                     "switchport mode hybrid vport 1", "switchport mode hybrid vport 2",
                     "switchport mode hybrid vport 3",
                     "service-port 1 vport 1 user-vlan 200 vlan 200",
                     "service-port 2 vport 2 user-vlan 300 vlan 300",
                     "service-port 3 vport 3 user-vlan 400 vlan 400"]
    else:
        comandos += ["switchport mode hybrid vport 1",
                     "service-port 1 vport 1 user-vlan 200 vlan 200"]

    comandos.append("exit")
    comandos.append(f"pon-onu-mng {interfaz_onu}")

    if servicio == "triple":
        comandos += ["service 1 gemport 1 vlan 200", "service 2 gemport 2 vlan 300",
                     "service 3 gemport 3 vlan 400"]
    else:
        comandos.append("service 1 gemport 1 vlan 200")

    if modo == "router":
        comandos.append("wan-ip 1 mode dhcp vlan-profile HSI-200 host 1")

    comandos.append("vlan port eth_0/1 mode tag vlan 200")
    if servicio == "triple":
        comandos.append("vlan port eth_0/2 mode tag vlan 300")
        comandos.append("vlan port eth_0/3 mode tag vlan 400")

    comandos += ["exit", "end", f"show gpon onu state {interfaz_olt}"]
    return comandos


# ---------------------------------------------------------------------------
# Conexion por Telnet (socket nativo de Python, sin librerias externas)
# ---------------------------------------------------------------------------
IAC, DONT, DO, WONT, WILL = 255, 254, 253, 252, 251


def _limpiar_iac(sock, datos):
    """
    Quita las secuencias de negociacion Telnet (IAC ...) del buffer recibido
    y responde rechazando cualquier opcion que el equipo intente negociar
    (WONT/DONT a todo). Esto evita que la negociacion "ensucie" el texto
    que despues buscamos interpretar (prompts, mensajes de error, etc.).
    """
    limpio = bytearray()
    i = 0
    n = len(datos)
    while i < n:
        b = datos[i]
        if b == IAC and i + 2 < n:
            cmd, opt = datos[i + 1], datos[i + 2]
            if cmd == DO:
                sock.sendall(bytes([IAC, WONT, opt]))
            elif cmd == WILL:
                sock.sendall(bytes([IAC, DONT, opt]))
            i += 3
            continue
        elif b == IAC and i + 1 < n:
            i += 2
            continue
        limpio.append(b)
        i += 1
    return bytes(limpio)


def _leer_telnet(sock, timeout=3):
    sock.settimeout(timeout)
    datos = b""
    try:
        while True:
            fragmento = sock.recv(4096)
            if not fragmento:
                break
            datos += fragmento
    except socket.timeout:
        pass
    except Exception:
        pass
    return _limpiar_iac(sock, datos).decode(errors="ignore")


def ejecutar_por_telnet(host, usuario, password, comandos, espera=1.5, puerto_telnet=23):
    sock = socket.create_connection((host, puerto_telnet), timeout=15)

    salida = []

    # --- Login: la mayoria de los equipos ZTE piden Username: y Password: ---
    inicial = _leer_telnet(sock, timeout=3)
    salida.append(inicial)

    sock.sendall((usuario + "\r\n").encode())
    time.sleep(0.5)
    resp_user = _leer_telnet(sock, timeout=2)
    salida.append(resp_user)

    sock.sendall((password + "\r\n").encode())
    time.sleep(1)
    resp_pass = _leer_telnet(sock, timeout=3)
    salida.append(resp_pass)

    if "%" in resp_pass and ("nvalid" in resp_pass or "denied" in resp_pass.lower()):
        sock.close()
        raise RuntimeError(
            "La OLT rechazo el usuario o la contrasena durante el login por Telnet.")

    # --- Envio de cada comando de la plantilla ---
    for cmd in comandos:
        sock.sendall((cmd + "\r\n").encode())
        time.sleep(espera)
        respuesta = _leer_telnet(sock, timeout=3)
        salida.append(f"$ {cmd}\n{respuesta}")

    sock.close()
    return "\n".join(salida)


# ---------------------------------------------------------------------------
# Plantilla HTML (un solo archivo, sin dependencias externas de CSS/JS)
# ---------------------------------------------------------------------------
PAGINA = """
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Aprovisionamiento ONU - ZXAN</title>
<style>
  body { font-family: -apple-system, Arial, sans-serif; max-width: 900px; margin: 30px auto; padding: 0 15px; color: #1a1a1a; }
  h1 { font-size: 1.4rem; }
  fieldset { border: 1px solid #ccc; border-radius: 8px; padding: 15px 20px; margin-bottom: 20px; }
  legend { font-weight: 600; padding: 0 6px; }
  label { display: block; margin-top: 10px; font-size: 0.9rem; color: #444; }
  input, select { width: 100%; padding: 6px 8px; margin-top: 3px; box-sizing: border-box; border: 1px solid #bbb; border-radius: 4px; }
  .fila { display: flex; gap: 15px; }
  .fila > div { flex: 1; }
  button { margin-top: 15px; padding: 10px 18px; border: none; border-radius: 6px; background: #2563eb; color: white; font-size: 0.95rem; cursor: pointer; }
  button.secundario { background: #6b7280; }
  button:hover { opacity: 0.9; }
  pre { background: #0f172a; color: #d1fae5; padding: 15px; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; font-size: 0.85rem; }
  .aviso { background: #fff7ed; border: 1px solid #fdba74; padding: 10px 15px; border-radius: 6px; font-size: 0.85rem; margin-bottom: 15px; }
</style>
</head>
<body>
<h1>Aprovisionamiento de ONUs - OLT ZTE ZXAN</h1>
<div class="aviso">Conexión por Telnet (sin cifrar) — usar solo dentro de la red del laboratorio/facultad. La contraseña se usa solo para esta conexión y no se guarda en ningún lado.</div>

<form method="post">
  <fieldset>
    <legend>Conexión a la OLT</legend>
    <div class="fila">
      <div>
        <label>IP de gestión</label>
        <input name="host" value="{{ f.host or '10.99.99.2' }}" required>
      </div>
      <div>
        <label>Usuario</label>
        <input name="user" value="{{ f.user or 'cidi' }}" required>
      </div>
      <div>
        <label>Contraseña</label>
        <input type="password" name="password" required>
      </div>
    </div>
  </fieldset>

  <fieldset>
    <legend>Datos del cliente</legend>
    <div class="fila">
      <div>
        <label>Puerto (ej: 1/13/4)</label>
        <input name="puerto" value="{{ f.puerto or '1/13/4' }}" required>
      </div>
      <div>
        <label>Número de ONU</label>
        <input name="onu_id" value="{{ f.onu_id or '' }}" required>
      </div>
      <div>
        <label>Modelo</label>
        <select name="modelo">
          <option {{ 'selected' if f.modelo=='generic-F670' else '' }}>generic-F670</option>
          <option {{ 'selected' if f.modelo=='ZTEG-F670' else '' }}>ZTEG-F670</option>
          <option {{ 'selected' if f.modelo=='ZTEG-F670L' else '' }}>ZTEG-F670L</option>
          <option {{ 'selected' if f.modelo=='generic-F601' else '' }}>generic-F601</option>
        </select>
      </div>
    </div>
    <label>Número de serie (SN, 12 caracteres)</label>
    <input name="sn" value="{{ f.sn or '' }}" required>
    <div class="fila">
      <div>
        <label>Plan</label>
        <select name="plan">
          <option value="100m" {{ 'selected' if f.plan=='100m' else '' }}>100 Mb</option>
          <option value="300m" {{ 'selected' if f.plan=='300m' else '' }}>300 Mb</option>
          <option value="600m" {{ 'selected' if f.plan=='600m' else '' }}>600 Mb</option>
          <option value="1g" {{ 'selected' if f.plan=='1g' else '' }}>1 Gb</option>
        </select>
      </div>
      <div>
        <label>Servicio</label>
        <select name="servicio">
          <option value="internet" {{ 'selected' if f.servicio=='internet' else '' }}>Solo internet</option>
          <option value="triple" {{ 'selected' if f.servicio=='triple' else '' }}>Triple play (internet+iptv+voz)</option>
        </select>
      </div>
      <div>
        <label>Modo</label>
        <select name="modo">
          <option value="router" {{ 'selected' if f.modo=='router' else '' }}>Router</option>
          <option value="bridge" {{ 'selected' if f.modo=='bridge' else '' }}>Bridge</option>
        </select>
      </div>
    </div>
  </fieldset>

  <button type="submit" name="accion" value="uncfg">1. Ver ONUs sin configurar en el puerto</button>
  <button type="submit" name="accion" value="provisionar">2. Dar de alta con estos datos</button>
  <button type="submit" name="accion" value="estado" class="secundario">Ver estado del puerto</button>
</form>

{% if comandos_previos %}
<h3>Comandos que se van a enviar (revisar antes de confirmar)</h3>
<pre>{{ comandos_previos }}</pre>
{% endif %}

{% if salida %}
<h3>Resultado</h3>
<pre>{{ salida }}</pre>
{% endif %}

{% if error %}
<h3 style="color:#b91c1c">Error</h3>
<pre style="background:#450a0a; color:#fecaca">{{ error }}</pre>
{% endif %}

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    f = request.form
    salida = None
    error = None
    comandos_previos = None

    if request.method == "POST":
        host = f.get("host", "").strip()
        user = f.get("user", "").strip()
        password = f.get("password", "")
        puerto = f.get("puerto", "").strip()
        accion = f.get("accion")

        try:
            if accion == "uncfg":
                cmds = [f"show gpon onu uncfg gpon-olt_{puerto}"]
                salida = ejecutar_por_telnet(host, user, password, cmds)

            elif accion == "estado":
                cmds = [f"show gpon onu state gpon-olt_{puerto}"]
                salida = ejecutar_por_telnet(host, user, password, cmds)

            elif accion == "provisionar":
                cmds = construir_comandos_alta(
                    puerto=puerto,
                    onu_id=f.get("onu_id", "").strip(),
                    modelo=f.get("modelo", "").strip(),
                    sn=f.get("sn", "").strip(),
                    plan=f.get("plan", "").strip(),
                    servicio=f.get("servicio", "internet"),
                    modo=f.get("modo", "router"),
                )
                comandos_previos = "\n".join(cmds)
                salida = ejecutar_por_telnet(host, user, password, cmds)

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

    return render_template_string(PAGINA, f=f, salida=salida, error=error,
                                   comandos_previos=comandos_previos)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
