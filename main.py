import threading
import time
import webview
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from openai import OpenAI
import tkinter as tk
import json
import os
import sys
from datetime import date
import logging
import base64
import secrets
import glob
import platform
import ctypes
from PIL import Image
import pystray
from werkzeug.utils import secure_filename

# --- CONFIGURACIÓN INICIAL Y RUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import estadopc as pc
import user_info
from env_loader import cargar_env

cargar_env()

import spotify_control as spotify

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
IMG_DIR = os.path.join(BASE_DIR, "img")
PROMPT_FILE = os.path.join(BASE_DIR, "prompt.txt")
CONVERS_PATH = os.path.join(BASE_DIR, "conversaciones")
LOGS_PATH = os.path.join(BASE_DIR, "logs")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(LOGS_PATH, exist_ok=True)
os.makedirs(CONVERS_PATH, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- CONFIGURACIÓN DE LOGGING ---
# (código de logging sin cambios)
fecha_hoy = date.today().strftime("%d-%m-%Y")
error_log_file = os.path.join(LOGS_PATH, f"error_{fecha_hoy}.log")
execution_log_file = os.path.join(LOGS_PATH, f"execution_{fecha_hoy}.log")
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
exec_handler = logging.FileHandler(execution_log_file, encoding="utf-8")
exec_handler.setLevel(logging.INFO)
exec_handler.setFormatter(formatter)
error_handler = logging.FileHandler(error_log_file, encoding="utf-8")
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)
logger.addHandler(exec_handler)
logger.addHandler(error_handler)


# --- INICIALIZACIÓN DE LA APP Y EXTENSIONES ---
app = Flask(__name__, static_folder=None, template_folder=TEMPLATES_DIR)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
socketio = SocketIO(app, async_mode='threading')

client = OpenAI(base_url="http://localhost:11434/v1", api_key="local")
MODELO = "gemma3:4b"#"gpt-oss:20b"
TEMPERATURA = 0.1
window_global = None
spotify_monitor_thread = None
stop_spotify_monitor = threading.Event()

# --- LÓGICA DE SPOTIFY CON WEBSOCKETS ---
def spotify_monitor():
    """
    Hilo que monitorea Spotify y emite actualizaciones vía WebSocket.
    """
    last_track_name = None
    while not stop_spotify_monitor.is_set():
        try:
            current_track = spotify.get_current_track()
            track_name = current_track.get('name') if current_track else None
            
            if track_name != last_track_name:
                last_track_name = track_name
                logging.info(f"Spotify: cambió la canción a '{track_name}'. Emitiendo update.")
                socketio.emit('spotify_update', current_track if current_track else {})
        except Exception as e:
            logging.error(f"Error en el monitor de Spotify: {e}", exc_info=False)
        
        socketio.sleep(3) # Pausa de 3 segundos entre verificaciones

@socketio.on('connect')
def handle_connect():
    logging.info("Cliente conectado a WebSocket.")
    # Al conectarse un cliente, se le envía el estado actual de Spotify.
    try:
        current_track = spotify.get_current_track()
        socketio.emit('spotify_update', current_track if current_track else {})
    except Exception as e:
        logging.error(f"Error al enviar estado inicial de Spotify: {e}", exc_info=True)


# --- MANEJO DE CONVERSACIÓN ---
# (Las funciones de conversación no cambian)
def leer_conversacion():
    fecha_hoy = date.today().strftime("%d-%m-%Y")
    carpeta = CONVERS_PATH
    nombre_archivo = f"conversacion_{fecha_hoy}.json"
    ruta_completa = os.path.join(carpeta, nombre_archivo)

    if not os.path.exists(ruta_completa):
        conversacion = []
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                prompt = f.read()
        except Exception as e:
            logging.error(f"No se pudo leer el archivo prompt.txt: {e}", exc_info=True)
            prompt = ""

        try:
            info_user = user_info.obtener_info_usuario_actual()
        except Exception as e:
            logging.error(f"Error obteniendo info de usuario: {e}", exc_info=True)
            info_user = {}
        prompt = prompt.replace("*user_info*", str(info_user))
        conversacion.append({"role": "system", "content": prompt})
        logging.info("Nueva conversación iniciada con prompt del sistema.")
        return conversacion
    else:
        try:
            with open(ruta_completa, "r", encoding="utf-8") as f:
                conversacion = json.load(f)
            logging.info(f"Conversación existente cargada: {ruta_completa}")
        except Exception as e:
            logging.error(f"Error cargando conversación desde {ruta_completa}: {e}", exc_info=True)
            conversacion = []
        return conversacion

