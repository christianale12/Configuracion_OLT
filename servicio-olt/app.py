#!/usr/bin/env python3
"""
App web (Telnet) para aprovisionamiento de ONUs en OLT ZTE ZXAN
================================================================
Interfaz web por Telnet con soporte de sesión activa.
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

# Prioridad a los templates editables (junto al exe / carpeta de desarrollo).
# Si existe "templates" al lado del ejecutable (o en la carpeta del proyecto),
# la app los lee de ahi para que los cambios se vean sin recompilar.
_EXTERNO = os.path.join(os.path.dirname(__file__), "templates")
if not os.path.isdir(_EXTERNO) and getattr(sys, "frozen", False):
    _junto_exe = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "templates")
    _arriba = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))), "templates")
    for _c in (_junto_exe, _arriba):
        if os.path.isdir(_c):
            _EXTERNO = _c
            break
_TEMPL = _EXTERNO if os.path.isdir(_EXTERNO) else os.path.join(_BASE, "templates")

app = Flask(__name__, template_folder=_TEMPL)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Clave secreta necesaria para que Flask mantenga las sesiones de usuario en cookies
app.secret_key = "zxan_olt_telnet_session_key_secret"

# Habilitamos conectar=True para activar los botones de Iniciar y Cerrar sesión
vistas.registrar(
    app,
    ejecutar_por_telnet,
    "index.html",
    conectar=True,
    modelos=True,
    modelos_validos=None,
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)