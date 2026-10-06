from src.extract.extract_db import extraer_ventas_db
from src.extract.extract_excel import extraer_logistica_excel
from src.eda.eda_inspection import comprension_inicial, perfil_calidad_datos, estadisticos_descriptivos, revisar_tipos
from src.eda.business_questions import responder_preguntas_negocio
from src.pipeline import aterrizar_bronze, transformar


def main():
    print("==================================================")
    print(" INICIANDO EJECUCIÓN COMPLETA KAISMART SOLUTIONS ")
    print("==================================================")

    # PARTES 1 Y 2: EXTRACCIÓN
    df_ventas = extraer_ventas_db()
    df_logistica = extraer_logistica_excel()

    if df_ventas is None or df_logistica is None:
        print("No se pudo completar la extracción. Revise logs/pipeline.log")
        return

    # CAPA BRONZE: los datos originales se guardan apenas se extraen (abre el manifiesto de la ejecución)
    manifiesto = aterrizar_bronze(df_ventas, df_logistica)

    # PARTE 3: COMPRENSIÓN INICIAL
    comprension_inicial(df_ventas, df_logistica)

    # PARTE 4: PERFIL DE CALIDAD DEL DATO (4.1-4.3 y 4.4)
    perfil_calidad_datos(df_ventas, df_logistica)
    revisar_tipos(df_ventas, df_logistica)

    # PARTE 5: ESTADÍSTICOS DESCRIPTIVOS
    estadisticos_descriptivos(df_ventas, df_logistica)

    # PARTE 6: PREGUNTAS DE NEGOCIO
    responder_preguntas_negocio(df_ventas, df_logistica)

    # PARTE 7: TRANSFORMACIÓN MEDALLION (Silver y Gold se construyen leyendo Bronze)
    df_ventas_transformado, df_logisitica_transformado, df_gold = transformar(manifiesto)

    print("\n==================================================")
    print(" PROCESO EJECUTADO Y COMPLETADO CON ÉXITO ")
    print(f" Carga de Bronze: {manifiesto.id_carga}")
    print(f" df_ventas_transformado: {df_ventas_transformado.shape}")
    print(f" df_logisitica_transformado: {df_logisitica_transformado.shape}")
    print(f" Gold (1 fila por pedido): {df_gold.shape}")
    print("==================================================")


if __name__ == "__main__":
    main()
