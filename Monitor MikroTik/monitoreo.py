#!/usr/bin/env python3
"""
Monitoreo en vivo, alarmas, topologia y metricas OSPF
=====================================================
Este modulo es el corazon del panel en vivo:

  - muestrear()/poll(): lee las interfaces de cada equipo conectado,
    calcula la tasa real en bps (los contadores de RouterOS son
    acumulados, asi que se diferencian entre muestras) y arma la
    topologia detectada por los cables.
  - El motor de alarmas evalua reglas guardadas en monitoreo.yml sobre
    esas tasas, genera eventos y, si la regla lo pide, cambia el costo
    OSPF del enlace afectado (en los dos extremos) y lo restaura al
    bajar la alarma.
  - la topologia se cachea en memoria: la consumen el grafo SVG y la
    busqueda de pares para cambiar metricas.

Todo el estado vive bajo un candado unico porque Flask atiende en varios
hilos y el monitoreo refresca cada pocos segundos.
"""

import fnmatch
import os
import threading
import time

import yaml

import transporte_mikrotik as tm

ARCHIVO = "monitoreo.yml"
CAPACIDAD_DEFECTO = 100_000_000
MUESTRA_VIEJA = 60.0
TOPO_TTL = 4.0
METRICAS = ("rx-bps", "tx-bps", "total-bps", "pct")
OPERADORES = (">", ">=", "<", "<=", "==", "!=")

_lock = threading.RLock()
_poll_lock = threading.Lock()
_muestra = {}
_config = {"capacidad-default": CAPACIDAD_DEFECTO, "capacidades": {}, "alarmas": []}
_ruta = [None]
_estados = {}
_eventos = []
_seq = [0]
_topo = {"ts": 0.0, "nodos": [], "enlaces": []}
_cache_id = {}
_cache_rid = {}


def iniciar(dir_datos):
    """Carga (y deja anotada) la ruta del archivo de configuracion."""
    ruta = os.path.join(dir_datos, ARCHIVO)
    with _lock:
        _ruta[0] = ruta
        if os.path.isfile(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f) or {}
                if isinstance(doc, dict):
                    _config.update({k: v for k, v in doc.items() if v is not None})
            except Exception:  # noqa: BLE001
                pass
        _config.setdefault("capacidad-default", CAPACIDAD_DEFECTO)
        _config.setdefault("capacidades", {})
        _config.setdefault("alarmas", [])
    return ruta


def _guardar():
    ruta = _ruta[0]
    if not ruta:
        return
    with _lock:
        copia = {
            "capacidad-default": _config.get("capacidad-default", CAPACIDAD_DEFECTO),
            "capacidades": dict(_config.get("capacidades") or {}),
            "alarmas": [dict(a) for a in (_config.get("alarmas") or [])],
        }
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            yaml.safe_dump(copia, f, allow_unicode=True, sort_keys=False)
    except OSError:
        pass


def config():
    with _lock:
        return {
            "capacidad-default": _config.get("capacidad-default", CAPACIDAD_DEFECTO),
            "capacidades": dict(_config.get("capacidades") or {}),
            "alarmas": [dict(a) for a in (_config.get("alarmas") or [])],
            "ruta": _ruta[0] or "",
        }


def capacidad(host, interfaz):
    """Bps disponibles para esa interfaz (override por interfaz o global)."""
    with _lock:
        mapa = _config.get("capacidades") or {}
        v = mapa.get(f"{host}/{interfaz}")
        if v:
            try:
                return max(1, int(v))
            except (TypeError, ValueError):
                pass
        try:
            return max(1, int(_config.get("capacidad-default") or CAPACIDAD_DEFECTO))
        except (TypeError, ValueError):
            return CAPACIDAD_DEFECTO


def guardar_capacidades(default, mapa):
    try:
        valor = max(1, int(default))
    except (TypeError, ValueError):
        valor = CAPACIDAD_DEFECTO
    limpio = {}
    for clave, v in (mapa or {}).items():
        try:
            limpio[str(clave)] = max(1, int(v))
        except (TypeError, ValueError):
            continue
    with _lock:
        _config["capacidad-default"] = valor
        _config["capacidades"] = limpio
    _guardar()
    return config()


