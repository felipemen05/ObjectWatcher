"""
ObjectWatcher - Monitor Fiscal e Governamental para Sistemas ERP
Ponto de entrada principal (CLI) para execução local, contínua, via Cron ou GitHub Actions.
"""

import os
import sys
import argparse
import logging
from src.config import settings
from src.watcher import ObjectWatcher
from src.discord_notifier import DiscordNotifier
from src.database import DatabaseManager


def setup_logging(verbose: bool = False):
    """Configura o formato de logs do sistema tanto no terminal quanto em arquivo."""
    from pathlib import Path
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "objectwatcher.log"

    level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8")
    ]

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers
    )


def main():
    parser = argparse.ArgumentParser(
        description="ObjectWatcher - Monitor Fiscal Inteligente para ERP da ObjectData",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Executa uma única rodada de monitoramento e encerra (ideal para Cron e GitHub Actions)."
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Executa continuamente em segundo plano com checagens periódicas."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.check_interval_minutes,
        help="Intervalo de checagem em minutos para o modo loop (padrão: 60)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo de simulação: executa scrapers e IA sem enviar ao Discord ou salvar no banco."
    )
    parser.add_argument(
        "--test-discord",
        action="store_true",
        help="Envia uma mensagem de teste rica para validar o Webhook do Discord."
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Exibe estatísticas de itens já capturados e salvos no banco SQLite."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Habilita logs detalhados de depuração (DEBUG)."
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    # 1. Comando de Teste do Discord
    if args.test_discord:
        print("\n[ObjectWatcher] Testando conectividade com o Discord Webhook...")
        notifier = DiscordNotifier()
        success = notifier.send_test_message()
        if success:
            print("[ObjectWatcher] Sucesso! Verifique o canal no Discord.\n")
            sys.exit(0)
        else:
            print("[ObjectWatcher] Erro: Falha ao enviar mensagem de teste. Verifique sua DISCORD_WEBHOOK_URL.\n")
            sys.exit(1)

    # 2. Comando de Estatísticas
    if args.stats:
        db = DatabaseManager()
        stats = db.get_stats()
        print("\n==================================================")
        print("📊 Estatísticas do ObjectWatcher")
        print("==================================================")
        print(f"Total de publicações processadas: {stats['total_items']}")
        print("\nPor Fonte:")
        for src, count in stats["by_source"].items():
            print(f"  • {src}: {count}")
        print("\nPor Nível de Urgência:")
        for lvl, count in stats["by_impact"].items():
            print(f"  • {lvl}: {count}")
        print("==================================================\n")
        sys.exit(0)

    # 3. Execução do Monitor
    watcher = ObjectWatcher()

    pid_file = settings.database_path.parent / "objectwatcher.pid"

    if args.loop:
        try:
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
            watcher.run_loop(interval_minutes=args.interval, dry_run=args.dry_run)
        finally:
            if pid_file.exists():
                try:
                    pid_file.unlink()
                except Exception:
                    pass
    else:
        # Padrão ou --run-once: executa um ciclo
        result = watcher.run_check(dry_run=args.dry_run)
        print(f"\n[Resultado] Verificados: {result['total_scraped']} | Novos: {result['total_new']} | Notificados: {result['total_notified']}\n")


if __name__ == "__main__":
    main()

