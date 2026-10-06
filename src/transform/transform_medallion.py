import pandas as pd
from src.utils.config import cargar_config
from src.utils.logger import setup_logger
from src.utils.manifiesto import escribir_linaje
from src.load.load import guardar_capa, leer_bronze
from src.transform.validaciones import MONTOS_VENTA, reglas_silver, reglas_gold, validar

COLUMNAS_INCIDENCIAS = ["fuente", "nivel", "clave", "pedido_id", "tipo", "accion", "detalle"]


def _limpiar_texto(serie):
    """Quita espacios al inicio/fin y colapsa espacios internos repetidos."""
    return serie.str.strip().str.replace(r"\s+", " ", regex=True)


def _incidencias(df, mascara, fuente, nivel, clave, tipo, accion, detalle=""):
    """Registra en la tabla de incidencias las filas de df que cumplen la máscara."""
    sel = df.loc[mascara]
    return pd.DataFrame({
        "fuente": fuente, "nivel": nivel, "clave": sel[clave].astype(str),
        "pedido_id": sel["pedido_id"].astype(str), "tipo": tipo, "accion": accion,
        "detalle": detalle if isinstance(detalle, str) else detalle.loc[mascara].astype(str),
    })


def _cuarentena(df, reglas, fuente, nivel, clave):
    """
    Separa las filas que no cumplen alguna regla de fila. Devuelve (filas válidas, rechazadas, incidencias).
    reglas: {motivo: máscara booleana de filas que NO cumplen}.
    """
    motivos = pd.Series("", index=df.index)
    for motivo, mascara in reglas.items():
        motivos = motivos.where(~mascara, motivos.where(motivos == "", motivos + "; ") + motivo)
    rechazar = motivos != ""
    rechazados = df.loc[rechazar].assign(motivo_rechazo=motivos[rechazar])
    inc = _incidencias(df, rechazar, fuente, nivel, clave, "Registro rechazado", "Enviado a cuarentena", motivos)
    return df.loc[~rechazar], rechazados, inc


# ---------------------------------------------------------------- SILVER
def silver_ventas(df_ventas_raw, config, logger):
    """Limpieza de ventas. Devuelve (ventas limpias, rechazadas, incidencias)."""
    df_v = df_ventas_raw.copy().drop_duplicates()
    logger.info(f"[SILVER] Ventas: filas idénticas eliminadas = {len(df_ventas_raw) - len(df_v)}")

    df_v["fecha_venta"] = pd.to_datetime(df_v["fecha_venta"], errors="coerce")
    # calificacion_cliente es una escala entera 1-5: entero nullable para conservar los nulos
    df_v["calificacion_cliente"] = df_v["calificacion_cliente"].astype("Int64")
    # Estandarización: el EDA mostró categorías consistentes, se normalizan espacios
    for col in ["ciudad", "canal", "categoria", "producto", "medio_pago", "id_cliente", "id_tienda"]:
        df_v[col] = _limpiar_texto(df_v[col])

    # Reglas de fila: lo que no cumple va a cuarentena en lugar de detener todo el pipeline
    calif = df_v["calificacion_cliente"]
    df_v, rechazados, inc = _cuarentena(df_v, {
        "fecha_venta nula o inválida": df_v["fecha_venta"].isna(),
        "ciudad fuera de cobertura": ~df_v["ciudad"].isin(config["reglas"]["cobertura"]),
        "montos negativos": (df_v[MONTOS_VENTA] < 0).any(axis=1),
        "montos inconsistentes": (((df_v["precio_unitario"] * df_v["cantidad"]) - df_v["valor_bruto"]).abs() > 1)
                                 | (((df_v["valor_bruto"] - df_v["valor_descuento"]) - df_v["valor_neto"]).abs() > 1),
        "calificacion fuera de 1-5": calif.notna() & ~calif.between(1, 5).fillna(False),
        "id_venta repetido": df_v["id_venta"].duplicated(),
        "pedido_id repetido": df_v["pedido_id"].duplicated(),
    }, "ventas", "venta", "id_venta")
    if len(rechazados):
        logger.warning(f"[SILVER] Ventas en cuarentena: {len(rechazados)}")

    # SE MANTIENEN NULOS (tienen significado válido en el proceso):
    #  calificacion_cliente: el cliente no calificó (43%); imputar sesgaría la satisfacción
    #  id_tienda: solo aplica a canal "Tienda física"
    return df_v, rechazados, inc


