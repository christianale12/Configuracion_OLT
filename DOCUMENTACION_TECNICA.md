# NETWORK ADMIN (`network_terminal`) — Documentación técnica del proyecto

> Aplicación de escritorio para administrar routers MikroTik y una OLT GPON ZTE ZXA10 C300:
> terminal remota, descarga de configuraciones (individual y en lote) y aprovisionamiento de ONU.

**Versión documentada:** `0.1.0` (`network_terminal/__init__.py`) — estado del código al 2026-10-05.
**Suite de pruebas:** 197 tests unitarios (`unittest`), todos pasando; no se conectan a equipos reales.

---

> **Correcciones aplicadas tras detectar hallazgos al redactar este documento (2026-10-05):** enmascarado de `password <valor>` en el log (con pruebas), `PyYAML` agregado a `requirements.txt` y `README.md` reescrito. El resto de los riesgos y limitaciones descritos sigue vigente.

## Cómo leer este documento

**Convenciones de estado.** Cada capacidad se marca con una de estas etiquetas:

| Etiqueta | Significado |
|---|---|
| **IMPLEMENTADO** | Existe en el código, está conectado a la interfaz y tiene (o no) pruebas, según se indique. |
| **IMPLEMENTACIÓN PARCIAL** | Existe pero con huecos concretos (se detallan). |
| **NO IMPLEMENTADO ACTUALMENTE** | No existe en el código, aunque pueda haber existido antes o sea razonable esperarlo. |
| **MEJORA FUTURA / PROPUESTA** | Idea del autor de este documento; no es una funcionalidad existente. |

**Fuentes de evidencia utilizadas** (y sus límites):

1. **El código actual** de `network_terminal/` (fuente principal de todo lo que se afirma sobre el funcionamiento).
2. **Comentarios y docstrings** del código, que registran el motivo de varias decisiones (muchos citan comportamientos "confirmados contra un equipo real").
3. **El prototipo original** `red3.py.txt` (+ `red3.exe`), en la carpeta padre del paquete.
4. **El `README.md` del paquete**, reescrito el 2026-10-05 para reflejar el estado actual (la versión anterior describía etapas ya eliminadas; ver §16).
5. **La sesión de desarrollo asistida** en la que se construyó y depuró el sistema (los problemas de las secciones 15 y 16 se reconstruyen de ahí y de los comentarios del código).
6. **No existe historial Git** (la carpeta no es un repositorio). Por eso la línea de tiempo de la §16 es una reconstrucción con evidencia indirecta y se advierte donde no hay certeza.

**Alcance de las verificaciones en equipos reales.** El código registra, en comentarios, comportamientos confirmados contra una OLT ZTE real (prompt `ZXAN#`, errores `%Error 20200/20203`, host key DSA, secuencia de activación de Internet) y contra un MikroTik real (RouterOS 6.49.7, comportamiento del banner y del eco de consola). La ruta `/export file=` + SFTP **no fue probada contra un MikroTik real**; solo con conexiones simuladas.

---

## 1. Portada / identificación del proyecto

| Campo | Valor |
|---|---|
| **Nombre** | `network_terminal` (paquete Python). Títulos de ventana: «NETWORK ADMIN» (principal), «NETOPS — TERMINAL», «NETOPS — OLT PROVISIONING». |
| **Descripción breve** | Cliente gráfico de administración de equipos de red por línea de comandos (SSH/Telnet) con automatización de descarga de configuraciones y aprovisionamiento GPON. |
| **Objetivo principal** | Reemplazar el trabajo manual y repetitivo sobre routers MikroTik y una OLT ZTE (conectarse, extraer configuración, dar de alta ONU/servicio) por flujos guiados, repetibles y con trazabilidad. |
| **Tipo de aplicación** | Aplicación de escritorio, monolítica, de ejecución local (Tkinter/ttk). Sin servidor, sin base de datos, sin red propia de gestión: el operador la ejecuta en su PC. |
| **Tecnologías principales** | Python 3 (declarado 3.11+; ejecutada en 3.13), Tkinter/ttk, `paramiko` (SSH/SFTP), `pywinpty` (consola virtual, solo Windows), `PyYAML` (exportación), `threading`/`concurrent.futures`, `unittest`. Cliente Telnet propio sobre `socket`. |
| **Protocolos de red** | **SSH-2** (puerto 22 por defecto), **Telnet** (puerto 23), **SFTP** (subsistema de SSH; solo MikroTik). Para la OLT con firmware viejo: SSH con algoritmos heredados (`diffie-hellman-group1-sha1`, `ssh-dss`, `aes128-cbc`, `hmac-sha1`) mediante el `ssh.exe` del sistema. |
| **Dispositivos que administra** | **MikroTik RouterOS** (`MikroTikDevice`), **ZTE ZXA10 C300 OLT** (`ZteOltDevice`) y equipos CLI en general con `GenericDevice` (solo backup por texto). |
| **Estado actual** | Funcional, versión 0.1.0. Verificado en equipos reales para los flujos de la OLT y la captura de configuración de MikroTik por terminal; partes secundarias son parciales (ver §4). |

### Resumen ejecutivo

Un proveedor de Internet que opera routers MikroTik y una OLT GPON repite constantemente las mismas tareas sobre la consola de cada equipo: abrir una sesión, deshabilitar la paginación, volcar la configuración, copiarla a un archivo con un nombre que permita ubicarla después, y —en la OLT— ejecutar secuencias largas y ordenadas de comandos para dar de alta cada abonado. Hecho a mano, es lento, depende de la memoria del técnico y admite errores silenciosos: un VLAN equivocado, un identificador ya usado por otro cliente, o simplemente un comando de configuración tipeado en el modo equivocado.

`network_terminal` encapsula ese conocimiento en software. Ofrece una **terminal interactiva** (SSH o Telnet) y, sobre ella, acciones de un clic: **obtener la configuración, guardarla** en una estructura de carpetas `Backups/<Categoría>/<Fabricante>/<host>/`, y **extraerla a YAML** estructurado. Para varios equipos a la vez, una **descarga en lote** con concurrencia acotada aísla las fallas de cada host. Para la OLT ZTE incorpora un asistente de **aprovisionamiento**: descubrir puertos PON, listar ONU, autenticarlas por número de serie, crear perfiles y **activar el servicio de Internet** (modo router o bridge) con la secuencia de comandos que fue verificada contra el equipo real, mostrando al final lo que quedó aplicado.

La solución se apoya en una arquitectura por capas (interfaz → lógica → driver por fabricante → conexión) que mantiene el conocimiento específico de cada marca (comandos, prompts, particularidades de la consola) aislado en una clase por fabricante. Su diseño prioriza la robustez frente a consolas reales: detección del fin de comando por reconocimiento del prompt, limpieza del eco de la consola, vaciado del canal antes de cada comando y respaldo automático cuando una vía alternativa (exportación por archivo) falla.

---

## 2. Problema que motivó el proyecto

### 2.1 Problema operativo

Administrar equipos de red por CLI es, en la práctica, una secuencia de pasos mecánicos repetidos por cada equipo. La aplicación apunta a tres tareas concretas que se ven reflejadas en el código:

1. **Respaldar configuraciones** (running-config) de routers y OLT.
2. **Auditar/extraer estado** de forma estructurada (interfaces, IP, rutas, VLAN, firewall/NAT en MikroTik; interfaces IP, rutas y estado de ONU en la OLT).
3. **Dar de alta abonados en una OLT GPON** (autenticar la ONU y configurar el servicio).

El prototipo original (`red3.py.txt`) muestra el origen del problema: una única ventana que, con IP y credenciales fijas, se conectaba a una OLT y a un MikroTik y volcaba un par de comandos a un YAML. Los botones de gestión de PON/VLAN/ONU del prototipo **no tenían acción asociada** (no hay `command=` en ellos): la gestión era una intención, la extracción era lo único operativo.

### 2.2 Cómo se haría sin la aplicación

| Tarea | Procedimiento manual |
|---|---|
| Backup de un MikroTik | Abrir un cliente SSH/Telnet, autenticarse, ejecutar `/export`, seleccionar y copiar el texto de la terminal (que además puede traer el banner de login y el eco del comando), pegarlo en un archivo y nombrarlo a mano. |
| Backup de un lote de equipos | Repetir lo anterior N veces, sin estructura de carpetas común ni registro de cuáles fallaron. |
| Backup/estado de la OLT | Idem, recordando antes `terminal length 0` para evitar la paginación (`--More--`), que si se omite deja la sesión trabada a mitad del pager. |
| Alta de un abonado en la OLT | Tipear de memoria ~14 comandos en orden (`configure terminal` → `interface gpon-onu_X/Y/Z:N` → `sn-bind enable sn` → `tcont` → `gemport` → `switchport mode hybrid vport` → `service-port` → `exit` → `pon-onu-mng` → `service` → `wan-ip` (si es router) → `vlan port <eth>` por cada puerto LAN → `end` → `write`). |

### 2.3 Riesgos y costos de la gestión manual (observados durante el desarrollo)

- **Modo de configuración equivocado.** En el equipo real, comandos como `interface …`, `pon` o `username …` tipeados en modo EXEC (`ZXAN#`) fallan con `%Error 20200: Invalid input detected`. El código lo documenta en `ZteOltDevice._enter_config_mode`.
- **Identificadores compartidos.** El `service-port` es un identificador **global de toda la OLT**, a diferencia de `tcont`/`gemport` (propios de cada ONU). Reusar uno ya tomado le pisa el servicio a otro cliente. La aplicación lo calcula buscando el primer libre en la running-config (`list_service_activation_helpers`).
- **Numeración confusa de ONU.** El índice que la OLT muestra para una ONU sin autenticar no es el ID que va a recibir; el operador puede confundirlos. La aplicación sugiere el próximo ID libre real (`next_free_onu_id`).
- **Salida de consola con ruido.** Capturar a mano pantalla de un MikroTik incluye eco carácter a carácter y secuencias de control (`\x1b[K`); un backup copiado así no es reimportable sin limpiarlo.
- **Pérdida de tiempo y falta de trazabilidad.** Sin una convención de nombres y carpetas, ubicar el backup de un equipo en una fecha es manual.

### 2.4 Por qué tiene sentido automatizar

Las tareas son **deterministas** (mismo comando por fabricante), **repetitivas** (por equipo / por abonado) y **propensas a error humano**. El conocimiento fino —qué comando, en qué modo, cuándo termina, qué ruido limpiar— es justamente lo que se pierde entre operadores y lo que el software puede fijar una vez.

### 2.5 Necesidades del administrador que cubre

Conexión rápida a un equipo puntual; backup limpio y ubicable; backup masivo tolerante a fallas; extracción estructurada para auditoría; alta de abonado sin errores de secuencia ni de identificadores; y verificación inmediata de lo aplicado.

---

## 3. Objetivos del proyecto

### 3.1 Objetivo general

Proveer una herramienta local, simple y segura que centralice la conexión remota a routers MikroTik y a una OLT ZTE, automatice la obtención y el archivo ordenado de sus configuraciones, y guíe el aprovisionamiento de ONU en la OLT.

### 3.2 Objetivos específicos (todos presentes en el código)

| # | Objetivo | Estado | Dónde |
|---|---|---|---|
| 1 | Conexión interactiva por SSH y Telnet con terminal en pantalla | IMPLEMENTADO | `connection/`, `ui/terminal_window.py` |
| 2 | Soporte multi-fabricante mediante un driver por marca | IMPLEMENTADO (2 marcas + genérico) | `devices/` |
| 3 | Obtención de running-config de un equipo | IMPLEMENTADO | `ConnectionManager.capture_config` |
| 4 | Guardado de backups en estructura `Categoría/Fabricante/host` con nombre `host_AAAA-MM-DD_HH-MM-SS` | IMPLEMENTADO | `backup/manager.py` |
| 5 | Descarga masiva con concurrencia acotada y aislamiento de fallas | IMPLEMENTADO | `batch/runner.py` |
| 6 | Extracción estructurada a YAML | IMPLEMENTADO (completo para MikroTik; parcial para ZTE) | `devices/facts.py`, `devices/parsers.py` |
| 7 | Inventario de equipos usados (sin contraseñas) | IMPLEMENTADO | `core/saved_devices.py` |
| 8 | Aprovisionamiento de ONU en OLT ZTE (autenticar, perfiles, activar Internet router/bridge, usuarios, quitar ONU) | IMPLEMENTADO | `devices/zte_olt.py`, `ui/olt_provisioning_dialog.py` |
| 9 | Descubrimiento automático de puertos PON, perfiles, VLAN y próximo `service-port` libre | IMPLEMENTADO | `list_pon_ports`, `list_service_activation_helpers` |
| 10 | Verificación posterior a la activación (estado y bloques aplicados) | IMPLEMENTADO | `onu_applied_summary` |
| 11 | Acceso SSH a una OLT con firmware antiguo (algoritmos obsoletos) | IMPLEMENTADO (solo Windows) | `connection/ssh_legacy_client.py` |
| 12 | Registro (log) con enmascarado de secretos | IMPLEMENTADO (corregido el 2026-10-05: ahora cubre también `password <valor>`; ver §14) | `core/logging_setup.py`, `tests/test_logging_setup.py` |

**No se incluyen** como objetivos monitoreo de tráfico, administración de switches, telefonía (VoIP) ni multicast/IPTV: existieron en etapas previas o se previeron, y fueron **retirados deliberadamente** (§16).

---

## 4. Alcance de la aplicación

### 4.1 Qué puede hacer actualmente

| Función | Estado | Notas |
|---|---|---|
| Terminal interactiva SSH/Telnet (envío de líneas, salida en vivo, menú contextual copiar/limpiar) | IMPLEMENTADO | Orientada a líneas; no es emulación TTY completa. |
| **GET CONFIG** (running-config) | IMPLEMENTADO | MikroTik: `/export file=` + SFTP con respaldo a lectura de terminal; ZTE: `show running-config`. |
| **SAVE BACKUP** (guardar el texto obtenido) y elección de carpeta | IMPLEMENTADO | La carpeta elegida vive solo en memoria durante la sesión. |
| **EXTRACT YAML** | IMPLEMENTADO | Ver §7.5 y §12. |
| Descarga en lote (1 a N hosts, 1–20 hilos) con salida `.txt`, `.yaml` o ambos | IMPLEMENTADO | `CategoryPanel._start` → `download_configs`. |
| Inventario de equipos recordados con modelo detectado (MikroTik) | IMPLEMENTADO | Modelo vacío («-») en ZTE. |
| OLT: descubrir puertos PON, listar ONU con estado, buscar sin configurar | IMPLEMENTADO | Estado: último campo de la fila de `show gpon onu state`. |
| OLT: autenticar ONU, quitar ONU, crear tipo de ONU | IMPLEMENTADO | `authenticate_onu`, `remove_onu`, `create_onu_type`. |
| OLT: perfiles T-CONT, tráfico (SIR/PIR), IP, VLAN | IMPLEMENTADO | T-CONT tipo 4 y tráfico confirmados contra equipo real; el resto sigue el manual (ver §4.5). |
| OLT: **activar Internet** (router o bridge), multi-puerto, con confirmación y verificación | IMPLEMENTADO | Secuencia confirmada contra equipo real. |
| OLT: cambiar modo del puerto LAN (`tag`/`transparent`) | IMPLEMENTACIÓN PARCIAL | `transparent` **no confirmado**; en una prueba real dejó al equipo conectado sin IP. |
| OLT: usuarios de acceso CLI (listar/alta/baja) | IMPLEMENTADO | Sin confirmar contra equipo real. |
| Visor de logs y pantalla «Acerca de» | IMPLEMENTADO | `ui/simple_panels.py`. |

### 4.2 Dispositivos soportados

| Tipo de equipo (registro) | Clase | Categoría | Observaciones |
|---|---|---|---|
| `MikroTik` | `MikroTikDevice` | router | Detección de prompt, limpieza de eco, detección de modelo, exportación por archivo. Observado en RouterOS 6.49.7. |
| `ZTE OLT` | `ZteOltDevice` | olt | ZXA10 C300. Manual de referencia incluido (V2.0.0, 2013) corresponde a un firmware distinto del real (§15). |
| `Genérico` | `GenericDevice` | generic | Comando de config por defecto `show running-config`. **IMPLEMENTACIÓN PARCIAL:** el comando es configurable en el constructor, pero la interfaz no lo expone, y el tipo solo se puede elegir en la **Terminal**: los paneles ROUTERS/OLT ofrecen únicamente los tipos de su categoría (hoy `MikroTik` y `ZTE OLT`), por lo que la descarga en lote no lo incluye. |

