"""
Scraper do Portal Nacional da NF-e e NFC-e (SEFAZ / ENCAT).
Monitora:
- Informes e Avisos da Página Principal
- Notas Técnicas e cronogramas de implantação
- Pacotes de Esquemas XML (.xsd)
- Informes Técnicos
"""

import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from src.scrapers.base import BaseScraper, ScrapedItem
from src.config import settings

logger = logging.getLogger("ObjectWatcher.SEFAZ")

BASE_NFE_URL = "https://www.nfe.fazenda.gov.br/portal/"


class NFeSefazScraper(BaseScraper):
    def __init__(self):
        super().__init__(name="SEFAZ NF-e / NFC-e")
        self.portal_url = urljoin(BASE_NFE_URL, "principal.aspx")
        self.nt_url = urljoin(BASE_NFE_URL, "listaConteudo.aspx?tipoConteudo=04BIflQt1aY=")
        self.schemas_url = urljoin(BASE_NFE_URL, "listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=")
        self.informes_url = urljoin(BASE_NFE_URL, "listaConteudo.aspx?tipoConteudo=hXzemuyNHW4=")

    def fetch_latest(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []

        try:
            # 1. Acessa a página principal para obter cookies de sessão da SEFAZ
            resp_main = self.session.get(self.portal_url, timeout=15)
            if resp_main.status_code == 200:
                soup_main = BeautifulSoup(resp_main.text, "html.parser")
                items.extend(self._parse_main_informes(soup_main))
            else:
                logger.warning(f"Erro ao acessar {self.portal_url} (HTTP {resp_main.status_code})")

            # 2. Monitora Notas Técnicas
            items.extend(self._scrape_notas_tecnicas())

            # 3. Monitora Esquemas XML
            items.extend(self._scrape_esquemas_xml())

            # 4. Monitora Informes Técnicos
            items.extend(self._scrape_informes_tecnicos())

        except Exception as e:
            logger.error(f"Erro durante scraping do Portal Nacional da NF-e: {e}", exc_info=True)

        return items

    def _parse_main_informes(self, soup: BeautifulSoup) -> list[ScrapedItem]:
        """Extrai os informes e avisos em destaque na página principal."""
        results: list[ScrapedItem] = []
        
        # Procura por links de informes (ex: informe.aspx?ehCTG=false&Informe=...)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "informe.aspx" in href and "Informe=" in href:
                title = a.get_text(strip=True)
                if not title or title.lower() in ["...(leia mais)", "leia mais", "ver mais"]:
                    continue

                full_url = urljoin(BASE_NFE_URL, href)
                parent = a.find_parent("tr") or a.find_parent("div") or a.parent
                context_text = parent.get_text(" ", strip=True) if parent else title

                # Tenta buscar o conteúdo completo do informe
                detail_text = self._fetch_informe_detail(full_url) or context_text

                results.append(ScrapedItem(
                    source=self.name,
                    unique_id=full_url,
                    title=f"[Aviso SEFAZ] {title}",
                    url=full_url,
                    published_at=None,
                    raw_content=detail_text
                ))

        return results[:5]

    def _fetch_informe_detail(self, url: str) -> str:
        """Busca o texto completo de um informe individual."""
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                s = BeautifulSoup(r.text, "html.parser")
                din = s.find("div", id="conteudoDinamico")
                if din:
                    return din.get_text(" ", strip=True)
        except Exception:
            pass
        return ""

    def _scrape_notas_tecnicas(self) -> list[ScrapedItem]:
        """Raspagem da página oficial de Notas Técnicas."""
        results: list[ScrapedItem] = []
        try:
            resp = self.session.get(self.nt_url, timeout=15)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            spans = soup.find_all("span", class_="tituloConteudo")

            for span in spans[:8]:
                title = span.get_text(strip=True)
                
                # O link direto do PDF é o elemento <a> pai do span
                a_tag = span.find_parent("a") or span.find("a")
                pdf_url = urljoin(BASE_NFE_URL, a_tag["href"]) if (a_tag and a_tag.get("href")) else self.nt_url

                # Extrai a descrição específica da NT a partir dos elementos irmãos
                desc_parts = []
                if a_tag:
                    for sib in a_tag.next_siblings:
                        if hasattr(sib, "name") and sib.name:
                            if sib.name == "a" or (hasattr(sib, "find") and sib.find("span", class_="tituloConteudo")):
                                break
                            desc_parts.append(sib.get_text(" ", strip=True))
                        elif isinstance(sib, str) and sib.strip():
                            desc_parts.append(sib.strip())

                desc_text = " ".join(desc_parts).strip() or title
                raw_content = f"{title}\n{desc_text}"

                # Se for um PDF e a configuração permitir, extrai o texto do cabeçalho da NT
                cfg_nfe = settings.sources_config.get("nfe_sefaz", {})
                if cfg_nfe.get("download_pdfs_for_ai", True) and "exibirArquivo.aspx" in pdf_url:
                    pdf_text = self.extract_pdf_text(pdf_url, max_pages=3)
                    if pdf_text:
                        raw_content = f"{title}\n{desc_text}\n\n[TRECHO DO PDF OFICIAL]:\n{pdf_text}"

                results.append(ScrapedItem(
                    source=self.name,
                    unique_id=pdf_url,
                    title=f"[Nota Técnica] {title}",
                    url=pdf_url,
                    published_at=None,
                    raw_content=raw_content,
                    pdf_url=pdf_url if "exibirArquivo.aspx" in pdf_url else None,
                    attachment_url=pdf_url if "exibirArquivo.aspx" in pdf_url else None
                ))

        except Exception as e:
            logger.warning(f"Erro ao raspar Notas Técnicas SEFAZ: {e}")

        return results

    def _scrape_esquemas_xml(self) -> list[ScrapedItem]:
        """Raspagem de pacotes de Esquemas XML (.xsd)."""
        results: list[ScrapedItem] = []
        try:
            resp = self.session.get(self.schemas_url, timeout=15)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            spans = soup.find_all("span", class_="tituloConteudo")

            for span in spans[:5]:
                title = span.get_text(strip=True)
                a_tag = span.find_parent("a") or span.find("a")
                file_url = urljoin(BASE_NFE_URL, a_tag["href"]) if (a_tag and a_tag.get("href")) else self.schemas_url

                results.append(ScrapedItem(
                    source=self.name,
                    unique_id=file_url,
                    title=f"[Schemas XML] {title}",
                    url=file_url,
                    published_at=None,
                    raw_content=title,
                    attachment_url=file_url if "exibirArquivo.aspx" in file_url else None
                ))

        except Exception as e:
            logger.warning(f"Erro ao raspar Esquemas XML SEFAZ: {e}")

        return results

    def _scrape_informes_tecnicos(self) -> list[ScrapedItem]:
        """Raspagem de Informes Técnicos."""
        results: list[ScrapedItem] = []
        try:
            resp = self.session.get(self.informes_url, timeout=15)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            spans = soup.find_all("span", class_="tituloConteudo")

            for span in spans[:4]:
                title = span.get_text(strip=True)
                a_tag = span.find_parent("a") or span.find("a")
                file_url = urljoin(BASE_NFE_URL, a_tag["href"]) if (a_tag and a_tag.get("href")) else self.informes_url

                results.append(ScrapedItem(
                    source=self.name,
                    unique_id=file_url,
                    title=f"[Informe Técnico] {title}",
                    url=file_url,
                    published_at=None,
                    raw_content=title,
                    attachment_url=file_url if "exibirArquivo.aspx" in file_url else None
                ))

        except Exception as e:
            logger.warning(f"Erro ao raspar Informes Técnicos SEFAZ: {e}")

        return results

