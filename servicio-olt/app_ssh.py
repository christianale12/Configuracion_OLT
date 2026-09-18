#!/usr/bin/env python3
"""
App web (SSH) para aprovisionamiento de ONUs en OLT ZTE ZXAN
=================================================================
Igual que app.py pero conectandose por SSH en vez de Telnet. El codigo
esta separado por partes:

  - nucleo.py            -> logica, validaciones y parsers (sin transporte)
  - transporte_ssh.py    -> conexion SSH a la OLT (OpenSSH -> plink)
  - vistas.py            -> rutas/controlador web (compartido)
  - templates/index_ssh.html -> interfaz grafica (HTML + Jinja)

La OLT (firmware 2013) solo acepta algoritmos legacy:
  1) Cliente ssh de OpenSSH de Windows (el que SI funciona con esa OLT),
     con la contrasena entregada por SSH_ASKPASS.
  2) Plink/PuTTY NO soporta los algoritmos de la OLT, asi que queda solo
     como ultimo recurso por si algun dia se habilita algo mas moderno.

Para correrla (en otro puerto para no chocar con la version Telnet):
    python app_ssh.py
    abrir http://localhost:5001

Requiere:
    pip install flask --break-system-packages
    y el cliente ssh de OpenSSH de Windows (el mismo que usas en CMD).
"""

import os
import sys

from flask import Flask

from transporte_ssh import ejecutar_por_ssh
import vistas

if getattr(sys, "frozen", False):
    _BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE, "templates"))

# Version SSH: incluye la accion "conectar" (show version). Al igual que la
# version Telnet, actualiza la lista de modelos desde la OLT y acepta
# cualquier modelo seguro (validacion por regex).
vistas.registrar(
    app,
    ejecutar_por_ssh,
    "index_ssh.html",
    conectar=True,
    modelos=True,
    modelos_validos=None,
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)