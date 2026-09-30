import os
import pandas as pd
import yaml
from src.utils.logger import setup_logger

def ejecutar_transformacion_medallion(df_ventas_raw, df_logistica_raw, config_path="config/config.yaml"):
    """
    PARTE 7. PROCESO DE TRANSFORMACIÓN DE DATOS (MEDALLION)
    Bronze -> Silver -> Gold
    """
    logger = setup_logger(config_path)
    logger.info("PARTE 7: Iniciando Transformación y Arquitectura Medallion...")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    bronze_dir = config["paths"]["bronze_dir"]
    silver_dir = config["paths"]["silver_dir"]
    gold_dir = config["paths"]["gold_dir"]

    # 1. CAPA BRONZE (Resguardo puro)
    df_ventas_raw.to_parquet(os.path.join(bronze_dir, "ventas_bronze.parquet"), index=False)
    df_logistica_raw.to_parquet(os.path.join(bronze_dir, "logistica_bronze.parquet"), index=False)
    logger.info("[BRONZE] Datos crudos respaldados en data/bronze/")

    # 2. CAPA SILVER (Limpieza, Deduplicación, Imputación explicada y Estandarización)
    df_v = df_ventas_raw.copy().drop_duplicates()
    df_l = df_logistica_raw.copy().drop_duplicates()

    # Columna basura del Excel (1 celda con una fórmula, 99.998% nula)
    df_l = df_l.drop(columns=[c for c in df_l.columns if c.startswith("Unnamed")])

    # evento_id repetido con contenido distinto: se conserva la fila más completa
    df_l["_nulos"] = df_l.isnull().sum(axis=1)
    df_l = (df_l.sort_values(["evento_id", "_nulos"])
                .drop_duplicates(subset="evento_id", keep="first")
                .drop(columns="_nulos")
                .sort_values("evento_id")
                .reset_index(drop=True))

    # Tipado de fechas (llegaban como texto en logística)
    df_v["fecha_venta"] = pd.to_datetime(df_v["fecha_venta"], errors="coerce")
    for col in ["fecha_evento", "fecha_prometida_entrega"]:
        df_l[col] = pd.to_datetime(df_l[col], errors="coerce")

    # Estandarización: el EDA mostró categorías consistentes, solo se limpian espacios
    for col in ["ciudad", "canal", "categoria", "producto", "medio_pago"]:
        df_v[col] = df_v[col].str.strip()
    for col in ["estado_evento", "ciudad_destino", "transportadora", "centro_logistico"]:
        df_l[col] = df_l[col].str.strip()

    # Nulos recuperables: estos datos son iguales en todos los eventos de un pedido
    for col in ["centro_logistico", "ciudad_destino", "fecha_prometida_entrega"]:
        df_l[col] = df_l.groupby("pedido_id")[col].transform("first")

    # Nulo = ausencia de novedad, se vuelve categoría explícita
    df_l["incidencia"] = df_l["incidencia"].fillna("Sin incidencia")
    df_l["observacion"] = df_l["observacion"].fillna("Sin observación")

    # SE MANTIENEN NULOS (tienen significado válido en el proceso):
    #  calificacion_cliente: el cliente no calificó (43%)
    #  id_tienda: solo aplica a tienda física
    #  transportadora / numero_guia: aún no hay despacho
    #  tiempo_etapa_horas: el primer evento no tiene etapa previa
    #  fecha_evento: no es recuperable desde otro evento

    df_ventas_transformado = df_v
    df_logisitica_transformado = df_l

    df_ventas_transformado.to_parquet(os.path.join(silver_dir, "df_ventas_transformado.parquet"), index=False)
    df_logisitica_transformado.to_parquet(os.path.join(silver_dir, "df_logistica_transformado.parquet"), index=False)
    logger.info("[SILVER] DataFrames transformados (df_ventas_transformado y df_logisitica_transformado) guardados.")

    # 3. CAPA GOLD (Integración mediante pedido_id)
    # 3. CAPA GOLD (integración por pedido_id)
    # 3.1 Detalle: una fila por evento, con los datos de la venta
    df_gold_eventos = pd.merge(df_ventas_transformado, df_logisitica_transformado,
                               on="pedido_id", how="left", validate="one_to_many")
    df_gold_eventos.to_parquet(os.path.join(gold_dir, "eventos_gold.parquet"), index=False)

    # 3.2 Resumen: una fila por pedido (para analizar ventas sin duplicar montos)
    log_ord = df_logisitica_transformado.sort_values(["pedido_id", "evento_id"])
    resumen_log = log_ord.groupby("pedido_id").agg(
        n_eventos=("evento_id", "count"),
        estado_final=("estado_evento", "last"),
        fecha_ultimo_evento=("fecha_evento", "max"),
        fecha_prometida_entrega=("fecha_prometida_entrega", "first"),
        centro_logistico=("centro_logistico", "first"),
        ciudad_destino=("ciudad_destino", "first"),
        transportadora=("transportadora", "first"),
        costo_envio=("costo_envio", "first"),
        tiempo_total_horas=("tiempo_etapa_horas", "sum"),
        n_incidencias=("incidencia", lambda s: (s != "Sin incidencia").sum()),
    ).reset_index()
    df_gold = df_ventas_transformado.merge(resumen_log, on="pedido_id", how="left", validate="one_to_one")
    # 3.3 Retraso: fecha real de entrega vs fecha prometida
    entregas = (df_logisitica_transformado[df_logisitica_transformado["estado_evento"] == "Entregado"]
                .groupby("pedido_id")["fecha_evento"].max()
                .rename("fecha_entrega").reset_index())
    df_gold = df_gold.merge(entregas, on="pedido_id", how="left", validate="one_to_one")
    df_gold["dias_retraso"] = ((df_gold["fecha_entrega"] - df_gold["fecha_prometida_entrega"])
                               .dt.total_seconds() / 86400).round(2)
    df_gold["entregado_tarde"] = (df_gold["dias_retraso"] > 0).astype("boolean").mask(df_gold["dias_retraso"].isna())

    df_gold.to_parquet(os.path.join(gold_dir, "ventas_logistica_gold.parquet"), index=False)
    logger.info(f"[GOLD] Eventos: {df_gold_eventos.shape} | Pedidos: {df_gold.shape}")

    return df_ventas_transformado, df_logisitica_transformado, df_gold