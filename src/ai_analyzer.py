"""
Módulo de Inteligência Artificial para Síntese Fiscal voltada a Desenvolvedores ERP.
Utiliza a API Google Gemini Flash para gerar relatórios técnicos objetivos e estruturados.
Possui fallback determinístico automático caso a chave de API não esteja configurada ou ocorra indisponibilidade.
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List
import requests
from src.config import settings

logger = logging.getLogger("ObjectWatcher.AI")


class AIAnalyzer:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.timeout = settings.ai_timeout
        self.last_working_model: Optional[str] = None
        self.exhausted_models: set[str] = set()

    def analyze_fiscal_content(
        self,
        source_name: str,
        title: str,
        content_text: str,
        url: str
    ) -> Dict[str, Any]:
        """
        Analisa o conteúdo fiscal (notícia, nota técnica, manual ou PDF extraído)
        e retorna um dicionário estruturado com foco estrito em desenvolvimento de ERP.
        """
        # Se a chave da API estiver configurada, tenta chamar o Gemini Flash
        if self.api_key and self.api_key.strip() and self.api_key != "sua_chave_gemini_aqui":
            try:
                result = self._call_gemini(source_name, title, content_text, url)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Falha ao chamar API Gemini Flash ({e}). Utilizando motor de fallback heurístico.")

        # Fallback heurístico e determinístico
        return self._heuristic_fallback(source_name, title, content_text, url)

    def _call_gemini(
        self,
        source_name: str,
        title: str,
        content_text: str,
        url: str
    ) -> Optional[Dict[str, Any]]:
        """Invoca a API do Google Gemini via REST JSON estruturado para analisar um item fiscal."""
        # Limita o texto de entrada para economizar tokens mantendo o essencial (até ~4.000 caracteres)
        truncated_content = content_text[:4000]

        prompt = f"""
Você é um Arquiteto de Software e Engenheiro de Integrações Fiscais Sênior de um sistema ERP brasileiro (ObjectData).
Analise o comunicado, notícia fiscal ou Nota Técnica abaixo e gere um relatório técnico estritamente voltado para desenvolvedores de software ERP.

FONTE: {source_name}
TÍTULO ORIGINAL: {title}
LINK: {url}
CONTEÚDO/EXTRAÇÃO DO TEXTO:
\"\"\"
{truncated_content}
\"\"\"

