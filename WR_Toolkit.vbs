Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

If fso.FileExists(strPath & "\.venv\Scripts\pythonw.exe") Then
    WshShell.Run Chr(34) & strPath & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & strPath & "\app.py" & Chr(34), 0, False
Else
    WshShell.Run "pythonw " & Chr(34) & strPath & "\app.py" & Chr(34), 0, False
End If
