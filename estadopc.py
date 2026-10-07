import os
import psutil
import GPUtil
import platform
import datetime
import subprocess
import ctypes
import webbrowser
from typing import List, Dict
from pathlib import Path
from PIL import ImageGrab

def obtener_informe_sistema() -> str:
    """
    Recopila información del sistema (CPU, GPU, memoria, discos, temperaturas, carga, etc.)
    y devuelve un informe detallado como un string formateado.
    """
    html = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html.append(f"<h2 style='color:#bb86fc;'>🖥️ INFORME DEL SISTEMA <span style='font-size:0.8em;color:#a0a0a0;'>({now})</span></h2>")
    html.append("<hr>")
    html.append(f"<b>Sistema operativo:</b> {platform.system()} {platform.release()} <span style='color:#a0a0a0;'>({platform.version()})</span><br>")
    html.append(f"<b>Arquitectura:</b> {platform.machine()} / <b>Procesador:</b> {platform.processor()}<br>")
    html.append("<br>")

    # ------- Información de CPU -------
    html.append("<h3 style='color:#03dac6;'>⚙️ CPU</h3>")
    try:
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        cpu_freq = psutil.cpu_freq()
        cpu_percent = psutil.cpu_percent(interval=0.2, percpu=False)
        load1, load5, load15 = psutil.getloadavg()
        html.append(f"<ul><li><b>Núcleos físicos:</b> {cpu_count_physical}, <b>lógicos:</b> {cpu_count_logical}</li>")
        if cpu_freq:
            html.append(f"<li><b>Frecuencia actual:</b> {cpu_freq.current:.2f} MHz <span style='color:#a0a0a0;'>(min: {cpu_freq.min:.2f} MHz, max: {cpu_freq.max:.2f} MHz)</span></li>")
        color_cpu = 'red' if cpu_percent > 80 else 'limegreen'
        html.append(f"<li><b>Uso total de CPU:</b> <span style='color:{color_cpu};'>{cpu_percent}%</span></li>")
        html.append(f"<li><b>Carga media:</b> 1m={load1:.2f}, 5m={load5:.2f}, 15m={load15:.2f}</li></ul>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener información de CPU: {e}</span><br>")

    # ------- Información de Memoria RAM -------
    html.append("<h3 style='color:#bb86fc;'>🧠 MEMORIA RAM</h3>")
    try:
        vm = psutil.virtual_memory()
        color_ram = 'red' if vm.percent > 80 else 'limegreen'
        html.append(f"<ul><li><b>Total:</b> {vm.total / (1024**3):.2f} GB</li>")
        html.append(f"<li><b>Disponible:</b> {vm.available / (1024**3):.2f} GB <span style='color:#a0a0a0;'>({vm.available * 100 / vm.total:.1f}%)</span></li>")
        html.append(f"<li><b>Usada:</b> <span style='color:{color_ram};'>{vm.used / (1024**3):.2f} GB ({vm.percent}%)</span></li>")
        swap = psutil.swap_memory()
        html.append(f"<li><b>Swap total:</b> {swap.total / (1024**3):.2f} GB</li>")
        html.append(f"<li><b>Swap usado:</b> {swap.used / (1024**3):.2f} GB ({swap.percent}%)</li></ul>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener información de memoria: {e}</span><br>")

    # ------- Información de Discos -------
    html.append("<h3 style='color:#03dac6;'>💾 DISCOS</h3>")
    try:
        partitions = psutil.disk_partitions(all=False)
        total_disks = 0
        used_disks = 0
        html.append("<table style='width:100%;border-collapse:collapse;'>"
                    "<tr style='background:#222;'><th>Montaje</th><th>Dispositivo</th><th>Tipo</th><th>Total</th><th>Usado</th><th>Libre</th></tr>")
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_disks += usage.total
                used_disks += usage.used
                color_disk = 'red' if usage.percent > 85 else 'limegreen'
                html.append(f"<tr><td>{part.mountpoint}</td><td>{part.device}</td><td>{part.fstype}</td>"
                            f"<td>{usage.total / (1024**3):.2f} GB</td>"
                            f"<td style='color:{color_disk};'>{usage.used / (1024**3):.2f} GB ({usage.percent}%)</td>"
                            f"<td>{usage.free / (1024**3):.2f} GB</td></tr>")
            except PermissionError:
                html.append(f"<tr><td colspan='6' style='color:red;'>Acceso denegado a {part.mountpoint}</td></tr>")
        html.append("</table>")
        if total_disks > 0:
            html.append(f"<b>→ Espacio total:</b> {total_disks / (1024**3):.2f} GB | <b>Usado:</b> {used_disks / (1024**3):.2f} GB ({used_disks * 100 / total_disks:.1f}%)<br>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener información de discos: {e}</span><br>")

    # ------- Información de Temperaturas -------
    html.append("<h3 style='color:#bb86fc;'>🌡️ TEMPERATURAS</h3>")
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
        if not temps:
            html.append("<span style='color:#a0a0a0;'>Ninguna sonda de temperatura detectada o no soportada en este sistema.</span><br>")
        else:
            html.append("<ul>")
            for sensor_name, entries in temps.items():
                html.append(f"<li><b>Sensor:</b> {sensor_name}<ul>")
                for entry in entries:
                    current = f"{entry.current:.1f}°C" if entry.current is not None else "N/A"
                    high = f"{entry.high:.1f}°C" if entry.high is not None else "N/A"
                    critical = f"{entry.critical:.1f}°C" if entry.critical is not None else "N/A"
                    label = entry.label or "—"
                    color_temp = 'red' if entry.current and entry.high and entry.current >= entry.high else 'limegreen'
                    html.append(f"<li>{label}: <span style='color:{color_temp};'>actual={current}</span>, alerta={high}, crítica={critical}</li>")
                html.append("</ul></li>")
            html.append("</ul>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener lecturas de temperatura: {e}</span><br>")

    # ------- Información de GPU -------
    html.append("<h3 style='color:#03dac6;'>🖲️ GPU(s)</h3>")
    try:
        gpus = GPUtil.getGPUs()
        if not gpus:
            html.append("<span style='color:#a0a0a0;'>No se han detectado GPUs compatibles o no se pudo acceder a la información.</span><br>")
        else:
            html.append("<ul>")
            for gpu in gpus:
                color_gpu = 'red' if gpu.load * 100 > 80 else 'limegreen'
                html.append(f"<li><b>GPU id {gpu.id} — {gpu.name}</b><ul>")
                html.append(f"<li>Carga GPU: <span style='color:{color_gpu};'>{gpu.load * 100:.1f}%</span></li>")
                html.append(f"<li>Memoria total: {gpu.memoryTotal} MB</li>")
                html.append(f"<li>Memoria usada: {gpu.memoryUsed} MB ({gpu.memoryUtil * 100:.1f}%)</li>")
                html.append(f"<li>Temperatura: {gpu.temperature} °C</li>")
                html.append(f"<li>Velocidad ventilador (fan): {gpu.fanSpeed} %</li>")
                html.append("</ul></li>")
            html.append("</ul>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener información de GPU: {e}</span><br>")

    # ------- Información de Procesos Top -------
    html.append("<h3 style='color:#bb86fc;'>🔝 PROCESOS TOP</h3>")
    try:
        procesos = [(p.pid, p.info['name'], p.info['cpu_percent'], p.info['memory_percent']) 
                    for p in psutil.process_iter(['name', 'cpu_percent', 'memory_percent'])]
        top_cpu = sorted(procesos, key=lambda x: x[2], reverse=True)[:5]
        top_mem = sorted(procesos, key=lambda x: x[3], reverse=True)[:5]
        html.append("<b>▶ Top 5 procesos por CPU:</b><ul>")
        for pid, name, cpu_pct, mem_pct in top_cpu:
            color_proc = 'red' if cpu_pct > 80 else 'limegreen'
            html.append(f"<li>PID {pid} — {name}: <span style='color:{color_proc};'>CPU={cpu_pct:.1f}%</span>, Memoria={mem_pct:.1f}%</li>")
        html.append("</ul>")
        html.append("<b>▶ Top 5 procesos por Memoria:</b><ul>")
        for pid, name, cpu_pct, mem_pct in top_mem:
            color_memproc = 'red' if mem_pct > 80 else 'limegreen'
            html.append(f"<li>PID {pid} — {name}: <span style='color:{color_memproc};'>Memoria={mem_pct:.1f}%</span>, CPU={cpu_pct:.1f}%</li>")
        html.append("</ul>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener información de procesos: {e}</span><br>")

    # ------- Uptime y otros datos -------
    html.append("<h3 style='color:#03dac6;'>⏱️ UPTIME Y RED</h3>")
    try:
        uptime_segundos = datetime.datetime.now().timestamp() - psutil.boot_time()
        uptime_str = str(datetime.timedelta(seconds=int(uptime_segundos)))
        html.append(f"<b>Tiempo desde último arranque:</b> {uptime_str} (días, hh:mm:ss)<br>")
        net_io = psutil.net_io_counters()
        html.append(f"<b>Tráfico de red total:</b> Enviado={net_io.bytes_sent / (1024**2):.2f} MB, Recibido={net_io.bytes_recv / (1024**2):.2f} MB<br>")
        # IP local
        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            html.append(f"<b>IP local:</b> {local_ip}<br>")
        except Exception:
            html.append("<span style='color:#a0a0a0;'>No se pudo obtener IP local.</span><br>")
        # IP pública
        try:
            import urllib.request
            public_ip = urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
            html.append(f"<b>IP pública:</b> {public_ip}<br>")
        except Exception:
            html.append("<span style='color:#a0a0a0;'>No se pudo obtener IP pública.</span><br>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener uptime/red: {e}</span><br>")

    # ------- Información de batería (si existe) -------
    html.append("<h3 style='color:#bb86fc;'>🔋 BATERÍA</h3>")
    try:
        battery = psutil.sensors_battery()
        if battery:
            color_bat = 'red' if battery.percent < 20 else 'limegreen'
            html.append(f"<b>Nivel batería:</b> <span style='color:{color_bat};'>{battery.percent}%</span> <b>Estado:</b> {'Cargando' if battery.power_plugged else 'Descargando'}<br>")
            html.append(f"<b>Tiempo restante:</b> {str(datetime.timedelta(seconds=battery.secsleft)) if battery.secsleft != psutil.POWER_TIME_UNLIMITED else 'Ilimitado'}<br>")
        else:
            html.append("<span style='color:#a0a0a0;'>No se detectó batería.</span><br>")
    except Exception as e:
        html.append(f"<span style='color:red;'>No se pudo obtener información de batería: {e}</span><br>")

    # ------- Reporte final -------
    informe = "".join(html)
    return informe


