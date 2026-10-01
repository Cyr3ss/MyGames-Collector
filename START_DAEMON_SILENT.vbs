' Auto Collect MyGames - Invisible Background Daemon Launcher
' Launches START_DAEMON.bat without opening any command prompt or terminal window.
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "START_DAEMON.bat", 0, False
Set WshShell = Nothing
