import os
import pandas as pd

archivos = {
    "bronze": ["ventas_bronze", "logistica_bronze"],
    "silver": ["df_ventas_transformado", "df_logistica_transformado"],
    "gold": ["ventas_logistica_gold", "eventos_gold"],
}

salida = "data/excel"
os.makedirs(salida, exist_ok=True)

for capa, nombres in archivos.items():
    for nombre in nombres:
        df = pd.read_parquet(f"data/{capa}/{nombre}.parquet")
        ruta = f"{salida}/{capa}_{nombre}.xlsx"
        df.to_excel(ruta, index=False)
        print(f"{ruta}: {df.shape[0]} filas x {df.shape[1]} columnas")