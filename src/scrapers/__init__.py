from src.scrapers.base import BaseScraper, ScrapedItem
from src.scrapers.nfe_sefaz import NFeSefazScraper
from src.scrapers.nfse_nacional import NFSeNacionalScraper
from src.scrapers.sped_rfb import SpedRfbScraper
from src.scrapers.acbr_community import AcbrCommunityScraper

__all__ = [
    "BaseScraper",
    "ScrapedItem",
    "NFeSefazScraper",
    "NFSeNacionalScraper",
    "SpedRfbScraper",
    "AcbrCommunityScraper",
]

