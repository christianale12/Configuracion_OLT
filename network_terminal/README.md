# network_terminal

Cliente simple de administración de equipos de red (SSH / Telnet), estilo PuTTY.
Pensada para convertirse más adelante en el módulo de conexión/automatización del
proyecto principal.

## Ejecutar

```bash
python -m network_terminal
```

## Dependencias

| Función            | Requiere                              |
| ------------------ | ------------------------------------- |
| GUI (tkinter)      | Biblioteca estándar — nada que instalar |
| Telnet             | Biblioteca estándar (socket)          |
| Tests (unittest)   | Biblioteca estándar                   |
| **SSH**            | `paramiko`  →  `pip install paramiko` |

`telnetlib` fue eliminado en Python 3.13, por eso el cliente Telnet se implementó
sobre `socket` con negociación IAC mínima (rechaza todas las opciones → modo línea).

Si `paramiko` no está instalado, la app arranca igual y Telnet funciona; al
intentar SSH se muestra el mensaje con la instrucción de instalación.

## Tests

```bash
python -m unittest discover -s network_terminal/tests -t .
```

No se conecta a ningún equipo real: todo se prueba con dobles (`FakeConnection`,
`FakeSocket`).

## Estructura

```
network_terminal/
├── app.py / __main__.py     punto de entrada
├── core/                    errores, validación, logging
├── connection/              base + ssh_client + telnet_client + manager (threading)
├── devices/                 Device (ABC) + MikroTik / Cisco / ZTE OLT / ZTE ONU / Genérico
│                            + registry + parsers + facts (recolección estructurada)
├── backup/                  BackupManager (Escritorio, nombres, .txt y .yaml)
├── batch/                   descarga masiva (parse_targets + download_configs, pool de hilos)
├── ui/                      ventana Tkinter + ventana de descarga masiva
└── tests/                   unittest + dobles
```

La GUI no contiene lógica de SSH/Telnet ni de archivos: todo pasa por las capas.

## Extracción a YAML estructurado

Botón **"Extraer a YAML"** (ventana principal, con la sesión abierta) y opción
**"Qué guardar → YAML / Ambos"** en la descarga masiva.

En vez de solo volcar la running-config como texto, ejecuta un conjunto de
comandos según el tipo de equipo, parsea la salida y arma un archivo
`IP_AAAA-MM-DD_HH-MM-SS.yaml` con secciones: `interfaces`, `ip_addresses`,
`routes`, `vlans`, `firewall_filter`, `firewall_nat`, `summary` (gateway por
defecto, IPs de gestión…), y `raw` con el texto crudo de cada comando para
trazabilidad. Lo que el equipo no tenga, simplemente no aparece.

Cada tipo de equipo aporta su propio conjunto de comandos y parsers
(`devices/<vendor>.py` + `devices/parsers.py`); `devices/facts.py` orquesta.
Requiere **PyYAML** (`pip install pyyaml`).

Estado de los parsers:
- **MikroTik**: funcional (parser de `... print detail`, fusiona `speed`/`poe`
  de `/interface ethernet`, deriva gateway por defecto de las rutas).
- **Cisco / ZTE OLT / ZTE ONU**: *scaffolding* — se definen los comandos y se
  guarda `raw_lines` por sección; solo se parsea lo tabular estable
  (`show ip interface brief`). Ajustar comandos/parsers contra el equipo real.
- **ZTE ONU**: pensado para ONU con CLI propia; muchas ONU se administran *a
  través de la OLT* (eso es otra funcionalidad, aún no implementada).

## Descarga masiva

Botón **"Descarga masiva…"** en la ventana principal. Se pegan varias IP/host
(uno por línea, o separados por coma/espacio), un único juego de credenciales +
protocolo + puerto + tipo de equipo, y se descarga la running-config de todos.

- Conexiones en paralelo acotadas (spinbox, 1–20; por defecto 5).
- Un equipo que falla **no detiene** al resto; cada resultado se ve en la tabla
  (OK / ERROR + detalle + segundos) a medida que termina.
- Un archivo por equipo (`IP_AAAA-MM-DD_HH-MM-SS.txt`), en el Escritorio o en la
  carpeta elegida; opción de crear una subcarpeta `configs_<fecha-hora>/`.
- Botón **Cancelar** (los equipos aún no procesados se marcan "Cancelado").
- Lógica en `batch/runner.py` (`parse_targets`, `download_configs`), reutilizable
  sin GUI y cubierta por `tests/test_bulk.py`.

## Seguridad (v1)

- La contraseña vive solo en memoria (StringVar / atributo privado). No se
  persiste en disco ni se escribe en logs. `SshConnection.close()` la descarta.
- Los logs pasan por un filtro que enmascara `password=…`, `secret …`, etc.
- **Host keys SSH**: política por defecto `RejectPolicy` (paramiko). El checkbox
  *"Confiar y recordar host key (TOFU)"* es una **excepción documentada**: acepta
  la clave desconocida la primera vez, la guarda en `~/.network_terminal/known_hosts`
  y registra un `WARNING`. Sin ese checkbox, un host no conocido se rechaza.

## Ubicaciones

- Logs: `~/.network_terminal/logs/network_terminal.log` (rota a 1 MB, 5 copias).
- `known_hosts` (TOFU): `~/.network_terminal/known_hosts`.
- Backups: **Escritorio del usuario actual** (en Windows se resuelve por API de
  carpetas conocidas, respeta OneDrive). Nombre: `IP-o-host_AAAA-MM-DD_HH-MM-SS.txt`.

## Limitaciones conocidas de esta versión

- Terminal **orientada a líneas** (escribir comando + Enter), no emulación TTY
  completa (sin colores ANSI, sin edición de scrollback).
- Login Telnet automático *best-effort* (detecta prompts habituales); si no los
  reconoce, se completa manualmente en la terminal.
- Sin autodetección de fabricante: se elige el tipo de equipo en un desplegable.
- Una sola sesión por ventana (sin tabs).
