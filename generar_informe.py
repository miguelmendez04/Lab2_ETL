"""
Genera el informe del laboratorio (Markdown + HTML) a partir de las capas Medallion.
Todas las cifras se calculan con las mismas funciones del EDA (src/eda/eda_inspection.py)
y de las preguntas de negocio (src/eda/business_questions.py), para que el informe
no pueda contradecir al código.
Requisito: haber ejecutado antes main.py u orchestrator.py (genera data/bronze, silver y gold).
"""
import os
import markdown
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.eda import eda_inspection as eda
from src.eda.business_questions import calcular_preguntas_negocio
from src.transform.transform_medallion import MONTOS_VENTA, _limpiar_texto
from src.load.load import listar_cargas
from src.utils.manifiesto import leer_json
from src.utils.config import cargar_config

sns.set_theme(style="whitegrid")
plt.rcParams.update({"font.sans-serif": "Segoe UI", "font.family": "sans-serif"})


# ---------- Funciones de formato ----------
def n(x):
    """Número entero con separador de miles: 1234567 -> 1.234.567"""
    if pd.isna(x):
        return "-"
    return f"{int(round(x)):,}".replace(",", ".")


def pc(x, dec=1):
    """Porcentaje con coma decimal: 16.87 -> 16,9%"""
    if pd.isna(x):
        return "-"
    return f"{x:.{dec}f}".replace(".", ",") + "%"


def fnum(x, dec=2):
    """Número con separador de miles y coma decimal: 455950.16 -> 455.950,16"""
    if pd.isna(x):
        return "-"
    entero, _, decimales = f"{x:,.{dec}f}".partition(".")
    return entero.replace(",", ".") + ("," + decimales if decimales else "")


ORIGEN = {"extraccion": "extracción", "reproceso": "reproceso"}


def plural(k, singular, plural_):
    """Concordancia: 1 guía compartida / 2 guías compartidas"""
    return f"{n(k)} {singular if k == 1 else plural_}"


def fmt_auto(x):
    """Formato para tablas de detalle: decimales en valores pequeños (promedios), miles en el resto"""
    if isinstance(x, (bool,)) or not isinstance(x, (int, float)) and not hasattr(x, "dtype"):
        return str(x)
    if isinstance(x, float) and abs(x) < 100:
        return fnum(x, 2)
    return n(x)


def tabla_md(df, formatos=None):
    """DataFrame -> tabla Markdown; formatos = {columna: función de formato}"""
    formatos = formatos or {}
    cab = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    filas = []
    for fila in df.itertuples(index=False):
        celdas = [formatos[c](x) if c in formatos else str(x) for c, x in zip(df.columns, fila)]
        filas.append("| " + " | ".join(celdas) + " |")
    return "\n".join([cab, sep] + filas)


def serie_md(serie, nombre_indice, nombre_valor, formato=n):
    t = serie.rename_axis(nombre_indice).reset_index(name=nombre_valor)
    return tabla_md(t, {nombre_valor: formato})


def conteo(serie, nombre):
    """Tabla de frecuencias con porcentaje"""
    frec = serie.value_counts()
    t = pd.DataFrame({nombre: frec.index, "registros": frec.values,
                      "%": frec.values / frec.sum() * 100})
    return tabla_md(t, {"registros": n, "%": pc})


def lista_md(items):
    items = list(items)
    return ", ".join(f"`{x}`" for x in items) if items else "_ninguna_"


def resumen_md(df, columnas):
    res = eda.resumen_numerico(df, columnas).reset_index().rename(columns={"index": "Variable"})
    res.columns = ["Variable", "Count", "Media", "Std", "Min", "P25", "Mediana", "P75", "Max"]
    fmts = {c: fnum for c in ["Media", "Std", "Min", "P25", "Mediana", "P75", "Max"]}
    fmts["Count"] = n
    return tabla_md(res, fmts)


# ---------- Gráficos ----------
def _anotar_barras(ax):
    for p in ax.patches:
        if p.get_height() > 0:
            ax.annotate(n(p.get_height()), (p.get_x() + p.get_width() / 2., p.get_height()),
                        ha="center", va="center", xytext=(0, 5), textcoords="offset points", fontsize=9)


def generar_graficos_distribucion(v, l, carpeta_img):
    os.makedirs(carpeta_img, exist_ok=True)
    rutas = {}

    _, ax = plt.subplots(figsize=(7, 4))
    sns.countplot(data=v, x="cantidad", hue="cantidad", palette="Blues_d", legend=False, ax=ax)
    ax.set_title("Distribución de cantidad de productos por venta", fontsize=12, pad=10)
    ax.set_xlabel("Cantidad de unidades")
    ax.set_ylabel("Número de ventas")
    _anotar_barras(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(carpeta_img, "dist_cantidad.png"), dpi=200)
    plt.close()
    rutas["cantidad"] = "img/dist_cantidad.png"

    _, ax = plt.subplots(figsize=(7, 4))
    calif = v["calificacion_cliente"].dropna().astype(int)
    sns.countplot(x=calif, hue=calif, palette="YlOrRd", legend=False, ax=ax)
    ax.set_title("Distribución de calificación del cliente (excluyendo nulos)", fontsize=12, pad=10)
    ax.set_xlabel("Calificación (estrellas)")
    ax.set_ylabel("Frecuencia")
    _anotar_barras(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(carpeta_img, "dist_calificacion.png"), dpi=200)
    plt.close()
    rutas["calificacion"] = "img/dist_calificacion.png"

    _, axes = plt.subplots(1, 2, figsize=(11, 4))
    sns.histplot(v["precio_unitario"], kde=True, color="#1a3a5c", ax=axes[0])
    axes[0].set_title("Distribución de precio unitario")
    axes[0].set_xlabel("Precio unitario ($)")
    axes[0].set_ylabel("Frecuencia")
    sns.histplot(v["valor_neto"], kde=True, color="#2b5c8f", ax=axes[1])
    axes[1].set_title("Distribución de valor neto de venta")
    axes[1].set_xlabel("Valor neto ($)")
    axes[1].set_ylabel("Frecuencia")
    plt.tight_layout()
    plt.savefig(os.path.join(carpeta_img, "dist_precios_neto.png"), dpi=200)
    plt.close()
    rutas["precios"] = "img/dist_precios_neto.png"

    _, ax = plt.subplots(figsize=(8, 4))
    sns.boxplot(data=l, x="tiempo_etapa_horas", color="#8ebad9", ax=ax)
    ax.set_title("Diagrama de caja - tiempo por etapa logística (horas)", fontsize=12, pad=10)
    ax.set_xlabel("Horas por etapa")
    plt.tight_layout()
    plt.savefig(os.path.join(carpeta_img, "dist_tiempo_etapa.png"), dpi=200)
    plt.close()
    rutas["tiempo_etapa"] = "img/dist_tiempo_etapa.png"

    return rutas


