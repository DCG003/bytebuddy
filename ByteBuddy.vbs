' launch.vbs
Option Explicit
Dim WshShell, fso, carpeta, python, script, cmd
Set WshShell = CreateObject("WScript.Shell")

' Directorio de trabajo: la carpeta de este script
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = carpeta

python = carpeta & "\.venv\Scripts\python.exe"  ' NO pythonw.exe
script = carpeta & "\main.py"

' -u = sin buffer para que los logs se escriban al instante
cmd = """" & python & """" & " -u " & """" & script & """"

' 0 = oculto, False = no esperar a que termine
WshShell.Run cmd, 0, False


