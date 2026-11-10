"""
Módulo de Notificações para o Discord via Webhook.
Gera Embeds ricos em conformidade com os padrões da ObjectData e especificações de integrações fiscais.
"""

import json
import time
import logging
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from src.config import settings

logger = logging.getLogger("ObjectWatcher.Discord")


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        bot_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        channel_id: Optional[str] = None
    ):
        self.webhook_url = webhook_url or settings.discord_webhook_url
        self.bot_token = bot_token or settings.discord_bot_token
        self.channel_id = channel_id or settings.discord_channel_id
        self.bot_name = bot_name or settings.discord_bot_name
        self.avatar_url = avatar_url or settings.discord_avatar_url

    def list_available_channels(self) -> list[dict[str, Any]]:
        """Lista todos os canais de texto disponíveis nos servidores em que o bot está presente."""
        if not self.bot_token:
            logger.warning("Bot token não configurado. Não é possível listar canais.")
            return []

        headers = {"Authorization": f"Bot {self.bot_token}"}
        channels: list[dict[str, Any]] = []

        try:
            # 1. Obtém as guildas (servidores) onde o bot está presente
            resp_guilds = requests.get("https://discord.com/api/v10/users/@me/guilds", headers=headers, timeout=10)
            if resp_guilds.status_code != 200:
                logger.error(f"Erro ao buscar servidores (HTTP {resp_guilds.status_code}): {resp_guilds.text}")
                return []

            guilds = resp_guilds.json()
            for guild in guilds:
                guild_id = guild.get("id")
                guild_name = guild.get("name")

                # 2. Obtém os canais da guilda
                resp_ch = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, timeout=10)
                if resp_ch.status_code == 200:
                    for ch in resp_ch.json():
                        # Tipo 0 = Canal de texto tradicional
                        if ch.get("type") == 0:
                            channels.append({
                                "guild_id": guild_id,
                                "guild_name": guild_name,
                                "channel_id": ch.get("id"),
                                "channel_name": ch.get("name"),
                                "topic": ch.get("topic") or ""
                            })
        except Exception as e:
            logger.error(f"Erro de conexão ao listar canais do Discord: {e}")

        return channels

    def _is_configured(self) -> bool:
        """Verifica se há ao menos um método de envio configurado (Webhook ou Bot Token)."""
        has_webhook = bool(self.webhook_url and "discord.com/api/webhooks" in self.webhook_url)
        has_bot_token = bool(self.bot_token and self.channel_id)
        return has_webhook or has_bot_token

    def send_fiscal_alert(
        self,
        analysis: Dict[str, Any],
        url: str,
        source_name: str,
        published_at: Optional[str] = None,
        attachment: Optional[tuple[str, bytes]] = None
    ) -> bool:
        """
        Envia um alerta fiscal completo e estilizado para o canal do Discord.
        Se houver anexo oficial (PDF/ZIP), o arquivo é enviado junto à mensagem.
        """
        if not self._is_configured():
            logger.warning("Discord não configurado (defina DISCORD_WEBHOOK_URL ou DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID).")
            return False

        # Determina a cor com base no nível de urgência
        urgency = analysis.get("nivel_urgencia", "INFORMATIVO").upper()
        if "ALTO" in urgency:
            color = settings.color_urgent       # Vermelho #E74C3C
            urgency_icon = "🚨"
        elif "MEDIO" in urgency or "MÉDIO" in urgency:
            color = settings.color_attention    # Laranja #E67E22
            urgency_icon = "⚠️"
        else:
            color = settings.color_info         # Azul #3498DB
            urgency_icon = "ℹ️"

        title = analysis.get("titulo_formatado", "Comunicado Fiscal").strip()
        if not title.startswith(("🚨", "⚠️", "ℹ️", "📢")):
            title = f"{urgency_icon} {title}"

        resumo = analysis.get("resumo_executivo", "Nenhum detalhe adicional informado.")
        regimes = analysis.get("regimes_afetados", "Todos os regimes")
        tags = analysis.get("novos_campos_tags", "Nenhuma alteração identificada")
        rejeicoes = analysis.get("regras_rejeicao", "Nenhuma rejeição impeditiva reportada")
        prazos = analysis.get("prazos", "Não especificado")

        fields = [
            {
                "name": "🏢 Regimes Afetados",
                "value": str(regimes)[:1000],
                "inline": False
            },
            {
                "name": "🏷️ Campos & Tags XML (.xsd)",
                "value": str(tags)[:1000],
                "inline": False
            },
            {
                "name": "⚠️ Regras de Rejeição (Impacto na Emissão)",
                "value": str(rejeicoes)[:1000],
                "inline": False
            },
            {
                "name": "📅 Prazos & Vigência",
                "value": str(prazos)[:1000],
                "inline": False
            }
        ]

        # Se houver arquivo anexo (PDF de NT, ZIP de Schemas), destaca no Embed
        if attachment:
            filename, file_bytes = attachment
            size_kb = len(file_bytes) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
            fields.append({
                "name": "📎 Arquivo Oficial Anexado",
                "value": f"`{filename}` ({size_str})\n*Arquivo salvo e anexado diretamente nesta mensagem para download imediato.*",
                "inline": False
            })

        fields.append({
            "name": "🔗 Link Oficial / Portal",
            "value": f"[Acessar Conteúdo no Portal Oficial]({url})",
            "inline": False
        })

        footer_text = f"ObjectWatcher • ObjectData Integrações Fiscais • Fonte: {source_name}"
        if published_at:
            footer_text += f" • Publ: {published_at}"

        embed = {
            "title": title[:250],
            "description": f"**Resumo Executivo:**\n{resumo[:2000]}",
            "url": url,
            "color": color,
            "fields": fields,
            "footer": {
                "text": footer_text,
                "icon_url": self.avatar_url
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        payload = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "embeds": [embed]
        }

        return self._post_payload(payload, attachment=attachment)

    def send_daily_digest(
        self,
        digest: Dict[str, Any],
        date_str: str,
        items_count: int
    ) -> bool:
        """
        Envia o Embed consolidado do Fechamento Fiscal Diário das 17:30 para o canal do Discord.
        """
        if not self._is_configured():
            logger.warning("Discord não configurado para envio do Resumo Diário.")
            return False

        color = settings.color_digest  # Roxo #9B59B6
        titulo = digest.get("titulo_digest", f"Fechamento Fiscal Diário • {date_str}")
        panorama = digest.get("panorama_geral", "Resumo das alterações fiscais apuradas no dia de hoje.")
        mudancas = digest.get("principais_mudancas", [])
        atencao = digest.get("atencao_desenvolvedores", "Acompanhar as notas técnicas em ambiente de homologação.")
        prazos = digest.get("prazos_urgentes", "Manter atenção aos prazos normativos em vigor.")

        if isinstance(mudancas, list):
            mudancas_str = "\n".join(f"• {m}" for m in mudancas)
        else:
            mudancas_str = str(mudancas)

        fields = [
            {
                "name": f"📋 Principais Mudanças Apuradas Hoje ({items_count} publicação{'ões' if items_count != 1 else ''})",
                "value": mudancas_str[:1000] if mudancas_str else "Nenhuma alteração impeditiva registrada.",
                "inline": False
            },
            {
                "name": "💻 Diretrizes Técnicas para o Time ERP",
                "value": str(atencao)[:1000],
                "inline": False
            },
            {
                "name": "📅 Prazos & Cronograma Regulatório",
                "value": str(prazos)[:1000],
                "inline": False
            }
        ]

        embed = {
            "title": f"📊 {titulo}",
            "description": f"**Panorama Geral do Dia:**\n{panorama[:2000]}",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "ObjectWatcher • Fechamento Fiscal das 17:30 • ObjectData ERP",
                "icon_url": self.avatar_url
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        payload = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "embeds": [embed]
        }

        logger.info(f"Enviando Resumo Diário das 17:30 para o Discord ({items_count} itens consolidados)...")
        return self._post_payload(payload)

    def send_test_message(self) -> bool:
        """Envia uma mensagem de teste para verificar a integridade da conexão com o Discord."""
        if not self._is_configured():
            logger.error("Discord não configurado! Defina DISCORD_WEBHOOK_URL ou DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID.")
            return False

        payload = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "embeds": [
                {
                    "title": "✅ [TESTE DE CONECTIVIDADE] ObjectWatcher Online",
                    "description": "O monitor fiscal **ObjectWatcher** da **ObjectData** foi inicializado com sucesso e está conectado a este canal.",
                    "color": settings.color_info,
                    "fields": [
                        {"name": "Status do Monitor", "value": "🟢 Monitoramento Ativo", "inline": True},
                        {"name": "Ambiente", "value": "Produção / Fiscal ERP", "inline": True},
                        {"name": "Portais Monitorados", "value": "• NF-e / NFC-e (SEFAZ)\n• NFS-e Nacional\n• SPED / RFB (Tributário)\n• ACBr Comunidade Dev", "inline": False}
                    ],
                    "footer": {
                        "text": "ObjectWatcher • ObjectData Integrações Fiscais",
                        "icon_url": self.avatar_url
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        return self._post_payload(payload)

    def _post_payload(
        self,
        payload: Dict[str, Any],
        attachment: Optional[tuple[str, bytes]] = None,
        max_retries: int = 3
    ) -> bool:
        """
        Executa o POST HTTP para o Discord.
        Suporta tanto Webhook direto quanto Bot Token oficial (via endpoint /channels/{id}/messages).
        """
        is_webhook = bool(self.webhook_url and "discord.com/api/webhooks" in self.webhook_url)

        if is_webhook:
            endpoint_url = self.webhook_url
            auth_header = {}
        elif self.bot_token and self.channel_id:
            endpoint_url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
            auth_header = {"Authorization": f"Bot {self.bot_token}"}
        else:
            logger.error("Nenhum destino válido configurado para o Discord.")
            return False

        for attempt in range(1, max_retries + 1):
            try:
                if attachment:
                    filename, file_bytes = attachment
                    files = {
                        "files[0]": (filename, file_bytes)
                    }
                    data = {
                        "payload_json": json.dumps(payload)
                    }
                    resp = requests.post(
                        endpoint_url,
                        data=data,
                        files=files,
                        headers=auth_header,
                        timeout=60
                    )
                else:
                    headers = {"Content-Type": "application/json", **auth_header}
                    resp = requests.post(
                        endpoint_url,
                        json=payload,
                        headers=headers,
                        timeout=15
                    )
                
                if resp.status_code in (200, 201, 204):
                    logger.info("Notificação enviada com sucesso ao Discord.")
                    time.sleep(settings.rate_limit_delay)
                    return True
                
                if resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 2.0)
                    logger.warning(f"Rate limit do Discord atingido. Aguardando {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                
                logger.error(f"Falha ao enviar ao Discord (HTTP {resp.status_code}): {resp.text}")
                return False

            except Exception as e:
                logger.error(f"Erro de rede ao enviar notificação ao Discord (Tentativa {attempt}/{max_retries}): {e}")
                time.sleep(2)

        return False

