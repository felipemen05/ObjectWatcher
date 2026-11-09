"""
Módulo de Persistência e Deduplicação via SQLite.
Garante que nenhuma notícia, nota técnica ou comunicado fiscal seja postado mais de uma vez.
"""

import sqlite3
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from src.config import settings


class DatabaseManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.database_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Cria as tabelas necessárias se não existirem."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitored_items (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    impact_level TEXT,
                    summary TEXT,
                    erp_impact TEXT,
                    sent_to_discord INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_monitored_items_source 
                ON monitored_items (source)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    @staticmethod
    def generate_id(source: str, unique_key: str) -> str:
        """Gera um hash único SHA-256 combinando a fonte e a chave única (URL ou código)."""
        normalized = f"{source.strip().lower()}::{unique_key.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def is_processed(self, item_id: str) -> bool:
        """Verifica se um item já foi processado e salvo no banco."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT 1 FROM monitored_items WHERE id = ?", (item_id,))
            return cur.fetchone() is not None

    def save_item(
        self,
        item_id: str,
        source: str,
        title: str,
        url: str,
        published_at: Optional[str] = None,
        impact_level: Optional[str] = "INFORMATIVO",
        summary: Optional[str] = None,
        erp_impact: Optional[str] = None,
        sent_to_discord: bool = True
    ) -> None:
        """Salva um item processado no banco de dados."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO monitored_items 
                (id, source, title, url, published_at, impact_level, summary, erp_impact, sent_to_discord)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                source,
                title,
                url,
                published_at,
                impact_level,
                summary,
                erp_impact,
                1 if sent_to_discord else 0
            ))
            conn.commit()

    def get_recent_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna os itens mais recentemente salvos."""
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT id, source, title, url, published_at, created_at, impact_level, sent_to_discord
                FROM monitored_items
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Obtém uma configuração dinâmica salva no banco de dados."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Salva ou atualiza uma configuração dinâmica no banco de dados."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, str(value)))
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de monitoramento."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM monitored_items").fetchone()[0]
            by_source = dict(conn.execute("""
                SELECT source, COUNT(*) FROM monitored_items GROUP BY source
            """).fetchall())
            by_impact = dict(conn.execute("""
                SELECT impact_level, COUNT(*) FROM monitored_items GROUP BY impact_level
            """).fetchall())
            return {
                "total_items": total,
                "by_source": by_source,
                "by_impact": by_impact
            }

