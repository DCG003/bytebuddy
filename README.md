# ByteBuddy · Asistente de escritorio con IA local

Asistente para Windows que funciona con un modelo de lenguaje **local** servido por
[Ollama](https://ollama.com). Vive en una ventana flotante en la esquina de la pantalla y en la
bandeja del sistema, responde en streaming y puede actuar sobre el equipo mediante llamadas a
funciones.

## Qué hace

- **Chat con un LLM local** a través de la API compatible con OpenAI de Ollama (por defecto
  `gemma3:4b`). Las respuestas llegan en streaming por Socket.IO.
- **Imágenes en el chat:** se puede adjuntar una imagen junto al mensaje.
- **Llamadas a funciones:** el modelo responde en JSON y, cuando lo necesita, añade un campo
  `llamada` que la aplicación ejecuta:
  - estado del equipo (CPU, GPU, memoria, discos, temperaturas y carga) y procesos que más consumen;
  - aplicaciones ejecutadas recientemente;
  - captura de pantalla, bloqueo de la sesión, abrir URLs y rutas, iniciar o cerrar aplicaciones;
  - recomendaciones de canciones.
- **Control de Spotify:** canción actual, reproducir o pausar, siguiente y anterior, playlists,
  recomendaciones y cola.
- **Contexto del usuario de Windows** (vía WMI) incluido en las instrucciones del modelo.
- **Historial de conversación** guardado en local, un archivo por día.
- **Módulo de Home Assistant** (`home.py`) para consultar estados y encender o apagar luces.

## Tecnologías

Python · Flask · Flask-SocketIO · pywebview · pystray · Ollama (API compatible con OpenAI) ·
Spotipy · WMI · psutil · GPUtil

## Instalación

Requisitos: Windows, Python 3.12 y Ollama.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
ollama pull gemma3:4b
copy .env.example .env
```

Rellena `.env` con tus claves (Spotify y, si lo usas, Home Assistant) y arranca:

```powershell
.venv\Scripts\python main.py
```

`ByteBuddy.vbs` arranca la aplicación sin ventana de consola.

## Configuración

| Variable | Para qué |
|---|---|
| `SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET` | Credenciales de tu app de Spotify |
| `SPOTIPY_REDIRECT_URI` | URI de redirección registrada en Spotify (`http://localhost:8080`) |
| `HA_URL` / `HA_TOKEN` | Dirección y token de larga duración de Home Assistant (opcional) |
| `FLASK_SECRET_KEY` | Clave de sesión de Flask (opcional; si falta se genera una aleatoria) |

Las conversaciones, los registros y las imágenes subidas se guardan en `conversaciones/`, `logs/`
y `uploads/`, que no se suben al repositorio.