### 4.3 Protocolos soportados

| Protocolo | Estado | Implementación |
|---|---|---|
| SSH | IMPLEMENTADO | `paramiko` (`SshConnection`); `ssh.exe` del sistema para ZTE legacy (`SshLegacyConnection`). |
| Telnet | IMPLEMENTADO | Cliente propio sobre `socket` (`TelnetConnection`); `telnetlib` ya no existe en Python 3.13. |
| SFTP | IMPLEMENTADO (solo MikroTik) | `SshConnection.download_file` sobre la misma sesión SSH. |
| SNMP, API de RouterOS, HTTP/HTTPS, NETCONF/RESTCONF | **NO IMPLEMENTADO ACTUALMENTE** | SNMP y la API de RouterOS existieron en etapas previas y fueron eliminados. |

### 4.4 Qué NO puede hacer actualmente

- Monitoreo/gráficos de tráfico (eliminado).
- Administrar switches (eliminado; el registro ya no ofrece Cisco/Dell/HP).
- Telefonía (SIP/H.248) y multicast/IPTV en la OLT (eliminados).
- Programar descargas automáticas, comparar versiones de configuración, enviar alertas.
- Autodetectar el fabricante (se elige a mano).
- Usuarios/roles propios de la aplicación, base de datos, API.
- **Quitar un `wan-ip` ya aplicado** (volver de Router a Bridge): IMPLEMENTADO como `ZteOltDevice.set_onu_wan_mode` y la pestaña *Router ↔ Bridge* (2026-10-05). Pasar a Router envía el `wan-ip` confirmado; pasar a Bridge prueba `no wan-ip <id>` y luego `wan-ip <id> mode bridge`, y si la OLT rechaza ambos (`%Error`) falla sin guardar. **Los comandos de quitado siguen sin verificarse contra el equipo real.**
- ZTE legacy por SSH en Linux/macOS (depende de `pywinpty` y del `ssh.exe` de Windows).

### 4.5 Límites actuales

- Terminal por líneas, sin colores ANSI ni edición de scrollback; una sesión por ventana.
- Reconocimiento del prompt de la OLT asume el nombre de host `ZXAN` (si se renombra, se pierde el atajo y se vuelve a esperas por silencio: más lento pero correcto).
- Parseo estructurado de la OLT mínimo: solo `show ip interface brief` se convierte en tabla; el resto se guarda como texto.
- Los comandos `show interface` y `show vlan` sin argumento son **rechazados** por el firmware real de la OLT (`%Error 20203`); quedan registrados en la sección `errors` del YAML.
- Las secuencias de los perfiles IP/VLAN/usuarios de la OLT siguen el manual PDF viejo y no tienen confirmación contra el equipo real (el manual resultó ser de otra versión de firmware: §15).

### 4.6 Alcance futuro

Ver §21 (**MEJORA FUTURA / PROPUESTA**).

---

## 5. Arquitectura general del sistema

### 5.1 Visión por capas

```
 Operador
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ INTERFAZ  (ui/)                                              │
│  MainWindow ─ CategoryPanel (ROUTERS / OLT) ─ LogsPanel ─    │
│  AboutPanel · TerminalWindow · OltProvisioningDialog         │
│  theme.py + widgets.py  (tema "Network Ops", componentes)    │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ LÓGICA DE APLICACIÓN                                         │
│  batch/runner.py (descarga en lote)  · devices/facts.py      │
│  devices/file_export.py              · backup/manager.py     │
│  core/saved_devices.py (inventario)                          │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ CAPA DE DISPOSITIVO  (devices/)                              │
│  Device (ABC) → MikroTikDevice · ZteOltDevice · GenericDevice│
│  registry.py (catálogo) · parsers.py                         │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ CAPA DE CONEXIÓN  (connection/)                              │
│  ConnectionManager (hilo lector, candado, capturas)          │
│  SshConnection · SshLegacyConnection · TelnetConnection      │
└───────────────┬──────────────────────────────────────────────┘
                ▼
        Equipo de red  (SSH 22 · Telnet 23 · SFTP)

 Transversal: core/  (errores, validación, logging, inventario)
```

### 5.2 Responsabilidades

| Capa | Responsabilidad | Componentes |
|---|---|---|
| Interfaz | Formularios, validación de entrada, presentación de resultados, hilos de fondo para no bloquear la GUI | `ui/*` |
| Lógica | Orquestar flujos: lote, YAML, exportación por archivo, rutas de backup | `batch/`, `backup/`, `devices/facts.py`, `devices/file_export.py` |
| Dispositivo | Conocimiento del fabricante: comandos, prompt, limpieza, errores, capacidades | `devices/*` |
| Conexión | Transporte interactivo: autenticar, enviar, leer sin bloquear, detectar fin de comando | `connection/*` |
| Transversal | Errores con mensaje de usuario, validación, logging con enmascarado, inventario | `core/*` |

### 5.3 Puntos de acoplamiento a tener en cuenta

- `connection/manager.py` y `batch/runner.py` **conocen por nombre** a `ZteOltDevice` y `MikroTikDevice` para elegir el tipo de conexión (`SshLegacyConnection` para la OLT; sufijo `+ct` para MikroTik). La capa de conexión no es 100 % agnóstica del fabricante (ver §25).
- La interfaz de aprovisionamiento llama directamente a métodos del driver `ZteOltDevice`, inyectándoles una función `run(comando) → texto`; el driver no importa nada de la interfaz.

### 5.4 Manejo de errores, logging y configuración

- **Errores:** jerarquía `TerminalError` (`core/errors.py`) con `user_message` (para mostrar) y `detail` (técnico, para el log).
- **Logging:** `core/logging_setup.py`: archivo rotativo (1 MB × 5) en `~/.network_terminal/logs/network_terminal.log` + consola; filtro de enmascarado de secretos.
- **Configuración persistente:** solo `~/.network_terminal/devices.json` (inventario sin contraseñas) y `~/.network_terminal/known_hosts` (TOFU). **No hay archivo de ajustes**: la carpeta de backups se elige en cada descarga y vive solo en memoria.
- **Procesamiento de comandos:** cada driver define el comando de configuración, la preparación (p. ej. `terminal length 0`), cómo reconocer el fin de la salida y cómo limpiarla.

---

## 6. Estructura de carpetas y archivos

### 6.1 Árbol real

```
redes/
├── red3.py.txt                  prototipo original (CustomTkinter + Netmiko) — LEGADO
├── red3.exe                     ejecutable (~19 MB) del prototipo — LEGADO
└── network_terminal/
    ├── __init__.py              versión 0.1.0
    ├── __main__.py              `python -m network_terminal`
    ├── app.py                   punto de entrada (logging + MainWindow)
    ├── README.md                guía rápida (reescrita al 2026-10-05)
    ├── requirements.txt         dependencias (paramiko, PyYAML, pywinpty)
    ├── c300 commands.txt        referencia de comandos probados en la OLT real
    ├── ZXA10 C300 Configuration Manual (CLI).pdf   manual V2.0.0 (2013)
    ├── 10.99.99.2_2026-09-24_19-08-17.yaml         salida de ejemplo de la OLT (dato real)
    ├── assets/                  icon.ico, icon.png
    ├── core/                    errors · validation · logging_setup · saved_devices
    ├── connection/              base · manager · ssh_client · ssh_legacy_client · telnet_client
    ├── devices/                 base · registry · mikrotik · zte_olt · generic · parsers · facts · file_export
    ├── backup/                  manager
    ├── batch/                   runner
    ├── ui/                      main_window · category_window · terminal_window ·
    │                            olt_provisioning_dialog · simple_panels · widgets · theme
    ├── docs/                    (este documento)
    └── tests/                   15 módulos de prueba + _fakes.py
```

Tamaños (líneas): `devices/zte_olt.py` 726 · `ui/olt_provisioning_dialog.py` 999 · `ui/category_window.py` 601 · `ui/terminal_window.py` 576 · `connection/manager.py` 383 · `batch/runner.py` 349 · `ui/theme.py` 311 · `connection/ssh_legacy_client.py` 234 · `ui/widgets.py` 226 · `devices/base.py` 209 · `connection/ssh_client.py` 205 · `backup/manager.py` 169.

### 6.2 Carpeta por carpeta

#### `core/` — utilidades transversales
- **Para qué existe:** piezas sin dependencia de red ni de interfaz que usa todo el sistema.
- **Archivos:** `errors.py` (jerarquía de errores), `validation.py` (validar host/puerto, sanear nombres de archivo), `logging_setup.py` (logging + enmascarado + rutas `APP_DIR`/`LOG_DIR`), `saved_devices.py` (inventario JSON).
- **Depende de él:** todas las demás capas. **Él depende de:** `devices.registry` (solo `saved_devices._category_for`, con import diferido).
- **Si se elimina:** nada arranca (errores y validación son comunes a todo).

#### `connection/` — transporte
- **Responsabilidad:** abrir/cerrar sesiones interactivas y leer/escribir sin bloquear.
- **Archivos:** `base.py` (contrato `BaseConnection`), `ssh_client.py` (paramiko + SFTP), `ssh_legacy_client.py` (`ssh.exe` + `pywinpty`), `telnet_client.py` (socket + IAC), `manager.py` (ciclo de vida, hilo lector, candado de capturas).
- **Usado por:** `ui/terminal_window.py`, `batch/runner.py`. **Usa:** `core/errors`, `devices/*` (para decidir conexión y captura).

#### `devices/` — conocimiento por fabricante
- **Responsabilidad:** qué comando, qué preparación, cómo terminar y limpiar la salida, qué es un error, qué capacidades tiene cada equipo.
- **Archivos:** `base.py` (ABC `Device`), `registry.py` (catálogo `DEVICE_TYPES`, categorías), `mikrotik.py`, `zte_olt.py`, `generic.py`, `parsers.py` (texto→estructuras), `facts.py` (recolección YAML), `file_export.py` (exportación por archivo).
- **Usado por:** UI, `batch`, `connection.manager`. **Usa:** `core`.

#### `backup/` — archivos de salida
- `manager.py`: rutas (`device_backup_dir`), nombres (`build_backup_filename`), escritura `.txt`/`.yaml` (`BackupManager`), detección del Escritorio (`get_desktop_dir`, API de Windows), carpeta elegida en sesión (`set_backup_root`/`current_backup_root`).

#### `batch/` — automatización masiva
- `runner.py`: `parse_targets`, `BulkConfig`, `HostResult`, `download_configs` (pool de hilos), `_drain`, `_capture`, `_detect_model`.

#### `ui/` — interfaz
- `main_window.py` (marco + navegación), `category_window.py` (paneles Routers/OLT: inventario + descarga), `terminal_window.py` (terminal interactiva), `olt_provisioning_dialog.py` (asistente OLT), `simple_panels.py` (Logs, Acerca de), `widgets.py` y `theme.py` (apariencia).

#### `tests/` — verificación
- Pruebas con dobles de conexión (`FakeConnection`, `ScriptedConnection`, `FakeSocket` en `_fakes.py`); no tocan equipos.

### 6.3 Archivos principales (ARCHIVO → COMPONENTE → RESPONSABILIDAD → RELACIÓN)

| Archivo | Componente | Responsabilidad | Relación con el sistema |
|---|---|---|---|
| `app.py` | `main()` | Configura logging y levanta `MainWindow` (import diferido de Tk) | Único punto de entrada |
| `connection/manager.py` | `ConnectionManager`, `ConnectionParams` | Conexión asíncrona, hilo lector → cola, candado de capturas, `capture_config`, `run_capture`, `_drain_until_quiet`, `_collect` | Lo usan `TerminalWindow` y el diálogo OLT; elige la conexión según protocolo y tipo de equipo |
| `connection/ssh_client.py` | `SshConnection` | SSH vía paramiko; política de host keys (Reject/TOFU); sufijo `+ct`; SFTP | Una conexión por equipo |
| `connection/ssh_legacy_client.py` | `SshLegacyConnection` | `ssh.exe` del sistema en consola virtual (`pywinpty`) con algoritmos heredados | Solo ZTE OLT por SSH |
| `connection/telnet_client.py` | `TelnetConnection` | Socket + negociación IAC mínima + login best-effort | Telnet |
| `devices/base.py` | `Device` (ABC) | Contrato de driver: capacidades, comandos, `execute`, `clean_output`, `is_output_complete`, `is_error_output`, ganchos de exportación por archivo | Superclase de todos los drivers |
| `devices/mikrotik.py` | `MikroTikDevice` | Comandos RouterOS, prompt, limpieza de eco, modelo, `postprocess` de facts | Registrado como `MikroTik` |
| `devices/zte_olt.py` | `ZteOltDevice` | Comandos ZXAN y ~25 métodos de aprovisionamiento | Registrado como `ZTE OLT` |
| `devices/facts.py` | `collect_device_facts` | Ejecuta los comandos de recolección, parsea, ordena, registra errores | Alimenta `save_yaml` |
| `devices/file_export.py` | `capture_via_file` | Exportar a archivo → SFTP → borrar | Lo usan `capture_config` y `batch._capture` |
| `batch/runner.py` | `download_configs` | Descarga en lote con `ThreadPoolExecutor` | Lo invoca `CategoryPanel._start` |
| `backup/manager.py` | `BackupManager` | Escribe `.txt`/`.yaml` sin sobrescribir | Lo usan lote y Terminal |
| `core/saved_devices.py` | `remember_device`, `load_devices` | Inventario `devices.json` sin contraseñas | Lo usa el panel de inventario |
| `ui/olt_provisioning_dialog.py` | `OltProvisioningDialog` | Asistente OLT (pestañas ONU / PERFILES / ACTIVAR SERVICIO / USUARIOS OLT) | Llama al driver ZTE con `run` inyectado |

> **Si se elimina o modifica:** `devices/base.py` (rompe todos los drivers), `connection/manager.py` (rompe Terminal y asistente OLT), `devices/registry.py` (la UI ya no ofrece equipos), `backup/manager.py` (no se guardan archivos). Eliminar `devices/file_export.py` solo quita la vía por archivo (el respaldo por terminal sigue). Eliminar `ssh_legacy_client.py` deja sin SSH a la OLT con firmware viejo.

### 6.4 Archivos que no son código de la aplicación

| Archivo | Naturaleza |
|---|---|
| `README.md` | Guía rápida, **reescrita el 2026-10-05** (la versión anterior documentaba Monitor de tráfico, SNMP, API de RouterOS, Cisco/Dell/HP y un botón «Descarga masiva…», que ya no existían; ver §16). |
| `c300 commands.txt` | Secuencia de comandos probada en la OLT real; **fuente** de la implementación actual de `activate_broadband_service`. |
| `ZXA10 C300 Configuration Manual (CLI).pdf` | Manual V2.0.0 (2013). Sirvió de base inicial, pero describe un dialecto distinto del firmware real (§15). |
| `10.99.99.2_….yaml` | Salida real de una extracción de la OLT. Contiene configuración de producción: no conviene distribuirla. |
| `red3.py.txt` / `red3.exe` | Prototipo original. El `.py.txt` contiene credenciales fijas en el código (no se reproducen aquí). Código **reemplazado** (§16). |


---

## 7. Explicación del código

Formato usado: **ARCHIVO → COMPONENTE → RESPONSABILIDAD → RELACIÓN CON EL RESTO DEL SISTEMA**.

### 7.1 `core/` — base común

**`core/errors.py` → jerarquía `TerminalError` → mensajes para el usuario y detalle técnico → la usan todas las capas.**
Cada excepción lleva `user_message` (texto corto que muestra la interfaz) y `detail` (para el log; el docstring prohíbe poner secretos). Clases: `HostInvalidError`, `ConnectFailedError`, `ConnectTimeoutError`, `AuthFailedError`, `PortClosedError`, `ProtocolError`, `HostKeyError`, `DependencyMissingError`, `CapabilityUnsupportedError`. La interfaz captura `TerminalError` y muestra `exc.user_message`; el motor de lote guarda ambos campos en `HostResult`.