def silver_logistica(df_logistica_raw, config, logger, pedidos_validos):
    """Limpieza de logística. Devuelve (eventos limpios, rechazados, incidencias)."""
    inc = []
    estados_transporte = config["reglas"]["estados_con_transporte"]

    duplicadas = df_logistica_raw.duplicated()
    inc.append(_incidencias(df_logistica_raw, duplicadas, "logistica", "evento", "evento_id",
                            "Fila duplicada", "Eliminada"))
    df_l = df_logistica_raw.loc[~duplicadas].copy()
    logger.info(f"[SILVER] Logística: filas idénticas eliminadas = {int(duplicadas.sum())}")

    # Columna basura del Excel (1 celda con la fórmula =AI(""), 99.998% nula)
    residuales = [c for c in df_l.columns if c.startswith("Unnamed")]
    for c in residuales:
        inc.append(pd.DataFrame([{"fuente": "logistica", "nivel": "columna", "clave": c, "pedido_id": "",
                                  "tipo": "Columna residual del Excel", "accion": "Eliminada",
                                  "detalle": f"{int(df_l[c].notna().sum())} celda(s) con datos"}]))
    df_l = df_l.drop(columns=residuales)

    # evento_id repetido con contenido distinto: se conserva la fila más completa (menos nulos)
    df_l["_nulos"] = df_l.isnull().sum(axis=1)
    df_l = df_l.sort_values(["evento_id", "_nulos"])
    descartadas = df_l["evento_id"].duplicated(keep="first")
    inc.append(_incidencias(df_l, descartadas, "logistica", "evento", "evento_id",
                            "evento_id repetido con contenido distinto", "Se conservó la versión más completa"))
    df_l = df_l.loc[~descartadas].drop(columns="_nulos").sort_values("evento_id").reset_index(drop=True)
    logger.info(f"[SILVER] evento_id repetidos con contenido distinto resueltos: {int(descartadas.sum())}")

    # Tipado de fechas (llegaban como texto)
    for col in ["fecha_evento", "fecha_prometida_entrega"]:
        df_l[col] = pd.to_datetime(df_l[col], errors="coerce")

    for col in ["estado_evento", "centro_logistico", "ciudad_destino", "transportadora",
                "numero_guia", "incidencia", "observacion"]:
        df_l[col] = _limpiar_texto(df_l[col])

    # Nulos recuperables: estos datos son iguales en todos los eventos de un pedido
    for col in ["centro_logistico", "ciudad_destino", "fecha_prometida_entrega"]:
        nulos = df_l[col].isna()
        df_l[col] = df_l.groupby("pedido_id")[col].transform("first")
        inc.append(_incidencias(df_l, nulos, "logistica", "evento", "evento_id", f"{col} nulo",
                                "Recuperado del mismo pedido"))

    # transportadora / numero_guia: el nulo es normal ANTES del despacho, pero es un problema
    # de calidad en los estados de transporte. Solo se completan esos, con el valor del mismo pedido.
    en_transporte = df_l["estado_evento"].isin(estados_transporte)
    for col in ["transportadora", "numero_guia"]:
        nulos = en_transporte & df_l[col].isna()
        valor_pedido = df_l.groupby("pedido_id")[col].transform("first")
        df_l.loc[en_transporte, col] = df_l.loc[en_transporte, col].fillna(valor_pedido[en_transporte])
        inc.append(_incidencias(df_l, nulos, "logistica", "evento", "evento_id",
                                f"{col} nulo en estado de transporte", "Completado con el valor del pedido"))

    # Nulo = ausencia de novedad, se vuelve categoría explícita
    df_l["incidencia"] = df_l["incidencia"].fillna("Sin incidencia")
    df_l["observacion"] = df_l["observacion"].fillna("Sin observación")

    # SE MANTIENEN NULOS (tienen significado válido en el proceso):
    #  transportadora / numero_guia antes del despacho: aún no hay transporte asignado
    #  tiempo_etapa_horas: "Pedido recibido" es el primer evento y no tiene etapa previa
    #  fecha_evento: no es recuperable desde otro evento del pedido (se registra como incidencia)
    inc.append(_incidencias(df_l, df_l["fecha_evento"].isna(), "logistica", "evento", "evento_id",
                            "fecha_evento nula", "Se mantiene nulo (no recuperable)", df_l["estado_evento"]))

    # Reglas de fila: eventos de pedidos sin venta válida o fuera de cobertura van a cuarentena
    df_l, rechazados, inc_rech = _cuarentena(df_l, {
        "pedido sin venta válida": ~df_l["pedido_id"].isin(pedidos_validos),
        "ciudad_destino fuera de cobertura": ~df_l["ciudad_destino"].isin(config["reglas"]["cobertura"]),
    }, "logistica", "evento", "evento_id")
    inc.append(inc_rech)
    if len(rechazados):
        logger.warning(f"[SILVER] Eventos logísticos en cuarentena: {len(rechazados)}")

    # Problemas a nivel de pedido: no se pueden corregir, se documentan para que el negocio los revise
    estados = df_l.groupby("pedido_id")["estado_evento"].agg(set)
    todos = set(df_l["estado_evento"].unique())
    faltantes = estados.map(lambda s: ", ".join(sorted(todos - s)))
    ped = pd.DataFrame({"pedido_id": faltantes.index, "faltan": faltantes.values})
    inc.append(_incidencias(ped, ped["faltan"] != "", "logistica", "pedido", "pedido_id",
                            "Trazabilidad incompleta", "Marcado en Gold", "Faltan: " + ped["faltan"]))
    entregado = df_l[df_l["estado_evento"] == "Entregado"].groupby("pedido_id")["fecha_evento"].apply(lambda s: s.isna().all())
    ped = pd.DataFrame({"pedido_id": entregado.index, "sin_fecha": entregado.values})
    inc.append(_incidencias(ped, ped["sin_fecha"], "logistica", "pedido", "pedido_id",
                            "Evento Entregado sin fecha", "Sin fecha de entrega en Gold"))
    for guia in guias_compartidas(df_l):
        ped = df_l.loc[df_l["numero_guia"] == guia, ["pedido_id"]].drop_duplicates()
        inc.append(_incidencias(ped, pd.Series(True, index=ped.index), "logistica", "pedido", "pedido_id",
                                "numero_guia compartido entre pedidos", "Marcado en Gold", guia))

    incidencias = pd.concat([i for i in inc if len(i)], ignore_index=True) if any(len(i) for i in inc) \
        else pd.DataFrame(columns=COLUMNAS_INCIDENCIAS)
    return df_l, rechazados, incidencias


