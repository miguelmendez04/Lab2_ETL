"""
Reglas de calidad que deben cumplirse antes de publicar las capas Silver y Gold.
Cada regla devuelve (capa, regla, cumple, detalle). Si alguna falla, el pipeline se detiene
y no publica datos incorrectos.
"""
import pandas as pd

MONTOS_VENTA = ["precio_unitario", "valor_bruto", "valor_descuento", "valor_neto"]


class ValidacionError(Exception):
    """Alguna regla de calidad no se cumplió."""


def _m(x):
    return f"{int(x):,}".replace(",", ".")


def _regla(capa, regla, cumple, detalle=""):
    return {"Capa": capa, "Regla": regla, "Cumple": bool(cumple), "Detalle": detalle}


def reglas_silver(df_v, df_l, config, rechazos=None):
    """rechazos: {"ventas": (n_rechazados, n_total), "logística": (...)} para controlar la cuarentena."""
    cobertura = set(config["reglas"]["cobertura"])
    transporte = df_l["estado_evento"].isin(config["reglas"]["estados_con_transporte"])
    calif = df_v["calificacion_cliente"].dropna()
    fuera_v = sorted(set(df_v["ciudad"].dropna()) - cobertura)
    fuera_l = sorted(set(df_l["ciudad_destino"].dropna()) - cobertura)
    huerfanos = int((~df_l["pedido_id"].isin(df_v["pedido_id"])).sum())

    r = [
        _regla("Silver ventas", "id_venta único", df_v["id_venta"].is_unique,
               f"{df_v['id_venta'].duplicated().sum()} repetidos"),
        _regla("Silver ventas", "pedido_id único", df_v["pedido_id"].is_unique,
               f"{df_v['pedido_id'].duplicated().sum()} repetidos"),
        _regla("Silver ventas", "fecha_venta es datetime y sin nulos",
               pd.api.types.is_datetime64_any_dtype(df_v["fecha_venta"]) and df_v["fecha_venta"].notna().all(),
               f"{df_v['fecha_venta'].isna().sum()} nulos"),
        _regla("Silver ventas", "calificacion_cliente entre 1 y 5 (o nula)", calif.between(1, 5).all(),
               f"{(~calif.between(1, 5)).sum()} fuera de rango"),
        _regla("Silver ventas", "Montos no negativos", (df_v[MONTOS_VENTA] >= 0).all().all(),
               f"{(df_v[MONTOS_VENTA] < 0).sum().sum()} negativos"),
        _regla("Silver ventas", "Ciudades dentro de la cobertura", not fuera_v, ", ".join(fuera_v) or "todas"),
        _regla("Silver logística", "evento_id único", df_l["evento_id"].is_unique,
               f"{df_l['evento_id'].duplicated().sum()} repetidos"),
        _regla("Silver logística", "Sin filas duplicadas", not df_l.duplicated().any(),
               f"{df_l.duplicated().sum()} duplicadas"),
        _regla("Silver logística", "Sin columnas residuales del Excel",
               not any(c.startswith("Unnamed") for c in df_l.columns), ""),
        _regla("Silver logística", "Fechas con tipo datetime",
               all(pd.api.types.is_datetime64_any_dtype(df_l[c]) for c in ["fecha_evento", "fecha_prometida_entrega"]), ""),
    ]
    for col in ["centro_logistico", "ciudad_destino", "fecha_prometida_entrega"]:
        r.append(_regla("Silver logística", f"{col} sin nulos", df_l[col].notna().all(),
                        f"{df_l[col].isna().sum()} nulos"))
    for col in ["transportadora", "numero_guia"]:
        r.append(_regla("Silver logística", f"{col} con valor en estados de transporte",
                        df_l.loc[transporte, col].notna().all(), f"{df_l.loc[transporte, col].isna().sum()} nulos"))
        r.append(_regla("Silver logística", f"{col} sin valor antes del despacho",
                        df_l.loc[~transporte, col].isna().all(), f"{df_l.loc[~transporte, col].notna().sum()} con valor"))
    r += [
        _regla("Silver logística", "Ciudades destino dentro de la cobertura", not fuera_l, ", ".join(fuera_l) or "todas"),
        _regla("Silver logística", "Todo pedido logístico existe en ventas", huerfanos == 0, f"{huerfanos} eventos huérfanos"),
    ]
    max_pct = config.get("silver", {}).get("max_pct_rechazados", 5)
    for fuente, (n_rech, n_total) in (rechazos or {}).items():
        pct = n_rech / n_total * 100 if n_total else 0
        pct_txt = f"{pct:.2f}".replace(".", ",")
        r.append(_regla(f"Silver {fuente}", f"Registros en cuarentena ≤ {max_pct}%", pct <= max_pct,
                        f"{_m(n_rech)} de {_m(n_total)} ({pct_txt}%)" if n_rech else "0"))
    return r


