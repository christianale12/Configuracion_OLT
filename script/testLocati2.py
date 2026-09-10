import customtkinter as ctk
import threading
import yaml
from netmiko import ConnectHandler
import psutil
import time
import re
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# =========================================================
# CREDENCIALES Y PUERTOS OBJETIVO
# =========================================================
USER_OLT = "cidi"
PASS_OLT = "gpon1234"
USER_MTK = "admin"
PASS_MTK = ""

# Puertos para escaneo de tráfico
PUERTO_OLT_TRAFICO = "gpon-olt_1/13/1" 
INTERFAZ_MTK_TRAFICO = "ether1"
# =========================================================

class RedApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gestor & Extractor de Red")
        
        # ---------------------------------------------------------
        # TAMAÑO Y CENTRADO EXACTO
        # ---------------------------------------------------------
        window_width = 850 
        window_height = 650
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x_cordinate = int((screen_width / 2) - (window_width / 2))
        y_cordinate = int((screen_height / 2) - (window_height / 2))
        self.geometry(f"{window_width}x{window_height}+{x_cordinate}+{y_cordinate}")
        self.resizable(False, False)
        
        # Variables de estado y datos
        self.vlans_agregadas = []
        self.monitoreo_local_activo = False
        self.escaneo_circuito_activo = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------
        # PANEL LATERAL (SIDEBAR)
        # ---------------------------------------------------------
        self.sidebar_frame = ctk.CTkFrame(self, width=150, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.lbl_title = ctk.CTkLabel(self.sidebar_frame, text="Red", font=("Arial", 18, "bold"))
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_tema = ctk.CTkButton(self.sidebar_frame, text="Estilo Moderno", command=self.toggle_tema)
        self.btn_tema.grid(row=1, column=0, pady=10, padx=10)

        self.btn_abrir_monitor = ctk.CTkButton(self.sidebar_frame, text="Monitor Local", command=self.abrir_ventana_monitor)
        self.btn_abrir_monitor.grid(row=2, column=0, pady=10, padx=10)

        # ---------------------------------------------------------
        # SISTEMA DE PESTAÑAS
        # ---------------------------------------------------------
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=1, padx=10, pady=(5, 0), sticky="nsew")
        
        self.tab_principal = self.tabview.add("Configuración y Provisión")
        self.tab_trafico = self.tabview.add("Tráfico Circuito") 

        self.construir_interfaz(self.tab_principal)
        self.construir_pestaña_trafico(self.tab_trafico)
        
        # ---------------------------------------------------------
        # CONSOLA ÚNICA GLOBAL
        # ---------------------------------------------------------
        self.txt_console = ctk.CTkTextbox(self, height=120)
        self.txt_console.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.txt_console.insert("end", "Sistema inicializado...\n")
        self.txt_console.configure(state="disabled")

        ctk.set_appearance_mode("Light")

    def construir_interfaz(self, parent):
        # --- SECCIÓN IP ---
        frame_conn = ctk.CTkFrame(parent)
        frame_conn.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(frame_conn, text="OLT ZTE:").grid(row=0, column=0, padx=5, pady=5)
        self.cmb_ip_olt = ctk.CTkComboBox(frame_conn, values=["10.0.10.100", "192.168.1.50"], width=130)
        self.cmb_ip_olt.set("") 
        self.cmb_ip_olt.grid(row=0, column=1, padx=5, pady=5)

        ctk.CTkLabel(frame_conn, text="MikroTik:").grid(row=0, column=2, padx=5, pady=5)
        self.cmb_ip_mtk = ctk.CTkComboBox(frame_conn, values=["192.168.10.1", "10.10.10.1"], width=130)
        self.cmb_ip_mtk.set("") 
        self.cmb_ip_mtk.grid(row=0, column=3, padx=5, pady=5)

        # --- SECCIÓN PROVISIÓN DE VLAN ---
        frame_ifaces = ctk.CTkFrame(parent)
        frame_ifaces.pack(fill="x", padx=5, pady=10)
        
        ctk.CTkLabel(frame_ifaces, text="CREACIÓN DE VLAN EN EQUIPOS", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=4, pady=5)

        ctk.CTkLabel(frame_ifaces, text="VLAN ID:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.entry_vlan_id = ctk.CTkEntry(frame_ifaces, placeholder_text="Ej: 300", width=100)
        self.entry_vlan_id.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(frame_ifaces, text="Nombre:").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.entry_vlan_name = ctk.CTkEntry(frame_ifaces, placeholder_text="Ej: iptv", width=130)
        self.entry_vlan_name.grid(row=1, column=3, padx=5, pady=5)

        ctk.CTkLabel(frame_ifaces, text="Uplink OLT:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.cmb_uplink_olt = ctk.CTkComboBox(frame_ifaces, values=["gei_1/19/3", "xgei_1/19/1"], width=100)
        self.cmb_uplink_olt.grid(row=2, column=1, padx=5, pady=5)

        ctk.CTkLabel(frame_ifaces, text="Aplicar a:").grid(row=2, column=2, padx=5, pady=5, sticky="e")
        self.cmb_target = ctk.CTkComboBox(frame_ifaces, values=["OLT ZTE", "MikroTik", "Ambos"], width=130)
        self.cmb_target.grid(row=2, column=3, padx=5, pady=5)

        self.btn_provisionar = ctk.CTkButton(frame_ifaces, text="⚡ Inyectar Configuración", fg_color="#C0392B", hover_color="#922B21", command=self.thread_provisionar_vlan)
        self.btn_provisionar.grid(row=3, column=0, columnspan=4, pady=15)

        # --- SECCIÓN EXTRACCIÓN ---
        self.btn_extraer = ctk.CTkButton(parent, text="Extraer y Generar YAML", height=35, command=self.thread_extraccion)
        self.btn_extraer.pack(pady=10)

        self.ui_elementos = {"frames": [frame_conn, frame_ifaces], "btns": [self.btn_extraer]}

    def construir_pestaña_trafico(self, parent):
        frame_ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        frame_ctrl.pack(fill="x", pady=5)

        self.btn_scan_circuito = ctk.CTkButton(frame_ctrl, text="▶ Comenzar Escaneo de Hardware", command=self.toggle_escaneo_circuito)
        self.btn_scan_circuito.pack(pady=5)

        self.fig_circuito, self.ax_circuito = plt.subplots(figsize=(6, 3.5), dpi=90)
        self.linea_olt, = self.ax_circuito.plot([], [], label=f'Tráfico OLT ({PUERTO_OLT_TRAFICO})', color='orange', marker='o', markersize=3)
        self.linea_mtk, = self.ax_circuito.plot([], [], label=f'Tráfico MTK ({INTERFAZ_MTK_TRAFICO})', color='purple', marker='x', markersize=3)
        self.ax_circuito.set_title("Monitoreo en Tiempo Real (vía SSH)")
        self.ax_circuito.set_ylabel("Métricas Brutas (Bytes/Paquetes)")
        self.ax_circuito.legend()

        self.canvas_circuito = FigureCanvasTkAgg(self.fig_circuito, master=parent)
        self.canvas_circuito.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

        self.historial_olt = []
        self.historial_mtk = []

    def toggle_tema(self):
        if ctk.get_appearance_mode() == "Dark":
            ctk.set_appearance_mode("Light")
            self.btn_tema.configure(text="Modo Moderno")
            color_fondo, color_texto, color_btn = "#D4D0C8", "#000000", "#0055AA"
            modo_actual = "Light"
        else:
            ctk.set_appearance_mode("Dark")
            self.btn_tema.configure(text="Modo Clásico")
            color_fondo, color_texto, color_btn = "#0A0A0A", "#00FF41", "#008F11"
            modo_actual = "Dark"

        for frame in self.ui_elementos["frames"]: 
            frame.configure(fg_color=color_fondo)
        
        for btn in self.ui_elementos["btns"]: 
            btn.configure(fg_color=color_btn, text_color="#FFFFFF" if modo_actual == "Light" else color_texto)
        
        self.sidebar_frame.configure(fg_color=color_fondo)
        self.txt_console.configure(fg_color=color_fondo, text_color=color_texto, font=("Consolas", 11))

    # =========================================================
    # LÓGICA DE APROVISIONAMIENTO SSH
    # =========================================================
    def thread_provisionar_vlan(self):
        vlan_id = self.entry_vlan_id.get().strip()
        vlan_name = self.entry_vlan_name.get().strip()
        uplink_olt = self.cmb_uplink_olt.get()
        target = self.cmb_target.get()
        ip_olt = self.cmb_ip_olt.get()
        ip_mtk = self.cmb_ip_mtk.get()

        if not vlan_id.isdigit():
            self.log_to_console("[!] ERROR: El VLAN ID debe ser numérico.")
            return

        self.btn_provisionar.configure(state="disabled")
        threading.Thread(target=self.ejecutar_provision, args=(vlan_id, vlan_name, uplink_olt, target, ip_olt, ip_mtk), daemon=True).start()

    def ejecutar_provision(self, vlan_id, vlan_name, uplink_olt, target, ip_olt, ip_mtk):
        self.log_to_console(f"[*] Iniciando provisión de VLAN {vlan_id}...")

        # --- APROVISIONAMIENTO EN OLT ZTE ---
        if target in ["OLT ZTE", "Ambos"]:
            if not ip_olt:
                self.log_to_console("[!] ERROR: IP de OLT no seleccionada.")
            else:
                try:
                    self.log_to_console(f"[*] Conectando a OLT ({ip_olt}) para inyectar configuración...")
                    conn_olt = ConnectHandler(device_type='zte_zxros', host=ip_olt, username=USER_OLT, password=PASS_OLT, port=22, timeout=10)
                    
                    # Secuencia de comandos según documentación C300
                    comandos_olt = [
                        "vlan database",
                        f"vlan {vlan_id}",
                        "exit",
                        f"vlan {vlan_id}",
                        f"name {vlan_name}",
                        "exit",
                        f"interface {uplink_olt}",
                        f"switchport vlan {vlan_id} tag",
                        "exit"
                    ]
                    
                    output = conn_olt.send_config_set(comandos_olt)
                    conn_olt.disconnect()
                    
                    self.log_to_console(f"[+] OLT ZTE configurada. VLAN {vlan_id} agregada al puerto {uplink_olt}.")
                    self.vlans_agregadas.append({"id": vlan_id, "equipo": "OLT", "name": vlan_name})
                    
                except Exception as e:
                    self.log_to_console(f"[!] FALLO EN OLT: Error al inyectar comandos. Detalles: {e}")

        # --- APROVISIONAMIENTO EN MIKROTIK ---
        if target in ["MikroTik", "Ambos"]:
            if not ip_mtk:
                self.log_to_console("[!] ERROR: IP de MikroTik no seleccionada.")
            else:
                try:
                    self.log_to_console(f"[*] Conectando a MikroTik ({ip_mtk}) para inyectar configuración...")
                    conn_mtk = ConnectHandler(device_type='mikrotik_routeros', host=ip_mtk, username=USER_MTK, password=PASS_MTK, timeout=10)
                    
                    # Comando de RouterOS para agregar VLAN
                    cmd_mtk = f"/interface vlan add name={vlan_name}_{vlan_id} vlan-id={vlan_id} interface={INTERFAZ_MTK_TRAFICO}"
                    output = conn_mtk.send_command(cmd_mtk)
                    conn_mtk.disconnect()
                    
                    self.log_to_console(f"[+] MikroTik configurado. VLAN {vlan_id} agregada.")
                    self.vlans_agregadas.append({"id": vlan_id, "equipo": "MikroTik", "name": vlan_name})

                except Exception as e:
                    self.log_to_console(f"[!] FALLO EN MIKROTIK: Error al inyectar comandos. Detalles: {e}")

        self.btn_provisionar.configure(state="normal")
        self.log_to_console("[✔] Proceso de provisión finalizado.")

    # =========================================================
    # UTILIDADES DE CONSOLA
    # =========================================================
    def log_to_console(self, mensaje):
        self.txt_console.configure(state="normal")
        self.txt_console.insert("end", mensaje + "\n")
        self.txt_console.see("end")
        self.txt_console.configure(state="disabled")

    # =========================================================
    # (MONITOR Y EXTRACCIÓN)
    # =========================================================
    def abrir_ventana_monitor(self):
        if hasattr(self, 'top_monitor') and self.top_monitor.winfo_exists():
            self.top_monitor.focus()
            return
        self.top_monitor = ctk.CTkToplevel(self)
        self.top_monitor.title("Monitor Local PC")
        self.top_monitor.geometry("450x330")
        self.top_monitor.protocol("WM_DELETE_WINDOW", self.cerrar_ventana_monitor) 
        self.lbl_estado_mon = ctk.CTkLabel(self.top_monitor, text="Sistema en espera. Presiona comenzar.", font=("Arial", 12))
        self.lbl_estado_mon.pack(pady=(10, 5))
        self.btn_iniciar_mon = ctk.CTkButton(self.top_monitor, text="▶ Comenzar Monitoreo", command=self.ejecutar_monitoreo_local)
        self.btn_iniciar_mon.pack(pady=5)
        self.fig_local, self.ax_local = plt.subplots(figsize=(5, 3), dpi=90)
        self.linea_rx_local, = self.ax_local.plot([], [], label='Bajada PC', color='green')
        self.linea_tx_local, = self.ax_local.plot([], [], label='Subida PC', color='blue')
        self.ax_local.legend()
        self.canvas_local = FigureCanvasTkAgg(self.fig_local, master=self.top_monitor)
        self.canvas_local.get_tk_widget().pack(fill="both", expand=True)

    def ejecutar_monitoreo_local(self):
        if not self.monitoreo_local_activo:
            self.monitoreo_local_activo = True
            self.btn_iniciar_mon.configure(text="⏸ Detener Monitoreo", fg_color="#C0392B")
            self.lbl_estado_mon.configure(text="Monitoreando tráfico en tiempo real...")
            self.contadores_locales = psutil.net_io_counters()
            self.tiempo_local = time.time()
            self.hist_rx_local, self.hist_tx_local = [], []
            self.log_to_console("[+] Monitor Local iniciado.")
            self.actualizar_grafico_local()
        else:
            self.monitoreo_local_activo = False
            self.btn_iniciar_mon.configure(text="▶ Comenzar Monitoreo", fg_color=["#3B8ED0", "#1F6AA5"])
            self.lbl_estado_mon.configure(text="Sistema en pausa.")
            self.log_to_console("[-] Monitor Local detenido.")

    def cerrar_ventana_monitor(self):
        self.monitoreo_local_activo = False
        if hasattr(self, 'top_monitor') and self.top_monitor.winfo_exists():
            self.top_monitor.destroy()

    def actualizar_grafico_local(self):
        if not self.monitoreo_local_activo or not self.top_monitor.winfo_exists(): return
        act = psutil.net_io_counters()
        t_act = time.time()
        dt = t_act - self.tiempo_local
        if dt > 0:
            mbps_rx = ((act.bytes_recv - self.contadores_locales.bytes_recv) * 8) / (1000000 * dt)
            mbps_tx = ((act.bytes_sent - self.contadores_locales.bytes_sent) * 8) / (1000000 * dt)
            self.contadores_locales, self.tiempo_local = act, t_act
            self.hist_rx_local.append(mbps_rx)
            self.hist_tx_local.append(mbps_tx)
            if len(self.hist_rx_local) > 30:
                self.hist_rx_local.pop(0)
                self.hist_tx_local.pop(0)
            self.linea_rx_local.set_data(range(len(self.hist_rx_local)), self.hist_rx_local)
            self.linea_tx_local.set_data(range(len(self.hist_tx_local)), self.hist_tx_local)
            self.ax_local.set_xlim(0, 30)
            self.ax_local.set_ylim(0, max(max(self.hist_rx_local + [1]), max(self.hist_tx_local + [1])) * 1.2)
            self.canvas_local.draw_idle()
        self.after(1000, self.actualizar_grafico_local)

    def toggle_escaneo_circuito(self):
        ip_olt = self.cmb_ip_olt.get()
        ip_mtk = self.cmb_ip_mtk.get()
        if not ip_olt or not ip_mtk:
            self.log_to_console("[!] ERROR: Debes seleccionar IPs de OLT y MikroTik para escanear.")
            return
        if not self.escaneo_circuito_activo:
            self.escaneo_circuito_activo = True
            self.btn_scan_circuito.configure(text="⏸ Detener Escaneo Hardware", fg_color="#C0392B")
            self.historial_olt.clear()
            self.historial_mtk.clear()
            self.log_to_console("[*] Iniciando conexión persistente a los equipos...")
            threading.Thread(target=self.hilo_polling_hardware, args=(ip_olt, ip_mtk), daemon=True).start()
            self.actualizar_grafico_circuito()
        else:
            self.escaneo_circuito_activo = False
            self.btn_scan_circuito.configure(text="▶ Comenzar Escaneo de Hardware", fg_color=["#3B8ED0", "#1F6AA5"])
            self.log_to_console("[-] Escaneo de hardware detenido.")

    def hilo_polling_hardware(self, ip_olt, ip_mtk):
        conn_mtk = None
        conn_olt = None
        try:
            conn_mtk = ConnectHandler(device_type='mikrotik_routeros', host=ip_mtk, username=USER_MTK, password=PASS_MTK, timeout=5)
            conn_olt = ConnectHandler(device_type='zte_zxros', host=ip_olt, username=USER_OLT, password=PASS_OLT, port=22, timeout=5)
            while self.escaneo_circuito_activo:
                out_mtk = conn_mtk.send_command(f"/interface print stats-detail where name={INTERFAZ_MTK_TRAFICO}")
                match_mtk = re.search(r'rx-byte=([\d]+)', out_mtk)
                valor_mtk = int(match_mtk.group(1)) if match_mtk else 0

                out_olt = conn_olt.send_command(f"show port statistics {PUERTO_OLT_TRAFICO}")
                match_olt = re.search(r'InBytes\s*:\s*([\d]+)', out_olt)
                valor_olt = int(match_olt.group(1)) if match_olt else 0

                self.historial_mtk.append(valor_mtk)
                self.historial_olt.append(valor_olt)

                if len(self.historial_mtk) > 30:
                    self.historial_mtk.pop(0)
                    self.historial_olt.pop(0)
                time.sleep(2)
        except Exception as e:
            self.escaneo_circuito_activo = False
            self.log_to_console(f"[!] ERROR REAL en el enlace SSH: {e}")
            self.btn_scan_circuito.configure(text="▶ Comenzar Escaneo de Hardware", fg_color=["#3B8ED0", "#1F6AA5"])
        finally:
            if conn_mtk: conn_mtk.disconnect()
            if conn_olt: conn_olt.disconnect()

    def actualizar_grafico_circuito(self):
        if not self.escaneo_circuito_activo: return
        if len(self.historial_mtk) > 0 and len(self.historial_olt) > 0:
            self.linea_mtk.set_data(range(len(self.historial_mtk)), self.historial_mtk)
            self.linea_olt.set_data(range(len(self.historial_olt)), self.historial_olt)
            self.ax_circuito.set_xlim(0, 30)
            max_val = max(max(self.historial_mtk + [1]), max(self.historial_olt + [1]))
            self.ax_circuito.set_ylim(0, max_val * 1.2)
            self.canvas_circuito.draw_idle()
        self.after(1000, self.actualizar_grafico_circuito)

    def thread_extraccion(self):
        self.log_to_console("[*] Iniciando extracción de configuración...")
        threading.Thread(target=self.ejecutar_extraccion).start()

    def ejecutar_extraccion(self):
        ip_olt = self.cmb_ip_olt.get()
        ip_mtk = self.cmb_ip_mtk.get()
        if not ip_olt or not ip_mtk:
            self.log_to_console("[!] Error: Selecciona IPs reales para extraer configuración.")
            return

        datos_maqueta = {
            "maqueta_red": {
                "olt_zte": {"ip_gestion": ip_olt},
                "mikrotik": {"ip_gestion": ip_mtk},
                "historial_vlans_inyectadas": self.vlans_agregadas
            }
        }

        try:
            conn_olt = ConnectHandler(device_type='zte_zxros', host=ip_olt, username=USER_OLT, password=PASS_OLT, port=22, timeout=5)
            vlans_olt = conn_olt.send_command("show vlan")
            datos_maqueta["maqueta_red"]["olt_zte"]["vlans_configuradas"] = vlans_olt
            conn_olt.disconnect()
        except Exception as e:
            datos_maqueta["maqueta_red"]["olt_zte"]["error"] = str(e)
            self.log_to_console(f"[!] Falló extracción OLT. Excepción: {e}")

        try:
            conn_mtk = ConnectHandler(device_type='mikrotik_routeros', host=ip_mtk, username=USER_MTK, password=PASS_MTK, timeout=5)
            ifaces = conn_mtk.send_command("/interface print detail")
            datos_maqueta["maqueta_red"]["mikrotik"]["interfaces"] = ifaces
            conn_mtk.disconnect()
        except Exception as e:
            datos_maqueta["maqueta_red"]["mikrotik"]["error"] = str(e)
            self.log_to_console(f"[!] Falló extracción MikroTik. Excepción: {e}")

        try:
            with open("configuracion_red.yaml", "w", encoding="utf-8") as file:
                yaml.dump(datos_maqueta, file, default_flow_style=False)
            self.log_to_console("[✔] Archivo YAML generado exitosamente con el estado actual.")
        except Exception as e:
            self.log_to_console(f"[!] Error de escritura YAML: {e}")

if __name__ == "__main__":
    app = RedApp()
    app.mainloop()