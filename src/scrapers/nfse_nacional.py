"""
Scraper do Portal Nacional da NFS-e (gov.br/nfse).
Monitora:
- Notícias e Comunicados da NFS-e Nacional
- Resoluções do Comitê Gestor (CGSN / CGNFS-e)
- Regras para Optantes do Simples Nacional e MEI
- Notas Técnicas e atualizações de leiaute da NFS-e e NFS-e Via
"""

import logging
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from src.scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger("ObjectWatcher.NFSe")

BASE_NFSE_URL = "https://www.gov.br/nfse/pt-br/noticias"


class NFSeNacionalScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="Portal NFS-e Nacional")
        self.noticias_url = BASE_NFSE_URL

    def fetch_latest(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []

        try:
            resp = self.session.get(self.noticias_url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Erro ao acessar {self.noticias_url} (HTTP {resp.status_code})")
                return items

            soup = BeautifulSoup(resp.text, "html.parser")
            un = soup.find("div", class_="ultimas-noticias") or soup.find("div", id="content-core")
            if not un:
                logger.warning("Contêiner de notícias da NFS-e não encontrado na página.")
                return items

            # Encontra todos os links de notícias dentro do contêiner
            found_urls = set()
            for a in un.find_all("a", href=True):
                href = a["href"]
                if "noticias/" in href and href != self.noticias_url:
                    full_url = urljoin(self.noticias_url, href)
                    if full_url in found_urls:
                        continue
                    found_urls.add(full_url)

                    title = a.get_text(strip=True)
                    if not title or len(title) < 10 or title.lower() in ["filtrar", "leia mais"]:
                        continue

                    parent = a.find_parent("div") or a.parent
                    parent_text = parent.get_text(" ", strip=True) if parent else ""

                    # Extrai data se presente no texto (formato DD/MM/AAAA)
                    date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", parent_text)
                    published_at = date_match.group(1) if date_match else None

                    # Acessa o artigo para obter o corpo completo da notícia e anexo oficial
                    body_text, attachment_url = self._fetch_article_body_and_attachment(full_url)
                    if not body_text:
                        body_text = parent_text

                    items.append(ScrapedItem(
                        source=self.name,
                        unique_id=full_url,
                        title=f"[NFS-e Nacional] {title}",
                        url=full_url,
                        published_at=published_at,
                        raw_content=body_text,
                        attachment_url=attachment_url
                    ))

                    if len(items) >= 8:
                        break

        except Exception as e:
            logger.error(f"Erro durante scraping da NFS-e Nacional: {e}", exc_info=True)

        return items

    def _fetch_article_body_and_attachment(self, url: str) -> tuple[str, str | None]:
        """Acessa a página da notícia para extrair o texto completo e eventuais anexos (PDF, ZIP)."""
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                core = soup.find("div", id="content-core") or soup.find("article") or soup.find("main")
                attachment_url = None

                if core:
                    # Procura por links de download direto (PDF, ZIP, etc.)
                    for a in core.find_all("a", href=True):
                        href = a["href"]
                        if any(ext in href.lower() for ext in [".pdf", ".zip", ".xlsx", ".docx", "/@@download/file"]):
                            attachment_url = urljoin(url, href)
                            break

                    # Remove scripts, styles e tags desnecessárias
                    for s in core(["script", "style", "nav", "footer"]):
                        s.decompose()
                    return core.get_text(" ", strip=True), attachment_url
        except Exception:
            pass
        return "", None

