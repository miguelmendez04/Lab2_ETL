import pandas as pd
from src.utils.config import cargar_config

# Conocimiento del negocio usado para clasificar variables
MONETARIAS = ["precio_unitario", "valor_bruto", "valor_descuento", "valor_neto", "costo_envio"]
ORDINALES = ["calificacion_cliente"]  # escala 1-5: se almacena como número pero es categórica ordinal


def _m(x):
    """Entero con separador de miles: 50000 -> 50.000"""
    return f"{int(x):,}".replace(",", ".")


FILA_VENTAS = ("Una venta (transacción) de un cliente: un pedido_id con un producto, su cantidad, "
               "precios, descuento, canal, ciudad, medio de pago y la calificación opcional del cliente.")
FILA_LOGISTICA = ("Un evento u hito del flujo logístico de un pedido (recibido, pago aprobado, alistamiento, "
                  "despacho, tránsito, entrega...). Cada pedido_id tiene normalmente 10 eventos.")


# ---------------------------------------------------------------- clasificación
def clasificar_variable(df, col):
    c = col.lower()
    if c.startswith("unnamed"):
        return "Columna residual"
    if c.startswith("id_") or c.endswith("_id") or c == "numero_guia":
        return "Identificador"
    if c.startswith("fecha"):
        return "Fecha"
    if c.startswith("tiempo"):
        return "Tiempo (duración numérica)"
    if col in ORDINALES:
        return "Categórica ordinal"
    if pd.api.types.is_numeric_dtype(df[col]):
        return "Numérica"
    return "Categórica"


def clasificar_variables(df):
    return {col: clasificar_variable(df, col) for col in df.columns}


def listas_por_tipo(df):
    clases = clasificar_variables(df)
    return {
        "identificadores": [c for c, k in clases.items() if k == "Identificador"],
        "categoricas": [c for c, k in clases.items() if k.startswith("Categórica")],
        "numericas": [c for c, k in clases.items() if k == "Numérica" or k.startswith("Tiempo")],
        "fechas_tiempos": [c for c, k in clases.items() if k == "Fecha" or k.startswith("Tiempo")],
        "residuales": [c for c, k in clases.items() if k == "Columna residual"],
    }


def rango_fechas(df):
    rangos = {}
    for c in [c for c in df.columns if c.lower().startswith("fecha")]:
        fechas = pd.to_datetime(df[c], errors="coerce")
        rangos[c] = (fechas.min(), fechas.max())
    return rangos


def tabla_estructura(df):
    """Parte 3, puntos 3, 4, 5 y clasificación de cada variable."""
    clases = clasificar_variables(df)
    return pd.DataFrame({
        "Variable": df.columns,
        "Tipo de dato": [str(df[c].dtype) for c in df.columns],
        "Registros no nulos": [int(df[c].notna().sum()) for c in df.columns],
        "Clasificación": [clases[c] for c in df.columns],
    })