def reglas_gold(df_v, df_l, df_gold_eventos, df_gold, marts=None):
    suma_silver = df_v["valor_neto"].sum()
    suma_gold = df_gold["valor_neto"].sum()
    montos_en_eventos = [c for c in MONTOS_VENTA if c in df_gold_eventos.columns]
    r = [
        _regla("Gold pedidos", "Una fila por venta", len(df_gold) == len(df_v), f"{_m(len(df_gold))} de {_m(len(df_v))}"),
        _regla("Gold pedidos", "pedido_id único", df_gold["pedido_id"].is_unique, ""),
        _regla("Gold pedidos", "valor_neto total igual al de Silver (sin duplicar)", abs(suma_gold - suma_silver) < 1,
               f"diferencia {_m(suma_gold - suma_silver)}"),
        _regla("Gold pedidos", "Todo pedido tiene resumen logístico", df_gold["n_eventos"].notna().all(),
               f"{df_gold['n_eventos'].isna().sum()} sin eventos"),
        _regla("Gold pedidos", "costo_envio sin nulos", df_gold["costo_envio"].notna().all(), ""),
        _regla("Gold eventos", "Una fila por evento de Silver", len(df_gold_eventos) == len(df_l),
               f"{_m(len(df_gold_eventos))} de {_m(len(df_l))}"),
        _regla("Gold eventos", "Sin montos de la venta repetidos", not montos_en_eventos, ", ".join(montos_en_eventos)),
    ]
    # Las tablas agregadas deben cuadrar con la tabla por pedido (mismos pedidos y mismo valor neto)
    for nombre, mart in (marts or {}).items():
        r.append(_regla(f"Gold {nombre}", "Suma de pedidos igual a Gold pedidos", int(mart["pedidos"].sum()) == len(df_gold),
                        f"{_m(mart['pedidos'].sum())} de {_m(len(df_gold))}"))
        if "valor_neto" in mart.columns:
            dif = mart["valor_neto"].sum() - suma_gold
            r.append(_regla(f"Gold {nombre}", "Suma de valor_neto igual a Gold pedidos", abs(dif) < 1, f"diferencia {_m(dif)}"))
    return r


def validar(reglas, logger):
    """Registra cada regla en el log y detiene el pipeline si alguna falla."""
    fallidas = [r for r in reglas if not r["Cumple"]]
    for r in reglas:
        nivel = logger.info if r["Cumple"] else logger.error
        nivel(f"[VALIDACIÓN] {'OK   ' if r['Cumple'] else 'FALLA'} {r['Capa']}: {r['Regla']} {('- ' + r['Detalle']) if r['Detalle'] else ''}")
    if fallidas:
        raise ValidacionError(f"{len(fallidas)} regla(s) de calidad no se cumplieron: "
                              + "; ".join(f"{r['Capa']}: {r['Regla']}" for r in fallidas))
    logger.info(f"[VALIDACIÓN] {len(reglas)} reglas cumplidas.")