def guardar_alarmas(lista):
    limpias = []
    ids = set()
    for a in (lista or []):
        if not isinstance(a, dict):
            continue
        aid = str(a.get("id") or "").strip() or f"al-{len(limpias) + 1}"
        a = dict(a)
        a["id"] = aid
        a.setdefault("habilitada", True)
        a.setdefault("severidad", "alerta")
        a.setdefault("metrica", "pct")
        a.setdefault("operador", ">=")
        a.setdefault("accion", "manual")
        a.setdefault("duracion-s", 10)
        a.setdefault("limpiar-s", 30)
        try:
            a["umbral"] = float(a.get("umbral"))
        except (TypeError, ValueError):
            continue
        if aid in ids:
            continue
        ids.add(aid)
        limpias.append(a)
    with _lock:
        _config["alarmas"] = limpias
        for clave in list(_estados):
            if clave.split("|", 1)[0] not in ids:
                _estados.pop(clave, None)
    _guardar()
    return config()


def borrar_alarma(aid):
    with _lock:
        _config["alarmas"] = [a for a in (_config.get("alarmas") or [])
                              if str(a.get("id")) != str(aid)]
        for clave in list(_estados):
            if clave.split("|", 1)[0] == str(aid):
                _estados.pop(clave, None)
    _guardar()
    return config()


def _entero(v):
    if isinstance(v, bool):
        return 0
    try:
        return int(float(str(v)))
    except (TypeError, ValueError):
        return 0


def muestrear(host, filas, ahora=None):
    """Devuelve las interfaces con rx/tx y las tasas en bps.

    Los contadores de RouterOS son acumulados: la tasa sale de la
    diferencia contra la muestra anterior dividida en el tiempo
    transcurrido. Si el contador baja (reinicio de interfaz) o paso
    demasiado tiempo, la tasa se toma como 0.
    """
    ahora = time.monotonic() if ahora is None else ahora
    with _lock:
        previa = _muestra.setdefault(host, {})
        salida = []
        for f in filas:
            nombre = str(f.get("nombre") or "")
            rx = _entero(f.get("rx"))
            tx = _entero(f.get("tx"))
            p = previa.get(nombre)
            rx_bps = tx_bps = 0.0
            if p:
                dt = ahora - p["t"]
                if 0 < dt <= MUESTRA_VIEJA:
                    rx_bps = max(0, rx - p["rx"]) / dt
                    tx_bps = max(0, tx - p["tx"]) / dt
            previa[nombre] = {"t": ahora, "rx": rx, "tx": tx}
            fila = dict(f)
            fila["rx-bps"] = int(round(rx_bps))
            fila["tx-bps"] = int(round(tx_bps))
            fila["total-bps"] = fila["rx-bps"] + fila["tx-bps"]
            salida.append(fila)
        return salida


def _utilizacion(fila, cap):
    peor = max(_entero(fila.get("rx-bps")), _entero(fila.get("tx-bps")))
    if cap <= 0:
        return 0.0
    return round(min(999.0, peor * 100.0 / cap), 1)


def _identidad(api, host):
    with _lock:
        v = _cache_id.get(host)
    if v and time.time() - v[1] < 600:
        return v[0]
    try:
        nombre = tm.identidad(api)
    except Exception:  # noqa: BLE001
        nombre = v[0] if v else ""
    with _lock:
        _cache_id[host] = (nombre, time.time())
    return nombre


def _router_id(api, host):
    with _lock:
        v = _cache_rid.get(host)
    if v and time.time() - v[1] < 600:
        return v[0]
    rid = ""
    try:
        inst = tm.ospf_instancias(api)
        rid = str(inst[0].get("router-id") or "") if inst else ""
    except Exception:  # noqa: BLE001
        rid = v[0] if v else ""
    with _lock:
        _cache_rid[host] = (rid, time.time())
    return rid


