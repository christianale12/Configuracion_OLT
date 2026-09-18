#!/usr/bin/env python3
"""
Transporte Telnet para la OLT ZTE ZXAN
=======================================
Conexion por Telnet usando el socket nativo de Python (sin librerias
externas). Expone una sola funcion usada por la interfaz:
    ejecutar_por_telnet(host, usuario, password, comandos)
    -> devuelve toda la salida de la sesion como texto.
"""

import socket
import time

IAC, DONT, DO, WONT, WILL = 255, 254, 253, 252, 251


def _limpiar_iac(sock, datos):
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


def _leer_hasta(sock, marcas, timeout=8):
    sock.settimeout(0.5)
    datos = b""
    fin = time.time() + timeout
    coincide = False
    try:
        while time.time() < fin:
            try:
                fragmento = sock.recv(4096)
            except socket.timeout:
                continue
            if not fragmento:
                break
            datos += fragmento
            texto = _limpiar_iac(sock, datos).decode(errors="ignore")
            if any(m in texto for m in marcas):
                coincide = True
                break
    except OSError:
        pass
    try:
        texto = _limpiar_iac(sock, datos).decode(errors="ignore")
    except OSError:
        texto = datos.decode(errors="ignore")
    return texto, coincide


def ejecutar_por_telnet(host, usuario, password, comandos, espera=0.3, puerto_telnet=23):
    sock = socket.create_connection((host, puerto_telnet), timeout=15)
    salida = []
    try:
        inicial, _ = _leer_hasta(sock, ["Username", "Username:", "Login:", "login:"], timeout=5)
        salida.append(inicial)

        sock.sendall((usuario + "\r\n").encode())
        resp_user, _ = _leer_hasta(sock, ["assword", "assword:"], timeout=5)
        salida.append(resp_user)

        sock.sendall((password + "\r\n").encode())
        resp_pass, _ = _leer_hasta(sock, ["#", ">"], timeout=8)
        salida.append(resp_pass)

        if "%" in resp_pass and (
                "nvalid" in resp_pass or "denied" in resp_pass.lower()
                or "ailed" in resp_pass.lower() or "icorrect" in resp_pass.lower()):
            raise RuntimeError(
                "La OLT rechazo el usuario o la contrasena durante el login por Telnet.")

        for cmd in comandos:
            sock.sendall((cmd + "\r\n").encode())
            if espera:
                time.sleep(espera)
            respuesta, _ = _leer_hasta(sock, ["#", ">"], timeout=10)
            salida.append(f"$ {cmd}\n{respuesta}")
    finally:
        sock.close()
    return "\n".join(salida)