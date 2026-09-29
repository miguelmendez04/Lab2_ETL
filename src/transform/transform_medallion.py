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

    # Tipado de fechas
    if 'fecha_venta' in df_v.columns:
        df_v['fecha_venta'] = pd.to_datetime(df_v['fecha_venta'])
    if 'fecha_evento' in df_l.columns:
        df_l['fecha_evento'] = pd.to_datetime(df_l['fecha_evento'])

    # Estandarización de cadenas
    for col in ['ciudad', 'canal', 'categoria']:
        if col in df_v.columns:
            df_v[col] = df_v[col].str.strip().str.title()

    for col in ['estado_evento', 'ciudad_destino', 'transportadora']:
        if col in df_l.columns:
            df_l[col] = df_l[col].str.strip().str.title()

    # Imputaciones explicadas
    # - calificacion_cliente: Se imputa con la mediana por presencia de valores atípicos.
    if 'calificacion_cliente' in df_v.columns:
        df_v['calificacion_cliente'] = df_v['calificacion_cliente'].fillna(df_v['calificacion_cliente'].median())

    # - incidencia: La ausencia representa una entrega normal, por lo que se imputa 'Sin Incidencia'.
    if 'incidencia' in df_l.columns:
        df_l['incidencia'] = df_l['incidencia'].fillna('Sin Incidencia')

    # - costo_envio: Se imputa con la mediana.
    if 'costo_envio' in df_l.columns:
        df_l['costo_envio'] = df_l['costo_envio'].fillna(df_l['costo_envio'].median())

    df_ventas_transformado = df_v
    df_logisitica_transformado = df_l

    df_ventas_transformado.to_parquet(os.path.join(silver_dir, "df_ventas_transformado.parquet"), index=False)
    df_logisitica_transformado.to_parquet(os.path.join(silver_dir, "df_logistica_transformado.parquet"), index=False)
    logger.info("[SILVER] DataFrames transformados (df_ventas_transformado y df_logisitica_transformado) guardados.")

    # 3. CAPA GOLD (Integración mediante pedido_id)
    df_gold = pd.merge(df_ventas_transformado, df_logisitica_transformado, on='pedido_id', how='inner')
    df_gold.to_parquet(os.path.join(gold_dir, "ventas_logistica_gold.parquet"), index=False)
    logger.info(f"[GOLD] Integración completada. Registros finales: {df_gold.shape}")

    return df_ventas_transformado, df_logisitica_transformado, df_gold