"""
Módulo de Configuração do ObjectWatcher.
Carrega parâmetros de .env, variáveis de ambiente do SO e config.yaml.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env caso exista
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    def __init__(self, config_file: str = "config.yaml"):
        self.config_path = BASE_DIR / config_file
        self.raw_config: Dict[str, Any] = {}
        
        # Carrega YAML se existir, senão usa config.yaml.example ou defaults
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.raw_config = yaml.safe_load(f) or {}
        else:
            example_path = BASE_DIR / "config.yaml.example"
            if example_path.exists():
                with open(example_path, "r", encoding="utf-8") as f:
                    self.raw_config = yaml.safe_load(f) or {}

        # Assegura que o diretório de dados existe
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------------------
    # Discord
    # --------------------------------------------------------------------------
    @property
    def discord_webhook_url(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_URL") or self.raw_config.get("discord", {}).get("webhook_url", "")

    @property
    def discord_bot_token(self) -> str:
        return os.getenv("DISCORD_BOT_TOKEN") or self.raw_config.get("discord", {}).get("bot_token", "")

    @property
    def discord_channel_id(self) -> str:
        # 1. Variável de ambiente (prioridade mais alta)
        env_val = os.getenv("DISCORD_CHANNEL_ID")
        if env_val and env_val.strip():
            return env_val.strip()

        # 2. Arquivo config.yaml
        cfg_val = self.raw_config.get("discord", {}).get("channel_id", "")
        if cfg_val and str(cfg_val).strip():
            return str(cfg_val).strip()

        # 3. Configuração dinâmica salva no banco de dados SQLite
        try:
            import sqlite3
            if self.database_path.exists():
                with sqlite3.connect(str(self.database_path)) as conn:
                    cur = conn.execute("SELECT value FROM app_settings WHERE key = 'target_channel_id'")
                    row = cur.fetchone()
                    if row and row[0]:
                        return str(row[0]).strip()
        except Exception:
            pass

        return ""

    @property
    def discord_bot_name(self) -> str:
        return os.getenv("DISCORD_BOT_NAME") or self.raw_config.get("bot", {}).get("name", "ObjectWatcher")

    @property
    def discord_avatar_url(self) -> str:
        return os.getenv("DISCORD_AVATAR_URL") or self.raw_config.get("bot", {}).get(
            "avatar_url", 
            "https://raw.githubusercontent.com/objectdata/objectwatcher/main/Foto_perfil.jpg"
        )

    @property
    def attach_files_to_discord(self) -> bool:
        env_val = os.getenv("ATTACH_FILES_TO_DISCORD")
        if env_val is not None:
            return env_val.lower() in ("1", "true", "yes", "sim")
        return bool(self.raw_config.get("discord", {}).get("attach_files", True))

    @property
    def max_attachment_size_mb(self) -> int:
        env_val = os.getenv("MAX_ATTACHMENT_SIZE_MB")
        if env_val:
            return int(env_val)
        return int(self.raw_config.get("discord", {}).get("max_attachment_size_mb", 25))

    @property
    def save_local_archive(self) -> bool:
        env_val = os.getenv("SAVE_LOCAL_ARCHIVE")
        if env_val is not None:
            return env_val.lower() in ("1", "true", "yes", "sim")
        return bool(self.raw_config.get("storage", {}).get("save_local_archive", True))

    @property
    def archive_dir(self) -> Path:
        raw = os.getenv("ARCHIVE_DIR") or self.raw_config.get("storage", {}).get("archive_dir", "downloads")
        path = BASE_DIR / raw
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def color_urgent(self) -> int:
        return self.raw_config.get("bot", {}).get("colors", {}).get("urgent", 0xE74C3C)

    @property
    def color_attention(self) -> int:
        return self.raw_config.get("bot", {}).get("colors", {}).get("attention", 0xE67E22)

    @property
    def color_info(self) -> int:
        return self.raw_config.get("bot", {}).get("colors", {}).get("info", 0x3498DB)

    @property
    def rate_limit_delay(self) -> float:
        return float(self.raw_config.get("discord", {}).get("rate_limit_delay_seconds", 1.5))

    # --------------------------------------------------------------------------
    # Inteligência Artificial (Gemini)
    # --------------------------------------------------------------------------
    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY") or self.raw_config.get("ai", {}).get("api_key", "")

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL") or self.raw_config.get("ai", {}).get("model", "gemini-3.8-flash")

    @property
    def ai_timeout(self) -> int:
        return int(self.raw_config.get("ai", {}).get("timeout_seconds", 30))

    # --------------------------------------------------------------------------
    # Banco de Dados & Agendamento
    # --------------------------------------------------------------------------
    @property
    def database_path(self) -> Path:
        raw_path = os.getenv("DATABASE_PATH") or self.raw_config.get("database", {}).get("path", "data/objectwatcher.db")
        return BASE_DIR / raw_path

    @property
    def check_interval_minutes(self) -> int:
        val = os.getenv("CHECK_INTERVAL_MINUTES") or self.raw_config.get("scheduler", {}).get("interval_minutes", 60)
        return int(val)

    # --------------------------------------------------------------------------
    # Fontes e Palavras-chave
    # --------------------------------------------------------------------------
    @property
    def sources_config(self) -> Dict[str, Any]:
        return self.raw_config.get("sources", {})

    @property
    def relevance_keywords(self) -> List[str]:
        return self.raw_config.get("relevance_keywords", [
            "nota técnica", "nt 20", "schema", "xsd", "layout", "leiaute",
            "nfe", "nf-e", "nfce", "nfc-e", "nfse", "nfs-e",
            "simples nacional", "mei", "cgsn", "rejeicao", "rejeição",
            "pis", "cofins", "ipi", "ibs", "cbs", "reforma tributária",
            "sped", "efd", "ecf", "ecd", "ncm", "cst", "csosn"
        ])


# Instância global reutilizável
settings = Config()
