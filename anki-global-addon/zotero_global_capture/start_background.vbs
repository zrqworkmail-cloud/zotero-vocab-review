Set shell = CreateObject("WScript.Shell")
If WScript.Arguments.Count = 1 Then
    shell.Environment("PROCESS")("ZVR_BACKGROUND_REVIEW") = "1"
    shell.Run Chr(34) & WScript.Arguments(0) & Chr(34), 7, False
End If