def guias_compartidas(df_logistica):
    """numero_guia usado por más de un pedido: no se puede saber cuál es el correcto, se marca en Gold."""
    guias = df_logistica.dropna(subset=["numero_guia"]).groupby("numero_guia")["pedido_id"].nunique()
    return guias[guias > 1].index.tolist()


# ---------------------------------------------------------------- GOLD
def capa_gold(df_ventas_transformado, df_logisitica_transformado):
    """
    Integración por pedido_id:
    - eventos: una fila por evento con los datos descriptivos de la venta (sin montos de la venta).
    - pedidos: una fila por pedido con la venta completa y el resumen logístico.
    """
    # Detalle por evento: sin montos de la venta, porque se repetirían en cada evento del pedido
    # y sumarlos multiplicaría las ventas. Los montos están en la tabla por pedido.
    df_gold_eventos = pd.merge(df_ventas_transformado.drop(columns=MONTOS_VENTA), df_logisitica_transformado,
                               on="pedido_id", how="left", validate="one_to_many")

    compartidas = guias_compartidas(df_logisitica_transformado)
    log_ord = df_logisitica_transformado.sort_values(["pedido_id", "evento_id"])
    resumen_log = log_ord.groupby("pedido_id").agg(
        n_eventos=("evento_id", "count"),
        n_estados=("estado_evento", "nunique"),
        estado_final=("estado_evento", "last"),
        fecha_ultimo_evento=("fecha_evento", "max"),
        fecha_prometida_entrega=("fecha_prometida_entrega", "first"),
        centro_logistico=("centro_logistico", "first"),
        ciudad_destino=("ciudad_destino", "first"),
        transportadora=("transportadora", "first"),
        numero_guia=("numero_guia", "first"),
        costo_envio=("costo_envio", "first"),
        tiempo_total_horas=("tiempo_etapa_horas", "sum"),
        n_incidencias=("incidencia", lambda s: (s != "Sin incidencia").sum()),
    ).reset_index()
    resumen_log["trazabilidad_completa"] = resumen_log["n_estados"] == df_logisitica_transformado["estado_evento"].nunique()
    resumen_log["guia_compartida"] = resumen_log["numero_guia"].isin(compartidas)
    df_gold = df_ventas_transformado.merge(resumen_log, on="pedido_id", how="left", validate="one_to_one")

    # Retraso: fecha real de entrega vs fecha prometida
    entregas = (df_logisitica_transformado[df_logisitica_transformado["estado_evento"] == "Entregado"]
                .groupby("pedido_id")["fecha_evento"].max()
                .rename("fecha_entrega").reset_index())
    df_gold = df_gold.merge(entregas, on="pedido_id", how="left", validate="one_to_one")
    df_gold["dias_retraso"] = ((df_gold["fecha_entrega"] - df_gold["fecha_prometida_entrega"])
                               .dt.total_seconds() / 86400).round(2)
    df_gold["entregado_tarde"] = (df_gold["dias_retraso"] > 0).astype("boolean").mask(df_gold["dias_retraso"].isna())

    # Indicadores de servicio
    con_entregado = set(df_logisitica_transformado.loc[df_logisitica_transformado["estado_evento"] == "Entregado", "pedido_id"])
    df_gold["entregado"] = df_gold["pedido_id"].isin(con_entregado)
    df_gold["dias_ciclo_entrega"] = ((df_gold["fecha_entrega"] - df_gold["fecha_venta"]).dt.total_seconds() / 86400).round(2)
    df_gold["dias_prometidos"] = ((df_gold["fecha_prometida_entrega"] - df_gold["fecha_venta"]).dt.total_seconds() / 86400).round(2)
    df_gold["mes_venta"] = df_gold["fecha_venta"].dt.strftime("%Y-%m")
    return df_gold_eventos, df_gold