def _gestion(host, dirs):
    """Interfaz de gestión: la que tiene una IP que contiene al host."""
    for d in dirs:
        addr = str(d.get("address") or "")
        try:
            if tm._en_rango(host, addr):
                return str(d.get("interface") or "")
        except Exception:  # noqa: BLE001
            continue
    return ""


def _red_de(addr):
    try:
        base, pref = tm._red_base(str(addr))
        return f"{base}/{pref}"
    except Exception:  # noqa: BLE001
        return str(addr or "")


def _lado(host, nodo, iface, addr, info, oif, vec):
    cap = capacidad(host, iface)
    rx = _entero(info.get("rx-bps"))
    tx = _entero(info.get("tx-bps"))
    return {
        "equipo": host,
        "nodo": nodo,
        "interfaz": iface,
        "direccion": addr,
        "red": _red_de(addr),
        "running": str(info.get("running", "")).lower() in ("true", "1", "yes"),
        "link-downs": _entero(info.get("link-downs")),
        "costo": _entero(oif.get("costo")) or None,
        "ospf": str(vec.get("estado") or "") if vec else "",
        "vecino-rid": str(vec.get("router-id") or "") if vec else "",
        "rx-bps": rx,
        "tx-bps": tx,
        "total-bps": rx + tx,
        "capacidad": cap,
        "pct": _utilizacion(info, cap),
        "rx": _entero(info.get("rx")),
        "tx": _entero(info.get("tx")),
    }


def _armar_topologia(recogidos):
    nodos = []
    por_host = {}
    rid_a_host = {}
    ident_a_host = {}
    usados = set()
    for host, d in recogidos.items():
        ident = d["identidad"] or host
        nid = ident
        n = 2
        while nid in usados:
            nid = f"{ident}#{n}"
            n += 1
        usados.add(nid)
        nodos.append({
            "id": nid,
            "host": host,
            "identidad": ident,
            "router-id": d["router-id"],
            "externo": False,
        })
        por_host[host] = nid
        if d["router-id"]:
            rid_a_host[d["router-id"]] = host
        ident_a_host.setdefault(ident, host)

    addr_idx = {}
    for host, d in recogidos.items():
        for dd in d["dirs"]:
            addr = str(dd.get("address") or "")
            iface = str(dd.get("interface") or "")
            if not addr or not iface:
                continue
            addr_idx[addr] = (host, iface)
            addr_idx[addr.split("/")[0]] = (host, iface)

    exactos = {}
    parciales = []

    def nodo_externo(etiqueta):
        nid = etiqueta or "desconocido"
        base = nid
        n = 2
        while nid in usados:
            nid = f"{base}#{n}"
            n += 1
        if nid not in usados:
            usados.add(nid)
            nodos.append({"id": nid, "host": "", "identidad": base,
                          "router-id": base if base.count(".") == 3 else "",
                          "externo": True})
        return nid

    for host, d in recogidos.items():
        nodo = por_host[host]
        gestion = _gestion(host, d["dirs"])
        itf_info = {str(i.get("nombre")): i for i in d["interfaces"]}
        oif = {str(o.get("interfaz")): o for o in d["ospf-itf"]}
        vecs = {str(v.get("interfaz")): v for v in d["ospf-vec"]}
        for dd in d["dirs"]:
            iface = str(dd.get("interface") or "")
            addr = str(dd.get("address") or "")
            if not iface or not addr:
                continue
            pref = int(addr.split("/")[1]) if "/" in addr else 32
            if pref >= 32 or iface == gestion:
                continue
            info = itf_info.get(iface, {})
            vec = vecs.get(iface)
            lado = _lado(host, nodo, iface, addr, info, oif.get(iface, {}), vec)
            if vec:
                destino = addr_idx.get(str(vec.get("direccion") or "").split("/")[0])
                if destino and destino[0] != host:
                    clave = frozenset({(host, iface), destino})
                    exactos.setdefault(clave, []).append(lado)
                    continue
                dest_host = rid_a_host.get(str(vec.get("router-id") or ""))
                if dest_host and dest_host != host:
                    lado["pendiente"] = dest_host
                    parciales.append(lado)
                    continue
                nid = nodo_externo(str(vec.get("router-id") or ""))
                lado["nodo-externo"] = nid
                exactos.setdefault(frozenset({(host, iface), ("ext", nid)}), []).append(lado)
                continue
            m = d["mndp"].get(iface) or {}
            ident_vec = str(m.get("identity") or "")
            dest_host = ident_a_host.get(ident_vec)
            if dest_host and dest_host != host:
                lado["pendiente"] = dest_host
                parciales.append(lado)
            elif ident_vec:
                nid = nodo_externo(ident_vec)
                lado["nodo-externo"] = nid
                exactos.setdefault(frozenset({(host, iface), ("ext", nid)}), []).append(lado)

    por_par = {}
    for lado in parciales:
        a, b = sorted([lado["equipo"], lado.pop("pendiente")])
        clave = (a, b)
        g = por_par.setdefault(clave, {"a": [], "b": []})
        g["a" if lado["equipo"] == a else "b"].append(lado)

    for (a, b), g in por_par.items():
        la = sorted(g["a"], key=lambda x: x["interfaz"])
        lb = sorted(g["b"], key=lambda x: x["interfaz"])
        if len(la) == len(lb) and la:
            for x, y in zip(la, lb):
                clave = frozenset({(a, x["interfaz"]), (b, y["interfaz"])})
                lista = exactos.setdefault(clave, [])
                lista.append(x)
                lista.append(y)
        else:
            for x in la:
                exactos.setdefault(frozenset({(a, x["interfaz"]), (b, "?")}), []).append(x)
            for y in lb:
                exactos.setdefault(frozenset({(a, "?"), (b, y["interfaz"])}), []).append(y)

    enlaces = []
    for clave, lados in exactos.items():
        lados = sorted(lados, key=lambda x: (x["equipo"], x["interfaz"]))
        a = lados[0]
        b = lados[1] if len(lados) > 1 else None
        enlaces.append(_armar_enlace(a, b))
    enlaces.sort(key=lambda e: (e["red"], e["a"]["equipo"], e["a"]["interfaz"]))
    nodos.sort(key=lambda n: (n["externo"], n["id"]))
    return {"nodos": nodos, "enlaces": enlaces}