# ---------------------------------------------------------------- calidad (Parte 3.10 y 4)
def chequeos_calidad(df_ventas, df_logistica):
    """Parte 3, punto 10: otros aspectos de calidad del dato. Devuelve (chequeo, resultado)."""
    v, l = df_ventas, df_logistica
    bruto_mal = int(((v["precio_unitario"] * v["cantidad"]) - v["valor_bruto"]).abs().gt(1).sum())
    desc_mal = int(((v["valor_bruto"] * v["descuento_pct"] / 100) - v["valor_descuento"]).abs().gt(1).sum())
    neto_mal = int(((v["valor_bruto"] - v["valor_descuento"]) - v["valor_neto"]).abs().gt(1).sum())
    num_v = v.select_dtypes("number")
    num_l = l.select_dtypes("number")
    negativos = int((num_v < 0).sum().sum() + (num_l < 0).sum().sum())
    sin_log = int((~v["pedido_id"].isin(l["pedido_id"])).sum())
    sin_venta = int((~l["pedido_id"].drop_duplicates().isin(v["pedido_id"])).sum())
    eventos = l.groupby("pedido_id").size()
    estados = l.groupby("pedido_id")["estado_evento"].nunique()
    n_estados = l["estado_evento"].nunique()
    costo_por_pedido = l.groupby("pedido_id")["costo_envio"].nunique()
    ciudad_v = v.set_index("pedido_id")["ciudad"]
    ciudad_l = l.dropna(subset=["ciudad_destino"]).groupby("pedido_id")["ciudad_destino"].first()
    ciudad_distinta = int((ciudad_v.reindex(ciudad_l.index) != ciudad_l).sum())
    guias = l.dropna(subset=["numero_guia"]).groupby("numero_guia")["pedido_id"].nunique()
    residual = [c for c in l.columns if c.startswith("Unnamed")]
    valores_residual = l[residual[0]].dropna().unique().tolist() if residual else []
    fechas_ev = pd.to_datetime(l["fecha_evento"], errors="coerce")
    no_convertibles = int((fechas_ev.isna() & l["fecha_evento"].notna()).sum())

    # Consistencia temporal (las fechas de logística se convierten solo para comparar, sin modificar el DataFrame)
    t = pd.DataFrame({"pedido_id": l["pedido_id"], "evento_id": l["evento_id"], "estado": l["estado_evento"],
                      "fecha_evento": fechas_ev,
                      "fecha_prometida": pd.to_datetime(l["fecha_prometida_entrega"], errors="coerce")})
    t = t.merge(v[["pedido_id", "fecha_venta"]], on="pedido_id", how="left").sort_values(["pedido_id", "evento_id"])
    antes_venta = int((t["fecha_evento"] < t["fecha_venta"]).sum())
    prometida_mal = int(t.drop_duplicates("pedido_id").eval("fecha_prometida <= fecha_venta").sum())
    retrocesos = t.dropna(subset=["fecha_evento"]).groupby("pedido_id")["fecha_evento"].diff().dt.total_seconds().lt(0)
    pedidos_desordenados = int(t.loc[retrocesos[retrocesos].index, "pedido_id"].nunique())
    primer_estado = t.groupby("pedido_id")["estado"].first().value_counts()

    return [
        ("valor_bruto = precio_unitario × cantidad", f"{_m(len(v) - bruto_mal)} de {_m(len(v))} cumplen ({bruto_mal} inconsistentes)"),
        ("valor_descuento = valor_bruto × descuento_pct / 100", f"{_m(len(v) - desc_mal)} de {_m(len(v))} cumplen ({desc_mal} inconsistentes)"),
        ("valor_neto = valor_bruto − valor_descuento", f"{_m(len(v) - neto_mal)} de {_m(len(v))} cumplen ({neto_mal} inconsistentes)"),
        ("Valores negativos en variables numéricas", f"{negativos}"),
        ("Integridad referencial por pedido_id", f"{sin_log} ventas sin eventos logísticos; {sin_venta} pedidos logísticos sin venta"),
        ("Ciudad de la venta vs ciudad_destino logística", f"{ciudad_distinta} pedidos con ciudad distinta"),
        ("Eventos por pedido", f"mín {eventos.min()}, máx {eventos.max()}, moda {eventos.mode()[0]}"),
        (f"Pedidos que no pasan por los {n_estados} estados", f"{int((estados < n_estados).sum())} pedidos con trazabilidad incompleta"),
        ("costo_envio constante dentro de cada pedido", f"{_m((costo_por_pedido == 1).sum())} de {_m(len(costo_por_pedido))} pedidos "
                                                        "(se repite en cada evento: no sumar por evento)"),
        ("numero_guia compartido por pedidos distintos", f"{int((guias > 1).sum())}: {', '.join(guias[guias > 1].index)}" if (guias > 1).any() else "0"),
        ("Fechas de logística almacenadas como texto", f"fecha_evento y fecha_prometida_entrega son {l['fecha_evento'].dtype}; "
                                                      f"{no_convertibles} valores no convertibles a fecha"),
        ("Columna residual del Excel", f"{residual[0]}, con un único valor: {valores_residual}" if residual else "No hay"),
        ("Eventos con fecha anterior a la venta", f"{_m(antes_venta)}"),
        ("Pedidos con fecha prometida igual o anterior a la venta", f"{_m(prometida_mal)}"),
        ("Pedidos con eventos fuera de orden cronológico (según evento_id)", f"{_m(pedidos_desordenados)}"),
        ("Primer evento de cada pedido", ", ".join(f"{k}: {_m(c)}" for k, c in primer_estado.items())),
    ]


def tabla_nulos(df):
    """4.1: cantidad y porcentaje de nulos de cada variable, de mayor a menor."""
    nulos = df.isnull().sum()
    return (pd.DataFrame({"Variable": nulos.index,
                          "Cantidad nulos": nulos.values.astype(int),
                          "Porcentaje (%)": (nulos.values / len(df) * 100)})
            .sort_values(["Porcentaje (%)", "Variable"], ascending=[False, True])
            .reset_index(drop=True))