**`core/validation.py` → `validate_host`, `validate_port`, `default_port_for`, `sanitize_filename_component`.**
- `validate_host(str)` → devuelve host normalizado o lanza `HostInvalidError`: acepta IP (`ipaddress`) o hostname RFC (etiquetas de 1–63 caracteres, largo ≤ 253, sin espacios).
- `validate_port(valor)` → `int` en 1–65535 o `ValueError`.
- `default_port_for("ssh"|"telnet")` → 22 / 23.
- `sanitize_filename_component` → deja `[A-Za-z0-9._-]`, colapsa repeticiones, recorta a 80, evita nombres reservados de Windows (`CON`, `COM1`…). **Relación:** garantiza que ni el host ni el fabricante puedan generar rutas fuera de la carpeta de backups (`backup/manager.py`).

**`core/logging_setup.py` → `configure_logging`, `SecretRedactingFilter`, `APP_DIR`, `LOG_DIR`.**
Archivo rotativo `~/.network_terminal/logs/network_terminal.log` (1 MB × 5 copias) y consola. El filtro enmascara `password=…`, `password <valor>`, `passwd` y `secret` (en ambas formas) antes de escribir. *Corregido el 2026-10-05:* hasta entonces no cubría la forma `password <valor>` y la clave de `username … password …` de la OLT se escribía en claro (ver §14).

**`core/saved_devices.py` → `SavedDevice`, `remember_device`, `load_devices`, `remove_device`.**
Inventario en `~/.network_terminal/devices.json` con `{name, host, port, protocol, device_type, username, category, model}` — **nunca la contraseña**. Escritura atómica (archivo temporal + `replace`) bajo un `threading.Lock`. La clave de unicidad es `(host, protocolo)`. `category` se completa desde el registro de drivers (compatibilidad con archivos antiguos). *Nota:* algunos comentarios aún mencionan el «Monitor de tráfico» (función eliminada): son comentarios obsoletos, no código activo.

### 7.2 `connection/` — transporte

**`connection/base.py` → `BaseConnection` (ABC) → contrato de transporte interactivo.**
Métodos: `connect()`, `send(str)`, `read() → str` (**no bloqueante**; devuelve `""` si no hay nada), `is_alive()`, `close()`, `send_line(línea)` (añade `default_newline`). Atributos de clase: `default_newline`, `supports_file_download` (False) y `download_file(ruta) → bytes`.

**`connection/manager.py` → `ConnectionManager` → ciclo de vida de una sesión y toda la «conversación» con el equipo.**

| Elemento | Descripción |
|---|---|
| `ConnectionParams` | `host, port, protocol, username, password, device_type, trust_new_host_key, connect_timeout=10.0` |
| `connect_async(params, on_success, on_error)` | Lanza `_connect_worker` en un hilo: valida host/puerto, construye la conexión, conecta (y, en Telnet, hace `login`), arranca el hilo lector |
| `_build_connection(params)` | SSH + `ZTE OLT` → `SshLegacyConnection`; SSH + otro → `SshConnection` (con `dumb_terminal` si es MikroTik); Telnet → `TelnetConnection` |
| `_read_loop` | Hilo lector: `conn.read()` → cola `_out`; duerme 0,05 s si no hay datos; respeta el evento `_pause` |
| `poll_output()` | La interfaz vacía la cola (cada 60 ms) para dibujar la salida |
| `_capture_lock` | Candado que serializa **toda** operación sobre el canal (`send`, `send_line`, `capture_config`, `run_capture`) para que dos operaciones no lean la respuesta una de la otra |
| `_reader_paused()` | Pausa el hilo lector durante una captura (duerme 0,15 s para que termine su iteración) |
| `_drain_until_quiet(conn, settle, hard_cap, done_check)` | Descarta lo que quedó sin leer antes de mandar un comando; si el driver reconoce su prompt, **espera a verlo en reposo** (evita que un banner con pausas internas se «cuele» como respuesta) |
| `capture_config(device, quiet_after=8, overall_timeout=60)` | Obtiene la running-config: primero la vía por archivo si aplica; si no, `prepare_commands` + comando + lectura hasta el prompt/silencio; devuelve `device.clean_output(texto)` |
| `run_capture(comando, quiet_after, overall_timeout, done_check)` | Ejecuta un comando suelto y devuelve su salida (lo usan el YAML y el asistente OLT) |
| `_collect(...)` | Núcleo común de lectura: envía el comando y acumula hasta `done_check` (con `idle ≥ 0,4 s`), `quiet_after` de silencio, o `overall_timeout` |

*Manejo de errores:* cualquier excepción de la conexión se traduce a `TerminalError`; un fallo en el hilo lector queda en el log y deja el estado en «disconnected».

**`connection/ssh_client.py` → `SshConnection` → SSH con paramiko.**
- `connect()`: `SSHClient`, `load_system_host_keys()`, `known_hosts` propio (`~/.network_terminal/known_hosts`). Política **`RejectPolicy`** por defecto; con «Confiar y recordar host key» usa `AutoAddPolicy` y guarda la clave (TOFU, con `WARNING` en el log).
- `allow_agent=False`, `look_for_keys=False` (solo usuario/contraseña), timeouts de conexión, banner y autenticación = `connect_timeout`.
- MikroTik: el usuario se envía como `usuario+ct` (consola simple: sin color ni redibujado de línea).
- `invoke_shell(width=200, height=50)`; canal no bloqueante; `default_newline = "\r\n"` (RouterOS solo reconoce `\r` como Enter).
- `download_file(ruta)`: abre SFTP sobre la **misma** sesión autenticada y lee el archivo.
- Mapeo de excepciones de paramiko/socket a errores propios (`AuthFailedError`, `HostKeyError`, `PortClosedError`, `ConnectTimeoutError`…).
- `close()` cierra canal y cliente y **descarta la contraseña** (`_password = ""`).

**`connection/ssh_legacy_client.py` → `SshLegacyConnection` → SSH con algoritmos heredados vía `ssh.exe`.**
Ver §9.3. Resumen: lanza `C:\Windows\System32\OpenSSH\ssh.exe` dentro de una consola virtual de `pywinpty`, con `-oKexAlgorithms=+diffie-hellman-group1-sha1 -oHostKeyAlgorithms=+ssh-dss -oCiphers=+aes128-cbc -oMACs=+hmac-sha1`, espera el texto `password:` y escribe la contraseña por la consola (no por argumentos). Clasifica errores por el texto que imprime `ssh` (`host key verification failed`, `connection refused`, `timed out`, `permission denied`).

**`connection/telnet_client.py` → `TelnetConnection` → Telnet sobre socket.**
`socket.create_connection` con timeout; socket no bloqueante; `_negotiate` filtra secuencias IAC y rechaza toda opción (responde `WONT` a `DO` y `DONT` a `WILL`) para caer en modo línea; `send` duplica el byte `0xFF`; `login(user, pass)` reconoce `login:/username:/user:` y `password` y envía las credenciales (best-effort: si no reconoce los prompts, se completa a mano).

### 7.3 `devices/` — conocimiento por fabricante

**`devices/base.py` → `Device` (ABC) → contrato de driver.**

| Miembro | Para qué sirve |
|---|---|
| `name`, `vendor`, `category` (`router`/`olt`/`generic`), `capabilities` | Identidad y capacidades (`terminal`, `backup`, `info`, `interfaces`, `vlans`, `automation`; el driver declara el resto, p. ej. `olt_provisioning`) |
| `HAS_PROMPT_DETECTION` + `is_output_complete(texto)` | Reconocer que el equipo terminó de responder (vuelve el prompt) |
| `clean_output(texto)` | Sacar ruido de consola del texto capturado |
| `is_error_output(texto)` | Reconocer el rechazo de un comando |
| `prepare_commands()` | Comandos previos (p. ej. quitar paginación) |
| `running_config_command()` (abstracto) | Comando que devuelve la configuración |
| `collection_commands()`, `parse_section()`, `postprocess()` | Recolección estructurada para YAML |
| `file_export_command/remote_name`, `file_remove_command` | Ganchos de exportación por archivo (solo MikroTik los implementa) |
| `execute(comando, quiet_after, overall_timeout)` | Envío y lectura sobre `self.conn` (lo usa el lote) |
| `detect_model(texto)` | Modelo real a partir de la salida de `info_command()` |

**Código disponible pero sin llamadores en la aplicación:** `get_running_config()`, `get_device_info()`, `get_interfaces()`, `get_vlans()` y la capacidad `automation` (declarada, sin consumidores). Quedaron de una etapa previa; hoy los flujos usan `capture_config`/`collect_device_facts`.

**`devices/mikrotik.py` → `MikroTikDevice`.**
- Comando de config: `/export`. Info: `/system resource print`.
- Prompt: `_PROMPT_RE` (`[usuario@nombre] >`, con `\x1b[K` opcional) → `HAS_PROMPT_DETECTION = True`.
- `clean_output`: quita secuencias `\x1b[K` y **toda línea que empiece con el prompt** (eco carácter a carácter y prompt final); ninguna línea de una configuración real empieza así.
- `detect_model`: lee `board-name:` de `/system resource print`.
- Exportación por archivo: `/export file=<nombre>` → `<nombre>.rsc` → `/file remove "<nombre>.rsc"`.
- Recolección YAML (`_PRINT_SECTIONS`, siete comandos con `print detail without-paging`): interfaces, ethernet, direcciones IP, rutas, VLAN, filtros de firewall, NAT; `parse_mikrotik_print_detail` los vuelve listas de diccionarios; `postprocess` fusiona velocidad/PoE del bloque ethernet en `interfaces` y calcula `summary` (gateway por defecto, IP, conteos).

**`devices/zte_olt.py` → `ZteOltDevice`.**
- Comandos: config `show running-config`; preparación `terminal length 0`; info `show version`; `show interface`; `show vlan`.
- Prompt: `ZXAN[^\r\n]*#` (cubre `ZXAN#`, `ZXAN(config)#`, subniveles); `clean_output` saca las líneas que son solo el prompt; `is_error_output` reconoce `%Error…`.
- Recolección YAML: `interfaces`, `ip_interface_brief`, `ip_interface`, `routes`, `vlans`, `gpon_onu_state`, `running_config`; solo `ip_interface_brief` se parsea a tabla.
- **Aprovisionamiento** (todos reciben `run(comando) → texto`; ver §7.3.1).

#### 7.3.1 Inventario de métodos de aprovisionamiento ZTE

| Método | Qué envía (resumen) | Respaldo |
|---|---|---|
| `_enter_config_mode(run)` | `end` + `configure terminal` (antes de **cada** operación de configuración) | Confirmado en equipo real |
| `list_pon_ports` | `show running-config` → líneas `interface gpon-olt_*` | Mismo escaneo que «Actualizar desde OLT» |
| `list_onus(pon)` | `show gpon onu state <pon>` + `show gpon onu uncfg <pon>` | Formato de `state` **no confirmado** con captura real |
| `list_unconfigured_onus`, `onu_state`, `list_used_onu_ids`, `next_free_onu_id` | consultas `show gpon onu …` | Tabla `uncfg` confirmada |
| `list_onu_types` | `show onu-type gpon` + running-config (tipos de fábrica + personalizados) | Confirmado |
| `authenticate_onu` | `interface <pon>` / `onu <id> type <tipo> sn <sn>` | Confirmado |
| `remove_onu` | `interface <pon>` / `no onu <id>` | Confirmado |
| `create_onu_type` | `pon` / `onu-type …` | Según manual |
| `create_tcont_profile` | `gpon` / `profile tcont <n> type <t> [fixed\|assured\|maximum]` | Tipo 4 confirmado |
| `create_traffic_profile` | `gpon` / `profile traffic <n> sir <s> pir <p>` | Confirmado |
| `create_onu_ip_profile`, `create_onu_vlan_profile` | `onu profile ip/vlan …` | Según manual |
| `activate_broadband_service` | ver abajo | **Confirmado en equipo real** |
| `set_onu_lan_port_mode` | `pon-onu-mng` / `vlan port <eth> mode tag\|transparent` | `transparent` no confirmado (dejó al cliente sin IP en una prueba) |
| `list_users`, `add_user`, `remove_user` | `username …` | Según manual |
| `list_service_activation_helpers` | una lectura de la running-config → perfiles T-CONT/tráfico/VLAN-WAN, VLAN usadas, puertos PON, próximo `service-port` libre | Escaneo propio |
| `onu_applied_summary` | fila de estado + bloques `interface`/`pon-onu-mng` de esa ONU | Escaneo propio |

Secuencia de `activate_broadband_service` (la verificada en el equipo real):

```
end · configure terminal
interface gpon-onu_X/Y/Z:N
  sn-bind enable sn
  tcont <id> name <nombre> profile <perfil-tcont>
  gemport <id> name <nombre> tcont <id>
  [gemport <id> traffic-limit downstream <perfil-tráfico>]
  switchport mode hybrid vport <v>
  service-port <sp> vport <v> user-vlan <vlan-usuario> vlan <vlan-servicio>
exit
pon-onu-mng gpon-onu_X/Y/Z:N
  service <sid> gemport <id> vlan <vlan-servicio>
  [wan-ip <i> mode dhcp vlan-profile <perfil> host <h>]      ← solo modo Router
  vlan port <eth_0/x> mode tag vlan <vlan-usuario>           ← uno por puerto LAN
end · write
```

**`devices/generic.py` → `GenericDevice`:** `running_config_command()` devuelve `show running-config` (configurable por constructor, no desde la interfaz).

**`devices/registry.py` → `DEVICE_TYPES`, `DEVICE_CATEGORIES`, `CATEGORY_LABELS`, `device_types_for_category`, `create_device`.** Catálogo `nombre → clase`; las categorías se arman solas a partir de `Device.category`.

**`devices/parsers.py` → `parse_mikrotik_print_detail`, `parse_table`.** Best-effort: si algo no encaja, se conserva el texto (`raw_lines`/`_raw`) y nunca se propaga una excepción.

**`devices/facts.py` → `collect_device_facts(device, run_command, host, protocol, include_raw)`.**
ENTRADA: driver + función que ejecuta comandos. PROCESAMIENTO: ejecuta `prepare_commands`; por cada comando de `collection_commands()`: ejecuta, normaliza (`normalize_text`: LF, sin espacios finales), **detecta rechazo del equipo** (`is_error_output`) y lo manda a `errors` en vez de guardarlo como dato, parsea, y al final ejecuta `postprocess`. SALIDA: diccionario ordenado (`device`, secciones conocidas, `errors`, `raw`).

**`devices/file_export.py` → `supports_file_export`, `capture_via_file`.** Ver §12.

### 7.4 `backup/` y `batch/`

**`backup/manager.py`** — `BackupManager.save_config/save_yaml` (nunca sobrescribe: `_unique_path` agrega `_1`, `_2`…; YAML con estilo de bloque literal para textos multilínea); `device_backup_dir(base, host, category, vendor)` → `base/<Routers|OLT|Otros>/<fabricante>/<host>`; `get_desktop_dir()` usa la API `SHGetFolderPathW` en Windows (respeta OneDrive).

**`batch/runner.py`** — `parse_targets(texto)` (separadores: línea, coma, `;`, espacio, tab; ignora `#`; deduplica sin distinguir mayúsculas; separa válidos/ inválidos), `BulkConfig`, `HostResult`, `download_configs` (ver §11).

### 7.5 `ui/` — interfaz

**`ui/main_window.py` → `MainWindow`.** Marco con barra lateral: `ROUTERS`, `OLT`, `LOGS`, `ACERCA DE`. Los paneles se crean **una sola vez** (al primer uso) y se muestran/ocultan con `tkraise`, de modo que una descarga en curso no se pierde al cambiar de sección. Al cerrar, avisa si hay una descarga activa (`is_busy`).

**`ui/category_window.py` → `CategoryPanel` (`RoutersPanel`, `OltPanel`).** Inventario (tabla con estado, IP, fabricante, modelo, protocolo, puerto), alta de equipo, formulario de descarga (usuario, contraseña, fabricante, protocolo, puerto, concurrencia 1–20, salida, TOFU, **destino**) y tabla de resultados con barra de progreso y cancelación.

**`ui/terminal_window.py` → `TerminalWindow`.** Formulario de conexión (se colapsa al conectar), vista de terminal, línea de comandos, botones `GET CONFIG`, `SAVE BACKUP`, `CARPETA…`, `EXTRACT YAML`, `OLT PROVISIONING…` (solo si el driver declara `olt_provisioning`) y `CLEAR`; barra de estado con indicador. Un temporizador (`_pump`, 60 ms) traslada la salida de la cola a pantalla. Las acciones largas corren en hilos y vuelven a la interfaz con `after(0, …)`.