def _armar_enlace(a, b):
    if not b:
        estado = "un-lado"
    elif not a["running"] or not b["running"]:
        estado = "caido"
    elif a["ospf"] == "Full" and b["ospf"] == "Full":
        estado = "full"
    elif a["ospf"] or b["ospf"]:
        estado = "degradado"
    else:
        estado = "sin-ospf"
    pcts = [a["pct"]] + ([b["pct"]] if b else [])
    return {
        "red": a["red"] or (b["red"] if b else ""),
        "estado": estado,
        "pct": max(pcts),
        "a": a,
        "b": b,
        "id": f"{a['equipo']}:{a['interfaz']}",
    }


def recoger(sesiones, hosts=None):
    """Lee de cada equipo todo lo necesario para monitoreo y topologia."""
    elegidos = [h for h in (hosts or list(sesiones)) if h in sesiones]
    recogidos = {}
    equipos = []
    for host in elegidos:
        ses = sesiones.get(host) or {}
        api = ses.get("api")
        if not api:
            continue
        try:
            filas = tm.interfaces_con_trafico(api)
            dirs = tm._filas(api, "/ip/address/print")
            ospf_itf = tm.ospf_interfaces_lista(api)
            ospf_vec = tm.ospf_vecinos(api)
            mndp = tm.vecinos_interfaz(api)
        except Exception as e:  # noqa: BLE001
            equipos.append({"host": host, "ok": False, "error": str(e), "interfaces": []})
            continue
        nombre = _identidad(api, host)
        rid = _router_id(api, host)
        interfaces = muestrear(host, filas)
        for i in interfaces:
            i["direccion"] = ""
        for d in dirs:
            for i in interfaces:
                if str(d.get("interface")) == i["nombre"]:
                    i["direccion"] = str(d.get("address") or "")
                    i["red"] = _red_de(d.get("address"))
        for i in interfaces:
            i["capacidad"] = capacidad(host, i["nombre"])
            i["pct"] = _utilizacion(i, i["capacidad"])
            i["alarma"] = None
        recogidos[host] = {
            "host": host,
            "identidad": nombre,
            "router-id": rid,
            "interfaces": interfaces,
            "dirs": dirs,
            "ospf-itf": ospf_itf,
            "ospf-vec": ospf_vec,
            "mndp": mndp,
        }
        equipos.append({
            "host": host,
            "identidad": nombre,
            "router-id": rid,
            "ok": True,
            "error": None,
            "interfaces": interfaces,
        })
    return recogidos, equipos


