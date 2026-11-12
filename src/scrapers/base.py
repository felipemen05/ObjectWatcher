"""
Classe base para todos os Scrapers e Consumidores de Feed do ObjectWatcher.
Fornece gerenciamento de sessão HTTP, manipulação de cookies, extração de PDFs e filtros de relevância.
"""

import io
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse
from pathlib import Path
import requests
from pypdf import PdfReader
from src.config import settings

logger = logging.getLogger("ObjectWatcher.Scraper")


@dataclass
class ScrapedItem:
    source: str
    unique_id: str
    title: str
    url: str
    published_at: Optional[str]
    raw_content: str
    pdf_url: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_filename: Optional[str] = None


class BaseScraper(ABC):
    def __init__(self, name: str):
        self.name = name
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    @abstractmethod
    def fetch_latest(self) -> List[ScrapedItem]:
        """Método abstrato que deve retornar a lista de publicações recentes encontradas."""
        pass

    def is_relevant(self, text: str) -> bool:
        """Verifica se o conteúdo possui relevância para o ERP com base nas palavras-chave configuradas."""
        if not text:
            return False
        lower_text = text.lower()
        return any(kw.lower() in lower_text for kw in settings.relevance_keywords)

    @staticmethod
    def classify_fiscal_urgency(title: str, text: str) -> tuple[str, list[str]]:
        """
        Classifica previamente a criticidade fiscal de uma publicação (sem custo de IA).
        Retorna ('ALTO', [motivos]) para notícias que exigem alerta em VERMELHO no ERP,
        ou ('INFORMATIVO', []) para avisos de rotina/baixa criticidade.
        """
        combined = f"{title}\n{text}".lower()
        matched_reasons: list[str] = []

        # 1. Regras de Rejeição, Erros e Falhas Impeditivas
        if re.search(r"\b(?:rejeição|rejeicao|rejeitado|rejeitada|erro\s+\d{3}|falha\s+no\s+schema)\b", combined):
            matched_reasons.append("Regras de Rejeição / Erro de Validação")

        # 2. Notas Técnicas e Pacotes de Schemas XML (.xsd)
        if re.search(r"\b(?:nota\s+t[eé]cnica|nt\s*\d{4}|nt\s*0\d{2}|schemas?\s+xml|pacote\s+de\s+libera[cç][aã]o|\.xsd)\b", combined):
            matched_reasons.append("Nota Técnica / Schemas XML (.xsd)")

        # 3. Alterações de Leiaute ou Tags XML
        if re.search(r"\b(?:leiaute|layout|novos?\s+campos?|novas?\s+tags?|<[a-zA-Z0-9_]+>)\b", combined):
            matched_reasons.append("Alteração de Leiaute / Tags XML")

        # 4. Prazos Fatais, Obrigatoriedades e Viradas de Chave
        if re.search(r"\b(?:obrigatoriedade|obrigat[oó]ri[ao]|virada\s+de\s+chave|entrada\s+em\s+vigor|prazo\s+de\s+implanta[cç][aã]o|prazo\s+fatal)\b", combined):
            matched_reasons.append("Obrigatoriedade / Prazo de Implantação")

        # 5. Indisponibilidade, Instabilidade ou Manutenção de SEFAZ
        if re.search(r"\b(?:indisponibilidade|instabilidade|fora\s+do\s+ar|manuten[cç][aã]o\s+programada|bloqueio)\b", combined):
            matched_reasons.append("Indisponibilidade / Instabilidade de Serviços")

        # 6. Reforma Tributária (IBS/CBS, Split Payment) e Atos Técnicos
        if re.search(r"\b(?:ibs|cbs|split\s+payment|reforma\s+tribut[aá]ria|ato\s+t[eé]cnico|ato\s+conjunto|resolu[cç][aã]o\s+cgsn)\b", combined):
            matched_reasons.append("Reforma Tributária / Atos Normativos (IBS/CBS)")

        # 7. Descontinuação ou Extinção de Serviços
        if re.search(r"\b(?:descontinua[cç][aã]o|descontinuad[oa]|inutiliza[cç][aã]o|autoriza[cç][aã]o\s+ass[ií]ncrona|revoga[cç][aã]o)\b", combined):
            matched_reasons.append("Descontinuação / Extinção de Serviços")

        if matched_reasons:
            return "ALTO", matched_reasons
        return "INFORMATIVO", []

    def download_file(self, url: str, max_size_mb: int = 25) -> Optional[Tuple[str, bytes]]:
        """
        Baixa um arquivo anexo oficial (PDF de Nota Técnica, ZIP de Schemas XML, manuais).
        Retorna uma tupla (nome_do_arquivo, conteudo_em_bytes) ou None em caso de falha.
        """
        try:
            url = url.strip().replace(" ", "%20")
            logger.debug(f"Iniciando download do arquivo anexo: {url}")
            resp = self.session.get(url, stream=True, timeout=30)
            if resp.status_code != 200:
                logger.warning(f"Falha ao baixar anexo de {url} (HTTP {resp.status_code})")
                return None

            # 1. Verifica tamanho máximo permitido antes e durante o download
            max_bytes = max_size_mb * 1024 * 1024
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                logger.warning(
                    f"Arquivo {url} excede o limite de upload do Discord "
                    f"({int(content_length)/(1024*1024):.1f}MB > {max_size_mb}MB)."
                )
                return None

            # 2. Extrai nome oficial do arquivo via Content-Disposition ou URL
            filename = self._resolve_filename(resp, url)

            # 3. Baixa o conteúdo limitando a max_bytes
            content_chunks = []
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        logger.warning(f"Download de {filename} interrompido: excedeu {max_size_mb}MB.")
                        return None
                    content_chunks.append(chunk)

            file_bytes = b"".join(content_chunks)
            logger.info(f"Arquivo '{filename}' baixado com sucesso ({len(file_bytes)/1024:.1f} KB).")
            return filename, file_bytes

        except Exception as e:
            logger.warning(f"Erro ao baixar arquivo anexo {url}: {e}")
            return None

    def _resolve_filename(self, resp: requests.Response, url: str) -> str:
        """Determina o nome do arquivo com base no cabeçalho ou extensão."""
        cd = resp.headers.get("Content-Disposition", "")
        if cd:
            # Procura por filename="exemplo.pdf" ou filename=exemplo.pdf
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
            if match:
                clean_name = unquote(match.group(1).strip("\"' \t"))
                # Corrige encoding ISO-8859-1 para UTF-8 comum em servidores governamentais brasileiros
                try:
                    clean_name = clean_name.encode("latin1").decode("utf-8")
                except Exception:
                    pass
                # Remove caminhos relativos indesejados
                return Path(clean_name).name

        # Fallback para o final da URL
        parsed_path = urlparse(url).path
        base_name = Path(parsed_path).name
        if base_name and "." in base_name and not base_name.endswith((".aspx", ".php", ".html")):
            return base_name

        # Fallback baseado no Content-Type
        ctype = resp.headers.get("Content-Type", "").lower()
        if "pdf" in ctype:
            ext = ".pdf"
        elif "zip" in ctype or "compressed" in ctype:
            ext = ".zip"
        elif "xml" in ctype:
            ext = ".xml"
        else:
            ext = ".bin"

        return f"documento_fiscal_{int(resp.elapsed.total_seconds())}{ext}"

    def extract_pdf_text(self, pdf_url: str, max_pages: int = 4) -> str:
        """
        Baixa o PDF indicado (ex: Nota Técnica oficial da SEFAZ) e extrai o texto
        das primeiras páginas em memória para alimentar a inteligência artificial.
        """
        try:
            pdf_url = pdf_url.strip().replace(" ", "%20")
            logger.debug(f"Baixando PDF para análise: {pdf_url}")
            resp = self.session.get(pdf_url, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"Não foi possível baixar o PDF {pdf_url} (HTTP {resp.status_code})")
                return ""

            if not resp.content.startswith(b"%PDF"):
                logger.debug(f"Arquivo retornado por {pdf_url} não é um PDF válido.")
                return ""

            reader = PdfReader(io.BytesIO(resp.content))
            extracted_pages = []
            total_pages = min(len(reader.pages), max_pages)

            for i in range(total_pages):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    extracted_pages.append(page_text.strip())

            return "\n\n--- PÁGINA SEGUINTE ---\n\n".join(extracted_pages)
        except Exception as e:
            logger.warning(f"Erro ao extrair texto do PDF {pdf_url}: {e}")
            return ""