def guardar_conversacion(conversacion):
    fecha_hoy = date.today().strftime("%d-%m-%Y")
    carpeta = CONVERS_PATH
    nombre_archivo = f"conversacion_{fecha_hoy}.json"
    ruta_completa = os.path.join(carpeta, nombre_archivo)
    os.makedirs(carpeta, exist_ok=True)
    try:
        with open(ruta_completa, "w", encoding="utf-8") as f:
            json.dump(conversacion, f, ensure_ascii=False, indent=2)
        logging.info(f"Conversación guardada en: {ruta_completa}")
    except Exception as e:
        logging.error(f"Error guardando conversación en {ruta_completa}: {e}", exc_info=True)
    return ruta_completa

# --- Utilidades de robustez para respuestas JSON ---
def _to_safe_html(text: str) -> str:
    if text is None:
        return ""
    # Conversión mínima: saltos de línea a <br> y evitar comillas dobles
    safe = str(text).replace("\r\n", "\n").replace("\r", "\n")
    safe = safe.replace("\n", "<br>")
    safe = safe.replace('"', "'")
    return safe

def _ensure_json_response(raw_content: str) -> dict:
    try:
        if raw_content and raw_content.strip():
            return json.loads(raw_content)
    except Exception:
        pass
    # Fallback: encapsular como JSON válido
    return {"respuesta_usuario": f"<div>{_to_safe_html(raw_content or 'Sin contenido')}</div>"}

# --- Helper para usar web_search tool (si está disponible) ---
def crear_chat_completion(messages, allow_web_search: bool = False):
    base_kwargs = {
        "model": MODELO,
        "messages": messages,
        "temperature": TEMPERATURA,
        "response_format": {"type": "json_object"},
        "stream": True
    }
    try:
        # Usar herramienta de búsqueda solo si está permitida por el front
        if allow_web_search:
            return client.chat.completions.create(
                tools=[{"type": "web_search"}],
                tool_choice="auto",
                **base_kwargs,
            )
        else:
            return client.chat.completions.create(**base_kwargs)
    except Exception as e:
        if allow_web_search:
            logging.warning(f"Fallo al usar web_search tool, reintentando sin tools: {e}")
            # Fallback si el backend no soporta tools
            return client.chat.completions.create(**base_kwargs)
        raise

def obtener_contenido_modelo(messages, allow_web_search: bool = False) -> str:
    """Intenta varias estrategias para obtener contenido no vacío del modelo."""
    base = {
        "model": MODELO,
        "messages": messages,
        "temperature": TEMPERATURA,
    }
    strategies = []
    if allow_web_search:
        strategies.append({**base, "tools": [{"type": "web_search"}], "tool_choice": "auto", "response_format": {"type": "json_object"}})
    strategies.append({**base, "response_format": {"type": "json_object"}})
    strategies.append({**base})

    for idx, kwargs in enumerate(strategies, start=1):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = (resp.choices[0].message.content or "").strip()
            if content:
                logging.info(f"Estrategia {idx}: contenido obtenido ({len(content)} chars)")
                return content
            # Si no hay contenido pero hay tool_calls y no podemos manejarlas aquí, seguimos intentando
            if getattr(resp.choices[0].message, "tool_calls", None):
                logging.info(f"Estrategia {idx}: tool_calls presentes sin contenido, probando siguiente estrategia")
        except Exception as e:
            logging.warning(f"Estrategia {idx} falló: {e}")
            continue
    return ""

