@echo off
chcp 65001 > nul
cls
echo ==============================================================
echo    ObjectWatcher - Agendador Nativo do Windows (A cada 1h)
echo ==============================================================
echo.
echo Esta opção cadastra o monitor no Agendador de Tarefas do Windows.
echo Vantagens:
echo   - 0%% de uso de memória RAM enquanto aguarda.
echo   - Executa 100%% em segundo plano sem nenhuma janela preta.
echo   - Inicia sozinho sempre que você ligar o computador.
echo.

set TASK_NAME=ObjectWatcher_Fiscal_Monitor
set PYTHON_PATH=pyw.exe
set SCRIPT_PATH=%~dp0main.py

echo Criando tarefa agendada '%TASK_NAME%'...
schtasks /create /tn "%TASK_NAME%" /tr "%PYTHON_PATH% \"%SCRIPT_PATH%\" --run-once" /sc HOURLY /mo 1 /f

echo.
if %errorlevel% equ 0 (
    echo [SUCESSO] Tarefa criada com sucesso no Windows!
    echo O bot será executado a cada 1 hora de forma 100%% silenciosa.
    echo.
    echo Para remover a tarefa no futuro, execute:
    echo   schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo [AVISO] Se ocorreu erro de permissão, clique com botão direito neste
    echo arquivo e selecione "Executar como Administrador".
)
echo.
pause