**`ui/olt_provisioning_dialog.py` → `OltProvisioningDialog`.** Cuatro pestañas: **ONU** (detectar puertos PON, buscar sin configurar, autenticar, crear tipo, listar ONU del puerto, quitar ONU), **PERFILES** (T-CONT, IP, VLAN, tráfico), **ACTIVAR SERVICIO** (subpestañas *Internet* y *Modo LAN*), **USUARIOS OLT**. Un único scroll general y un panel «Resultado». No abre conexiones: recibe `run(comando)`.

**`ui/theme.py` / `ui/widgets.py`.** Tema oscuro verde «Network Ops» (paleta, tipografías, estilos `ttk`) y componentes (`CyberButton`, `CyberPanel`, `StatusIndicator`, `ScrollableFrame`, `TerminalText`…). `CyberCheckbutton`/`CyberRadiobutton` usan widgets clásicos de Tk porque, en Windows, el indicador de `ttk.Checkbutton` ignora el estilo y queda ilegible. `MetricCard` está definido sin usos (resto de la etapa del monitor).

**`ui/simple_panels.py`.** `LogsPanel` (últimas 500 líneas del log, abrir carpeta) y `AboutPanel` (descripción del proyecto).


---

## 8. Flujo de funcionamiento

Formato por flujo: **OBJETIVO → ENTRADA → PROCESAMIENTO → COMUNICACIÓN → RESULTADO**. Los nombres son los reales del código.

### 8.1 Arranque

1. `python -m network_terminal` → `__main__.py` → `app.main()`.
2. `configure_logging()` crea `~/.network_terminal/logs/` y registra el archivo de log.
3. Se importa `ui.main_window` (import diferido: Tk solo se carga si se abre la interfaz) y se crea `MainWindow`: aplica el tema (`theme.apply_theme`), arma encabezado y barra lateral.
4. `_select("router")` crea `RoutersPanel`, que carga el inventario (`load_devices()`, filtrado por categoría `router`).

No hay lectura de archivo de configuración: la aplicación arranca siempre con los mismos valores por defecto.

### 8.2 Conectarse con la Terminal

- **ENTRADA:** host, usuario, contraseña, tipo de equipo, protocolo, puerto, opción TOFU.
- **PROCESAMIENTO:** `TerminalWindow._on_connect` valida host/puerto (`validate_host`, `validate_port`) → arma `ConnectionParams` → `ConnectionManager.connect_async` (hilo) → `_connect_worker` → `_build_connection` → `conn.connect()` → (Telnet: `login`) → se arranca el hilo lector.
- **COMUNICACIÓN:** SSH (22) / Telnet (23) hacia el equipo; en la OLT ZTE por SSH, `SshLegacyConnection`.
- **RESULTADO:** indicador «ONLINE», la sesión queda en pantalla, el formulario de conexión se colapsa a un resumen (`host:puerto (PROTOCOLO, tipo)`) con botón «EDITAR…», y el equipo se recuerda en el inventario sin contraseña (`remember_device`).
- **Errores:** `TerminalError` → mensaje en pantalla y cartel; el formulario permanece visible para corregir.

### 8.3 Enviar un comando a mano

`ent_cmd` (Enter) → `ConnectionManager.send_line` (bajo `_capture_lock`) → el hilo lector deja la respuesta en la cola → `_pump` la dibuja. Se bloquea mientras hay una captura en curso (`_capture_busy`).

### 8.4 GET CONFIG (obtener configuración)

1. Hilo de fondo: `ConnectionManager.capture_config(device)`.
2. Toma `_capture_lock`, pausa el hilo lector y vacía el canal (`_drain_until_quiet`).
3. **MikroTik por SSH:** intenta `capture_via_file` (exportar a archivo → SFTP → borrar, §12). Si falla, registra una advertencia y sigue con 4.
4. Ejecuta `prepare_commands()` (ZTE: `terminal length 0`), envía `running_config_command()` (`/export` o `show running-config`) y lee hasta reconocer el prompt (con 0,4 s de reposo) o 8 s de silencio, con tope de 60 s.
5. `device.clean_output()` limpia el eco/prompt. El texto se muestra y queda en `_last_config` (habilita `SAVE BACKUP`).

### 8.5 SAVE BACKUP

`BackupManager(device_backup_dir(raíz, host, categoría, fabricante)).save_config(texto, host)` → `…/Backups/<Routers|OLT>/<fabricante>/<host>/<host>_AAAA-MM-DD_HH-MM-SS.txt`. Rechaza contenido vacío; no sobrescribe archivos previos. La raíz es `Escritorio/Backups` salvo que se haya elegido otra con «CARPETA…».

### 8.6 EXTRACT YAML

`collect_device_facts(device, lambda c: manager.run_capture(c, done_check=…), host, protocol)` en un hilo → por cada comando de `collection_commands()`: ejecutar, normalizar, detectar rechazo, parsear → `postprocess` → `BackupManager.save_yaml`. El YAML incluye `device` (metadatos), las secciones, `errors` y `raw`.

### 8.7 Descarga en lote (Routers / OLT)

- **ENTRADA:** lista de hosts (una IP = individual; varias = lote automáticamente), credenciales comunes, fabricante, protocolo, puerto, concurrencia, salida (`.txt` / `.yaml` / ambos), TOFU, destino.
- **PROCESAMIENTO:** `CategoryPanel._start` → `parse_targets` → `BulkConfig` → hilo → `download_configs` (§11).
- **RESULTADO:** tabla con OK/ERROR por equipo, archivos generados, tiempo y modelo detectado; los equipos exitosos se recuerdan en el inventario.

### 8.8 Aprovisionamiento de una ONU en la OLT

1. Desde la Terminal conectada a un `ZTE OLT`, el botón **OLT PROVISIONING…** abre `OltProvisioningDialog` pasándole `run = lambda cmd: _run_on_session(device, cmd)` (que usa `run_capture` con 8 s de silencio / 90 s de tope y detección de prompt).
2. A los 300 ms el diálogo **detecta los puertos PON** solos (`list_pon_ports`) y los ofrece en los desplegables.
3. **Listar ONU** del puerto (`list_onus`) o **buscar sin configurar** (`list_unconfigured_onus` + `next_free_onu_id`: sugiere el próximo ID libre, no el índice que muestra la OLT).
4. **Autenticar** (`authenticate_onu`: `interface <pon>` / `onu <id> type <tipo> sn <sn>`), seguido de `show gpon onu state` para confirmar.
5. **Activar Internet:** «ACTUALIZAR DESDE OLT» llena perfiles, VLAN, próximo `service-port` libre; se elige PON PORT + ID de ONU, perfil T-CONT, VLAN, puertos LAN (casillas `eth_0/1…4` + «otros») y **modo Router o Bridge**; el sistema pide **confirmación** con un resumen y ejecuta `activate_broadband_service`.
6. **Verificación:** se muestra la fila de estado de la ONU y los bloques `interface` / `pon-onu-mng` que quedaron en la running-config.

### 8.9 Modo Router vs. Bridge (comportamiento observado)

- **Router:** `wan-ip … mode dhcp vlan-profile <perfil>` + `vlan port <eth> mode tag vlan <vlan>`. En el equipo real, la ONU terminó actuando como router y entregó una red privada (observada `192.168.10.0/24`) a **todos** sus puertos LAN. Esa red la define la propia ONU, no los comandos de la OLT.
- **Bridge:** se omite el `wan-ip`; el puerto queda solo etiquetado a la VLAN y el equipo del cliente recibe la IP del proveedor.
- Antes de que la ONU complete su negociación WAN puede observarse un comportamiento intermedio (la PC recibe la IP del proveedor). La causa exacta de ese intervalo es una **hipótesis**, no una conclusión verificada.

---

## 9. Comunicación con los dispositivos de red

### 9.1 Resumen por protocolo

| Aspecto | SSH (`SshConnection`) | SSH legacy ZTE (`SshLegacyConnection`) | Telnet (`TelnetConnection`) |
|---|---|---|---|
| **Puerto** | 22 (editable) | 22 (editable) | 23 (editable) |
| **Establecimiento** | `paramiko.SSHClient.connect` | Subproceso `ssh.exe` en consola virtual | `socket.create_connection` |
| **Autenticación** | Usuario + contraseña (sin agente ni claves) | Contraseña escrita en la consola al aparecer `password:` | Login por texto (`login:`/`password`), best-effort |
| **Cifrado** | Moderno (negociado por paramiko) | **Obsoleto por necesidad**: DH group1 + SHA-1, host key DSA, AES-128-CBC, HMAC-SHA1 | **Ninguno** (texto plano) |
| **Verificación del servidor** | `RejectPolicy` por defecto; TOFU opcional con `known_hosts` propio | `StrictHostKeyChecking=yes`, o `accept-new` con TOFU; usa el `known_hosts` del usuario de Windows | No existe |
| **Envío de comandos** | `send` sobre el canal; línea = texto + `\r\n` | `PtyProcess.write` | `sendall` (duplica `0xFF`) |
| **Recepción** | `recv(65535)` no bloqueante, UTF-8 con reemplazo | Hilo interno lee la consola y deja el texto en una cola | `recv` no bloqueante + filtrado IAC |
| **Cierre** | Cierra canal/cliente, descarta la contraseña | `terminate(force=True)`, descarta la contraseña | Cierra el socket |

### 9.2 Cómo se detecta que un comando terminó

Sin esto una terminal «de líneas» no sabe cuándo parar de leer. Hay dos señales y una red de seguridad:

1. **Prompt reconocido (rápido y fiable)** — drivers con `HAS_PROMPT_DETECTION`: MikroTik (`[user@host] >`) y ZTE (`ZXAN…#`). Se exige además `idle ≥ 0,4 s` para no cortar si todavía llega más texto.
2. **Silencio de `quiet_after` segundos** — red de seguridad siempre activa (8 s en capturas de configuración; 5 s por defecto en `run_capture`).
3. **`overall_timeout`** — tope absoluto (60 s en `capture_config`, 90 s para el asistente OLT, 45 s por defecto en `run_capture`).

Antes de enviar, `_drain_until_quiet` descarta lo pendiente del canal. Con prompt reconocible exige **ver el prompt en reposo** (hasta `hard_cap` 10 s): resuelve el caso real de un banner de login que llega en ráfagas con pausas y se colaba como si fuera la respuesta del comando.

### 9.3 Detalle de la conexión SSH a la OLT con firmware viejo

- **Problema:** el firmware de la OLT solo ofrece `ssh-dss` (clave de host DSA) y algoritmos de hace más de una década. `paramiko` 4.x eliminó por completo `DSSKey`: negociar con esa OLT es imposible con esa librería, sin importar la configuración.
- **Solución:** `ssh.exe` de `C:\Windows\System32\OpenSSH` (build de Windows que conserva DSA) con las opciones `+` (agregan algoritmos sin quitar los modernos). Se prefiere la ruta absoluta porque otro `ssh` en el `PATH` (p. ej. el de Git) fue verificado sin soporte DSA.
- **Contraseña:** `ssh` solo muestra un prompt utilizable si cree estar en una terminal; se usa `pywinpty` (ConPTY) y se escribe la contraseña por la consola al ver `password:`. No va en argumentos de línea de comandos (visibles en la lista de procesos) ni en archivos.
- **Login «best-effort»:** igual que Telnet, `connect()` no verifica que la contraseña sea correcta: si falla, se ve `Permission denied, please try again.` en la terminal y el equipo vuelve a pedir contraseña (comportamiento observado contra la OLT real).
- **Errores clasificados por texto:** `host key verification failed` → `HostKeyError`; `connection refused` → `PortClosedError`; `timed out` → `ConnectTimeoutError`; `permission denied` → `AuthFailedError`.
- **Alcance:** solo Windows (requiere `pywinpty` y el `ssh.exe` del sistema). En otros sistemas lanza `DependencyMissingError`.

### 9.4 Timeouts (valores reales)

| Contexto | Valor |
|---|---|
| Conexión (paramiko: conexión, banner, auth) | 10 s (`ConnectionParams.connect_timeout`) |
| Lote: conexión / lectura de config | 10 s / silencio 8 s, tope 60 s (`BulkConfig`) |
| Lote: pausa tras conectar | 0,3 s (`connect_settle`) |
| Detección de modelo | silencio 2 s, tope 15 s |
| Exportación por archivo | comando 3 s / 20 s; descarga SFTP 8 reintentos × 0,5 s |
| Asistente OLT | silencio 8 s / tope 90 s |

### 9.5 Credenciales y riesgos de seguridad de la comunicación

- Las contraseñas viven solo en memoria: `StringVar` → `ConnectionParams` → atributo privado de la conexión; nunca se escriben a disco por diseño.
- **Telnet transmite usuario y contraseña en texto claro**: solo es razonable en una red de gestión aislada; está soportado porque algunos equipos lo exigen.
- La OLT por SSH usa criptografía obsoleta (DSA, SHA-1, CBC, DH group1): **riesgo aceptado por necesidad del equipo**; conviene limitarlo a una red de gestión.
- El modo TOFU confía en la primera clave vista: un ataque de intermediario en ese primer contacto no se detecta.

---

## 10. Soporte multifabricante

### 10.1 Cómo se diferencia un equipo de otro

El operador **elige el tipo** de equipo en un desplegable (no hay autodetección). `devices/registry.py` mantiene `DEVICE_TYPES = {nombre: clase}`; `create_device(nombre, conexión)` instancia el driver. Cada clase fija `name`, `vendor`, `category` y `capabilities`.

### 10.2 Qué es específico y qué es genérico

| Genérico (en `Device` / capa de conexión) | Específico (en cada driver) |
|---|---|
| Ejecutar y acumular salida (`execute`), ciclo de captura, candado, drenaje | Comando de configuración |
| Normalización de texto en `facts` | Comandos de preparación (`terminal length 0`) |
| Rutas y nombres de backup | Reconocimiento del prompt y limpieza de eco |
| Manejo de errores y logging | Formato de errores del equipo (`%Error…`) |
| Hilo lector y no bloqueo | Comandos de recolección y parseo, detección de modelo |
| | Tipo de conexión necesaria (legacy), sufijo de login (`+ct`), exportación por archivo |

### 10.3 Diferencias reales entre los fabricantes soportados

| Aspecto | MikroTik RouterOS | ZTE ZXA10 C300 |
|---|---|---|
| Prompt | `[usuario@nombre] >` | `ZXAN#` / `ZXAN(config)#` |
| Config | `/export` (o archivo `.rsc`) | `show running-config` |
| Paginación | `without-paging` en `print`; consola simple con `+ct` | `terminal length 0` previo |
| Eco de consola | Redibuja el prompt carácter a carácter (se limpia) | Prompt pegado al final (se limpia) |
| Errores | Texto libre | `%Error 2020x: …` |
| Modo de configuración | No aplica | Hay que entrar con `configure terminal` antes de cada operación |
| Conexión SSH | paramiko | `ssh.exe` + consola virtual (firmware viejo) |

### 10.4 Cómo se agrega un fabricante nuevo

1. Crear `devices/<marca>.py` con una subclase de `Device` que implemente `running_config_command()` y declare `name`, `vendor`, `category`, `capabilities`.
2. Opcionales según la marca: `prepare_commands`, `is_output_complete` + `HAS_PROMPT_DETECTION`, `clean_output`, `is_error_output`, `collection_commands` + `parse_section`/`postprocess`, `detect_model`.
3. Registrarlo en `DEVICE_TYPES`.

La interfaz ofrece el nuevo tipo **automáticamente** dentro de su categoría. Si la categoría es nueva (no `router`/`olt`), además hace falta un panel (`CategoryPanel`), una entrada de navegación y una carpeta en `CATEGORY_FOLDERS`. Si el equipo necesita un transporte especial, hay que tocar `ConnectionManager._build_connection` y `batch/runner._default_connection_factory` (punto de acoplamiento señalado en §5.3).

**Valoración de escalabilidad del diseño:** agregar una marca «simple» (solo CLI con prompt estándar) son unas decenas de líneas y no toca ninguna otra capa; las marcas con particularidades de transporte exigen modificaciones en dos fábricas de conexión.

---

## 11. Automatización

### 11.1 Qué automatiza

- Descarga de configuración de **uno o varios** equipos (el motor es el mismo; `len(hosts)` decide).
- Extracción YAML por lote.
- Recordado de equipos exitosos y modelo detectado.
- En la OLT: secuencias completas de comandos (autenticación, perfiles, activación) y descubrimiento de datos para completar formularios.

### 11.2 Motor de lote (`batch/runner.py`)

