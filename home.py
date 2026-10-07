import requests
import json
import os

from env_loader import cargar_env

cargar_env()
BASE_URL = os.getenv("HA_URL", "http://homeassistant.local:8123")
TOKEN = os.getenv("HA_TOKEN", "")



def set_dispositivo(entity_id: str, action: str)-> None:

    if action not in ('turn_on', 'turn_off'):
        raise ValueError("Action debe ser 'turn_on' o 'turn_off'.")

    url = f"{BASE_URL}/api/services/light/{action}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": entity_id}

    resp = requests.post(url, json=payload, headers=headers)
    print(resp.json())
    resp.raise_for_status()  # Lanza excepción si hay error HTTP

    return  f"Dispositivo {entity_id} ha sido {action} correctamente."


def get_filtered_devices(domains=None) -> dict:

    if domains is None:
        domains = ["light", "media_player", "sensor", "weather","person"]

    # Llamada a la API para obtener todos los estados
    url = f"{BASE_URL}/api/states"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    all_states = resp.json()

    # Inicializa estructura filtrada
    devices = {domain: [] for domain in domains}

    # Filtra, selecciona campos y agrupa
    for state in all_states:
        eid = state.get("entity_id", "")
        dom = eid.split(".", 1)[0] if "." in eid else None
        if dom in devices:
            devices[dom].append({
                "entity_id": eid,
                "state": state.get("state"),
                "attributes": state.get("attributes", {})
            })

    # Ordena cada lista por entity_id
    for dom in devices:
        devices[dom].sort(key=lambda x: x["entity_id"])

    return devices