# ---------- Estilos y plantilla HTML ----------
CSS = """
body{font-family:Segoe UI,Arial,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#222}
h1,h2,h3,h4{color:#1a3a5c}
table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.88rem}
th,td{border:1px solid #ccc;padding:6px 10px;text-align:left;vertical-align:top}
th{background:#eef3f8}
code{background:#f3f3f3;padding:1px 4px;border-radius:3px}
hr{border:none;border-top:1px solid #ddd;margin:2rem 0}
img{max-width:100%;height:auto;display:block;margin:1.5rem auto;border:1px solid #ddd;border-radius:4px}
"""

PLANTILLA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laboratorio ETL Kaismart Solutions</title><style>{{CSS}}</style></head>
<body>{{CUERPO}}</body></html>"""


def seccion_dataset(nombre, df, representa):
    tipos = eda.listas_por_tipo(df)
    rangos = " | ".join(f"`{c}`: {ini:%Y-%m-%d} a {fin:%Y-%m-%d}" for c, (ini, fin) in eda.rango_fechas(df).items())
    est = eda.tabla_estructura(df)
    est["% nulos"] = (1 - est["Registros no nulos"] / len(df)) * 100
    return [
        f"**¿Qué representa una fila?** {representa}",
        "",
        f"1. **Número de registros:** {n(len(df))}",
        f"2. **Número de variables:** {df.shape[1]}",
        f"3. **Variables:** {lista_md(df.columns)}",
        "4. y 5. **Tipo de dato y registros no nulos:** ver tabla.",
        f"6. **Identificadores:** {lista_md(tipos['identificadores'])}",
        f"7. **Categóricas:** {lista_md(tipos['categoricas'])}",
        f"8. **Numéricas:** {lista_md(tipos['numericas'])}",
        f"9. **Fechas / tiempos:** {lista_md(tipos['fechas_tiempos'])}",
        f"- **Rango de fechas:** {rangos}",
        "",
        tabla_md(est, {"Registros no nulos": n, "% nulos": lambda x: pc(x, 2)}),
    ]


# ---------- Función principal ----------
def generar_informe(config_path="config/config.yaml", salida="docs"):
    cfg = cargar_config(config_path)
    p = cfg["paths"]
    autores = ", ".join(cfg.get("autores", [])) or "[nombres del equipo]"

    # ---------- Carga de capas Medallion ----------
    v = pd.read_parquet(os.path.join(p["bronze_dir"], "ventas_bronze.parquet"))
    l = pd.read_parquet(os.path.join(p["bronze_dir"], "logistica_bronze.parquet"))
    vs = pd.read_parquet(os.path.join(p["silver_dir"], "df_ventas_transformado.parquet"))
    ls = pd.read_parquet(os.path.join(p["silver_dir"], "df_logistica_transformado.parquet"))
    g = pd.read_parquet(os.path.join(p["gold_dir"], "ventas_logistica_gold.parquet"))
    ge = pd.read_parquet(os.path.join(p["gold_dir"], "eventos_gold.parquet"))

    img = generar_graficos_distribucion(v, l, os.path.join(salida, "img"))

    # ---------- Cálculos del EDA (sobre los datos originales = Bronze) ----------
    chequeos = pd.DataFrame(eda.chequeos_calidad(v, l), columns=["Chequeo", "Resultado"])
    diag_nulos = eda.diagnostico_nulos(v, l, config_path)
    dup = eda.analizar_duplicados(v, l)
    preguntas = calcular_preguntas_negocio(v, l)
    estados_tr = cfg["reglas"]["estados_con_transporte"]
    post = l["estado_evento"].isin(estados_tr)
    post_s = ls["estado_evento"].isin(estados_tr)

    # evento_id repetido con contenido distinto: qué columnas difieren
    rep = l[l["evento_id"].duplicated(keep=False)].drop_duplicates()
    rep = rep[rep["evento_id"].duplicated(keep=False)]
    difieren = {}
    for eid, grupo in rep.groupby("evento_id"):
        difieren[eid] = [c for c in grupo.columns if grupo[c].nunique(dropna=False) > 1]

    # ---------- Indicadores de ventas ----------
    neto_ciudad = v.groupby("ciudad")["valor_neto"].sum().sort_values(ascending=False)
    top3_ciudad = neto_ciudad.head(3)
    neto_cat = v.groupby("categoria")["valor_neto"].sum().sort_values(ascending=False)
    trans_cat = v["categoria"].value_counts()
    canal_pct = v["canal"].value_counts(normalize=True) * 100
    califica_alta = v["calificacion_cliente"].isin([4, 5]).sum() / v["calificacion_cliente"].notna().sum() * 100
    con_desc = (v["descuento_pct"] > 0).mean() * 100
    compras = v["id_cliente"].value_counts()
    recurrentes = compras[compras > 1]
    pct_ventas_rec = v["id_cliente"].isin(recurrentes.index).mean() * 100
    prod_neto = v.groupby(["producto", "categoria"])["valor_neto"].sum().sort_values(ascending=False)
    top_prod, top_prod_cat = prod_neto.index[0]
    peso_top = prod_neto.iloc[0] / neto_cat[top_prod_cat] * 100
    if top_prod_cat == neto_cat.index[0]:
        explica = f"lo explica `{top_prod}`, que aporta el {pc(peso_top)} del valor neto de {top_prod_cat}"
    else:
        explica = f"el producto de mayor valor es `{top_prod}` ({top_prod_cat})"

    # ---------- Estandarización: se mide qué cambió la limpieza y si hay variantes de una misma categoría ----------
    textos = [(v, c) for c in ["ciudad", "canal", "categoria", "producto", "medio_pago"]] +              [(l, c) for c in ["estado_evento", "centro_logistico", "ciudad_destino", "transportadora", "incidencia", "observacion"]]
    valores_cambiados = 0
    variantes = []
    for df_, c in textos:
        limpio = _limpiar_texto(df_[c])
        valores_cambiados += int((df_[c].notna() & (limpio != df_[c])).sum())
        if limpio.str.lower().nunique() < df_[c].nunique():
            variantes.append(c)
    fuera_cobertura = sorted((set(vs["ciudad"].dropna()) | set(ls["ciudad_destino"].dropna())) - set(cfg["reglas"]["cobertura"]))
    texto_cobertura = ("todas las ciudades están dentro de la cobertura" if not fuera_cobertura
                       else f"hay ciudades fuera de la cobertura: {lista_md(fuera_cobertura)}")
    texto_variantes = ("no hay variantes de escritura de una misma categoría (mayúsculas, tildes o espacios), así que no fue "
                       "necesario recodificar" if not variantes
                       else f"las columnas {lista_md(variantes)} tienen variantes de escritura que deben unificarse")
    montos_en_eventos = [c for c in MONTOS_VENTA if c in ge.columns]
    cols_pedido = ["centro_logistico", "ciudad_destino", "fecha_prometida_entrega"]
    max_nulo_pedido = l[cols_pedido + ["fecha_evento"]].isna().mean().max() * 100
    fisica = v["canal"] == "Tienda física"
    tienda_exacta = bool(v.loc[~fisica, "id_tienda"].isna().all() and v.loc[fisica, "id_tienda"].notna().all())
    _ch = dict(zip(chequeos["Chequeo"], chequeos["Resultado"]))
    eventos_ok_temporal = (_ch["Eventos con fecha anterior a la venta"] == "0"
                           and _ch["Pedidos con eventos fuera de orden cronológico (según evento_id)"] == "0")
    cuadra = (((v["precio_unitario"] * v["cantidad"]) - v["valor_bruto"]).abs().le(1)
              & ((v["valor_bruto"] * v["descuento_pct"] / 100) - v["valor_descuento"]).abs().le(1)
              & ((v["valor_bruto"] - v["valor_descuento"]) - v["valor_neto"]).abs().le(1))
    pct_aritmetica = cuadra.mean() * 100
    residuales = [c for c in l.columns if c.startswith("Unnamed")]
    fechas_texto = [c for c in l.columns if c.startswith("fecha") and not pd.api.types.is_datetime64_any_dtype(l[c])]
    nulos_pedido_bronze = int(l[cols_pedido].isna().sum().sum())
    nulos_pedido_silver = int(ls[cols_pedido].isna().sum().sum())

    # ---------- Indicadores de transformación / Gold ----------
    con_entrega = int(g["entregado_tarde"].notna().sum())
    tarde = int(g["entregado_tarde"].sum())
    sin_entrega = int(g["fecha_entrega"].isna().sum())
    pedidos_entregado = set(ls.loc[ls["estado_evento"] == "Entregado", "pedido_id"])
    sin_evento = int((~g.loc[g["fecha_entrega"].isna(), "pedido_id"].isin(pedidos_entregado)).sum())
    fecha_nula = sin_entrega - sin_evento
    tarde_media = g.loc[g["entregado_tarde"] == True, "dias_retraso"].mean()
    n_entregados = int(g["entregado"].sum())
    ciclo_med = g["dias_ciclo_entrega"].median()
    prometido_med = g["dias_prometidos"].median()
    # Tablas agregadas de Gold: el informe las lee, no las recalcula
    kpi_mensual = pd.read_parquet(os.path.join(p["gold_dir"], "kpi_mensual.parquet"))
    transp = pd.read_parquet(os.path.join(p["gold_dir"], "desempeno_transportadora.parquet"))
    ciudad_canal = pd.read_parquet(os.path.join(p["gold_dir"], "ventas_ciudad_canal.parquet"))
    incid = pd.read_parquet(os.path.join(p["silver_dir"], "incidencias_calidad.parquet"))
    rech_v = pd.read_parquet(os.path.join(p["silver_dir"], "rechazados", "ventas_rechazadas.parquet"))
    rech_l = pd.read_parquet(os.path.join(p["silver_dir"], "rechazados", "logistica_rechazada.parquet"))
    con_recibido = set(ls.loc[ls["estado_evento"] == "Pedido recibido", "pedido_id"])
    sin_recibido = int((~g["pedido_id"].isin(con_recibido)).sum())

    # Linaje: manifiesto de la ejecución que generó el Gold publicado (validaciones tal como corrieron)
    linaje = leer_json(os.path.join(p["gold_dir"], "_linaje.json"))
    manif = leer_json(os.path.join(p["manifiestos_dir"], f"{linaje['id_ejecucion']}.json"))
    reglas = pd.DataFrame(manif["validaciones"]["silver"]["reglas"] + manif["validaciones"]["gold"]["reglas"])
    reglas["Cumple"] = reglas["Cumple"].map({True: "Sí", False: "**No**"})
    n_reglas_ok = int((reglas["Cumple"] == "Sí").sum())
    historial = []
    for f in sorted(os.listdir(p["manifiestos_dir"]))[-8:]:
        m = leer_json(os.path.join(p["manifiestos_dir"], f))
        val = m.get("validaciones", {})
        historial.append({"Ejecución": m["id_ejecucion"], "Origen": ORIGEN.get(m["origen"], m["origen"]), "Carga Bronze": m["id_carga"] or "-",
                          "Estado": m["estado"], "Duración (s)": fnum(m["duracion_s"], 1) if m["duracion_s"] is not None else "-",
                          "Reglas cumplidas": f"{sum(x['cumplidas'] for x in val.values())} de {sum(x['total'] for x in val.values())}"})
    historial = pd.DataFrame(historial)

    # Histórico de Bronze
    cargas_hist = listar_cargas(config_path)
    cfg_bronze = cfg.get("bronze", {})
    resumen_incid = (incid.groupby(["nivel", "tipo", "accion"]).size().rename("registros").reset_index()
                     .sort_values("registros", ascending=False))
    incompletos = int((~g["trazabilidad_completa"]).sum())
    guia_comp = g.loc[g["guia_compartida"], "pedido_id"].tolist()

    cols_nulos = [c for c in l.columns if l[c].isna().any()]
    estrategia = {
        "Unnamed: 13": ("Eliminar columna", "Columna residual del Excel (una sola celda con la fórmula `=AI(\"\")`)."),
        "incidencia": ("Categoría `Sin incidencia`", "El nulo significa que no hubo novedad; se hace explícito (equivale a \"NO INFORMADO\")."),
        "observacion": ("Categoría `Sin observación`", "El nulo significa que no se anotó nada; se hace explícito."),
        "transportadora": ("Valor del mismo pedido, solo en estados de transporte",
                           f"Antes del despacho el nulo es válido y se mantiene. En {', '.join(estados_tr)} se completa con la "
                           "transportadora del pedido (cada pedido tiene una sola)."),
        "numero_guia": ("Valor del mismo pedido, solo en estados de transporte", "Igual que `transportadora`: cada pedido tiene una sola guía."),
        "tiempo_etapa_horas": ("Se mantiene nulo", "Todos los nulos están en `Pedido recibido`, el primer evento, que no tiene etapa previa. "
                                                   "Imputar media o mediana inventaría una duración que no existe."),
        "centro_logistico": ("Valor del mismo pedido", "Es constante dentro del pedido (1 valor por pedido), así que se recupera el valor real. "
                                                       "Es más exacto que la moda."),
        "fecha_evento": ("Se mantiene nulo", "No se puede deducir la hora real de un evento; imputarla alteraría tiempos y retrasos."),
        "fecha_prometida_entrega": ("Valor del mismo pedido", "Es constante dentro del pedido, así que se recupera el valor real."),
        "ciudad_destino": ("Valor del mismo pedido", "Es constante dentro del pedido y coincide con la ciudad de la venta."),
    }
    tabla_imputacion = pd.DataFrame([{
        "Variable": c,
        "Nulos Bronze": int(l[c].isna().sum()),
        "Estrategia": estrategia.get(c, ("-", "-"))[0],
        "Justificación": estrategia.get(c, ("-", "-"))[1],
        "Nulos Silver": int(ls[c].isna().sum()) if c in ls.columns else "eliminada",
    } for c in cols_nulos])
    tabla_imputacion_v = pd.DataFrame([
        {"Variable": "id_tienda", "Nulos Bronze": int(v["id_tienda"].isna().sum()), "Estrategia": "Se mantiene nulo",
         "Justificación": "Solo aplica al canal Tienda física; en web y app no existe tienda.",
         "Nulos Silver": int(vs["id_tienda"].isna().sum())},
        {"Variable": "calificacion_cliente", "Nulos Bronze": int(v["calificacion_cliente"].isna().sum()),
         "Estrategia": "Se mantiene nulo (tipo Int64)",
         "Justificación": "El cliente no calificó. Imputar moda (5) o media inflaría o distorsionaría la satisfacción.",
         "Nulos Silver": int(vs["calificacion_cliente"].isna().sum())},
    ])
    fmt_imp = {"Nulos Bronze": n, "Nulos Silver": lambda x: x if isinstance(x, str) else n(x)}

    # ---------- Construcción del Markdown ----------
    md = [
        "# Laboratorio ETL Kaismart Solutions S.A.S.",
        "",
        f"**Autores:** {autores}",
        "",
        "Fuentes: base MySQL `clientes`, tabla `ventas` (`df_ventas`), y archivo `kaismart_eventos_logisticos.xlsx` "
        "(`df_logistica`). Las secciones 1 a 4 se calculan sobre los datos originales (capa Bronze), sin limpiar ni integrar.",
        "",
        "---",
        "",
        "## 1. Comprensión inicial de los datasets",
        "",
        "### 1.1 Ventas (`df_ventas`)",
        "",
        *seccion_dataset("df_ventas", v, eda.FILA_VENTAS),
        "",
        "### 1.2 Logística (`df_logistica`)",
        "",
        *seccion_dataset("df_logistica", l, eda.FILA_LOGISTICA),
        "",
        "### 1.3 Otros aspectos de calidad del dato",
        "",
        tabla_md(chequeos),
        "",
        "## 2. Perfil inicial de calidad del dato",
        "",
        "### 2.1 Valores nulos",
        "",
        "#### Nulos en `df_ventas` (de mayor a menor)",
        tabla_md(eda.tabla_nulos(v), {"Cantidad nulos": n, "Porcentaje (%)": lambda x: pc(x, 2)}),
        "",
        "#### Nulos en `df_logistica` (de mayor a menor)",
        tabla_md(eda.tabla_nulos(l), {"Cantidad nulos": n, "Porcentaje (%)": lambda x: pc(x, 3)}),
        "",
        "#### Interpretación: nulos normales del proceso vs. problemas de calidad",
        tabla_md(diag_nulos),
        "",
        "En esta etapa no se elimina ni se imputa ningún valor.",
        "",
        "### 2.2 Valores únicos y cardinalidad (`nunique()`)",
        "",
        "#### Cardinalidad en `df_ventas`",
        tabla_md(eda.tabla_cardinalidad(v), {"Valores únicos": n, "% sobre registros": lambda x: pc(x, 2)}),
        "",
        "#### Cardinalidad en `df_logistica`",
        tabla_md(eda.tabla_cardinalidad(l), {"Valores únicos": n, "% sobre registros": lambda x: pc(x, 2)}),
        "",
        f"- **`id_venta`:** {n(v['id_venta'].nunique())} valores para {n(len(v))} filas. Es el identificador único de la venta.",
        f"- **`pedido_id`:** único en ventas ({n(v['pedido_id'].nunique())}), pero en logística se repite "
        f"(~{len(l) / l['pedido_id'].nunique():.0f} eventos por pedido). Es la clave para integrar las fuentes (relación 1 a muchos).",
        f"- **`evento_id`:** {n(l['evento_id'].nunique())} valores para {n(len(l))} filas. Debería ser único, así que hay "
        f"{n(dup['logistica_evento_id_repetidos'])} repetidos (ver 2.3).",
        f"- **Alta cardinalidad:** `id_cliente` ({n(v['id_cliente'].nunique())} clientes; hay clientes que compran varias veces). "
        f"`producto` ({v['producto'].nunique()} valores) tiene cardinalidad media.",
        "- **Baja cardinalidad (pocos valores posibles):** `canal`, `ciudad`, `categoria`, `medio_pago`, `calificacion_cliente`, "
        "`estado_evento`, `centro_logistico`, `ciudad_destino`, `transportadora`, `incidencia` y `observacion`. Son ideales para agrupar.",
        f"- **Numéricas discretas:** `cantidad` ({v['cantidad'].nunique()} valores), `descuento_pct` ({v['descuento_pct'].nunique()}) "
        f"y `costo_envio` ({l['costo_envio'].nunique()} tarifas) toman pocos valores.",
        "",
        "### 2.3 Duplicados",
        "",
        "| Revisión | df_ventas | df_logistica |",
        "|---|---|---|",
        f"| Filas completamente duplicadas | {dup['ventas_filas_duplicadas']} | {dup['logistica_filas_duplicadas']} |",
        f"| `id_venta` repetidos | {dup['ventas_id_venta_repetidos']} | - |",
        f"| `pedido_id` repetidos | {dup['ventas_pedido_id_repetidos']} | {n(dup['logistica_pedido_id_repetidos'])} (esperado: varios eventos por pedido) |",
        f"| `evento_id` repetidos | - | {dup['logistica_evento_id_repetidos']} |",
        f"| `numero_guia` compartido por pedidos distintos | - | {len(dup['logistica_guias_compartidas'])} ({lista_md(dup['logistica_guias_compartidas'])}) |",
        "",
        ("- **Ventas:** no hay duplicados. Cada venta es un pedido único (relación 1 a 1 entre `id_venta` y `pedido_id`)."
         if dup["ventas_filas_duplicadas"] + dup["ventas_id_venta_repetidos"] + dup["ventas_pedido_id_repetidos"] == 0 else
         f"- **Ventas:** hay {dup['ventas_filas_duplicadas']} filas duplicadas, {dup['ventas_id_venta_repetidos']} `id_venta` y "
         f"{dup['ventas_pedido_id_repetidos']} `pedido_id` repetidos."),
        f"- **Logística:** de los {dup['logistica_evento_id_repetidos']} `evento_id` repetidos, "
        f"{dup['logistica_evento_id_repetidos_por_fila_identica']} son filas idénticas (el mismo evento cargado dos veces) y "
        f"{dup['logistica_evento_id_repetidos_con_contenido_distinto']} tiene contenido distinto: "
        + "; ".join(f"`evento_id` {eid} difiere solo en {lista_md(cols)}" for eid, cols in difieren.items())
        + ". Se conservará la fila más completa.",
        f"- **Guía compartida:** {lista_md(dup['logistica_guias_compartidas'])} aparece en los pedidos {lista_md(guia_comp)}. "
        "Una guía debería identificar a un solo envío.",
        "- No se elimina ningún duplicado en esta etapa.",
        "",
        "### 2.4 Coherencia de tipos de datos",
        "",
        "#### Tipos en `df_ventas`",
        tabla_md(eda.tabla_tipos(v)),
        "",
        "#### Tipos en `df_logistica`",
        tabla_md(eda.tabla_tipos(l)),
        "",
        "**Columnas a revisar antes de analizar:** `fecha_evento` y `fecha_prometida_entrega` (texto, se deben convertir a datetime), "
        "`calificacion_cliente` (float por los nulos, es una escala entera), `Unnamed: 13` (residual), y `costo_envio`, "
        "que se repite en cada evento del pedido y no debe sumarse por evento. Los montos son numéricos y los identificadores "
        "de texto son coherentes; `id_venta` y `evento_id` son claves técnicas enteras, así que no se opera con ellas.",
        "",
        "## 3. Estadísticos descriptivos y resúmenes",
        "",
        "### 3.1 Variables numéricas",
        "",
        "#### `df_ventas`",
        resumen_md(v, eda.listas_por_tipo(v)["numericas"]),
        "",
        f"Los montos tienen asimetría positiva: la media de `valor_neto` ({fnum(v['valor_neto'].mean(), 0)}) casi duplica la mediana "
        f"({fnum(v['valor_neto'].median(), 0)}), porque pocas ventas de valor alto elevan el promedio. Para este tipo de variable, "
        "la mediana es la medida central más representativa.",
        "",
        f"![Distribución de precios y valor neto]({img['precios']})",
        "",
        "#### `df_logistica`",
        resumen_md(l, ["tiempo_etapa_horas", "costo_envio"]),
        "",
        f"`costo_envio` está calculado por evento. Por pedido (un valor por pedido) la media es "
        f"{fnum(l.groupby('pedido_id')['costo_envio'].first().mean(), 0)}.",
        "",
        f"![Diagrama de caja tiempo por etapa]({img['tiempo_etapa']})",
        "",
        "### 3.2 Variables categóricas",
        "",
        "#### Resumen general",
        tabla_md(pd.concat([eda.resumen_categoricas(v).assign(DataFrame="df_ventas"),
                            eda.resumen_categoricas(l).assign(DataFrame="df_logistica")])
                 [["DataFrame", "Variable", "Valores únicos", "Categoría más frecuente", "Frecuencia", "% de no nulos", "Categorías"]],
                 {"Frecuencia": n, "% de no nulos": pc}),
        "",
        "#### `df_ventas`: ventas por ciudad",
        conteo(v["ciudad"], "ciudad"),
        "",
        "#### `df_ventas`: ventas por canal",
        conteo(v["canal"], "canal"),
        "",
        "#### `df_ventas`: ventas por categoría",
        conteo(v["categoria"], "categoria"),
        "",
        "#### `df_ventas`: distribución de la cantidad de productos vendidos",
        conteo(v["cantidad"], "cantidad"),
        "",
        f"![Distribución de cantidad]({img['cantidad']})",
        "",
        "#### `df_ventas`: resumen de `precio_unitario`, `valor_bruto`, `valor_descuento` y `valor_neto`",
        resumen_md(v, ["precio_unitario", "valor_bruto", "valor_descuento", "valor_neto"]),
        "",
        f"#### `df_ventas`: distribución de `calificacion_cliente` ({n(v['calificacion_cliente'].notna().sum())} registros con información)",
        conteo(v["calificacion_cliente"].dropna().astype(int), "calificacion"),
        "",
        f"![Distribución de calificaciones]({img['calificacion']})",
        "",
        "#### `df_logistica`: eventos por `estado_evento`",
        conteo(l["estado_evento"], "estado_evento"),
        "",
        "#### `df_logistica`: eventos por `ciudad_destino`",
        conteo(l["ciudad_destino"].dropna(), "ciudad_destino"),
        "",
        "#### `df_logistica`: frecuencia de transportadoras (eventos)",
        conteo(l["transportadora"].dropna(), "transportadora"),
        "",
        "#### `df_logistica`: frecuencia de incidencias",
        conteo(l["incidencia"].dropna(), "incidencia"),
        "",
        "#### `df_logistica`: resumen de `tiempo_etapa_horas` y `costo_envio`",
        resumen_md(l, ["tiempo_etapa_horas", "costo_envio"]),
        "",
        "## 4. Preguntas de negocio (datos originales)",
        "",
    ]
    for i, r in enumerate(preguntas, start=1):
        md += [f"**{i}. {r['pregunta']}**", "", r["respuesta"], ""]
        det = r["detalle"]
        if det is not None:
            if isinstance(det, pd.Series):
                md += [serie_md(det, det.index.name or "clave", det.name or "valor", formato=fmt_auto), ""]
            else:
                t = det.reset_index()
                md += [tabla_md(t, {c: fmt_auto for c in t.columns[1:]}), ""]

    md += [
        "## 5. Transformación de datos (Medallion)",
        "",
        "| Capa | Contenido | Archivos |",
        "|---|---|---|",
        f"| Bronze | Copia exacta de las fuentes: última carga y un histórico por ejecución con el `.xlsx` original sin tocar | `ventas_bronze.parquet` ({n(len(v))} × {v.shape[1]}), `logistica_bronze.parquet` ({n(len(l))} × {l.shape[1]}), `historico/` ({plural(len(cargas_hist), 'carga', 'cargas')}) |",
        f"| Silver | Se construye **leyendo Bronze**. Datos depurados por fuente, registro de incidencias y cuarentena | `df_ventas_transformado.parquet` ({n(len(vs))} × {vs.shape[1]}), `df_logistica_transformado.parquet` ({n(len(ls))} × {ls.shape[1]}), `incidencias_calidad.parquet` ({n(len(incid))}), `rechazados/` ({n(len(rech_v) + len(rech_l))}) |",
        f"| Gold | Integración por `pedido_id` y tablas agregadas listas para consumo | `ventas_logistica_gold.parquet` (1 fila por pedido, {n(len(g))} × {g.shape[1]}), `eventos_gold.parquet` (1 fila por evento, {n(len(ge))} × {ge.shape[1]}), `kpi_mensual`, `desempeno_transportadora`, `ventas_ciudad_canal` |",
        "",
        "### 5.1 Duplicados",
        "",
        f"- Se eliminaron {dup['logistica_filas_duplicadas']} filas idénticas en logística. En ventas no había duplicados.",
        f"- Se resolvió {dup['logistica_evento_id_repetidos_con_contenido_distinto']} `evento_id` repetido con contenido distinto "
        "conservando la fila con menos nulos (las dos versiones solo difieren en "
        + "; ".join(f"{lista_md(cols)} para el evento {eid}" for eid, cols in difieren.items()) + ").",
        f"- Resultado: `evento_id` es único en Silver ({n(ls['evento_id'].nunique())} valores para {n(len(ls))} filas).",
        "",
        "### 5.2 Tratamiento de nulos (cada decisión es explícita, no automática)",
        "",
        "#### Logística",
        tabla_md(tabla_imputacion, fmt_imp),
        "",
        f"En estados de transporte, `transportadora` pasó de {int(l.loc[post, 'transportadora'].isna().sum())} a "
        f"{int(ls.loc[post_s, 'transportadora'].isna().sum())} nulos y `numero_guia` de {int(l.loc[post, 'numero_guia'].isna().sum())} a "
        f"{int(ls.loc[post_s, 'numero_guia'].isna().sum())}. Los nulos que quedan son todos de eventos anteriores al despacho, donde son válidos.",
        "",
        "#### Ventas",
        tabla_md(tabla_imputacion_v, fmt_imp),
        "",
        "No se usó media ni mediana porque ninguna variable numérica tiene nulos que sean errores. Los únicos nulos numéricos "
        "(`tiempo_etapa_horas` y `calificacion_cliente`) tienen un significado válido. Tampoco se usó la moda para las "
        "categóricas: el valor real se podía recuperar del mismo pedido, y eso es más exacto.",
        "",
        "### 5.3 Tipos y estandarización",
        "",
        "- `fecha_evento` y `fecha_prometida_entrega` pasan de texto a `datetime`; `fecha_venta` ya era `datetime`.",
        "- `calificacion_cliente` pasa de `float64` a `Int64` (entero que admite nulos).",
        f"- En las variables de texto se eliminaron espacios al inicio y al final y se colapsaron los espacios repetidos "
        f"({n(valores_cambiados)} valores cambiaron). Al validar contra la cobertura de `config.yaml` "
        f"({', '.join(cfg['reglas']['cobertura'])}), {texto_cobertura}, y {texto_variantes}.",
        "- Se eliminó la columna residual `Unnamed: 13`.",
        "",
        "### 5.4 Capa Gold",
        "",
        "`ventas_logistica_gold` agrega una fila por pedido con la venta y su resumen logístico: número de eventos y estados, estado final, "
        "transportadora, costo de envío (una vez por pedido), tiempo total, incidencias, fecha de entrega, `dias_retraso`, "
        "`entregado_tarde`, `trazabilidad_completa`, `guia_compartida`, `entregado`, `dias_ciclo_entrega` (de la venta a la entrega), "
        "`dias_prometidos` (de la venta a la fecha prometida) y `mes_venta`.",
        "",
        f"`eventos_gold` ({n(len(ge))} × {ge.shape[1]}) tiene una fila por evento con los datos descriptivos de la venta, "
        + ("**sin los montos de la venta** (" + lista_md(MONTOS_VENTA) + "): repetidos en cada evento, una suma multiplicaría "
           "las ventas ~10 veces." if not montos_en_eventos else
           f"**con los montos {lista_md(montos_en_eventos)} repetidos en cada evento**: no deben sumarse en esta tabla.")
        + " `costo_envio` sí está, porque es dato logístico, pero se repite en cada evento del pedido y no debe sumarse ahí. "
        "Los montos y el costo por pedido se analizan en `ventas_logistica_gold`.",
        "",
        f"- **Entregas tardías:** {pc(tarde / con_entrega * 100)} de los pedidos entregados ({n(tarde)} de {n(con_entrega)}) llegaron después "
        f"de la fecha prometida, con un retraso promedio de {fnum(tarde_media)} días entre los tardíos. El promedio global es "
        f"{fnum(g['dias_retraso'].mean())} días (negativo = entrega anticipada) y el retraso máximo es {fnum(g['dias_retraso'].max())} días.",
        f"- **Pedidos sin fecha de entrega:** {n(sin_entrega)}. De ellos, {n(sin_evento)} no tienen el evento `Entregado` y "
        f"{n(fecha_nula)} lo tienen pero sin fecha.",
        f"- **Trazabilidad incompleta:** {n(incompletos)} pedidos no pasan por los {ls['estado_evento'].nunique()} estados "
        f"({n(sin_recibido)} no registran `Pedido recibido`).",
        f"- **Pedidos entregados:** {n(n_entregados)} de {n(len(g))}.",
        f"- **Tiempo de ciclo:** de la venta a la entrega pasan {fnum(ciclo_med)} días (mediana), frente a {fnum(prometido_med)} días "
        f"prometidos. Los pedidos que llegan tarde se retrasan en promedio {fnum(tarde_media)} días.",
        "",
        "Las tablas siguientes se leen directamente de las tablas agregadas de Gold. Están listas para Excel o Power BI, "
        "sin tener que recalcularlas.",
        "",
        "#### `gold/desempeno_transportadora`",
        tabla_md(transp, {"pedidos": n, "pct_entregas_tardias": pc, "retraso_promedio_tardias": fnum, "ciclo_mediano_dias": fnum,
                          "tiempo_total_mediano_horas": fnum, "costo_envio_promedio": n, "pct_pedidos_con_incidencia": pc,
                          "calificacion_promedio": fnum}),
        "",
        "#### `gold/kpi_mensual`",
        tabla_md(kpi_mensual[["mes_venta", "pedidos", "clientes", "valor_neto", "ticket_promedio", "pct_entregas_tardias",
                              "ciclo_mediano_dias", "pct_pedidos_con_incidencia", "calificacion_promedio"]],
                 {"pedidos": n, "clientes": n, "valor_neto": n, "ticket_promedio": n, "pct_entregas_tardias": pc,
                  "ciclo_mediano_dias": fnum, "pct_pedidos_con_incidencia": pc, "calificacion_promedio": fnum}),
        "",
        f"La tasa de entregas tardías pasa de {pc(kpi_mensual['pct_entregas_tardias'].iloc[0])} en {kpi_mensual['mes_venta'].iloc[0]} a "
        f"{pc(kpi_mensual['pct_entregas_tardias'].iloc[-1])} en {kpi_mensual['mes_venta'].iloc[-1]}. El mes de mayor valor neto es "
        f"{kpi_mensual.loc[kpi_mensual['valor_neto'].idxmax(), 'mes_venta']}.",
        "",
        "#### `gold/ventas_ciudad_canal` (las 6 combinaciones de mayor valor)",
        tabla_md(ciudad_canal.head(6), {"pedidos": n, "unidades": n, "valor_neto": n, "ticket_promedio": n,
                                        "pct_entregas_tardias": pc, "pct_valor_neto_total": pc}),
        "",
        "### 5.5 Validaciones de calidad",
        "",
        f"Antes de guardar Silver y Gold, el pipeline verifica estas reglas ([validaciones.py](../src/transform/validaciones.py)). "
        f"Si alguna falla, se detiene y no publica datos incorrectos. Resultado sobre los datos publicados: "
        f"**{n_reglas_ok} de {len(reglas)} reglas cumplidas**.",
        "",
        tabla_md(reglas),
        "",
        "Además de las reglas por tabla, cada fila se revisa (fecha válida, ciudad en cobertura, montos coherentes, claves sin repetir, "
        "pedido existente). Las filas que no cumplen **no detienen el pipeline**: van a `silver/rechazados/` con el motivo, y se "
        f"publica el resto. Solo si superan el {cfg.get('silver', {}).get('max_pct_rechazados', '-')}% de una fuente se detiene todo.",
        "",
        "### 5.6 Incidencias de calidad y cuarentena",
        "",
        f"`silver/incidencias_calidad.parquet` registra cada problema detectado ({n(len(incid))} registros) con su nivel (evento, pedido o "
        "columna), la clave afectada y la acción tomada. Es la lista que el negocio puede usar para corregir las fuentes.",
        "",
        tabla_md(resumen_incid, {"registros": n}),
        "",
        f"Cuarentena en esta ejecución: {plural(len(rech_v), 'venta', 'ventas')} y {plural(len(rech_l), 'evento', 'eventos')} logísticos.",
        "",
        "### 5.7 Trazabilidad (linaje)",
        "",
        f"Silver y Gold fueron generados por la ejecución `{linaje['id_ejecucion']}` ({ORIGEN.get(linaje['origen'], linaje['origen'])}) a partir de la carga de Bronze "
        f"`{linaje['id_carga']}`. El manifiesto `data/manifiestos/{linaje['id_ejecucion']}.json` registra las fuentes (incluida la huella "
        f"SHA-256 del Excel: `{manif['fuentes'].get('logistica', {}).get('sha256', '-')[:16]}…`), las filas de cada archivo de cada capa y "
        "el resultado de las validaciones.",
        "",
        ("" if not cargas_hist or linaje["id_carga"] == cargas_hist[-1] else
         f"Atención: la carga más reciente de Bronze es `{cargas_hist[-1]}`, pero Silver y Gold vienen de `{linaje['id_carga']}` "
         "(reproceso de una carga anterior). Las secciones 1 a 4 usan la última carga."),
        "",
        "#### Últimas ejecuciones",
        tabla_md(historial),
        "",
        "## 6. Automatización (Parte 8)",
        "",
        f"`orchestrator.py` usa la librería `schedule` para ejecutar el pipeline completo (extracción de MySQL y Excel, y luego "
        f"Bronze → Silver → Gold) apenas se inicia y después cada {plural(cfg['orquestador']['cada_horas'], 'hora', 'horas')}, según "
        "`config.yaml`. Cada ejecución queda registrada en `logs/pipeline.log`: el resultado de cada validación y, si algo falla, "
        "la traza completa del error.",
        "",
        f"Como el orquestador vuelve a extraer en cada ejecución, Bronze guarda además una copia de cada carga en "
        f"`data/bronze/historico/AAAAMMDD_HHMMSS/` y conserva las últimas {cfg_bronze.get('max_cargas', '-')}. Así se puede auditar "
        "qué llegó en cada ejecución.",
        "",
        "Como Silver se construye leyendo Bronze, cualquier carga del histórico se puede **reprocesar sin volver a consultar MySQL "
        "ni el Excel**. Por ejemplo, si cambia una regla de limpieza: `python reprocesar.py --carga AAAAMMDD_HHMMSS` reconstruye "
        "Silver y Gold, y deja su propio manifiesto.",
        "",
        "## 7. Conclusiones",
        "",
        "### Hallazgos sobre `df_ventas`",
        f"1. **Estructura e integridad:** {n(len(v))} ventas y {v.shape[1]} variables, sin filas duplicadas. `id_venta` y `pedido_id` "
        "son únicos y todos los pedidos tienen eventos logísticos.",
        f"2. **Nulos estructurales:** `id_tienda` ({pc(v['id_tienda'].isna().mean() * 100, 2)}) es nulo "
        f"{'exactamente' if tienda_exacta else 'principalmente'} en las ventas que no son de tienda física. `calificacion_cliente` ({pc(v['calificacion_cliente'].isna().mean() * 100, 2)}) es opcional, y de quienes "
        f"califican, el {pc(califica_alta)} da 4 o 5.",
        f"3. **Consistencia aritmética:** `valor_bruto = precio × cantidad`, `valor_descuento = bruto × descuento_pct` y "
        f"`valor_neto = bruto − descuento` se cumplen en el {pc(pct_aritmetica)} de los registros.",
        f"4. **Concentración:** {', '.join(top3_ciudad.index)} suman el {pc(top3_ciudad.sum() / neto_ciudad.sum() * 100)} del valor neto, "
        f"y {canal_pct.index[0]} es el canal principal ({pc(canal_pct.iloc[0])} de las transacciones).",
        f"5. **Clientes recurrentes:** {n(len(recurrentes))} de {n(len(compras))} clientes ({pc(len(recurrentes) / len(compras) * 100)}) "
        f"compraron más de una vez y generan el {pc(pct_ventas_rec)} de las ventas.",
        f"6. **Categoría y producto:** {neto_cat.index[0]} lidera el valor neto con {pc(neto_cat.iloc[0] / neto_cat.sum() * 100)} del total, "
        f"aunque {trans_cat.index[0]} tiene más transacciones ({n(trans_cat.iloc[0])} frente a {n(trans_cat[neto_cat.index[0]])}); "
        f"{explica}.",
        f"7. **Distribuciones:** los montos tienen asimetría positiva (media de valor neto {fnum(v['valor_neto'].mean(), 0)} frente a "
        f"mediana {fnum(v['valor_neto'].median(), 0)}). El {pc((v['cantidad'] == 1).mean() * 100)} de las ventas es de 1 unidad y el "
        f"{pc(con_desc)} tiene descuento.",
        "",
        "### Hallazgos sobre `df_logistica`",
        f"1. **Estructura:** {n(len(l))} eventos de {n(l['pedido_id'].nunique())} pedidos (~{len(l) / l['pedido_id'].nunique():.0f} por pedido)"
        + (f" y una columna residual {lista_md(residuales)} con {plural(int(l[residuales].notna().sum().sum()), 'celda', 'celdas')} con datos." if residuales else "."),
        f"2. **Tipos:** {lista_md(fechas_texto)} vienen como texto y deben convertirse a fecha." if fechas_texto
        else "2. **Tipos:** las fechas ya vienen con tipo fecha.",
        f"3. **Duplicados:** {dup['logistica_filas_duplicadas']} filas idénticas y {dup['logistica_evento_id_repetidos']} `evento_id` repetidos, "
        f"además de {plural(len(dup['logistica_guias_compartidas']), 'número de guía compartido', 'números de guía compartidos')} entre pedidos.",
        f"4. **Nulos:** `transportadora` y `numero_guia` (~{l['transportadora'].isna().mean() * 100:.0f}%) son nulos normales antes del despacho, pero "
        f"{int(l.loc[post, 'transportadora'].isna().sum())} y {int(l.loc[post, 'numero_guia'].isna().sum())} nulos en estados de transporte son errores. "
        f"Los nulos de `centro_logistico`, `ciudad_destino`, `fecha_prometida_entrega` y `fecha_evento` (hasta {pc(max_nulo_pedido, 2)}) "
        "son problemas de calidad.",
        f"5. **Trazabilidad:** {n(int((l.groupby('pedido_id')['estado_evento'].nunique() < l['estado_evento'].nunique()).sum()))} pedidos "
        f"no tienen todos los estados (por ejemplo, {n(sin_recibido)} no registran `Pedido recibido`), por eso la frecuencia por estado "
        f"no es exactamente {n(l['pedido_id'].nunique())}. Las fechas sí son consistentes: ningún evento es anterior a la venta ni "
        "aparece fuera de orden." if eventos_ok_temporal else
        "no tienen todos los estados, y hay inconsistencias temporales (ver 1.3).",
        f"6. **Incidencias:** afectan al {pc(l['incidencia'].notna().mean() * 100, 2)} de los eventos ({pc(l.loc[l['incidencia'].notna(), 'pedido_id'].nunique() / l['pedido_id'].nunique() * 100)} "
        f"de los pedidos). La más frecuente es `{l['incidencia'].mode()[0]}`.",
        f"7. **Costos y tiempos:** `costo_envio` es constante por pedido ({l['costo_envio'].nunique()} tarifas) y `tiempo_etapa_horas` "
        f"tiene una mediana de {fnum(l['tiempo_etapa_horas'].median())} h y un máximo de {fnum(l['tiempo_etapa_horas'].max())} h.",
        "",
        "### Hallazgos de la transformación",
        f"1. Logística pasó de {n(len(l))} × {l.shape[1]} a {n(len(ls))} × {ls.shape[1]}: se eliminaron duplicados y la columna residual, "
        "y `evento_id` quedó único.",
        f"2. Los nulos de datos del pedido (centro, ciudad destino y fecha prometida) pasaron de {n(nulos_pedido_bronze)} a "
        f"{n(nulos_pedido_silver)} al recuperarlos desde el mismo pedido, sin necesidad de moda ni media.",
        "3. Los nulos con significado (`id_tienda`, `calificacion_cliente`, `tiempo_etapa_horas` y `transportadora` antes del despacho) "
        "se conservaron, para no sesgar los indicadores.",
        f"4. La integración en Gold es 1 a 1 por pedido ({n(len(g))} filas) y permite medir el cumplimiento: "
        f"{pc(tarde / con_entrega * 100)} de entregas tardías.",
        f"5. Quedan problemas que no se pueden corregir con los datos disponibles y se dejan marcados: {fecha_nula} pedidos con evento `Entregado` "
        f"sin fecha, {n(incompletos)} pedidos con trazabilidad incompleta y {plural(len(dup['logistica_guias_compartidas']), 'guía compartida', 'guías compartidas')}.",
        "6. `eventos_gold` se publica sin los montos de la venta, para evitar que se sumen ~10 veces por pedido.",
        f"7. Las {len(reglas)} reglas de calidad se verifican automáticamente en cada ejecución ({n_reglas_ok} cumplidas), "
        f"y el tiempo de ciclo mediano ({fnum(ciclo_med)} días) queda por debajo de lo prometido ({fnum(prometido_med)} días).",
        f"8. Cada problema detectado queda documentado en `incidencias_calidad` ({n(len(incid))} registros, "
        f"{plural(int(incid['tipo'].nunique()), 'tipo', 'tipos')}). Las filas inválidas van a cuarentena sin detener el pipeline "
        f"(en esta ejecución: {n(len(rech_v) + len(rech_l))}).",
        f"9. Silver y Gold se construyen leyendo Bronze, y cada ejecución deja un manifiesto con su linaje. Las "
        f"{plural(len(cargas_hist), 'carga', 'cargas')} del histórico se pueden reprocesar sin volver a extraer de las fuentes.",
        "",
    ]
    texto = "\n".join(md)

    # ---------- Guardado ----------
    os.makedirs(salida, exist_ok=True)
    ruta_md = os.path.join(salida, "Informe_KaismartSolutions.md")
    ruta_html = os.path.join(salida, "Informe_KaismartSolutions.html")
    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write(texto)
    cuerpo = markdown.markdown(texto, extensions=["tables", "sane_lists"])
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(PLANTILLA.replace("{{CSS}}", CSS).replace("{{CUERPO}}", cuerpo))

    print(f"Informe generado:\n - {ruta_md}\n - {ruta_html}")
    return ruta_html


if __name__ == "__main__":
    generar_informe()