```
download_configs(hosts, cfg, ...)
   ThreadPoolExecutor(max_workers = cfg.max_workers)     ← 1–20 desde la interfaz (5 por defecto)
       one(host)  por cada host:
           ¿cancelado?  → HostResult "Cancelado"
           conectar (SshLegacy / Ssh / Telnet según tipo y protocolo)
           (Telnet) login · pausa 0,3 s
           create_device(tipo, conn) · detectar modelo (info_command)
           _drain(conn)                      ← evita contaminar la captura real
           salida config/both → _capture() → save_config   (bajo save_lock)
           salida yaml/both   → collect_device_facts → save_yaml
           finally: conn.close()
   as_completed → on_result / on_progress (la interfaz los reencola con after())
   resultados reordenados según el orden original de los hosts
```

### 11.3 Manejo de errores individuales

Cada `one()` atrapa `TerminalError` (guarda `user_message` y `detail`) y cualquier otra excepción («Error inesperado») dentro de su propio `try`: **un equipo que falla no detiene a los demás**. La conexión se cierra siempre (`finally`). Un equipo que no responde termina por los timeouts de conexión/lectura y figura como ERROR con su tiempo.

### 11.4 Concurrencia

- **Un hilo por equipo en vuelo, una conexión por hilo**; no se comparten conexiones entre hilos.
- Región compartida protegida: `save_lock` al escribir archivos (evita colisiones de nombre entre hilos).
- Cancelación: `threading.Event`; se consulta **al iniciar** cada equipo. Los equipos ya en curso terminan; los no iniciados quedan «Cancelado».
- **No hay reintentos, backoff ni limitación de velocidad** (NO IMPLEMENTADO ACTUALMENTE).

### 11.5 Resultados

Un archivo por equipo y por formato; tabla de resultados en pantalla; mensaje final con totales (equipos, exitosos, con error) y carpeta destino; log con una línea por equipo (`descarga masiva: <host> OK -> <archivo> (<seg>s)` o `ERROR`).

---

## 12. Backups y gestión de configuraciones

### 12.1 Cómo se obtiene una configuración

| Equipo | Vía principal | Respaldo |
|---|---|---|
| MikroTik por SSH | `/export file=netops-<fecha>` → SFTP del `.rsc` → `/file remove` | Lectura del texto de `/export` en la terminal |
| MikroTik por Telnet | Texto de `/export` en la terminal | — |
| ZTE OLT | `terminal length 0` + `show running-config` (terminal) | — |
| Genérico | `show running-config` (terminal) | — |

La vía por archivo (**IMPLEMENTADO, sin verificación contra equipo real**) obtiene los bytes exactos del archivo y evita el eco de consola, el banner y el paginado. Requiere que el usuario del MikroTik tenga permiso `ftp` (necesario para SFTP). Si falla cualquier paso (sin SFTP, sin permiso, rechazo del comando, archivo que no aparece tras 8 intentos, archivo vacío), el sistema **vuelve solo** a la captura por terminal; el archivo temporal se borra del equipo aunque la descarga falle.

### 12.2 Cómo se guarda

- **Formato:** `.txt` (texto de la configuración) y/o `.yaml` (estructurado, con `raw` y `errors`).
- **Nombre:** `<host sanitizado>_AAAA-MM-DD_HH-MM-SS.<ext>`; si existe, `_1`, `_2`… (nunca se sobrescribe).
- **Ubicación:** `Escritorio/Backups/<Routers|OLT|Otros>/<fabricante>/<host>/`. La raíz se puede cambiar en cada descarga; el cambio vale solo mientras la aplicación está abierta.
- **Distinción entre equipos:** carpeta por host + host en el nombre del archivo.

### 12.3 Recuperación

El texto de MikroTik es el formato de `/export`, reimportable con `/import file=…` luego de subirlo al router (**la reimportación no está automatizada**). Para la OLT, el `.txt` sirve de referencia/auditoría; no hay función de restauración (NO IMPLEMENTADO ACTUALMENTE).

### 12.4 Ventajas y limitaciones

**Ventajas:** nombres y carpetas predecibles, no destructivo, vía por archivo robusta frente al ruido de consola, YAML con trazabilidad (`raw`, `errors`).
**Limitaciones:** archivos en texto plano que pueden contener secretos (p. ej. claves WiFi o usuarios en una exportación de MikroTik); sin versionado ni comparación de versiones; sin retención ni limpieza; sin firma/hash de integridad; sin cifrado.

---

## 13. Interfaz gráfica

### 13.1 Ventanas y componentes

| Ventana / panel | Contenido |
|---|---|
| **MainWindow** («NETWORK ADMIN») | Encabezado con reloj; barra lateral `ROUTERS` · `OLT` · `LOGS` · `ACERCA DE` |
| **Panel Routers / OLT** | Inventario (selección múltiple), alta de equipo, «Descargar configuraciones» (formulario, resultados, progreso, cancelar, abrir carpeta, destino) |
| **TerminalWindow** | Conexión (colapsable), terminal con menú contextual, línea de comando, acciones y barra de estado |
| **OltProvisioningDialog** | Pestañas ONU · PERFILES · ACTIVAR SERVICIO (Internet / Modo LAN) · USUARIOS OLT + panel de resultado |
| **LOGS** | Últimas 500 líneas del log, abrir carpeta, refrescar |
| **ACERCA DE** | Descripción del proyecto |

Indicadores de estado: `StatusIndicator` (punto + texto: OFFLINE/CONNECTING/ONLINE/ERROR) y barra de estado; mensajes de error con `messagebox`; operaciones destructivas piden confirmación (quitar ONU, eliminar usuario, activar Internet).

### 13.2 Conexión con la lógica

- La interfaz **no abre sockets ni escribe archivos de equipos**: delega en `ConnectionManager`, `BackupManager`, `download_configs`, `collect_device_facts` y los drivers.
- Toda operación larga corre en **hilos** (`threading.Thread`, daemon) y regresa a Tk con `after(0, …)`; los botones se deshabilitan mientras hay una operación activa (`_busy`/`_capture_busy`).

### 13.3 Grado de separación interfaz / lógica (evaluación)

**Bien separado:** protocolos, archivos, comandos por fabricante, parsing.
**Acoplamientos reales encontrados:**
- `OltProvisioningDialog._onu_interface_from` arma `gpon-onu_…:N` a partir de `gpon-olt_…` (conocimiento de la nomenclatura de la OLT dentro de la interfaz).
- Las reglas de validación y el armado de resúmenes de `_on_activate_broadband` viven en la interfaz.
- `CategoryPanel._row_done` decide cómo recordar equipos tras una descarga.
- `ConnectionManager` (capa de conexión) importa drivers concretos para elegir el transporte.
No impide el uso, pero dificulta probar esas reglas sin la interfaz: **no hay pruebas automáticas de la capa gráfica**.

---

## 14. Seguridad

### 14.1 Buenas prácticas actuales (verificadas en el código)

- Contraseñas **solo en memoria**; la conexión descarta la suya al cerrar; ninguna se persiste (inventario sin contraseñas).
- Sin shell: la conexión legacy invoca `ssh` con lista de argumentos (no por `shell=True`); la contraseña **no** se pasa por argv.
- Host keys SSH: `RejectPolicy` por defecto; TOFU solo si el operador lo activa explícitamente (con `WARNING`).
- `allow_agent=False`, `look_for_keys=False`: no usa claves ni agentes del usuario por accidente.
- Validación de host/puerto antes de conectar; nombres de archivo y carpetas saneados (sin recorridos de ruta).
- Escritura atómica del inventario (archivo temporal + reemplazo).
- Confirmación explícita antes de acciones de configuración riesgosas.

### 14.2 Riesgos encontrados

| # | Riesgo | Evidencia | Severidad |
|---|---|---|---|
| 1 | **(CORREGIDO el 2026-10-05)** El log podía contener contraseñas de la OLT en claro: `add_user` envía `username <u> password <p> privilege <n>`, el comando se registra a nivel INFO (`comando ejecutado: …`) y el filtro solo enmascaraba `password=…`, `passwd …`, `secret …`. Se amplió el filtro y se agregó `tests/test_logging_setup.py`. **Los logs generados antes de la corrección pueden conservar contraseñas:** conviene borrar `~/.network_terminal/logs/`. | `core/logging_setup.py`, `connection/manager.py` (`_collect`) | Era media-alta; hoy resuelto para las formas cubiertas |
| 2 | Telnet sin cifrado | `telnet_client.py` | Inherente al protocolo |
| 3 | Criptografía obsoleta en la conexión legacy (DSA, SHA-1, CBC, DH group1) | `ssh_legacy_client.py` | Requerida por el equipo |
| 4 | Backups en texto plano en el Escritorio, con permisos por defecto; pueden incluir secretos | `backup/manager.py` | Media |
| 5 | La contraseña sigue en memoria tras desconectar: `TerminalWindow._last_connect_params` conserva el `ConnectionParams` completo y el campo de la interfaz mantiene el texto | `terminal_window.py` | Baja |
| 6 | Parámetros de comando sin validación/escape (nombres de perfil, SN, usuarios se interpolan en f-strings). Un valor con salto de línea se enviaría como comandos separados. Es un operador autenticado y los campos son `Entry` de una línea; **no se pudo verificar** si un pegado puede introducir saltos | `zte_olt.py` | Baja |
| 7 | TOFU: el primer contacto no se autentica | `ssh_client.py` | Baja (opt-in) |
| 8 | El prototipo `red3.py.txt` contiene **credenciales fijas** en el código fuente | `../red3.py.txt` | Legado, fuera del paquete |
| 9 | Un `devices.json`/YAML de ejemplo de producción está dentro de la carpeta del proyecto | `10.99.99.2_….yaml` | Higiene |

### 14.3 Cómo podrían solucionarse (propuestas)

1. **(HECHO el 2026-10-05) — riesgo 1:** se amplió `SecretRedactingFilter` (`password=…`, `password <valor>`, `passwd`, `secret`). **MEJORA FUTURA / PROPUESTA:** además, no registrar los comandos que contienen credenciales (marcarlos como sensibles en el driver), para no depender de patrones de texto.
2. Cifrar o proteger los backups (p. ej. carpeta con permisos restringidos, o aviso al guardar) y no versionar archivos de ejemplo reales.
3. Limpiar `_last_connect_params.password` al desconectar.
4. Validar con lista blanca (`[A-Za-z0-9._:/-]`) los valores que se interpolan en comandos.
5. Restringir Telnet y la OLT legacy a una VLAN de gestión.

### 14.4 Dependencias y entorno

`requirements.txt` fija `paramiko>=3.4,<4`, pero el entorno de desarrollo tenía instalado `paramiko 4.0.0` (la restricción no se aplicó; no se modificó el entorno). `PyYAML`, que la exportación a YAML necesita, **se agregó a `requirements.txt` el 2026-10-05** (el código ya degradaba con un mensaje claro si faltaba).


---

## 15. Problemas y dificultades durante el desarrollo

> **Honestidad sobre la evidencia.** No hay historial Git. Cada problema indica su evidencia: **[CÓDIGO]** si hay un comentario/docstring que lo documenta y es verificable hoy; **[SESIÓN]** si se reconstruye de la sesión de desarrollo asistida (conversación con capturas y salidas reales aportadas por el operador). Donde solo hay una de las dos, se dice. No se reconstruyen problemas sin ninguna evidencia.

Formato: **PROBLEMA → CAUSA → IMPACTO → INVESTIGACIÓN → SOLUCIÓN → RESULTADO → APRENDIZAJE**.

### 15.1 La «configuración» descargada del MikroTik era el banner de login

- **Problema:** el archivo guardado contenía el banner de RouterOS y el aviso «(21 messages not shown)» con eventos de login fallido en lugar de la configuración. **[SESIÓN]**
- **Causa (diagnóstico a partir del archivo capturado; no se midió el tráfico del equipo):** `ConnectionManager._drain_until_quiet` daba el canal por «limpio» tras 0,3 s de silencio; el aviso de seguridad de RouterOS llegaría en ráfagas con pausas más largas, y su cola se leía como si fuera la respuesta de `/export`. La corrección eliminó el síntoma en el equipo real.
- **Impacto:** backups inútiles que parecían correctos (tenían contenido).
- **Investigación:** análisis del archivo capturado; se identificó el patrón de pausa dentro del banner.
- **Solución:** cuando el driver reconoce su prompt, el drenaje exige verlo en reposo (`done_check`, tope de 10 s) y solo aplica ese criterio si llegó algún dato (si el canal ya está callado no espera de más). **[CÓDIGO]** docstring de `_drain_until_quiet`; prueba `test_mikrotik_prompt_completion` (banner con pausa interna).
- **Resultado:** la prueba reproduce el fallo sin la corrección y pasa con ella.
- **Aprendizaje:** «silencio» no es fin de respuesta; conviene una señal positiva (el prompt).

### 15.2 Eco carácter a carácter dentro del backup

- **Problema:** el texto guardado empezaba con líneas como `[admin@MikroTik] > /expor[Kt`. **[SESIÓN]**
- **Causa:** RouterOS redibuja el prompt con cada tecla; el sufijo `+ct` no siempre lo desactiva (lo dice el docstring de `test_mikrotik_prompt_completion`). **[CÓDIGO]**
- **Solución:** gancho `Device.clean_output`; en MikroTik elimina `\x1b[K` y toda línea que empiece con el prompt. Se aplica en `capture_config`, en el lote y en el YAML.
- **Resultado:** backup limpio (solo configuración).
- **Aprendizaje:** el texto de una consola interactiva no es un archivo: hay que sanearlo.

### 15.3 Contaminación entre comandos consecutivos en el lote

- **Problema:** al agregar la detección de modelo (segundo comando por conexión) la captura de configuración devolvía vacío o salida mezclada. **[CÓDIGO]** (docstring de `_drain` en `runner.py`: «Antes de agregar la detección de modelo, este motor solo mandaba UN comando por conexión»).
- **Causa:** restos del primer comando llegaban durante el segundo.
- **Solución:** `_drain(conn)` entre ambos comandos; prueba con una conexión de goteo (`TrickleConnection` en `tests/test_bulk.py`) que falla sin la corrección.
- **Aprendizaje:** una regresión nace de cambiar un supuesto implícito (1 comando por sesión).

### 15.4 «Invalid input detected» en la OLT

- **Problema:** `%Error 20200: Invalid input detected` al autenticar una ONU. **[SESIÓN]**; documentado en `_enter_config_mode`. **[CÓDIGO]**
- **Causa:** los comandos de configuración se enviaban desde el modo EXEC (`ZXAN#`).
- **Solución:** `_enter_config_mode` (`end` + `configure terminal`) al inicio de **todos** los métodos de configuración, y `end` al final.
- **Aprendizaje:** el estado de la sesión (modo del CLI) es parte del contrato de cada operación.

### 15.5 El manual PDF correspondía a otro firmware

- **Problema:** la activación de Internet, escrita desde el manual V2.0.0 (2013), no funcionaba. **[CÓDIGO]** docstring de `activate_broadband_service`.
- **Causa:** el manual describe otro dialecto: tocaba el puerto de uplink, usaba `service HSI gemport … cos …` y `pri` en `vlan port`; el equipo real exige `sn-bind enable sn`, `switchport mode hybrid vport`, `service <id> gemport … vlan …` y (para router) `wan-ip`, que el manual no menciona.
- **Investigación:** el operador aportó una secuencia probada (`c300 commands.txt`).
- **Solución:** se reescribió el método desde esa evidencia; también aparecieron comandos nuevos (`profile traffic`, `no onu`).
- **Resultado:** secuencia confirmada contra el equipo real.
- **Aprendizaje:** **la evidencia del equipo real prima sobre la documentación**. Los métodos de perfiles IP/VLAN y usuarios siguen basados en el manual y están marcados como no confirmados (§7.3.1).

### 15.6 Cada comando de la OLT tardaba 8 s

- **Problema:** «Activar Internet» tardaba cerca de 2 minutos. **[CÓDIGO]** comentario sobre `_PROMPT_RE` en `zte_olt.py` (describe el efecto: «>1 min»).
- **Causa:** sin reconocimiento de prompt, cada uno de los ~14 comandos esperaba el silencio completo (`quiet_after = 8 s`).
- **Solución:** `HAS_PROMPT_DETECTION` y `is_output_complete` para `ZXAN…#`.
- **Resultado:** el atajo corta apenas reaparece el prompt (la prueba verifica < 2 s).
- **Limitación conocida:** si el equipo cambia su nombre de host, el atajo no aplica y vuelve a ser lento (pero correcto).

