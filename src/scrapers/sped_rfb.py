"""
Scraper do SPED e Legislação Tributária Federal (Receita Federal do Brasil).
Monitora:
- Publicações do Portal SPED (EFD-Contribuições, EFD-ICMS/IPI, ECF, ECD, Tabelas de NCM/CST)
- Notícias Fiscais da Receita Federal (PIS, COFINS, IPI e Reforma Tributária IBS/CBS)
"""

import logging
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from src.scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger("ObjectWatcher.SPED")

BASE_SPED_URL = "http://sped.rfb.gov.br/"
BASE_RFB_NEWS_URL = "https://www.gov.br/receitafederal/pt-br/assuntos/noticias"


class SpedRfbScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="SPED / Receita Federal")
        self.sped_url = BASE_SPED_URL
        self.rfb_url = BASE_RFB_NEWS_URL

    def fetch_latest(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []

        # 1. Portal SPED
        items.extend(self._scrape_sped_portal())

        # 2. Portal Receita Federal (Notícias Fiscais)
        items.extend(self._scrape_rfb_news())

        return items

    def _scrape_sped_portal(self) -> list[ScrapedItem]:
        results: list[ScrapedItem] = []
        try:
            resp = self.session.get(self.sped_url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Erro ao acessar {self.sped_url} (HTTP {resp.status_code})")
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            seen_urls = set()

            # Procura títulos nos destaques (h2)
            for h2 in soup.find_all("h2"):
                a = h2.find("a", href=True)
                if not a:
                    continue

                href = a["href"]
                if "/item/show/" not in href:
                    continue

                full_url = urljoin(self.sped_url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = a.get_text(strip=True)
                if not title:
                    continue

                # Busca corpo da notícia, data e anexo no SPED
                body_text, pub_date, attachment_url = self._fetch_sped_item_detail(full_url)

                results.append(ScrapedItem(
                    source=self.name,
                    unique_id=full_url,
                    title=f"[SPED / RFB] {title}",
                    url=full_url,
                    published_at=pub_date,
                    raw_content=body_text or title,
                    attachment_url=attachment_url
                ))

                if len(results) >= 6:
                    break

        except Exception as e:
            logger.error(f"Erro durante scraping do portal SPED: {e}")

        return results

    def _fetch_sped_item_detail(self, url: str) -> tuple[str, str | None, str | None]:
        """Acessa a página de detalhes do item do SPED para extrair texto, data e anexos."""
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                col = soup.find("div", id="col-meio") or soup.find("div", class_="col-meio")
                if col:
                    attachment_url = None
                    for a in col.find_all("a", href=True):
                        href = a["href"]
                        if any(ext in href.lower() for ext in [".pdf", ".zip", ".exe", ".jar", ".xsd"]):
                            attachment_url = urljoin(url, href)
                            break

                    text = col.get_text(" ", strip=True)
                    date_match = re.search(r"Publicado\s+em\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
                    pub_date = date_match.group(1) if date_match else None
                    return text, pub_date, attachment_url
        except Exception:
            pass
        return "", None, None

    def _scrape_rfb_news(self) -> list[ScrapedItem]:
        """Monitora notícias fiscais no portal oficial da Receita Federal."""
        results: list[ScrapedItem] = []
        try:
            resp = self.session.get(self.rfb_url, timeout=15)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            core = soup.find("div", id="content-core") or soup.find("main")
            if not core:
                return results

            seen_urls = set()
            for a in core.find_all("a", href=True):
                href = a["href"]
                if "noticias/" not in href or href == self.rfb_url:
                    continue

                full_url = urljoin(self.rfb_url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = a.get_text(strip=True)
                if not title or len(title) < 15:
                    continue

                parent = a.find_parent("li") or a.find_parent("div")
                parent_text = parent.get_text(" ", strip=True) if parent else title

                # Filtra apenas notícias relevantes para tributos e ERP
                if not self.is_relevant(parent_text):
                    continue

                date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", parent_text)
                pub_date = date_match.group(1) if date_match else None

                results.append(ScrapedItem(
                    source="Receita Federal Tributária",
                    unique_id=full_url,
                    title=f"[TRIBUTÁRIO] {title}",
                    url=full_url,
                    published_at=pub_date,
                    raw_content=parent_text
                ))

                if len(results) >= 4:
                    break

        except Exception as e:
            logger.warning(f"Erro ao raspar notícias da Receita Federal: {e}")

        return results

