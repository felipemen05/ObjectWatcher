"""
Utilitário para encerrar instâncias em segundo plano do ObjectWatcher.
"""

import os
import subprocess
from status import get_running_pid, PID_FILE


def main():
    print("=" * 60)
    print("       ObjectWatcher - Encerrar Monitor em Segundo Plano")
    print("=" * 60)
    print()

    pid = get_running_pid()
    if not pid:
        print("[INFO] Nenhuma instancia do ObjectWatcher em segundo plano esta ativa.")
        return

    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True, capture_output=True)
        print(f"[OK] Processo PID {pid} encerrado com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao encerrar PID {pid}: {e}")
    finally:
        PID_FILE.unlink(missing_ok=True)

    print()
    print("[CONCLUIDO] ObjectWatcher finalizado.")


if __name__ == "__main__":
    main()