def diagnostico_nulos(df_ventas, df_logistica, config_path="config/config.yaml"):
    """4.1: qué nulos son normales por el proceso y cuáles son un problema de calidad (con evidencia)."""
    v, l = df_ventas, df_logistica
    estados_transporte = cargar_config(config_path)["reglas"]["estados_con_transporte"]
    fisica = v["canal"] == "Tienda física"
    pre = ~l["estado_evento"].isin(estados_transporte)
    tiempo_nulo = l.loc[l["tiempo_etapa_horas"].isna(), "estado_evento"].value_counts()
    obs_sin_inc = int((l["observacion"].notna() & l["incidencia"].isna()).sum())
    filas = [
        ("df_ventas", "id_tienda", "Normal",
         f"Es nulo en {_m(v.loc[~fisica, 'id_tienda'].isna().sum())} de {_m((~fisica).sum())} ventas web/app y en "
         f"{_m(v.loc[fisica, 'id_tienda'].isna().sum())} de {_m(fisica.sum())} ventas en tienda física: solo aplica a tienda física."),
        ("df_ventas", "calificacion_cliente", "Normal",
         "Calificar es opcional para el cliente. Debe tenerse en cuenta que los promedios solo representan a quien calificó."),
        ("df_logistica", "transportadora / numero_guia", "Normal antes del despacho",
         f"Nulos antes del despacho: {_m(l.loc[pre, 'transportadora'].isna().sum())} / {_m(l.loc[pre, 'numero_guia'].isna().sum())} "
         f"(el 100% de esos eventos): aún no hay transporte asignado."),
        ("df_logistica", "transportadora / numero_guia", "Problema",
         f"Nulos en estados de transporte (Despachado en adelante): {int(l.loc[~pre, 'transportadora'].isna().sum())} / "
         f"{int(l.loc[~pre, 'numero_guia'].isna().sum())}. Un pedido despachado debe tener transportadora y guía."),
        ("df_logistica", "tiempo_etapa_horas", "Normal",
         f"Los {_m(tiempo_nulo.sum())} nulos están en: " + ", ".join(f"{k} ({_m(c)})" for k, c in tiempo_nulo.items())
         + ". Es el primer evento y no tiene etapa previa."),
        ("df_logistica", "incidencia", "Normal", "Solo se registra cuando hay una novedad."),
        ("df_logistica", "observacion", "Normal",
         f"Solo se registra cuando hay algo que anotar ({_m(obs_sin_inc)} observaciones existen sin incidencia)."),
        ("df_logistica", "centro_logistico, ciudad_destino, fecha_prometida_entrega", "Problema",
         "Son datos del pedido y deben existir en todos sus eventos (son constantes dentro del pedido)."),
        ("df_logistica", "fecha_evento", "Problema", "Todo evento ocurrido debe tener fecha y hora."),
    ]
    for c in [c for c in l.columns if c.startswith("Unnamed")]:
        filas.append(("df_logistica", c, "Problema (columna residual)",
                      f"{_m(l[c].isna().sum())} nulos de {_m(len(l))}: columna sin nombre que no pertenece al modelo de datos."))
    return pd.DataFrame(filas, columns=["DataFrame", "Variable", "Tipo de nulo", "Interpretación"])


def tabla_cardinalidad(df):
    """4.2: nunique() de cada variable y su evaluación."""
    clases = clasificar_variables(df)
    filas = []
    for col in df.columns:
        unicos = int(df[col].nunique())
        no_nulos = int(df[col].notna().sum())
        clase = clases[col]
        if clase == "Identificador":
            if unicos == no_nulos:
                evaluacion = "Identificador único"
            elif unicos >= 0.4 * no_nulos:
                evaluacion = "Identificador con repetidos (alta cardinalidad)"
            else:
                evaluacion = f"Clave que se repite (~{no_nulos / unicos:.1f} filas por valor)".replace(".", ",")
        elif clase.startswith("Categórica"):
            if unicos <= 10:
                evaluacion = "Baja cardinalidad (pocos valores posibles)"
            elif unicos <= 50:
                evaluacion = "Cardinalidad media"
            else:
                evaluacion = "Alta cardinalidad"
        elif clase == "Columna residual":
            evaluacion = "Sin información útil"
        elif clase == "Fecha":
            evaluacion = "Fecha (casi única por registro)" if unicos > 0.5 * no_nulos else "Fecha que se repite"
        else:
            evaluacion = "Numérica discreta (pocos valores)" if unicos <= 12 else "Numérica continua"
        filas.append({"Variable": col, "Clasificación": clase, "Valores únicos": unicos,
                      "% sobre registros": unicos / len(df) * 100, "Evaluación": evaluacion})
    return (pd.DataFrame(filas)
            .sort_values("Valores únicos", ascending=False)
            .reset_index(drop=True))


