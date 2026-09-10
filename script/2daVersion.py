import customtkinter as ctk
import threading
import yaml  
from netmiko import ConnectHandler

# Credenciales 
USER_OLT = "cidi"
PASS_OLT = "gpon1234"

class RedApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gestor & Extractor de Red PRO (Exportador YAML)")
        self.geometry("900x820")
        ctk.set_appearance_mode("Light")
        
        self.lbl_title = ctk.CTkLabel(self, text="Gestión de Extracción y Auditoría de Red", font=("Arial", 22, "bold"))
        self.lbl_title.pack(pady=10)

        # ---- FRAME 1: Conexión ----
        self.frame_conn = ctk.CTkFrame(self, fg_color=("#E5E5E5", "#2B2B2B"))
        self.frame_conn.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(self.frame_conn, text="IP OLT ZTE:").grid(row=0, column=0, padx=10, pady=10)
        self.ent_ip_olt = ctk.CTkEntry(self.frame_conn, width=130)
        self.ent_ip_olt.insert(0, "10.0.10.100")
        self.ent_ip_olt.grid(row=0, column=1, padx=10, pady=10)

        ctk.CTkLabel(self.frame_conn, text="IP MikroTik:").grid(row=0, column=2, padx=10, pady=10)
        self.ent_ip_mtk = ctk.CTkEntry(self.frame_conn, width=130)
        self.ent_ip_mtk.insert(0, "192.168.10.1")
        self.ent_ip_mtk.grid(row=0, column=3, padx=10, pady=10)

        ctk.CTkLabel(self.frame_conn, text="Tema Visual:").grid(row=1, column=0, padx=10, pady=10)
        self.cmb_tema = ctk.CTkOptionMenu(self.frame_conn, values=["Light", "Dark"], command=self.cambiar_tema)
        self.cmb_tema.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        # ---- FRAME 2: Interfaces ----
        self.frame_ifaces = ctk.CTkFrame(self, fg_color=("#D9EAD3", "#1e2b22"))
        self.frame_ifaces.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(self.frame_ifaces, text="1. Gestión de Interfaces y VLANs", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(self.frame_ifaces, text="Puerto PON (Ej: 1/13/2):").grid(row=1, column=0, padx=10, pady=5)
        self.ent_pon = ctk.CTkEntry(self.frame_ifaces, width=120)
        self.ent_pon.insert(0, "1/13/2")
        self.ent_pon.grid(row=1, column=1, padx=10, pady=5)
        
        self.btn_up_pon = ctk.CTkButton(self.frame_ifaces, text="Habilitar PON", fg_color="#2E8B57")
        self.btn_up_pon.grid(row=1, column=2, padx=5, pady=5)
        
        self.btn_down_pon = ctk.CTkButton(self.frame_ifaces, text="Apagar PON", fg_color="#C0392B")
        self.btn_down_pon.grid(row=1, column=3, padx=5, pady=5)

        ctk.CTkLabel(self.frame_ifaces, text="ID de VLAN:").grid(row=2, column=0, padx=10, pady=5)
        self.ent_vlan_id = ctk.CTkEntry(self.frame_ifaces, width=120)
        self.ent_vlan_id.insert(0, "200")
        self.ent_vlan_id.grid(row=2, column=1, padx=10, pady=5)

        self.btn_add_vlan = ctk.CTkButton(self.frame_ifaces, text="Agregar VLAN", fg_color="#2E8B57")
        self.btn_add_vlan.grid(row=2, column=2, padx=5, pady=5)

        self.btn_del_vlan = ctk.CTkButton(self.frame_ifaces, text="Quitar VLAN", fg_color="#C0392B")
        self.btn_del_vlan.grid(row=2, column=3, padx=5, pady=5)

        # ---- FRAME 3: ONUs ----
        self.frame_onu = ctk.CTkFrame(self, fg_color=("#CFE2F3", "#1a2430"))
        self.frame_onu.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(self.frame_onu, text="2. Gestión de ONUs", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(self.frame_onu, text="ONU Index:").grid(row=1, column=0, padx=10, pady=5)
        self.ent_onu_idx = ctk.CTkEntry(self.frame_onu, width=150)
        self.ent_onu_idx.insert(0, "gpon-onu_1/13/2:1")
        self.ent_onu_idx.grid(row=1, column=1, padx=10, pady=5)

        self.btn_add_onu = ctk.CTkButton(self.frame_onu, text="Agregar ONU", fg_color="#2E8B57")
        self.btn_add_onu.grid(row=1, column=2, padx=5, pady=5)

        self.btn_del_onu = ctk.CTkButton(self.frame_onu, text="Eliminar ONU", fg_color="#C0392B")
        self.btn_del_onu.grid(row=1, column=3, padx=5, pady=5)

        # ---- BOTÓN DE EXT Y EXP ----
        self.btn_extraer = ctk.CTkButton(self, text="Extraer Configuración y Generar YAML", font=("Arial", 14, "bold"), height=40, command=self.thread_extraccion)
        self.btn_extraer.pack(pady=15)

        # ---- CONSOLA DE SALIDA ----
        self.txt_console = ctk.CTkTextbox(self, width=850, height=200, font=("Consolas", 12))
        self.txt_console.pack(padx=20, pady=10, fill="both", expand=True)
        self.log_to_console("Sistema PRO preparado. Listo para extraer datos y exportar a YAML.")

    def cambiar_tema(self, choice):
        ctk.set_appearance_mode(choice)

    def log_to_console(self, mensaje):
        self.txt_console.configure(state="normal")
        self.txt_console.insert("end", mensaje + "\n")
        self.txt_console.see("end")
        self.txt_console.configure(state="disabled")

    def thread_extraccion(self):
        self.btn_extraer.configure(state="disabled")
        t = threading.Thread(target=self.ejecutar_extraccion_real)
        t.start()

    def ejecutar_extraccion_real(self):
        ip_olt = self.ent_ip_olt.get()
        onu_idx = self.ent_onu_idx.get()
        puerto_pon = self.ent_pon.get()
        
        ip_mtk = self.ent_ip_mtk.get()
        USER_MTK = "admin"
        PASS_MTK = ""

        # Estructura de diccionario 
        datos_maqueta = {
            "maqueta_red": {
                "olt_zte": {"ip_gestion": ip_olt},
                "mikrotik": {"ip_gestion": ip_mtk}
            }
        }

        # 1. CONEXIÓN Y EXT OLT ZTE
        try:
            self.log_to_console(f"\n[+] Conectando a OLT ZTE ({ip_olt})...")
            conn_olt = ConnectHandler(device_type='zte_zxros', host=ip_olt, username=USER_OLT, password=PASS_OLT, port=22, global_delay_factor=2)
            
            estado_onu = conn_olt.send_command(f"show gpon onu state gpon-olt_{puerto_pon}")
            optica_onu = conn_olt.send_command(f"show gpon onu optical-power {onu_idx}")
            vlans_olt = conn_olt.send_command("show vlan")
            
            datos_maqueta["maqueta_red"]["olt_zte"]["estado_onus"] = estado_onu
            datos_maqueta["maqueta_red"]["olt_zte"]["potencia_optica"] = optica_onu
            datos_maqueta["maqueta_red"]["olt_zte"]["vlans_configuradas"] = vlans_olt
            
            conn_olt.disconnect()
            self.log_to_console("[+] Extracción OLT ZTE completada.")
        except Exception as e:
            self.log_to_console(f"[!] Error extrayendo OLT: {str(e)}")
            datos_maqueta["maqueta_red"]["olt_zte"]["error"] = str(e)

        # 2. CONEXIÓN Y EXT MIKROTIK
        try:
            self.log_to_console(f"\n[+] Conectando a MikroTik ({ip_mtk})...")
            conn_mtk = ConnectHandler(device_type='mikrotik_routeros', host=ip_mtk, username=USER_MTK, password=PASS_MTK, port=22)

            # Comandos requeridos por la consigna (IP, Máscara, Gateway, Rutas, VLANs, Filtros/ACL, NAT)
            ifaces = conn_mtk.send_command("/interface print detail")
            ips = conn_mtk.send_command("/ip address print detail")
            rutas = conn_mtk.send_command("/ip route print detail")
            vlans = conn_mtk.send_command("/interface vlan print detail")
            nat = conn_mtk.send_command("/ip firewall nat print detail")
            filtros_acl = conn_mtk.send_command("/ip firewall filter print detail")

            datos_maqueta["maqueta_red"]["mikrotik"]["interfaces"] = ifaces
            datos_maqueta["maqueta_red"]["mikrotik"]["ip_direcciones_mascaras"] = ips
            datos_maqueta["maqueta_red"]["mikrotik"]["rutas_gateway"] = rutas
            datos_maqueta["maqueta_red"]["mikrotik"]["vlans"] = vlans
            datos_maqueta["maqueta_red"]["mikrotik"]["reglas_nat"] = nat
            datos_maqueta["maqueta_red"]["mikrotik"]["filtros_acl"] = filtros_acl

            conn_mtk.disconnect()
            self.log_to_console("[+] Extracción MikroTik completada.")
        except Exception as e:
            self.log_to_console(f"[!] Error extrayendo MikroTik: {str(e)}")
            datos_maqueta["maqueta_red"]["mikrotik"]["error"] = str(e)

        # 3. GENERACIÓNARCHIVO YAML 
        try:
            nombre_archivo = "configuracion_red.yaml"
            with open(nombre_archivo, "w", encoding="utf-8") as file:
                yaml.dump(datos_maqueta, file, default_flow_style=False, allow_unicode=True)
            self.log_to_console(f"\n[✔] ÉXITO: Archivo '{nombre_archivo}' generado correctamente en la carpeta raíz del script.")
        except Exception as e:
            self.log_to_console(f"\n[!] Error al escribir el archivo YAML: {str(e)}")

        self.btn_extraer.configure(state="normal")

if __name__ == "__main__":
    app = RedApp()
    app.mainloop()