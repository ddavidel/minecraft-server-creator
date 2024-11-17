Set oShell = CreateObject ("Wscript.Shell") 
Dim strArgs
strArgs = "cmd /c activate.bat"
oShell.Run strArgs, 0, false