def analizar_duplicados(df_ventas, df_logistica):
    """4.3: filas completamente duplicadas e identificadores que deberían ser únicos."""
    l = df_logistica
    repetidos_evento = l[l["evento_id"].duplicated(keep=False)]
    exactos_evento = repetidos_evento[repetidos_evento.duplicated(keep=False)]["evento_id"].nunique()
    distintos_evento = repetidos_evento["evento_id"].nunique() - exactos_evento
    guias = l.dropna(subset=["numero_guia"]).groupby("numero_guia")["pedido_id"].nunique()
    return {
        "ventas_filas_duplicadas": int(df_ventas.duplicated().sum()),
        "ventas_id_venta_repetidos": int(df_ventas["id_venta"].duplicated().sum()),
        "ventas_pedido_id_repetidos": int(df_ventas["pedido_id"].duplicated().sum()),
        "logistica_filas_duplicadas": int(l.duplicated().sum()),
        "logistica_evento_id_repetidos": int(l["evento_id"].duplicated().sum()),
        "logistica_evento_id_repetidos_por_fila_identica": int(exactos_evento),
        "logistica_evento_id_repetidos_con_contenido_distinto": int(distintos_evento),
        "logistica_pedido_id_repetidos": int(l["pedido_id"].duplicated().sum()),
        "logistica_guias_compartidas": guias[guias > 1].index.tolist(),
    }


def tabla_tipos(df):
    """4.4: coherencia del tipo detectado por Python con el significado de la variable."""
    filas = []
    for col in df.columns:
        clase = clasificar_variable(df, col)
        s = df[col]
        es_num = pd.api.types.is_numeric_dtype(s)
        es_fecha = pd.api.types.is_datetime64_any_dtype(s)
        if clase == "Fecha":
            diag = "OK (datetime)" if es_fecha else f"REVISAR: fecha almacenada como {s.dtype}, convertir a datetime"
        elif clase == "Identificador":
            diag = ("OK: clave técnica entera (no se opera aritméticamente)" if es_num else "OK (texto)")
        elif col in MONETARIAS:
            diag = "OK (monetaria numérica)" if es_num else "REVISAR: monto no numérico"
        elif clase == "Categórica ordinal":
            diag = f"REVISAR: escala entera 1-5 almacenada como {s.dtype} por los nulos; usar Int64"
        elif clase == "Columna residual":
            diag = "REVISAR: eliminar (no pertenece al modelo de datos)"
        elif clase.startswith("Tiempo"):
            diag = "OK: duración en horas (numérica), no es una fecha"
        elif clase == "Numérica":
            diag = "OK (numérica)" if es_num else "REVISAR: debería ser numérica"
        else:
            diag = "OK (texto)" if not es_num else "REVISAR: categoría almacenada como número"
        filas.append({"Variable": col, "Tipo detectado": str(s.dtype), "Diagnóstico": diag})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- Parte 5
def resumen_numerico(df, columnas):
    cols = [c for c in columnas if c in df.columns]
    res = df[cols].describe().T[["count", "mean", "std", "min", "25%", "50%", "75%", "max"]]
    res.columns = ["count", "mean", "std", "min", "p25", "mediana", "p75", "max"]
    return res


def resumen_categoricas(df):
    """5.2: número de valores únicos, categorías, frecuencia y categoría más frecuente."""
    filas = []
    for col in listas_por_tipo(df)["categoricas"]:
        frec = df[col].value_counts()
        filas.append({"Variable": col, "Valores únicos": int(df[col].nunique()),
                      "Categoría más frecuente": frec.index[0], "Frecuencia": int(frec.iloc[0]),
                      "% de no nulos": frec.iloc[0] / frec.sum() * 100,
                      "Categorías": ", ".join(map(str, frec.index))})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- funciones que imprimen (main.py)
def comprension_inicial(df_ventas, df_logistica):
    """PARTE 3. COMPRENSIÓN INICIAL DE LOS DATASETS (20 puntos)"""
    print("\n" + "#"*60)
    print(" PARTE 3: COMPRENSIÓN INICIAL DE LOS DATASETS")
    print("#"*60)

    for nombre, df in [("df_ventas", df_ventas), ("df_logistica", df_logistica)]:
        tipos = listas_por_tipo(df)
        print(f"\n---> Exploración de {nombre} <---")
        print(f"1. Registros (filas): {df.shape[0]}")
        print(f"2. Variables (columnas): {df.shape[1]}")
        print(f"3. Nombres de variables: {list(df.columns)}")
        print("\n4 y 5. Tipos de datos y registros no nulos:")
        print(tabla_estructura(df).to_string(index=False))
        print(f"\n6. Identificadores: {tipos['identificadores']}")
        print(f"7. Variables categóricas: {tipos['categoricas']}")
        print(f"8. Variables numéricas: {tipos['numericas']}")
        print(f"9. Variables de fecha / tiempo: {tipos['fechas_tiempos']}")
        if tipos["residuales"]:
            print(f"   ATENCIÓN: columnas sin nombre (residuo del Excel): {tipos['residuales']}")
        for col, (ini, fin) in rango_fechas(df).items():
            print(f"   Rango de fechas en '{col}': {ini} a {fin}")

    print("\n10. Otros aspectos de calidad del dato:")
    for chequeo, resultado in chequeos_calidad(df_ventas, df_logistica):
        print(f"   - {chequeo}: {resultado}")

    print("\n--- ¿QUÉ REPRESENTA UNA FILA? ---")
    print(f"• df_ventas: {FILA_VENTAS}")
    print(f"• df_logistica: {FILA_LOGISTICA}")


