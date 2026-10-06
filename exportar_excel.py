"""Exporta a data/excel/ todas las tablas Parquet de Bronze (última carga), Silver y Gold, para revisarlas en Excel."""
import glob
import os
import pandas as pd
from src.utils.config import cargar_config

paths = cargar_config()["paths"]
capas = {
    "bronze": [paths["bronze_dir"]],
    "silver": [paths["silver_dir"], os.path.join(paths["silver_dir"], "rechazados")],
    "gold": [paths["gold_dir"]],
}

salida = "data/excel"
os.makedirs(salida, exist_ok=True)

for capa, carpetas in capas.items():
    for carpeta in carpetas:
        for archivo in sorted(glob.glob(os.path.join(carpeta, "*.parquet"))):
            df = pd.read_parquet(archivo)
            nombre = os.path.splitext(os.path.basename(archivo))[0]
            ruta = os.path.join(salida, f"{capa}_{nombre}.xlsx")
            df.to_excel(ruta, index=False)
            print(f"{ruta}: {df.shape[0]} filas x {df.shape[1]} columnas")
