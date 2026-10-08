#!/usr/bin/env python3
"""
Transporte SSH para la OLT ZTE ZXAN
===================================
Conexion por SSH. La OLT (firmware 2013) solo acepta algoritmos legacy:
  1) Cliente ssh de OpenSSH de Windows (el que SI funciona con esa OLT),
     con la contrasena entregada por un helper SSH_ASKPASS.
     IMPORTANTE: la OLT exige terminal (pty). En CMD funciona porque hay
     consola; desde la app se fuerza con `-tt` y los comandos se envian
     con fin de linea de terminal (CRLF). A lo ultimo se cierra la
     conexion y la sesion de la OLT se libera sola (equivale a cerrar
     PuTTY).
  2) Plink/PuTTY NO soporta los algoritmos de la OLT, asi que queda solo
     como ultimo recurso por si algun dia se habilita algo mas moderno.

Expone una sola funcion usada por la interfaz:
    ejecutar_por_ssh(host, usuario, password, comandos)
"""

import os
import shutil
import subprocess
import tempfile
import threading
import time

# Mismas opciones que las que usas en CMD (ssh.txt)
OPCIONES_LEGACY = [
    "-oKexAlgorithms=+diffie-hellman-group1-sha1",
    "-oHostKeyAlgorithms=+ssh-dss",
    "-oCiphers=+aes128-cbc",
    "-oMACs=+hmac-sha1",
]


def _hay_ejecutable(nombre):
    return shutil.which(nombre) is not None


def _crear_askpass():
    """Helper que le responde la contrasena al pedido de ssh."""
    fd, ruta = tempfile.mkstemp(suffix=".cmd")
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write("@echo off\r\necho %SSH_ASKPASS_PASS%\r\n")
    return ruta


def _leer_stream(proc, acumulador):
    """Vuelca stdout a la lista acumulador hasta que cierre el proceso."""
    try:
        for linea in proc.stdout:
            acumulador.append(linea)
    except (OSError, ValueError):
        pass


def ejecutar_por_ssh_openssh(host, usuario, password, comandos,
                             puerto_ssh=22, espera_arranque=2.0,
                             espera_por_comando=1.2, quieto=3.0,
                             timeout_total=120):
    """Conecta por SSH usando el cliente OpenSSH de Windows con opciones
    legacy y TTY forzado (la OLT vieja no abre el shell sin pty)."""
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError("No se encontro el cliente 'ssh' de OpenSSH.")

    ruta_askpass = _crear_askpass()
    ruta_known = os.path.join(tempfile.gettempdir(), "olt_known_hosts")
    try:
        env = os.environ.copy()
        env["SSH_ASKPASS"] = ruta_askpass
        env["SSH_ASKPASS_PASS"] = password
        env["SSH_ASKPASS_REQUIRE"] = "force"

        cmd = [ssh, "-tt", "-p", str(puerto_ssh)]
        cmd += OPCIONES_LEGACY
        cmd += ["-oStrictHostKeyChecking=accept-new",
                "-oUserKnownHostsFile=" + ruta_known,
                f"{usuario}@{host}"]

        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, env=env,
            encoding="utf-8", errors="replace", bufsize=1)

        lineas = []
        hilo = threading.Thread(target=_leer_stream, args=(proc, lineas),
                                daemon=True)
        hilo.start()

        # Deja que arranque la sesion (banner + login)
        time.sleep(espera_arranque)

        for comando in comandos:
            try:
                proc.stdin.write(comando + "\r\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                break
            time.sleep(espera_por_comando)

        # Espera a que se termine de imprimir (salida quieta)
        ultimo = len(lineas)
        fin = time.time() + timeout_total
        while time.time() < fin:
            time.sleep(0.4)
            if len(lineas) != ultimo:
                ultimo = len(lineas)
                continue
            time.sleep(quieto)
            if len(lineas) == ultimo:
                break
            ultimo = len(lineas)

        # Cierra la conexion (la OLT libera la sesion como con PuTTY cerrado)
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait(timeout=5)

        return "".join(lineas)
    finally:
        try:
            os.unlink(ruta_askpass)
        except OSError:
            pass


def ejecutar_por_plink(host, usuario, password, comandos, puerto_ssh=22):
    """Ultimo recurso: conecta con plink (PuTTY). Ojo: PuTTY NO soporta
    los algoritmos legacy de esta OLT, asi que normalmente fallara."""
    if not _hay_ejecutable("plink"):
        raise RuntimeError("No se encontro 'plink' (instala PuTTY o agregalo al PATH).")
    script = "\n".join(comandos) + "\n"
    with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(script)
        ruta = f.name
    try:
        proc = subprocess.run(
            ["plink", "-ssh", f"{usuario}@{host}", "-P", str(puerto_ssh),
             "-pw", password, "-m", ruta],
            capture_output=True, text=True, timeout=120, input="y\n")
        salida = proc.stdout + proc.stderr
        if proc.returncode != 0:
            raise RuntimeError(
                "plink fallo (rc=%s). Revisa que la OLT tenga el SSH habilitado "
                "y el host key aceptado.\n%s" % (proc.returncode, salida[:500]))
        return salida
    finally:
        try:
            os.unlink(ruta)
        except OSError:
            pass


def ejecutar_por_ssh(host, usuario, password, comandos, espera=0.3, puerto_ssh=22):
    """Transporte SSH: usa el ssh de OpenSSH con TTY forzado (necesario
    porque la OLT vieja no abre el shell sin pty). Plink queda solo como
    ultimo recurso si no existe el cliente OpenSSH.
    """
    if _hay_ejecutable("ssh"):
        return ejecutar_por_ssh_openssh(host, usuario, password, comandos, puerto_ssh)
    return ejecutar_por_plink(host, usuario, password, comandos, puerto_ssh)