def obtener_resumen_procesos(limit: int = 5) -> Dict[str, List[Dict[str, float]]]:
    """Devuelve los procesos más exigentes en CPU y memoria."""
    try:
        limit = int(limit)
    except Exception:
        limit = 5
    if limit <= 0:
        limit = 5

    procesos = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        procesos.append(info)

    def limpiar(entries: List[Dict[str, float]]) -> List[Dict[str, float]]:
        resultado = []
        for entry in entries:
            resultado.append({
                "pid": entry.get('pid'),
                "nombre": entry.get('name') or 'Desconocido',
                "cpu": round(float(entry.get('cpu_percent') or 0.0), 1),
                "memoria": round(float(entry.get('memory_percent') or 0.0), 1),
            })
        return resultado

    top_cpu = sorted(procesos, key=lambda x: x.get('cpu_percent') or 0.0, reverse=True)[:limit]
    top_mem = sorted(procesos, key=lambda x: x.get('memory_percent') or 0.0, reverse=True)[:limit]

    return {
        "top_cpu": limpiar(top_cpu),
        "top_memoria": limpiar(top_mem),
    }


def guardar_captura_pantalla(destino: str) -> str:
    """Captura la pantalla completa y guarda la imagen en la ruta indicada."""
    try:
        imagen = ImageGrab.grab()
    except Exception as exc:
        raise RuntimeError("No se pudo capturar la pantalla.") from exc

    destino_path = Path(destino)
    destino_path.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(destino_path, format='PNG')
    return str(destino_path)