def marts_gold(df_gold):
    """
    Tablas agregadas listas para consumo (informe, Excel, Power BI). Se calculan desde la tabla
    por pedido, así que no duplican montos.
    """
    g = df_gold.assign(con_incidencia=df_gold["n_incidencias"] > 0,
                       retraso_tardias=df_gold["dias_retraso"].where(df_gold["entregado_tarde"] == True))
    pct = lambda s: s.mean() * 100

    kpi_mensual = g.groupby("mes_venta").agg(
        pedidos=("pedido_id", "count"), clientes=("id_cliente", "nunique"), unidades=("cantidad", "sum"),
        valor_bruto=("valor_bruto", "sum"), valor_descuento=("valor_descuento", "sum"), valor_neto=("valor_neto", "sum"),
        ticket_promedio=("valor_neto", "mean"), costo_envio_total=("costo_envio", "sum"),
        pct_entregas_tardias=("entregado_tarde", pct), dias_retraso_promedio=("dias_retraso", "mean"),
        ciclo_mediano_dias=("dias_ciclo_entrega", "median"), pct_pedidos_con_incidencia=("con_incidencia", pct),
        calificacion_promedio=("calificacion_cliente", "mean"),
    ).reset_index()

    desempeno_transportadora = g.groupby("transportadora").agg(
        pedidos=("pedido_id", "count"), pct_entregas_tardias=("entregado_tarde", pct),
        retraso_promedio_tardias=("retraso_tardias", "mean"), ciclo_mediano_dias=("dias_ciclo_entrega", "median"),
        tiempo_total_mediano_horas=("tiempo_total_horas", "median"), costo_envio_promedio=("costo_envio", "mean"),
        pct_pedidos_con_incidencia=("con_incidencia", pct), calificacion_promedio=("calificacion_cliente", "mean"),
    ).reset_index().sort_values("pct_entregas_tardias", ascending=False)

    ventas_ciudad_canal = g.groupby(["ciudad", "canal"]).agg(
        pedidos=("pedido_id", "count"), unidades=("cantidad", "sum"), valor_neto=("valor_neto", "sum"),
        ticket_promedio=("valor_neto", "mean"), pct_entregas_tardias=("entregado_tarde", pct),
    ).reset_index()
    ventas_ciudad_canal["pct_valor_neto_total"] = ventas_ciudad_canal["valor_neto"] / g["valor_neto"].sum() * 100
    ventas_ciudad_canal = ventas_ciudad_canal.sort_values("valor_neto", ascending=False)

    marts = {"kpi_mensual": kpi_mensual, "desempeno_transportadora": desempeno_transportadora,
             "ventas_ciudad_canal": ventas_ciudad_canal}
    for df in marts.values():
        cols = df.select_dtypes("float").columns
        df[cols] = df[cols].round(2)
    return marts


