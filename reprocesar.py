"""
Reprocesa Silver y Gold desde el histórico de Bronze, sin volver a extraer de MySQL ni del Excel.

    python reprocesar.py                      # usa la carga más reciente
    python reprocesar.py --carga 20261005_200607
    python reprocesar.py --listar             # muestra las cargas disponibles
"""
import argparse
from src.load.load import listar_cargas
from src.pipeline import reprocesar

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reprocesa Silver y Gold desde una carga de Bronze.")
    parser.add_argument("--carga", help="id de la carga (AAAAMMDD_HHMMSS); por defecto, la más reciente")
    parser.add_argument("--listar", action="store_true", help="lista las cargas disponibles y termina")
    args = parser.parse_args()

    if args.listar:
        cargas = listar_cargas()
        print("\n".join(cargas) if cargas else "No hay cargas en data/bronze/historico")
    else:
        df_v, df_l, df_gold = reprocesar(args.carga)
        print(f"Reproceso terminado. Silver: ventas {df_v.shape}, logística {df_l.shape} | Gold: {df_gold.shape}")