### 15.7 SSH imposible hacia la OLT con firmware viejo

- **Problema:** conectar por SSH a la OLT no funcionaba desde la aplicación. **[CÓDIGO]** docstring de `ssh_legacy_client.py`.
- **Causa:** la OLT solo ofrece host key `ssh-dss` y algoritmos antiguos; `paramiko` 4 eliminó `DSSKey` (no existe la clase, `from_type_string('ssh-dss')` lanza `UnknownKeyType`), así que ninguna configuración lo habilita. Además, el `ssh` de Git que aparece primero en el `PATH` tampoco trae DSA.
- **Investigación:** se inspeccionaron las listas de algoritmos de paramiko y de los `ssh.exe` instalados; se comprobó que el de `System32\OpenSSH` sí negocia, y que la OLT (10.99.99.2) devuelve host key DSA.
- **Solución:** `SshLegacyConnection` (`ssh.exe` + `pywinpty`).
- **Aprendizaje:** una librería moderna puede ser incompatible con equipos viejos; a veces la salida es delegar en el binario del sistema.

### 15.8 Parseos y salidas de la OLT que no coincidían con la realidad

| Problema | Causa | Solución | Evidencia |
|---|---|---|---|
| `list tipos` mostraba basura | Se tomaba la primera palabra de cada línea (`Description:`, `Max…`) | `_ONU_TYPE_NAME_RE` sobre la línea `ONU type name:` | [CÓDIGO] comentario en `zte_olt.py` |
| Faltaban los tipos de ONU personalizados | `show onu-type gpon` solo lista los de fábrica | Fusionar con las líneas `onu-type <n> gpon …` de la running-config | [CÓDIGO] |
| La sesión se «trababa» en `--More--` | `terminal length 0` se enviaba solo antes de la running-config | Enviarlo antes de **toda** consulta que pueda paginar | [CÓDIGO] docstring de `list_onu_types` |
| El YAML de la OLT salía como una línea con `\r\n` y el prompt pegado; los comandos rechazados (`%Error 20203`) se guardaban como datos | No se normalizaba el texto ni se detectaban errores del equipo | `normalize_text`, `is_error_output`, sección `errors`, estilo de bloque en YAML | [SESIÓN]; pruebas en `test_facts.py` |
| El índice de una ONU «sin autenticar» no coincide con el ID que recibirá | La OLT usa otra numeración para ese listado | Se sugiere el próximo ID libre real y no se informa el índice como ID | [SESIÓN] |

### 15.9 Problemas de interfaz

| Problema | Causa | Solución | Evidencia |
|---|---|---|---|
| Casillas de verificación ilegibles | En Windows el indicador de `ttk.Checkbutton` ignora el estilo | Widgets clásicos `tk.Checkbutton`/`tk.Radiobutton` temáticos (`CyberCheckbutton`) | [CÓDIGO] docstring de `widgets.py` («confirmado con captura de pantalla real») |
| Pestañas ilegibles | `ttk.Notebook` usa los colores claros nativos | Estilos `TNotebook`/`TNotebook.Tab` en `theme.py` | [CÓDIGO] comentario |
| Formularios mal proporcionados | Scroll dentro de scroll no calcula bien su alto | Un único `ScrollableFrame` general en el asistente OLT | [CÓDIGO] comentario en `_scrollable_tab` |
| Terminal incómoda | El panel de conexión ocupaba espacio fijo | Panel colapsable al conectar, ventana mayor | [SESIÓN] |

### 15.10 Aprendizajes sobre modo router/bridge y modos de puerto

- La ONU del equipo real terminó actuando como router (red privada propia) con `wan-ip` + `vlan port … tag`; en bridge puro la PC recibe la IP del proveedor. Con `vlan port … mode transparent` + `wan-ip`, la PC conectada **no recibió IP**. **[SESIÓN]** Resultado: la interfaz tiene un selector explícito Router/Bridge (en Bridge nunca se envía `wan-ip`) y `transparent` quedó marcado como no confirmado.
- Una explicación inicial (el puerto en `tag` «hacía bridge» y el `wan-ip` sería solo una IP de gestión) **no se sostuvo** frente a la prueba; se documenta aquí porque la causa de fondo del intervalo observado antes de que la ONU se comporte como router **sigue siendo una hipótesis**.

### 15.11 Condición de carrera en la conexión legacy

El hilo lector de `SshLegacyConnection` leía `self._proc` mientras `close()` lo ponía en `None` desde otro hilo (`AttributeError` tras las pruebas). **[SESIÓN]** Solución: el hilo toma una referencia local al proceso (`proc = self._proc`).

---

## 16. Evolución del proyecto

> Reconstrucción con evidencia indirecta (marcas de fecha de archivos, comentarios, README, sesión de desarrollo). **No hay Git**; las fechas de la columna «Evidencia» son las de modificación de los archivos o las observadas en la sesión; los eventos de la sesión sin fecha exacta se marcan con «~».

### 16.1 Línea de tiempo técnica

| Fecha (aprox.) | Hito | Evidencia |
|---|---|---|
| 2026-09-07 | **Prototipo `red3`**: ventana CustomTkinter + **Netmiko**, IP y credenciales fijas, extrae YAML de una OLT y un MikroTik; botones de gestión sin acción | `red3.py.txt`, `red3.exe` (~19 MB) |
| 2026-09-08 | Nace el paquete `network_terminal` (`__init__`, `__main__`, `app.py`): terminal SSH/Telnet «estilo PuTTY», pensada como módulo de conexión | marcas de fecha; docstring de `__init__.py` |
| 2026-09 (hasta 16) | Etapas incrementales: capas `connection/devices/backup/batch`, YAML estructurado, descarga masiva, rediseño visual («Etapa 3»), **monitor de tráfico** (API de RouterOS, SNMP), drivers Cisco/Dell/HP, inventario de equipos, panel de Settings | `README.md` (16-sep), comentarios con «Etapa 3/8» |
| 2026-09-16/17 | Ícono de la aplicación; se incorpora el manual PDF de la OLT | `assets/`, `…Manual (CLI).pdf` |
| 2026-09-20 | Se reemplaza la activación de Internet basada en el manual por la **secuencia probada en el equipo real** | `c300 commands.txt` (20-sep) |
| 2026-09-24 | Se detectan los problemas de captura del MikroTik (banner/eco) y se generan los primeros YAML reales de la OLT | archivo YAML (24-sep); §15.1–15.2 |
| ~2026-09-29 | **Recorte deliberado del alcance (decisión de producto):** se eliminan voz y multicast de la OLT, los switches (Cisco/Dell/HP), el monitor de tráfico (con la API de RouterOS y el cliente SNMP) | sesión de desarrollo |
| 2026-10-01 | **SSH a la OLT con firmware viejo** vía `ssh.exe` + `pywinpty` | `requirements.txt` (01-oct) |
| ~2026-10-05 | Exportación MikroTik por archivo + SFTP; YAML legible; limpieza de interfaz (se quitan Settings y Backups; la carpeta se elige al descargar; se agrega «Acerca de»); listado de ONU, detección automática de puertos PON, verificación posterior a la activación y selector Router/Bridge | sesión; §7–§13 |

### 16.2 Cómo cambió la arquitectura

- **De script a paquete por capas:** el prototipo mezclaba interfaz, conexión (Netmiko) y archivo en una clase; el paquete separa `ui/`, `connection/`, `devices/`, `backup/`, `batch/`, `core/`.
- **De Netmiko a paramiko + cliente Telnet propio:** el prototipo dependía de Netmiko (`device_type='zte_zxros'`, `'mikrotik_routeros'`); `requirements.txt` hoy solo lista `paramiko` (+ `pywinpty`, PyYAML sin listar). **El motivo exacto del cambio no puede determinarse con certeza desde el código**; el README solo expresa la preferencia por minimizar dependencias (por ejemplo, el Telnet propio por la desaparición de `telnetlib` en Python 3.13).
- **De «un comando por sesión» a conversación con candado y detección de prompt:** surgió de los problemas §15.1–15.3.
- **De «conocimiento del manual» a «conocimiento verificado en el equipo»** (§15.5).

### 16.3 Funcionalidades descartadas

| Funcionalidad | Estado | Motivo |
|---|---|---|
| Monitor de tráfico (API RouterOS, SNMP, gráfico) | Eliminado | Decisión de producto: la aplicación no se usará para ver tráfico |
| Switches (Cisco/Dell/HP) | Eliminado | No se administrarán switches |
| Voz (SIP/H.248) y multicast/IPTV en la OLT | Eliminado | No se ofrecerá el servicio |
| Pestañas Settings y Backups | Eliminadas | Quedaban casi vacías; la carpeta de destino se eligió al momento de descargar |
| Prototipo `red3` | Reemplazado | Superado por el paquete |

> **Código antiguo y comentarios obsoletos que quedan:** comentarios de `core/saved_devices.py` que citan el monitor; `ui/widgets.MetricCard` (sin usos); parámetro `vendor_filter` de `CategoryPanel` (siempre `False` hoy); métodos `Device.get_*` sin llamadores (§7.3). El `README.md`, que también describía lo eliminado, se reescribió el 2026-10-05.

---

## 17. Decisiones de diseño

| Decisión | Alternativas | Por qué es conveniente | Desventajas |
|---|---|---|---|
| **Python + Tkinter/ttk** | Qt, web, Electron | Sin dependencias para la GUI; un solo lenguaje; distribución simple | Aspecto y herramientas de UI limitados; sin pruebas de GUI automáticas |
| **Capas + un driver por fabricante** | Condicionales por marca en un único módulo | El conocimiento de cada marca queda aislado; agregar una marca no toca otras capas | Acople residual en las fábricas de conexión |
| **Sesión interactiva (`invoke_shell`) y no `exec_command`** | Ejecutar comando a comando sin shell | Las CLI de red mantienen modo/estado (p. ej. `configure terminal`) | Hay que detectar fin de comando y limpiar eco |
| **Detectar el prompt (con silencio como red de seguridad)** | Esperas fijas | Rápido y robusto ante respuestas lentas | Depende de reconocer el prompt (p. ej. `ZXAN`) |
| **Hilo lector + cola + candado de capturas** | Lectura sincrónica en el hilo de la GUI | La GUI no se bloquea y no se mezclan respuestas | Más complejidad de concurrencia |
| **Telnet propio con IAC mínima** | `telnetlib`, librería externa | `telnetlib` ya no existe; sin dependencia | Solo modo línea, sin negociación avanzada |
| **`ssh.exe` + `pywinpty` para la OLT** | Parchear paramiko, otra librería, plink | Funciona hoy con el equipo real; la contraseña no va en argv | Solo Windows; depende de un binario externo |
| **Hilos (`ThreadPoolExecutor`) para el lote** | `asyncio`, procesos | E/S de red con bibliotecas bloqueantes; simple | Tope práctico de decenas de hilos |
| **Archivos locales (JSON/TXT/YAML), sin base de datos** | SQLite, base de red | Cero administración; inspeccionable a mano | Sin consultas, historial ni concurrencia entre usuarios |
| **Nunca persistir contraseñas** | Gestor de credenciales | Reduce la superficie de ataque | El operador reescribe credenciales cada vez |
| **Carpeta de backups solo en memoria de sesión** | Archivo de ajustes | Sin archivo extra; valor por defecto sensato (Escritorio) | No recuerda la elección entre sesiones |
| **Exportación por archivo con respaldo por terminal (MikroTik)** | Solo terminal / solo SFTP | Bytes exactos cuando se puede; nunca peor que antes | Dos caminos que probar; la vía nueva sin verificar en equipo real |
| **Inyectar `run(comando)` al driver de la OLT** | Que el driver abra su conexión | Reusa la sesión y el candado de la terminal; testeable con un doble | El driver depende de que `run` ya tenga las garantías (candado, prompt) |
| **Confirmación explícita antes de activar** | Ejecutar directo | Un alta incorrecta deja a un cliente sin servicio | Un clic más |
| **Reglas «no inventar»** (modelo vacío = «-», estado de ONU = último campo) | Valores supuestos | Evita mostrar datos falsos | Menos información cuando el equipo no está soportado |

---

## 18. Ventajas del sistema

| Ventaja | Por qué lo es (técnicamente) |
|---|---|
| **Ahorro de tiempo** | Una activación de ~14 comandos o una descarga de N equipos pasa a un clic; en lote, el tiempo crece como ⌈N/W⌉·t (W hilos) y no como N·t. |
| **Reducción de errores humanos** | Secuencias fijas, modo de configuración forzado, validación de entradas, próximo `service-port`/ID de ONU calculado y no recordado, confirmación previa. |
| **Repetibilidad** | El mismo flujo produce los mismos comandos y archivos; las pruebas fijan ese comportamiento (197 tests). |
| **Trazabilidad** | Nombres con host+fecha/hora, carpetas por categoría/fabricante, YAML con `raw` y `errors`, log rotativo. |
| **Aislamiento de fallas** | En el lote un equipo caído no detiene a los demás y cada resultado queda registrado. |
| **Centralización** | Un solo lugar para terminal, backup, YAML y alta de ONU. |
| **Escalabilidad de diseño** | Agregar una marca simple = una clase; el resto de las capas no cambia. |
| **Seguridad por diseño básico** | Sin contraseñas en disco; host keys rechazadas por defecto; sin shell. |
| **Robustez frente a consolas reales** | Limpieza de eco, drenaje del canal, detección de errores del equipo y respaldo cuando una vía alternativa falla. |
| **Verificación inmediata** | Tras activar Internet muestra el estado y la configuración que quedó aplicada. |

---

## 19. Desventajas y limitaciones

- **Dependencia de comandos específicos de cada fabricante:** cualquier cambio de firmware puede romper un comando o un parseo (ya ocurrió con el manual de 2013). Varias secuencias de la OLT no tienen confirmación en equipo real.
- **Soporte limitado de equipos y de parseo estructurado:** solo MikroTik y ZTE OLT; la OLT casi no se estructura (solo `show ip interface brief`).
- **Seguridad:** Telnet en claro; criptografía obsoleta hacia la OLT; log que puede contener contraseñas de usuarios de la OLT (§14.2); backups sin cifrar.
- **Plataforma:** la conexión a la OLT con firmware viejo requiere Windows (`pywinpty` + `ssh.exe`).
- **Terminal «por líneas»:** sin emulación TTY (no sirve para editores o paginadores interactivos), una sesión por ventana.
- **Reconocimiento del prompt de la OLT atado al nombre `ZXAN`.**
- **Credenciales únicas por lote:** todos los equipos de una descarga usan el mismo usuario/contraseña; sin reintentos ni programación.
- **Sin pruebas de interfaz gráfica** ni contra equipos reales de forma automática: las pruebas usan dobles; los comportamientos «confirmados» provienen de pruebas manuales.
- **Mantenimiento:** código sin uso y comentarios que mencionan funciones eliminadas; la capa de conexión conoce drivers concretos; versión de `paramiko` del entorno distinta de la fijada en `requirements.txt`.
- **Sin autodetección** del fabricante ni de la versión de firmware.

---

## 20. Escalabilidad

> Todo lo siguiente son **estimaciones razonadas a partir del diseño**, no mediciones. Modelo: `T ≈ ⌈N / W⌉ · t_host`, con `W` = hilos (1–20 en la interfaz; el motor no impone tope) y `t_host` del orden de unos segundos a algunas decenas (conexión + 0,3 s de asentamiento + detección de modelo + vaciado de canal + captura).

| Equipos | Qué ocurre | Cuellos de botella probables |
|---|---|---|
| **5** | Una sola tanda (W=5); segundos a poco más de un minuto | Ninguno relevante |
| **50** | ~10 tandas con W=5; minutos | Latencia y consolas lentas; `quiet_after` de 8 s en equipos sin detección de prompt |
| **500** | ~100 tandas con W=5 (o 25 con W=20); decenas de minutos | Credencial única para todos; sin reintentos (una caída transitoria exige repetir); tabla de resultados y log crecen |
| **5.000** | Inviable operativamente con este diseño | Ver abajo |

