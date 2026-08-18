' =============================================================================
'  Incoop.vbs - La puerta del doble clic (Ecosistema de Licitaciones, Capa 10)
' =============================================================================
'
'  ESTE FICHERO NO TIENE LOGICA, Y ESO ES EL DISENO, NO UN DESCUIDO.
'
'  VBScript no se puede probar con la suite de pytest, asi que todo lo que pueda
'  romperse vive en Python (src/lanzador.py) y aqui solo queda abrir la puerta:
'  invocar el orquestador con la ventana oculta. Cuantas menos decisiones se tomen
'  en este fichero, menos codigo hay sin red de seguridad.
'
'  POR QUE pythonw.exe Y NO python.exe: python.exe abre una consola negra que se
'  queda ahi toda la sesion. pythonw.exe no tiene consola. La ventana oculta del
'  Run() de abajo (el 0) tapa la consola, pero pythonw evita crearla siquiera.
'
'  POR QUE NO SE ESPERA AL PROCESO (el False del Run): el lanzador vive mientras
'  la persona tenga el Cockpit abierto, que pueden ser horas. Esperarlo dejaria un
'  wscript.exe colgado todo ese rato sin ninguna utilidad: el codigo de salida solo
'  le importa al Programador de tareas, y el Programador NO invoca este fichero.
'
'  IMPORTANTE PARA EL PASO 8: la tarea programada llama a Python directamente,
'  nunca a este .vbs. El MsgBox de abajo colgaria para siempre en la Session 0,
'  que es exactamente el fallo que la invariante central existe para impedir. Aqui
'  se admite un unico dialogo porque este fichero solo se ejecuta por doble clic,
'  y porque cubre el unico fallo del que Python no puede avisar: no haber podido
'  arrancar Python.
'
'  SIN ACENTOS A PROPOSITO: un .vbs guardado en UTF-8 sin BOM muestra los acentos
'  rotos en el MsgBox, y con BOM algunos motores de Windows se atragantan. Escribir
'  en ASCII puro es la unica forma de que el aviso se lea bien en cualquier equipo.
'
'  El directorio de trabajo se fija a la carpeta de este fichero porque "python -m"
'  resuelve el paquete desde el directorio actual. Todo lo demas se ancla solo a la
'  raiz del proyecto (leccion de H-18): un acceso directo no arranca donde uno cree.

Option Explicit

Dim shell, fso, raiz, modo, orden

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

raiz = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = raiz

' Sin argumento, doble clic = modo completo: servidor, Cockpit y prospeccion.
' Con argumento, el acceso directo secundario pide "cockpit" (abrir sin prospectar).
If WScript.Arguments.Count > 0 Then
    modo = WScript.Arguments(0)
Else
    modo = "completo"
End If

orden = "pythonw.exe -m src.lanzador --modo " & modo

On Error Resume Next
shell.Run orden, 0, False

If Err.Number <> 0 Then
    MsgBox "No se ha podido arrancar el Ecosistema de Licitaciones." & vbCrLf & vbCrLf & _
           "Windows no encuentra pythonw.exe, de modo que el sistema no ha llegado" & vbCrLf & _
           "a ejecutarse y no ha podido avisar por si mismo." & vbCrLf & vbCrLf & _
           "Como resolverlo: instalar Python 3.12 marcando la casilla" & vbCrLf & _
           """Add python.exe to PATH"" durante la instalacion." & vbCrLf & vbCrLf & _
           "Detalle tecnico: " & Err.Description, _
           vbCritical, "Ecosistema de Licitaciones"
    WScript.Quit 10
End If
On Error Goto 0

WScript.Quit 0
