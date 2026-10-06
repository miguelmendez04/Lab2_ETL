import yaml


def cargar_config(config_path="config/config.yaml"):
    """Lee config.yaml (autores, rutas y reglas de negocio)."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
