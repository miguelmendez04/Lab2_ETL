import os
import pandas as pd
from src.utils.config import cargar_config
from src.utils.logger import setup_logger

def extraer_logistica_excel(config_path="config/config.yaml"):
    """
    PARTE 2. EXTRACCIÓN DESDE EL ARCHIVO EXCEL
    1. Lee el archivo kaismart_eventos_logisticos.xlsx (50.000 registros).
    2. Almacena en df_logistica.
    3. Comprueba mostrando shape, columns, head() y muestra aleatoria.
    """
    logger = setup_logger(config_path)
    logger.info("Iniciando PARTE 2: Extracción desde Excel (Sistema Logístico)...")
    
    excel_path = cargar_config(config_path)["paths"]["excel_logistica"]
    
    if not os.path.exists(excel_path):
        logger.error(f"El archivo Excel no existe en la ruta: {excel_path}")
        return None
        
    df_logistica = pd.read_excel(excel_path)
    
    # Comprobar la extracción
    print("\n" + "="*50)
    print("    COMPROBACIÓN EXTRACCIÓN: df_logistica")
    print("="*50)
    print(f"df_logistica.shape: {df_logistica.shape}")
    print(f"\ndf_logistica.columns:\n{list(df_logistica.columns)}")
    print("\ndf_logistica.head():")
    print(df_logistica.head())
    print("\nMuestra aleatoria de 5 registros:")
    print(df_logistica.sample(n=min(5, len(df_logistica)), random_state=42))
    print("="*50 + "\n")
    
    logger.info(f"Extracción exitosa de df_logistica con forma {df_logistica.shape}")
    return df_logistica