# ---------------------------------------------------------------- orquestación Bronze -> Silver -> Gold
def ejecutar_transformacion_medallion(config_path="config/config.yaml", carga=None, manifiesto=None):
    """
    PARTE 7. PROCESO DE TRANSFORMACIÓN DE DATOS (MEDALLION).
    Lee Bronze (la última carga o, con 'carga', una del histórico), construye Silver y Gold,
    valida cada capa antes de publicarla y deja el linaje en el manifiesto.
    """
    logger = setup_logger(config_path)
    config = cargar_config(config_path)
    paths = config["paths"]
    logger.info(f"PARTE 7: Transformación Medallion desde Bronze ({carga or 'última carga'})...")

    df_ventas_raw, df_logistica_raw = leer_bronze(config_path, carga)

    # SILVER
    df_ventas_transformado, rech_v, inc_v = silver_ventas(df_ventas_raw, config, logger)
    df_logisitica_transformado, rech_l, inc_l = silver_logistica(df_logistica_raw, config, logger,
                                                                 set(df_ventas_transformado["pedido_id"]))
    incidencias = pd.concat([d for d in [inc_v, inc_l] if len(d)], ignore_index=True)
    rechazos = {"ventas": (len(rech_v), len(df_ventas_raw)), "logística": (len(rech_l), len(df_logistica_raw))}

    reglas = reglas_silver(df_ventas_transformado, df_logisitica_transformado, config, rechazos)
    if manifiesto is not None:
        manifiesto.validaciones("silver", reglas)
    validar(reglas, logger)  # si alguna regla falla, se detiene aquí y no publica Silver

    compartidas = guias_compartidas(df_logisitica_transformado)
    if compartidas:
        logger.warning(f"[SILVER] numero_guia compartido por varios pedidos (se conserva y se marca en Gold): {compartidas}")

    silver_dir = paths["silver_dir"]
    guardar_capa(df_ventas_transformado, silver_dir, "df_ventas_transformado", config_path, manifiesto, "silver")
    guardar_capa(df_logisitica_transformado, silver_dir, "df_logistica_transformado", config_path, manifiesto, "silver")
    guardar_capa(incidencias, silver_dir, "incidencias_calidad", config_path, manifiesto, "silver")
    guardar_capa(rech_v, f"{silver_dir}/rechazados", "ventas_rechazadas", config_path, manifiesto, "silver")
    guardar_capa(rech_l, f"{silver_dir}/rechazados", "logistica_rechazada", config_path, manifiesto, "silver")
    logger.info(f"[SILVER] Publicado: {len(incidencias)} incidencias de calidad documentadas, "
                f"{len(rech_v) + len(rech_l)} registros en cuarentena.")

    # GOLD
    df_gold_eventos, df_gold = capa_gold(df_ventas_transformado, df_logisitica_transformado)
    marts = marts_gold(df_gold)
    reglas = reglas_gold(df_ventas_transformado, df_logisitica_transformado, df_gold_eventos, df_gold, marts)
    if manifiesto is not None:
        manifiesto.validaciones("gold", reglas)
    validar(reglas, logger)

    gold_dir = paths["gold_dir"]
    guardar_capa(df_gold_eventos, gold_dir, "eventos_gold", config_path, manifiesto, "gold")
    guardar_capa(df_gold, gold_dir, "ventas_logistica_gold", config_path, manifiesto, "gold")
    for nombre, mart in marts.items():
        guardar_capa(mart, gold_dir, nombre, config_path, manifiesto, "gold")
    logger.info(f"[GOLD] Eventos: {df_gold_eventos.shape} | Pedidos: {df_gold.shape} | Tablas agregadas: {list(marts)}")

    if manifiesto is not None:
        escribir_linaje(silver_dir, manifiesto)
        escribir_linaje(gold_dir, manifiesto)

    return df_ventas_transformado, df_logisitica_transformado, df_gold
