# App de aprovisionamiento ONU - OLT ZTE ZXAN

App web con formulario para dar de alta clientes en la OLT sin escribir
comandos a mano. Se conecta por SSH y manda la misma secuencia validada
manualmente (registro en OLT + tcont/gemport/vport + pon-onu-mng).

## Instalación (una sola vez)

```
pip install flask --break-system-packages
```

(usa Telnet nativo de Python, no hace falta ninguna librería extra
para la conexión)

**IMPORTANTE — Seguridad:** esta versión se conecta por Telnet, que
no cifra nada: ni el usuario, ni la contraseña, ni los comandos
viajan protegidos por la red. Usala solo dentro de una red cerrada y
confiable (el laboratorio/red interna de la facultad). Nunca la uses
sobre una red pública, WiFi compartido con desconocidos, o internet.

## Uso

```
python3 app.py
```

Abrí en el navegador: **http://localhost:5000**

Si querés que otros compañeros de la facultad la usen desde otra
computadora de la misma red, entrá a:

```
http://<IP-de-tu-PC>:5000
```

(la IP de tu PC, no la de la OLT — la app ya escucha en todas las
interfaces de red por el `host="0.0.0.0"` configurado).

## Cómo se usa

1. Completá los datos de conexión (IP de gestión de la OLT, usuario,
   contraseña) — no se guardan en ningún lado, solo se usan para esa
   conexión puntual.
2. Completá los datos del cliente: puerto, número de ONU, modelo,
   SN, plan, tipo de servicio (solo internet o triple play) y modo
   (router o bridge).
3. Botón **"Ver ONUs sin configurar en el puerto"** — antes de dar de
   alta, usalo para confirmar el SN real del equipo conectado (evita
   errores de tipeo).
4. Botón **"Dar de alta con estos datos"** — manda la secuencia
   completa y muestra la respuesta de la OLT, incluyendo el
   `show gpon onu state` final para confirmar si quedó en
   `operation`/`working`.
5. Botón **"Ver estado del puerto"** — para consultar en cualquier
   momento el estado de las ONUs ya configuradas.

## Importante

- Esta app no reemplaza la revisión manual: siempre mirá la salida
  que muestra antes de asumir que el alta funcionó.
- Los perfiles `onu-profile gpon` que puedan existir en la OLT
  (INT-100M, INT-300M, etc.) no se usan acá — se confirmó que este
  firmware no permite aplicarlos por CLI, así que la app arma la
  configuración manual completa (tcont/gemport directo en la
  interfaz), que es el método que sí funciona.
- Probá siempre primero con una ONU de prueba antes de usarla con
  un cliente real.
