import os
import getpass
from datetime import datetime, timedelta
import wmi
import pythoncom
from win32com.shell import shell
from win32com.shell import shellcon
import winreg
import codecs
import struct
from datetime import datetime

def obtener_info_usuario_actual():
    """
    Recupera información del usuario de Windows que tiene la sesión abierta,
    usando WMI y Win32 API para rutas de carpetas especiales.
    Devuelve un diccionario con campos similares a los de Win32_UserAccount,
    pero sin fallar si alguna propiedad no está presente.
    """
    # 1. Nombre de usuario actual
    usuario = getpass.getuser()  # equivale a os.getlogin() en la mayoría de casos

    # 2. Inicializar WMI (necesario para entornos multihilo)
    pythoncom.CoInitialize()
    c = wmi.WMI()

    # 3. Consultar Win32_UserAccount para ese usuario local
    try:
        usuarios = c.Win32_UserAccount(Name=usuario, LocalAccount=True)
    except Exception as e:
        pythoncom.CoUninitialize()
        raise RuntimeError(f"Error al consultar Win32_UserAccount: {e!s}")

    if not usuarios:
        pythoncom.CoUninitialize()
        raise RuntimeError(f"No se encontró la cuenta local '{usuario}' en Win32_UserAccount.")
    user_wmi = usuarios[0]

    # 4. Construir el diccionario con la información básica de WMI,
    #    usando getattr(..., None) o hasattr() para evitar AttributeError.
    info = {}

    info["Nombre"] = getattr(user_wmi, "Name", None)
    info["NombreCompleto"] = getattr(user_wmi, "FullName", None)
    info["Descripción"] = getattr(user_wmi, "Description", None)
    info["SID"] = getattr(user_wmi, "SID", None)

    # Si 'Disabled' o 'Lockout' no existe, asumimos "Desconocido" o false
    estado_disabled = getattr(user_wmi, "Disabled", None)
    if estado_disabled is not None:
        info["Estado"] = "Deshabilitado" if estado_disabled else "Habilitado"
    else:
        info["Estado"] = "Desconocido"

    bloqueado = getattr(user_wmi, "Lockout", None)
    if bloqueado is not None:
        info["Bloqueado"] = "Sí" if bloqueado else "No"
    else:
        info["Bloqueado"] = "Desconocido"

    # 'MaxInvalidPasswordAttempts' puede no existir en algunas configuraciones
    max_intentos = getattr(user_wmi, "MaxInvalidPasswordAttempts", None)
    info["MaxIntentosFallidos"] = max_intentos if max_intentos is not None else "No disponible"

    # 5. Conversiones de fecha/hora de WMI
    raw_creation = getattr(user_wmi, "CreationDate", None)
    if raw_creation:
        # Win32_DateTime viene en formato “yyyymmddHHMMSS.microsegundos+tz”
        raw_str = raw_creation.split('.')[0]
        try:
            info["FechaCreación"] = datetime.strptime(raw_str, "%Y%m%d%H%M%S")
        except Exception:
            info["FechaCreación"] = None
    else:
        info["FechaCreación"] = None

    #    PasswordAge está en segundos desde el último cambio de contraseña
    password_age = getattr(user_wmi, "PasswordAge", None)
    if password_age is not None:
        try:
            info["EdadContraseña"] = timedelta(seconds=int(password_age))
        except Exception:
            info["EdadContraseña"] = None
    else:
        info["EdadContraseña"] = None

    # 6. Obtener pertenencia a grupos locales
    try:
        filtro = (
            f'Win32_UserAccount.Domain="{os.environ["COMPUTERNAME"]}",'
            f'Name="{usuario}"'
        )
        miembros = c.Win32_GroupUser(AccountComponent=filtro)
    except Exception:
        miembros = []

    grupos = []
    for rel in miembros:
        # rel.GroupComponent tiene formato: Win32_Group.Domain="MI-PC",Name="Usuarios"
        comp = getattr(rel, "GroupComponent", "")
        if comp:
            partes = comp.split(",")
            if len(partes) >= 2:
                # El segundo elemento será algo como Name="Usuarios"
                nombre_grupo = partes[1].split("=")[1].strip('"')
                grupos.append(nombre_grupo)
    info["PertenenciaGrupos"] = grupos

    # 7. Rutas de carpetas estándar del perfil (usuario actual)
    info["RutaPerfil"] = os.environ.get("USERPROFILE", "")

    try:
        info["CarpetaDocumentos"] = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
    except Exception:
        info["CarpetaDocumentos"] = None

    try:
        info["CarpetaEscritorio"] = shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOP, None, 0)
    except Exception:
        info["CarpetaEscritorio"] = None

    try:
        info["CarpetaAppData"] = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, None, 0)
    except Exception:
        info["CarpetaAppData"] = None

    # 8. Limpiar COM al terminar
    pythoncom.CoUninitialize()

    return info



def listar_todas_las_entradas_UserAssist():
    clave_base = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
    todas = []

    try:
        ua_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave_base)
    except OSError as e:
        print(f"No se pudo abrir la clave UserAssist: {e}")
        return todas

    idx_guid = 0
    while True:
        try:
            guid = winreg.EnumKey(ua_key, idx_guid)
        except OSError:
            break
        ruta_count = clave_base + "\\" + guid + r"\Count"

        try:
            count_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta_count)
        except OSError:
            idx_guid += 1
            continue

        idx_val = 0
        while True:
            try:
                nombre_rot13, datos, _ = winreg.EnumValue(count_key, idx_val)
            except OSError:
                break

            try:
                nombre = codecs.decode(nombre_rot13, "rot_13")
            except Exception:
                nombre = None

            # Intentamos extraer fecha, aunque sea None
            if datos and len(datos) >= 16:
                raw_filetime = struct.unpack("<Q", datos[8:16])[0]
                try:
                    segundos_unix = (raw_filetime - 116444736000000000) / 10_000_000
                    fecha = datetime.fromtimestamp(segundos_unix)
                except Exception:
                    fecha = None
            else:
                fecha = None

            todas.append((guid, nombre_rot13, nombre, fecha))
            idx_val += 1

        winreg.CloseKey(count_key)
        idx_guid += 1

    winreg.CloseKey(ua_key)
    return todas

