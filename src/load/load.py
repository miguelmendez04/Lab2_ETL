import hashlib
import os
import shutil
import pandas as pd
from src.utils.config import cargar_config
from src.utils.logger import setup_logger
from src.utils.manifiesto import nuevo_id


def guardar_capa(df, carpeta, nombre, config_path="config/config.yaml", manifiesto=None, capa=None):
    """
    CARGA (L del ETL): persiste un DataFrame como Parquet en la capa Medallion indicada.
    Crea la carpeta si no existe y, si recibe un manifiesto, registra el archivo (filas y columnas).
    """
    logger = setup_logger(config_path)
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.normpath(os.path.join(carpeta, f"{nombre}.parquet"))
    df.to_parquet(ruta, index=False)
    logger.info(f"Guardado {ruta} ({df.shape[0]} filas x {df.shape[1]} columnas)")
    if manifiesto is not None and capa is not None:
        manifiesto.archivo(capa, ruta, df)
    return ruta


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def listar_cargas(config_path="config/config.yaml"):
    """Cargas disponibles en el histórico de Bronze, de la más antigua a la más reciente."""
    historico = os.path.join(cargar_config(config_path)["paths"]["bronze_dir"], "historico")
    if not os.path.isdir(historico):
        return []
    return sorted(d for d in os.listdir(historico) if os.path.isdir(os.path.join(historico, d)))


def _depurar_historico(carpeta_historico, max_cargas, logger):
    """Conserva solo las últimas max_cargas copias (los nombres AAAAMMDD_HHMMSS se ordenan cronológicamente)."""
    cargas = sorted(d for d in os.listdir(carpeta_historico) if os.path.isdir(os.path.join(carpeta_historico, d)))
    for antigua in cargas[:-max_cargas]:
        shutil.rmtree(os.path.join(carpeta_historico, antigua))
        logger.info(f"[BRONZE] Carga histórica eliminada por retención: {antigua}")


def guardar_bronze(df_ventas, df_logistica, config_path="config/config.yaml", manifiesto=None):
    """
    CAPA BRONZE: aterriza los datos tal como llegan de las fuentes, sin ningún cambio.
    Se ejecuta inmediatamente después de la extracción y antes de cualquier transformación.
    - data/bronze/*.parquet: última carga.
    - data/bronze/historico/AAAAMMDD_HHMMSS/: copia de cada ejecución (Parquet + el .xlsx original sin tocar),
      para auditar o reprocesar una carga anterior sin volver a extraer.
    Devuelve el id de la carga.
    """
    logger = setup_logger(config_path)
    config = cargar_config(config_path)
    bronze_dir = config["paths"]["bronze_dir"]
    id_carga = manifiesto.id_carga if manifiesto is not None and manifiesto.id_carga else nuevo_id()

    guardar_capa(df_ventas, bronze_dir, "ventas_bronze", config_path, manifiesto, "bronze")
    guardar_capa(df_logistica, bronze_dir, "logistica_bronze", config_path, manifiesto, "bronze")

    excel = config["paths"]["excel_logistica"]
    cfg_bronze = config.get("bronze", {})
    if cfg_bronze.get("historico", False):
        historico = os.path.join(bronze_dir, "historico")
        carpeta = os.path.join(historico, id_carga)
        guardar_capa(df_ventas, carpeta, "ventas_bronze", config_path, manifiesto, "bronze")
        guardar_capa(df_logistica, carpeta, "logistica_bronze", config_path, manifiesto, "bronze")
        # Copia byte a byte del archivo fuente: Bronze conserva el original aunque pandas lo interprete distinto
        shutil.copy2(excel, os.path.join(carpeta, os.path.basename(excel)))
        _depurar_historico(historico, cfg_bronze.get("max_cargas", 48), logger)

    if manifiesto is not None:
        manifiesto.id_carga = id_carga
        manifiesto.fuente("ventas", tipo="MySQL", base=os.getenv("DB_NAME"), tabla=config["database"]["table_ventas"],
                          filas=int(df_ventas.shape[0]), columnas=int(df_ventas.shape[1]))
        manifiesto.fuente("logistica", tipo="Excel", archivo=excel, sha256=_sha256(excel),
                          filas=int(df_logistica.shape[0]), columnas=int(df_logistica.shape[1]))

    logger.info(f"[BRONZE] Carga {id_carga}: datos originales respaldados sin cambios.")
    return id_carga


def leer_bronze(config_path="config/config.yaml", carga=None):
    """
    Lee Bronze para construir Silver. Sin 'carga' usa la última carga; con 'carga' (AAAAMMDD_HHMMSS)
    usa esa copia del histórico, lo que permite reprocesar sin volver a extraer de las fuentes.
    """
    bronze_dir = cargar_config(config_path)["paths"]["bronze_dir"]
    carpeta = bronze_dir if carga is None else os.path.join(bronze_dir, "historico", carga)
    if not os.path.isdir(carpeta):
        raise FileNotFoundError(f"No existe la carga de Bronze '{carga}' ({carpeta})")
    return (pd.read_parquet(os.path.join(carpeta, "ventas_bronze.parquet")),
            pd.read_parquet(os.path.join(carpeta, "logistica_bronze.parquet")))