Você DEVE responder ESTRITAMENTE em formato JSON (sem blocos markdown adicionais em volta ou com ```json ... ```) com as seguintes chaves:
{{
  "titulo_formatado": "Tipo do documento e número com colchetes (Ex: [NF-e / NFC-e] NT 2026.008 v1.01 - Criação do Valor Líquido ou [NFS-e Nacional] Resolução CGSN nº 175 ou [TRIBUTÁRIO] Nova Tabela de PIS/COFINS)",
  "resumo_executivo": "O que mudou em exatas 2 ou 3 frases curtas e diretas, sem enrolação.",
  "regimes_afetados": "Indique claramente os regimes: Simples Nacional, Lucro Presumido, Lucro Real, MEI, ou 'Todos os contribuintes'",
  "novos_campos_tags": "Liste novos campos, tags XML (.xsd), grupos (ex: <vLiq>, <cBenef>) ou informe 'Nenhuma alteração de tag XML identificada'.",
  "regras_rejeicao": "Liste novas regras de validação/rejeição que podem travar a emissão ou 'Nenhuma nova regra de rejeição impeditiva reportada'.",
  "prazos": "Data de homologação, produção ou início da obrigatoriedade (ex: Homologação: 01/12/2026 | Produção: 01/02/2027). Se não constar data explícita, informe 'Em vigor imediato / A verificar'.",
  "nivel_urgencia": "ALTO (para novas rejeições que travam emissão, quebra de schema XSD ou paradas de serviço), MEDIO (para novos campos facultativos ou prazos futuros) ou INFORMATIVO (para comunicados normativos, manuais ou reuniões)."
}}
"""
        return self._call_gemini_prompt(prompt)

    def _call_gemini_prompt(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Executa um prompt JSON estruturado na cascata de modelos do Google Gemini."""
        # Lista ordenada de modelos para degradação graciosa (Cascata de Segurança)
        # Se os tokens/cota de um modelo esgotarem (HTTP 429), houver sobrecarga (HTTP 503) ou timeout,
        # o sistema desce automaticamente para o próximo modelo.
        # Se já encontramos um modelo funcional no ciclo recente, prioriza ele para economizar tempo.
        preferred_models = [self.last_working_model] if self.last_working_model and self.last_working_model not in self.exhausted_models else []

        cascade_models = preferred_models + [
            self.model,
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
        ]
        unique_models = [m for m in dict.fromkeys(cascade_models) if m and m not in self.exhausted_models]

        if not unique_models:
            logger.info("Todos os modelos de IA da cascata esgotaram cota. Utilizando motor heurístico local.")
            return None

        for model_name in unique_models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "topP": 0.8,
                    "maxOutputTokens": 1500,
                    "responseMimeType": "application/json"
                }
            }

            try:
                # Timeout ágil por modelo (10s) para não travar o fluxo caso haja lentidão
                resp = requests.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        clean_json_str = self._clean_json(raw_text)
                        try:
                            parsed = json.loads(clean_json_str)
                            self._normalize_parsed_fields(parsed)
                            self.last_working_model = model_name
                            logger.info(f"✅ Síntese fiscal gerada com sucesso via Gemini ({model_name}).")
                            return parsed
                        except json.JSONDecodeError as je:
                            logger.warning(f"Resposta JSON incompleta do modelo '{model_name}': {je}. Tentando próximo modelo...")
                            continue

                elif resp.status_code == 429:
                    self.exhausted_models.add(model_name)
                    logger.warning(
                        f"⚠️ Tokens/Cota esgotados para o modelo '{model_name}' (HTTP 429). "
                        "Descendo automaticamente para o próximo modelo da cascata..."
                    )
                    continue

                elif resp.status_code == 503:
                    logger.warning(
                        f"⚠️ Modelo '{model_name}' com sobrecarga temporária (HTTP 503). "
                        "Descendo automaticamente para o próximo modelo da cascata..."
                    )
                    continue

                elif resp.status_code in (400, 401, 403):
                    logger.warning(
                        f"Chave da API Gemini não autorizada (HTTP {resp.status_code}). "
                        "Ativando motor heurístico local de emergência."
                    )
                    break

                elif resp.status_code == 404:
                    logger.debug(f"Modelo '{model_name}' não disponível nesta versão (404). Próximo...")
                    continue

                else:
                    logger.warning(f"Resposta inesperada do Gemini ({model_name} - HTTP {resp.status_code}): {resp.text[:120]}")

            except requests.exceptions.Timeout:
                logger.warning(f"⏱️ Tempo limite esgotado para o modelo '{model_name}'. Descendo para o próximo...")
                continue
            except Exception as e:
                logger.warning(f"Falha de conexão com '{model_name}' ({e}). Tentando próximo modelo...")
                continue

        logger.info("🛡️ Todos os modelos de IA indisponíveis ou com tokens esgotados. Ativando Motor Heurístico Local.")
        return None

    def generate_daily_digest(
        self,
        items: List[Dict[str, Any]],
        date_str: str
    ) -> Dict[str, Any]:
        """
        Compila e resume todas as publicações fiscais do dia em um briefing executivo consolidado para o time de ERP.
        """
        if not items:
            return {
                "titulo_digest": f"Fechamento Fiscal Diário • {date_str}",
                "panorama_geral": "Nenhuma alteração fiscal crítica ou regra de validação foi publicada nos portais monitorados hoje.",
                "principais_mudancas": ["Portais da SEFAZ, NFS-e e Receita Federal operando em estabilidade sem publicações impeditivas hoje."],
                "atencao_desenvolvedores": "Nenhuma ação corretiva ou atualização de layout necessária no ERP para o dia de hoje.",
                "prazos_urgentes": "Manter o cronograma regular de homologação e emissão.",
                "nivel_atencao_geral": "INFORMATIVO"
            }

        itens_formatados = []
        for idx, item in enumerate(items[:10], start=1):
            source = item.get("source", "Portal Fiscal")
            title = item.get("title", "Sem título")
            summary = item.get("summary") or item.get("erp_impact") or ""
            itens_formatados.append(f"{idx}. [{source}] {title}\n   Detalhes: {summary[:250]}")

        bloco_itens = "\n\n".join(itens_formatados)

        prompt = f"""
Você é o Arquiteto de Software e Engenheiro de Integrações Fiscais Sênior da empresa ObjectData (sistema ERP).
Gere o RELATÓRIO DE FECHAMENTO FISCAL DIÁRIO ({date_str}) consolidando todas as novidades fiscais do dia para a equipe de tecnologia.

PUBLICAÇÕES DO DIA:
\"\"\"
{bloco_itens}
\"\"\"

Você DEVE responder ESTRITAMENTE em formato JSON (sem blocos markdown adicionais em volta ou com ```json ... ```) com as seguintes chaves:
{{
  "titulo_digest": "Fechamento Fiscal Diário • {date_str}",
  "panorama_geral": "Visão geral e executiva do dia em exatas 2 ou 3 frases claras, sintetizando o impacto global nas operações do ERP.",
  "principais_mudancas": [
    "Resumo em tópicos concisos das mudanças mais importantes (máximo 4 tópicos diretos)"
  ],
  "atencao_desenvolvedores": "Diretrizes práticas para o time de desenvolvimento (ex: novas tags XML a testar, schemas a atualizar, regras de validação para conferir).",
  "prazos_urgentes": "Destaque dos prazos mais críticos mencionados (ou 'Nenhum prazo imediato reportado hoje').",
  "nivel_atencao_geral": "ALTO (se houver rejeições ou quebras de schema) ou MEDIO (se forem apenas prazos ou evoluções) ou INFORMATIVO"
}}
"""
        if self.api_key and self.api_key.strip() and self.api_key != "sua_chave_gemini_aqui":
            try:
                res = self._call_gemini_prompt(prompt)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Falha ao gerar resumo diário via Gemini ({e}). Usando gerador heurístico.")

        return self._heuristic_daily_digest(items, date_str)

    def _heuristic_daily_digest(self, items: List[Dict[str, Any]], date_str: str) -> Dict[str, Any]:
        """Motor heurístico para gerar o resumo diário se a API de IA estiver indisponível."""
        if not items:
            return {
                "titulo_digest": f"Fechamento Fiscal Diário • {date_str}",
                "panorama_geral": "Nenhuma alteração fiscal crítica ou regra de validação impeditiva foi publicada hoje.",
                "principais_mudancas": ["Portais fiscais operando em estabilidade sem impactos imediatos nas emissões de notas."],
                "atencao_desenvolvedores": "Manter rotinas padrão de monitoramento e testes.",
                "prazos_urgentes": "Sem prazos emergenciais reportados hoje.",
                "nivel_atencao_geral": "INFORMATIVO"
            }

        mudancas = []
        for it in items[:5]:
            title = it.get("title", "Comunicado Fiscal")
            mudancas.append(f"• {title}")

        return {
            "titulo_digest": f"Fechamento Fiscal Diário • {date_str}",
            "panorama_geral": f"Foram registradas {len(items)} publicação(ões) fiscal(is) relevante(s) nos portais governamentais hoje.",
            "principais_mudancas": mudancas,
            "atencao_desenvolvedores": "Revisar possíveis adequações de leiaute, tags XML e regras de validação apontadas nas publicações.",
            "prazos_urgentes": "Verificar os prazos individuais detalhados nos alertas de cada publicação.",
            "nivel_atencao_geral": "ALTO" if any(it.get("impact_level") == "ALTO" for it in items) else "MEDIO"
        }

    @staticmethod
    def _normalize_parsed_fields(parsed: Dict[str, Any]) -> None:
        """Garante que listas ou dicionários retornados pela IA sejam convertidos em strings limpas para o Discord."""
        for field in ["regimes_afetados", "novos_campos_tags", "regras_rejeicao"]:
            val = parsed.get(field)
            if isinstance(val, list):
                parsed[field] = ", ".join(str(x) for x in val)
            elif isinstance(val, dict):
                parsed[field] = " | ".join(f"{k}: {v}" for k, v in val.items())

        prazos_val = parsed.get("prazos")
        if isinstance(prazos_val, dict):
            parsed["prazos"] = " | ".join(f"{k.capitalize()}: {v}" for k, v in prazos_val.items())
        elif isinstance(prazos_val, list):
            parsed["prazos"] = ", ".join(str(x) for x in prazos_val)

    @staticmethod
    def _clean_json(raw_text: str) -> str:
        """Limpa blocos de código markdown como ```json ... ``` se existirem."""
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def _heuristic_fallback(
        self,
        source_name: str,
        title: str,
        content_text: str,
        url: str
    ) -> Dict[str, Any]:
        """
        Motor heurístico avançado para gerar a síntese fiscal caso a IA não esteja disponível.
        Usa expressões regulares para identificar tags XML, números de NT, prazos e impactos.
        """
        combined = f"{title}\n{content_text}".lower()

        # 1. Determina prefixo e título formatado
        prefix = "[GERAL]"
        if "nfe" in combined or "nfc-e" in combined or "nota fiscal eletrônica" in combined or "sefaz" in combined:
            prefix = "[NF-e / NFC-e]"
        elif "nfse" in combined or "nfs-e" in combined or "serviço" in combined or "abrasf" in combined:
            prefix = "[NFS-e Nacional]"
        elif any(k in combined for k in ["pis", "cofins", "ipi", "sped", "efd", "ecf", "reforma tributária", "ibs", "cbs"]):
            prefix = "[TRIBUTÁRIO / SPED]"
        elif "acbr" in source_name.lower():
            prefix = "[COMUNIDADE DEV]"

        titulo_formatado = f"{prefix} {title}"

        # 2. Resumo Executivo
        clean_lead = re.sub(r"\s+", " ", content_text).strip()
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", clean_lead) if len(s.strip()) > 15]
        resumo_executivo = ". ".join(sentences[:2])
        if not resumo_executivo:
            resumo_executivo = f"Publicação detectada no portal fiscal {source_name}. Verifique os detalhes técnicos oficiais."
        elif not resumo_executivo.endswith("."):
            resumo_executivo += "."

        # 3. Regimes afetados
        regimes = []
        if "simples nacional" in combined:
            regimes.append("Simples Nacional")
        if "mei" in combined or "microempreendedor" in combined:
            regimes.append("MEI")
        if "lucro presumido" in combined:
            regimes.append("Lucro Presumido")
        if "lucro real" in combined:
            regimes.append("Lucro Real")
        
        regimes_afetados = ", ".join(regimes) if regimes else "Empresas e emissores do documento fiscal em questão"

        # 4. Tags / Campos XML
        xml_tags = re.findall(r"<[a-zA-Z0-9_]+>", content_text)
        if xml_tags:
            novos_campos_tags = f"Tags identificadas: {', '.join(sorted(set(xml_tags))[:5])}"
        elif "schema" in combined or "xsd" in combined:
            novos_campos_tags = "Pacote de Schemas XML (.xsd) atualizado para o documento fiscal."
        else:
            novos_campos_tags = "Não foram mencionadas alterações diretas de tags XML no texto preliminar."

        # 5. Regras de Rejeição
        rejeicoes = re.findall(r"(?:rejeição|rejeicao)\s*(?:n[º°])?\s*(\d{3,4})", combined)
        if rejeicoes:
            regras_rejeicao = f"Atenção para novas regras ou rejeições: {', '.join(set(rejeicoes))}"
        elif any(w in combined for w in ["rejeição", "rejeicao", "validação", "validacao"]):
            regras_rejeicao = "Contém novas regras de validação ou adequação de consistência."
        else:
            regras_rejeicao = "Nenhuma nova regra de rejeição impeditiva reportada."

        # 6. Prazos
        dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", content_text)
        if dates:
            prazos = f"Datas identificadas na publicação: {', '.join(dates[:3])}"
        else:
            prazos = "Vigência imediata ou conforme data de publicação no portal."

        # 7. Nível de Urgência
        if any(w in combined for w in ["rejeição", "rejeicao", "urgente", "indisponibilidade", "bloqueio", "imediato"]):
            nivel_urgencia = "ALTO"
        elif any(w in combined for w in ["nota técnica", "nt 20", "schema", "leiaute", "layout", "obrigatório"]):
            nivel_urgencia = "MEDIO"
        else:
            nivel_urgencia = "INFORMATIVO"

        return {
            "titulo_formatado": titulo_formatado,
            "resumo_executivo": resumo_executivo,
            "regimes_afetados": regimes_afetados,
            "novos_campos_tags": novos_campos_tags,
            "regras_rejeicao": regras_rejeicao,
            "prazos": prazos,
            "nivel_urgencia": nivel_urgencia
        }
