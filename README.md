# Laboratorio ETL: Kaismart Solutions S.A.S.

Pipeline ETL en Python con arquitectura Medallion (Bronze → Silver → Gold) sobre dos fuentes:

- **Ventas:** base MySQL `clientes`, tabla `ventas` (5.000 registros), en `df_ventas`.
- **Logística:** `data/kaismart_eventos_logisticos.xlsx` (50.000 eventos), en `df_logistica`.

Los autores están en [config/config.yaml](config/config.yaml).

## Instalación

Requiere **Python 3.11** (probado con 3.11.9). Las librerías tienen versiones fijas en `requirements.txt` para que los resultados sean idénticos en cualquier equipo.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

Copie `.env.example` como `.env` y complete las credenciales de MySQL.

## Ejecución

Todos los comandos se ejecutan desde la raíz del proyecto.

| Comando | Qué hace |
|---|---|
| `python main.py` | Ejecuta todo: extracción (Partes 1-2), EDA (3-5), preguntas de negocio (6) y Medallion (7) |
| `python orchestrator.py` | Parte 8: ejecuta el pipeline ETL con `schedule` al iniciar y luego cada `orquestador.cada_horas` |
| `python reprocesar.py [--carga ID] [--listar]` | Reconstruye Silver y Gold desde una carga del histórico de Bronze, sin volver a extraer |
| `python generar_informe.py` | Genera `docs/Informe_KaismartSolutions.md` y `.html` desde las capas Medallion |
| `python exportar_excel.py` | Exporta cada capa a `data/excel/` para revisarla en Excel |
| `notebooks/EDA.ipynb` | Presentación paso a paso de las Partes 1 a 8 con sus salidas |

## Estructura

```
config/config.yaml                    autores, rutas y reglas de negocio (cobertura, estados de transporte)
src/extract/extract_db.py             Parte 1: MySQL con mysql.connector -> df_ventas
src/extract/extract_excel.py          Parte 2: Excel -> df_logistica
src/eda/eda_inspection.py             Partes 3, 4 y 5: comprensión, calidad y descriptivos
src/eda/business_questions.py         Parte 6: 10 preguntas de negocio
src/load/load.py                      capa Bronze (justo después de extraer) y guardado de cada capa
src/transform/transform_medallion.py  Parte 7: silver_ventas, silver_logistica y capa_gold
src/transform/validaciones.py         reglas de calidad que se verifican antes de publicar Silver y Gold
src/pipeline.py                       flujo completo (extraer -> Bronze -> Silver -> Gold) y reproceso desde Bronze
src/utils/manifiesto.py               manifiesto de ejecución y linaje
src/utils/                            configuración y logger compartidos
orchestrator.py                       Parte 8: automatización con schedule
data/bronze | silver | gold           capas Medallion (Parquet)
data/bronze/historico/                copia de cada carga (Parquet + .xlsx original); se conservan las últimas bronze.max_cargas
data/silver/incidencias_calidad       cada problema de calidad detectado y la acción tomada
data/silver/rechazados/               cuarentena: filas que no cumplen una regla, con su motivo
data/gold/kpi_mensual | desempeno_transportadora | ventas_ciudad_canal   tablas agregadas listas para consumo
data/manifiestos/                     un JSON por ejecución: fuentes, filas por capa, validaciones y estado
docs/                                 informe con hallazgos y conclusiones
logs/pipeline.log                     bitácora de ejecuciones
```

Flujo: **extraer → Bronze → (EDA y preguntas sobre Bronze) → Silver (leyendo Bronze) → validar → Gold → validar → manifiesto**.

## Calidad y operación

- **Validaciones:** antes de guardar Silver y Gold se verifican 33 reglas: unicidad de claves, nulos recuperables en cero, transportadora presente en los estados de transporte, cobertura de ciudades, Gold 1 a 1 sin duplicar montos, tablas agregadas que cuadran con Gold, etc. Si alguna falla, el pipeline se detiene, no publica y registra el detalle en `logs/pipeline.log`.
- **Errores:** el orquestador guarda la traza completa de cualquier falla (`logger.exception`).
- **Histórico de Bronze:** cada ejecución deja una copia (Parquet y el `.xlsx` original) en `data/bronze/historico/`. La retención se configura en `config.yaml` → `bronze`.
- **Reproceso:** como Silver se construye leyendo Bronze, `python reprocesar.py --carga ID` reconstruye Silver y Gold desde cualquier carga sin consultar las fuentes.
- **Cuarentena:** las filas que no cumplen una regla van a `silver/rechazados/` y el resto se publica. Si superan `silver.max_pct_rechazados` (5 %), el pipeline se detiene.
- **Incidencias:** `silver/incidencias_calidad` documenta cada problema detectado y qué se hizo con él.
- **Linaje:** cada ejecución escribe `data/manifiestos/<id>.json`, y `silver/_linaje.json` y `gold/_linaje.json` indican de qué carga provienen.

## DataFrames del enunciado

- `df_ventas` y `df_logistica`: datos originales (también en `data/bronze/`).
- `df_ventas_transformado` y `df_logisitica_transformado`: datos depurados (`data/silver/`).
- Gold: `ventas_logistica_gold` (1 fila por pedido, con montos, costo de envío, retraso, tiempo de ciclo y mes) y `eventos_gold` (1 fila por evento).
  `eventos_gold` no trae los montos de la venta para que no se sumen ~10 veces por pedido. `costo_envio` también se
  repite en cada evento: súmelo solo desde `ventas_logistica_gold`.
