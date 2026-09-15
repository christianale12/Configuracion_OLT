"""Ventana principal (Tkinter). Solo presentación: delega todo en las capas
connection / devices / backup.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from ..backup.manager import BackupManager
from ..connection.manager import ConnectionManager, ConnectionParams
from ..core.errors import TerminalError
from ..core.validation import default_port_for, validate_host, validate_port
from ..devices.facts import collect_device_facts
from ..devices.registry import DEFAULT_DEVICE_TYPE, DEVICE_TYPES, create_device

log = logging.getLogger(__name__)


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Network Device Terminal")
        self.geometry("880x640")
        self.minsize(720, 540)

        self.manager = ConnectionManager()
        self._last_config = ""
        self._connecting = False

        self._build_form()
        self._build_terminal()
        self._build_statusbar()
        self._sync_port_with_protocol(force=True)
        self._update_controls()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(60, self._pump)
        log.info("aplicación iniciada")

    # ---------- construcción ----------
    def _build_form(self):
        frm = ttk.LabelFrame(self, text="Conexión")
        frm.pack(fill="x", padx=10, pady=(10, 6))
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(3, weight=1)

        self.var_host = tk.StringVar()
        self.var_user = tk.StringVar()
        self.var_password = tk.StringVar()
        self.var_protocol = tk.StringVar(value="ssh")
        self.var_port = tk.StringVar()
        self.var_devtype = tk.StringVar(value=DEFAULT_DEVICE_TYPE)
        self.var_trust = tk.BooleanVar(value=False)

        ttk.Label(frm, text="IP / Host:").grid(row=0, column=0, sticky="e", padx=6, pady=5)
        ttk.Entry(frm, textvariable=self.var_host).grid(
            row=0, column=1, sticky="ew", padx=6, pady=5
        )
        ttk.Label(frm, text="Usuario:").grid(row=0, column=2, sticky="e", padx=6, pady=5)
        ttk.Entry(frm, textvariable=self.var_user).grid(
            row=0, column=3, sticky="ew", padx=6, pady=5
        )

        ttk.Label(frm, text="Contraseña:").grid(row=1, column=0, sticky="e", padx=6, pady=5)
        ttk.Entry(frm, textvariable=self.var_password, show="•").grid(
            row=1, column=1, sticky="ew", padx=6, pady=5
        )
        ttk.Label(frm, text="Tipo de equipo:").grid(
            row=1, column=2, sticky="e", padx=6, pady=5
        )
        ttk.Combobox(
            frm,
            textvariable=self.var_devtype,
            values=list(DEVICE_TYPES),
            state="readonly",
        ).grid(row=1, column=3, sticky="ew", padx=6, pady=5)

        ttk.Label(frm, text="Protocolo:").grid(row=2, column=0, sticky="e", padx=6, pady=5)
        proto = ttk.Frame(frm)
        proto.grid(row=2, column=1, sticky="w", padx=6, pady=5)
        ttk.Radiobutton(
            proto, text="SSH", value="ssh", variable=self.var_protocol,
            command=self._sync_port_with_protocol,
        ).pack(side="left")
        ttk.Radiobutton(
            proto, text="Telnet", value="telnet", variable=self.var_protocol,
            command=self._sync_port_with_protocol,
        ).pack(side="left", padx=(10, 0))

        ttk.Label(frm, text="Puerto:").grid(row=2, column=2, sticky="e", padx=6, pady=5)
        ttk.Entry(frm, textvariable=self.var_port, width=10).grid(
            row=2, column=3, sticky="w", padx=6, pady=5
        )

        self.chk_trust = ttk.Checkbutton(
            frm,
            text="Confiar y recordar host key SSH desconocida (TOFU)",
            variable=self.var_trust,
        )
        self.chk_trust.grid(row=3, column=1, columnspan=3, sticky="w", padx=6, pady=(0, 4))

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=4, sticky="ew", padx=6, pady=6)
        self.btn_connect = ttk.Button(btns, text="CONECTAR", command=self._on_connect)
        self.btn_connect.pack(side="left")
        self.btn_disconnect = ttk.Button(
            btns, text="Desconectar", command=self._on_disconnect
        )
        self.btn_disconnect.pack(side="left", padx=6)
        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(
            btns, text="Descarga masiva…", command=self._open_bulk
        ).pack(side="left")

    def _build_terminal(self):
        frm = ttk.LabelFrame(self, text="Terminal")
        frm.pack(fill="both", expand=True, padx=10, pady=6)

        self.txt = scrolledtext.ScrolledText(
            frm,
            wrap="char",
            height=18,
            font=("Consolas", 10),
            background="#101418",
            foreground="#d6dee7",
            insertbackground="#d6dee7",
        )
        self.txt.pack(fill="both", expand=True, padx=6, pady=6)
        self.txt.configure(state="disabled")

        self._menu = tk.Menu(self.txt, tearoff=0)
        self._menu.add_command(label="Copiar", command=self._copy_selection)
        self._menu.add_command(label="Seleccionar todo", command=self._select_all)
        self._menu.add_separator()
        self._menu.add_command(label="Limpiar terminal", command=self._clear_terminal)
        self.txt.bind("<Button-3>", self._show_menu)

        row = ttk.Frame(frm)
        row.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(row, text=">").pack(side="left")
        self.var_cmd = tk.StringVar()
        self.ent_cmd = ttk.Entry(row, textvariable=self.var_cmd)
        self.ent_cmd.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.ent_cmd.bind("<Return>", self._on_send_command)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        self.btn_getcfg = ttk.Button(
            btns, text="Obtener configuración", command=self._on_get_config
        )
        self.btn_getcfg.pack(side="left")
        self.btn_savecfg = ttk.Button(
            btns, text="Guardar configuración", command=self._on_save_config
        )
        self.btn_savecfg.pack(side="left", padx=6)
        self.btn_yaml = ttk.Button(
            btns, text="Extraer a YAML", command=self._on_extract_yaml
        )
        self.btn_yaml.pack(side="left")
        ttk.Button(btns, text="Limpiar", command=self._clear_terminal).pack(
            side="left", padx=6
        )

    def _build_statusbar(self):
        self.var_status = tk.StringVar(value="Desconectado")
        bar = ttk.Frame(self)
        bar.pack(fill="x", side="bottom")
        ttk.Label(
            bar, textvariable=self.var_status, anchor="w", relief="sunken", padding=(6, 3)
        ).pack(fill="x")

    # ---------- helpers ----------
    def _append(self, text: str):
        if not text:
            return
        self.txt.configure(state="normal")
        self.txt.insert("end", text)
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _sync_port_with_protocol(self, *_evt, force: bool = False):
        new_default = str(default_port_for(self.var_protocol.get()))
        other_default = {"22": "23", "23": "22"}.get(new_default, "")
        current = self.var_port.get().strip()
        if force or current == "" or current == other_default:
            self.var_port.set(new_default)

    def _update_controls(self):
        connected = self.manager.is_connected()
        self.btn_connect.configure(
            state="disabled" if connected or self._connecting else "normal"
        )
        self.btn_disconnect.configure(state="normal" if connected else "disabled")
        self.ent_cmd.configure(state="normal" if connected else "disabled")
        self.btn_getcfg.configure(
            state="normal" if connected and not self._connecting else "disabled"
        )
        self.btn_yaml.configure(
            state="normal" if connected and not self._connecting else "disabled"
        )
        self.btn_savecfg.configure(state="normal" if self._last_config else "disabled")

    def _pump(self):
        try:
            self._append(self.manager.poll_output())
        finally:
            self.after(60, self._pump)

    # ---------- acciones ----------
    def _on_connect(self):
        if self._connecting:
            return
        try:
            host = validate_host(self.var_host.get())
            port = validate_port(self.var_port.get())
        except TerminalError as exc:
            messagebox.showerror("Datos inválidos", exc.user_message)
            return
        except ValueError as exc:
            messagebox.showerror("Datos inválidos", str(exc))
            return

        params = ConnectionParams(
            host=host,
            port=port,
            protocol=self.var_protocol.get(),
            username=self.var_user.get(),
            password=self.var_password.get(),
            trust_new_host_key=bool(self.var_trust.get()),
        )
        self._connecting = True
        self.var_status.set(f"Conectando a {host}:{port} ({params.protocol})…")
        self._append(f"\r\n[conectando a {host}:{port} vía {params.protocol}]\r\n")
        self._update_controls()
        self.manager.connect_async(
            params,
            on_success=lambda: self.after(0, self._on_connect_ok),
            on_error=lambda exc: self.after(0, lambda: self._on_connect_err(exc)),
        )

    def _on_connect_ok(self):
        self._connecting = False
        self.var_status.set(f"Conectado ({self.var_protocol.get()})")
        self._append("[conectado]\r\n")
        self._update_controls()
        self.ent_cmd.focus_set()

    def _on_connect_err(self, exc: TerminalError):
        self._connecting = False
        self.var_status.set(f"Error: {exc.user_message}")
        self._append(f"[error] {exc.user_message}\r\n")
        messagebox.showerror("No se pudo conectar", exc.user_message)
        self._update_controls()

    def _on_disconnect(self):
        self.manager.disconnect()
        self.var_status.set("Desconectado")
        self._append("\r\n[desconectado]\r\n")
        self._update_controls()

    def _open_bulk(self):
        from .bulk_window import BulkWindow

        BulkWindow(
            self,
            {
                "username": self.var_user.get(),
                "password": self.var_password.get(),
                "protocol": self.var_protocol.get(),
                "port": self.var_port.get(),
                "device_type": self.var_devtype.get(),
                "trust": bool(self.var_trust.get()),
            },
        )

    def _on_send_command(self, _evt=None):
        if not self.manager.is_connected():
            return
        line = self.var_cmd.get()
        self.var_cmd.set("")
        try:
            self.manager.send_line(line)
        except TerminalError as exc:
            self._append(f"[error] {exc.user_message}\r\n")

    def _on_get_config(self):
        if not self.manager.is_connected():
            return
        device = create_device(self.var_devtype.get(), None)
        self.btn_getcfg.configure(state="disabled")
        self.var_status.set("Obteniendo configuración…")
        self._append(
            f"\r\n[obteniendo configuración: {device.running_config_command()}]\r\n"
        )

        def worker():
            try:
                cfg = self.manager.capture_config(device)
            except TerminalError as exc:
                self.after(0, lambda: self._get_config_err(exc))
                return
            except Exception as exc:
                log.exception("obtener configuración: error inesperado")
                self.after(
                    0,
                    lambda: self._get_config_err(
                        TerminalError(
                            str(exc),
                            user_message="No se pudo obtener la configuración.",
                        )
                    ),
                )
                return
            self.after(0, lambda: self._get_config_ok(cfg))

        threading.Thread(target=worker, daemon=True).start()

    def _get_config_ok(self, cfg: str):
        self._last_config = cfg
        self._append(cfg if cfg.endswith("\n") else cfg + "\r\n")
        self._append("[configuración recibida]\r\n")
        self.var_status.set(f"Configuración obtenida ({len(cfg)} caracteres)")
        self._update_controls()

    def _get_config_err(self, exc: TerminalError):
        self.var_status.set(f"Error: {exc.user_message}")
        self._append(f"[error] {exc.user_message}\r\n")
        messagebox.showerror("Obtener configuración", exc.user_message)
        self._update_controls()

    def _on_extract_yaml(self):
        if not self.manager.is_connected():
            return
        device = create_device(self.var_devtype.get(), None)
        host = self.var_host.get().strip() or "device"
        proto = self.var_protocol.get()
        self.btn_yaml.configure(state="disabled")
        self.var_status.set("Extrayendo información estructurada…")
        self._append("\r\n[extrayendo información estructurada a YAML…]\r\n")

        def worker():
            try:
                facts = collect_device_facts(
                    device,
                    lambda c: self.manager.run_capture(c),
                    host=host,
                    protocol=proto,
                )
                path = BackupManager().save_yaml(facts, host)
            except TerminalError as exc:
                self.after(0, lambda: self._yaml_err(exc))
                return
            except Exception as exc:
                log.exception("extraer YAML: error inesperado")
                self.after(
                    0,
                    lambda: self._yaml_err(
                        TerminalError(
                            str(exc),
                            user_message="No se pudo extraer la información.",
                        )
                    ),
                )
                return
            self.after(0, lambda: self._yaml_ok(facts, path))

        threading.Thread(target=worker, daemon=True).start()

    def _yaml_ok(self, facts: dict, path):
        sections = [k for k in facts if k not in ("device", "raw", "errors")]
        self._append(f"[YAML guardado en {path}]\r\n")
        self._append(f"  secciones: {', '.join(sections) or '(ninguna)'}\r\n")
        if facts.get("errors"):
            self._append(
                f"  avisos en: {', '.join(facts['errors'])}\r\n"
            )
        self.var_status.set(f"YAML guardado: {path}")
        self._update_controls()
        messagebox.showinfo("Extraer a YAML", f"Se guardó en:\n{path}")

    def _yaml_err(self, exc: TerminalError):
        self.var_status.set(f"Error: {exc.user_message}")
        self._append(f"[error] {exc.user_message}\r\n")
        self._update_controls()
        messagebox.showerror("Extraer a YAML", exc.user_message)

    def _on_save_config(self):
        if not self._last_config:
            messagebox.showinfo(
                "Guardar configuración",
                "Primero obtené la configuración con 'Obtener configuración'.",
            )
            return
        host = self.var_host.get().strip() or "device"
        try:
            path = BackupManager().save_config(self._last_config, host)
        except (ValueError, OSError) as exc:
            log.warning("guardar backup falló: %s", exc)
            messagebox.showerror("Guardar configuración", str(exc))
            return
        self.var_status.set(f"Backup guardado: {path}")
        self._append(f"[backup guardado en {path}]\r\n")
        messagebox.showinfo("Backup guardado", f"Se guardó en:\n{path}")

    # ---------- menú contextual ----------
    def _show_menu(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _copy_selection(self):
        try:
            sel = self.txt.get("sel.first", "sel.last")
        except tk.TclError:
            return
        self.clipboard_clear()
        self.clipboard_append(sel)

    def _select_all(self):
        self.txt.tag_add("sel", "1.0", "end")

    def _clear_terminal(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def _on_close(self):
        try:
            self.manager.disconnect()
        finally:
            self.destroy()
