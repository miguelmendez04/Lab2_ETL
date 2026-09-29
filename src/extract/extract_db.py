import pandas as pd
from sqlalchemy import create_engine
import yaml
from src.utils.logger import setup_logger
import os
from dotenv import load_dotenv

def extraer_ventas_db(config_path="config/config.yaml"):
    
    logger = setup_logger(config_path)
    logger.info("PARTE 1: Iniciando extracción desde la Base de Datos MySQL...")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    db_cfg = config["database"]
    load_dotenv()
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    db = os.getenv("DB_NAME")
    connection_string = f"mysql+pymysql://{user}:{password}@{host}/{db}"
    engine = None
    
    try:
        engine = create_engine(connection_string)
        query = f"SELECT * FROM {db_cfg['table_ventas']};"
        
        df_ventas = pd.read_sql(query, con=engine)
        
        print("\n" + "="*50)
        print("  PARTE 1: COMPROBACIÓN DE EXTRACCIÓN - df_ventas")
        print("="*50)
        print(f"df_ventas.shape: {df_ventas.shape}")
        print(f"df_ventas.columns:\n{list(df_ventas.columns)}")
        print("\ndf_ventas.head():")
        print(df_ventas.head())
        print("\nMuestra aleatoria de 5 registros:")
        print(df_ventas.sample(n=min(5, len(df_ventas)), random_state=42))
        print("="*50 + "\n")
        
        logger.info(f"df_ventas extraído con éxito. Registros: {df_ventas.shape[0]}, Columnas: {df_ventas.shape[1]}")
        return df_ventas

    except Exception as e:
        logger.error(f"Error al extraer datos desde MySQL: {e}")
        return None
        
    finally:
        if engine:
            engine.dispose()
            logger.info("Conexión MySQL cerrada correctamente.")