def topologia(sesiones, forzar=False):
    """Topologia detectada (nodos + enlaces), cacheada por TOPO_TTL."""
    with _lock:
        ts = _topo.get("ts")
        guardada = dict(_topo)
    if not forzar and time.time() - float(ts or 0) < TOPO_TTL:
        return guardada
    recogidos, _ = recoger(sesiones)
    if not recogidos:
        vacia = {"ts": time.time(), "nodos": [], "enlaces": []}
        with _lock:
            _topo.clear()
            _topo.update(vacia)
        return vacia
    nueva = _armar_topologia(recogidos)
    nueva["ts"] = time.time()
    with _lock:
        _topo.clear()
        _topo.update(nueva)
    return nueva


def _existe_enlace(topo, host, iface):
    for e in topo.get("enlaces", []):
        for lado in (e.get("a"), e.get("b")):
            if lado and lado.get("equipo") == host and lado.get("interfaz") == iface:
                return e
    return None


def _extremos(topo, host, iface):
    e = _existe_enlace(topo, host, iface)
    if not e:
        return [(host, iface)]
    res = []
    for lado in (e.get("a"), e.get("b")):
        if lado and lado.get("equipo") and lado.get("interfaz") != "?":
            par = (lado["equipo"], lado["interfaz"])
            if par not in res:
                res.append(par)
    if not res:
        res = [(host, iface)]
    return res


def cambiar_costo(sesiones, host, interfaz, costo):
    """Cambia el costo OSPF de una interfaz (None = restaurar el dinámico)."""
    api = (sesiones.get(host) or {}).get("api")
    if not api:
        return False, f"No hay sesión activa con {host}."
    err = tm.fijar_costo_ospf(api, interfaz, costo)
    if err:
        return False, err
    with _lock:
        _topo["ts"] = 0.0
    if costo is None:
        return True, f"{host} {interfaz}: costo dinámico restaurado."
    return True, f"{host} {interfaz}: costo {costo} aplicado."


def cambiar_costo_enlace(sesiones, host, interfaz, costo, top=None):
    """Aplica el costo a los dos extremos del enlace. Devuelve (ok, mensajes)."""
    topo = top if top is not None else topologia(sesiones)
    extremos = _extremos(topo, host, interfaz)
    mensajes = []
    ok = True
    for eq, itf in extremos:
        bien, msg = cambiar_costo(sesiones, eq, itf, costo)
        ok = ok and bien
        mensajes.append(msg)
    return ok, mensajes


def _valor_metrica(fila, metrica):
    if metrica not in METRICAS:
        return None
    return _entero(fila.get(metrica))


def _cumple(valor, operador, umbral):
    if operador == ">":
        return valor > umbral
    if operador == ">=":
        return valor >= umbral
    if operador == "<":
        return valor < umbral
    if operador == "<=":
        return valor <= umbral
    if operador == "==":
        return valor == umbral
    if operador == "!=":
        return valor != umbral
    return valor >= umbral


def _nuevo_evento(**campos):
    with _lock:
        _seq[0] += 1
        ev = {"seq": _seq[0], "ts": time.time()}
        ev.update(campos)
        _eventos.append(ev)
        if len(_eventos) > 300:
            del _eventos[:-300]
    return ev


def eventos_desde(seq=0):
    with _lock:
        return [dict(e) for e in _eventos if int(e.get("seq") or 0) > int(seq or 0)]