Componentes a vigilar:
- **Conexiones simultáneas:** un hilo del SO y un socket por equipo en vuelo; el tope de 20 es práctico (la interfaz lo limita), no técnico.
- **CPU:** baja (E/S de red y parseo de texto); **RAM:** cada configuración se mantiene completa en memoria durante su guardado; sin problemas hasta cientos de equipos.
- **Almacenamiento:** un archivo por equipo y formato; sin retención ni deduplicación.
- **Logs:** rotativos (1 MB × 5): con miles de equipos las líneas más viejas se pierden pronto.
- **Inventario:** `remember_device` carga y reescribe **todo** `devices.json` por cada equipo exitoso (coste O(N) por alta, O(N²) en total) y toma un candado global.
- **Arquitectura:** la interfaz es de un solo proceso; no hay cola de trabajos, ni persistencia del estado de una tanda, ni credenciales por equipo.

**Qué habría que cambiar para escalar (MEJORA FUTURA / PROPUESTA):** cola de trabajos persistente con reintentos y backoff, credenciales por equipo desde un almacén seguro, base de datos para inventario/resultados, motor de ejecución separado de la interfaz (servicio/CLI), límite de tasa por segmento de red, y escritura incremental del inventario.

---

## 21. Posibles mejoras futuras (**MEJORA FUTURA / PROPUESTA**)

> Todo lo de esta sección **no existe actualmente**.

### Corto plazo (cambios acotados)
1. ~~Enmascarar `password <valor>` en el log~~ — **HECHO el 2026-10-05** (§14.3). Pendiente: no registrar comandos con credenciales.
2. ~~Agregar `PyYAML` a `requirements.txt` y reescribir el `README.md`~~ — **HECHO el 2026-10-05**.
3. Eliminar código y comentarios obsoletos (`MetricCard`, `Device.get_*`, `vendor_filter`, menciones al monitor).
4. Confirmar en el equipo real el comando que quita el `wan-ip` (hoy `set_onu_wan_mode` prueba dos candidatos).
5. Limpiar la contraseña en memoria al desconectar; validar con lista blanca los valores que se envían en comandos.
6. Verificar contra un MikroTik real la exportación por archivo + SFTP.
7. Persistir (opcional) la carpeta de backups elegida.

### Mediano plazo (cambios estructurales moderados)
1. **Comparación (diff) entre dos descargas** del mismo equipo y versionado simple de configuraciones.
2. **Reintentos con backoff** y reporte de equipos fallidos para repetir.
3. **Credenciales por equipo** (en memoria o con un gestor del sistema) para lotes heterogéneos.
4. Confirmar y completar los comandos de la OLT hoy basados en el manual (perfiles IP/VLAN, usuarios) y parsear `show gpon onu state` con una captura real.
5. Pruebas de interfaz y pruebas de integración contra equipos de laboratorio.
6. Soporte multiplataforma para la OLT legacy (alternativa a `pywinpty`).

### Largo plazo (cambios de arquitectura)
1. Separar el **motor de ejecución** de la interfaz (servicio/CLI) con cola de trabajos y programación (descargas periódicas).
2. Base de datos para inventario, historial de configuraciones y auditoría; usuarios y roles (RBAC).
3. Otros mecanismos de gestión (SNMP, APIs de fabricante, NETCONF/RESTCONF) si se retoma monitoreo o equipos que los exijan.
4. Autodetección de fabricante y versión de firmware.
5. Descubrimiento automático y alertas.

---

## 22. Comparación con la gestión manual

| Criterio | Manual | Con la aplicación |
|---|---|---|
| **Tiempo** | Proporcional a N·(abrir sesión + comandos + guardar) | Un clic; el lote crece como ⌈N/W⌉ |
| **Cantidad de equipos** | Práctica hasta unos pocos | Decenas a cientos con el mismo flujo |
| **Probabilidad de error** | Alta (modo equivocado, identificador repetido, olvido de `write`, copia con ruido) | Baja: secuencia fija, validaciones, confirmación y verificación posterior |
| **Repetibilidad** | Depende de cada técnico | Idéntica cada vez; fijada por pruebas |
| **Trazabilidad** | Nombres y carpetas ad hoc | Convención host+fecha, carpetas por categoría/fabricante, log |
| **Escalabilidad** | Lineal en horas-persona | Lineal en tiempo de máquina, con paralelismo acotado |
| **Seguridad** | Contraseñas en notas/historial de terminal, backups dispersos | Sin contraseñas en disco; pero backups/logs con riesgos propios (§14) |
| **Facilidad de operación** | Requiere memorizar comandos por marca | Formularios y desplegables con datos descubiertos del equipo |
| **Control fino** | Total | Limitado a lo implementado (la Terminal permite volver a lo manual) |


---

## 23. Casos de uso

> Basados exclusivamente en funciones existentes. La administración de **switches** no figura porque ya no está implementada.

### Caso 1 — Backup de configuración de un router MikroTik
- **Situación:** antes de un cambio en el router de borde, hay que guardar su configuración.
- **Usuario:** técnico de redes.
- **Objetivo:** obtener un archivo limpio y ubicable.
- **Pasos:** ROUTERS → seleccionar el equipo → «TERMINAL» → CONNECT (SSH, tipo `MikroTik`) → **GET CONFIG** → **SAVE BACKUP**.
- **Resultado:** `Escritorio/Backups/Routers/MikroTik/<host>/<host>_AAAA-MM-DD_HH-MM-SS.txt`, sin banner ni eco; el equipo queda en el inventario con su modelo.

### Caso 2 — Backup masivo de varios routers
- **Situación:** auditoría mensual de 40 routers.
- **Objetivo:** bajar todas las configuraciones sin atender equipo por equipo.
- **Pasos:** ROUTERS → «Descargar configuraciones» → pegar las IP (una por línea) o usar «Usar seleccionados» del inventario → usuario/contraseña → concurrencia 5 → salida `.txt` (o «Ambos») → **DESCARGAR**.
- **Resultado:** un archivo por equipo; tabla con OK/ERROR y tiempos; los caídos no frenan al resto; el resumen final indica totales y la carpeta.

### Caso 3 — Alta de un abonado en la OLT (modo router)
- **Situación:** hay una ONU nueva conectada y detectada, sin autenticar.
- **Objetivo:** dejar al cliente navegando con la red privada de la ONU.
- **Pasos:** Terminal → `ZTE OLT` (SSH) → **OLT PROVISIONING…** → pestaña ONU: buscar sin configurar y **autenticar** (ID sugerido) → ACTIVAR SERVICIO → «ACTUALIZAR DESDE OLT» → completar PON PORT, ID de ONU, perfil T-CONT, VLAN, puertos, modo **Router** + perfil VLAN WAN → **ACTIVAR INTERNET** → confirmar.
- **Resultado:** secuencia ejecutada y guardada (`write`); el panel muestra el estado de la ONU y los bloques aplicados.

### Caso 4 — Alta en modo bridge (el cliente usa su propio router)
- **Pasos:** igual al Caso 3, eligiendo **Bridge**; no se envía `wan-ip`.
- **Resultado:** el equipo del cliente recibe la IP del proveedor y hace su propio NAT. *Nota:* el equipo conectado directo al puerto (sin router) recibirá esa IP pública/del ISP.

### Caso 5 — Auditoría estructurada
- **Objetivo:** obtener interfaces/IP/rutas/VLAN/firewall de un MikroTik en un solo archivo.
- **Pasos:** Terminal conectada → **EXTRACT YAML** (o salida «YAML»/«Ambos» en el lote).
- **Resultado:** `.yaml` con secciones, `summary` (gateway por defecto, IPs) y `raw` para trazabilidad. En la OLT, los comandos que el firmware rechaza figuran en `errors`.

### Caso 6 — Revisión del parque de ONU de un puerto PON
- **Pasos:** OLT PROVISIONING → ONU → **DETECTAR PUERTOS** → elegir puerto → **LISTAR ONU**.
- **Resultado:** tabla con ONU autenticadas y su estado y las que esperan autenticación (con SN).

---

## 24. Ejemplo de operación completa: «Activar Internet» en una ONU (modo router)

Datos de ejemplo: puerto `gpon-olt_1/13/4`, ONU id `2`, VLAN 200, perfil T-CONT `plan-600m`, perfil VLAN WAN `HSI-200`, puertos `eth_0/1` y `eth_0/3`.

```
Operador
  │  1. Completa el formulario y pulsa «ACTIVAR INTERNET»
  ▼
ui/olt_provisioning_dialog.py  ·  _on_activate_broadband()
  │  2. Valida (campos obligatorios, enteros, PON PORT con forma gpon-olt_…)
  │  3. Compone la interfaz:  gpon-olt_1/13/4 + id 2  →  gpon-onu_1/13/4:2
  │  4. Reúne puertos (casillas + «otros»); modo Router exige perfil VLAN WAN
  │  5. Muestra resumen y pide confirmación  ──► si responde «No», no se envía nada
  │  6. Lanza un hilo de fondo (_run_bg) para no bloquear la ventana
  ▼
devices/zte_olt.py  ·  ZteOltDevice.activate_broadband_service(..., run=…)
  │  7. _enter_config_mode:  end  →  configure terminal
  │  8. Va armando comandos y llamando run(comando) por cada uno:
  │       interface gpon-onu_1/13/4:2
  │       sn-bind enable sn
  │       tcont 1 name internet profile plan-600m
  │       gemport 1 name internet tcont 1
  │       switchport mode hybrid vport 1
  │       service-port 2 vport 1 user-vlan 200 vlan 200     (service-port = próximo libre)
  │       exit
  │       pon-onu-mng gpon-onu_1/13/4:2
  │       service 1 gemport 1 vlan 200
  │       wan-ip 1 mode dhcp vlan-profile HSI-200 host 1
  │       vlan port eth_0/1 mode tag vlan 200
  │       vlan port eth_0/3 mode tag vlan 200
  │       end  →  write
  ▼
ui/terminal_window.py · _run_on_session  →  ConnectionManager.run_capture(cmd)
  │  9. Toma _capture_lock, pausa el hilo lector, vacía el canal (_drain_until_quiet)
  │ 10. conn.send_line(cmd)  (+ "\r\n")
  ▼
connection/ssh_legacy_client.py · SshLegacyConnection.send  →  PtyProcess.write
  ▼
ssh.exe (consola virtual)  ──SSH (DH group1, DSA, AES-CBC)──►  OLT ZTE ZXA10 C300
  │                                                              │
  │ 11. La OLT ejecuta el comando y responde, terminando con el prompt  ZXAN(config-if)#
  ◄──────────────────────────────────────────────────────────────┘
  │ 12. Hilo lector → cola → _collect acumula; ZteOltDevice.is_output_complete(ZXAN…#)
  │     + 0,4 s de reposo ⇒ el comando terminó (no espera los 8 s de silencio)
  ▼
Retorno: cada run() devuelve su texto; activate_broadband_service lo concatena
  │ 13. onu_applied_summary:  show gpon onu state <puerto>  +  show running-config
  │     (terminal length 0 antes)  → extrae la fila de la ONU 2 y los bloques
  │     "interface gpon-onu_1/13/4:2" y "pon-onu-mng gpon-onu_1/13/4:2"
  ▼
Panel «Resultado»:  [Internet activado — verificación en el equipo:]
                    Estado: …   Configuración aplicada: …
```

**Qué muestra este ejemplo:** (a) la interfaz solo valida y orquesta; (b) el conocimiento de comandos vive en el driver; (c) la sesión y sus garantías (candado, vaciado, prompt) viven en `ConnectionManager`; (d) el transporte se resuelve según el tipo de equipo; (e) **no es transaccional**: si la conexión se corta a mitad de la secuencia, queda aplicada solo una parte y, si no llegó a `write`, la configuración no se guardó en la OLT (no hay reversión automática).

---

## 25. Evaluación técnica del proyecto

| Criterio | Evaluación | Fundamento |
|---|---|---|
| **Arquitectura** | **Buena, con acoplamientos puntuales** | Capas claras (UI → lógica → driver → conexión) y contratos (`Device`, `BaseConnection`). Puntos flojos: `ConnectionManager`/`runner` importan drivers concretos; parte de las reglas de dominio está en la interfaz (§13.3). |
| **Mantenibilidad** | **Media-buena** | 197 pruebas unitarias y docstrings que explican el porqué. Pesan: archivos grandes (`olt_provisioning_dialog.py` ~1000 líneas, `zte_olt.py` ~730), README desactualizado, código sin uso y comentarios que citan funciones eliminadas. |
| **Escalabilidad** | **Limitada por diseño** | Adecuada hasta decenas/cientos de equipos; sin cola, reintentos, credenciales por equipo ni persistencia de estado (§20). |
| **Seguridad** | **Básica y mayormente prudente** | Sin contraseñas en disco, host keys rechazadas por defecto, sin shell, log con enmascarado de secretos (ampliado el 2026-10-05 tras detectar que `password <valor>` no se enmascaraba). Pendientes: backups sin cifrar, Telnet, limpieza de la contraseña en memoria, validación de parámetros de comandos. |
| **Robustez** | **Alta en la captura, media en el login** | Vaciado del canal, detección de prompt, limpieza de eco, detección de rechazos y respaldo ante fallo de la vía por archivo. El login Telnet/SSH-legacy es *best-effort* y no verifica el éxito de la autenticación. Activaciones no transaccionales. |
| **Modularidad** | **Buena** | Un módulo por responsabilidad; la UI se puede reemplazar sin tocar `connection/` ni `devices/`. |
| **Facilidad para agregar fabricantes** | **Buena** | Una clase + registro (§10.4); las marcas con transporte especial exigen tocar dos fábricas. |
| **Facilidad para agregar funciones** | **Media** | Nuevas acciones de la OLT son métodos con `run` inyectado y fáciles de probar; nuevas pantallas implican código de Tkinter sin pruebas automáticas. |
| **Experiencia de usuario** | **Aceptable y orientada al operador** | Formularios con descubrimiento (puertos, perfiles, VLAN), confirmaciones y verificación; terminal por líneas y estética propia. Sin pruebas de usabilidad. |
| **Cobertura de pruebas** | **Parcial** | Fuerte en conexión, drivers, lote, backup, validación; nula en la capa gráfica y sin integración contra equipos reales. |
| **Fidelidad con equipos reales** | **Desigual** | Activación de Internet y varios comandos confirmados; otras secuencias de la OLT siguen el manual de otro firmware. |

---

## 26. Conclusiones

**Qué problema resolvimos.** Convertimos tareas manuales y propensas a error —respaldar configuraciones y dar de alta ONU en una OLT GPON— en flujos guiados, repetibles y con trazabilidad, sobre una base de código por capas.

**Qué logramos implementar.** Terminal SSH/Telnet; descarga de configuraciones individual y en lote con aislamiento de fallas; YAML estructurado; inventario sin contraseñas; aprovisionamiento de ONU con descubrimiento automático y verificación; una conexión SSH especial para un equipo de firmware antiguo; y un conjunto de pruebas de 197 casos.

**Qué aprendimos.**
1. En redes, la verdad está en el equipo real: la documentación de otra versión llevó a un diseño que había que rehacer.
2. Una consola interactiva no es una API: hay que resolver el fin de comando, el eco, el paginado y el estado del CLI.
3. «Silencio» no es fin de respuesta; conviene una señal positiva (el prompt) y un respaldo.
4. Los equipos viejos y las librerías nuevas chocan (DSA en `paramiko` 4); a veces la solución es delegar en el binario del sistema.
5. Recortar alcance a tiempo (monitoreo, switches, voz, multicast) deja un producto más pequeño y más verificable.

**Qué limitaciones quedan.** Dependencia de comandos por fabricante; seguridad por mejorar (backups sin cifrar, Telnet, validación de parámetros); escalabilidad acotada; terminal por líneas; sin pruebas de interfaz ni de integración con equipos.

**Potencial.** La arquitectura permite sumar fabricantes con poco código; el motor de lote puede separarse de la interfaz y crecer hacia programación, versionado y comparación de configuraciones.

**Cómo podría evolucionar.** Ver §21: primero retirar código obsoleto y reforzar seguridad restante, luego versionado/diff y credenciales por equipo, y a largo plazo un motor de ejecución independiente con cola, base de datos y control de acceso.

---

## 27. Guion para una presentación oral (15–30 min)

> Distribución sugerida de tiempo (≈ 25 min): 1 (1) · 2 (2) · 3 (1) · 4 (3) · 5 (1) · 6 (2) · 7 (3) · 8 (2) · 9 (3, demo) · 10–11 (3) · 12 (1) · 13 (1) · 14 (1) · 15 (1).

