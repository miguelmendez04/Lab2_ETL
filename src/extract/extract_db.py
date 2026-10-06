import os
import pandas as pd
import mysql.connector
from dotenv import load_dotenv
from src.utils.config import cargar_config
from src.utils.logger import setup_logger


def extraer_ventas_db(config_path="config/config.yaml"):
    """
    PARTE 1. EXTRACCIÓN DESDE LA BASE DE DATOS (MySQL - base 'clientes')
    1. Importa mysql.connector (librería vista en clase).
    2. Crea la conexión con las credenciales del archivo .env.
    3-4. Consulta la tabla ventas y extrae todos los registros.
    5. Almacena el resultado en df_ventas.
    6. Comprueba la extracción: shape, columns, head() y muestra aleatoria de 5.
    7. Cierra el cursor y la conexión.
    """
    logger = setup_logger(config_path)
    logger.info("PARTE 1: Iniciando extracción desde la Base de Datos MySQL...")

    tabla = cargar_config(config_path)["database"]["table_ventas"]

    load_dotenv()
    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
        )
        logger.info("Conexión MySQL establecida.")

        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {tabla};")
        registros = cursor.fetchall()

        # coerce_float convierte los DECIMAL de MySQL a float (si no, quedan como objetos Decimal)
        df_ventas = pd.DataFrame.from_records(registros, columns=cursor.column_names, coerce_float=True)

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

    except mysql.connector.Error as e:
        logger.error(f"Error al extraer datos desde MySQL: {e}")
        return None

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()
            logger.info("Conexión MySQL cerrada correctamente.")
