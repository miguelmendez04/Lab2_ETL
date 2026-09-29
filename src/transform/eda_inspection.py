import pandas as pd

def _identificadores(df):
    return [c for c in df.columns
            if c.lower().startswith("id_") or c.lower().endswith("_id") or c.lower() == "numero_guia"]

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
        
        ids = _identificadores(df)
        fechas = [c for c in df.columns if c.lower().startswith("fecha")]
        num = [c for c in df.select_dtypes(include="number").columns if c not in ids]
        cat = [c for c in df.columns if c not in ids + fechas + num]
        
        num = [c for c in num if c not in ids]
        cat = [c for c in cat if c not in ids and c not in fechas]
        
        print(f"\n6. Identificadores: {ids}")
        print(f"7. Categorical Variables: {cat}")
        print(f"8. Numeric Variables: {num}")
        print(f"9. Fecha / Tiempo: {fechas}")

        basura = [c for c in df.columns if c.startswith("Unnamed")]
        if basura:
            print(f"   ATENCIÓN: columnas sin nombre (posible basura del Excel): {basura}")

        for f in fechas:
            try:
                col_dt = pd.to_datetime(df[f], errors="coerce")
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
        for id_col in _identificadores(df):
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
    print("\nDistribución de cantidad:\n", df_ventas["cantidad"].value_counts().sort_index())
    print("\nDistribución de calificacion_cliente (no nulos):\n", df_ventas["calificacion_cliente"].value_counts().sort_index())
            
    print("\n--- 5.2 df_logistica ---")
    print("Estadísticas numéricas:")
    print(df_logistica.describe().T)
    for c in ['estado_evento', 'ciudad_destino', 'transportadora', 'incidencia']:
        if c in df_logistica.columns:
            print(f"\nFrecuencia de {c}:\n", df_logistica[c].value_counts())

def revisar_tipos(df_ventas, df_logistica):
    reglas = {
        "df_ventas": {
            "fechas": ["fecha_venta"],
            "monetarias": ["precio_unitario", "valor_bruto", "valor_descuento", "valor_neto"],
            "ids_texto": ["pedido_id", "id_cliente", "id_tienda"],
        },
        "df_logistica": {
            "fechas": ["fecha_evento", "fecha_prometida_entrega"],
            "monetarias": ["costo_envio"],
            "ids_texto": ["pedido_id", "numero_guia"],
        },
    }
    print("\n" + "#"*60)
    print(" 4.4 REVISIÓN DE TIPOS DE DATOS")
    print("#"*60)
    for nombre, df in [("df_ventas", df_ventas), ("df_logistica", df_logistica)]:
        r = reglas[nombre]
        print(f"\n=== {nombre} ===")
        print(df.dtypes.to_frame("dtype_actual"))
        for c in r["fechas"]:
            ok = pd.api.types.is_datetime64_any_dtype(df[c])
            print(f"  {c}: {'OK' if ok else 'REVISAR: debería ser datetime, llegó como ' + str(df[c].dtype)}")
        for c in r["monetarias"]:
            ok = pd.api.types.is_numeric_dtype(df[c])
            print(f"  {c}: {'OK (numérico)' if ok else 'REVISAR: monto no numérico'}")
        for c in r["ids_texto"]:
            ok = not pd.api.types.is_numeric_dtype(df[c])
            print(f"  {c}: {'OK (texto)' if ok else 'REVISAR: id numérico'}")
    print("\nOtras columnas a revisar antes de analizar:")
    print("  - calificacion_cliente: es float por los nulos, pero es una escala 1-5 (mejor Int64 o categoría ordinal).")
    print("  - descuento_pct: solo 5 valores, se comporta como categoría.")
    print("  - tiempo_etapa_horas: es una duración numérica, no una fecha.")
    print("  - Unnamed: 13: columna basura del Excel.")