**1. Introducción**
- *Explicar:* qué es NETWORK ADMIN y para quién (operador de un ISP con routers MikroTik y una OLT ZTE).
- *Conceptos:* CLI, administración remota, automatización de tareas.
- *Mostrar:* ventana principal y su navegación.
- *Pregunta posible:* «¿Es un NMS?» → No: no monitorea ni recolecta continuamente; automatiza tareas puntuales por CLI.

**2. Problema**
- *Explicar:* backups manuales con ruido de consola y altas de ONU de ~14 comandos con identificadores globales.
- *Conceptos:* modos del CLI, `service-port` global, paginación.
- *Mostrar:* `c300 commands.txt` (la secuencia manual).
- *Pregunta:* «¿Por qué no un script?» → Un script no resuelve fin de comando, eco ni estado del CLI de forma robusta ni da formularios guiados.

**3. Objetivos y alcance**
- *Explicar:* objetivos reales y lo que NO hace (§3, §4).
- *Mostrar:* pestaña «Acerca de».
- *Pregunta:* «¿Y switches/monitoreo?» → Se eliminaron por decisión de producto; no están implementados.

**4. Arquitectura**
- *Explicar:* capas UI → lógica → driver → conexión; transversal `core`.
- *Conceptos:* separación de responsabilidades, ABC, inyección de dependencias (`run`).
- *Mostrar:* el árbol de carpetas y el diagrama de §5.
- *Pregunta:* «¿Qué acoplamientos hay?» → Las fábricas de conexión conocen drivers; parte de las reglas está en la interfaz (§13.3).

**5. Tecnologías**
- *Explicar:* Python, Tkinter, paramiko, pywinpty, PyYAML, hilos.
- *Pregunta:* «¿Por qué Telnet propio?» → `telnetlib` no existe en Python 3.13.

**6. Funcionamiento general**
- *Explicar:* flujo de conexión y GET CONFIG (§8.2, §8.4).
- *Mostrar:* conectar a un equipo y obtener la configuración.
- *Pregunta:* «¿Cómo sabe que terminó el comando?» → Prompt reconocido + reposo, con silencio y tope como red de seguridad.

**7. Comunicación con los dispositivos**
- *Explicar:* SSH/Telnet/SFTP, puertos 22/23, autenticación, ssh legacy.
- *Conceptos:* host key, TOFU, kex/cipher/MAC, DSA, ConPTY.
- *Mostrar:* los flags `-oKexAlgorithms…` en `ssh_legacy_client.py`.
- *Pregunta:* «¿Por qué aceptar criptografía obsoleta?» → Lo exige el firmware de la OLT; se limita a ese equipo y se recomienda una red de gestión.

**8. Automatización**
- *Explicar:* descarga en lote, pool de hilos, aislamiento de fallas, cancelación.
- *Mostrar:* descarga de 3–5 equipos con uno caído.
- *Pregunta:* «¿Reintenta?» → No, no está implementado.

**9. Demostración** (en vivo o grabada)
- *Secuencia sugerida:* Terminal → GET CONFIG/SAVE BACKUP → EXTRACT YAML → OLT PROVISIONING (detección de puertos, listar ONU) → Activar Internet (resumen de confirmación y verificación).
- *Evitar:* mostrar contraseñas o datos de clientes reales en pantalla.

**10. Problemas encontrados** — banner en el backup (§15.1), `configure terminal` (§15.4), manual de otro firmware (§15.5), 8 s por comando (§15.6), DSA en paramiko 4 (§15.7).
**11. Soluciones** — prompt-aware drain, `clean_output`, `_enter_config_mode`, evidencia del equipo real, detección de prompt, `ssh.exe` + ConPTY.
- *Pregunta:* «¿Cómo validaron?» → Pruebas con dobles + comprobación manual en el equipo; no hay integración automática.

**12. Seguridad**
- *Explicar:* contraseñas en memoria, host keys, y los riesgos encontrados (§14.2), incluido el log.
- *Pregunta:* «¿Se guardan contraseñas?» → No en disco por diseño; ojo con el log de comandos de alta de usuarios (hallazgo conocido).

**13. Limitaciones** — §19.
**14. Futuras mejoras** — §21 (corto: seguridad/higiene; mediano: diff y credenciales por equipo; largo: motor desacoplado).
**15. Conclusión** — §26.

---

## 28. Preguntas difíciles para la defensa

| # | Pregunta | Respuesta técnica basada en el proyecto |
|---|---|---|
| 1 | ¿Cómo garantizan que un comando terminó antes de enviar el siguiente? | Con `run_capture`/`_collect`: se reconoce el prompt del driver (`is_output_complete`) y se exige 0,4 s de reposo; si no hay prompt reconocible, rige el silencio (`quiet_after`, 8 s en el asistente) y un tope (`overall_timeout`). Además `_drain_until_quiet` vacía el canal antes de enviar. |
| 2 | ¿Qué pasa si dos acciones usan la misma sesión a la vez? | Todas pasan por `_capture_lock` (`send`, `send_line`, `capture_config`, `run_capture`) y el hilo lector se pausa durante las capturas. Así una respuesta no se atribuye a otro comando. |
| 3 | ¿Por qué no `exec_command` en SSH? | Las CLI de red son stateful (modos como `configure terminal`) y muchas no aceptan comandos sueltos; se usa un shell interactivo (`invoke_shell`) y se resuelve el fin de comando. |
| 4 | ¿Cómo manejan la paginación (`--More--`)? | Con `terminal length 0` antes de cualquier consulta que pueda paginar (ZTE) y con `without-paging` en los `print` de MikroTik. Si se omite, la sesión queda atrapada en el paginador. |
| 5 | ¿Por qué Telnet si es inseguro? | Algunos equipos lo exigen. Transmite credenciales en claro: debe usarse en una red de gestión aislada. SSH es la opción por defecto. |
| 6 | ¿Cómo protegen las credenciales? | Solo en memoria (`StringVar` → `ConnectionParams` → atributo privado; se descarta al cerrar), nunca en disco; en la conexión legacy van por la consola virtual, no por argumentos. El log enmascara `password=…` y `password <valor>`; esta última forma se detectó sin cubrir durante la elaboración de este documento y se corrigió (con prueba) el 2026-10-05. |
| 7 | ¿Cómo verifican la identidad del servidor SSH? | `RejectPolicy` por defecto; TOFU opcional que guarda la clave en `known_hosts`. La ruta legacy usa `StrictHostKeyChecking=yes` o `accept-new`. TOFU no protege el primer contacto. |
| 8 | ¿Por qué usan `ssh.exe` para la OLT y no paramiko? | La OLT solo ofrece host key `ssh-dss`; `paramiko` 4 eliminó `DSSKey`, así que no puede negociar. El `ssh.exe` de `System32` sí soporta DSA con las opciones `+`. |
| 9 | ¿Qué riesgo implica DSA/SHA-1/CBC/DH group1? | Algoritmos débiles/obsoletos: confidencialidad e integridad reducidas. Es necesidad del equipo; mitigación: limitarlo a una VLAN de gestión y actualizar el firmware. |
| 10 | ¿Cómo manejan un equipo caído en un lote? | Cada `one()` tiene su propio `try`; el error queda en `HostResult` (mensaje y detalle) y el resto continúa. La conexión se cierra siempre. No hay reintentos. |
| 11 | ¿Qué escalabilidad tiene? | `T ≈ ⌈N/W⌉·t_host`, W ≤ 20 desde la interfaz. Sirve para decenas/cientos; no para miles (sin cola, reintentos, credenciales por equipo; `devices.json` se reescribe completo en cada alta). |
| 12 | ¿Por qué el `service-port` se busca en la running-config? | Es un identificador **global** de la OLT (a diferencia de `tcont`/`gemport`, propios de cada ONU); reusar uno ocupado le pisa el servicio a otro cliente. |
| 13 | ¿Cómo diferencia modo router de bridge en la ONU? | Router: se envía `wan-ip … mode dhcp vlan-profile …`; Bridge: se omite el `wan-ip` y el puerto queda etiquetado a la VLAN. Observado en el equipo real: en router la ONU entregó una red privada propia. La causa de comportamientos intermedios es una hipótesis. |
| 14 | ¿Es transaccional la activación? | No. Son comandos secuenciales; si se corta a mitad queda una configuración parcial y, si no llegó a `write`, sin guardar. No hay rollback automático (solo `remove_onu` quita la autenticación). |
| 15 | ¿Cómo agregan un fabricante? | Subclase de `Device` con `running_config_command` y, si hace falta, prompt/limpieza/errores/comandos de recolección; registrarla en `DEVICE_TYPES`. La UI la ofrece sola. Solo se toca la conexión si el transporte es especial. |
| 16 | ¿Qué garantiza la integridad de los backups? | No hay hash ni firma. Se garantiza no sobrescribir (`_unique_path`) y que no se guarde contenido vacío. La vía por archivo de MikroTik entrega los bytes exactos del equipo (sin verificar aún en equipo real). |
| 17 | ¿Cómo evitan inyección de comandos? | Validan host/puerto y sanean nombres de archivo, pero los parámetros que se interpolan en comandos (nombres de perfil, SN, usuarios) **no** se validan. Riesgo bajo (operador autenticado, campos de una línea), con mejora propuesta de lista blanca. |
| 18 | ¿Cómo prueban sin equipos reales? | `unittest` con dobles (`FakeConnection`, `ScriptedConnection`, conexiones que gotean datos, consola virtual simulada). Lo «confirmado» en equipo real proviene de pruebas manuales y está marcado en el código. Limitación: no hay integración automática ni pruebas de GUI. |
| 19 | ¿Por qué hilos y no `asyncio`? | Las bibliotecas (paramiko, sockets bloqueantes, `pywinpty`) son bloqueantes; el pool de hilos es simple y suficiente para decenas de conexiones. La GUI se mantiene fluida con `after(0, …)`. |
| 20 | ¿Qué pasa si cambian el nombre de host de la OLT? | `is_output_complete` busca `ZXAN…#`; con otro nombre no reconoce el prompt y vuelve a depender del silencio (8 s por comando): más lento, no incorrecto. |
| 21 | ¿La interfaz está desacoplada de la lógica? | Mayormente (no abre sockets ni escribe archivos de equipos), pero hay reglas en la UI (componer `gpon-onu_…`, validaciones del alta) y no hay pruebas de GUI. |
| 22 | ¿Qué detectan del equipo (modelo/versión)? | Solo el modelo de MikroTik (`board-name`). La OLT muestra «-»; no se detecta la versión de firmware. |
| 23 | ¿Por qué eliminaron el monitor de tráfico y los switches? | Decisión de producto: no se usará la aplicación para eso. Hay algunas menciones obsoletas en comentarios del código (§16.3). |
| 24 | ¿Qué harían primero para mejorar la seguridad? | (1) No registrar comandos con credenciales en vez de depender de patrones de texto, (2) proteger/avisar sobre backups con secretos, (3) limpiar la contraseña en memoria al desconectar, (4) validar parámetros enviados a comandos. |

---

## 29. Glosario

| Término | Significado en este proyecto |
|---|---|
| **CLI** | Interfaz de línea de comandos del equipo (RouterOS, ZXAN). |
| **SSH / SFTP** | Acceso remoto cifrado / transferencia de archivos sobre SSH (usada para bajar el `.rsc` de MikroTik). |
| **Telnet** | Acceso remoto sin cifrar (puerto 23). |
| **Host key / TOFU** | Clave que identifica al servidor SSH / «confiar en el primer uso»: se acepta y guarda la clave la primera vez. |
| **Prompt** | Texto que muestra el CLI al esperar un comando (`[admin@MikroTik] >`, `ZXAN#`); se usa para saber que terminó una respuesta. |
| **Paginación (`--More--`)** | Corte de salida largo en páginas; se desactiva con `terminal length 0`. |
| **PTY / ConPTY** | Terminal virtual; en Windows, el mecanismo que permite que `ssh.exe` crea estar en una consola real. |
| **OLT** | *Optical Line Terminal*: equipo del proveedor que gestiona la red GPON. Aquí, ZTE ZXA10 C300. |
| **ONU / ONT** | Equipo del cliente en la red óptica; se autentica en la OLT por número de serie. |
| **GPON** | Red óptica pasiva de acceso con una OLT y muchas ONU por puerto PON. |
| **Puerto PON** | Interfaz óptica de la OLT (`gpon-olt_1/13/4` = rack/slot/puerto). |
| **SN** | Número de serie de la ONU, usado para autenticarla. |
| **T-CONT** | Contenedor de tráfico GPON con un perfil de ancho de banda. |
| **GEM port** | Canal de transporte de tráfico del usuario dentro de GPON. |
| **VLAN / service-port** | Red virtual etiquetada / asociación en la OLT entre la ONU y la VLAN de servicio (identificador global). |
| **vport** | Puerto virtual de la ONU en la OLT. |
| **`pon-onu-mng`** | Modo de gestión remota de la ONU en la CLI de la OLT. |
| **`wan-ip`** | Comando de la ONU para su interfaz WAN (en modo router, DHCP sobre un perfil VLAN). |
| **Modo router / bridge** | La ONU hace NAT y DHCP propios / pasa la red del proveedor sin enrutar. |
| **running-config** | Configuración activa del equipo. |
| **`/export` / `.rsc`** | Comando de RouterOS que vuelca la configuración / archivo de script resultante. |
| **YAML** | Formato de texto estructurado usado para la extracción de datos. |
| **Driver (de dispositivo)** | Clase que encapsula comandos y particularidades de un fabricante. |
| **Hilo (thread) / pool** | Ejecución concurrente dentro del proceso / conjunto acotado de hilos de trabajo. |
| **Backup** | Copia de la configuración guardada en archivo. |
| **Firmware** | Software interno del equipo; su versión cambia los comandos válidos. |
| **RBAC / NETCONF / SNMP** | Conceptos mencionados solo como mejoras futuras o funciones eliminadas; **no** forman parte del sistema actual. |

---

## 30. Resumen final del proyecto

**Qué es.** NETWORK ADMIN (`network_terminal`, versión 0.1.0) es una aplicación de escritorio en Python/Tkinter para operar routers MikroTik y una OLT GPON ZTE ZXA10 C300 desde una única interfaz.

**Para qué sirve.** Para conectarse a los equipos por SSH o Telnet, obtener y archivar sus configuraciones (de uno o muchos equipos), extraerlas a YAML estructurado y, en la OLT, dar de alta abonados: descubrir puertos PON, listar y autenticar ONU, crear perfiles y activar Internet en modo router o bridge, con confirmación previa y verificación posterior.

**Cómo funciona.** Una arquitectura por capas separa la interfaz (Tkinter), la lógica de aplicación (lote, YAML, backups), los drivers por fabricante (comandos, prompt, limpieza, errores) y la conexión (SSH con paramiko, Telnet propio, SSH heredado mediante el `ssh.exe` del sistema y una consola virtual). La sesión se serializa con un candado, se vacía antes de cada comando y se detecta el fin de respuesta reconociendo el prompt, con silencio y tope como respaldo. El lote usa un pool de hilos con aislamiento de fallas.

**Tecnologías.** Python 3, Tkinter/ttk, paramiko, pywinpty (Windows), PyYAML, `threading`/`concurrent.futures`, `unittest`.

**Qué problema resuelve.** Elimina tareas manuales repetitivas y propensas a error (modo del CLI equivocado, identificadores globales repetidos, capturas con ruido, secuencias largas tipeadas de memoria), y deja una convención clara de archivos y registros.

**Ventajas.** Ahorro de tiempo, repetibilidad, trazabilidad, aislamiento de fallas, diseño extensible a nuevas marcas y robustez frente a consolas reales.

**Limitaciones.** Solo MikroTik y ZTE OLT; dependencia de comandos y firmwares específicos; parte de la OLT sin confirmación en equipo real; seguridad por mejorar (log que puede guardar contraseñas de usuarios de la OLT, Telnet en claro, backups sin cifrar); escalabilidad acotada (sin cola, reintentos ni credenciales por equipo); terminal por líneas; ZTE por SSH legacy solo en Windows; sin pruebas de interfaz ni de integración.

**Hacia dónde puede evolucionar.** Corrección del log y de la documentación, comparación y versionado de configuraciones, reintentos y credenciales por equipo, y —a largo plazo— un motor de ejecución desacoplado con cola de trabajos, base de datos y control de acceso. Todo lo anterior es **propuesta**; no existe hoy.

---

*Fin del documento. Para mantenerlo: cada vez que cambie un driver, un flujo o una limitación, actualizar las secciones 4, 7, 15 y 19, y la tabla de §6.4.*