def hacer_llamada_funcion(funcion, parametros):
    try:
        params = []
        if isinstance(parametros, (list, tuple)):
            params = list(parametros)
        elif isinstance(parametros, dict):
            params = list(parametros.values())

        if funcion == "gestionar_aplicacion":
            if len(params) < 2:
                return {
                    "second_response": False,
                    "respuesta": "<div>No recibí suficientes datos para gestionar la aplicación solicitada.</div>"
                }
            nombre = params[0]
            accion = params[1]
            resultado = pc.gestionar_aplicacion(nombre, accion)
            logging.info(f"Ejecutando 'gestionar_aplicacion' para {nombre} ({accion})")
            return {
                "second_response": True,
                "respuesta": resultado
            }
        if funcion == "info_pc":
            respuesta = pc.obtener_informe_sistema()
            logging.info("Ejecutando función 'info_pc' para obtener informe del sistema.")
            return {
                "second_response": True,
                "respuesta": "Datos del equipo: " + str(respuesta)
            }
        if funcion == "registro_aplicaciones":
            lista_programas = user_info.listar_todas_las_entradas_UserAssist()
            logging.info("Ejecutando función 'registro_aplicaciones' para listar programas.")
            return {
                "second_response": True,
                "respuesta": "Lista programas: " + str(lista_programas)
            }
        if funcion == "recomendar_canciones":
            song_name = params[0] if params else ""
            logging.info(f"Ejecutando 'recomendar_canciones' para '{song_name}'")
            resultado = spotify.get_recommendations(song_name)
            
            if "error" in resultado:
                respuesta_final = resultado["error"]
            else:
                respuesta_final = (
                    f"Aquí tienes algunas recomendaciones basadas en '{song_name}':\n"
                    f"{', '.join(resultado.get('recommendations', []))}\n\n"
                    f"Estado de la cola: {resultado.get('queue_status', 'Desconocido.')}"
                )

            return {
                "second_response": True,
                "respuesta": respuesta_final
            }

        if funcion == "añadir_a_cola":
            song_list = params
            logging.info(f"Ejecutando 'añadir_a_cola' para {len(song_list)} canciones")
            resultado = spotify.add_songs_to_queue(song_list)
            return {
                "second_response": True,
                "respuesta": resultado.get("status", "Error al procesar la solicitud de añadir a la cola.")
            }
        if funcion == "resumen_procesos":
            limite = params[0] if params else 5
            try:
                datos = pc.obtener_resumen_procesos(limite)
            except Exception as e:
                logging.error("Error obteniendo resumen de procesos: %s", e, exc_info=True)
                mensaje = _to_safe_html(str(e))
                return {
                    "second_response": False,
                    "respuesta": f"<div>No se pudo obtener el resumen de procesos.<br><small>{mensaje}</small></div>"
                }

            cpu_items = "".join(
                f"<li>PID {item.get('pid', '?')} - {_to_safe_html(item.get('nombre'))} (CPU {item.get('cpu', 0)}%)</li>"
                for item in datos.get("top_cpu", [])
            )
            mem_items = "".join(
                f"<li>PID {item.get('pid', '?')} - {_to_safe_html(item.get('nombre'))} (Memoria {item.get('memoria', 0)}%)</li>"
                for item in datos.get("top_memoria", [])
            )
            if not cpu_items:
                cpu_items = "<li>No hay datos de CPU disponibles.</li>"
            if not mem_items:
                mem_items = "<li>No hay datos de memoria disponibles.</li>"

            html_respuesta = (
                "<div>Resumen rápido de procesos activos.<br>"
                "<b>CPU:</b><ul>" + cpu_items + "</ul>"
                "<b>Memoria:</b><ul>" + mem_items + "</ul></div>"
            )
            return {
                "second_response": False,
                "respuesta": html_respuesta
            }
        if funcion == "captura_pantalla":
            timestamp = int(time.time())
            nombre_archivo = f"captura_{timestamp}.png"
            ruta_destino = os.path.join(UPLOAD_FOLDER, nombre_archivo)
            try:
                pc.guardar_captura_pantalla(ruta_destino)
                html_respuesta = (
                    f"<div>He guardado una captura de pantalla reciente.<br>"
                    f"<img src='/uploads/{nombre_archivo}' alt='Captura de pantalla'></div>"
                )
                return {
                    "second_response": False,
                    "respuesta": html_respuesta
                }
            except Exception as e:
                logging.error("Error al capturar pantalla: %s", e, exc_info=True)
                mensaje = _to_safe_html(str(e))
                return {
                    "second_response": False,
                    "respuesta": f"<div>No pude tomar la captura.<br><small>{mensaje}</small></div>"
                }
        if funcion == "bloquear_equipo":
            try:
                pc.bloquear_equipo()
                return {
                    "second_response": False,
                    "respuesta": "<div>He bloqueado el equipo. Podrás reanudar cuando inicies sesión de nuevo.</div>"
                }
            except Exception as e:
                logging.error("Error al bloquear el equipo: %s", e, exc_info=True)
                mensaje = _to_safe_html(str(e))
                return {
                    "second_response": False,
                    "respuesta": f"<div>No pude bloquear el equipo.<br><small>{mensaje}</small></div>"
                }
        if funcion == "abrir_url":
            if not params:
                return {
                    "second_response": False,
                    "respuesta": "<div>No recibí ninguna dirección web para abrir.</div>"
                }
            try:
                url_abierta = pc.abrir_url(str(params[0]))
                html_respuesta = f"<div>He abierto la página {_to_safe_html(url_abierta)} en el navegador predeterminado.</div>"
                return {
                    "second_response": False,
                    "respuesta": html_respuesta
                }
            except Exception as e:
                logging.error("Error al abrir URL: %s", e, exc_info=True)
                mensaje = _to_safe_html(str(e))
                return {
                    "second_response": False,
                    "respuesta": f"<div>No pude abrir la página solicitada.<br><small>{mensaje}</small></div>"
                }
        if funcion == "abrir_ruta":
            if not params:
                return {
                    "second_response": False,
                    "respuesta": "<div>No recibí ninguna ruta para abrir.</div>"
                }
            try:
                ruta_abierta = pc.abrir_ruta(str(params[0]))
                html_respuesta = f"<div>He abierto la ruta {_to_safe_html(ruta_abierta)} en el explorador.</div>"
                return {
                    "second_response": False,
                    "respuesta": html_respuesta
                }
            except FileNotFoundError as e:
                logging.warning("Ruta no encontrada: %s", e)
                mensaje = _to_safe_html(str(e))
                return {
                    "second_response": False,
                    "respuesta": f"<div>No encontré la ruta indicada.<br><small>{mensaje}</small></div>"
                }
            except Exception as e:
                logging.error("Error al abrir ruta: %s", e, exc_info=True)
                mensaje = _to_safe_html(str(e))
                return {
                    "second_response": False,
                    "respuesta": f"<div>No pude abrir la ruta solicitada.<br><small>{mensaje}</small></div>"
                }
        # Si no coincide ninguna función, devolver mensaje neutro
        logging.warning(f"Función solicitada desconocida: {funcion}")
        return {"respuesta": f"Función desconocida: {funcion}", "second_response": False}
    except Exception as e:
        logging.error(f"Error al hacer llamada a la función {funcion}: {e}", exc_info=True)
        return {
            "respuesta": f"Error al hacer llamada a la función {funcion}: {e}",
            "second_response": False
        }