def _aplicar_costo_automatico(sesiones, topo, host, iface, costo):
    mensajes = []
    extremos = _extremos(topo, host, iface)
    for eq, itf in extremos:
        api = (sesiones.get(eq) or {}).get("api")
        if not api:
            mensajes.append(f"sin sesión para {eq}")
            continue
        err = tm.fijar_costo_ospf(api, itf, costo)
        if err:
            mensajes.append(err)
    with _lock:
        _topo["ts"] = 0.0
    return mensajes


def _evaluar_alarmas(sesiones, topo, equipos, ahora):
    """Mantiene el estado de cada regla y lanza eventos.

    La regla se evalua por cada interfaz que matchea su alcance
    (equipo/identidad y patron de interfaz), asi que una sola regla
    puede disparar varias instancias a la vez. El cambio de costo solo
    ocurre cuando la regla esta marcada como automatica.
    """
    alarmas = config().get("alarmas") or []
    resumen = []
    orden_sev = {"info": 1, "alerta": 2, "critico": 3}
    for al in alarmas:
        if not al.get("habilitada", True):
            continue
        eq = str(al.get("equipo") or "").strip()
        patron = str(al.get("interfaz") or "").strip() or "*"
        metrica = str(al.get("metrica") or "pct")
        op = str(al.get("operador") or ">=")
        umbral = float(al.get("umbral") or 0)
        dur = float(al.get("duracion-s") or 0)
        limpia = float(al.get("limpiar-s") or 0)
        severidad = str(al.get("severidad") or "alerta")
        accion = str(al.get("accion") or "manual")
        coincidencias = 0
        for eq_datos in equipos:
            if not eq_datos.get("ok"):
                continue
            host = eq_datos["host"]
            if eq and eq not in (host, eq_datos.get("identidad") or ""):
                continue
            for fila in eq_datos.get("interfaces") or []:
                iface = fila.get("nombre") or ""
                if not fnmatch.fnmatchcase(iface, patron):
                    continue
                valor = _valor_metrica(fila, metrica)
                if valor is None:
                    continue
                coincidencias += 1
                clave = f"{al['id']}|{host}|{iface}"
                with _lock:
                    est = _estados.setdefault(clave, {
                        "activa": False, "cond": None, "t": ahora,
                        "valor": valor, "desde": ahora, "costos": [],
                    })
                cumple = _cumple(valor, op, umbral)
                if cumple != bool(est.get("cond")):
                    est["cond"] = cumple
                    est["t"] = ahora
                est["valor"] = valor
                if cumple and not est["activa"] and ahora - est["t"] >= dur:
                    est["activa"] = True
                    est["desde"] = ahora
                    mensaje = (f"{eq_datos.get('identidad') or host} {iface}: "
                               f"{metrica}={valor} {op} {umbral:g} ({severidad})")
                    accion_txt = ""
                    if accion == "automatica":
                        costo = al.get("costo")
                        if costo is not None:
                            previos = []
                            for eq2, itf2 in _extremos(topo, host, iface):
                                lado = _lado_de(topo, eq2, itf2)
                                if lado and lado.get("costo") is not None:
                                    previos.append((eq2, itf2, lado["costo"]))
                            est["costos"] = previos
                            erros = _aplicar_costo_automatico(
                                sesiones, topo, host, iface, costo)
                            accion_txt = (f"costo {costo} aplicado al enlace"
                                          if not erros else "; ".join(erros))
                            mensaje += f" -> {accion_txt}"
                    _nuevo_evento(tipo="activada", alarma=al["id"],
                                   nombre=al.get("nombre") or al["id"],
                                   severidad=severidad, equipo=host,
                                   identidad=eq_datos.get("identidad") or "",
                                   interfaz=iface, valor=valor, umbral=umbral,
                                   metrica=metrica, mensaje=mensaje,
                                   detalle=accion_txt)
                elif not cumple and est["activa"] and ahora - est["t"] >= limpia:
                    est["activa"] = False
                    est["desde"] = ahora
                    mensaje = (f"{eq_datos.get('identidad') or host} {iface}: "
                               f"{metrica}={valor} recuperada")
                    if accion == "automatica" and est.get("costos"):
                        destino = al.get("costo-normal")
                        if destino is not None:
                            try:
                                destino = int(destino)
                            except (TypeError, ValueError):
                                destino = None
                        erros = _aplicar_costo_automatico(
                            sesiones, topo, host, iface, destino)
                        etiqueta = ("costo dinámico restaurado"
                                    if destino is None
                                    else f"costo {destino} restaurado")
                        mensaje += (f" ({etiqueta})"
                                    if not erros else " (" + "; ".join(erros) + ")")
                    est["costos"] = []
                    _nuevo_evento(tipo="desactivada", alarma=al["id"],
                                   nombre=al.get("nombre") or al["id"],
                                   severidad="ok", equipo=host,
                                   identidad=eq_datos.get("identidad") or "",
                                   interfaz=iface, valor=valor, umbral=umbral,
                                   metrica=metrica, mensaje=mensaje, detalle="")
                if est["activa"]:
                    previa = fila.get("alarma")
                    if orden_sev.get(severidad, 0) >= orden_sev.get(previa or "", 0):
                        fila["alarma"] = severidad
                resumen.append({
                    "id": al["id"],
                    "nombre": al.get("nombre") or al["id"],
                    "host": host,
                    "identidad": eq_datos.get("identidad") or "",
                    "interfaz": iface,
                    "metrica": metrica,
                    "operador": op,
                    "umbral": umbral,
                    "valor": valor,
                    "severidad": severidad,
                    "accion": accion,
                    "estado": "activa" if est["activa"] else "ok",
                    "desde": est.get("desde") or ahora,
                    "duracion-s": dur,
                    "limpiar-s": limpia,
                })
        if not coincidencias:
            resumen.append({
                "id": al["id"],
                "nombre": al.get("nombre") or al["id"],
                "host": "",
                "identidad": "",
                "interfaz": patron,
                "metrica": metrica,
                "operador": op,
                "umbral": umbral,
                "valor": None,
                "severidad": severidad,
                "accion": accion,
                "estado": "sin-datos",
                "desde": ahora,
                "duracion-s": dur,
                "limpiar-s": limpia,
            })
    return resumen


