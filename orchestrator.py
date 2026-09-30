import time
import schedule
from src.extract.extract_db import extraer_ventas_db
from src.extract.extract_excel import extraer_logistica_excel
from src.transform.transform_medallion import ejecutar_transformacion_medallion
from src.utils.logger import setup_logger

logger = setup_logger()


def tarea_pipeline_etl():
    inicio = time.time()
    logger.info("=== EJECUTANDO TAREA PROGRAMADA DE PIPELINE ETL ===")
    try:
        df_v = extraer_ventas_db()
        df_l = extraer_logistica_excel()

        if df_v is None or df_l is None:
            logger.error("Cancelado por falla en extracción de datos.")
            return

        ejecutar_transformacion_medallion(df_v, df_l)
        logger.info(f"=== PIPELINE COMPLETADO CON ÉXITO en {time.time() - inicio:.1f} s ===")
    except Exception as e:
        logger.error(f"Falla inesperada en el pipeline: {e}")


# Frecuencia de producción: cada 1 hora
schedule.every(1).hours.do(tarea_pipeline_etl)

if __name__ == "__main__":
    print("Orquestador iniciado con librería Schedule. Presione Ctrl+C para salir.")
    # Ejecución inicial inmediata
    tarea_pipeline_etl()

    while True:
        schedule.run_pending()
        time.sleep(30)