def perfil_calidad_datos(df_ventas, df_logistica):
    """PARTE 4. PERFIL INICIAL DE CALIDAD DEL DATO (25 puntos) - 4.1, 4.2 y 4.3. No elimina ni imputa."""
    print("\n" + "#"*60)
    print(" PARTE 4: PERFIL INICIAL DE CALIDAD DEL DATO")
    print("#"*60)

    for nombre, df in [("df_ventas", df_ventas), ("df_logistica", df_logistica)]:
        print(f"\n=== {nombre} ===")
        print("\n--- 4.1 Valores nulos (de mayor a menor porcentaje) ---")
        print(tabla_nulos(df).to_string(index=False))
        print("\n--- 4.2 Valores únicos (nunique) y cardinalidad ---")
        print(tabla_cardinalidad(df).to_string(index=False))

    print("\n--- 4.1 Interpretación de los nulos ---")
    print(diagnostico_nulos(df_ventas, df_logistica).to_string(index=False))

    print("\n--- 4.3 Duplicados (no se eliminan en esta etapa) ---")
    for clave, valor in analizar_duplicados(df_ventas, df_logistica).items():
        print(f"   {clave}: {valor}")
    print("   Nota: pedido_id se repite en logística por diseño (varios eventos por pedido).")


def revisar_tipos(df_ventas, df_logistica):
    """PARTE 4.4. TIPOS DE DATOS"""
    print("\n" + "#"*60)
    print(" 4.4 REVISIÓN DE TIPOS DE DATOS")
    print("#"*60)
    for nombre, df in [("df_ventas", df_ventas), ("df_logistica", df_logistica)]:
        print(f"\n=== {nombre} ===")
        print(tabla_tipos(df).to_string(index=False))


def estadisticos_descriptivos(df_ventas, df_logistica):
    """PARTE 5. ESTADÍSTICOS DESCRIPTIVOS Y RESÚMENES (15 puntos)"""
    print("\n" + "#"*60)
    print(" PARTE 5: ESTADÍSTICOS DESCRIPTIVOS Y RESÚMENES")
    print("#"*60)

    for nombre, df in [("df_ventas", df_ventas), ("df_logistica", df_logistica)]:
        print(f"\n--- 5.1 Variables numéricas de {nombre} ---")
        print(resumen_numerico(df, listas_por_tipo(df)["numericas"]))
        print(f"\n--- 5.2 Variables categóricas de {nombre} ---")
        print(resumen_categoricas(df).drop(columns="Categorías").to_string(index=False))

    print("\n--- df_ventas ---")
    for c in ["ciudad", "canal", "categoria"]:
        print(f"\nVentas por {c}:\n{df_ventas[c].value_counts()}")
    print(f"\nDistribución de cantidad:\n{df_ventas['cantidad'].value_counts().sort_index()}")
    print("\nResumen de variables monetarias:")
    print(resumen_numerico(df_ventas, ["precio_unitario", "valor_bruto", "valor_descuento", "valor_neto"]))
    print(f"\nDistribución de calificacion_cliente (no nulos):\n{df_ventas['calificacion_cliente'].value_counts().sort_index()}")

    print("\n--- df_logistica ---")
    for c in ["estado_evento", "ciudad_destino", "transportadora", "incidencia"]:
        print(f"\nFrecuencia de {c}:\n{df_logistica[c].value_counts()}")
    print("\nResumen de tiempo_etapa_horas y costo_envio (por evento):")
    print(resumen_numerico(df_logistica, ["tiempo_etapa_horas", "costo_envio"]))
    print("\ncosto_envio por pedido (se repite en cada evento, se toma una vez por pedido):")
    print(df_logistica.groupby("pedido_id")["costo_envio"].first().describe())