def _lado_de(topo, host, iface):
    for e in topo.get("enlaces", []):
        for lado in (e.get("a"), e.get("b")):
            if lado and lado.get("equipo") == host and lado.get("interfaz") == iface:
                return lado
    return None


def poll(sesiones, hosts=None):
    """Ciclo completo de monitoreo: lee, calcula, evalúa alarmas, arma topología.

    Un candado propio evita que dos refrescos simultáneos (por ejemplo al
    reanudar la pestaña) lean y escriban el estado de las alarmas a la vez.
    """
    with _poll_lock:
        recogidos, equipos = recoger(sesiones, hosts)
        topo = _armar_topologia(recogidos) if recogidos else {"nodos": [], "enlaces": []}
        topo["ts"] = time.time()
        with _lock:
            _topo.clear()
            _topo.update(topo)
        alarmas = _evaluar_alarmas(sesiones, topo, equipos, time.time())
        with _lock:
            ultimo = _seq[0]
    return {
        "ok": True,
        "ts": time.time(),
        "equipos": equipos,
        "alarmas": alarmas,
        "topologia": topo,
        "seq": ultimo,
    }


def metricas(sesiones, hosts=None):
    """Costos y estado OSPF por interfaz, para la pestaña de métricas."""
    elegidos = [h for h in (hosts or list(sesiones)) if h in sesiones]
    salida = []
    for host in elegidos:
        api = (sesiones.get(host) or {}).get("api")
        if not api:
            continue
        try:
            filas = tm.ospf_interfaces_lista(api)
            nombre = _identidad(api, host)
        except Exception as e:  # noqa: BLE001
            salida.append({"host": host, "ok": False, "error": str(e), "interfaces": []})
            continue
        salida.append({
            "host": host,
            "identidad": nombre,
            "ok": True,
            "error": None,
            "interfaces": filas,
        })
    return salida


def reiniciar_estados():
    with _lock:
        _estados.clear()
        _eventos.clear()
        _seq[0] = 0
    return True
