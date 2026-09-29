import logging
import os
import yaml

def setup_logger(config_path="config/config.yaml"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            log_file = config["paths"]["log_file"]
    else:
        log_file = "logs/pipeline.log"
        
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logger = logging.getLogger("KaismartETL")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] - %(message)s")
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
    return logger