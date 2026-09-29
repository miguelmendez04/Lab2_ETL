from src.extract.extract_db import extraer_ventas_db
from src.extract.extract_excel import extraer_logistica_excel
from src.transform.eda_inspection import comprension_inicial, perfil_calidad_datos, estadisticos_descriptivos, revisar_tipos
from src.transform.business_questions import responder_preguntas_negocio
from src.transform.transform_medallion import ejecutar_transformacion_medallion

def main():
    print("==================================================")
    print(" INICIANDO EJECUCIÓN COMPLETA KAISMART SOLUTIONS ")
    print("==================================================")
    
    # PARTES 1 Y 2: EXTRACCIÓN
    df_ventas = extraer_ventas_db()
    df_logistica = extraer_logistica_excel()
    
    if df_ventas is not None and df_logistica is not None:
        # PARTE 3: COMPRENSIÓN INICIAL
        comprension_inicial(df_ventas, df_logistica)
        
        # PARTE 4: PERFIL DE CALIDAD DEL DATO
        perfil_calidad_datos(df_ventas, df_logistica)
        revisar_tipos(df_ventas, df_logistica)
        
        # PARTE 5: ESTADÍSTICOS DESCRIPTIVOS
        estadisticos_descriptivos(df_ventas, df_logistica)
        
        # PARTE 6: PREGUNTAS DE NEGOCIO
        responder_preguntas_negocio(df_ventas, df_logistica)
        
        # PARTE 7: TRANSFORMACIÓN MEDALLION
        df_v_trans, df_l_trans, df_gold = ejecutar_transformacion_medallion(df_ventas, df_logistica)
        
        print("\n==================================================")
        print(" PROCESO EJECUTADO Y COMPLETADO CON ÉXITO ")
        print("==================================================")

if __name__ == "__main__":
    main()