def bloquear_equipo() -> None:
    """Bloquea la sesión de Windows."""
    if platform.system().lower() != "windows":
        raise RuntimeError("El bloqueo remoto solo está disponible en Windows.")
    try:
        ctypes.windll.user32.LockWorkStation()
    except Exception as exc:
        raise RuntimeError("No se pudo bloquear el equipo.") from exc


def abrir_url(url: str) -> str:
    """Abre una URL en el navegador predeterminado."""
    if not url:
        raise ValueError("No se proporcionó una URL válida.")
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    abierto = webbrowser.open(url)
    if not abierto:
        raise RuntimeError("No se pudo abrir la URL solicitada.")
    return url


def abrir_ruta(path: str) -> str:
    """Abre un archivo o carpeta usando el explorador de Windows."""
    if not path:
        raise ValueError("No se especificó ninguna ruta.")
    ruta = os.path.expandvars(os.path.expanduser(path)).strip('"')
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"La ruta '{ruta}' no existe.")
    os.startfile(ruta)
    return ruta


def gestionar_aplicacion(nombre, accion):
    """
    Inicia o para una aplicación por su nombre.
    nombre: nombre del ejecutable (ej: 'notepad.exe')
    accion: 'iniciar' o 'parar'
    """
    nombre = nombre.lower()
    if accion == 'iniciar':
        try:
            subprocess.Popen(nombre)
            return f"Aplicación '{nombre}' iniciada correctamente."
        except Exception as e:
            return f"Error al iniciar '{nombre}': {e}"
    elif accion == 'cerrar':
        encontrados = []
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == nombre:
                    proc.terminate()
                    encontrados.append(proc.pid)
            except Exception:
                pass
        if encontrados:
            return f"Aplicación '{nombre}' detenida (PID: {', '.join(map(str, encontrados))})."
        else:
            return f"No se encontró ninguna instancia de '{nombre}' en ejecución."
    else:
        return "Acción no reconocida. Usa 'iniciar' o 'parar'."
