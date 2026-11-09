@echo off
chcp 65001 > nul
cls
echo Removendo tarefa agendada do ObjectWatcher...
schtasks /delete /tn "ObjectWatcher_Fiscal_Monitor" /f
echo.
echo Concluído.
pause

