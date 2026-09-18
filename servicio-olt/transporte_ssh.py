#!/usr/bin/env python3
"""
Transporte SSH para la OLT ZTE ZXAN
===================================
Conexion por SSH. La OLT (firmware 2013) solo acepta algoritmos legacy:
  1) Cliente ssh de OpenSSH de Windows (el que SI funciona con esa OLT),
     con la contrasena entregada por un helper SSH_ASKPASS.
     Si no hay consola (GUI), OpenSSH usa SSH_ASKPASS_REQUIRE.
  2) Plink/PuTTY NO soporta los algoritmos de la OLT, así que queda solo
     como ultimo recurso por si algun dia se habilita algo mas moderno.

Expone una sola funcion usada por la interfaz:
    ejecutar_por_ssh(host, usuario, password, comandos)
"""

import os
import shutil
import subprocess
import tempfile

# Mismas opciones que las que usas en CMD (ssh.txt)
OPCIONES_LEGACY = [
    "-oKexAlgorithms=+diffie-hellman-group1-sha1",
    "-oHostKeyAlgorithms=+ssh-dss",
    "-oCiphers=+aes128-cbc",
    "-oMACs=+hmac-sha1",
]


def _hay_ejecutable(nombre):
    return shutil.which(nombre) is not None


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


def ejecutar_por_ssh_openssh(host, usuario, password, comandos, puerto_ssh=22):
    """Conecta por SSH usando el cliente OpenSSH de Windows con opciones
    legacy y la contrasena entregada por un helper SSH_ASKPASS."""
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError("No se encontro el cliente 'ssh' de OpenSSH.")
    script = "\n".join(comandos) + "\n"

    # Helper que "contesta" la contrasena al pedido de ssh (SSH_ASKPASS)
    with tempfile.NamedTemporaryFile(
            "w", suffix=".cmd", delete=False, encoding="utf-8") as f:
        f.write("@echo off\r\necho %SSH_ASKPASS_PASS%\r\n")
        ruta_askpass = f.name
    try:
        env = os.environ.copy()
        env["SSH_ASKPASS"] = ruta_askpass
        env["SSH_ASKPASS_PASS"] = password
        env["SSH_ASKPASS_REQUIRE"] = "force"

        cmd = [ssh, "-T", "-p", str(puerto_ssh)]
        cmd += OPCIONES_LEGACY
        cmd += ["-oStrictHostKeyChecking=accept-new",
                "-oUserKnownHostsFile=" + os.path.join(tempfile.gettempdir(), "olt_known_hosts"),
                f"{usuario}@{host}"]
        proc = subprocess.run(cmd, input=script, capture_output=True,
                              text=True, timeout=180, env=env)
        salida = proc.stdout + proc.stderr
        if proc.returncode != 0:
            raise RuntimeError(
                "ssh de OpenSSH fallo (rc=%s).\n%s" % (proc.returncode, salida[:500]))
        return salida
    finally:
        try:
            os.unlink(ruta_askpass)
        except OSError:
            pass


def ejecutar_por_ssh(host, usuario, password, comandos, espera=0.3, puerto_ssh=22):
    """Transporte SSH: usa el ssh de OpenSSH (el que si funciona con la OLT).

    Plink/PuTTY no soporta los algoritmos legacy de la OLT, asi que solo se
    usa como ultimo recurso si no existe el cliente OpenSSH.
    """
    if _hay_ejecutable("ssh"):
        return ejecutar_por_ssh_openssh(host, usuario, password, comandos, puerto_ssh)
    return ejecutar_por_plink(host, usuario, password, comandos, puerto_ssh)