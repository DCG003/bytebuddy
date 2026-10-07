"""Carga en os.environ las variables del archivo .env de la carpeta del proyecto, si existe.

Las variables ya definidas en el sistema tienen prioridad sobre las del archivo.
"""
import os
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")


def cargar_env(ruta: Path = ENV_FILE) -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