# --- RUTAS HTTP Y DE CHAT ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/img/<path:filename>")
def img_files(filename):
    return send_from_directory(IMG_DIR, filename)


@app.route("/uploads/<path:filename>")
def upload_files(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    allow_web_search = bool(data.get("allow_web_search", False))

    logging.info(f"Mensaje recibido del usuario: {user_message}")

    # Leer o inicializar conversación
    conversacion = leer_conversacion()
    conversacion.append({"role": "user", "content": user_message})

    try:
        raw_content = obtener_contenido_modelo(conversacion, allow_web_search=allow_web_search)
        logging.info(f"Respuesta cruda del modelo: {raw_content}")
    except Exception as e:
        logging.error(f"Error al llamar a la API de OpenAI: {e}", exc_info=True)
        return jsonify({"response": "Error interno al procesar la solicitud."}), 500

    response_json = _ensure_json_response(raw_content)

    try:
        llamada = response_json.get("llamada")
        if llamada:
            servicio = llamada.get("servicio")
            parametros = llamada.get("parametros", [])
            logging.info(f"El modelo solicitó la función '{servicio}' con parámetros: {parametros}")
            respuesta_func = hacer_llamada_funcion(servicio, parametros)

            if respuesta_func.get("second_response"):
                conversacion.append({"role": "system", "content": respuesta_func["respuesta"]})
                try:
                    second_content = obtener_contenido_modelo(conversacion, allow_web_search=allow_web_search)
                    logging.info(f"Segunda respuesta cruda del modelo: {second_content}")
                    response_json = _ensure_json_response(second_content)
                except Exception as e:
                    logging.error(f"Error en la segunda llamada al modelo: {e}", exc_info=True)
                    return jsonify({"response": "Error interno al procesar la segunda respuesta."}), 500
            else:
                response_json["respuesta_usuario"] = respuesta_func["respuesta"]
    except Exception as e:
        logging.error(f"Error procesando la llamada solicitada por el modelo: {e}", exc_info=True)

    # Extraer la respuesta final al usuario
    respuesta_usuario = response_json.get("respuesta_usuario", "")
    conversacion.append({"role": "assistant", "content": respuesta_usuario})
    guardar_conversacion(conversacion)

    logging.info(f"Respuesta final al usuario: {respuesta_usuario}")
    return jsonify({"response": respuesta_usuario})


@app.route("/chat_img", methods=["POST"])
def chat_img():
    # ... (código de la ruta de chat con imágenes sin cambios)
    user_text = request.form.get("message", "")
    allow_web_search = request.form.get("allow_web_search", "false").lower() in ("1","true","yes","on")
    img_file  = request.files.get("image")
    logging.info(f"Mensaje + posible imagen recibido: {user_text!r}")

    content = [{"type":"text","text": user_text}]
    if img_file:
        filename = secure_filename(img_file.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        img_file.save(path)
        logging.info(f"Imagen guardada en: {path}")
        data_url = encode_image_to_data_url(path)
        content.append({
            "type":"image_url",
            "image_url": {"url": data_url, "detail":"auto"}
        })

    conversacion = leer_conversacion()
    conversacion.append({"role":"user","content":content})

    try:
        raw = obtener_contenido_modelo(conversacion, allow_web_search=allow_web_search)
        logging.info(f"Respuesta cruda (multimodal): {raw}")
    except Exception as e:
        logging.error("Error OpenAI API (multimodal)", exc_info=True)
        return jsonify({"response":"Error interno al procesar la solicitud."}),500

    resp_json = _ensure_json_response(raw)

    try:
        llamada = resp_json.get("llamada")
        if llamada:
            svc = llamada.get("servicio")
            params = llamada.get("parametros", [])
            func_res = hacer_llamada_funcion(svc, params)
            if func_res.get("second_response"):
                conversacion.append({"role":"system","content":func_res["respuesta"]})
                raw2 = obtener_contenido_modelo(conversacion, allow_web_search=allow_web_search)
                resp_json = _ensure_json_response(raw2)
            else:
                resp_json["respuesta_usuario"] = func_res["respuesta"]
    except Exception as e:
        logging.error("Error en función multimodal", exc_info=True)

    final = resp_json.get("respuesta_usuario", "")
    conversacion.append({"role":"assistant","content":final})
    guardar_conversacion(conversacion)
    logging.info(f"Respuesta final multimodal: {final!r}")
    return jsonify({"response": final})


def encode_image_to_data_url(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = f"image/{'jpeg' if ext in ['jpg','jpeg'] else ext}"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# --- RUTAS PARA SPOTIFY (AHORA EMITEN UPDATES) ---
@app.route("/spotify/control", methods=["POST"])
def spotify_control_route():
    action = request.json.get("action")
    track = None
    try:
        if action == "play_pause": track = spotify.play_pause()
        elif action == "next": track = spotify.next_track()
        elif action == "previous": track = spotify.previous_track()
        else: return jsonify({"error": "Acción no válida"}), 400
        
        socketio.emit('spotify_update', track if track else {})
        return jsonify(track if track else {})
    except Exception as e:
        logging.error(f"Error en /spotify/control: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- CLASE API PARA WEBVIEW Y FUNCIONES DE UI ---
class API:
    def get_windows_avatar(self):
        if platform.system().lower() != "windows":
            return ""
        
        rutas = []
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            rutas.append(os.path.join(appdata, "Microsoft", "Windows", "AccountPictures"))
        
        programdata = os.environ.get("PROGRAMDATA", "")
        if programdata:
            rutas.append(os.path.join(programdata, "Microsoft", "User Account Pictures"))

        todos_archivos = []
        for carpeta in rutas:
            if os.path.isdir(carpeta):
                todos_archivos.extend(glob.glob(os.path.join(carpeta, "*.jpg")))
                todos_archivos.extend(glob.glob(os.path.join(carpeta, "*.png")))

        if not todos_archivos:
            return ""

        latest_file = max(todos_archivos, key=os.path.getmtime)

        try:
            with open(latest_file, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                mime = "image/png" if latest_file.lower().endswith(".png") else "image/jpeg"
                return f"data:{mime};base64,{encoded}"
        except Exception:
            return ""

    def hide_window(self):
        if window_global: window_global.hide()

def get_bottom_right_position(width, height, margin=20):
    root = tk.Tk()
    root.withdraw()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()
    x = screen_width - width - margin
    y = screen_height - height - margin
    return x, y

def hide_from_taskbar(title):
    if platform.system() != "Windows": return
    
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if not hwnd:
        # Reintentar un par de veces si la ventana aún no está lista
        for _ in range(5):
            time.sleep(0.1)
            hwnd = ctypes.windll.user32.FindWindowW(None, title)
            if hwnd: break
    
    if not hwnd:
        logging.error(f"No se pudo encontrar la ventana con el título '{title}' para ocultarla.")
        return

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    try:
        exstyle = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, exstyle | WS_EX_TOOLWINDOW)
    except Exception as e:
        logging.error(f"Error al intentar ocultar de la barra de tareas: {e}", exc_info=True)


def create_tray_icon(window):
    icon_path = os.path.join(IMG_DIR, "icono.ico")
    try: image = Image.open(icon_path)
    except Exception: return

    def on_quit(icon, item):
        stop_spotify_monitor.set()
        icon.stop()
        if window: window.destroy()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Mostrar", lambda: window.show(), default=True),
        pystray.MenuItem("Salir", on_quit)
    )
    tray_icon = pystray.Icon("ByteBuddy", image, "ByteBuddy", menu)
    tray_icon.run()

# --- STREAMING DE CHAT POR SOCKET.IO ---
@socketio.on('chat_request')
def socket_chat_request(data):
    try:
        user_message = (data or {}).get('message', '')
        allow_web_search = bool((data or {}).get('allow_web_search', False))
        sid = request.sid
        logging.info(f"[stream] Mensaje recibido: {user_message!r} (allow_web_search={allow_web_search})")
        socketio.start_background_task(target=_stream_chat_response, sid=sid, user_message=user_message, allow_web_search=allow_web_search)
    except Exception as e:
        logging.error(f"[stream] Error en chat_request: {e}", exc_info=True)
        socketio.emit('chat_error', {"error": str(e)})


def _stream_chat_response(sid: str, user_message: str, allow_web_search: bool):
    conversacion = leer_conversacion()
    conversacion.append({"role": "user", "content": user_message})


    try:
        socketio.emit('chat_start', {}, to=sid)
        base_kwargs = {
            "model": MODELO,
            "messages": conversacion,
            "temperature": TEMPERATURA,
            "stream": True,
            "response_format": {"type": "json_object"}
        }

        respuesta_chunks: list[str] = []
        buffer = ""
        respuesta_usuario_emitted_len = 0
        found_resp_start = False
        resp_start_idx = 0

        import re
        start_regex = re.compile(r'"respuesta_usuario"\s*:\s*"')

        def emit_from_buffer():
            nonlocal respuesta_usuario_emitted_len
            if not found_resp_start:
                return
            # Encontrar cierre de la cadena sin escapar
            i = resp_start_idx
            end = None
            escaped = False
            for j in range(i, len(buffer)):
                ch = buffer[j]
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    end = j
                    break
            # Si no encontramos cierre, usamos el final actual del buffer
            slice_end = end if end is not None else len(buffer)
            current_value = buffer[i:slice_end]
            safe_html = _to_safe_html(current_value)
            if len(safe_html) > respuesta_usuario_emitted_len:
                delta_html = safe_html[respuesta_usuario_emitted_len:]
                respuesta_usuario_emitted_len = len(safe_html)
                socketio.emit('chat_delta', {"delta": delta_html}, to=sid)

        def run_stream(with_tools: bool):
            kwargs = dict(base_kwargs)
            if with_tools:
                kwargs["tools"] = [{"type": "web_search"}]
                kwargs["tool_choice"] = "auto"
            stream = client.chat.completions.create(**kwargs)
            nonlocal found_resp_start, buffer, resp_start_idx
            for chunk in stream:
                try:
                    delta = getattr(chunk.choices[0].delta, 'content', None)
                except Exception:
                    delta = None
                if delta:
                    respuesta_chunks.append(delta)
                    buffer += delta
                    if not found_resp_start:
                        m = start_regex.search(buffer)
                        if m:
                            found_resp_start = True
                            resp_start_idx = m.end()
                    emit_from_buffer()

        tried_tools = False
        try:
            if allow_web_search:
                tried_tools = True
                run_stream(with_tools=True)
            else:
                run_stream(with_tools=False)
        except Exception as e:
            logging.warning(f"[stream] Falla en streaming (tools={allow_web_search}): {e}")
            # Reintento sin tools
            if tried_tools:
                try:
                    run_stream(with_tools=False)
                except Exception as e2:
                    logging.warning(f"[stream] Reintento sin tools también falló: {e2}")

        # Si no hubo chunks, intentamos un fallback sin streaming
        if not respuesta_chunks:
            raw_fallback = obtener_contenido_modelo(conversacion, allow_web_search=False)
            if raw_fallback:
                socketio.emit('chat_delta', {"delta": _to_safe_html(raw_fallback)}, to=sid)
                respuesta_chunks = [raw_fallback]

        # Parsear el JSON completo de lo recibido
        full_raw = "".join(respuesta_chunks)
        resp_json = _ensure_json_response(full_raw)
        respuesta_usuario = resp_json.get("respuesta_usuario", "")

        # Si el streaming parcial no mostró todo, asegurar que el final esté completo
        if respuesta_usuario and respuesta_usuario_emitted_len < len(respuesta_usuario):
            remaining = respuesta_usuario[respuesta_usuario_emitted_len:]
            socketio.emit('chat_delta', {"delta": remaining}, to=sid)
            respuesta_usuario_emitted_len = len(respuesta_usuario)

        # Procesar llamada a función si existe
        llamada = resp_json.get("llamada")
        final_text = respuesta_usuario
        if llamada:
            try:
                servicio = llamada.get("servicio")
                parametros = llamada.get("parametros", [])
                logging.info(f"[stream] El modelo solicitó función '{servicio}' con parámetros: {parametros}")
                func_res = hacer_llamada_funcion(servicio, parametros)
                if func_res.get("second_response"):
                    conversacion.append({"role": "system", "content": func_res["respuesta"]})
                    # Segunda respuesta (no streaming para simplificar)
                    second_raw = obtener_contenido_modelo(conversacion, allow_web_search=allow_web_search)
                    second_json = _ensure_json_response(second_raw)
                    second_text = second_json.get("respuesta_usuario", "")
                    if second_text:
                        socketio.emit('chat_delta', {"delta": second_text}, to=sid)
                        final_text += second_text
                else:
                    # Si no requiere segunda pasada, añadimos la respuesta directa
                    extra = func_res.get("respuesta", "")
                    if extra:
                        socketio.emit('chat_delta', {"delta": _to_safe_html(extra)}, to=sid)
                        final_text += _to_safe_html(extra)
            except Exception as e:
                logging.error(f"[stream] Error procesando llamada de función: {e}", exc_info=True)

        conversacion.append({"role": "assistant", "content": final_text})
        guardar_conversacion(conversacion)
        socketio.emit('chat_end', {"message": final_text}, to=sid)
    except Exception as e:
        logging.error("[stream] Error generando respuesta en streaming", exc_info=True)
        socketio.emit('chat_error', {"error": str(e)}, to=sid)

# --- ARRANQUE DE LA APLICACIÓN ---
def run_app():
    global spotify_monitor_thread
    spotify_monitor_thread = socketio.start_background_task(target=spotify_monitor)
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    if platform.system() == "Windows":
        myappid = u'mycompany.myproduct.subproduct.version'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    flask_thread = threading.Thread(target=run_app, daemon=True)
    flask_thread.start()
    time.sleep(1)

    api = API()
    width, height = 400, 600
    x, y = get_bottom_right_position(width, height)
    
    window_global = webview.create_window(
        title="ByteBuddy", url="http://127.0.0.1:5000",
        width=width, height=height, x=x, y=y,
        resizable=False, frameless=True, easy_drag=False,
        js_api=api, background_color="#121212", hidden=True
    )

    def on_loaded():
        hide_from_taskbar("ByteBuddy")
        threading.Thread(target=create_tray_icon, args=(window_global,), daemon=True).start()

    webview.start(on_loaded, debug=False)
