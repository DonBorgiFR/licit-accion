' =============================================================================
'  Despertador.vbs - Activar o desactivar la prospeccion nocturna (Capa 10, 10.C)
' =============================================================================
'
'  ESTE FICHERO NO TIENE LOGICA, igual que Incoop.vbs y por el mismo motivo: lo
'  que puede romperse vive en Python, donde la suite lo alcanza. Aqui solo se abre
'  la puerta a tools/despertador_ventana.py.
'
'  POR QUE UN SOLO ICONO Y NO DOS ("activar" y "desactivar"): dos accesos invitan a
'  equivocarse y ninguno contesta la pregunta que la persona tiene de verdad, que
'  es "esta activo?". La ventana empieza contestandola y ofrece el boton contrario
'  al estado actual.
'
'  POR QUE pythonw.exe: python.exe abriria una consola negra delante de la ventana,
'  y la decision A.1 de direccion es que el manual no mencione una terminal.
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
shell.Run "pythonw.exe -m tools.despertador_ventana", 0, False

If Err.Number <> 0 Then
    MsgBox "No se ha podido abrir la prospeccion nocturna porque falta Python." & vbCrLf & vbCrLf & _
           "Windows no encuentra pythonw.exe, de modo que no ha llegado a" & vbCrLf & _
           "ejecutarse y no ha podido avisar por si misma." & vbCrLf & vbCrLf & _
           "Como resolverlo: hacer doble clic en ""Preparar equipo"", en la carpeta" & vbCrLf & _
           "del proyecto, que explica que instalar y en que orden." & vbCrLf & vbCrLf & _
           "Detalle tecnico: " & Err.Description, _
           vbCritical, "Prospeccion nocturna - Incoop"
    WScript.Quit 10
End If
On Error Goto 0

WScript.Quit 0
