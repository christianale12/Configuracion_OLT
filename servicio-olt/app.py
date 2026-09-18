#!/usr/bin/env python3
"""
App web (Telnet) para aprovisionamiento de ONUs en OLT ZTE ZXAN
================================================================
Interfaz web por Telnet. El codigo esta separado por partes:

  - nucleo.py            -> logica, validaciones y parsers (sin transporte)
  - transporte_telnet.py -> conexion Telnet a la OLT
  - vistas.py            -> rutas/controlador web (compartido)
  - templates/index.html -> interfaz grafica (HTML + Jinja)

Para correrla:
    python app.py
    abrir http://localhost:5000
"""

import os
import sys

from flask import Flask

from transporte_telnet import ejecutar_por_telnet
import vistas

if getattr(sys, "frozen", False):
    _BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE, "templates"))

# Version Telnet: permite actualizar la lista de modelos desde la OLT y
# acepta cualquier modelo seguro (validacion por regex, no por lista fija).
vistas.registrar(
    app,
    ejecutar_por_telnet,
    "index.html",
    modelos=True,
    modelos_validos=None,
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)