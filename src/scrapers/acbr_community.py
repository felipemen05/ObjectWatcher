"""
Consumidor de Feeds RSS da Comunidade Fiscal ACBr (Projeto ACBr).
Captura avisos de mudanças normativas, discussões de novas NTs e alertas de falhas em webservices da SEFAZ
assim que são identificados e homologados pela comunidade desenvolvedora.
"""

import logging
import feedparser
from bs4 import BeautifulSoup
from src.scrapers.base import BaseScraper, ScrapedItem
from src.config import settings

logger = logging.getLogger("ObjectWatcher.ACBr")


class AcbrCommunityScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="Comunidade Fiscal ACBr")
        self.feeds = settings.sources_config.get("acbr_community", {}).get("feeds", [
            {
                "name": "ACBr - Notícias Fiscais",
                "url": "https://www.projetoacbr.com.br/forum/forum/35-not%C3%ADcias-do-acbr.xml/"
            },
            {
                "name": "ACBr - Legislação Fiscal",
                "url": "https://www.projetoacbr.com.br/forum/forum/5-legisla%C3%A7%C3%A3o-fiscal-e-tribut%C3%A1ria.xml/"
            }
        ])

    def fetch_latest(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []

        for feed_info in self.feeds:
            feed_name = feed_info.get("name", "ACBr")
            feed_url = feed_info.get("url", "")
            if not feed_url:
                continue

            try:
                parsed = feedparser.parse(feed_url)
                if parsed.bozo:
                    logger.debug(f"Aviso de parsing no feed {feed_url}: {parsed.bozo_exception}")

                for entry in parsed.entries[:6]:
                    title = getattr(entry, "title", "").strip()
                    link = getattr(entry, "link", "").strip()
                    published = getattr(entry, "published", None)

                    # Obtém resumo ou descrição do post
                    summary_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    clean_summary = BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True)

                    combined_text = f"{title}\n{clean_summary}"

                    # Verifica relevância caso seja o feed amplo
                    if not self.is_relevant(combined_text) and "notícia" not in feed_name.lower():
                        continue

                    items.append(ScrapedItem(
                        source=feed_name,
                        unique_id=link,
                        title=f"[ACBr Dev] {title}",
                        url=link,
                        published_at=published,
                        raw_content=combined_text
                    ))

            except Exception as e:
                logger.error(f"Erro ao consultar feed RSS ACBr ({feed_url}): {e}")

        return items

