#!/usr/bin/env python3
"""
App de escritorio para aprovisionamiento de ONUs en OLT ZTE ZXAN.
============================================================================

Abre la interfaz de la app (la misma pagina web) en una VENTANA NATIVA de
Windows usando WebView2 (via pywebview), sin necesidad de abrir el navegador.

Uso:
    python app_desktop.py            -> usa el transporte Telnet (app.py)
    python app_desktop.py ssh        -> usa el transporte SSH (app_ssh.py)

Requiere:
    pip install pywebview flask
    (WebView2 viene instalado en Windows 10/11 por defecto)
"""

import socket
import sys
import threading
import time

import webview

# Elegir la version de la app segun el argumento (Telnet por defecto)
USAR_SSH = any(arg.lower() in ("ssh", "--ssh") for arg in sys.argv[1:])
if USAR_SSH:
    import app_ssh as core
    TITULO = "Aprovisionamiento ONU - ZXAN (SSH)"
else:
    import app as core
    TITULO = "Aprovisionamiento ONU - ZXAN (Telnet)"


def puerto_libre():
    """Pide al sistema un puerto TCP libre en localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar_servidor(host, puerto, timeout=15):
    """Espera a que el servidor Flask empiece a aceptar conexiones."""
    limite = time.time() + timeout
    while time.time() < limite:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex((host, puerto)) == 0:
                return True
        time.sleep(0.1)
    return False


def main():
    puerto = puerto_libre()
    host = "127.0.0.1"

    servidor = threading.Thread(
        target=lambda: core.app.run(host=host, port=puerto,
                                    debug=False, use_reloader=False),
        daemon=True,
    )
    servidor.start()

    if not esperar_servidor(host, puerto):
        print("No se pudo iniciar el servidor interno.", file=sys.stderr)
        sys.exit(1)

    webview.create_window(
        TITULO,
        f"http://{host}:{puerto}",
        width=1000,
        height=850,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()