@echo off
cls
echo Iniciando o ObjectWatcher em segundo plano (modo 100%% silencioso)...
wscript.exe "%~dp0iniciar_segundo_plano.vbs"
ping 127.0.0.1 -n 3 > nul
echo.
py "%~dp0status.py"
echo.
echo Pressione qualquer tecla para fechar esta janela (o bot continuara rodando).
pause > nul
