Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Obtém o diretório onde este script está localizado
strScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Executa pyw.exe de forma 100% invisível (janela oculta = 0)
strCommand = "pyw.exe """ & strScriptDir & "\main.py"" --loop --interval 60"
WshShell.Run strCommand, 0, False

