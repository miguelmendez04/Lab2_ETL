"""
Flujo Medallion completo con manifiesto de ejecución:
    extraer -> Bronze -> Silver -> Gold          (ejecutar_etl, usado por el orquestador)
    Bronze (carga histórica) -> Silver -> Gold   (reprocesar, sin volver a extraer de las fuentes)
"""
from src.extract.extract_db import extraer_ventas_db
from src.extract.extract_excel import extraer_logistica_excel
from src.load.load import guardar_bronze, listar_cargas
from src.transform.transform_medallion import ejecutar_transformacion_medallion
from src.utils.logger import setup_logger
from src.utils.manifiesto import Manifiesto


def aterrizar_bronze(df_ventas, df_logistica, config_path="config/config.yaml"):
    """Guarda en Bronze lo recién extraído y abre el manifiesto de la ejecución. Devuelve el manifiesto."""
    manifiesto = Manifiesto("extraccion", config_path=config_path)
    manifiesto.id_carga = manifiesto.id_ejecucion  # en una extracción, la carga nace con la ejecución
    guardar_bronze(df_ventas, df_logistica, config_path, manifiesto)
    return manifiesto


def transformar(manifiesto, config_path="config/config.yaml"):
    """Bronze -> Silver -> Gold para la carga del manifiesto. Cierra el manifiesto con el resultado."""
    logger = setup_logger(config_path)
    # Si la carga está en el histórico se lee de ahí (exactamente lo que se aterrizó); si no, la última carga
    carga = manifiesto.id_carga if manifiesto.id_carga in listar_cargas(config_path) else None
    try:
        resultado = ejecutar_transformacion_medallion(config_path, carga, manifiesto)
    except Exception as e:
        ruta = manifiesto.cerrar("FALLA", f"{type(e).__name__}: {e}")
        logger.error(f"Manifiesto de la ejecución fallida: {ruta}")
        raise
    ruta = manifiesto.cerrar("OK")
    logger.info(f"Manifiesto de la ejecución: {ruta}")
    return resultado


def ejecutar_etl(config_path="config/config.yaml"):
    """Pipeline completo: extracción de MySQL y Excel -> Bronze -> Silver -> Gold."""
    df_ventas = extraer_ventas_db(config_path)
    df_logistica = extraer_logistica_excel(config_path)
    if df_ventas is None or df_logistica is None:
        Manifiesto("extraccion", config_path=config_path).cerrar("FALLA", "No se pudo extraer de las fuentes")
        raise RuntimeError("Falla en la extracción de datos (ver logs/pipeline.log)")
    return transformar(aterrizar_bronze(df_ventas, df_logistica, config_path), config_path)


def reprocesar(carga=None, config_path="config/config.yaml"):
    """
    Reconstruye Silver y Gold desde una carga del histórico de Bronze, sin consultar MySQL ni el Excel.
    Útil cuando cambia una regla de limpieza o para revisar cómo estaban los datos en una fecha.
    Sin 'carga' usa la más reciente.
    """
    cargas = listar_cargas(config_path)
    if not cargas:
        raise FileNotFoundError("No hay cargas en el histórico de Bronze (data/bronze/historico)")
    carga = carga or cargas[-1]
    if carga not in cargas:
        raise ValueError(f"La carga '{carga}' no existe. Disponibles: {', '.join(cargas)}")
    setup_logger(config_path).info(f"=== REPROCESO desde la carga de Bronze {carga} ===")
    return transformar(Manifiesto("reproceso", id_carga=carga, config_path=config_path), config_path)
