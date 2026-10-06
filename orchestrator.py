import time
import schedule
from src.pipeline import ejecutar_etl
from src.utils.config import cargar_config
from src.utils.logger import setup_logger

CONFIG_PATH = "config/config.yaml"
logger = setup_logger(CONFIG_PATH)


def tarea_pipeline_etl():
    """PARTE 8: pipeline completo Extracción -> Bronze -> Silver -> Gold, con manifiesto de ejecución."""
    inicio = time.time()
    logger.info("=== EJECUTANDO TAREA PROGRAMADA DE PIPELINE ETL ===")
    try:
        ejecutar_etl(CONFIG_PATH)
        logger.info(f"=== PIPELINE COMPLETADO CON ÉXITO en {time.time() - inicio:.1f} s ===")
    except Exception:
        # logger.exception guarda también la traza completa (archivo y línea del error)
        logger.exception("Falla en el pipeline")


if __name__ == "__main__":
    cada_horas = cargar_config(CONFIG_PATH)["orquestador"]["cada_horas"]

    schedule.every(cada_horas).hours.do(tarea_pipeline_etl)
    print(f"Orquestador iniciado con librería Schedule (cada {cada_horas} h). Presione Ctrl+C para salir.")

    # Ejecución inicial inmediata
    tarea_pipeline_etl()

    while True:
        schedule.run_pending()
        time.sleep(30)
