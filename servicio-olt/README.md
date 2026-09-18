# Aprovisionamiento ONU - OLT ZTE ZXAN

App para dar de alta/consultar ONUs en la OLT ZTE ZXAN, por **Telnet** o **SSH**.
La interfaz es una página web local (Flask) que también se abre como ventana
nativa de Windows (`app_desktop.py`).

---

## Estructura del proyecto

```
servicio-olt/
├── app.py                  Entrada versión TELNET (puerto 5000)
├── app_ssh.py              Entrada versión SSH (puerto 5001)
├── app_desktop.py          Launcher: abre la app en ventana nativa
│                           (sin args = Telnet,  "ssh" = SSH)
├── comandos.py             Armado de comandos y validación (sin transporte)
├── parsers.py              Parsers de salidas de la OLT + modelos dinámicos
├── vistas.py               Controlador web / rutas (compartido)
├── transporte_telnet.py    Conexión Telnet a la OLT
├── transporte_ssh.py       Conexión SSH a la OLT (OpenSSH -> plink)
├── templates/
│   ├── index.html          Interfaz versión Telnet
│   └── index_ssh.html      Interfaz versión SSH
└── dist/
    └── AprovisionamientoONU.exe   Ejecutable (Telnet; "ssh" como argumento)
```

## Qué hace cada archivo

### app.py / app_ssh.py
Archivos de **entrada** (los únicos que hay que correr). Configuran Flask y
registran las rutas con `vistas.registrar(...)`, indicando qué transporte usar
y qué opciones habilitar.

### vistas.py
El **controlador**: una sola copia de las rutas para Telnet y SSH. Contiene la
función `index()` con todas las acciones del formulario:
`volver`, `autocompletar`, `uncfg`, `estado`, `interfaz_on/off`,
`interfaces`, `interfaz_sel`, `ocupadas`, `eliminar`,
`provisionar`, y (solo Telnet) `modelos`, (solo SSH) `conectar`.

### comandos.py
Armado de comandos y **validación** anti-inyección:
- `construir_comandos_alta()` - arma los comandos de alta de ONU
- `validar_puerto()/validar_onu_id()/validar_sn()/validar_opciones()` - validación anti-inyección
- `MODELOS_VALIDOS`, `PLANES_VALIDOS` y regex `RE_PUERTO/RE_SN/RE_MODELO`

### parsers.py
**Parsers** de salidas de la OLT y listado dinámico de modelos:
- `parsear_modelos()` - modelos desde `show running-config`
- `cargar_modelos()/guardar_modelos()` - persistencia de modelos (`%APPDATA%\AprovisionamientoONU\modelos_onu.json`)
- `parsear_onus_activas()/parsear_onus_config()/mostrar_onus_ocupadas()` - ONUs del puerto
- `parsear_interfaces()/comandos_escanear_interfaces()` - estado de puertos GPON
- `verificar_aplicacion()` - confirma que la config quedó aplicada

### transporte_telnet.py
Conexión Telnet con socket nativo de Python. Función principal:
`ejecutar_por_telnet(host, usuario, password, comandos)`.

### transporte_ssh.py
Conexión SSH. Usa el cliente OpenSSH de Windows (con opciones legacy para la
OLT) y `plink` solo como último recurso. Función principal:
`ejecutar_por_ssh(host, usuario, password, comandos)`.

### templates/
HTML + Jinja. `index.html` tiene los modelos dinámicos (botón "Actualizar
modelos desde OLT") y `index_ssh.html` igual (las dos versiones actualizan la
lista de modelos desde la OLT; SSH además mantiene el botón "conectar").

## Cómo correrla

| Versión | Código | Ejecutable |
| --- | --- | --- |
| Telnet | `python app.py` → http://localhost:5000 | `AprovisionamientoONU.exe` |
| SSH | `python app_ssh.py` → http://localhost:5001 | `AprovisionamientoONU.exe ssh` |
| Ventana (Telnet) | `python app_desktop.py` | doble clic |
| Ventana (SSH) | `python app_desktop.py ssh` | `AprovisionamientoONU SSH.bat` |

## Dónde mirar si algo falla

- **No conecta / login rechazado** → `transporte_telnet.py` o `transporte_ssh.py`
- **El alta no aplica bien** → `comandos.py` (`construir_comandos_alta`,
  `verificar_aplicacion` en `parsers.py`)
- **No muestra ONUs / listados raros** → parsers en `parsers.py`
- **Botón no hace nada / página no carga** → `vistas.py` y `templates\`
- **Modelos no aparecen los nuevos** → acción `modelos` en `vistas.py` +
  `parsear_modelos()` en `parsers.py`

## Construir el ejecutable

```
python -m PyInstaller --noconfirm --onefile --windowed --name AprovisionamientoONU ^
  --add-data "templates;templates" --hidden-import app --hidden-import app_ssh app_desktop.py
```