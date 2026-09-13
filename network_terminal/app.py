"""Punto de entrada de la aplicación."""

from __future__ import annotations

import logging

from .core.logging_setup import configure_logging


def main() -> int:
    log_file = configure_logging()
    logging.getLogger(__name__).info("log en %s", log_file)

    # Import diferido: solo se carga Tk si realmente se abre la GUI.
    from .ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()
    return 0
