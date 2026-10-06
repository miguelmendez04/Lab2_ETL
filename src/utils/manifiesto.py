"""
Manifiesto de ejecución: registra qué carga de Bronze se procesó, cuántas filas tiene cada archivo
de cada capa, el resultado de las validaciones y el estado final. Permite responder
"¿de dónde salió este dato?" (linaje Bronze -> Silver -> Gold).
"""
import json
import os
from datetime import datetime
from src.utils.config import cargar_config


def nuevo_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class Manifiesto:
    def __init__(self, origen, id_carga=None, config_path="config/config.yaml"):
        self.config_path = config_path
        self.datos = {
            "id_ejecucion": nuevo_id(),
            "id_carga": id_carga,
            "origen": origen,  # "extraccion" o "reproceso"
            "inicio": datetime.now().isoformat(timespec="seconds"),
            "fin": None,
            "duracion_s": None,
            "estado": "EN CURSO",
            "error": None,
            "fuentes": {},
            "capas": {"bronze": [], "silver": [], "gold": []},
            "validaciones": {},
        }

    @property
    def id_ejecucion(self):
        return self.datos["id_ejecucion"]

    @property
    def id_carga(self):
        return self.datos["id_carga"]

    @id_carga.setter
    def id_carga(self, valor):
        self.datos["id_carga"] = valor

    def fuente(self, nombre, **info):
        self.datos["fuentes"][nombre] = info

    def archivo(self, capa, ruta, df):
        self.datos["capas"][capa].append({"ruta": ruta.replace("\\", "/"), "filas": int(df.shape[0]),
                                          "columnas": int(df.shape[1])})

    def validaciones(self, capa, reglas):
        fallidas = [f"{r['Capa']}: {r['Regla']} ({r['Detalle']})" for r in reglas if not r["Cumple"]]
        self.datos["validaciones"][capa] = {"total": len(reglas), "cumplidas": len(reglas) - len(fallidas),
                                            "fallidas": fallidas, "reglas": reglas}

    def cerrar(self, estado, error=None):
        fin = datetime.now()
        self.datos["fin"] = fin.isoformat(timespec="seconds")
        self.datos["duracion_s"] = round((fin - datetime.fromisoformat(self.datos["inicio"])).total_seconds(), 1)
        self.datos["estado"] = estado
        self.datos["error"] = error
        carpeta = cargar_config(self.config_path)["paths"]["manifiestos_dir"]
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, f"{self.id_ejecucion}.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(self.datos, f, ensure_ascii=False, indent=2, default=str)
        return ruta


def escribir_linaje(carpeta_capa, manifiesto):
    """Deja en la carpeta de la capa un _linaje.json que apunta a la ejecución y la carga de Bronze de origen."""
    os.makedirs(carpeta_capa, exist_ok=True)
    with open(os.path.join(carpeta_capa, "_linaje.json"), "w", encoding="utf-8") as f:
        json.dump({"id_ejecucion": manifiesto.id_ejecucion, "id_carga": manifiesto.id_carga,
                   "origen": manifiesto.datos["origen"],
                   "generado": datetime.now().isoformat(timespec="seconds")}, f, ensure_ascii=False, indent=2)


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)
