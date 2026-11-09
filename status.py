"""
Utilitário de verificação de status do ObjectWatcher.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / "data" / "objectwatcher.pid"
LOG_FILE = BASE_DIR / "logs" / "objectwatcher.log"


def is_pid_running(pid: int) -> bool:
    """Verifica de forma nativa e sem comandos externos se o PID está em execução."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        process_handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if process_handle:
            kernel32.CloseHandle(process_handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def get_running_pid():
    if PID_FILE.exists():
        try:
            content = PID_FILE.read_text(encoding="utf-8").strip()
            pid = int(content)
            if is_pid_running(pid):
                return pid
            else:
                # Processo não existe mais, limpa PID antigo
                PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    return None


def main():
    print("=" * 60)
    print("       ObjectWatcher - Status do Monitor em Segundo Plano")
    print("=" * 60)
    print()

    pid = get_running_pid()
    if pid:
        print(f"STATUS: [ONLINE] Rodando silenciosamente em segundo plano!")
        print(f"PID do Processo: {pid}")
    else:
        print("STATUS: [OFFLINE] O monitor nao esta rodando no momento.")

    print()
    print("-" * 60)
    print("Ultimos registros de log (logs/objectwatcher.log):")
    print("-" * 60)

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-12:]:
            print(line)
        if not lines:
            print("Arquivo de log vazio.")
    else:
        print("Nenhum arquivo de log gerado ainda.")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
