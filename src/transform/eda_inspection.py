import pandas as pd

def comprension_inicial(df_ventas, df_logistica):

    print("\n" + "#"*60)
    print(" PARTE 3: COMPRENSIÓN INICIAL DE LOS DATASETS")
    print("#"*60)
    
    datasets = [("df_ventas", df_ventas), ("df_logistica", df_logistica)]
    
    for nombre, df in datasets:
        print(f"\n---> Exploración de {nombre} <---")
        print(f"1. Registros (Filas): {df.shape[0]}")
        print(f"2. Variables (Columnas): {df.shape[1]}")
        print(f"3. Nombres de variables: {list(df.columns)}")
        print("\n4 y 5. Tipos de datos y registros no nulos:")
        print(df.info())
        
        ids = [c for c in df.columns if 'id' in c.lower()]
        fechas = [c for c in df.columns if 'fecha' in c.lower() or 'tiempo' in c.lower()]
        num = list(df.select_dtypes(include=['number']).columns)
        cat = list(df.select_dtypes(include=['object', 'category']).columns)
        
        num = [c for c in num if c not in ids]
        cat = [c for c in cat if c not in ids and c not in fechas]
        
        print(f"\n6. Identificadores: {ids}")
        print(f"7. Categorical Variables: {cat}")
        print(f"8. Numeric Variables: {num}")
        print(f"9. Fecha / Tiempo: {fechas}")
        
        for f in fechas:
            try:
                col_dt = pd.to_datetime(df[f])
                print(f"   Rango de fechas en '{f}': {col_dt.min()} a {col_dt.max()}")
            except Exception:
                pass
                
    print("\n--- REPRESENTACIÓN CONCEPTUAL DE FILAS ---")
    print("• Una fila en df_ventas representa: Una transacción u orden de compra individual realizada por un cliente en un canal comercial.")
    print("• Una fila en df_logistica representa: Un evento u hito operativo (despacho, transporte, novedad, entrega) dentro del flujo de atención de un pedido_id.")


def perfil_calidad_datos(df_ventas, df_logistica):
    """
    PARTE 4. PERFIL INICIAL DE CALIDAD DEL DATO (25 puntos)
    """
    print("\n" + "#"*60)
    print(" PARTE 4: PERFIL INICIAL DE CALIDAD DEL DATO")
    print("#"*60)
    
    for nombre, df in [("df_ventas", df_ventas), ("df_logistica", df_logistica)]:
        print(f"\n=== PERFIL DE CALIDAD: {nombre} ===")
        
        # 4.1 Nulos
        nulos_cnt = df.isnull().sum()
        nulos_pct = (nulos_cnt / len(df)) * 100
        df_nulos = pd.DataFrame({'Cantidad Nulos': nulos_cnt, 'Porcentaje (%)': nulos_pct}).sort_values(by='Porcentaje (%)', ascending=False)
        print("\n--- 4.1 Valores Nulos (Organizados de mayor a menor) ---")
        print(df_nulos)
        
        # 4.2 Valores únicos / Cardinalidad
        df_unicos = pd.DataFrame({'Valores Unicos': df.nunique()})
        df_unicos['Alta Cardinalidad'] = df_unicos['Valores Unicos'] > (len(df) * 0.5)
        print("\n--- 4.2 Cardinalidad (nunique) ---")
        print(df_unicos)
        
        # 4.3 Duplicados
        tot_dups = df.duplicated().sum()
        print(f"\n--- 4.3 Filas completamente duplicadas: {tot_dups} ---")
        for id_col in [c for c in df.columns if 'id' in c.lower()]:
            print(f"    Duplicados en identificador '{id_col}': {df[id_col].duplicated().sum()}")


def estadisticos_descriptivos(df_ventas, df_logistica):
    """
    PARTE 5. ESTADÍSTICOS DESCRIPTIVOS Y RESÚMENES (15 puntos)
    """
    print("\n" + "#"*60)
    print(" PARTE 5: ESTADÍSTICOS DESCRIPTIVOS Y RESÚMENES")
    print("#"*60)
    
    print("\n--- 5.1 df_ventas ---")
    print("Estadísticas numéricas:")
    print(df_ventas.describe().T)
    for c in ['ciudad', 'canal', 'categoria']:
        if c in df_ventas.columns:
            print(f"\nVentas por {c}:\n", df_ventas[c].value_counts())
            
    print("\n--- 5.2 df_logistica ---")
    print("Estadísticas numéricas:")
    print(df_logistica.describe().T)
    for c in ['estado_evento', 'ciudad_destino', 'transportadora', 'incidencia']:
        if c in df_logistica.columns:
            print(f"\nFrecuencia de {c}:\n", df_logistica[c].value_counts())