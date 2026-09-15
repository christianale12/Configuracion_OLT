"""Ventana de descarga masiva de configuraciones (varios equipos a la vez)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from ..backup.manager import get_desktop_dir
from ..batch.runner import BulkConfig, download_configs, parse_targets
from ..core.validation import default_port_for, validate_port
from ..devices.registry import DEFAULT_DEVICE_TYPE, DEVICE_TYPES

_OUTPUT_LABELS = {
    "running-config (.txt)": "config",
    "YAML estructurado (.yaml)": "yaml",
    "Ambos (.txt + .yaml)": "both",
}

log = logging.getLogger(__name__)


class BulkWindow(tk.Toplevel):
    def __init__(self, master=None, defaults: dict | None = None):
        super().__init__(master)
        d = defaults or {}
        self.title("Descarga masiva de configuraciones")
        self.geometry("840x640")
        self.minsize(720, 560)
        self.transient(master)

        self._running = False
        self._cancel = threading.Event()
        self._dest_dir: Path = get_desktop_dir()
        self._active_dest: Path = self._dest_dir
        self._rows: dict[str, str] = {}
        self._saved_any = False

        self.var_user = tk.StringVar(value=d.get("username", ""))
        self.var_password = tk.StringVar(value=d.get("password", ""))
        self.var_protocol = tk.StringVar(value=d.get("protocol", "ssh"))
        self.var_port = tk.StringVar(
            value=str(d.get("port") or default_port_for(self.var_protocol.get()))
        )
        self.var_devtype = tk.StringVar(value=d.get("device_type", DEFAULT_DEVICE_TYPE))
        self.var_trust = tk.BooleanVar(value=bool(d.get("trust", False)))
        self.var_workers = tk.StringVar(value="5")
        self.var_output = tk.StringVar(value="running-config (.txt)")
        self.var_subfolder = tk.BooleanVar(value=True)
        self.var_progress = tk.StringVar(value="")

        self._build()
        self._refresh_dest_label()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- construcción ----------
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="both", expand=False, padx=10, pady=(10, 4))
        ttk.Label(
            top,
            text="IP / hostname de los equipos (uno por línea, o separados por coma/espacio):",
        ).pack(anchor="w")
        self.txt_ips = scrolledtext.ScrolledText(top, height=8, font=("Consolas", 10))
        self.txt_ips.pack(fill="both", expand=True, pady=(2, 6))

        form = ttk.LabelFrame(self, text="Parámetros (comunes a todos los equipos)")
        form.pack(fill="x", padx=10, pady=4)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Usuario:").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(form, textvariable=self.var_user).grid(
            row=0, column=1, sticky="ew", padx=6, pady=4
        )
        ttk.Label(form, text="Contraseña:").grid(
            row=0, column=2, sticky="e", padx=6, pady=4
        )
        ttk.Entry(form, textvariable=self.var_password, show="•").grid(
            row=0, column=3, sticky="ew", padx=6, pady=4
        )

        ttk.Label(form, text="Protocolo:").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        proto = ttk.Frame(form)
        proto.grid(row=1, column=1, sticky="w", padx=6, pady=4)
        ttk.Radiobutton(
            proto, text="SSH", value="ssh", variable=self.var_protocol,
            command=self._sync_port,
        ).pack(side="left")
        ttk.Radiobutton(
            proto, text="Telnet", value="telnet", variable=self.var_protocol,
            command=self._sync_port,
        ).pack(side="left", padx=(10, 0))

        ttk.Label(form, text="Puerto:").grid(row=1, column=2, sticky="e", padx=6, pady=4)
        ttk.Entry(form, textvariable=self.var_port, width=10).grid(
            row=1, column=3, sticky="w", padx=6, pady=4
        )

        ttk.Label(form, text="Tipo de equipo:").grid(
            row=2, column=0, sticky="e", padx=6, pady=4
        )
        ttk.Combobox(
            form, textvariable=self.var_devtype, values=list(DEVICE_TYPES),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(form, text="Conexiones en paralelo:").grid(
            row=2, column=2, sticky="e", padx=6, pady=4
        )
        ttk.Spinbox(
            form, from_=1, to=20, textvariable=self.var_workers, width=8
        ).grid(row=2, column=3, sticky="w", padx=6, pady=4)

        ttk.Label(form, text="Qué guardar:").grid(
            row=3, column=0, sticky="e", padx=6, pady=4
        )
        ttk.Combobox(
            form, textvariable=self.var_output, values=list(_OUTPUT_LABELS),
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", padx=6, pady=4)

        ttk.Checkbutton(
            form,
            text="Confiar y recordar host key SSH desconocida (TOFU)",
            variable=self.var_trust,
        ).grid(row=4, column=1, columnspan=3, sticky="w", padx=6, pady=(0, 4))

        dest = ttk.Frame(form)
        dest.grid(row=5, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
        ttk.Button(dest, text="Carpeta destino…", command=self._choose_dir).pack(
            side="left"
        )
        ttk.Checkbutton(
            dest, text="Subcarpeta con fecha/hora", variable=self.var_subfolder,
            command=self._refresh_dest_label,
        ).pack(side="left", padx=(8, 0))
        self.lbl_dest = ttk.Label(dest, text="", foreground="#666")
        self.lbl_dest.pack(side="left", padx=(8, 0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10, pady=4)
        self.btn_start = ttk.Button(
            actions, text="Descargar todo", command=self._start
        )
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(
            actions, text="Cancelar", command=self._on_cancel, state="disabled"
        )
        self.btn_cancel.pack(side="left", padx=6)
        self.btn_open = ttk.Button(
            actions, text="Abrir carpeta", command=self._open_dir, state="disabled"
        )
        self.btn_open.pack(side="left")
        ttk.Label(actions, textvariable=self.var_progress).pack(side="right")

        self.pbar = ttk.Progressbar(self, mode="determinate")
        self.pbar.pack(fill="x", padx=10)

        res = ttk.LabelFrame(self, text="Resultados")
        res.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.tree = ttk.Treeview(
            res, columns=("estado", "detalle", "seg"), show="tree headings", height=8
        )
        self.tree.heading("#0", text="IP / host")
        self.tree.heading("estado", text="Estado")
        self.tree.heading("detalle", text="Detalle")
        self.tree.heading("seg", text="Seg")
        self.tree.column("#0", width=180)
        self.tree.column("estado", width=80, anchor="center")
        self.tree.column("detalle", width=440)
        self.tree.column("seg", width=60, anchor="e")
        vsb = ttk.Scrollbar(res, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("ok", foreground="#1a7f37")
        self.tree.tag_configure("err", foreground="#b3261e")
        self.tree.tag_configure("pend", foreground="#666")

    # ---------- helpers ----------
    def _sync_port(self):
        new_default = str(default_port_for(self.var_protocol.get()))
        other = {"22": "23", "23": "22"}.get(new_default, "")
        cur = self.var_port.get().strip()
        if cur == "" or cur == other:
            self.var_port.set(new_default)

    def _choose_dir(self):
        chosen = filedialog.askdirectory(initialdir=str(self._dest_dir), parent=self)
        if chosen:
            self._dest_dir = Path(chosen)
            self._refresh_dest_label()

    def _resolved_dest(self) -> Path:
        if self.var_subfolder.get():
            return self._dest_dir / f"configs_{datetime.now():%Y-%m-%d_%H-%M-%S}"
        return self._dest_dir

    def _refresh_dest_label(self):
        suffix = (
            "  →  configs_AAAA-MM-DD_HH-MM-SS/" if self.var_subfolder.get() else ""
        )
        self.lbl_dest.configure(text=str(self._dest_dir) + suffix)

    def _set_running(self, running: bool):
        self._running = running
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_cancel.configure(state="normal" if running else "disabled")

    # ---------- acción ----------
    def _start(self):
        if self._running:
            return
        valid, invalid = parse_targets(self.txt_ips.get("1.0", "end"))
        if not valid:
            messagebox.showwarning(
                "Descarga masiva",
                "No hay ninguna IP/host válido para procesar.",
                parent=self,
            )
            return
        try:
            port = validate_port(self.var_port.get())
        except ValueError as exc:
            messagebox.showerror("Descarga masiva", str(exc), parent=self)
            return
        try:
            workers = max(1, min(20, int(self.var_workers.get())))
        except (TypeError, ValueError):
            workers = 5

        cfg = BulkConfig(
            username=self.var_user.get(),
            password=self.var_password.get(),
            protocol=self.var_protocol.get(),
            port=port,
            device_type=self.var_devtype.get(),
            trust_new_host_key=bool(self.var_trust.get()),
            max_workers=workers,
            output=_OUTPUT_LABELS.get(self.var_output.get(), "config"),
        )
        dest = self._resolved_dest()
        self._active_dest = dest

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows.clear()
        for host in valid:
            self._rows[host] = self.tree.insert(
                "", "end", text=host, values=("Pendiente", "", ""), tags=("pend",)
            )
        for host in invalid:
            self.tree.insert(
                "", "end", text=host,
                values=("ERROR", "IP/host inválido", ""), tags=("err",),
            )

        self.pbar.configure(maximum=len(valid), value=0)
        self.var_progress.set(f"0 / {len(valid)}")
        self._cancel = threading.Event()
        self._saved_any = False
        self._set_running(True)
        log.info("descarga masiva: iniciada por el usuario (%d equipos)", len(valid))

        def on_result(res):
            self.after(0, lambda: self._row_done(res))

        def on_progress(done, total):
            self.after(0, lambda: self._progress(done, total))

        def worker():
            try:
                results = download_configs(
                    valid, cfg, backup_dir=dest, cancel_event=self._cancel,
                    on_result=on_result, on_progress=on_progress,
                )
            except Exception as exc:  # fallo general: no debe tumbar la ventana
                log.exception("descarga masiva: fallo general")
                self.after(0, lambda: self._finished_error(str(exc)))
                return
            self.after(0, lambda: self._finished(results))

        threading.Thread(target=worker, daemon=True).start()

    def _row_done(self, res):
        iid = self._rows.get(res.host)
        if not iid:
            return
        if res.ok:
            self._saved_any = True
            self.tree.item(
                iid,
                values=(
                    "OK",
                    res.filenames or (res.path.name if res.path else ""),
                    f"{res.duration:.1f}",
                ),
                tags=("ok",),
            )
        else:
            detail = res.error
            if res.detail and res.detail != res.error:
                detail = f"{res.error} ({res.detail})"
            self.tree.item(
                iid, values=("ERROR", detail, f"{res.duration:.1f}"), tags=("err",)
            )
        self.tree.see(iid)

    def _progress(self, done, total):
        self.pbar.configure(value=done)
        self.var_progress.set(f"{done} / {total}")

    def _finished(self, results):
        self._set_running(False)
        ok = sum(1 for r in results if r.ok)
        fail = len(results) - ok
        if self._saved_any:
            self.btn_open.configure(state="normal")
        msg = f"Terminado.\n\nOK: {ok}\nCon error: {fail}"
        if self._saved_any:
            msg += f"\n\nCarpeta:\n{self._active_dest}"
        messagebox.showinfo("Descarga masiva", msg, parent=self)

    def _finished_error(self, detail):
        self._set_running(False)
        messagebox.showerror(
            "Descarga masiva", f"Error general: {detail}", parent=self
        )

    def _on_cancel(self):
        self._cancel.set()
        self.btn_cancel.configure(state="disabled")
        self.var_progress.set(self.var_progress.get() + "  (cancelando…)")

    def _open_dir(self):
        d = self._active_dest
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(d))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(d)], check=False)
            else:
                subprocess.run(["xdg-open", str(d)], check=False)
        except Exception:
            messagebox.showinfo("Carpeta", str(d), parent=self)

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno(
                "Descarga masiva",
                "Hay una descarga en curso. ¿Cerrar de todos modos?",
                parent=self,
            ):
                return
            self._cancel.set()
        self.destroy()
