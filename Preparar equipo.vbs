' =============================================================================
'  Preparar equipo.vbs - Dejar un PC listo sin escribir un comando (Capa 10, 10.C)
' =============================================================================
'
'  ESTE FICHERO NO TIENE LOGICA, IGUAL QUE Incoop.vbs, Y POR EL MISMO MOTIVO.
'
'  VBScript no se puede probar con la suite de pytest, asi que todo lo que pueda
'  romperse vive en Python: los pasos en tools/preparar_equipo.py y la ventana en
'  tools/preparar_equipo_ventana.py. Aqui solo se abre la puerta.
'
'  POR QUE ESTE FICHERO ESTA EN LA CARPETA DEL PROYECTO Y NO EN EL ESCRITORIO:
'  preparar un equipo se hace ANTES de que existan los accesos directos - de hecho
'  es quien los crea -, asi que en un PC recien copiado no habria ningun icono al
'  que ir. Aqui siempre esta, junto a la carpeta que la persona acaba de copiar.
'
'  POR QUE pythonw.exe: python.exe abriria una consola negra delante de la ventana,
'  y la decision A.1 de direccion es que el manual no mencione una terminal.
'
'  POR QUE NO SE ESPERA AL PROCESO (el False del Run): la ventana de la preparacion
'  vive lo que dure - varios minutos la primera vez -, y esperarla dejaria un
'  wscript.exe colgado todo ese rato sin ninguna utilidad. Nadie recoge este codigo
'  de salida: quien informa es la ventana.
'
'  SIN ACENTOS A PROPOSITO: un .vbs en UTF-8 sin BOM muestra los acentos rotos en el
'  MsgBox, y con BOM algunos motores de Windows se atragantan.

Option Explicit

Dim shell, fso, raiz

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

raiz = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = raiz

On Error Resume Next
shell.Run "pythonw.exe -m tools.preparar_equipo_ventana", 0, False

If Err.Number <> 0 Then
    MsgBox "No se ha podido preparar el equipo porque falta Python." & vbCrLf & vbCrLf & _
           "Windows no encuentra pythonw.exe, de modo que la preparacion no ha" & vbCrLf & _
           "llegado a ejecutarse y no ha podido avisar por si misma." & vbCrLf & vbCrLf & _
           "Como resolverlo: instalar Python 3.12 desde python.org dejando" & vbCrLf & _
           "marcadas las dos casillas que vienen puestas por defecto," & vbCrLf & _
           """Add python.exe to PATH"" y ""tcl/tk and IDLE""." & vbCrLf & vbCrLf & _
           "Despues, volver a hacer doble clic en este mismo fichero." & vbCrLf & vbCrLf & _
           "Detalle tecnico: " & Err.Description, _
           vbCritical, "Preparar este equipo - Incoop"
    WScript.Quit 10
End If
On Error Goto 0

WScript.Quit 0
