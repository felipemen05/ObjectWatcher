"""
Orquestrador Central do ObjectWatcher.
Coordena o fluxo de execução: Raspagem -> Deduplicação -> Síntese com IA -> Notificação Discord -> Persistência.
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, List
from src.config import settings
from src.database import DatabaseManager
from src.ai_analyzer import AIAnalyzer
from src.discord_notifier import DiscordNotifier
from src.scrapers import (
    BaseScraper,
    NFeSefazScraper,
    NFSeNacionalScraper,
    SpedRfbScraper,
    AcbrCommunityScraper,
)

logger = logging.getLogger("ObjectWatcher.Core")


class ObjectWatcher:
    def __init__(self):
        self.db = DatabaseManager()
        self.ai = AIAnalyzer()
        self.notifier = DiscordNotifier()
        self.scrapers: List[BaseScraper] = self._load_scrapers()

    def _load_scrapers(self) -> List[BaseScraper]:
        """Inicializa os módulos de monitoramento ativos conforme o arquivo de configuração."""
        scrapers: List[BaseScraper] = []
        sources = settings.sources_config

        if sources.get("nfe_sefaz", {}).get("enabled", True):
            scrapers.append(NFeSefazScraper())
        if sources.get("nfse_nacional", {}).get("enabled", True):
            scrapers.append(NFSeNacionalScraper())
        if sources.get("sped_rfb", {}).get("enabled", True):
            scrapers.append(SpedRfbScraper())
        if sources.get("acbr_community", {}).get("enabled", True):
            scrapers.append(AcbrCommunityScraper())

        logger.info(f"ObjectWatcher inicializado com {len(scrapers)} scrapers ativos: {[s.name for s in scrapers]}")
        return scrapers

    def run_check(self, dry_run: bool = False, max_new_per_run: int = 15) -> Dict[str, Any]:
        """
        Executa uma rodada completa de checagem em todas as fontes configuradas.
        
        :param dry_run: Se True, simula o processamento sem enviar mensagens ao Discord ou salvar no banco.
        :param max_new_per_run: Limite máximo de novos itens processados por execução (evita flood na primeira execução).
        """
        logger.info("=== Iniciando ciclo de monitoramento fiscal ===")
        total_scraped = 0
        total_filtered = 0
        total_new = 0
        total_notified = 0

        for scraper in self.scrapers:
            logger.info(f"Consultando fonte: {scraper.name}...")
            try:
                items = scraper.fetch_latest()
                total_scraped += len(items)

                for item in items:
                    # Gera chave única para deduplicação
                    item_id = self.db.generate_id(item.source, item.unique_id)

                    # Verifica se o item já foi processado no histórico
                    if self.db.is_processed(item_id):
                        logger.debug(f"Item já processado anteriormente: {item.title}")
                        continue

                    # Classificação prévia de urgência sem consumo de tokens de IA
                    urgency_level, matched_reasons = BaseScraper.classify_fiscal_urgency(item.title, item.raw_content)

                    # Se configurado para revisar apenas urgências (alertas em vermelho), descarta rotinas informativas
                    if settings.filter_only_urgent and urgency_level != "ALTO":
                        total_filtered += 1
                        logger.info(
                            f"⏭️ [ECONOMIA DE TOKENS] Publicação rotineira/informativa ignorada: '{item.title}'. "
                            f"(Nenhuma chamada à API Gemini realizada e nenhum alerta enviado ao Discord)"
                        )
                        # Salva no histórico do banco para não reprocessar no futuro
                        if not dry_run:
                            self.db.save_item(
                                item_id=item_id,
                                source=item.source,
                                title=item.title,
                                url=item.url,
                                published_at=item.published_at,
                                impact_level="INFORMATIVO",
                                summary="Ignorado pelo filtro de urgência (economia de tokens).",
                                erp_impact="Nenhum impacto crítico identificado.",
                                sent_to_discord=False
                            )
                        continue

                    total_new += 1
                    reasons_str = ", ".join(matched_reasons) if matched_reasons else "Relevância fiscal identificada"
                    logger.info(f"🚨 [URGÊNCIA ALTA / ALERTA VERMELHO] Item crítico detectado: '{item.title}' (Motivos: {reasons_str})")

                    # 1. Processamento e síntese inteligente do conteúdo fiscal (somente aqui a IA é chamada!)
                    analysis = self.ai.analyze_fiscal_content(
                        source_name=item.source,
                        title=item.title,
                        content_text=item.raw_content,
                        url=item.url
                    )

                    # Garante que itens críticos identificados sejam enviados com urgência ALTA (cor vermelha #E74C3C)
                    if urgency_level == "ALTO":
                        analysis["nivel_urgencia"] = "ALTO"

                    # 2. Download e arquivamento do arquivo oficial (PDF de NT, ZIP de Schemas)
                    attachment_data = None
                    if item.attachment_url and (settings.attach_files_to_discord or settings.save_local_archive):
                        attachment_data = scraper.download_file(
                            item.attachment_url,
                            max_size_mb=settings.max_attachment_size_mb
                        )
                        if attachment_data and settings.save_local_archive:
                            # Salva uma cópia local organizada por data (ex: downloads/2026-11-09/arquivo.pdf)
                            self._save_to_local_archive(attachment_data, item.source)

                    if dry_run:
                        logger.info(f"[DRY-RUN] Embed simulado para '{analysis.get('titulo_formatado')}':")
                        logger.info(f"   Urgência: {analysis.get('nivel_urgencia')} (Alerta Vermelho)")
                        logger.info(f"   Resumo: {analysis.get('resumo_executivo')}")
                        logger.info(f"   Regimes: {analysis.get('regimes_afetados')}")
                        logger.info(f"   Tags XML: {analysis.get('novos_campos_tags')}")
                        logger.info(f"   Rejeições: {analysis.get('regras_rejeicao')}")
                        logger.info(f"   Prazos: {analysis.get('prazos')}")
                        if attachment_data:
                            logger.info(f"   📎 Anexo Detectado: {attachment_data[0]} ({len(attachment_data[1])/1024:.1f} KB)")
                        continue

                    # 3. Envio da notificação rica ao canal do Discord com anexo direto
                    attachment_to_send = attachment_data if settings.attach_files_to_discord else None
                    sent = self.notifier.send_fiscal_alert(
                        analysis=analysis,
                        url=item.url,
                        source_name=item.source,
                        published_at=item.published_at,
                        attachment=attachment_to_send
                    )

                    if sent:
                        total_notified += 1

                    # 4. Persistência no banco SQLite para deduplicação futura
                    self.db.save_item(
                        item_id=item_id,
                        source=item.source,
                        title=item.title,
                        url=item.url,
                        published_at=item.published_at,
                        impact_level=analysis.get("nivel_urgencia", "ALTO"),
                        summary=analysis.get("resumo_executivo"),
                        erp_impact=f"Regimes: {analysis.get('regimes_afetados')} | Tags: {analysis.get('novos_campos_tags')}",
                        sent_to_discord=sent
                    )

                    if total_new >= max_new_per_run:
                        logger.warning(f"Limite máximo de {max_new_per_run} novos itens atingido para este ciclo.")
                        break

            except Exception as e:
                logger.error(f"Erro ao processar fonte '{scraper.name}': {e}", exc_info=True)

        logger.info(
            f"=== Ciclo concluído: {total_scraped} verificados | {total_filtered} rotineiros ignorados (tokens salvos) | "
            f"{total_new} urgentes processados | {total_notified} alertas enviados ==="
        )

        return {
            "total_scraped": total_scraped,
            "total_filtered": total_filtered,
            "total_new": total_new,
            "total_notified": total_notified,
            "dry_run": dry_run
        }

    def _save_to_local_archive(self, attachment: tuple[str, bytes], source_name: str) -> None:
        """Salva uma cópia local organizada por data no diretório de downloads."""
        try:
            filename, file_bytes = attachment
            today_str = datetime.now().strftime("%Y-%m-%d")
            dest_dir = settings.archive_dir / today_str
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            dest_path = dest_dir / filename
            dest_path.write_bytes(file_bytes)
            logger.info(f"💾 Cópia local arquivada em: {dest_path}")
        except Exception as e:
            logger.warning(f"Erro ao salvar cópia local do arquivo '{attachment[0]}': {e}")

    def run_loop(self, interval_minutes: int = 60, dry_run: bool = False):
        """Executa o monitor continuamente em loop com o intervalo especificado."""
        logger.info(f"Iniciando ObjectWatcher em modo contínuo (intervalo: {interval_minutes} minutos).")
        try:
            while True:
                self.run_check(dry_run=dry_run)
                logger.info(f"Aguardando {interval_minutes} minutos até a próxima checagem...")
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            logger.info("Monitoramento interrompido pelo usuário.")

