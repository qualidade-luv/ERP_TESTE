import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import os
import numpy as np
import io
import unicodedata
from openpyxl import load_workbook
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import traceback
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import time
import json
from datetime import datetime, timedelta, date, time as dt_time
from functools import wraps
import plotly.express as px
import plotly.graph_objects as go

# ======================
# FUNÇÃO PARA LIMPAR CACHE E RECARREGAR
# ======================
def limpar_cache_e_recarregar():
    """
    Limpa todo o cache do Streamlit e força o recarregamento dos dados
    """
    try:
        # Limpa o cache de dados
        st.cache_data.clear()
        
        # Limpa o cache de recursos
        st.cache_resource.clear()
        
        # Limpa arquivos de cache locais, se existirem
        arquivos_cache = [
            "cache_prensados.pkl",
            "cache_sopro.pkl", 
            "cache_tempera.pkl",
            "cache_ar.pkl",
            "cache_rm.pkl",
            "cache_preventiva.pkl",
            "cache_habilidades.pkl",
            "notificacoes_enviadas.json"
        ]
        
        for arquivo in arquivos_cache:
            try:
                if os.path.exists(arquivo):
                    os.remove(arquivo)
                    print(f"🗑️ Cache removido: {arquivo}")
            except:
                pass
        
        # Reset dos timestamps de atualização
        if "ultima_verificacao_popup" in st.session_state:
            st.session_state.ultima_verificacao_popup = datetime.now() - timedelta(minutes=5)
        
        if "ultima_atualizacao_mensagem" in st.session_state:
            st.session_state.ultima_atualizacao_mensagem = datetime.now() - timedelta(minutes=5)
        
        return True, "✅ Cache limpo com sucesso! Recarregando dados..."
        
    except Exception as e:
        return False, f"❌ Erro ao limpar cache: {str(e)}"

# ======================
# DECORATOR DE RETRY PARA ERROS DE QUOTA (429)
# ======================
def retry_on_quota(max_retries=3, delay=5):
    """Decorator para tentar novamente quando ocorrer erro de quota (429)"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "429" in str(e) or "Quota exceeded" in str(e):
                        if attempt < max_retries - 1:
                            wait = delay * (attempt + 1)
                            st.warning(f"Limite de requisições atingido. Tentando novamente em {wait}s...")
                            time.sleep(wait)
                            continue
                    raise
            return None
        return wrapper
    return decorator

# ======================
# SISTEMA DE NOTIFICAÇÕES - POPUP SIMPLES (APENAS REGISTROS NOVOS DO DIA ATUAL)
# ======================

# Arquivo para armazenar IDs dos registros já notificados
ARQUIVO_NOTIFICACOES = "notificacoes_enviadas.json"

class SistemaNotificacao:
    """Sistema simples de notificações - só mostra registros novos do dia atual"""
    
    def __init__(self):
        self.notificacoes_enviadas = self.carregar_notificacoes()
    
    def carregar_notificacoes(self):
        """Carrega lista de registros já notificados"""
        try:
            if os.path.exists(ARQUIVO_NOTIFICACOES):
                with open(ARQUIVO_NOTIFICACOES, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    if isinstance(dados, dict) and 'ar' in dados and 'rm' in dados:
                        return dados
        except:
            pass
        return {"ar": [], "rm": [], "data_ultima_limpeza": ""}
    
    def salvar_notificacoes(self):
        """Salva lista de registros notificados"""
        try:
            with open(ARQUIVO_NOTIFICACOES, 'w', encoding='utf-8') as f:
                json.dump(self.notificacoes_enviadas, f, ensure_ascii=False)
        except:
            pass
    
    def limpar_notificacoes_antigas(self):
        """Remove notificações de dias anteriores (executa uma vez por dia)"""
        hoje = datetime.now().strftime("%Y-%m-%d")
        if self.notificacoes_enviadas.get("data_ultima_limpeza") != hoje:
            self.notificacoes_enviadas["ar"] = []
            self.notificacoes_enviadas["rm"] = []
            self.notificacoes_enviadas["data_ultima_limpeza"] = hoje
            self.salvar_notificacoes()
    
    def verificar_novos_registros(self):
        """
        Verifica apenas registros do dia atual que ainda NÃO foram notificados.
        Retorna listas de novos ARs e RMs.
        """
        hoje = datetime.now().date()
        novos_ar = []
        novos_rm = []
        
        # Limpar registros antigos (uma vez por dia)
        self.limpar_notificacoes_antigas()
        
        # ===== VERIFICAR NOVOS AVISOS DE REJEIÇÃO (AR) =====
        try:
            registros_ar = carregar_registros_ar_sem_cache()
            if registros_ar:
                for registro in registros_ar:
                    if registro.data and registro.data.date() == hoje:
                        if str(registro.numero) not in self.notificacoes_enviadas["ar"]:
                            novos_ar.append({
                                "numero": registro.numero,
                                "data": registro.data.strftime("%d/%m/%Y"),
                                "hora": registro.hora,
                                "referencia": registro.referencia[:35] + "..." if len(registro.referencia) > 35 else registro.referencia,
                                "emissor": registro.emissor,
                                "tipo": "AR"
                            })
                            self.notificacoes_enviadas["ar"].append(str(registro.numero))
        except Exception as e:
            pass
        
        # ===== VERIFICAR NOVAS REQUISIÇÕES DE MANUTENÇÃO (RM) =====
        try:
            registros_rm = carregar_registros_rm_sem_cache()
            if registros_rm:
                for registro in registros_rm:
                    if registro.data and registro.data.date() == hoje:
                        if str(registro.id) not in self.notificacoes_enviadas["rm"]:
                            novos_rm.append({
                                "id": registro.id,
                                "data": registro.data.strftime("%d/%m/%Y"),
                                "hora": registro.hora,
                                "equipamento": registro.equipamento[:35] + "..." if len(registro.equipamento) > 35 else registro.equipamento,
                                "emissor": registro.emissor,
                                "tipo": "RM"
                            })
                            self.notificacoes_enviadas["rm"].append(str(registro.id))
        except Exception as e:
            pass
        
        if novos_ar or novos_rm:
            self.salvar_notificacoes()
        
        return novos_ar, novos_rm

# Instância global do sistema de notificações
sistema_notificacao = SistemaNotificacao()

# ======================
# CSS PARA POPUP SIMPLES (BALÃO INFERIOR DIREITO)
# ======================
NOTIFICACAO_CSS = """
<style>
/* Container de popups - canto inferior direito */
.popup-container {
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 99999;
    display: flex;
    flex-direction: column;
    gap: 10px;
    pointer-events: none;
}

/* Estilo do popup */
.simple-popup {
    pointer-events: auto;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    width: 280px;
    overflow: hidden;
    animation: slideIn 0.3s ease-out;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

@keyframes slideIn {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

@keyframes fadeOut {
    from {
        opacity: 1;
        transform: translateX(0);
    }
    to {
        opacity: 0;
        transform: translateX(100%);
        visibility: hidden;
    }
}

.simple-popup.fade-out {
    animation: fadeOut 0.3s ease-out forwards;
}

/* Header do popup */
.popup-header {
    padding: 8px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 2px solid;
}

.popup-title {
    font-weight: 600;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
}

.popup-close {
    cursor: pointer;
    font-size: 16px;
    font-weight: bold;
    color: #9ca3af;
    background: none;
    border: none;
    padding: 0 4px;
    line-height: 1;
}

.popup-close:hover {
    color: #ef4444;
}

/* Corpo do popup */
.popup-body {
    padding: 10px 12px;
    font-size: 11px;
}

.popup-line {
    margin-bottom: 6px;
    display: flex;
    gap: 8px;
}

.popup-label {
    font-weight: 600;
    color: #6b7280;
    min-width: 55px;
    font-size: 10px;
}

.popup-value {
    color: #1f2937;
    word-break: break-word;
    flex: 1;
    font-size: 11px;
}

/* Footer */
.popup-footer {
    background: #f9fafb;
    padding: 5px 12px;
    font-size: 9px;
    color: #9ca3af;
    text-align: right;
    border-top: 1px solid #e5e7eb;
}
</style>

<script>
function fecharPopup(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.add('fade-out');
        setTimeout(() => {
            if (element.parentNode) element.remove();
        }, 300);
    }
}
</script>
"""

def gerar_popup_html(notificacao):
    """Gera o HTML do popup para uma notificação"""
    tipo = notificacao["tipo"]
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    if tipo == "AR":
        cor = "#dc2626"
        icone = "📋"
        titulo = "NOVO AVISO DE REJEIÇÃO"
        popup_id = f"popup_ar_{notificacao['numero']}_{timestamp.replace(':', '')}"
        
        html = f'''
        <div id="{popup_id}" class="simple-popup">
            <div class="popup-header" style="border-bottom-color: {cor};">
                <div class="popup-title" style="color: {cor};">
                    <span>{icone}</span> {titulo}
                </div>
                <button class="popup-close" onclick="fecharPopup('{popup_id}')">✕</button>
            </div>
            <div class="popup-body">
                <div class="popup-line">
                    <span class="popup-label">Nº:</span>
                    <span class="popup-value">{notificacao['numero']}</span>
                </div>
                <div class="popup-line">
                    <span class="popup-label">Ref:</span>
                    <span class="popup-value">{notificacao['referencia']}</span>
                </div>
                <div class="popup-line">
                    <span class="popup-label">Emissor:</span>
                    <span class="popup-value">{notificacao['emissor']}</span>
                </div>
                <div class="popup-line">
                    <span class="popup-label">Hora:</span>
                    <span class="popup-value">{notificacao['hora']}</span>
                </div>
            </div>
            <div class="popup-footer">
                {timestamp}
            </div>
        </div>
        '''
    else:
        cor = "#10b981"
        icone = "🔧"
        titulo = "NOVA REQUISIÇÃO DE MANUTENÇÃO"
        popup_id = f"popup_rm_{notificacao['id']}_{timestamp.replace(':', '')}"
        
        html = f'''
        <div id="{popup_id}" class="simple-popup">
            <div class="popup-header" style="border-bottom-color: {cor};">
                <div class="popup-title" style="color: {cor};">
                    <span>{icone}</span> {titulo}
                </div>
                <button class="popup-close" onclick="fecharPopup('{popup_id}')">✕</button>
            </div>
            <div class="popup-body">
                <div class="popup-line">
                    <span class="popup-label">ID:</span>
                    <span class="popup-value">{notificacao['id']}</span>
                </div>
                <div class="popup-line">
                    <span class="popup-label">Equip:</span>
                    <span class="popup-value">{notificacao['equipamento']}</span>
                </div>
                <div class="popup-line">
                    <span class="popup-label">Emissor:</span>
                    <span class="popup-value">{notificacao['emissor']}</span>
                </div>
                <div class="popup-line">
                    <span class="popup-label">Hora:</span>
                    <span class="popup-value">{notificacao['hora']}</span>
                </div>
            </div>
            <div class="popup-footer">
                {timestamp}
            </div>
        </div>
        '''
    
    return html, popup_id

# Controlar última verificação de popups (para não exceder quota)
if "ultima_verificacao_popup" not in st.session_state:
    st.session_state.ultima_verificacao_popup = datetime.now()

def verificar_e_exibir_popups():
    """Função principal que verifica novos registros e exibe popups, limitada a cada 60 segundos"""
    aba_atual = st.session_state.get("aba_selecionada", "")
    if aba_atual in ["AVISO DE REJEIÇÃO", "REQUISIÇÃO MANUTENÇÃO"]:
        return
    
    agora = datetime.now()
    if (agora - st.session_state.ultima_verificacao_popup).total_seconds() < 60:
        return  # verifica no máximo a cada 60 segundos
    
    st.session_state.ultima_verificacao_popup = agora
    
    novos_ar, novos_rm = sistema_notificacao.verificar_novos_registros()
    
    todas_notificacoes = []
    for notif in novos_ar:
        todas_notificacoes.append(notif)
    for notif in novos_rm:
        todas_notificacoes.append(notif)
    
    if todas_notificacoes:
        if "popups_para_exibir" not in st.session_state:
            st.session_state.popups_para_exibir = []
        
        for notif in todas_notificacoes:
            chave = f"{notif['tipo']}_{notif.get('numero', notif.get('id'))}"
            if chave not in [p.get("chave") for p in st.session_state.popups_para_exibir]:
                notif["chave"] = chave
                st.session_state.popups_para_exibir.append(notif)
        
        st.rerun()

def renderizar_popups_pendentes():
    """Renderiza todos os popups pendentes no container inferior direito"""
    if "popups_para_exibir" in st.session_state and st.session_state.popups_para_exibir:
        st.markdown('<div class="popup-container" id="popup-container">', unsafe_allow_html=True)
        
        for notif in st.session_state.popups_para_exibir.copy():
            html_popup, _ = gerar_popup_html(notif)
            st.markdown(html_popup, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        st.session_state.popups_para_exibir = []

# ======================
# CSS PARA A FAIXA DE ROLAGEM (MARQUEE)
# ======================
MARQUEE_CSS = """
<style>
/* Container da faixa de rolagem fixa no rodapé */
.marquee-container {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(90deg, #1a1a2e 0%, #16213e 50%, #1a1a2e 100%);
    color: #ffd700;
    padding: 10px 0;
    z-index: 9998;
    border-top: 2px solid #ffd700;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.3);
    font-family: 'JetBrains Mono', monospace;
    overflow: hidden;
    white-space: nowrap;
    backdrop-filter: blur(5px);
}

/* Efeito de rolagem - da DIREITA para ESQUERDA */
.marquee-content {
    display: inline-block;
    animation: scrollMarquee 45s linear infinite;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 1px;
    /* Começa fora da tela pela DIREITA */
    transform: translateX(100%);
}

.marquee-content span {
    display: inline-block;
    margin-right: 100px;
}

/* Animação de rolagem - DA DIREITA PARA ESQUERDA */
@keyframes scrollMarquee {
    0% {
        transform: translateX(100%);  /* Começa completamente fora da tela pela DIREITA */
    }
    100% {
        transform: translateX(-100%);  /* Sai completamente pela ESQUERDA */
    }
}

/* Pausar animação ao passar o mouse */
.marquee-container:hover .marquee-content {
    animation-play-state: paused;
}

/* Ícone decorativo */
.marquee-icon {
    display: inline-block;
    margin: 0 20px;
    font-size: 16px;
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.7; transform: scale(1.1); }
}

/* Responsivo para mobile */
@media (max-width: 768px) {
    .marquee-content {
        font-size: 11px;
        animation-duration: 35s;
    }
    .marquee-container {
        padding: 6px 0;
    }
}

/* Espaçador para não sobrepor conteúdo */
.marquee-spacer {
    height: 55px;
}
</style>

<script>
function updateMarqueeMessage(newMessage) {
    const marqueeElement = document.getElementById('marquee-content');
    if (marqueeElement) {
        marqueeElement.innerHTML = '<span>✨ ' + newMessage + ' ✨</span>';
    }
}
</script>
"""

# ======================
# CONFIGURAÇÕES
# ======================
ID_PLANILHA_PRENSADOS_SOPRO = '1Hjy4UGtgwIPJgqmcv46LyXNWOrYk_oeJWWV5vlfKF2k'
ID_PLANILHA_TEMPERA = '1GJegUHosaQLEJVMCH6QVuKjSjuaxrWkgzNEr9vM5Yio'

ID_PLANILHA_AR = '12pz6EE1KDo41szDyGEyTyK27mAOb9F1FyU77_M1kL0o'
ABA_AR = 'AR'
ABA_RM = 'RM'
EMAIL_SERVICE_ACCOUNT = 'script-atualizacao@dashboard-gerencial-492613.iam.gserviceaccount.com'

PRACAS_NAO_SOPRO = ['GIL', 'GILSIMAR', 'ED CARLOS', 'EDI CARLOS', 'ROBÔ 2', 'ROBÔ-2', 'ROBÔ', 'ROBO']

ABAS = {
    'PRENSADOS': 'TRS_INDUSTRIAL',
    'SOPRO': 'TRS_SOPRO',
    'TÊMPERA': 'TRS_TEMPERA',
    'AVISO DE REJEIÇÃO': 'AR',
    'REQUISIÇÃO MANUTENÇÃO': 'RM',
    'FECHAMENTO TURNO': 'FT',
    'MANUTENÇÃO PREVENTIVA': 'MP',
    'MAPEAMENTO DE HABILIDADES': 'MH',   # <-- CORRIGIDO: antes era 'MP'
    'FERRAMENTARIA': 'FM',
    'PRÊMIO PRENSADOS': 'PP',
    'REPASSES DE PRODUÇÃO': 'RP'         # <-- NOVO
}

CAMINHO_PDF_AR = r"\\srv-luvidarte\dados\DOC\Engenharia_Luvidarte\SGQ - LUVIDARTE - ALTERADAS\0-AVISO DE REJEIÇÃO\1-PDF"
CAMINHO_PDF_RELATORIO_AR = r"\\srv-luvidarte\dados\DOC\Engenharia_Luvidarte\SGQ - LUVIDARTE - ALTERADAS\0-AVISO DE REJEIÇÃO\2-PDF"

# ID da planilha PREVENTIVA
ID_PLANILHA_PREVENTIVA = '1FOh8OT5NaqPV3OWZziQLlclwJdSnIdd7qkS1KbbUS40'
ABA_PREVENTIVA = 'PREVENTIVA'
ABA_CADASTRO_PREVENTIVA = 'CADASTRO'

EMAIL_CONFIG_AR = {
    "usuario": "erp@luvidarte.com.br",
    "senha": "Qualidade123#",
    "destinatarios": ["producao@luvidarte.com.br", "engenharia@luvidarte.com.br", 
                     "qualidade@luvidarte.com.br", "qualidade2@luvidarte.com.br"],
    "smtp_server": "email-ssl.com.br",
    "smtp_port": 465
}

OPCOES_DECISAO_AR = ["APROVADO CONDICIONAL", "REPROVADO", "EM ANÁLISE"]
OPCOES_STATUS_AR = ["ABERTO", "FINALIZADO", "NÃO RESPONDIDA"]
OPCOES_TURNO_AR = ["Manhã", "Tarde", "Noite"]

for caminho in [CAMINHO_PDF_AR, CAMINHO_PDF_RELATORIO_AR]:
    try:
        os.makedirs(caminho, exist_ok=True)
    except:
        pass

# ======================
# TEMA VISUAL - CLARO (LIGHT MODE)
# ======================
THEME = {
    'bg_primary':     '#F5F7FA',
    'bg_card':        '#FFFFFF',
    'bg_card2':       '#F8F9FC',
    'accent_cyan':    '#0078D4',
    'accent_lime':    '#107C10',
    'accent_orange':  '#E86C2C',
    'accent_yellow':  '#FFB900',
    'accent_red':     '#E81123',
    'accent_purple':  '#6B46C1',
    'text_primary':   '#1E1E1E',
    'text_muted':     '#605E5C',
    'border':         '#D1D1D1',
    'border_bright':  '#C0C0C0',
    'grid':           '#E0E0E0',
}

st.set_page_config(
    page_title="TRS Dashboard",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)
# ==================================================================================================
# SISTEMA DE LOGIN - SESSÃO E AUTENTICAÇÃO
# ==================================================================================================

# Importações adicionais para o login
import hashlib
from datetime import datetime, timedelta

# ======================
# CONFIGURAÇÕES DE SEGURANÇA
# ======================
SESSAO_EXPIRACAO_MINUTOS = 10  # Tempo de expiração da sessão em minutos

# ======================
# FUNÇÃO DE HASH PARA SENHAS
# ======================
def hash_senha(senha: str) -> str:
    """Cria um hash seguro da senha usando SHA-256"""
    return hashlib.sha256(senha.encode()).hexdigest()

# ======================
# ======================
# FUNÇÃO DE LOGIN - VERIFICA CREDENCIAIS NA PLANILHA (SENHAS EM TEXTO PURO)
# ======================
def verificar_login(user: str, senha: str) -> tuple:
    """
    Verifica as credenciais na planilha LOGIN
    As senhas são armazenadas em texto puro (NÃO HASH)
    Retorna: (sucesso, nivel, setor, status, mensagem)
    """
    try:
        # Obtém cliente do Google Sheets
        client = get_gspread_client()
        if client is None:
            return False, None, None, None, "❌ Erro de conexão com o banco de dados"
        
        # Acessa a planilha de LOGIN
        spreadsheet = client.open_by_key('1_54o1YFfG8GxqBJQ2stwWNpeQptJQHUc4SSzT4gV1QM')
        sheet = spreadsheet.worksheet('LOGIN')
        
        # Lê todos os dados
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return False, None, None, None, "❌ Nenhum usuário cadastrado"
        
        # Procura o usuário
        for row in todos_dados[1:]:  # Pula cabeçalho
            if len(row) < 6:
                continue
                
            id_user = row[0].strip()
            usuario = row[1].strip()
            senha_armazenada = row[2].strip()  # Senha em texto puro
            nivel = row[3].strip()
            setor = row[4].strip()
            status = row[5].strip().upper()
            
            # DEBUG: Mostra o que está sendo verificado
            print(f"Verificando: Usuário='{usuario}', Senha armazenada='{senha_armazenada}'")
            
            # Verifica se o usuário existe (case insensitive)
            if usuario.lower() == user.lower():
                # Verifica se o status é ATIVO
                if status != "ATIVO":
                    return False, None, None, None, f"❌ Usuário bloqueado. Status: {status}"
                
                # Comparação direta de senha (texto puro)
                if senha == senha_armazenada:
                    return True, nivel, setor, status, "✅ Login realizado com sucesso!"
                else:
                    return False, None, None, None, "❌ Senha incorreta!"
        
        return False, None, None, None, "❌ Usuário não encontrado!"
        
    except Exception as e:
        return False, None, None, None, f"❌ Erro ao verificar login: {str(e)}"

# ======================
# FUNÇÃO PARA INICIALIZAR SESSÃO
# ======================
def inicializar_sessao():
    """Inicializa a sessão do usuário"""
    st.session_state.logado = True
    st.session_state.usuario = st.session_state.user_input
    st.session_state.nivel = st.session_state.nivel_usuario
    st.session_state.setor = st.session_state.setor_usuario
    st.session_state.tempo_login = datetime.now()
    st.session_state.ultima_atividade = datetime.now()

# ======================
# FUNÇÃO PARA VERIFICAR EXPIRAÇÃO DA SESSÃO
# ======================
def verificar_expiracao_sessao():
    """
    Verifica se a sessão expirou.
    Retorna True se expirou, False se ainda está ativa.
    """
    if 'logado' not in st.session_state or not st.session_state.logado:
        return True
    
    if 'ultima_atividade' not in st.session_state:
        return True
    
    tempo_decorrido = (datetime.now() - st.session_state.ultima_atividade).total_seconds()
    tempo_limite = SESSAO_EXPIRACAO_MINUTOS * 60  # Converte para segundos
    
    if tempo_decorrido > tempo_limite:
        # Sessão expirada
        st.session_state.logado = False
        st.session_state.mensagem_logout = "⏰ Sessão expirada! Faça login novamente."
        return True
    
    return False

# ======================
# FUNÇÃO PARA ATUALIZAR ATIVIDADE
# ======================
def atualizar_atividade():
    """Atualiza o timestamp da última atividade"""
    if 'logado' in st.session_state and st.session_state.logado:
        st.session_state.ultima_atividade = datetime.now()

# ======================
# FUNÇÃO DE LOGOUT
# ======================
def fazer_logout():
    """Realiza o logout do usuário"""
    st.session_state.logado = False
    st.session_state.mensagem_logout = "👋 Logout realizado com sucesso!"
    if 'user_input' in st.session_state:
        st.session_state.user_input = ""
    if 'password_input' in st.session_state:
        st.session_state.password_input = ""
    # Limpa o cache para evitar dados antigos
    st.cache_data.clear()
    st.rerun()

# ======================
# CSS DA TELA DE LOGIN
# ======================
LOGIN_CSS = """
<style>
/* Reset e fundo */
.login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    font-family: 'Barlow', sans-serif;
    padding: 20px;
}

/* Card de login */
.login-card {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border-radius: 20px;
    padding: 50px 40px;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 25px 60px rgba(0,0,0,0.5);
    border: 1px solid rgba(255,255,255,0.1);
    animation: slideUp 0.6s ease-out;
}

@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Logo e título */
.login-logo {
    text-align: center;
    margin-bottom: 35px;
}

.login-logo .icon {
    font-size: 48px;
    display: block;
    margin-bottom: 10px;
}

.login-logo h1 {
    font-family: 'Rajdhani', sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: #1a1a2e;
    letter-spacing: 0.1em;
    margin: 0;
}

.login-logo .subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #6b7280;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-top: 5px;
}

/* Campos de input */
.login-field {
    margin-bottom: 20px;
}

.login-field label {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #4b5563;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 6px;
}

.login-field .input-wrapper {
    position: relative;
}

.login-field input {
    width: 100%;
    padding: 12px 15px;
    border: 2px solid #e5e7eb;
    border-radius: 10px;
    font-size: 15px;
    font-family: 'Barlow', sans-serif;
    color: #1a1a2e;
    background: #f9fafb;
    transition: all 0.3s ease;
    outline: none;
}

.login-field input:focus {
    border-color: #0078D4;
    background: white;
    box-shadow: 0 0 0 4px rgba(0,120,212,0.1);
}

.login-field input::placeholder {
    color: #9ca3af;
}

/* Botão de login */
.login-btn {
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #0078D4, #005a9e);
    color: white;
    border: none;
    border-radius: 10px;
    font-family: 'Rajdhani', sans-serif;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 0.3s ease;
    margin-top: 10px;
}

.login-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0,120,212,0.3);
}

.login-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
}

/* Mensagens de erro/sucesso */
.login-message {
    text-align: center;
    padding: 10px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    margin-top: 15px;
}

.login-message.error {
    background: #fee2e2;
    color: #dc2626;
    border: 1px solid #fecaca;
}

.login-message.success {
    background: #d1fae5;
    color: #059669;
    border: 1px solid #a7f3d0;
}

/* Rodapé */
.login-footer {
    text-align: center;
    margin-top: 25px;
    font-size: 11px;
    color: #9ca3af;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.05em;
}

/* Responsivo */
@media (max-width: 480px) {
    .login-card {
        padding: 30px 20px;
    }
    
    .login-logo h1 {
        font-size: 22px;
    }
}
</style>
"""

# ======================
# FUNÇÃO PARA RENDERIZAR TELA DE LOGIN
# ======================
def renderizar_tela_login():
    """Renderiza a tela de login profissional"""
    
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="login-container">
        <div class="login-card">
            <div class="login-logo">
                <span class="icon">⚙️</span>
                <h1>TRS DASHBOARD</h1>
                <div class="subtitle">Sistema de Gestão Industrial</div>
            </div>
    """, unsafe_allow_html=True)
    
    with st.form("login_form", clear_on_submit=False):
        # Campo de usuário
        st.markdown("""
        <div class="login-field">
            <label>👤 Usuário</label>
            <div class="input-wrapper">
        """, unsafe_allow_html=True)
        
        user = st.text_input(
            "Usuário",
            placeholder="Digite seu usuário",
            key="user_input",
            label_visibility="collapsed"
        )
        
        st.markdown("</div></div>", unsafe_allow_html=True)
        
        # Campo de senha
        st.markdown("""
        <div class="login-field">
            <label>🔒 Senha</label>
            <div class="input-wrapper">
        """, unsafe_allow_html=True)
        
        senha = st.text_input(
            "Senha",
            placeholder="Digite sua senha",
            type="password",
            key="password_input",
            label_visibility="collapsed"
        )
        
        st.markdown("</div></div>", unsafe_allow_html=True)
        
        # Mensagem de erro
        if 'mensagem_login' in st.session_state:
            tipo = st.session_state.mensagem_login.get('tipo', 'error')
            texto = st.session_state.mensagem_login.get('texto', '')
            if texto:
                st.markdown(f"""
                <div class="login-message {tipo}">
                    {texto}
                </div>
                """, unsafe_allow_html=True)
        
        # Botão de login
        submitted = st.form_submit_button(
            "🔐 ENTRAR",
            use_container_width=True,
            type="primary"
        )
        
        # Rodapé
        st.markdown("""
        <div class="login-footer">
            Sistema protegido © 2026 Luvidarte<br>
            <span style="font-size: 10px;">Versão 2.0</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div></div>", unsafe_allow_html=True)
    
    # Processar login
    if submitted:
        if not user:
            st.session_state.mensagem_login = {
                'tipo': 'error',
                'texto': '❌ Por favor, digite seu usuário!'
            }
            st.rerun()
        elif not senha:
            st.session_state.mensagem_login = {
                'tipo': 'error',
                'texto': '❌ Por favor, digite sua senha!'
            }
            st.rerun()
        else:
            # Verificar credenciais
            sucesso, nivel, setor, status, mensagem = verificar_login(user, senha)
            
            if sucesso:
                # Login bem-sucedido
                st.session_state.logado = True
                st.session_state.usuario = user
                st.session_state.nivel = nivel
                st.session_state.setor = setor
                st.session_state.nivel_usuario = nivel
                st.session_state.setor_usuario = setor
                st.session_state.tempo_login = datetime.now()
                st.session_state.ultima_atividade = datetime.now()
                
                st.session_state.mensagem_login = {
                    'tipo': 'success',
                    'texto': f'✅ Bem-vindo, {user}!'
                }
                
                st.rerun()
            else:
                st.session_state.mensagem_login = {
                    'tipo': 'error',
                    'texto': mensagem
                }
                st.rerun()

# ======================
# FUNÇÃO PARA VERIFICAR SE O USUÁRIO ESTÁ LOGADO
# ======================
def verificar_acesso():
    """
    Verifica se o usuário está logado e se a sessão é válida.
    Retorna True se tudo ok, False se precisa fazer login.
    """
    # Verifica se já está logado
    if 'logado' not in st.session_state:
        st.session_state.logado = False
    
    if not st.session_state.logado:
        renderizar_tela_login()
        return False
    
    # Verifica expiração da sessão (apenas para nível != 0)
    if st.session_state.get('nivel', '0') != '0':
        if verificar_expiracao_sessao():
            renderizar_tela_login()
            return False
    
    # Atualiza atividade a cada requisição
    atualizar_atividade()
    
    return True

# ======================
# FUNÇÃO PARA HORÁRIO BRASÍLIA
# ======================
def get_horario_brasilia():
    from datetime import timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    brasilia_offset = timezone(timedelta(hours=-3))
    agora_brasilia = utc_now.astimezone(brasilia_offset)
    return agora_brasilia.strftime('%d/%m/%Y %H:%M')
    
def get_horario_brasilia_obj():
    from datetime import timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    brasilia_offset = timezone(timedelta(hours=-3))
    return utc_now.astimezone(brasilia_offset)    

# ======================
# NOVA FUNÇÃO PARA CARREGAR MENSAGENS DA PLANILHA RECADOS (FAIXA DE ROLAGEM)
# ======================
ID_PLANILHA_RECADOS = '1R0V4HpmRNXAd2TxVv8c_dVVoc1tXDPBOVSFBX1JKHvs'
ABA_RECADOS = 'Rodapé'

@st.cache_data(ttl=240)  # Atualiza a cada 60 segundos
def carregar_mensagens_rodape():
    """
    Carrega as mensagens da planilha Recados - aba Rodapé.
    Filtra apenas mensagens da data atual.
    Retorna uma lista de mensagens [(texto, data), ...]
    """
    try:
        client = get_gspread_client()
        if client is None:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        # Abre a planilha de Recados
        spreadsheet = client.open_by_key(ID_PLANILHA_RECADOS)
        
        # Tenta pegar a aba "Rodapé"
        try:
            sheet = spreadsheet.worksheet(ABA_RECADOS)
        except Exception as e:
            print(f"Aba '{ABA_RECADOS}' não encontrada na planilha Recados. Erro: {e}")
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        # Lê todos os dados da planilha
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        # Cabeçalhos: primeira linha
        cabecalho = todos_dados[0]
        # Mapear índices das colunas
        idx_data = None
        idx_mensagem = None
        
        for i, col in enumerate(cabecalho):
            col_clean = str(col).strip().upper()
            if col_clean == 'DATA':
                idx_data = i
            elif col_clean == 'MENSAGEM':
                idx_mensagem = i
        
        if idx_data is None or idx_mensagem is None:
            print(f"Colunas 'DATA' ou 'MENSAGEM' não encontradas. Cabeçalho: {cabecalho}")
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        # Data atual para comparação - USANDO APENAS DATA LOCAL
        hoje = datetime.now().date()
        print(f"Data atual para filtro: {hoje}")  # Debug
        
        mensagens_validas = []
        
        # Processa as linhas (a partir da linha 1, índice 1)
        for row in todos_dados[1:]:
            # Verifica se a linha tem pelo menos as colunas necessárias
            if len(row) <= max(idx_data, idx_mensagem):
                continue
            
            data_str = row[idx_data].strip() if row[idx_data] else ""
            mensagem = row[idx_mensagem].strip() if idx_mensagem < len(row) else ""
            
            if not mensagem:
                continue
            
            print(f"Processando linha: data='{data_str}', mensagem='{mensagem[:50]}'")  # Debug
            
            # Converte a data da planilha para objeto date
            data_mensagem = None
            
            # Formato DD/MM/YYYY (prioritário para datas brasileiras)
            try:
                if '/' in data_str:
                    partes = data_str.split('/')
                    if len(partes) == 3:
                        dia = int(partes[0])
                        mes = int(partes[1])
                        ano = int(partes[2])
                        data_mensagem = date(ano, mes, dia)
                        print(f"  Convertido via DD/MM/YYYY: {data_mensagem}")
            except Exception as e:
                print(f"  Erro conversão DD/MM/YYYY: {e}")
            
            # Fallback para outros formatos
            if data_mensagem is None:
                formatos = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]
                for fmt in formatos:
                    try:
                        data_mensagem = datetime.strptime(data_str, fmt).date()
                        print(f"  Convertido via {fmt}: {data_mensagem}")
                        break
                    except:
                        continue
            
            # Se conseguiu converter a data e é igual a hoje, adiciona
            if data_mensagem:
                print(f"  Comparando: data_mensagem={data_mensagem} vs hoje={hoje} -> {data_mensagem == hoje}")
                if data_mensagem == hoje:
                    mensagens_validas.append(mensagem)
                    print(f"  ✅ MENSAGEM ADICIONADA: {mensagem[:50]}")
            else:
                print(f"  ❌ Falha ao converter data: '{data_str}'")
        
        # Se não encontrou nenhuma mensagem para hoje, retorna mensagem padrão
        if not mensagens_validas:
            print("Nenhuma mensagem válida encontrada para hoje")
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        print(f"Total de mensagens encontradas: {len(mensagens_validas)}")
        return mensagens_validas
        
    except Exception as e:
        print(f"Erro ao carregar mensagens da planilha Recados: {str(e)}")
        return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]


# ======================
# FUNÇÃO PARA RENDERIZAR A FAIXA DE ROLAGEM COM MÚLTIPLAS MENSAGENS
# ======================
def renderizar_faixa_rolagem():
    """Renderiza a faixa de rolagem no rodapé da página com múltiplas mensagens do dia"""
    
    # Carrega as mensagens da planilha Recados
    mensagens = carregar_mensagens_rodape()
    
    # Prepara o texto da faixa com indicadores se houver múltiplas mensagens
    total_mensagens = len(mensagens)
    
    if total_mensagens == 1:
        texto_faixa = f"✨ {mensagens[0]} ✨"
    else:
        # Cria uma lista com indicadores: "1/3 Mensagem 1  |  2/3 Mensagem 2  |  3/3 Mensagem 3"
        partes = []
        for i, msg in enumerate(mensagens, start=1):
            partes.append(f"[{i}/{total_mensagens}] {msg}")
        texto_faixa = " ✨ | ✨ ".join(partes)
        texto_faixa = f"✨ {texto_faixa} ✨"
    
    # Adiciona CSS
    st.markdown(MARQUEE_CSS, unsafe_allow_html=True)
    
    # Adiciona a faixa de rolagem
    st.markdown(f"""
    <div class="marquee-container">
        <div class="marquee-content" id="marquee-content">
            <span>{texto_faixa}</span>
        </div>
    </div>
    <div class="marquee-spacer"></div>
    """, unsafe_allow_html=True)
    
    # Força atualização periódica (a cada 60 segundos)
    if "ultima_atualizacao_mensagem" not in st.session_state:
        st.session_state.ultima_atualizacao_mensagem = datetime.now()
    
    agora = datetime.now()
    if (agora - st.session_state.ultima_atualizacao_mensagem).total_seconds() > 60:
        st.session_state.ultima_atualizacao_mensagem = agora
        # Limpa o cache para forçar recarregamento na próxima execução
        st.cache_data.clear()
        st.rerun()

# ======================
# FUNÇÕES AUXILIARES GLOBAIS
# ======================
def safe_float_tempera(val):
    if val is None or pd.isna(val):
        return 0.0
    try:
        val_str = str(val).strip()
        if val_str == '' or val_str == 'nan':
            return 0.0
        val_str = val_str.replace(',', '.')
        return float(val_str)
    except:
        return 0.0

@st.cache_resource
def get_gspread_client():
    """Retorna cliente autenticado do gspread (cacheado)"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if 'gcp_service_account' in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
    except:
        pass
    
    caminhos_credenciais = [
        r'C:\Users\elton\OneDrive\Documentos\dashboard-gerencial-492613-042470f98e27.json',
        r'C:\Users\elton\OneDrive\Desktop\dashboard-gerencial-492613-042470f98e27.json',
        r'C:\Users\elton\Desktop\dashboard-gerencial-492613-042470f98e27.json',
        r'C:\Users\elton\Downloads\dashboard-gerencial-492613-042470f98e27.json',
        r'dashboard-gerencial-492613-042470f98e27.json',
        r'\\srv-luvidarte\dados\DOC\Engenharia_Luvidarte\SGQ - LUVIDARTE - ALTERADAS\4-TRS\dashboard-gerencial-492613-042470f98e27.json',
    ]
    for caminho in caminhos_credenciais:
        try:
            if os.path.exists(caminho):
                creds = ServiceAccountCredentials.from_json_keyfile_name(caminho, scope)
                return gspread.authorize(creds)
        except:
            pass
    return None

def converter_numero_br(valor):
    if valor is None or pd.isna(valor):
        return 0.0
    try:
        if isinstance(valor, (int, float)):
            if valor > 1e9:
                return 0.0
            return float(valor)
        valor_str = str(valor).strip()
        if not valor_str:
            return 0.0
        if '%' in valor_str:
            valor_str = valor_str.replace('%', '')
        num_pontos = valor_str.count('.')
        num_virgulas = valor_str.count(',')
        if num_virgulas > 0:
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif num_pontos > 0:
            partes = valor_str.split('.')
            if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
                valor_str = valor_str.replace('.', '')
        valor_str = re.sub(r'[^\d.-]', '', valor_str)
        if not valor_str or valor_str == '.':
            return 0.0
        resultado = float(valor_str)
        if resultado > 10_000_000:
            return 0.0
        return resultado
    except:
        return 0.0

def converter_data_br(data_str):
    if data_str is None or pd.isna(data_str):
        return None
    try:
        if isinstance(data_str, (datetime, pd.Timestamp)):
            if data_str > datetime.now():
                return None
            return data_str
        data_str = str(data_str).strip()
        if not data_str:
            return None
        if '/' in data_str:
            partes = data_str.split('/')
            if len(partes) == 3:
                dia, mes, ano = int(partes[0]), int(partes[1]), int(partes[2])
                if ano < 100:
                    ano = 2000 + ano
                data_obj = datetime(ano, mes, dia)
                hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                if data_obj > hoje:
                    return None
                if data_obj.year < 2020:
                    return None
                return data_obj
        data_obj = pd.to_datetime(data_str, errors='coerce', dayfirst=True)
        if pd.notna(data_obj):
            hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if data_obj > hoje:
                return None
            return data_obj
        return None
    except:
        return None

def minutos_para_horas_str(minutos):
    if pd.isna(minutos) or minutos is None or minutos == 0:
        return "00:00"
    horas = int(minutos) // 60
    mins = int(minutos) % 60
    return f"{horas:02d}:{mins:02d}"

def converter_tempo_para_minutos(valor):
    if pd.isna(valor) or valor is None or valor == '':
        return 0
    if hasattr(valor, 'hour') and hasattr(valor, 'minute'):
        try:
            return valor.hour * 60 + valor.minute + (valor.second // 60 if hasattr(valor, 'second') else 0)
        except:
            pass
    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            return 0
        if ':' in valor:
            partes = valor.split(':')
            try:
                if len(partes) == 3:
                    h, m, s = map(int, partes)
                    return h * 60 + m + s // 60
                elif len(partes) == 2:
                    h, m = map(int, partes)
                    return h * 60 + m
            except:
                pass
        try:
            num = float(valor.replace(',', '.'))
            if num > 0:
                if num < 24:
                    return int(num * 60)
                else:
                    return int(num)
        except:
            pass
        return 0
    elif isinstance(valor, (int, float)):
        if valor > 0:
            if valor < 24:
                return int(valor * 60)
            elif valor > 100:
                return int(valor)
            else:
                return int(valor * 60)
    return 0

# ======================
# FUNÇÕES DE CARREGAMENTO DE DADOS (COM CACHE E RETRY)
# ======================
@retry_on_quota()
@st.cache_data(ttl=1200)
def carregar_dados_prensados():
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame()
        sheet = client.open_by_key(ID_PLANILHA_PRENSADOS_SOPRO).worksheet('TRS_INDUSTRIAL')
        todos_dados = sheet.get_all_values()
        if len(todos_dados) < 2:
            return pd.DataFrame()
        cabecalho = todos_dados[1]
        valores = todos_dados[2:]
        df = pd.DataFrame(valores, columns=cabecalho)
        df.columns = df.columns.str.strip().str.upper()
        if 'DATA' in df.columns:
            df['DATA'] = df['DATA'].apply(converter_data_br)
            df = df.dropna(subset=['DATA'])
        if 'APROVADO FINAL' in df.columns:
            df = df.rename(columns={'APROVADO FINAL': 'EMBALADO'})
        colunas_numericas = ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%', 'REFUGADO', 'BOQUETA']
        for col in colunas_numericas:
            if col in df.columns:
                df[col] = df[col].apply(converter_numero_br)
        df['ANO_MES'] = df['DATA'].dt.to_period('M').astype(str)
        df['DIA_SEMANA'] = df['DATA'].dt.day_name()
        df['SEMANA'] = df['DATA'].dt.isocalendar().week
        df['IS_SABADO'] = df['DATA'].dt.dayofweek == 5
        for col in df.columns:
            col_upper = str(col).upper()
            if 'ACERTO' in col_upper and 'MIN' not in col_upper:
                df['ACERTOS_MIN'] = df[col].apply(converter_tempo_para_minutos)
            if 'MANUT' in col_upper and 'MIN' not in col_upper:
                df['MANUT_MIN'] = df[col].apply(converter_tempo_para_minutos)
            if 'HORAS TOTAIS' in col_upper or 'HORA TOTAL' in col_upper:
                df['HORAS_TOTAIS_MIN'] = df[col].apply(converter_tempo_para_minutos)
        if 'ACERTOS_MIN' in df.columns:
            df['ACERTOS_MIN_AJUSTADO'] = df.apply(
                lambda row: max(0, row['ACERTOS_MIN'] - 165) if row['IS_SABADO'] else row['ACERTOS_MIN'], axis=1
            )
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de Prensados: {e}")
        return pd.DataFrame()

@retry_on_quota()
@st.cache_data(ttl=1200)
def carregar_dados_sopro():
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame()
        sheet = client.open_by_key(ID_PLANILHA_PRENSADOS_SOPRO).worksheet('TRS_SOPRO')
        todos_dados = sheet.get_all_values()
        if len(todos_dados) < 2:
            return pd.DataFrame()
        cabecalho = todos_dados[0]
        valores = todos_dados[1:]
        df = pd.DataFrame(valores, columns=cabecalho)
        df.columns = df.columns.str.strip().str.upper()
        if 'PRAÇA' in df.columns:
            df['PRAÇA_NORM'] = df['PRAÇA'].fillna('').astype(str).str.upper().str.strip()
            mascara = ~df['PRAÇA_NORM'].apply(
                lambda x: any(p in x for p in [p.upper() for p in PRACAS_NAO_SOPRO])
            )
            df = df[mascara].copy()
            df = df.drop(columns=['PRAÇA_NORM'])
        if 'DATA' in df.columns:
            df['DATA'] = df['DATA'].apply(converter_data_br)
            df = df.dropna(subset=['DATA'])
        for col in ['PRODUZIDO', 'APROVADO', 'TRS_BRUTO']:
            if col in df.columns:
                df[col] = df[col].apply(converter_numero_br)
        if 'PRODUZIDO' in df.columns and 'APROVADO' in df.columns:
            df['REFUGADO'] = (df['PRODUZIDO'] - df['APROVADO']).clip(lower=0)
        else:
            df['REFUGADO'] = 0
        df['ANO_MES'] = df['DATA'].dt.to_period('M').astype(str)
        return df
    except Exception:
        return pd.DataFrame()

@retry_on_quota()
@st.cache_data(ttl=1200)
def carregar_dados_tempera():
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame()
        sheet = client.open_by_key(ID_PLANILHA_TEMPERA).worksheet('TRS_TEMPERA')
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return pd.DataFrame()
        
        cabecalho = todos_dados[0]
        valores = todos_dados[1:]
        df = pd.DataFrame(valores, columns=cabecalho)
        colunas = list(df.columns)
        
        if len(colunas) >= 5:
            df = df.rename(columns={
                colunas[0]: 'PRODUCAO',
                colunas[1]: 'DATA_TEMP',
                colunas[2]: 'TURNO_TEMP',
                colunas[3]: 'PRODUTO',
                colunas[4]: 'GANCHEIRA'
            })
        
        if len(colunas) >= 8:
            df = df.rename(columns={
                colunas[5]: 'SUPERIOR',
                colunas[6]: 'MEIO',
                colunas[7]: 'INFERIOR'
            })
        
        if len(colunas) >= 11:
            df = df.rename(columns={
                colunas[8]: 'A1',
                colunas[9]: 'C1',
                colunas[10]: 'A2'
            })
        
        if len(colunas) >= 14:
            df = df.rename(columns={
                colunas[11]: 'C2',
                colunas[12]: 'A3',
                colunas[13]: 'C3'
            })
        
        if len(colunas) >= 17:
            df = df.rename(columns={
                colunas[14]: 'A4',
                colunas[15]: 'C4',
                colunas[16]: 'A5'
            })
        
        if len(colunas) >= 20:
            df = df.rename(columns={
                colunas[17]: 'C5',
                colunas[18]: 'A e B'
            })
        
        if 'DATA_TEMP' in df.columns:
            df['DATA'] = df['DATA_TEMP'].apply(converter_data_br)
        elif 'PRODUCAO' in df.columns:
            df['DATA'] = df['PRODUCAO'].apply(converter_data_br)
        
        if 'DATA' in df.columns:
            df = df.dropna(subset=['DATA'])
        
        colunas_numericas = ['SUPERIOR', 'MEIO', 'INFERIOR', 'A1', 'C1', 'A2', 'C2', 'A3', 'C3', 'A4', 'C4', 'A5', 'C5', 'A e B']
        
        for col in colunas_numericas:
            if col in df.columns:
                df[col] = df[col].apply(safe_float_tempera)
        
        if 'C2' in df.columns:
            def converter_tempo_c2(val):
                if pd.isna(val) or val == 0:
                    return 0
                if val <= 1:
                    return val * 100
                elif val <= 10:
                    return val * 10
                else:
                    return val
            df['C2'] = df['C2'].apply(converter_tempo_c2)
        
        colunas_posicoes_validas = []
        for col in df.columns:
            try:
                num = int(str(col).strip())
                if 19 <= num <= 70:
                    colunas_posicoes_validas.append(col)
            except:
                pass
        
        df['TOTAL_PECAS'] = 40
        df['APROVADO'] = 40
        df['TOTAL_DEFEITOS'] = 0
        df['IS_CRITICO'] = False
        
        MAPEAMENTO_DEFEITOS = {
            1: 'Estourou após furar',
            2: 'Quebra no resfriamento',
            3: 'Quebra teste impacto',
            4: 'Furada e não fraturou',
            5: 'Quebra de quarentena',
            6: 'Ovalizada'
        }
        CODIGOS_DEFEITO_REAIS = [2, 3, 4, 5, 6]
        
        for codigo, nome in MAPEAMENTO_DEFEITOS.items():
            nome_clean = nome.upper().replace(' ', '_').replace('Ç', 'C').replace('Ã', 'A').replace('Á', 'A').replace('Ó', 'O')
            df[f'QTD_{nome_clean}'] = 0
        
        for idx, row in df.iterrows():
            defeitos_contagem = {codigo: 0 for codigo in MAPEAMENTO_DEFEITOS.keys()}
            
            for col in colunas_posicoes_validas:
                try:
                    val = row[col]
                    if pd.notna(val) and str(val).strip():
                        codigo = int(float(str(val).strip()))
                        if codigo in MAPEAMENTO_DEFEITOS:
                            defeitos_contagem[codigo] += 1
                except:
                    pass
            
            total_defeitos_reais = sum(defeitos_contagem.get(cod, 0) for cod in CODIGOS_DEFEITO_REAIS)
            aprovadas = 40 - total_defeitos_reais
            
            df.at[idx, 'APROVADO'] = aprovadas
            df.at[idx, 'TOTAL_DEFEITOS'] = total_defeitos_reais
            df.at[idx, 'TRS (%)'] = (aprovadas / 40 * 100) if 40 > 0 else 0
            
            is_critico = False
            if defeitos_contagem.get(4, 0) >= 1:
                is_critico = True
            if defeitos_contagem.get(3, 0) > 2:
                is_critico = True
            df.at[idx, 'IS_CRITICO'] = is_critico
            
            for codigo, nome in MAPEAMENTO_DEFEITOS.items():
                nome_clean = nome.upper().replace(' ', '_').replace('Ç', 'C').replace('Ã', 'A').replace('Á', 'A').replace('Ó', 'O')
                col_nome = f'QTD_{nome_clean}'
                if col_nome in df.columns:
                    df.at[idx, col_nome] = defeitos_contagem.get(codigo, 0)
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

# ======================
# ======================
# FUNÇÕES DO SISTEMA AR (AVISO DE REJEIÇÃO) - COM BIBLIOTECA DE DEFEITOS
# ======================

# ======================
# BIBLIOTECA DE DEFEITOS CONHECIDOS
# ======================
ID_PLANILHA_BIBLIOTECA = '1YbtwIajV3WpQB-fz3CqaZ69UNDPgcYyzjJw5Pyy1JGU'
ABA_BIBLIOTECA = 'BIBLIOTECA'

@st.cache_data(ttl=3600)  # Cache de 1 hora
def carregar_biblioteca_defeitos():
    """
    Carrega a biblioteca de defeitos conhecidos do Google Sheets
    Retorna um dicionário com defeito -> {sugestao, direcionamento}
    """
    try:
        client = get_gspread_client()
        if client is None:
            return {}
        
        spreadsheet = client.open_by_key(ID_PLANILHA_BIBLIOTECA)
        sheet = spreadsheet.worksheet(ABA_BIBLIOTECA)
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return {}
        
        biblioteca = {}
        for row in todos_dados[1:]:  # Pula cabeçalho
            if len(row) >= 3:
                defeito = row[0].strip() if row[0] else ""
                sugestao = row[1].strip() if len(row) > 1 and row[1] else ""
                direcionamento = row[2].strip() if len(row) > 2 and row[2] else ""
                
                if defeito:
                    biblioteca[defeito] = {
                        'sugestao': sugestao,
                        'direcionamento': direcionamento
                    }
        
        return biblioteca
        
    except Exception as e:
        print(f"Erro ao carregar biblioteca de defeitos: {e}")
        return {}

@dataclass
class RegistroAR:
    numero: Optional[int] = None
    data: Optional[datetime] = None
    hora: str = ""
    codigo: str = ""
    emissor: str = ""
    referencia: str = ""
    decisao: str = ""
    descricao: str = ""
    status: str = "ABERTO"
    disposicao: str = ""
    data_finalizacao: Optional[datetime] = None
    turno: str = ""
    # NOVOS CAMPOS PARA BIBLIOTECA
    defeito_biblioteca: str = ""
    sugestao_biblioteca: str = ""
    direcionamento_biblioteca: str = ""

def sanitize_filename_ar(filename: str) -> str:
    filename = unicodedata.normalize("NFKD", filename).encode("ASCII", "ignore").decode("ASCII")
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)
    return filename[:50]

def obter_proximo_numero_ar():
    try:
        client = get_gspread_client()
        if client is None:
            return 1
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
        todos_dados = sheet.get_all_values()
        if len(todos_dados) < 2:
            return 1
        numeros = []
        for row in todos_dados[1:]:
            if len(row) > 0 and row[0]:
                try:
                    num = int(float(row[0]))
                    numeros.append(num)
                except:
                    pass
        if not numeros:
            return 1
        return max(numeros) + 1
    except:
        return 1

# Função sem cache para ser usada nas notificações (verificação em tempo real, mas limitada a cada 60s)
@retry_on_quota()
def carregar_registros_ar_sem_cache() -> List[RegistroAR]:
    registros = []
    try:
        client = get_gspread_client()
        if client is None:
            return registros
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
        todos_dados = sheet.get_all_values()
        if len(todos_dados) < 2:
            return registros
        for row in todos_dados[1:]:
            if len(row) < 12:
                continue
            try:
                registro = RegistroAR()
                registro.numero = int(float(row[0])) if row[0].strip() else None
                registro.data = converter_data_br(row[1])
                registro.hora = row[2] if len(row) > 2 else ""
                registro.codigo = row[3] if len(row) > 3 else ""
                registro.emissor = row[4] if len(row) > 4 else ""
                registro.referencia = row[5] if len(row) > 5 else ""
                registro.decisao = row[6] if len(row) > 6 else ""
                registro.descricao = row[7] if len(row) > 7 else ""
                registro.status = row[8] if len(row) > 8 else "ABERTO"
                registro.disposicao = row[9] if len(row) > 9 else ""
                registro.data_finalizacao = converter_data_br(row[10]) if len(row) > 10 else None
                registro.turno = row[11] if len(row) > 11 else ""
                # NOVOS CAMPOS
                registro.defeito_biblioteca = row[12] if len(row) > 12 else ""
                registro.sugestao_biblioteca = row[13] if len(row) > 13 else ""
                registro.direcionamento_biblioteca = row[14] if len(row) > 14 else ""
                registros.append(registro)
            except:
                continue
        registros.sort(key=lambda x: x.data if x.data else datetime.min, reverse=True)
    except:
        pass
    return registros

# Função com cache para uso geral (visualização, edição, etc.)
@st.cache_data(ttl=1200)
def carregar_registros_ar(filtros: Dict[str, Any] = None) -> List[RegistroAR]:
    registros = carregar_registros_ar_sem_cache()
    if filtros:
        registros_filtrados = []
        for r in registros:
            incluir = True
            if filtros.get('numero') and filtros['numero'] != r.numero:
                incluir = False
            if filtros.get('status') and filtros['status'].upper() != r.status.upper():
                incluir = False
            if filtros.get('decisao') and filtros['decisao'].upper() != r.decisao.upper():
                incluir = False
            if incluir:
                registros_filtrados.append(r)
        return registros_filtrados
    return registros

def salvar_registro_ar(registro: RegistroAR, eh_alteracao: bool = False) -> bool:
    try:
        client = get_gspread_client()
        if client is None:
            return False
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
        dados = [
            str(registro.numero), 
            registro.data.strftime("%d/%m/%Y") if registro.data else "",
            registro.hora, 
            registro.codigo, 
            registro.emissor, 
            registro.referencia,
            registro.decisao, 
            registro.descricao, 
            registro.status, 
            registro.disposicao,
            registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else "",
            registro.turno,
            # NOVOS CAMPOS
            registro.defeito_biblioteca,
            registro.sugestao_biblioteca,
            registro.direcionamento_biblioteca
        ]
        if eh_alteracao:
            cell = sheet.find(str(registro.numero), in_column=1)
            if cell:
                for col, valor in enumerate(dados, start=1):
                    sheet.update_cell(cell.row, col, valor)
            else:
                sheet.append_row(dados)
        else:
            sheet.insert_row(dados, index=2)
        # Limpar cache para forçar recarregamento
        st.cache_data.clear()
        return True
    except:
        return False

def excluir_registro_ar(numero: int) -> bool:
    try:
        client = get_gspread_client()
        if client is None:
            return False
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
        cell = sheet.find(str(numero), in_column=1)
        if cell:
            sheet.delete_rows(cell.row)
            st.cache_data.clear()
            return True
        return False
    except:
        return False

def gerar_pdf_ar(registro: RegistroAR) -> Optional[bytes]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        
        buffer = io.BytesIO()
        
        # ===== CONFIGURAR DOCUMENTO =====
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm,
            leftMargin=1.5*cm,
            rightMargin=1.5*cm
        )
        elementos = []
        styles = getSampleStyleSheet()
        styleN = styles["Normal"]
        style_grande = ParagraphStyle('style_grande', parent=styleN, fontSize=11, leading=14)
        style_titulo_secao = ParagraphStyle('style_titulo_secao', parent=styleN, fontSize=11, spaceAfter=4, fontName='Helvetica-Bold')
        style_sugestao = ParagraphStyle('style_sugestao', parent=styleN, fontSize=10, leading=12, spaceAfter=3)
        style_descricao = ParagraphStyle('style_descricao', parent=styleN, fontSize=11, leading=14, spaceAfter=8)
        
        # ===== TÍTULO =====
        elementos.append(Paragraph("<b>AVISO DE REJEIÇÃO</b>", ParagraphStyle(name='Titulo', parent=styleN, fontSize=14, alignment=1, spaceAfter=8)))
        elementos.append(Paragraph("<b>CQ-018 REV004 - Luvidarte</b>", ParagraphStyle(name='Subtitulo', parent=styleN, fontSize=11, alignment=1, spaceAfter=12)))
        
        data_str = registro.data.strftime("%d/%m/%Y") if registro.data else ""
        data_fim_str = registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else ""
        
        # ===== TABELA DE CABEÇALHO (SEM O DEFEITO) =====
        dados_tabela = [
            ["Nº Controle:", str(registro.numero) if registro.numero else "", "Data:", data_str],
            ["Hora:", registro.hora, "Turno:", registro.turno],
            ["Código:", registro.codigo, "Status:", registro.status],
            ["Emissor:", registro.emissor, "", ""],
            ["Referência:", registro.referencia, "", ""],
            ["Situação:", registro.decisao, "Data Finalização:", data_fim_str]
        ]
        
        tabela_cabecalho = Table(dados_tabela, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
        
        estilo_tabela = [
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (0,0), (-1,-1), "LEFT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("PADDING", (0,0), (-1,-1), 5),
            ("SPAN", (2,3), (3,3)),
            ("SPAN", (2,4), (3,4)),
        ]
        
        tabela_cabecalho.setStyle(TableStyle(estilo_tabela))
        elementos.append(tabela_cabecalho)
        elementos.append(Spacer(1, 12))
        
        # ===== DESCRIÇÃO DO PROBLEMA COM DEFEITO CONCATENADO =====
        elementos.append(Paragraph("<b>DESCRIÇÃO DO PROBLEMA:</b>", style_titulo_secao))
        
        # Construir a descrição completa
        texto_descricao = ""
        
        # Se tiver defeito da biblioteca, adicionar em negrito
        if registro.defeito_biblioteca and str(registro.defeito_biblioteca).strip():
            texto_descricao += f"<b>DEFEITO IDENTIFICADO: {str(registro.defeito_biblioteca).strip()}</b>"
            
            # Se também tiver descrição, adicionar um separador
            if registro.descricao and registro.descricao.strip():
                texto_descricao += "<br/><br/>"
        
        # Adicionar a descrição do usuário
        if registro.descricao and registro.descricao.strip():
            texto_descricao += str(registro.descricao).strip()
        
        # Se não tiver nada, mostrar "-"
        if not texto_descricao:
            texto_descricao = "-"
        
        # Adicionar ao PDF
        elementos.append(Paragraph(texto_descricao, style_descricao))
        elementos.append(Spacer(1, 8))
        
        # ===== SUGESTÃO PARA SOLUCIONAR PROBLEMA =====
        if registro.sugestao_biblioteca and str(registro.sugestao_biblioteca).strip():
            elementos.append(Paragraph("<b>SUGESTÃO PARA SOLUCIONAR PROBLEMA:</b>", style_titulo_secao))
            
            # Processar a sugestão: dividir por * e criar bullets
            sugestao_texto = str(registro.sugestao_biblioteca)
            partes = sugestao_texto.split('*')
            for parte in partes:
                parte_limpa = parte.strip()
                if parte_limpa:
                    texto_formatado = f"• {parte_limpa}"
                    elementos.append(Paragraph(texto_formatado, style_sugestao))
            
            elementos.append(Spacer(1, 6))
        
        # ===== DIRECIONAMENTO AO INSPETOR =====
        if registro.direcionamento_biblioteca and str(registro.direcionamento_biblioteca).strip():
            elementos.append(Paragraph("<b>DIRECIONAMENTO AO INSPETOR:</b>", style_titulo_secao))
            elementos.append(Paragraph(str(registro.direcionamento_biblioteca), style_grande))
            elementos.append(Spacer(1, 8))
        
        # ===== DISPOSIÇÃO / AÇÕES TOMADAS =====
        elementos.append(Paragraph("<b>DISPOSIÇÃO / AÇÕES TOMADAS:</b>", style_titulo_secao))
        if registro.disposicao and registro.disposicao.strip():
            elementos.append(Paragraph(registro.disposicao, style_grande))
        else:
            elementos.append(Paragraph("-", style_grande))
        elementos.append(Spacer(1, 8))
        
        # ===== ASSINATURAS =====
        elementos.append(Paragraph("<b>ASSINATURAS:</b>", style_titulo_secao))
        
        tabela_assinatura = Table([
            ["Responsável:", "________________________________________"],
            ["Cargo:", "________________________________________"],
            ["Visto:", "________________________________________"],
            ["Cargo:", "________________________________________"],
            ["Data:", "________________________________________"]
        ], colWidths=[4*cm, 13*cm])
        
        tabela_assinatura.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.lightgrey),
            ("ALIGN", (0,0), (0,-1), "LEFT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("PADDING", (0,0), (-1,-1), 6),
            ("BACKGROUND", (0,0), (0,-1), colors.lightgrey),
        ]))
        elementos.append(tabela_assinatura)
        
        # ===== RODAPÉ =====
        elementos.append(Spacer(1, 12))
        elementos.append(Paragraph(f"Documento gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ParagraphStyle(name='Rodape', parent=styleN, fontSize=7, alignment=2)))
        elementos.append(Paragraph("* Espaços em branco devem ser preenchidos manualmente após impressão", ParagraphStyle(name='RodapeInstrucao', parent=styleN, fontSize=7, alignment=2, textColor=colors.gray)))
        
        # ===== CONSTRUIR PDF =====
        doc.build(elementos)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f"Erro ao gerar PDF do AR: {e}")
        traceback.print_exc()
        return None

def enviar_email_ar(destinatarios, assunto, corpo, anexo_bytes=None, nome_anexo=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG_AR["usuario"]
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain'))
        if anexo_bytes and nome_anexo:
            anexo = MIMEApplication(anexo_bytes, _subtype='pdf')
            anexo.add_header('Content-Disposition', 'attachment', filename=nome_anexo)
            msg.attach(anexo)
        with smtplib.SMTP_SSL(EMAIL_CONFIG_AR["smtp_server"], EMAIL_CONFIG_AR["smtp_port"], timeout=30) as server:
            server.login(EMAIL_CONFIG_AR["usuario"], EMAIL_CONFIG_AR["senha"])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail do AR: {e}")
        return False

# ======================
# FUNÇÕES DO SISTEMA RM (REQUISIÇÃO MANUTENÇÃO)
# ======================
@dataclass
class RegistroRM:
    id: Optional[int] = None
    data: Optional[datetime] = None
    hora: str = ""
    emissor: str = ""
    equipamento: str = ""
    setor: str = ""
    caracter: str = ""
    setor2: str = ""
    problema: str = ""
    trabalho: str = ""
    analise: str = ""
    status: str = "ABERTO"
    data_finalizacao: Optional[datetime] = None
    emissor2: str = ""

OPCOES_CARATER_RM = ["1 - Risco Físico/Segurança", "2 - Impacto Imediato na Produção", "3 - Impacto a Longo Prazo", "4 - Melhoria/Preventiva"]
OPCOES_SETORES_RM = ["Produção", "Corte", "Vidraria", "Rodaria", "Embalagem", "Expedição", "Qualidade", "Ferramentaria", "Manutenção", "Outros"]
OPCOES_SETORES2_RM = ["Elétrica", "Mecânica", "Informática", "Ferramentaria", "Manutenção Geral"]
OPCOES_STATUS_RM = ["ABERTO", "EM ANDAMENTO", "FINALIZADO", "CANCELADO"]

def obter_proximo_id_rm():
    try:
        client = get_gspread_client()
        if client is None:
            return 1
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
        todos_dados = sheet.get_all_values()
        if len(todos_dados) < 2:
            return 1
        ids = []
        for row in todos_dados[1:]:
            if row and row[0].strip():
                try:
                    ids.append(int(row[0]))
                except:
                    pass
        return max(ids) + 1 if ids else 1
    except:
        return 1

# Função sem cache para notificações
@retry_on_quota()
def carregar_registros_rm_sem_cache() -> List[RegistroRM]:
    registros = []
    try:
        client = get_gspread_client()
        if client is None:
            return registros
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
        todos_dados = sheet.get_all_values()
        if len(todos_dados) < 2:
            return registros
        for row in todos_dados[1:]:
            if len(row) < 14:
                continue
            try:
                registro = RegistroRM()
                registro.id = int(row[0]) if row[0].strip() else None
                registro.data = converter_data_br(row[1])
                registro.hora = row[2] if len(row) > 2 else ""
                registro.emissor = row[3] if len(row) > 3 else ""
                registro.equipamento = row[4] if len(row) > 4 else ""
                registro.setor = row[5] if len(row) > 5 else ""
                registro.caracter = row[6] if len(row) > 6 else ""
                registro.setor2 = row[7] if len(row) > 7 else ""
                registro.problema = row[8] if len(row) > 8 else ""
                registro.trabalho = row[9] if len(row) > 9 else ""
                registro.analise = row[10] if len(row) > 10 else ""
                registro.status = row[11] if len(row) > 11 else "ABERTO"
                registro.data_finalizacao = converter_data_br(row[12]) if len(row) > 12 else None
                registro.emissor2 = row[13] if len(row) > 13 else ""
                
                if registro.id is not None:
                    registros.append(registro)
            except:
                continue
        registros.sort(key=lambda x: x.id if x.id else 0, reverse=True)
    except:
        pass
    return registros

# Função com cache para uso geral
@st.cache_data(ttl=1200)
def carregar_registros_rm(filtros: Dict[str, Any] = None) -> List[RegistroRM]:
    registros = carregar_registros_rm_sem_cache()
    if filtros:
        registros_filtrados = []
        for r in registros:
            incluir = True
            if filtros.get('id') and filtros['id'] != r.id:
                incluir = False
            if filtros.get('equipamento') and filtros['equipamento'].lower() not in r.equipamento.lower():
                incluir = False
            if filtros.get('status') and filtros['status'] != r.status:
                incluir = False
            if incluir:
                registros_filtrados.append(r)
        return registros_filtrados
    return registros

def salvar_registro_rm(registro: RegistroRM, eh_alteracao: bool = False) -> bool:
    try:
        client = get_gspread_client()
        if client is None:
            return False
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
        dados = [
            str(registro.id) if registro.id else "",
            registro.data.strftime("%d/%m/%Y") if registro.data else "",
            registro.hora, registro.emissor, registro.equipamento, registro.setor,
            registro.caracter, registro.setor2, registro.problema, registro.trabalho,
            registro.analise, registro.status,
            registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else "",
            registro.emissor2
        ]
        if eh_alteracao:
            cell = sheet.find(str(registro.id), in_column=1)
            if cell:
                for col, valor in enumerate(dados, start=1):
                    sheet.update_cell(cell.row, col, valor)
            else:
                sheet.append_row(dados)
        else:
            sheet.insert_row(dados, index=2)
        st.cache_data.clear()
        return True
    except:
        return False

def excluir_registro_rm(id: int) -> bool:
    try:
        client = get_gspread_client()
        if client is None:
            return False
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
        cell = sheet.find(str(id), in_column=1)
        if cell:
            sheet.delete_rows(cell.row)
            st.cache_data.clear()
            return True
        return False
    except:
        return False

def gerar_pdf_rm(registro: RegistroRM) -> Optional[bytes]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elementos = []
        styles = getSampleStyleSheet()
        styleN = styles["Normal"]
        
        elementos.append(Paragraph("<b>REQUISIÇÃO DE MANUTENÇÃO</b>", ParagraphStyle(name='Titulo', parent=styles["Heading1"], fontSize=16, alignment=1, spaceAfter=12)))
        elementos.append(Paragraph("<b>MF-001 - Luvidarte</b>", ParagraphStyle(name='Subtitulo', parent=styles["Heading2"], fontSize=12, alignment=1, spaceAfter=24)))
        
        data_str = registro.data.strftime("%d/%m/%Y") if registro.data else ""
        data_fim_str = registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else ""
        
        tabela_dados = Table([
            ["ID:", registro.id, "Data:", data_str, "Hora:", registro.hora],
            ["Emissor:", registro.emissor, "Equipamento:", registro.equipamento, "Setor:", registro.setor],
            ["Caráter:", registro.caracter, "Setor Destino:", registro.setor2, "Status:", registro.status],
            ["Emissor Técnico:", registro.emissor2, "Data Finalização:", data_fim_str, "", ""],
        ], colWidths=[2.5*cm, 4*cm, 2.5*cm, 4*cm, 2*cm, 2.5*cm])
        
        tabela_dados.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (0,0), (-1,-1), "LEFT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("PADDING", (0,0), (-1,-1), 6),
        ]))
        elementos.append(tabela_dados)
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>DESCRIÇÃO DO PROBLEMA:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        elementos.append(Paragraph(registro.problema or "-", styleN))
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>TRABALHO REALIZADO:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        elementos.append(Paragraph(registro.trabalho or "_________________________", styleN))
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>ANÁLISE DO SERVIÇO:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        elementos.append(Paragraph(registro.analise or "_________________________", styleN))
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>ASSINATURAS:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        tabela_assinatura = Table([
            ["Solicitante", "Responsável Técnico", "Conferência Qualidade"],
            ["_________________________", "_________________________", "_________________________"],
            ["Data: __/__/____", "Data: __/__/____", "Data: __/__/____"]
        ], colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
        tabela_assinatura.setStyle(TableStyle([
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("PADDING", (0,0), (-1,-1), 10),
            ("FONTNAME", (0,0), (0,0), "Helvetica-Bold"),
            ("FONTNAME", (1,0), (1,0), "Helvetica-Bold"),
            ("FONTNAME", (2,0), (2,0), "Helvetica-Bold"),
        ]))
        elementos.append(tabela_assinatura)
        
        elementos.append(Spacer(1, 36))
        elementos.append(Paragraph(f"Documento gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ParagraphStyle(name='Rodape', parent=styleN, fontSize=8, alignment=2)))
        
        doc.build(elementos)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        return None

# ======================
# FUNÇÕES DE RENDERIZAÇÃO
# ======================
def render_page_header(title: str, subtitle: str, accent: str = None):
    if accent is None:
        accent = THEME['accent_cyan']
    st.markdown(f"""
    <div style="padding: 28px 0 20px 0; border-bottom: 1px solid {THEME['border_bright']}; margin-bottom: 28px; display: flex; align-items: center; gap: 16px;">
        <div style="width: 4px; height: 48px; background: linear-gradient(180deg, {accent}, transparent); border-radius: 2px;"></div>
        <div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.25em; color: {accent}; text-transform: uppercase;">LUVIDARTE / TRS DASHBOARD</div>
            <div style="font-family: 'Rajdhani', sans-serif; font-size: 36px; font-weight: 700; color: {THEME['text_primary']}; letter-spacing: 0.1em; text-transform: uppercase;">{title}</div>
            <div style="font-family: 'Barlow', sans-serif; font-size: 13px; color: {THEME['text_muted']}; margin-top: 4px;">{subtitle}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_section_header(title: str, icon: str = "▸", accent: str = None):
    if accent is None:
        accent = THEME['accent_cyan']
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 10px; margin: 28px 0 14px 0; padding-bottom: 8px; border-bottom: 1px solid {THEME['border']};">
        <span style="color: {accent}; font-size: 16px;">{icon}</span>
        <span style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: {THEME['text_primary']};">{title}</span>
    </div>
    """, unsafe_allow_html=True)

def render_kpi_card(label: str, value: str, accent: str = None, icon: str = ""):
    if accent is None:
        accent = THEME['accent_cyan']
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%); border: 1px solid {THEME['border_bright']}; border-radius: 8px; padding: 18px 22px; position: relative; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <div style="position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, {accent}, transparent);"></div>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: {THEME['text_muted']}; margin-bottom: 8px;">{icon} {label}</div>
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 34px; font-weight: 700; color: {accent}; letter-spacing: 0.03em; line-height: 1;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def apply_chart_style(ax, fig, title: str, xlabel: str = "", ylabel: str = "", accent: str = None):
    if accent is None:
        accent = THEME['accent_cyan']
    fig.patch.set_facecolor(THEME['bg_card'])
    ax.set_facecolor(THEME['bg_card'])
    ax.set_title(title, fontsize=14, fontweight='bold', color=THEME['text_primary'], pad=16, loc='left')
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, color=THEME['text_muted'], labelpad=8)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, color=THEME['text_muted'], labelpad=8)
    ax.tick_params(colors=THEME['text_muted'], labelsize=9)
    ax.grid(True, alpha=0.3, color=THEME['grid'], linewidth=0.8, linestyle='--')
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor(THEME['border_bright'])
        spine.set_linewidth(0.8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

# ======================
# CSS GLOBAL
# ======================
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Barlow:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {{
      font-family: 'Barlow', sans-serif;
      background-color: {THEME['bg_primary']} !important;
      color: {THEME['text_primary']} !important;
  }}
  .stApp {{ background-color: {THEME['bg_primary']} !important; }}

  [data-testid="stSidebar"] {{
      background: linear-gradient(180deg, #FFFFFF 0%, #F0F2F5 100%) !important;
      border-right: 1px solid {THEME['border_bright']} !important;
  }}
  
  [data-testid="stSidebar"] .stRadio label {{
      color: #000000 !important;
      font-weight: bold !important;
      font-family: 'Rajdhani', sans-serif !important;
      font-size: 15px !important;
      letter-spacing: 0.08em;
  }}
  
  [data-testid="stSidebar"] .stRadio * {{
      color: #000000 !important;
      font-weight: bold !important;
  }}
  
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stTextInput label,
  [data-testid="stSidebar"] .stDateInput label,
  [data-testid="stSidebar"] .stNumberInput label,
  [data-testid="stSidebar"] .stCheckbox label {{
      color: #000000 !important;
      font-weight: bold !important;
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 11px !important;
      text-transform: uppercase;
      letter-spacing: 0.12em;
  }}
  
  [data-testid="stSidebar"] h1 {{
      font-family: 'Rajdhani', sans-serif !important;
      color: {THEME['accent_cyan']} !important;
      font-size: 20px !important;
      font-weight: 700 !important;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      border-bottom: 1px solid {THEME['border_bright']};
      padding-bottom: 8px;
  }}

  .stSelectbox div[data-baseweb="select"] > div,
  .stTextInput input,
  .stNumberInput input,
  .stDateInput input {{
      background-color: {THEME['bg_card']} !important;
      border: 1px solid {THEME['border_bright']} !important;
      color: {THEME['text_primary']} !important;
      border-radius: 4px !important;
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 12px !important;
  }}

  [data-testid="stMetric"] {{
      background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%) !important;
      border: 1px solid {THEME['border_bright']} !important;
      border-radius: 8px !important;
      padding: 16px 20px !important;
      position: relative;
      overflow: hidden;
      box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  }}
  
  [data-testid="stMetric"]::before {{
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: linear-gradient(90deg, {THEME['accent_cyan']}, transparent);
  }}
  
  [data-testid="stMetricLabel"] {{
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 10px !important;
      font-weight: 500 !important;
      letter-spacing: 0.15em !important;
      text-transform: uppercase !important;
      color: {THEME['text_muted']} !important;
  }}
  
  [data-testid="stMetricValue"] {{
      font-family: 'Rajdhani', sans-serif !important;
      font-size: 32px !important;
      font-weight: 700 !important;
      color: {THEME['accent_cyan']} !important;
      letter-spacing: 0.05em;
  }}

  h1 {{
      font-family: 'Rajdhani', sans-serif !important;
      font-weight: 700 !important;
      font-size: 26px !important;
      letter-spacing: 0.1em !important;
      text-transform: uppercase !important;
      color: {THEME['text_primary']} !important;
  }}
  
  h2, h3 {{
      font-family: 'Rajdhani', sans-serif !important;
      font-weight: 600 !important;
      letter-spacing: 0.08em !important;
      text-transform: uppercase !important;
      color: {THEME['text_primary']} !important;
  }}

  .stDataFrame {{
      border: 1px solid {THEME['border_bright']} !important;
      border-radius: 6px !important;
      overflow: hidden;
  }}
  
  .stDataFrame thead th {{
      background-color: {THEME['bg_card']} !important;
      color: {THEME['accent_cyan']} !important;
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 11px !important;
      text-transform: uppercase !important;
      letter-spacing: 0.1em !important;
  }}

  hr {{
      border: none !important;
      border-top: 1px solid {THEME['border_bright']} !important;
      margin: 24px 0 !important;
  }}

  .stInfo {{ background-color: rgba(0,120,212,0.08) !important; border-left: 3px solid {THEME['accent_cyan']} !important; }}
  .stWarning {{ background-color: rgba(232,108,44,0.08) !important; border-left: 3px solid {THEME['accent_orange']} !important; }}
  .stSuccess {{ background-color: rgba(16,124,16,0.08) !important; border-left: 3px solid {THEME['accent_lime']} !important; }}
  .stError {{ background-color: rgba(232,17,35,0.08) !important; border-left: 3px solid {THEME['accent_red']} !important; }}
</style>
{NOTIFICACAO_CSS}
{MARQUEE_CSS}
""", unsafe_allow_html=True)

# ======================
# SIDEBAR - navegação e informações do usuário
# ======================
with st.sidebar:
    st.markdown(f"""
    <div style="text-align: center; padding: 20px 0 16px; border-bottom: 1px solid {THEME['border_bright']}; margin-bottom: 20px;">
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 24px; font-weight: 700; color: {THEME['accent_cyan']}; letter-spacing: 0.2em;">⚙ TRS</div>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: {THEME['text_muted']}; letter-spacing: 0.2em; text-transform: uppercase;">Industrial Dashboard</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"<div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:{THEME['accent_cyan']};margin-bottom:8px'>▸ Setor</div>", unsafe_allow_html=True)
    aba_selecionada = st.radio("", list(ABAS.keys()), label_visibility="collapsed")
    st.session_state.aba_selecionada = aba_selecionada
    
    # ===== INFORMAÇÕES DO USUÁRIO E LOGOUT =====
    st.markdown("---")
    
    # Informações do usuário
    usuario_logado = st.session_state.get('usuario', 'Usuário')
    nivel_logado = st.session_state.get('nivel', '0')
    setor_logado = st.session_state.get('setor', '')
    
    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.markdown(f"""
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: {THEME['text_muted']};">
            👤 <b style="color: {THEME['text_primary']};">{usuario_logado}</b><br>
            📊 Nível: {nivel_logado}<br>
            🏢 {setor_logado}
        </div>
        """, unsafe_allow_html=True)
    
    with col_btn:
        if st.button("🚪", help="Sair do sistema", key="btn_logout", use_container_width=True):
            fazer_logout()
    
    # ===== BOTÃO PARA LIMPAR CACHE E RECARREGAR =====
    st.markdown("---")
    
    # Exibir horário da última atualização
    if "ultima_atualizacao_cache" not in st.session_state:
        st.session_state.ultima_atualizacao_cache = datetime.now()
    
    st.caption(f"🔄 Última atualização: {st.session_state.ultima_atualizacao_cache.strftime('%H:%M:%S')}")
    
    # Botão de limpar cache
    if st.button("🔄 Limpar Cache e Recarregar", use_container_width=True, type="primary"):
        with st.spinner("🧹 Limpando cache e recarregando dados..."):
            sucesso, mensagem = limpar_cache_e_recarregar()
            if sucesso:
                st.session_state.ultima_atualizacao_cache = datetime.now()
                st.success(mensagem)
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(mensagem)
    
    # Botão adicional para recarregar apenas os dados (sem limpar cache completo)
    if st.button("📊 Recarregar Dados Apenas", use_container_width=True):
        with st.spinner("🔄 Recarregando dados..."):
            st.cache_data.clear()
            st.session_state.ultima_atualizacao_cache = datetime.now()
            st.success("✅ Dados recarregados!")
            time.sleep(0.3)
            st.rerun()
    
    # ===== INFORMAÇÕES DO SISTEMA =====
    st.markdown("---")
    st.caption(f"""
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 8px; color: {THEME['text_muted']}; text-align: center;">
        TRS Dashboard v2.0<br>
        {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

# ==================================================================================================
# VERIFICAÇÃO DE LOGIN - Protege todo o sistema
# ==================================================================================================

# Verifica se o usuário está logado e se a sessão é válida
if not verificar_acesso():
    # Se não estiver logado, a tela de login já foi renderizada
    # Para a execução aqui para não mostrar o resto do sistema
    st.stop()

# Se chegou aqui, o usuário está logado e a sessão é válida
# Remove mensagens de login antigas para não aparecerem na interface
if 'mensagem_login' in st.session_state:
    del st.session_state.mensagem_login

# Adiciona um botão de logout no sidebar (após a navegação)
# Modifique a seção do sidebar para incluir o logout

# ======================
# RENDERIZAR POPUPS PENDENTES E VERIFICAR NOVOS REGISTROS
# ======================
renderizar_popups_pendentes()
verificar_e_exibir_popups()

# ==================================================================================================
# PRENSADOS
# ==================================================================================================
if aba_selecionada == 'PRENSADOS':
    with st.spinner("Carregando dados..."):
        df_base = carregar_dados_prensados()

    if df_base.empty:
        st.warning("Não foi possível carregar os dados.")
        st.stop()

    df_base_calc = df_base.copy()
    colunas_numericas = ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%', 'REFUGADO']
    for col in colunas_numericas:
        if col in df_base_calc.columns:
            df_base_calc[col] = pd.to_numeric(df_base_calc[col], errors='coerce').fillna(0)

    if 'TRS 100%' in df_base_calc.columns:
        df_base_calc['TRS 1ª ESCOLHA (%)'] = df_base_calc.apply(
            lambda row: (row['APROVADO'] / row['TRS 100%'] * 100) if row['TRS 100%'] != 0 else 0, axis=1
        )
        df_base_calc['TRS FINAL (%)'] = df_base_calc.apply(
            lambda row: (row['EMBALADO'] / row['TRS 100%'] * 100) if row['TRS 100%'] != 0 else 0, axis=1
        )
    else:
        df_base_calc['TRS 1ª ESCOLHA (%)'] = 0
        df_base_calc['TRS FINAL (%)'] = 0

    melhores_trs_historico = {}
    if 'REFERÊNCIA' in df_base_calc.columns:
        for ref in df_base_calc['REFERÊNCIA'].unique():
            ref_df = df_base_calc[df_base_calc['REFERÊNCIA'] == ref]
            if not ref_df.empty:
                max_trs = ref_df['TRS FINAL (%)'].max()
                if max_trs > 0:
                    melhores_trs_historico[ref] = max_trs

    # Sidebar filtros PRENSADOS
    with st.sidebar:
        st.markdown(f"<div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:{THEME['accent_cyan']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>▸ Filtros · Prensados</div>", unsafe_allow_html=True)
        filtro_melhores_trs = st.checkbox("Melhores TRS por Referência", value=False)
        data_ini = st.date_input("Data inicial", value=None, key="prensados_data_ini")
        data_fim = st.date_input("Data final", value=None, key="prensados_data_fim")
        turno = st.selectbox("Turno", options=["(Todos)", "M", "T", "N"], key="prensados_turno")
        referencia = st.text_input("Referência (parte do código)", key="prensados_ref")
        prensa_tipo = st.selectbox("Tipo de prensa", ["(Todos)", "Semi-Automática", "Automática"], key="prensados_tipo")
        mostrar_defeitos = st.checkbox("Somatório de Defeitos", value=True, key="prensados_defeitos")
        qtd = st.number_input("Linhas na tabela (0 = todas)", min_value=0, max_value=5000, value=0, step=10, key="prensados_qtd")

    # Aplicar filtros
    df = df_base.copy()
    if data_ini:
        df = df[df['DATA'] >= pd.to_datetime(data_ini)]
    if data_fim:
        df = df[df['DATA'] <= pd.to_datetime(data_fim)]
    if turno != "(Todos)" and 'TURNO' in df.columns:
        df = df[df['TURNO'].fillna('').str.upper() == turno.upper()]
    if referencia and 'REFERÊNCIA' in df.columns:
        df = df[df['REFERÊNCIA'].fillna('').str.lower().str.contains(referencia.lower())]
    if prensa_tipo != "(Todos)" and 'BOQUETA' in df.columns:
        if "Semi" in prensa_tipo:
            df = df[df['BOQUETA'] == 1]
        elif "Auto" in prensa_tipo:
            df = df[df['BOQUETA'] == 2]

    # KPIs
    if not df.empty:
        for col in ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%', 'REFUGADO']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        total_prod = int(df['PRODUZIDO'].sum())
        total_apro = int(df['APROVADO'].sum())
        total_embal = int(df['EMBALADO'].sum()) if 'EMBALADO' in df.columns else 0
        total_meta = int(df['TRS 100%'].sum()) if 'TRS 100%' in df.columns else 0
        
        trs_primeira_escolha = (total_apro / total_meta * 100) if total_meta else 0
        trs_final_total = (total_embal / total_meta * 100) if total_meta else 0
    else:
        total_prod = total_apro = total_embal = total_meta = trs_primeira_escolha = trs_final_total = 0

    # Page header
    render_page_header("PRENSADOS", f"Industrial · {len(df):,} registros carregados · Atualizado {get_horario_brasilia()}", THEME['accent_cyan'])

    # KPIs (6 cards)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: render_kpi_card("Produzido", f"{total_prod:,}".replace(",","."), THEME['accent_cyan'], "◈")
    with c2: render_kpi_card("Aprovado", f"{total_apro:,}".replace(",","."), THEME['accent_lime'], "◈")
    with c3: render_kpi_card("Meta Líquida", f"{total_meta:,}".replace(",","."), THEME['accent_purple'], "◈")
    with c4: render_kpi_card("Embalado", f"{total_embal:,}".replace(",","."), THEME['accent_yellow'], "◈")
    with c5:
        trs_primeira_cor = THEME['accent_lime'] if trs_primeira_escolha >= 85 else THEME['accent_orange'] if trs_primeira_escolha >= 70 else THEME['accent_red']
        render_kpi_card("TRS 1ª Escolha", f"{trs_primeira_escolha:.1f}%", trs_primeira_cor, "◎")
    with c6:
        trs_final_cor = THEME['accent_lime'] if trs_final_total >= 85 else THEME['accent_orange'] if trs_final_total >= 70 else THEME['accent_red']
        render_kpi_card("TRS Final", f"{trs_final_total:.1f}%", trs_final_cor, "◎")

    # Tabela de produção
    render_section_header("Tabela de Produção", "▸")

    if not df.empty:
        if 'TRS 100%' in df.columns:
            df['TRS 1ª ESCOLHA (%)'] = df.apply(lambda r: (r['APROVADO'] / r['TRS 100%'] * 100) if r['TRS 100%'] != 0 else 0, axis=1)
            df['TRS FINAL (%)'] = df.apply(lambda r: (r['EMBALADO'] / r['TRS 100%'] * 100) if r['TRS 100%'] != 0 else 0, axis=1)
        df['TRS 1ª ESCOLHA (%)'] = df['TRS 1ª ESCOLHA (%)'].round(2)
        df['TRS FINAL (%)'] = df['TRS FINAL (%)'].round(2)

    df_sorted = df.sort_values(by="DATA", ascending=False).reset_index(drop=True)

    if filtro_melhores_trs and not df_sorted.empty and 'REFERÊNCIA' in df_sorted.columns:
        df_sorted = df_sorted[df_sorted.apply(lambda row: row['REFERÊNCIA'] in melhores_trs_historico and abs(row['TRS FINAL (%)'] - melhores_trs_historico[row['REFERÊNCIA']]) < 0.01, axis=1)].reset_index(drop=True)
        if not df_sorted.empty:
            st.info(f"Exibindo {len(df_sorted)} registro(s) — Melhor TRS Final Histórico por referência")
        else:
            st.warning("Nenhum registro encontrado com Melhor TRS Final Histórico")

    df_view = df_sorted if qtd == 0 else df_sorted.head(qtd)

    if not df_view.empty:
        df_display = df_view.copy()
        df_display['DATA'] = pd.to_datetime(df_display['DATA']).dt.strftime('%d/%m/%Y')

        for col in ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'REFUGADO', 'TRS 100%']:
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(lambda x: int(round(x)) if pd.notnull(x) else 0)
                df_display[col] = df_display[col].apply(lambda x: f"{x:,}".replace(",", "."))
        
        if 'TRS 1ª ESCOLHA (%)' in df_display.columns:
            df_display['TRS 1ª ESCOLHA (%)'] = df_display['TRS 1ª ESCOLHA (%)'].apply(lambda x: f"{x:.2f}%")
        if 'TRS FINAL (%)' in df_display.columns:
            df_display['TRS FINAL (%)'] = df_display['TRS FINAL (%)'].apply(lambda x: f"{x:.2f}%")

        colunas_exibir = ['DATA', 'REFERÊNCIA', 'TURNO', 'PRODUZIDO', 'APROVADO', 'TRS 100%', 'EMBALADO', 'REFUGADO', 'TRS 1ª ESCOLHA (%)', 'TRS FINAL (%)']
        if 'ANALISE' in df_display.columns:
            colunas_exibir.append('ANALISE')
        colunas_exibir = [col for col in colunas_exibir if col in df_display.columns]

        st.dataframe(df_display[colunas_exibir], use_container_width=True, height=400)

        if not filtro_melhores_trs:
            st.caption("▸ Dourado: Melhor TRS Final Histórico por referência   ▸ Verde: Análise registrada")

    # Gráfico TRS Diário
    render_section_header("Evolução Diária do TRS", "▸")

    if not df.empty and 'TRS 100%' in df.columns:
        colunas_agg = {}
        for col in ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%']:
            if col in df.columns:
                colunas_agg[col] = 'sum'
        
        if colunas_agg:
            resumo_dia = df.groupby(df['DATA'].dt.date).agg(colunas_agg).reset_index()
            resumo_dia['DATA'] = pd.to_datetime(resumo_dia['DATA'])
            
            if 'APROVADO' in resumo_dia.columns and 'TRS 100%' in resumo_dia.columns:
                resumo_dia['TRS 1ª ESCOLHA (%)'] = (resumo_dia['APROVADO'] / resumo_dia['TRS 100%'].replace(0, 1) * 100).fillna(0)
            
            if 'EMBALADO' in resumo_dia.columns and 'TRS 100%' in resumo_dia.columns:
                resumo_dia['TRS FINAL (%)'] = (resumo_dia['EMBALADO'] / resumo_dia['TRS 100%'].replace(0, 1) * 100).fillna(0)
            
            resumo_dia = resumo_dia.sort_values('DATA')

            if not resumo_dia.empty and ('TRS 1ª ESCOLHA (%)' in resumo_dia.columns or 'TRS FINAL (%)' in resumo_dia.columns):
                fig, ax = plt.subplots(figsize=(14, 5), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "TRS Diário — Período Selecionado", ylabel="TRS (%)")

                if 'TRS 1ª ESCOLHA (%)' in resumo_dia.columns:
                    ax.plot(resumo_dia['DATA'], resumo_dia['TRS 1ª ESCOLHA (%)'],
                            marker='o', markersize=6, linewidth=2.5,
                            color=THEME['accent_cyan'], alpha=0.95, label='TRS 1ª Escolha',
                            markerfacecolor=THEME['bg_card'], markeredgecolor=THEME['accent_cyan'], markeredgewidth=2)

                if 'TRS FINAL (%)' in resumo_dia.columns:
                    ax.plot(resumo_dia['DATA'], resumo_dia['TRS FINAL (%)'],
                            marker='s', markersize=6, linewidth=2.5,
                            color=THEME['accent_orange'], alpha=0.95, label='TRS Final',
                            markerfacecolor=THEME['bg_card'], markeredgecolor=THEME['accent_orange'], markeredgewidth=2)

                ax.axhline(y=85, color=THEME['accent_red'], linestyle=':', alpha=0.7, linewidth=1.5, label='Meta 85%')

                ax.legend(framealpha=0.15, facecolor=THEME['bg_card'], edgecolor=THEME['border_bright'],
                          labelcolor=THEME['text_primary'], fontsize=9)
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha='right', fontsize=8,
                         color=THEME['text_muted'])
                fig.tight_layout(pad=1.5)
                st.pyplot(fig)
                plt.close(fig)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Manual vs Automática
    render_section_header("Desempenho por Tipo de Prensa", "▸")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""<div style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.2em;
            text-transform:uppercase;color:{THEME['text_muted']};margin-bottom:8px">▸ Semi-Automática (Manual)</div>""", unsafe_allow_html=True)
        if 'BOQUETA' in df.columns:
            df_manual = df[df['BOQUETA'] == 1]
            if not df_manual.empty:
                t_ap_m = df_manual['APROVADO'].sum()
                t_emb_m = df_manual['EMBALADO'].sum()
                t_mt_m = df_manual['TRS 100%'].sum() if 'TRS 100%' in df_manual.columns else 1
                trs1_m = (t_ap_m / t_mt_m * 100) if t_mt_m > 0 else 0
                trs_final_m = (t_emb_m / t_mt_m * 100) if t_mt_m > 0 else 0
                prod_m = df_manual['PRODUZIDO'].sum()
                
                trs_color_m = THEME['accent_lime'] if trs1_m >= 85 else THEME['accent_orange'] if trs1_m >= 70 else THEME['accent_red']
                render_kpi_card("TRS 1ª Escolha — Manual", f"{trs1_m:.1f}%", trs_color_m)
                st.caption(f"TRS Final: {trs_final_m:.1f}% | Produção: {prod_m:,.0f} un".replace(",","."))
            else:
                st.info("Sem dados para Prensa Manual")

    with col2:
        st.markdown(f"""<div style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.2em;
            text-transform:uppercase;color:{THEME['text_muted']};margin-bottom:8px">▸ Automática</div>""", unsafe_allow_html=True)
        if 'BOQUETA' in df.columns:
            df_auto = df[df['BOQUETA'] == 2]
            if not df_auto.empty:
                t_ap_a = df_auto['APROVADO'].sum()
                t_emb_a = df_auto['EMBALADO'].sum()
                t_mt_a = df_auto['TRS 100%'].sum() if 'TRS 100%' in df_auto.columns else 1
                trs1_a = (t_ap_a / t_mt_a * 100) if t_mt_a > 0 else 0
                trs_final_a = (t_emb_a / t_mt_a * 100) if t_mt_a > 0 else 0
                prod_a = df_auto['PRODUZIDO'].sum()
                
                trs_color_a = THEME['accent_lime'] if trs1_a >= 85 else THEME['accent_orange'] if trs1_a >= 70 else THEME['accent_red']
                render_kpi_card("TRS 1ª Escolha — Automática", f"{trs1_a:.1f}%", trs_color_a)
                st.caption(f"TRS Final: {trs_final_a:.1f}% | Produção: {prod_a:,.0f} un".replace(",","."))
            else:
                st.info("Sem dados para Prensa Automática")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ==================================================================
    # ANÁLISE DE PARADAS - COM HORAS TRABALHADAS PRODUTIVAS NO PIZZA
    # ==================================================================
    render_section_header("Análise de Paradas", "▸")

    # 1. HORAS TRABALHADAS PRODUTIVAS = soma direta da coluna HORAS TOTAIS
    horas_trabalhadas_produtivas = 0
    if 'HORAS_TOTAIS_MIN' in df.columns:
        horas_trabalhadas_produtivas = df['HORAS_TOTAIS_MIN'].sum()
    else:
        for col in df.columns:
            col_upper = str(col).upper()
            if 'HORAS TOTAIS' in col_upper or 'HORA TOTAL' in col_upper:
                df['HORAS_TOTAIS_MIN'] = df[col].apply(converter_tempo_para_minutos)
                horas_trabalhadas_produtivas = df['HORAS_TOTAIS_MIN'].sum()
                break

    # 2. ERROS DE PROCESSO = soma da coluna ACERTOS (ignorando 02:45:00)
    total_acertos = 0
    if 'ACERTOS_MIN' in df.columns:
        def filtrar_acertos(val):
            if val == 165:  # 02:45:00 = 165 minutos
                return 0
            return val
        
        total_acertos = df['ACERTOS_MIN'].apply(filtrar_acertos).sum()
    else:
        for col in df.columns:
            col_upper = str(col).upper()
            if 'ACERTO' in col_upper and 'MIN' not in col_upper:
                df['ACERTOS_MIN'] = df[col].apply(converter_tempo_para_minutos)
                total_acertos = df['ACERTOS_MIN'].apply(filtrar_acertos).sum()
                break

    # 3. MANUTENÇÃO = soma da coluna MANUT.
    total_manut = 0
    if 'MANUT_MIN' in df.columns:
        total_manut = df['MANUT_MIN'].sum()
    else:
        for col in df.columns:
            col_upper = str(col).upper()
            if 'MANUT' in col_upper and 'MIN' not in col_upper:
                df['MANUT_MIN'] = df[col].apply(converter_tempo_para_minutos)
                total_manut = df['MANUT_MIN'].sum()
                break

    # Calcular Horas Produtivas para o gráfico de pizza
    horas_produtivas = max(0, horas_trabalhadas_produtivas - (total_acertos + total_manut))

    # Exibir APENAS 3 cards (Horas Trabalhadas Produtivas, Erros, Manutenção)
    p1, p2, p3 = st.columns(3)
    with p1: 
        render_kpi_card(
            "Horas Trabalhadas Produtivas", 
            minutos_para_horas_str(horas_trabalhadas_produtivas), 
            THEME['accent_lime']
        )
    with p2: 
        render_kpi_card(
            "Erros Processo", 
            minutos_para_horas_str(total_acertos), 
            THEME['accent_yellow']
        )
    with p3: 
        render_kpi_card(
            "Manutenção", 
            minutos_para_horas_str(total_manut), 
            THEME['accent_red']
        )

    # Gráfico de barras empilhadas: Manual vs Automática
    col1, col2 = st.columns(2)

    with col1:
        if 'BOQUETA' in df.columns:
            df_manual_p = df[df['BOQUETA'] == 1]
            df_auto_p = df[df['BOQUETA'] == 2]
            
            def filtrar_acertos_maquina(series):
                if len(series) == 0:
                    return 0
                return series.apply(lambda x: 0 if x == 165 else x).sum()
            
            acertos_m = filtrar_acertos_maquina(df_manual_p['ACERTOS_MIN']) if 'ACERTOS_MIN' in df_manual_p.columns else 0
            manut_m = df_manual_p['MANUT_MIN'].sum() if 'MANUT_MIN' in df_manual_p.columns else 0
            acertos_a = filtrar_acertos_maquina(df_auto_p['ACERTOS_MIN']) if 'ACERTOS_MIN' in df_auto_p.columns else 0
            manut_a = df_auto_p['MANUT_MIN'].sum() if 'MANUT_MIN' in df_auto_p.columns else 0

            categorias = ['Manual', 'Automática']
            acertos_v = [acertos_m, acertos_a]
            manut_v = [manut_m, manut_a]

            fig, ax = plt.subplots(figsize=(7, 5), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "Composição das Paradas", ylabel="Minutos")

            x = np.arange(len(categorias))
            w = 0.55
            ax.bar(x, acertos_v, w, label='Erros Processo', color=THEME['accent_yellow'], alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5)
            ax.bar(x, manut_v, w, bottom=acertos_v, label='Manutenção', color=THEME['accent_red'], alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5)

            for i, (a, m) in enumerate(zip(acertos_v, manut_v)):
                total = a + m
                if a > 0: 
                    ax.text(i, a/2, minutos_para_horas_str(a), ha='center', va='center', color='black', fontweight='bold', fontsize=10)
                if m > 0: 
                    ax.text(i, a + m/2, minutos_para_horas_str(m), ha='center', va='center', color='black', fontweight='bold', fontsize=10)
                if total > 0:
                    ax.text(i, total * 1.05, minutos_para_horas_str(total),
                            ha='center', va='bottom', color=THEME['text_primary'], fontweight='bold', fontsize=11)

            ax.set_xticks(x)
            ax.set_xticklabels(categorias, fontsize=10, color=THEME['text_muted'])
            ax.legend(framealpha=0.15, facecolor=THEME['bg_card'], edgecolor=THEME['border_bright'],
                      labelcolor=THEME['text_primary'], fontsize=9)
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    with col2:
        # GRÁFICO DE PIZZA - Usando a SOMA DOS 3 CARDS como 100%
        total_geral = horas_trabalhadas_produtivas + total_acertos + total_manut
        
        if total_geral > 0:
            perc_produtivo = (horas_trabalhadas_produtivas / total_geral * 100)
            perc_erros = (total_acertos / total_geral * 100)
            perc_manut = (total_manut / total_geral * 100)
            
            labels_p = ['Horas Trabalhadas Produtivas', 'Erros Processo', 'Manutenção']
            vals_p = [perc_produtivo, perc_erros, perc_manut]
            cores_p = [THEME['accent_lime'], THEME['accent_yellow'], THEME['accent_red']]
            
            dados_pizza = [(l, v, c) for l, v, c in zip(labels_p, vals_p, cores_p) if v > 0]
            
            if dados_pizza:
                lf, vf, cf = zip(*dados_pizza)
                
                fig, ax = plt.subplots(figsize=(7, 5), facecolor=THEME['bg_card'])
                fig.patch.set_facecolor(THEME['bg_card'])
                ax.set_facecolor(THEME['bg_card'])

                wedges, texts, autotexts = ax.pie(
                    vf, 
                    labels=lf, 
                    colors=cf,
                    autopct=lambda pct: f'{pct:.1f}%' if pct > 0.5 else '',
                    startangle=90,
                    textprops={'color': THEME['text_primary'], 'fontsize': 10},
                    wedgeprops={'edgecolor': THEME['bg_card'], 'linewidth': 2}
                )
                
                for autotext in autotexts:
                    if autotext.get_text():
                        autotext.set_color('white')
                        autotext.set_fontweight('bold')
                        autotext.set_fontsize(10)

                ax.set_title(
                    f"Distribuição do Tempo\nTotal: {minutos_para_horas_str(total_geral)}",
                    fontsize=13, fontweight='bold', color=THEME['text_primary'], pad=14
                )
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("Sem dados para exibir no gráfico")
        else:
            st.info("Sem dados de tempo para exibir")

    # ==================================================================
    # NOVOS GRÁFICOS: MANUAL E AUTOMÁTICA - MÊS A MÊS
    # ==================================================================
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("📊 Evolução Mensal de Erros e Manutenção por Tipo de Prensa", "▸")

    # Função para filtrar acertos (ignorar 02:45:00)
    def filtrar_acertos_para_grafico(valor):
        """Retorna 0 se o valor for 02:45:00 (165 minutos), senão retorna o valor original"""
        if valor == 165:
            return 0
        return valor

    # Verificar se temos dados para ambos os tipos
    if 'BOQUETA' in df.columns and 'ACERTOS_MIN' in df.columns and 'MANUT_MIN' in df.columns:
        # Criar coluna de mês/ano
        df['MES_ANO'] = df['DATA'].dt.to_period('M').astype(str)
        
        # Separar dados por tipo de prensa
        df_manual = df[df['BOQUETA'] == 1].copy()
        df_auto = df[df['BOQUETA'] == 2].copy()
        
        # ==== GRÁFICO MANUAL ====
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;
            color:{THEME['accent_cyan']};margin:10px 0 5px;font-weight:bold;">
            🔧 SEMI-AUTOMÁTICA (MANUAL)
        </div>
        """, unsafe_allow_html=True)
        
        if not df_manual.empty:
            # Agrupar por mês
            agg_manual = df_manual.groupby('MES_ANO').agg({
                'ACERTOS_MIN': lambda x: x.apply(filtrar_acertos_para_grafico).sum(),
                'MANUT_MIN': 'sum'
            }).reset_index()
            
            # Ordenar por mês
            agg_manual = agg_manual.sort_values('MES_ANO')
            
            if not agg_manual.empty:
                fig, ax = plt.subplots(figsize=(12, 5), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "Manual - Erros de Processo vs Manutenção", ylabel="Minutos")
                
                x = np.arange(len(agg_manual))
                width = 0.35
                
                bars1 = ax.bar(x - width/2, agg_manual['ACERTOS_MIN'], width, 
                              label='Erros Processo', color=THEME['accent_yellow'], 
                              alpha=0.85, edgecolor='white', linewidth=1.5)
                bars2 = ax.bar(x + width/2, agg_manual['MANUT_MIN'], width, 
                              label='Manutenção', color=THEME['accent_red'], 
                              alpha=0.85, edgecolor='white', linewidth=1.5)
                
                # Adicionar valores nas barras
                for bars in [bars1, bars2]:
                    for bar in bars:
                        height = bar.get_height()
                        if height > 0:
                            ax.text(bar.get_x() + bar.get_width()/2., height + 3,
                                   minutos_para_horas_str(int(height)),
                                   ha='center', va='bottom', fontsize=8, fontweight='bold')
                
                ax.set_xticks(x)
                ax.set_xticklabels(agg_manual['MES_ANO'], fontsize=10, fontweight='bold')
                ax.legend(loc='upper left', fontsize=10)
                
                # Ajustar limites
                max_valor = max(agg_manual['ACERTOS_MIN'].max(), agg_manual['MANUT_MIN'].max())
                if max_valor > 0:
                    ax.set_ylim(0, max_valor * 1.2)
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
                
                # Mostrar total do período
                total_acertos_m = agg_manual['ACERTOS_MIN'].sum()
                total_manut_m = agg_manual['MANUT_MIN'].sum()
                st.caption(f"📊 Total Manual: Erros Processo: {minutos_para_horas_str(int(total_acertos_m))} | Manutenção: {minutos_para_horas_str(int(total_manut_m))}")
            else:
                st.info("📭 Sem dados mensais para Prensa Manual")
        else:
            st.info("📭 Nenhum dado disponível para Prensa Manual")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # ==== GRÁFICO AUTOMÁTICA ====
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;
            color:{THEME['accent_purple']};margin:10px 0 5px;font-weight:bold;">
            🤖 AUTOMÁTICA
        </div>
        """, unsafe_allow_html=True)
        
        if not df_auto.empty:
            # Agrupar por mês
            agg_auto = df_auto.groupby('MES_ANO').agg({
                'ACERTOS_MIN': lambda x: x.apply(filtrar_acertos_para_grafico).sum(),
                'MANUT_MIN': 'sum'
            }).reset_index()
            
            # Ordenar por mês
            agg_auto = agg_auto.sort_values('MES_ANO')
            
            if not agg_auto.empty:
                fig, ax = plt.subplots(figsize=(12, 5), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "Automática - Erros de Processo vs Manutenção", ylabel="Minutos")
                
                x = np.arange(len(agg_auto))
                width = 0.35
                
                bars1 = ax.bar(x - width/2, agg_auto['ACERTOS_MIN'], width, 
                              label='Erros Processo', color=THEME['accent_yellow'], 
                              alpha=0.85, edgecolor='white', linewidth=1.5)
                bars2 = ax.bar(x + width/2, agg_auto['MANUT_MIN'], width, 
                              label='Manutenção', color=THEME['accent_red'], 
                              alpha=0.85, edgecolor='white', linewidth=1.5)
                
                # Adicionar valores nas barras
                for bars in [bars1, bars2]:
                    for bar in bars:
                        height = bar.get_height()
                        if height > 0:
                            ax.text(bar.get_x() + bar.get_width()/2., height + 3,
                                   minutos_para_horas_str(int(height)),
                                   ha='center', va='bottom', fontsize=8, fontweight='bold')
                
                ax.set_xticks(x)
                ax.set_xticklabels(agg_auto['MES_ANO'], fontsize=10, fontweight='bold')
                ax.legend(loc='upper left', fontsize=10)
                
                # Ajustar limites
                max_valor = max(agg_auto['ACERTOS_MIN'].max(), agg_auto['MANUT_MIN'].max())
                if max_valor > 0:
                    ax.set_ylim(0, max_valor * 1.2)
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
                
                # Mostrar total do período
                total_acertos_a = agg_auto['ACERTOS_MIN'].sum()
                total_manut_a = agg_auto['MANUT_MIN'].sum()
                st.caption(f"📊 Total Automática: Erros Processo: {minutos_para_horas_str(int(total_acertos_a))} | Manutenção: {minutos_para_horas_str(int(total_manut_a))}")
            else:
                st.info("📭 Sem dados mensais para Prensa Automática")
        else:
            st.info("📭 Nenhum dado disponível para Prensa Automática")

    else:
        st.warning("⚠️ Dados insuficientes para gerar os gráficos mensais. Verifique as colunas 'BOQUETA', 'ACERTOS_MIN' e 'MANUT_MIN'.")

    # ==================================================================
    # GRÁFICO DE COLUNAS POR TURNO (Horas Trabalhadas, Erros, Manutenção) + TRS (linha)
    # ==================================================================
    if not df.empty and 'TURNO' in df.columns:
        render_section_header("Tempo de Parada x Produtividade (TRS)", "▸")
        
        mapeamento_turnos = {
            'M': {'nome': 'Manhã', 'lider': 'Felipe'},
            'T': {'nome': 'Tarde', 'lider': 'Ubaldo'},
            'N': {'nome': 'Noite', 'lider': 'Carlos'}
        }
        
        ordem_turnos = ['M', 'T', 'N']
        
        turno_data = []
        
        for turno in ordem_turnos:
            df_turno = df[df['TURNO'] == turno]
            
            if df_turno.empty:
                turno_data.append({
                    'Turno': turno,
                    'TurnoNome': mapeamento_turnos.get(turno, {}).get('nome', turno),
                    'Lider': mapeamento_turnos.get(turno, {}).get('lider', ''),
                    'Horas Trabalhadas': 0,
                    'Erros Processo': 0,
                    'Manutenção': 0,
                    'TRS': 0
                })
                continue
            
            horas_turno = 0
            if 'HORAS_TOTAIS_MIN' in df_turno.columns:
                horas_turno = df_turno['HORAS_TOTAIS_MIN'].sum()
            else:
                for col in df_turno.columns:
                    col_upper = str(col).upper()
                    if 'HORAS TOTAIS' in col_upper or 'HORA TOTAL' in col_upper:
                        horas_turno = df_turno[col].apply(converter_tempo_para_minutos).sum()
                        break
            
            erros_turno = 0
            if 'ACERTOS_MIN' in df_turno.columns:
                def filtrar_acertos_turno(val):
                    if val == 165:
                        return 0
                    return val
                erros_turno = df_turno['ACERTOS_MIN'].apply(filtrar_acertos_turno).sum()
            
            manut_turno = 0
            if 'MANUT_MIN' in df_turno.columns:
                manut_turno = df_turno['MANUT_MIN'].sum()
            
            total_aprovado = df_turno['APROVADO'].sum() if 'APROVADO' in df_turno.columns else 0
            total_meta = df_turno['TRS 100%'].sum() if 'TRS 100%' in df_turno.columns else 1
            trs_correto = (total_aprovado / total_meta * 100) if total_meta > 0 else 0
            
            turno_data.append({
                'Turno': turno,
                'TurnoNome': mapeamento_turnos.get(turno, {}).get('nome', turno),
                'Lider': mapeamento_turnos.get(turno, {}).get('lider', ''),
                'Horas Trabalhadas': horas_turno,
                'Erros Processo': erros_turno,
                'Manutenção': manut_turno,
                'TRS': trs_correto
            })
        
        if turno_data:
            df_turno_graf = pd.DataFrame(turno_data)
            
            fig, ax1 = plt.subplots(figsize=(14, 7), facecolor=THEME['bg_card'])
            fig.patch.set_facecolor(THEME['bg_card'])
            
            ax1.set_xlabel("Turno", fontsize=12, fontweight='bold')
            ax1.set_ylabel("Minutos", fontsize=12, fontweight='bold', color=THEME['text_primary'])
            ax1.tick_params(axis='y', labelcolor=THEME['text_primary'])
            ax1.set_facecolor(THEME['bg_card'])
            ax1.grid(True, alpha=0.3, color=THEME['grid'], linewidth=0.8, linestyle='--')
            ax1.set_axisbelow(True)
            
            x = np.arange(len(df_turno_graf))
            width = 0.25
            
            bars1 = ax1.bar(x - width, df_turno_graf['Horas Trabalhadas'], width, 
                           label='Horas Trabalhadas', color=THEME['accent_lime'], alpha=0.85, 
                           edgecolor='white', linewidth=1.5)
            bars2 = ax1.bar(x, df_turno_graf['Erros Processo'], width, 
                           label='Erros Processo', color=THEME['accent_yellow'], alpha=0.85, 
                           edgecolor='white', linewidth=1.5)
            bars3 = ax1.bar(x + width, df_turno_graf['Manutenção'], width, 
                           label='Manutenção', color=THEME['accent_red'], alpha=0.85, 
                           edgecolor='white', linewidth=1.5)
            
            for bars in [bars1, bars2, bars3]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax1.text(bar.get_x() + bar.get_width()/2., height + 5,
                                f'{minutos_para_horas_str(int(height))}',
                                ha='center', va='bottom', fontsize=8, rotation=0, 
                                color=THEME['text_primary'], fontweight='bold')
            
            max_valor = max(df_turno_graf[['Horas Trabalhadas', 'Erros Processo', 'Manutenção']].max())
            ax1.set_ylim(0, max_valor * 1.2 if max_valor > 0 else 100)
            
            ax2 = ax1.twinx()
            ax2.set_ylabel("TRS 1ª Escolha (%)", fontsize=12, fontweight='bold', color=THEME['accent_purple'])
            
            trs_values = df_turno_graf['TRS'].values
            line = ax2.plot(x, trs_values, marker='o', markersize=10, linewidth=2.5, 
                           color=THEME['accent_purple'], label='TRS 1ª Escolha (%)',
                           markerfacecolor=THEME['bg_card'], 
                           markeredgecolor=THEME['accent_purple'], 
                           markeredgewidth=2)
            
            for i, (x_pos, trs_val) in enumerate(zip(x, trs_values)):
                if trs_val > 0:
                    ax2.annotate(f'{trs_val:.1f}%', 
                                (x_pos, trs_val),
                                textcoords="offset points", 
                                xytext=(0, 12),
                                ha='center', 
                                fontsize=10, 
                                fontweight='bold',
                                color=THEME['accent_purple'],
                                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8, edgecolor=THEME['accent_purple']))
            
            ax2.tick_params(axis='y', labelcolor=THEME['accent_purple'])
            ax2.set_ylim(0, 105)
            
            rotulos_x = [f"{row['Turno']} ({row['TurnoNome']})\n{row['Lider']}" for _, row in df_turno_graf.iterrows()]
            ax1.set_xticks(x)
            ax1.set_xticklabels(rotulos_x, fontsize=11, fontweight='bold')
            
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10, 
                      framealpha=0.15, facecolor=THEME['bg_card'], edgecolor=THEME['border_bright'])
            
            ax1.set_title("Tempo de Parada x Produtividade (TRS)", 
                         fontsize=16, fontweight='bold', color=THEME['text_primary'], pad=20)
            
            ax1.spines['top'].set_visible(False)
            ax2.spines['top'].set_visible(False)
            ax1.spines['right'].set_visible(False)
            
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
            
            with st.expander("📊 Ver tabela detalhada por Turno"):
                df_tabela_turno = df_turno_graf.copy()
                for col in ['Horas Trabalhadas', 'Erros Processo', 'Manutenção']:
                    df_tabela_turno[col] = df_tabela_turno[col].apply(
                        lambda x: minutos_para_horas_str(int(x)) if x > 0 else "00:00"
                    )
                df_tabela_turno = df_tabela_turno[['Turno', 'TurnoNome', 'Lider', 'Horas Trabalhadas', 'Erros Processo', 'Manutenção', 'TRS']]
                df_tabela_turno = df_tabela_turno.rename(columns={
                    'Turno': 'Turno',
                    'TurnoNome': 'Turno Nome',
                    'Lider': 'Líder Industrial',
                    'Horas Trabalhadas': 'Horas Trabalhadas',
                    'Erros Processo': 'Erros Processo',
                    'Manutenção': 'Manutenção',
                    'TRS': 'TRS 1ª Escolha (%)'
                })
                df_tabela_turno['TRS 1ª Escolha (%)'] = df_tabela_turno['TRS 1ª Escolha (%)'].apply(lambda x: f"{x:.1f}%")
                st.dataframe(df_tabela_turno, use_container_width=True, hide_index=True)
        else:
            st.info("Sem dados de turno para exibir")            
            
    st.markdown("<hr>", unsafe_allow_html=True)

    # TRS por Turno
    if not df.empty and 'TURNO' in df.columns and 'TRS 100%' in df.columns:
        render_section_header("TRS por Turno", "▸")
        turno_data = []
        for t in df['TURNO'].unique():
            df_t = df[df['TURNO'] == t]
            te = df_t['EMBALADO'].sum() if 'EMBALADO' in df_t.columns else 0
            ta = df_t['APROVADO'].sum()
            tm = df_t['TRS 100%'].sum()
            turno_data.append({
                'Turno': t, 
                'TRS 1ª Escolha': (ta/tm*100) if tm > 0 else 0,
                'TRS Final': (te/tm*100) if tm > 0 else 0
            })
        df_tt = pd.DataFrame(turno_data)
        if not df_tt.empty:
            fig, ax = plt.subplots(figsize=(10, 5), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "TRS por Turno", ylabel="TRS (%)")
            
            x = np.arange(len(df_tt))
            width = 0.35
            
            bars1 = ax.bar(x - width/2, df_tt['TRS 1ª Escolha'], width, label='TRS 1ª Escolha', color=THEME['accent_cyan'], alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5)
            bars2 = ax.bar(x + width/2, df_tt['TRS Final'], width, label='TRS Final', color=THEME['accent_orange'], alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5)
            
            ax.axhline(y=85, color=THEME['accent_red'], linestyle='--', alpha=0.5, linewidth=1.5, label='Meta 85%')
            
            for bar in bars1:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, h + 1, f'{h:.1f}%', ha='center', va='bottom', fontsize=8, color=THEME['accent_cyan'])
            
            for bar in bars2:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, h + 1, f'{h:.1f}%', ha='center', va='bottom', fontsize=8, color=THEME['accent_orange'])
            
            ax.set_xticks(x)
            ax.set_xticklabels(df_tt['Turno'], fontsize=11)
            ax.legend(loc='upper right', fontsize=9)
            ax.set_ylim(0, 105)
            
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    # Defeitos de Prensados
    if mostrar_defeitos:
        render_section_header("Estratificação de Defeitos - Prensados", "▸")
        colunas_defeitos_prensados = [
            'BOLHA', 'PEDRA', 'TRINCA', 'RUGAS', 'CORTE TESOURA', 
            'DOBRA', 'FARINHA', 'QUEBRA', 'ARREADO', 'VIDRO GRUDADO',
            'CONTRA-PEÇA', 'FALHAS', 'CHUPADO', 'ÓLEO TESOURA', 
            'CROMO', 'MACHO', 'BARRO', 'EMPENO', 'OUTROS'
        ]
        
        defeitos_existentes = []
        for defeito in colunas_defeitos_prensados:
            for col in df.columns:
                if col.upper() == defeito.upper():
                    defeitos_existentes.append(col)
                    break
        
        if not defeitos_existentes:
            for col in df.columns:
                col_upper = col.upper()
                for defeito in colunas_defeitos_prensados:
                    if defeito.upper() == col_upper:
                        defeitos_existentes.append(col)
                        break
        
        if defeitos_existentes:
            defeitos_existentes = list(dict.fromkeys(defeitos_existentes))
            
            df_def = df[defeitos_existentes].apply(pd.to_numeric, errors='coerce').fillna(0)
            df_def_sum = df_def.sum().sort_values(ascending=False)
            df_def_sum = df_def_sum[df_def_sum > 0]
            
            if not df_def_sum.empty:
                altura_grafico = max(4, len(df_def_sum) * 0.35)
                
                fig, ax = plt.subplots(figsize=(12, altura_grafico), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "Defeitos — Somatório", ylabel="Quantidade")
                
                bars = ax.barh(range(len(df_def_sum)), df_def_sum.values,
                              color=THEME['accent_red'], alpha=0.8,
                              edgecolor=THEME['bg_card'], linewidth=1.2)
                
                ax.set_yticks(range(len(df_def_sum)))
                ax.set_yticklabels(df_def_sum.index, fontsize=9, color=THEME['text_muted'])
                ax.invert_yaxis()
                
                max_valor = df_def_sum.max() if len(df_def_sum) > 0 else 1
                for bar, val in zip(bars, df_def_sum.values):
                    if val > 0:
                        ax.text(bar.get_width() + (max_valor * 0.01), 
                               bar.get_y() + bar.get_height()/2,
                               f"{int(val):,}".replace(",","."), 
                               va='center', fontsize=9, color=THEME['text_primary'])
                
                ax.set_xlabel("Quantidade", fontsize=10, color=THEME['text_muted'])
                fig.tight_layout(pad=1.5)
                st.pyplot(fig)
                plt.close(fig)
                
                total_def = df_def_sum.sum()
                st.caption(f"**Total de defeitos:** {int(total_def):,}".replace(",","."))
                
                with st.expander("📊 Ver tabela detalhada de defeitos"):
                    tabela_defeitos = pd.DataFrame({
                        'Defeito': df_def_sum.index,
                        'Quantidade': df_def_sum.values.astype(int),
                        '% do Total': (df_def_sum.values / total_def * 100).round(1)
                    })
                    tabela_defeitos['% do Total'] = tabela_defeitos['% do Total'].astype(str) + '%'
                    st.dataframe(tabela_defeitos, use_container_width=True, hide_index=True)
                    
                    if len(df_def_sum) > 1:
                        st.markdown("**📈 Top 5 Defeitos**")
                        top5 = df_def_sum.head(5)
                        outros_total = df_def_sum.iloc[5:].sum() if len(df_def_sum) > 5 else 0
                        
                        dados_pizza = []
                        labels_pizza = []
                        for idx, (defeito, qtd) in enumerate(top5.items()):
                            dados_pizza.append(qtd)
                            labels_pizza.append(f"{defeito}\n({qtd:.0f})")
                        if outros_total > 0:
                            dados_pizza.append(outros_total)
                            labels_pizza.append(f"Outros\n({outros_total:.0f})")
                        
                        fig2, ax2 = plt.subplots(figsize=(6, 6), facecolor=THEME['bg_card'])
                        cores_pizza = ['#E81123', '#FF8C00', '#FFB900', '#107C10', '#0078D4', '#6B46C1']
                        wedges, texts, autotexts = ax2.pie(
                            dados_pizza, 
                            labels=labels_pizza,
                            colors=cores_pizza[:len(dados_pizza)],
                            autopct='%1.0f%%',
                            startangle=90,
                            textprops={'fontsize': 9}
                        )
                        for autotext in autotexts:
                            autotext.set_color('white')
                            autotext.set_fontweight('bold')
                            autotext.set_fontsize(10)
                        ax2.set_title('Distribuição dos Defeitos (Top 5)', fontweight='bold', fontsize=12)
                        fig2.tight_layout()
                        st.pyplot(fig2)
                        plt.close(fig2)
            else:
                st.info("📭 Nenhum defeito registrado no período selecionado")
        else:
            st.warning("⚠️ Colunas de defeitos não encontradas na planilha de Prensados")
            st.caption(f"Colunas disponíveis na planilha: {', '.join(list(df.columns)[:15])}...")

    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        TRS DASHBOARD · PRENSADOS · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)


# ==================================================================================================
# SOPRO
# ==================================================================================================
elif aba_selecionada == 'SOPRO':
    with st.spinner("Carregando dados..."):
        df_base = carregar_dados_sopro()

    if df_base.empty:
        st.warning("Não foi possível carregar os dados.")
        st.stop()

    df_base_calc = df_base.copy()
    if 'TRS_BRUTO' in df_base_calc.columns:
        df_base_calc['TRS LÍQUIDO (%)'] = (df_base_calc['TRS_BRUTO'] * 100).round(2)
        df_base_calc['META'] = df_base_calc.apply(
            lambda row: (row['APROVADO'] / (row['TRS LÍQUIDO (%)'] / 100)) if row['TRS LÍQUIDO (%)'] > 0 else row['APROVADO'], axis=1
        ).round(0)
    else:
        df_base_calc['TRS LÍQUIDO (%)'] = 0
        df_base_calc['META'] = 0

    melhores_trs_historico = {}
    if 'REFERÊNCIA' in df_base_calc.columns:
        for ref in df_base_calc['REFERÊNCIA'].unique():
            ref_df = df_base_calc[df_base_calc['REFERÊNCIA'] == ref]
            if not ref_df.empty:
                mt = ref_df['TRS LÍQUIDO (%)'].max()
                if mt > 0:
                    melhores_trs_historico[ref] = mt

    # Sidebar filtros SOPRO
    with st.sidebar:
        st.markdown(f"<div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:{THEME['accent_lime']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>▸ Filtros · Sopro</div>", unsafe_allow_html=True)
        filtro_melhores_trs = st.checkbox("Melhores TRS Líquido por Referência", value=False, key="sopro_melhores")
        data_ini = st.date_input("Data inicial", value=None, key="sopro_data_ini")
        data_fim = st.date_input("Data final",   value=None, key="sopro_data_fim")
        if 'TURNO' in df_base.columns:
            turnos_disp = ["(Todos)"] + sorted(df_base['TURNO'].dropna().unique().tolist())
            turno = st.selectbox("Turno", options=turnos_disp, key="sopro_turno")
        else:
            turno = "(Todos)"
        referencia = st.text_input("Referência (parte do código)", key="sopro_ref")
        if 'PRAÇA' in df_base.columns:
            pracas_disp = ["(Todas)"] + sorted(df_base['PRAÇA'].dropna().unique().tolist())
            praca = st.selectbox("Praça", options=pracas_disp, key="sopro_praca")
        else:
            praca = "(Todas)"
        mostrar_defeitos = st.checkbox("Somatório de Defeitos", value=True, key="sopro_defeitos")
        qtd = st.number_input("Linhas na tabela (0 = todas)", min_value=0, max_value=5000, value=0, step=10, key="sopro_qtd")

    # Filtros
    df = df_base.copy()
    if data_ini: df = df[df['DATA'] >= pd.to_datetime(data_ini)]
    if data_fim: df = df[df['DATA'] <= pd.to_datetime(data_fim)]
    if turno != "(Todos)" and 'TURNO' in df.columns:
        df = df[df['TURNO'].fillna('').str.upper() == turno.upper()]
    if referencia and 'REFERÊNCIA' in df.columns:
        df = df[df['REFERÊNCIA'].fillna('').str.lower().str.contains(referencia.lower())]
    if praca != "(Todas)" and 'PRAÇA' in df.columns:
        df = df[df['PRAÇA'].fillna('').str.upper() == praca.upper()]

    for col in ['PRODUZIDO', 'REFUGADO', 'APROVADO', 'TRS_BRUTO']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    total_prod   = int(df['PRODUZIDO'].sum()) if 'PRODUZIDO' in df.columns else 0
    total_refugo = int(df['REFUGADO'].sum())  if 'REFUGADO'  in df.columns else 0
    total_apro   = int(df['APROVADO'].sum())  if 'APROVADO'  in df.columns else 0
    trs_liq_med  = df['TRS_BRUTO'].mean() * 100 if 'TRS_BRUTO' in df.columns and not df.empty else 0
    
    if not df.empty and 'TRS_BRUTO' in df.columns and 'APROVADO' in df.columns:
        df['TRS_LIQUIDO_PCT'] = df['TRS_BRUTO'] * 100
        df['META_CALC'] = df.apply(
            lambda row: (row['APROVADO'] / (row['TRS_LIQUIDO_PCT'] / 100)) if row['TRS_LIQUIDO_PCT'] > 0 else row['APROVADO'], axis=1
        )
        total_meta = int(df['META_CALC'].sum())
    else:
        total_meta = 0

    # Page header
    render_page_header("SOPRO", f"Industrial · {len(df):,} registros carregados · Atualizado {get_horario_brasilia()}", THEME['accent_lime'])

    # KPIs (5 cards)
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1: render_kpi_card("Produzido", f"{total_prod:,}".replace(",","."), THEME['accent_cyan'], "◈")
    with c2: render_kpi_card("Aprovado", f"{total_apro:,}".replace(",","."), THEME['accent_lime'], "◈")
    with c3: render_kpi_card("Meta (TRS 100%)", f"{total_meta:,}".replace(",","."), THEME['accent_purple'], "◈")
    with c4: render_kpi_card("Refugo", f"{total_refugo:,}".replace(",","."), THEME['accent_orange'], "◈")
    with c5:
        trs_c = THEME['accent_lime'] if trs_liq_med >= 85 else THEME['accent_orange'] if trs_liq_med >= 70 else THEME['accent_red']
        render_kpi_card("TRS Líquido Médio", f"{trs_liq_med:.1f}%", trs_c, "◎")

    # Tabela
    render_section_header("Tabela de Produção", "▸", THEME['accent_lime'])

    if not df.empty and 'TRS_BRUTO' in df.columns:
        df['TRS LÍQUIDO (%)'] = (df['TRS_BRUTO'] * 100).round(2)
        df['META'] = df.apply(
            lambda row: int(round(row['APROVADO'] / (row['TRS LÍQUIDO (%)'] / 100))) if row['TRS LÍQUIDO (%)'] > 0 else int(row['APROVADO']), axis=1
        )

    df_sorted = df.sort_values(by="DATA", ascending=False).reset_index(drop=True)

    if filtro_melhores_trs and not df_sorted.empty and 'REFERÊNCIA' in df_sorted.columns and 'TRS LÍQUIDO (%)' in df_sorted.columns:
        df_sorted = df_sorted[df_sorted.apply(
            lambda r: r['REFERÊNCIA'] in melhores_trs_historico and
                      abs(r['TRS LÍQUIDO (%)'] - melhores_trs_historico[r['REFERÊNCIA']]) < 0.01, axis=1
        )].reset_index(drop=True)
        if not df_sorted.empty:
            st.info(f"Exibindo {len(df_sorted)} registro(s) — Melhor TRS Líquido Histórico por referência")
        else:
            st.warning("Nenhum registro encontrado")

    df_view = df_sorted if qtd == 0 else df_sorted.head(qtd)

    if not df_view.empty:
        df_display = df_view.copy()
        df_display['DATA'] = pd.to_datetime(df_display['DATA']).dt.strftime('%d/%m/%Y')
        
        for col in ['PRODUZIDO', 'APROVADO', 'REFUGADO', 'META']:
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(lambda x: int(round(x)) if pd.notnull(x) else 0)
                df_display[col] = df_display[col].apply(lambda x: f"{x:,}".replace(",", "."))
        
        if 'TRS LÍQUIDO (%)' in df_display.columns:
            df_display['TRS LÍQUIDO (%)'] = df_display['TRS LÍQUIDO (%)'].apply(lambda x: f"{x:.2f}%")

        colunas_exibir = ['DATA','TURNO','PRAÇA','REFERÊNCIA','PRODUZIDO','META','APROVADO','REFUGADO','TRS LÍQUIDO (%)']
        colunas_exibir = [c for c in colunas_exibir if c in df_display.columns]

        st.dataframe(df_display[colunas_exibir], use_container_width=True, height=400)
        if not filtro_melhores_trs:
            st.caption("▸ Dourado: Melhor TRS Líquido Histórico por referência")
    else:
        st.warning("Nenhum dado encontrado com os filtros selecionados.")

    # TRS Líquido Diário
    render_section_header("Evolução Diária do TRS Líquido", "▸", THEME['accent_lime'])
    if not df.empty and 'TRS_BRUTO' in df.columns:
        res_dia = df.groupby(df['DATA'].dt.date).agg({
            'TRS_BRUTO': 'mean', 
            'PRODUZIDO': 'sum', 
            'APROVADO': 'sum'
        }).reset_index()
        res_dia['DATA'] = pd.to_datetime(res_dia['DATA'])
        res_dia['TRS Líquido (%)'] = res_dia['TRS_BRUTO'] * 100
        res_dia = res_dia.sort_values('DATA')
        
        if not res_dia.empty:
            fig, ax = plt.subplots(figsize=(14, 5), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "TRS Líquido Diário — Período Selecionado", ylabel="TRS Líquido (%)")
            ax.fill_between(res_dia['DATA'], 0, res_dia['TRS Líquido (%)'], alpha=0.12, color=THEME['accent_lime'])
            ax.plot(res_dia['DATA'], res_dia['TRS Líquido (%)'],
                    marker='o', markersize=6, linewidth=2.5, color=THEME['accent_lime'], alpha=0.95,
                    label='TRS Líquido', markerfacecolor=THEME['bg_card'],
                    markeredgecolor=THEME['accent_lime'], markeredgewidth=2)
            if len(res_dia) > 1:
                mm = res_dia['TRS Líquido (%)'].rolling(window=min(3, len(res_dia)), min_periods=1).mean()
                ax.plot(res_dia['DATA'], mm, color=THEME['accent_yellow'], alpha=0.8,
                        linewidth=1.8, linestyle='--', label='Média 3 dias')
            ax.axhline(y=85, color=THEME['accent_red'], linestyle=':', alpha=0.7, linewidth=1.5, label='Meta 85%')
            ax.legend(framealpha=0.15, facecolor=THEME['bg_card'], edgecolor=THEME['border_bright'],
                      labelcolor=THEME['text_primary'], fontsize=9)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha='right', fontsize=8, color=THEME['text_muted'])
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Por Praça
    if 'PRAÇA' in df.columns and not df.empty and 'TRS_BRUTO' in df.columns:
        render_section_header("TRS Líquido por Praça", "▸", THEME['accent_lime'])
        res_praca = df.groupby('PRAÇA').agg({
            'TRS_BRUTO': 'mean', 
            'PRODUZIDO': 'sum',
            'APROVADO': 'sum'
        }).reset_index()
        res_praca['TRS Líquido (%)'] = res_praca['TRS_BRUTO'] * 100
        res_praca = res_praca.sort_values('TRS Líquido (%)', ascending=False)
        
        if not res_praca.empty:
            fig, ax = plt.subplots(figsize=(10, 5), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "TRS Líquido Médio por Praça", ylabel="TRS Líquido (%)")
            bar_cols = [THEME['accent_lime'] if v >= 85 else THEME['accent_orange'] if v >= 70 else THEME['accent_red']
                        for v in res_praca['TRS Líquido (%)']]
            bars = ax.bar(range(len(res_praca)), res_praca['TRS Líquido (%)'], color=bar_cols,
                          alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5, width=0.6)
            ax.axhline(y=85, color=THEME['accent_red'], linestyle='--', alpha=0.4, linewidth=1.5)
            for bar, v in zip(bars, res_praca['TRS Líquido (%)']):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f'{v:.1f}%', ha='center', va='bottom', fontsize=9,
                        color=THEME['text_primary'], fontweight='bold')
            ax.set_xticks(range(len(res_praca)))
            ax.set_xticklabels(res_praca['PRAÇA'], rotation=40, ha='right', fontsize=9)
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Mensal
    render_section_header("TRS Líquido Mensal", "▸", THEME['accent_lime'])
    if not df.empty and 'ANO_MES' in df.columns and 'TRS_BRUTO' in df.columns:
        res_mes = df.groupby('ANO_MES').agg({
            'TRS_BRUTO': 'mean', 
            'PRODUZIDO': 'sum', 
            'APROVADO': 'sum'
        }).reset_index()
        res_mes['TRS Líquido (%)'] = res_mes['TRS_BRUTO'] * 100
        res_mes = res_mes.sort_values('ANO_MES')
        
        if not res_mes.empty:
            fig, ax = plt.subplots(figsize=(12, 5), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "TRS Líquido Mensal", ylabel="TRS Líquido (%)")
            bar_cols = [THEME['accent_lime'] if v >= 85 else THEME['accent_orange'] if v >= 70 else THEME['accent_red']
                        for v in res_mes['TRS Líquido (%)']]
            bars = ax.bar(range(len(res_mes)), res_mes['TRS Líquido (%)'], color=bar_cols,
                          alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5, width=0.65)
            ax.axhline(y=85, color=THEME['accent_red'], linestyle='--', alpha=0.4, linewidth=1.5)
            for bar, v in zip(bars, res_mes['TRS Líquido (%)']):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f'{v:.1f}%', ha='center', va='bottom', fontsize=10,
                        color=THEME['text_primary'], fontweight='bold')
            meses_fmt = []
            for m in res_mes['ANO_MES']:
                ms = str(m)
                meses_fmt.append(ms[5:7]+'/'+ms[:4] if len(ms) > 6 else ms)
            ax.set_xticks(range(len(res_mes)))
            ax.set_xticklabels(meses_fmt, rotation=40, ha='right', fontsize=9)
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Por Turno
    if not df.empty and 'TURNO' in df.columns and 'TRS_BRUTO' in df.columns:
        render_section_header("TRS Líquido por Turno", "▸", THEME['accent_lime'])
        turno_data = [{'Turno': t, 'TRS Líquido': df[df['TURNO'] == t]['TRS_BRUTO'].mean() * 100} for t in df['TURNO'].unique()]
        df_tt = pd.DataFrame(turno_data)
        if not df_tt.empty:
            fig, ax = plt.subplots(figsize=(8, 4), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "TRS Líquido por Turno", ylabel="TRS Líquido (%)")
            cores_t = {'M': THEME['accent_cyan'], 'T': THEME['accent_orange'], 'N': THEME['accent_lime'],
                       'A': THEME['accent_cyan'], 'B': THEME['accent_orange'], 'C': THEME['accent_lime']}
            bc = [cores_t.get(t, THEME['text_muted']) for t in df_tt['Turno']]
            ax.bar(range(len(df_tt)), df_tt['TRS Líquido'], color=bc, alpha=0.88,
                   edgecolor=THEME['bg_card'], linewidth=1.5, width=0.55)
            ax.axhline(y=85, color=THEME['accent_red'], linestyle='--', alpha=0.5, linewidth=1.5)
            for i, v in enumerate(df_tt['TRS Líquido']):
                ax.text(i, v + 1, f"{v:.1f}%", ha='center', va='bottom', fontweight='bold', fontsize=11, color=THEME['text_primary'])
            ax.set_xticks(range(len(df_tt)))
            ax.set_xticklabels(df_tt['Turno'], fontsize=11)
            ax.set_ylim(0, 115)
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    # Defeitos
    if mostrar_defeitos:
        render_section_header("Estratificação de Defeitos", "▸", THEME['accent_lime'])
        colunas_defeitos = [
            'BOLHA','PEDRA','CALCINADO','BALANÇANDO','AMASSADO','OVAL','CORTE','QUEBRADA',
            'VIDRO GRUDADO','CORDA','FORMA','RISCO','TORTO','RUGA','GABARITO','SUJEIRA',
            'EMPENO','MARCAS','FALHADA','DOBRA','CHUPADO','ARREADO','GOSMA','BARRO','CROMO','MACHO'
        ]
        def_exist = []
        for defeito in colunas_defeitos:
            for col in df.columns:
                if col.upper() == defeito.upper():
                    def_exist.append(col)
                    break
        if def_exist:
            df_def = df[def_exist].apply(pd.to_numeric, errors='coerce').fillna(0)
            df_def_s = df_def.sum().sort_values(ascending=False)
            df_def_s = df_def_s[df_def_s > 0]
            if not df_def_s.empty:
                fig, ax = plt.subplots(figsize=(12, 4), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "Defeitos — Somatório", ylabel="Quantidade")
                bars = ax.bar(range(len(df_def_s)), df_def_s.values,
                              color=THEME['accent_red'], alpha=0.8,
                              edgecolor=THEME['bg_card'], linewidth=1.2)
                ax.set_xticks(range(len(df_def_s)))
                ax.set_xticklabels(df_def_s.index, rotation=40, ha='right', fontsize=9, color=THEME['text_muted'])
                for bar, val in zip(bars, df_def_s.values):
                    if val > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.02,
                                f"{int(val):,}".replace(",","."), ha='center', va='bottom',
                                fontsize=8, color=THEME['text_primary'])
                fig.tight_layout(pad=1.5)
                st.pyplot(fig)
                plt.close(fig)
                st.caption(f"Total de defeitos: {int(df_def_s.sum()):,}".replace(",","."))

    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        TRS DASHBOARD · SOPRO · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)


# ==================================================================================================
# TÊMPERA (COM MAPEAMENTO CORRETO DAS COLUNAS)
# ==================================================================================================
elif aba_selecionada == 'TÊMPERA':
    ABA = 'TRS_TEMPERA'

    # Mapeamento dos códigos de defeito
    MAPEAMENTO_DEFEITOS = {
        1: 'Estourou após furar',
        2: 'Quebra no resfriamento',
        3: 'Quebra teste impacto',
        4: 'Furada e não fraturou',
        5: 'Quebra de quarentena',
        6: 'Ovalizada'
    }
    
    CODIGOS_DEFEITO_REAIS = [2, 3, 4, 5, 6]

    # ======================
    # ARQUIVO DE CACHE LOCAL
    # ======================
    CACHE_FILE_TEMPERA = "cache_tempera.pkl"
    
    def safe_float(val):
        """Converte valor para float de forma segura"""
        if val is None or pd.isna(val):
            return 0.0
        try:
            val_str = str(val).strip()
            if val_str == '' or val_str == 'nan':
                return 0.0
            val_str = val_str.replace(',', '.')
            return float(val_str)
        except:
            return 0.0

    def salvar_cache_tempera(df):
        """Salva o DataFrame em cache local"""
        try:
            df.to_pickle(CACHE_FILE_TEMPERA)
            return True
        except Exception as e:
            print(f"Erro ao salvar cache: {e}")
            return False
    
    def carregar_cache_tempera():
        """Carrega o DataFrame do cache local"""
        try:
            if os.path.exists(CACHE_FILE_TEMPERA):
                df = pd.read_pickle(CACHE_FILE_TEMPERA)
                if not df.empty:
                    return df
            return None
        except Exception as e:
            print(f"Erro ao carregar cache: {e}")
            return None

    # ======================
    # FUNÇÃO DE PROCESSAMENTO DOS DADOS - CORRIGIDA
    # ======================
    def processar_dados_tempera(todos_dados):
        """Processa os dados brutos da planilha e retorna DataFrame processado"""
        if len(todos_dados) < 2:
            return pd.DataFrame()
        
        cabecalho = todos_dados[0]
        valores = todos_dados[1:]
        df = pd.DataFrame(valores, columns=cabecalho)
        
        # ===== CORREÇÃO: Mapeamento baseado nos nomes REAIS das colunas =====
        # Baseado no diagnóstico: os nomes reais são 'DATA TEMP.', 'TURNO TEMP.', 'PROD.'
        
        # Mapeamento de nomes de colunas
        rename_map = {}
        
        for col in df.columns:
            col_clean = str(col).strip().upper()
            
            if 'DATA TEMP' in col_clean or col_clean == 'DATA':
                rename_map[col] = 'DATA_TEMP'
            elif 'TURNO TEMP' in col_clean or col_clean == 'TURNO':
                rename_map[col] = 'TURNO_TEMP'
            elif col_clean == 'PROD.' or col_clean == 'PRODUTO' or col_clean == 'PROD':
                rename_map[col] = 'PRODUTO'
            elif col_clean == 'GANCHEIRA':
                rename_map[col] = 'GANCHEIRA'
            elif col_clean == 'SUPEIOR' or col_clean == 'SUPERIOR':
                rename_map[col] = 'SUPERIOR'
            elif col_clean == 'MEIO':
                rename_map[col] = 'MEIO'
            elif col_clean == 'INFERIOR':
                rename_map[col] = 'INFERIOR'
            elif col_clean == 'A1':
                rename_map[col] = 'A1'
            elif col_clean == 'C1':
                rename_map[col] = 'C1'
            elif col_clean == 'A2':
                rename_map[col] = 'A2'
            elif col_clean == 'C2':
                rename_map[col] = 'C2'
            elif col_clean == 'A3':
                rename_map[col] = 'A3'
            elif col_clean == 'C3':
                rename_map[col] = 'C3'
            elif col_clean == 'A4':
                rename_map[col] = 'A4'
            elif col_clean == 'C4':
                rename_map[col] = 'C4'
            elif col_clean == 'A5':
                rename_map[col] = 'A5'
            elif col_clean == 'C5':
                rename_map[col] = 'C5'
            elif col_clean == 'A E B':
                rename_map[col] = 'A e B'
            elif col_clean == 'APROVADAS':
                rename_map[col] = 'APROVADAS'
        
        # Aplicar renomeação
        df = df.rename(columns=rename_map)
        
        # Converter datas
        if 'DATA_TEMP' in df.columns:
            df['DATA'] = df['DATA_TEMP'].apply(converter_data_br)
        
        if 'DATA' in df.columns:
            df = df.dropna(subset=['DATA'])
        
        # Converter colunas numéricas
        colunas_numericas = ['SUPERIOR', 'MEIO', 'INFERIOR', 'A1', 'C1', 'A2', 'C2', 'A3', 'C3', 'A4', 'C4', 'A5', 'C5', 'A e B', 'APROVADAS']
        
        for col in colunas_numericas:
            if col in df.columns:
                df[col] = df[col].apply(safe_float)
        
        # CORREÇÃO: Tempo C2 - converter para segundos
        if 'C2' in df.columns:
            def converter_tempo_c2(val):
                if pd.isna(val) or val == 0:
                    return 0
                if val <= 1:
                    return val * 100
                elif val <= 10:
                    return val * 10
                else:
                    return val
            df['C2'] = df['C2'].apply(converter_tempo_c2)
        
        # Identificar colunas de posições (colunas com números)
        colunas_posicoes_validas = []
        for col in df.columns:
            try:
                # Tenta converter para número
                num = float(str(col).strip())
                if 19 <= num <= 70:
                    colunas_posicoes_validas.append(col)
            except:
                pass
        
        # Se não encontrou colunas de posição, tentar identificar colunas com números
        if not colunas_posicoes_validas:
            for col in df.columns:
                try:
                    num = float(str(col).strip())
                    if 1 <= num <= 100:
                        colunas_posicoes_validas.append(col)
                except:
                    pass
        
        # Inicializar colunas
        df['TOTAL_PECAS'] = 40
        df['APROVADO'] = 40
        df['TOTAL_DEFEITOS'] = 0
        df['IS_CRITICO'] = False
        
        for codigo, nome in MAPEAMENTO_DEFEITOS.items():
            nome_clean = nome.upper().replace(' ', '_').replace('Ç', 'C').replace('Ã', 'A').replace('Á', 'A').replace('Ó', 'O')
            df[f'QTD_{nome_clean}'] = 0
        
        # Processar cada linha para contar defeitos
        for idx, row in df.iterrows():
            defeitos_contagem = {codigo: 0 for codigo in MAPEAMENTO_DEFEITOS.keys()}
            
            for col in colunas_posicoes_validas:
                try:
                    val = row[col]
                    if pd.notna(val) and str(val).strip():
                        # Converter para número
                        val_str = str(val).strip().replace(',', '.')
                        codigo = int(float(val_str))
                        if codigo in MAPEAMENTO_DEFEITOS:
                            defeitos_contagem[codigo] += 1
                except:
                    pass
            
            total_defeitos_reais = sum(defeitos_contagem.get(cod, 0) for cod in CODIGOS_DEFEITO_REAIS)
            aprovadas = 40 - total_defeitos_reais
            
            df.at[idx, 'APROVADO'] = aprovadas
            df.at[idx, 'TOTAL_DEFEITOS'] = total_defeitos_reais
            df.at[idx, 'TRS (%)'] = (aprovadas / 40 * 100) if 40 > 0 else 0
            
            is_critico = False
            if defeitos_contagem.get(4, 0) >= 1:
                is_critico = True
            if defeitos_contagem.get(3, 0) > 2:
                is_critico = True
            df.at[idx, 'IS_CRITICO'] = is_critico
            
            for codigo, nome in MAPEAMENTO_DEFEITOS.items():
                nome_clean = nome.upper().replace(' ', '_').replace('Ç', 'C').replace('Ã', 'A').replace('Á', 'A').replace('Ó', 'O')
                col_nome = f'QTD_{nome_clean}'
                if col_nome in df.columns:
                    df.at[idx, col_nome] = defeitos_contagem.get(codigo, 0)
        
        return df

    # ======================
    # FUNÇÃO DE CARREGAMENTO COM VALIDAÇÃO
    # ======================
    @retry_on_quota(max_retries=3, delay=5)
    def carregar_dados_tempera():
        """
        Carrega dados da têmpera com validação e fallback para cache
        """
        # 1. TENTAR CARREGAR DO CACHE PRIMEIRO (mais rápido)
        df_cache = carregar_cache_tempera()
        if df_cache is not None and not df_cache.empty:
            return df_cache
        
        # 2. TENTAR CARREGAR DA API
        try:
            client = get_gspread_client()
            if client is None:
                st.error("❌ Não foi possível conectar ao Google Sheets")
                return pd.DataFrame()
            
            # Tentar carregar a planilha
            try:
                sheet = client.open_by_key(ID_PLANILHA_TEMPERA).worksheet(ABA)
            except Exception as e:
                st.error(f"❌ Erro ao acessar a planilha: {e}")
                return pd.DataFrame()
            
            # Ler os dados
            todos_dados = sheet.get_all_values()
            
            # Validar se há dados
            if len(todos_dados) < 2:
                st.warning("⚠️ A planilha está vazia ou não tem dados suficientes.")
                return pd.DataFrame()
            
            # Processar os dados
            df = processar_dados_tempera(todos_dados)
            
            # Validar se o processamento gerou dados
            if df.empty:
                st.warning("⚠️ Nenhum dado válido encontrado na planilha.")
                return pd.DataFrame()
            
            # Salvar em cache
            salvar_cache_tempera(df)
            
            return df
            
        except Exception as e:
            # Tratamento para erro de quota
            if "429" in str(e) or "Quota exceeded" in str(e):
                st.warning("⚠️ Limite de requisições ao Google Sheets atingido.")
                # Tentar carregar do cache novamente
                df_cache = carregar_cache_tempera()
                if df_cache is not None and not df_cache.empty:
                    st.info(f"📂 Usando dados em cache ({len(df_cache)} registros).")
                    return df_cache
                else:
                    st.error("❌ Sem dados em cache disponíveis. Aguarde alguns minutos e tente novamente.")
                    return pd.DataFrame()
            else:
                st.error(f"❌ Erro ao carregar dados: {str(e)}")
                df_cache = carregar_cache_tempera()
                if df_cache is not None and not df_cache.empty:
                    st.info(f"📂 Usando dados em cache devido ao erro ({len(df_cache)} registros).")
                    return df_cache
                return pd.DataFrame()

    # ======================
    # FUNÇÃO PARA FORCAR RECARREGAMENTO
    # ======================
    def forcar_recarregamento_tempera():
        """Força o recarregamento dos dados da API"""
        try:
            if os.path.exists(CACHE_FILE_TEMPERA):
                os.remove(CACHE_FILE_TEMPERA)
            st.cache_data.clear()
            return True
        except:
            return False

    # ======================
    # CARREGAR DADOS PRIMEIRO
    # ======================
    with st.spinner("Carregando dados da Têmpera..."):
        df_base = carregar_dados_tempera()

    if df_base.empty:
        st.error("""
        ❌ **Não foi possível carregar os dados da Têmpera.**
        
        **Possíveis causas:**
        1. A planilha está vazia ou sem dados
        2. Limite de requisições ao Google Sheets atingido
        3. Problemas de conexão com a internet
        
        **Soluções:**
        1. Aguarde alguns minutos e clique em "Recarregar Dados da Planilha" no sidebar
        2. Verifique se a planilha está acessível
        3. Verifique sua conexão com a internet
        """)
        
        # Botão para tentar novamente
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔄 Tentar Novamente", use_container_width=True):
                forcar_recarregamento_tempera()
                st.rerun()
        st.stop()

    # ======================
    # SIDEBAR FILTROS
    # ======================
    with st.sidebar:
        st.markdown(f"<div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:{THEME['accent_purple']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>▸ Filtros · Têmpera</div>", unsafe_allow_html=True)
        
        data_ini = st.date_input("Data inicial", value=None, key="tempera_data_ini")
        data_fim = st.date_input("Data final", value=None, key="tempera_data_fim")
        
        if 'TURNO_TEMP' in df_base.columns:
            turnos_disp = ["(Todos)"] + sorted([str(t) for t in df_base['TURNO_TEMP'].dropna().unique()])
            turno = st.selectbox("Turno", options=turnos_disp, key="tempera_turno")
        else:
            turno = "(Todos)"
        
        if 'PRODUTO' in df_base.columns:
            produtos_disp = ["(Todos)"] + sorted([str(p) for p in df_base['PRODUTO'].dropna().unique()])
            produto = st.selectbox("Produto", options=produtos_disp, key="tempera_produto")
        else:
            produto = "(Todos)"
        
        excluir_criticos = st.checkbox("Excluir registros críticos", value=False, key="tempera_excluir_criticos")
        qtd = st.number_input("Linhas na tabela", min_value=0, max_value=5000, value=20, step=10, key="tempera_qtd")
        
        st.markdown("---")
        
        # Botão para forçar recarregamento
        if st.button("🔄 Recarregar Dados da Planilha", key="btn_recarregar_tempera", use_container_width=True):
            if forcar_recarregamento_tempera():
                st.success("✅ Cache limpo! Recarregando dados da planilha...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Erro ao limpar cache")
        
        # Informações do cache
        if os.path.exists(CACHE_FILE_TEMPERA):
            try:
                tamanho = os.path.getsize(CACHE_FILE_TEMPERA) / 1024
                st.caption(f"💾 Cache: {tamanho:.1f} KB")
            except:
                pass

    # ── Aplicar filtros ──
    df = df_base.copy()
    
    if data_ini:
        df = df[df['DATA'] >= pd.to_datetime(data_ini)]
    if data_fim:
        df = df[df['DATA'] <= pd.to_datetime(data_fim)]
    if turno != "(Todos)" and 'TURNO_TEMP' in df.columns:
        df = df[df['TURNO_TEMP'].astype(str).str.upper() == turno.upper()]
    if produto != "(Todos)" and 'PRODUTO' in df.columns:
        df = df[df['PRODUTO'].astype(str) == produto]
    
    if excluir_criticos and 'IS_CRITICO' in df.columns:
        df = df[~df['IS_CRITICO']].copy()

    if df.empty:
        st.warning("Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    # ── Função para média ignorando zeros ──
    def safe_mean(col):
        """Calcula média ignorando valores zero e NaN"""
        if col in df.columns:
            valores = df[col][(df[col] > 0) & (pd.notna(df[col]))]
            if len(valores) > 0:
                return valores.mean()
        return 0

    # ── KPIs (médias ignorando zeros) ──
    total_registros = len(df)
    total_pecas = total_registros * 40
    total_aprovado = int(df['APROVADO'].sum())
    total_defeitos = int(df['TOTAL_DEFEITOS'].sum())
    trs_medio = (total_aprovado / total_pecas * 100) if total_pecas > 0 else 0
    
    temp_sup = safe_mean('SUPERIOR')
    temp_meio = safe_mean('MEIO')
    temp_inf = safe_mean('INFERIOR')
    temp_entrada = safe_mean('A1')
    tempo_c2 = safe_mean('C2')
    humidade = safe_mean('C4')
    pressao_ar = safe_mean('A e B')

    # ── Page header ──
    render_page_header(
        "TÊMPERA",
        f"Industrial · {total_registros:,} registros · Atualizado {get_horario_brasilia()}",
        THEME['accent_purple']
    )

    # KPIs principais
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("Total Peças", f"{total_pecas:,}".replace(",","."), THEME['accent_cyan'])
    with c2:
        render_kpi_card("Aprovadas", f"{total_aprovado:,}".replace(",","."), THEME['accent_lime'])
    with c3:
        render_kpi_card("Defeitos", f"{total_defeitos:,}".replace(",","."), THEME['accent_red'])
    with c4:
        trs_color = THEME['accent_lime'] if trs_medio >= 80 else THEME['accent_orange'] if trs_medio >= 70 else THEME['accent_red']
        render_kpi_card("TRS Médio", f"{trs_medio:.1f}%", trs_color)

    # Temperaturas Forno (médias ignorando zeros)
    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi_card("Temp. Superior", f"{temp_sup:.0f}°C" if temp_sup > 0 else "N/A", THEME['accent_orange'])
    with c2:
        render_kpi_card("Temp. Meio", f"{temp_meio:.0f}°C" if temp_meio > 0 else "N/A", THEME['accent_orange'])
    with c3:
        render_kpi_card("Temp. Inferior", f"{temp_inf:.0f}°C" if temp_inf > 0 else "N/A", THEME['accent_orange'])

    # Processo - Médias (ignorando zeros)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-family:JetBrains Mono,monospace;font-size:10px;color:{THEME['accent_purple']}';>▸ PROCESSO - MÉDIAS DO PERÍODO (ignorando zeros)</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("Temp. Entrada (A1)", f"{temp_entrada:.0f}°C" if temp_entrada > 0 else "N/A", THEME['accent_cyan'])
    with c2:
        render_kpi_card("Tempo (C2)", f"{tempo_c2:.0f}s" if tempo_c2 > 0 else "N/A", THEME['accent_lime'])
    with c3:
        render_kpi_card("Humidade (C4)", f"{humidade:.1f}%" if humidade > 0 else "N/A", THEME['accent_orange'])
    with c4:
        render_kpi_card("Pressão Ar (A e B)", f"{pressao_ar:.1f}" if pressao_ar > 0 else "N/A", THEME['accent_purple'])

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Tabela ──
    render_section_header("Registros de Têmpera", "▸", THEME['accent_purple'])
    
    df_display = df.sort_values(by="DATA", ascending=False).head(qtd if qtd > 0 else 100).copy()
    df_display['DATA'] = pd.to_datetime(df_display['DATA']).dt.strftime('%d/%m/%Y')
    df_display['TRS (%)'] = df_display['TRS (%)'].round(1).astype(str) + '%'
    
    colunas = ['DATA', 'TURNO_TEMP', 'PRODUTO', 'GANCHEIRA', 'APROVADO', 'TOTAL_DEFEITOS', 'TRS (%)']
    colunas = [c for c in colunas if c in df_display.columns]
    
    st.dataframe(df_display[colunas], use_container_width=True, height=400)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Gráfico TRS Diário ──
    render_section_header("Evolução Diária do TRS", "▸", THEME['accent_purple'])
    
    resumo_dia = df.groupby(df['DATA'].dt.date).agg({'APROVADO': 'sum'}).reset_index()
    resumo_dia['DATA'] = pd.to_datetime(resumo_dia['DATA'])
    counts = df.groupby(df['DATA'].dt.date).size().values
    resumo_dia['TRS (%)'] = (resumo_dia['APROVADO'] / (counts * 40) * 100)
    resumo_dia = resumo_dia.sort_values('DATA')
    
    if not resumo_dia.empty:
        fig, ax = plt.subplots(figsize=(12, 4), facecolor=THEME['bg_card'])
        apply_chart_style(ax, fig, "TRS Diário", ylabel="TRS (%)", accent=THEME['accent_purple'])
        ax.fill_between(resumo_dia['DATA'], 0, resumo_dia['TRS (%)'], alpha=0.12, color=THEME['accent_purple'])
        ax.plot(resumo_dia['DATA'], resumo_dia['TRS (%)'], marker='o', markersize=5, linewidth=2, color=THEME['accent_purple'])
        ax.axhline(y=80, color=THEME['accent_red'], linestyle=':', linewidth=1.5, label='Meta 80%')
        ax.legend(loc='upper right', fontsize=9)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha='right', fontsize=8)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    # ── PADRÃO DE EXCELÊNCIA (Média das TOP 15) ──
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("🏆 PADRÃO DE EXCELÊNCIA (Média Top 15)", "▸", THEME['accent_purple'])
    
    TOP_N = 15
    
    # Filtra produções válidas (com dados de pressão, se disponível)
    if 'A e B' in df.columns:
        df_validos = df[df['A e B'] > 0].copy()
    else:
        df_validos = df.copy()
    
    if len(df_validos) >= TOP_N:
        # Seleciona as TOP N produções com base no maior número de peças aprovadas
        df_top = df_validos.nlargest(TOP_N, ['APROVADO', 'TRS (%)'])
        
        # Calcula as médias
        media_aprovadas = df_top['APROVADO'].mean()
        media_trs = df_top['TRS (%)'].mean()
        media_defeitos = df_top['TOTAL_DEFEITOS'].mean()
        
        # Médias dos parâmetros de processo
        media_temp_sup = df_top['SUPERIOR'].mean()
        media_temp_meio = df_top['MEIO'].mean()
        media_temp_inf = df_top['INFERIOR'].mean()
        media_temp_entrada = df_top['A1'].mean()
        media_tempo_c2 = df_top['C2'].mean()
        media_humidade = df_top['C4'].mean()
        media_pressao_ar = df_top['A e B'].mean()
        
        # Desvio padrão para noção de estabilidade
        std_trs = df_top['TRS (%)'].std()
        criticas_top = df_top['IS_CRITICO'].sum()
        
        st.markdown(f"""
        <div style="background: {THEME['bg_card2']}; padding: 20px; border-radius: 10px; border-left: 4px solid {THEME['accent_lime']};">
            <h4 style="margin:0 0 5px 0; color:{THEME['accent_lime']};">🎯 Referência de Excelência</h4>
            <p style="margin:0 0 15px 0; font-size:12px; color:{THEME['text_muted']};">Média calculada com base nas {TOP_N} melhores produções do período</p>
        """, unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 TRS Médio (Top 15)", f"{media_trs:.1f}%", f"±{std_trs:.1f}%" if std_trs > 0 else "estável")
        with col2:
            st.metric("✅ Aprovadas (Média)", f"{media_aprovadas:.1f}/40")
        with col3:
            st.metric("❌ Defeitos (Média)", f"{media_defeitos:.1f}")
        with col4:
            st.metric("⚠️ Produções Críticas", f"{criticas_top}/{TOP_N}")
        
        st.markdown("<hr style='margin:15px 0; opacity:0.3;'>", unsafe_allow_html=True)
        
        st.markdown("#### 🔥 Temperaturas do Forno (Média)")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Superior", f"{media_temp_sup:.0f}°C" if pd.notna(media_temp_sup) else "N/A")
        with col2:
            st.metric("Meio", f"{media_temp_meio:.0f}°C" if pd.notna(media_temp_meio) else "N/A")
        with col3:
            st.metric("Inferior", f"{media_temp_inf:.0f}°C" if pd.notna(media_temp_inf) else "N/A")
        
        st.markdown("#### 📍 Principais Indicadores (Média)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Temp. Entrada (A1)", f"{media_temp_entrada:.0f}°C" if pd.notna(media_temp_entrada) else "N/A")
        with col2:
            st.metric("Tempo (C2)", f"{media_tempo_c2:.0f}s" if pd.notna(media_tempo_c2) else "N/A")
        with col3:
            st.metric("Humidade (C4)", f"{media_humidade:.1f}%" if pd.notna(media_humidade) else "N/A")
        with col4:
            st.metric("Pressão Ar (A e B)", f"{media_pressao_ar:.1f}" if pd.notna(media_pressao_ar) else "N/A")
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Expander com detalhes das Top 15
        with st.expander(f"🔍 Ver detalhes das {TOP_N} melhores produções"):
            st.markdown(f"**As {TOP_N} produções que definem o padrão de excelência:**")
            df_top_display = df_top[['DATA', 'TURNO_TEMP', 'PRODUTO', 'GANCHEIRA', 'APROVADO', 'TRS (%)', 'TOTAL_DEFEITOS']].copy()
            df_top_display['DATA'] = pd.to_datetime(df_top_display['DATA']).dt.strftime('%d/%m/%Y')
            df_top_display['TRS (%)'] = df_top_display['TRS (%)'].round(1).astype(str) + '%'
            st.dataframe(df_top_display, use_container_width=True, height=300)
            
            st.markdown("**📊 Estatísticas das Top 15 vs. Média Geral:**")
            media_geral_trs = (df_validos['APROVADO'].sum() / (len(df_validos) * 40) * 100) if len(df_validos) > 0 else 0
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Média Geral TRS", f"{media_geral_trs:.1f}%")
            with col2:
                ganho = media_trs - media_geral_trs
                st.metric("Ganho Potencial", f"+{ganho:.1f}%", delta_color="normal")
                
    elif len(df_validos) > 0:
        st.warning(f"Dados insuficientes para calcular a média das {TOP_N} melhores produções. Apenas {len(df_validos)} registros encontrados. Exibindo a melhor produção individual:")
        
        # Fallback: mostra a melhor produção individual
        idx_melhor = df_validos['APROVADO'].idxmax()
        melhor = df_validos.loc[idx_melhor]
        
        st.markdown(f"""
        <div style="background: {THEME['bg_card2']}; padding: 20px; border-radius: 10px; border-left: 4px solid {THEME['accent_lime']};">
            <h4 style="margin:0 0 15px 0; color:{THEME['accent_lime']};">🎯 Melhor Resultado Individual</h4>
        """, unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            data_str = pd.to_datetime(melhor['DATA']).strftime('%d/%m/%Y') if pd.notna(melhor['DATA']) else 'N/A'
            st.metric("📅 Data", data_str)
        with col2:
            st.metric("⏰ Turno", str(melhor.get('TURNO_TEMP', 'N/A')))
        with col3:
            st.metric("📦 Produto", str(melhor.get('PRODUTO', 'N/A'))[:15])
        with col4:
            st.metric("🔧 Gancheira", str(melhor.get('GANCHEIRA', 'N/A')))
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("✅ Aprovadas", f"{int(melhor['APROVADO'])}/40")
        with col2:
            st.metric("📊 TRS", f"{melhor['TRS (%)']:.1f}%")
        with col3:
            st.metric("❌ Defeitos", int(melhor['TOTAL_DEFEITOS']))
        with col4:
            criticos = "Sim" if melhor.get('IS_CRITICO', False) else "Não"
            st.metric("⚠️ Crítico", criticos)
        
        st.markdown("<hr style='margin:15px 0; opacity:0.3;'>", unsafe_allow_html=True)
        
        st.markdown("#### 🔥 Temperaturas do Forno")
        col1, col2, col3 = st.columns(3)
        with col1:
            val = melhor.get('SUPERIOR', 0)
            st.metric("Superior", f"{val:.0f}°C" if pd.notna(val) and val > 0 else "N/A")
        with col2:
            val = melhor.get('MEIO', 0)
            st.metric("Meio", f"{val:.0f}°C" if pd.notna(val) and val > 0 else "N/A")
        with col3:
            val = melhor.get('INFERIOR', 0)
            st.metric("Inferior", f"{val:.0f}°C" if pd.notna(val) and val > 0 else "N/A")
        
        st.markdown("#### 📍 Principais Indicadores")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            val = melhor.get('A1', 0)
            st.metric("Temp. Entrada (A1)", f"{val:.0f}°C" if pd.notna(val) and val > 0 else "N/A")
        with col2:
            val = melhor.get('C2', 0)
            st.metric("Tempo (C2)", f"{val:.0f}s" if pd.notna(val) and val > 0 else "N/A")
        with col3:
            val = melhor.get('C4', 0)
            st.metric("Humidade (C4)", f"{val:.1f}%" if pd.notna(val) and val > 0 else "N/A")
        with col4:
            val = melhor.get('A e B', 0)
            st.metric("Pressão Ar (A e B)", f"{val:.1f}" if pd.notna(val) and val > 0 else "N/A")
        
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Nenhum registro válido encontrado (Pressão Ar > 0).")

    # ── Ranking de Gancheiras (Pior → Melhor) ──
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("🏭 Ranking de Gancheiras (Pior → Melhor)", "▸", THEME['accent_purple'])
    
    if not df.empty and 'GANCHEIRA' in df.columns:
        ranking_gancheiras = []
        for gancheira in df['GANCHEIRA'].dropna().unique():
            df_g = df[df['GANCHEIRA'] == gancheira]
            total_registros_g = len(df_g)
            total_aprovado_g = int(df_g['APROVADO'].sum())
            total_defeitos_g = int(df_g['TOTAL_DEFEITOS'].sum())
            total_pecas_g = total_registros_g * 40
            trs_g = (total_aprovado_g / total_pecas_g * 100) if total_pecas_g > 0 else 0
            
            defeitos_gancheira = {}
            for codigo, nome in MAPEAMENTO_DEFEITOS.items():
                if codigo in CODIGOS_DEFEITO_REAIS:
                    nome_clean = nome.upper().replace(' ', '_').replace('Ç', 'C').replace('Ã', 'A').replace('Á', 'A').replace('Ó', 'O')
                    col = f'QTD_{nome_clean}'
                    if col in df_g.columns:
                        qtd = int(df_g[col].sum())
                        if qtd > 0:
                            defeitos_gancheira[nome] = qtd
            
            media_defeitos = total_defeitos_g / total_registros_g if total_registros_g > 0 else 0
            det_str = ' | '.join([f"{k}: {v}" for k, v in defeitos_gancheira.items()]) if defeitos_gancheira else "-"
            
            ranking_gancheiras.append({
                'Pos': 0,
                'Gancheira': str(gancheira),
                'Reg': total_registros_g,
                'Defeitos': total_defeitos_g,
                'Média': media_defeitos,
                'TRS_num': trs_g,
                'TRS': f"{trs_g:.1f}%",
                'Detalhamento': det_str
            })
        
        df_ranking = pd.DataFrame(ranking_gancheiras)
        df_ranking = df_ranking.sort_values('Defeitos', ascending=False)
        df_ranking['Pos'] = range(1, len(df_ranking) + 1)
        
        if not df_ranking.empty:
            piores = df_ranking.head(3)
            st.warning(f"⚠️ **Piores gancheiras:** {', '.join(piores['Gancheira'].tolist())}")
            
            df_tabela = df_ranking[['Pos', 'Gancheira', 'Reg', 'Defeitos', 'Média', 'TRS']].copy()
            df_tabela['Média'] = df_tabela['Média'].round(1)
            
            def estilo_ranking(row):
                styles = [''] * len(row)
                pos = row['Pos']
                if pos <= 3:
                    styles[0] = 'color: #E81123; font-weight: bold;'
                elif pos > len(df_ranking) - 3:
                    styles[0] = 'color: #107C10; font-weight: bold;'
                styles[3] = 'color: #E81123; font-weight: bold;'
                try:
                    trs_val = float(row['TRS'].replace('%', ''))
                    if trs_val >= 80:
                        styles[5] = 'color: #107C10; font-weight: bold;'
                    elif trs_val >= 70:
                        styles[5] = 'color: #E86C2C; font-weight: bold;'
                except:
                    pass
                return styles
            
            styled = df_tabela.style.apply(estilo_ranking, axis=1)
            st.dataframe(styled, use_container_width=True, height=250)
            
            with st.expander("🔍 Detalhamento das 5 Piores Gancheiras", expanded=False):
                for i, (_, row) in enumerate(df_ranking.head(5).iterrows(), 1):
                    st.markdown(f"""
                    **{i}º - Gancheira {row['Gancheira']}** | ❌ {row['Defeitos']} defeitos | TRS: {row['TRS']}  
                    📋 {row['Detalhamento']}
                    """)
            
            fig, ax = plt.subplots(figsize=(10, 3), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "Top 10 Piores Gancheiras", accent=THEME['accent_purple'])
            top10 = df_ranking.head(10)
            colors = [THEME['accent_red'] if i < 3 else THEME['accent_orange'] for i in range(len(top10))]
            ax.barh(range(len(top10)), top10['Defeitos'], color=colors, alpha=0.8)
            ax.set_yticks(range(len(top10)))
            ax.set_yticklabels(top10['Gancheira'])
            ax.invert_yaxis()
            ax.set_xlabel('Defeitos')
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("Sem dados de gancheiras disponíveis.")
    else:
        st.info("Coluna GANCHEIRA não encontrada.")

    # ── Análise de Posições da Pior Gancheira ──
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("🔧 Análise de Posições - Pior Gancheira", "▸", THEME['accent_purple'])
    
    if not df.empty and 'GANCHEIRA' in df.columns:
        ranking = []
        for g in df['GANCHEIRA'].dropna().unique():
            df_g = df[df['GANCHEIRA'] == g]
            ranking.append({'Gancheira': str(g), 'Defeitos': int(df_g['TOTAL_DEFEITOS'].sum()), 'Reg': len(df_g)})
        
        if ranking:
            df_rank = pd.DataFrame(ranking).sort_values('Defeitos', ascending=False)
            pior = df_rank.iloc[0]
            
            st.markdown(f"""
            <div style="background: {THEME['bg_card2']}; padding: 10px 15px; margin-bottom: 15px; border-left: 4px solid {THEME['accent_red']};">
                <span style="font-weight: bold; color: {THEME['accent_red']};">🔴 PIOR GANCHEIRA: {pior['Gancheira']}</span> | 
                {pior['Defeitos']} defeitos em {pior['Reg']} registros
            </div>
            """, unsafe_allow_html=True)
            
            df_pior = df[df['GANCHEIRA'] == pior['Gancheira']]
            posicoes_dados = []
            for col in df_base.columns:
                try:
                    num = int(str(col).strip())
                    if 11 <= num <= 78 and col in df_pior.columns:
                        contagem = {c: 0 for c in CODIGOS_DEFEITO_REAIS}
                        total = 0
                        for val in df_pior[col].dropna():
                            try:
                                cod = int(float(str(val).strip()))
                                if cod in CODIGOS_DEFEITO_REAIS:
                                    contagem[cod] += 1
                                    total += 1
                            except:
                                pass
                        if total > 0:
                            principal_cod = max(contagem, key=contagem.get)
                            principal_nome = MAPEAMENTO_DEFEITOS.get(principal_cod, '?')
                            posicoes_dados.append({
                                'Posição': num,
                                'Defeitos': total,
                                'Principal': f"{principal_nome[:20]} ({contagem[principal_cod]})"
                            })
                except:
                    pass
            
            if posicoes_dados:
                df_pos = pd.DataFrame(posicoes_dados).sort_values('Defeitos', ascending=False)
                total_def = df_pos['Defeitos'].sum()
                df_pos['%'] = (df_pos['Defeitos'] / total_def * 100).round(1)
                
                st.metric("Posições afetadas", len(df_pos))
                
                df_tabela_pos = df_pos[['Posição', 'Defeitos', '%', 'Principal']].head(15).copy()
                df_tabela_pos['%'] = df_tabela_pos['%'].astype(str) + '%'
                
                def estilo_pos(row):
                    styles = [''] * len(row)
                    defeitos = row['Defeitos']
                    if defeitos > 5:
                        styles[1] = 'color: #E81123; font-weight: bold;'
                    elif defeitos > 2:
                        styles[1] = 'color: #E86C2C; font-weight: bold;'
                    return styles
                
                styled_pos = df_tabela_pos.style.apply(estilo_pos, axis=1)
                st.dataframe(styled_pos, use_container_width=True, height=300)
                
                criticas = df_pos[df_pos['Defeitos'] > 5]['Posição'].tolist()
                alerta = df_pos[(df_pos['Defeitos'] >= 2) & (df_pos['Defeitos'] <= 5)]['Posição'].tolist()
                
                if criticas:
                    st.error(f"🚨 **Críticas (>5):** {', '.join(map(str, criticas))}")
                if alerta:
                    st.warning(f"⚠️ **Alerta (2-5):** {', '.join(map(str, alerta))}")
                if not criticas and not alerta:
                    st.success("✅ Nenhuma posição crítica ou em alerta")
                
                if len(df_pos) > 0:
                    fig, ax = plt.subplots(figsize=(10, 3), facecolor=THEME['bg_card'])
                    apply_chart_style(ax, fig, f"Posições com defeitos - Gancheira {pior['Gancheira']}", accent=THEME['accent_red'])
                    top = df_pos.head(20)
                    colors = [THEME['accent_red'] if d > 5 else THEME['accent_orange'] if d > 2 else THEME['accent_yellow'] for d in top['Defeitos']]
                    ax.barh(range(len(top)), top['Defeitos'], color=colors, alpha=0.8)
                    ax.set_yticks(range(len(top)))
                    ax.set_yticklabels(top['Posição'].astype(str))
                    ax.invert_yaxis()
                    ax.set_xlabel('Defeitos')
                    fig.tight_layout()
                    st.pyplot(fig)
                    plt.close(fig)
            else:
                st.info(f"Nenhum defeito nas posições da gancheira {pior['Gancheira']}.")
        else:
            st.info("Sem dados de gancheiras.")
    else:
        st.info("Coluna GANCHEIRA não encontrada.")

    # ── Comparativo por Turnos ──
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("📊 Comparativo por Turno", "▸", THEME['accent_purple'])
    
    if not df.empty and 'TURNO_TEMP' in df.columns:
        turnos = df['TURNO_TEMP'].dropna().unique()
        
        if len(turnos) > 0:
            dados_turnos = []
            for t in turnos:
                df_t = df[df['TURNO_TEMP'] == t]
                total_gancheiras = len(df_t)
                total_aprovado = int(df_t['APROVADO'].sum())
                total_defeitos = int(df_t['TOTAL_DEFEITOS'].sum())
                trs_medio_t = (total_aprovado / (total_gancheiras * 40) * 100) if total_gancheiras > 0 else 0
                
                dados_turnos.append({
                    'Turno': str(t),
                    'Gancheiras': total_gancheiras,
                    'Aprovados': total_aprovado,
                    'Defeitos': total_defeitos,
                    'TRS_num': trs_medio_t,
                    'TRS': f"{trs_medio_t:.1f}%"
                })
            
            df_turnos = pd.DataFrame(dados_turnos)
            df_turnos = df_turnos.sort_values('TRS_num', ascending=False)
            
            df_tabela_turno = df_turnos[['Turno', 'Gancheiras', 'Aprovados', 'Defeitos', 'TRS']].copy()
            
            def estilo_turno(row):
                styles = [''] * len(row)
                try:
                    trs_val = float(row['TRS'].replace('%', ''))
                    if trs_val >= 80:
                        styles[4] = 'color: #107C10; font-weight: bold;'
                    elif trs_val >= 70:
                        styles[4] = 'color: #E86C2C; font-weight: bold;'
                    else:
                        styles[4] = 'color: #E81123; font-weight: bold;'
                except:
                    pass
                styles[2] = 'color: #107C10;'
                styles[3] = 'color: #E81123;'
                return styles
            
            styled_turno = df_tabela_turno.style.apply(estilo_turno, axis=1)
            st.dataframe(styled_turno, use_container_width=True, height=150)
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig, ax = plt.subplots(figsize=(5, 3.5), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "Aprovados vs Defeitos", accent=THEME['accent_purple'])
                x = range(len(df_turnos))
                width = 0.35
                bars1 = ax.bar([i - width/2 for i in x], df_turnos['Aprovados'], width, label='Aprovados', color=THEME['accent_lime'], alpha=0.8)
                bars2 = ax.bar([i + width/2 for i in x], df_turnos['Defeitos'], width, label='Defeitos', color=THEME['accent_red'], alpha=0.8)
                ax.set_xticks(x)
                ax.set_xticklabels(df_turnos['Turno'], fontsize=9)
                ax.legend(loc='upper right', fontsize=8)
                for bar in bars1:
                    h = bar.get_height()
                    if h > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, h + 5, f'{int(h)}', ha='center', va='bottom', fontsize=7, color=THEME['accent_lime'])
                for bar in bars2:
                    h = bar.get_height()
                    if h > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, h + 2, f'{int(h)}', ha='center', va='bottom', fontsize=7, color=THEME['accent_red'])
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            
            with col2:
                fig2, ax2 = plt.subplots(figsize=(5, 3.5), facecolor=THEME['bg_card'])
                apply_chart_style(ax2, fig2, "TRS por Turno", ylabel="TRS (%)", accent=THEME['accent_purple'])
                cores_turno = {'M': THEME['accent_cyan'], 'T': THEME['accent_orange'], 'N': THEME['accent_lime']}
                bar_colors = [cores_turno.get(str(t), THEME['accent_purple']) for t in df_turnos['Turno']]
                bars = ax2.bar(range(len(df_turnos)), df_turnos['TRS_num'], color=bar_colors, alpha=0.88, edgecolor=THEME['bg_card'], linewidth=1.5, width=0.55)
                ax2.axhline(y=80, color=THEME['accent_red'], linestyle='--', alpha=0.5, linewidth=1.5, label='Meta 80%')
                for i, (_, row) in enumerate(df_turnos.iterrows()):
                    ax2.text(i, row['TRS_num'] + 1, f"{row['TRS_num']:.1f}%", ha='center', va='bottom', fontweight='bold', fontsize=9, color=THEME['text_primary'])
                ax2.set_xticks(range(len(df_turnos)))
                ax2.set_xticklabels(df_turnos['Turno'], fontsize=10)
                ax2.set_ylim(0, 105)
                ax2.legend(loc='upper right', fontsize=8)
                fig2.tight_layout()
                st.pyplot(fig2)
                plt.close(fig2)
            
            melhor_turno = df_turnos.iloc[0]
            pior_turno = df_turnos.iloc[-1]
            st.info(f"🏆 **Melhor turno:** {melhor_turno['Turno']} ({melhor_turno['TRS']}) | ⚠️ **Pior turno:** {pior_turno['Turno']} ({pior_turno['TRS']})")
        else:
            st.info("Sem dados de turno disponíveis.")
    else:
        st.info("Coluna TURNO_TEMP não encontrada.")

    # ── Defeitos por Tipo ──
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("Defeitos por Tipo", "▸", THEME['accent_purple'])
    
    defeitos_totais = {}
    for codigo, nome in MAPEAMENTO_DEFEITOS.items():
        nome_clean = nome.upper().replace(' ', '_').replace('Ç', 'C').replace('Ã', 'A').replace('Á', 'A').replace('Ó', 'O')
        col = f'QTD_{nome_clean}'
        if col in df.columns:
            total = int(df[col].sum())
            if total > 0:
                defeitos_totais[nome] = total
    
    if defeitos_totais:
        df_def = pd.DataFrame(list(defeitos_totais.items()), columns=['Defeito', 'Qtd']).sort_values('Qtd', ascending=False)
        
        fig, ax = plt.subplots(figsize=(10, 3), facecolor=THEME['bg_card'])
        apply_chart_style(ax, fig, "", accent=THEME['accent_purple'])
        
        colors = [THEME['accent_lime'] if 'Estourou' in d else THEME['accent_red'] for d in df_def['Defeito']]
        bars = ax.bar(range(len(df_def)), df_def['Qtd'], color=colors, alpha=0.8)
        ax.set_xticks(range(len(df_def)))
        ax.set_xticklabels(df_def['Defeito'], rotation=30, ha='right', fontsize=8)
        
        for bar, v in zip(bars, df_def['Qtd']):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(v), ha='center', fontsize=9)
        
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info("Nenhum defeito registrado.")

# ==================================================================================================
# AVISO DE REJEIÇÃO (AR)
# ==================================================================================================
elif aba_selecionada == 'AVISO DE REJEIÇÃO':
    render_page_header("AVISO DE REJEIÇÃO", f"CQ-018 REV004 · Atualizado {get_horario_brasilia()}", THEME['accent_red'])
    
    # Adicionar a opção "NÃO RESPONDIDO" nas opções de decisão
    OPCOES_DECISAO_AR_MOD = ["APROVADO CONDICIONAL", "REPROVADO", "EM ANÁLISE", "NÃO RESPONDIDO"]
    
    with st.container():
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%); padding: 15px 20px; border-radius: 10px; border-left: 4px solid {THEME['accent_red']}; margin: 20px 0;">
            <span style="font-size: 20px; margin-right: 10px;">📋</span>
            <span style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: bold; color: {THEME['accent_red']};">AVISO DE REJEIÇÃO - CQ-018</span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {THEME['text_muted']}; margin-left: 15px;">Sistema de Gestão da Qualidade</span>
        </div>
        """, unsafe_allow_html=True)
        
        menu_ar = st.radio("Opções do AR:", ["📝 Novo Registro", "📊 Visualizar Registros", "🔍 Buscar/Editar/Excluir", "📈 Dashboard AR"], horizontal=True, key="menu_ar_principal")
        
        if 'ar_pdf_bytes' not in st.session_state:
            st.session_state.ar_pdf_bytes = None
        if 'ar_pdf_nome' not in st.session_state:
            st.session_state.ar_pdf_nome = None
        if 'ar_mostrar_pdf' not in st.session_state:
            st.session_state.ar_mostrar_pdf = False
        if 'ar_ultimo_registro' not in st.session_state:
            st.session_state.ar_ultimo_registro = None
        if 'ar_etapa_confirmacao' not in st.session_state:
            st.session_state.ar_etapa_confirmacao = 1
        if 'ar_confirmar_email' not in st.session_state:
            st.session_state.ar_confirmar_email = None
        if 'ar_confirmar_imprimir' not in st.session_state:
            st.session_state.ar_confirmar_imprimir = None
        if 'ar_registro_editando' not in st.session_state:
            st.session_state.ar_registro_editando = None
        
        # Função para obter horário de Brasília
        def get_horario_brasilia_ar():
            from datetime import timezone, timedelta
            utc_now = datetime.now(timezone.utc)
            brasilia_offset = timezone(timedelta(hours=-3))
            agora_brasilia = utc_now.astimezone(brasilia_offset)
            return agora_brasilia
        
        # Função para EXCLUIR registro do Google Sheets
        def excluir_registro_ar(numero: int) -> bool:
            """Exclui registro do Google Sheets"""
            try:
                client = get_gspread_client()
                if client is None:
                    st.error("❌ Não foi possível conectar ao Google Sheets")
                    return False
                
                sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
                
                celula = sheet.find(str(numero), in_column=1)
                if celula:
                    sheet.delete_rows(celula.row)
                    return True
                else:
                    st.warning(f"⚠️ Registro Nº {numero} não encontrado no Google Sheets")
                    return False
                    
            except Exception as e:
                st.error(f"❌ Erro ao excluir registro: {str(e)}")
                return False
        
        # Função para ALTERAR registro no Google Sheets
        def atualizar_registro_ar(registro: RegistroAR) -> bool:
            """Atualiza registro existente no Google Sheets"""
            try:
                client = get_gspread_client()
                if client is None:
                    st.error("❌ Não foi possível conectar ao Google Sheets")
                    return False
                
                sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
                
                celula = sheet.find(str(registro.numero), in_column=1)
                if celula:
                    linha = celula.row
                    
                    dados = [
                        str(registro.numero),
                        registro.data.strftime("%d/%m/%Y") if registro.data else "",
                        registro.hora,
                        registro.codigo,
                        registro.emissor,
                        registro.referencia,
                        registro.decisao,
                        registro.descricao,
                        registro.status,
                        registro.disposicao,
                        registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else "",
                        registro.turno
                    ]
                    
                    for col, valor in enumerate(dados, start=1):
                        sheet.update_cell(linha, col, valor)
                    
                    return True
                else:
                    st.warning(f"⚠️ Registro Nº {registro.numero} não encontrado para atualização")
                    return False
                    
            except Exception as e:
                st.error(f"❌ Erro ao atualizar registro: {str(e)}")
                return False
        
        # Função para abrir PDF no navegador e imprimir
        def imprimir_pdf_ar(pdf_bytes: bytes, nome_arquivo: str):
            """Abre o PDF em nova aba para impressão via navegador"""
            try:
                import base64
                import webbrowser
                from datetime import datetime
                
                if not nome_arquivo.lower().endswith('.pdf'):
                    nome_arquivo = nome_arquivo + '.pdf'
                
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>{nome_arquivo}</title>
                    <meta charset="UTF-8">
                    <style>
                        body {{
                            margin: 0;
                            padding: 0;
                            height: 100vh;
                            display: flex;
                            flex-direction: column;
                            font-family: Arial, sans-serif;
                        }}
                        .toolbar {{
                            background: #2c3e50;
                            padding: 12px 20px;
                            text-align: center;
                            border-bottom: 2px solid #3498db;
                            display: flex;
                            justify-content: center;
                            gap: 15px;
                            flex-wrap: wrap;
                        }}
                        button {{
                            padding: 10px 24px;
                            margin: 0 5px;
                            cursor: pointer;
                            background: #3498db;
                            color: white;
                            border: none;
                            border-radius: 6px;
                            font-size: 14px;
                            font-weight: bold;
                            transition: all 0.3s ease;
                        }}
                        button:hover {{
                            background: #2980b9;
                            transform: scale(1.02);
                        }}
                        .info {{
                            background: #ecf0f1;
                            padding: 8px 16px;
                            border-radius: 6px;
                            color: #2c3e50;
                            font-size: 13px;
                            display: flex;
                            align-items: center;
                            gap: 10px;
                        }}
                        .info span {{
                            font-weight: bold;
                        }}
                        embed {{
                            width: 100%;
                            height: calc(100vh - 70px);
                        }}
                        @media print {{
                            .toolbar {{
                                display: none;
                            }}
                            embed {{
                                height: 100vh;
                            }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="toolbar">
                        <button onclick="window.print()">🖨️ IMPRIMIR (Ctrl+P)</button>
                        <button onclick="window.close()">❌ FECHAR</button>
                        <div class="info">
                            <span>📄 {nome_arquivo}</span>
                            <span>|</span>
                            <span>💡 Pressione Ctrl+P para imprimir</span>
                        </div>
                    </div>
                    <embed src="data:application/pdf;base64,{pdf_base64}" type="application/pdf">
                    <script>
                        setTimeout(function() {{
                            window.print();
                        }}, 1000);
                    </script>
                </body>
                </html>
                """
                
                temp_html = os.path.join(CAMINHO_PDF_AR, f"temp_print_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
                with open(temp_html, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                webbrowser.open(f'file://{temp_html}')
                
                import threading
                def limpar_arquivo():
                    import time
                    time.sleep(30)
                    try:
                        if os.path.exists(temp_html):
                            os.remove(temp_html)
                    except:
                        pass
                
                threading.Thread(target=limpar_arquivo, daemon=True).start()
                
                return True, "PDF aberto no navegador. A impressão será iniciada automaticamente ou pressione Ctrl+P."
                
            except Exception as e:
                return False, f"Erro ao abrir PDF: {str(e)}"
        
        # ======================
        # FUNÇÃO PARA DASHBOARD AR
        # ======================
        def gerar_dashboard_ar(registros):
            """Gera dashboard com estatísticas dos ARs"""
            if not registros:
                st.info("📭 Nenhum registro encontrado para análise.")
                return
            
            # Estatísticas gerais
            total_registros = len(registros)
            abertos = len([r for r in registros if r.status == "ABERTO"])
            finalizados = len([r for r in registros if r.status == "FINALIZADO"])
            nao_respondidos = len([r for r in registros if r.status == "NÃO RESPONDIDA"])
            
            # Distribuição por decisão
            decisao_counts = {}
            for d in OPCOES_DECISAO_AR_MOD:
                decisao_counts[d] = len([r for r in registros if r.decisao == d])
            
            # Distribuição por turno
            turno_counts = {}
            for t in OPCOES_TURNO_AR:
                turno_counts[t] = len([r for r in registros if r.turno == t])
            
            # NOVO: Estatísticas por Turno com status (ABERTO, FINALIZADO, NÃO RESPONDIDA)
            turno_status = {}
            for t in OPCOES_TURNO_AR:
                registros_turno = [r for r in registros if r.turno == t]
                turno_status[t] = {
                    'ABERTO': len([r for r in registros_turno if r.status == "ABERTO"]),
                    'FINALIZADO': len([r for r in registros_turno if r.status == "FINALIZADO"]),
                    'NÃO RESPONDIDA': len([r for r in registros_turno if r.status == "NÃO RESPONDIDA"])
                }
            
            # Top emissores
            emissor_counts = {}
            for r in registros:
                emissor_counts[r.emissor] = emissor_counts.get(r.emissor, 0) + 1
            top_emissores = sorted(emissor_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Top referências com mais rejeições
            referencia_counts = {}
            for r in registros:
                ref = r.referencia[:30] if len(r.referencia) > 30 else r.referencia
                referencia_counts[ref] = referencia_counts.get(ref, 0) + 1
            top_referencias = sorted(referencia_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # KPIs
            st.subheader("📊 Indicadores Gerais")
            col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
            with col_k1:
                st.metric("📋 Total ARs", total_registros)
            with col_k2:
                st.metric("🟡 Em Aberto", abertos)
            with col_k3:
                st.metric("🟢 Finalizados", finalizados)
            with col_k4:
                st.metric("🔴 Não Respondidos", nao_respondidos)
            with col_k5:
                perc_finalizado = (finalizados / total_registros * 100) if total_registros > 0 else 0
                st.metric("✅ Taxa Finalização", f"{perc_finalizado:.1f}%")
            
            st.markdown("<hr>", unsafe_allow_html=True)
            
            # NOVO GRÁFICO: Status por Turno (Barras agrupadas)
            st.subheader("📊 Status dos ARs por Turno")
            
            # Preparar dados para o gráfico de barras agrupadas
            turnos_lista = list(turno_status.keys())
            abertos_lista = [turno_status[t]['ABERTO'] for t in turnos_lista]
            finalizados_lista = [turno_status[t]['FINALIZADO'] for t in turnos_lista]
            nao_respondidos_lista = [turno_status[t]['NÃO RESPONDIDA'] for t in turnos_lista]
            
            fig, ax = plt.subplots(figsize=(10, 6), facecolor=THEME['bg_card'])
            apply_chart_style(ax, fig, "ARs por Turno e Status", ylabel="Quantidade")
            
            x = np.arange(len(turnos_lista))
            width = 0.25
            
            bars1 = ax.bar(x - width, abertos_lista, width, label='🟡 Em Aberto', color='#ffc107', alpha=0.85, edgecolor='white', linewidth=1)
            bars2 = ax.bar(x, finalizados_lista, width, label='🟢 Finalizados', color='#28a745', alpha=0.85, edgecolor='white', linewidth=1)
            bars3 = ax.bar(x + width, nao_respondidos_lista, width, label='🔴 Não Respondidos', color='#dc3545', alpha=0.85, edgecolor='white', linewidth=1)
            
            # Adicionar valores nas barras
            for bars in [bars1, bars2, bars3]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                                f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
            
            ax.set_xticks(x)
            ax.set_xticklabels(turnos_lista, fontsize=11, fontweight='bold')
            ax.set_ylabel("Quantidade", fontsize=11)
            ax.legend(loc='upper right', fontsize=10)
            ax.set_ylim(0, max(max(abertos_lista), max(finalizados_lista), max(nao_respondidos_lista)) * 1.15)
            
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
            
            st.markdown("<hr>", unsafe_allow_html=True)
            
            # Gráficos
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.subheader("📊 Distribuição por Decisão")
                fig, ax = plt.subplots(figsize=(6, 4), facecolor=THEME['bg_card'])
                
                decisao_labels = list(decisao_counts.keys())
                decisao_valores = list(decisao_counts.values())
                cores_decisao = ['#107C10' if 'APROVADO' in d else '#E81123' if 'REPROVADO' in d else '#FFB900' if 'EM ANÁLISE' in d else '#9E9E9E' for d in decisao_labels]
                
                bars = ax.bar(range(len(decisao_labels)), decisao_valores, color=cores_decisao, alpha=0.8)
                ax.set_xticks(range(len(decisao_labels)))
                ax.set_xticklabels(decisao_labels, rotation=25, ha='right', fontsize=9)
                ax.set_ylabel("Quantidade")
                ax.set_title("ARs por Decisão")
                
                for bar, val in zip(bars, decisao_valores):
                    if val > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(val), ha='center', va='bottom', fontsize=10, fontweight='bold')
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            
            with col_g2:
                st.subheader("🕐 Distribuição por Turno")
                fig, ax = plt.subplots(figsize=(5, 4), facecolor=THEME['bg_card'])
                
                turno_labels = list(turno_counts.keys())
                turno_valores = list(turno_counts.values())
                cores_turno = {'Manhã': '#0078D4', 'Tarde': '#E86C2C', 'Noite': '#6B46C1'}
                cores_graf = [cores_turno.get(t, '#9E9E9E') for t in turno_labels]
                
                bars = ax.bar(range(len(turno_labels)), turno_valores, color=cores_graf, alpha=0.8)
                ax.set_xticks(range(len(turno_labels)))
                ax.set_xticklabels(turno_labels, fontsize=10)
                ax.set_ylabel("Quantidade")
                ax.set_title("ARs por Turno")
                
                for bar, val in zip(bars, turno_valores):
                    if val > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(val), ha='center', va='bottom', fontsize=10, fontweight='bold')
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            
            # Status dos ARs (Gráfico de Pizza)
            st.subheader("📈 Status dos ARs")
            col_p1, col_p2 = st.columns([1, 1])
            
            with col_p1:
                fig, ax = plt.subplots(figsize=(5, 4), facecolor=THEME['bg_card'])
                status_labels = ['ABERTO', 'FINALIZADO', 'NÃO RESPONDIDA']
                status_valores = [abertos, finalizados, nao_respondidos]
                status_cores = ['#ffc107', '#28a745', '#dc3545']
                
                valores_validos = [(l, v, c) for l, v, c in zip(status_labels, status_valores, status_cores) if v > 0]
                
                if valores_validos:
                    labels, sizes, colors_pie = zip(*valores_validos)
                    wedges, texts, autotexts = ax.pie(
                        sizes, labels=labels, colors=colors_pie,
                        autopct='%1.1f%%', startangle=90,
                        textprops={'fontsize': 9}
                    )
                    for autotext in autotexts:
                        autotext.set_color('white')
                        autotext.set_fontweight('bold')
                    ax.set_title('Distribuição por Status', fontweight='bold', fontsize=12)
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            
            with col_p2:
                if top_emissores:
                    st.subheader("👥 Top 5 Emissores")
                    fig, ax = plt.subplots(figsize=(5, 3.5), facecolor=THEME['bg_card'])
                    emissores, quantidades = zip(*top_emissores)
                    bars = ax.barh(range(len(emissores)), quantidades, color=THEME['accent_cyan'], alpha=0.8)
                    ax.set_yticks(range(len(emissores)))
                    ax.set_yticklabels([e[:20] for e in emissores], fontsize=9)
                    ax.set_xlabel("Quantidade de ARs")
                    ax.invert_yaxis()
                    for bar, val in zip(bars, quantidades):
                        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height()/2, str(val), va='center', fontsize=9, fontweight='bold')
                    fig.tight_layout()
                    st.pyplot(fig)
                    plt.close(fig)
            
            # Top referências com mais rejeições
            if top_referencias:
                st.subheader("🏷️ Top 5 Referências com Mais Rejeições")
                df_ref = pd.DataFrame(top_referencias, columns=['Referência', 'Quantidade'])
                df_ref = df_ref.sort_values('Quantidade', ascending=False)
                
                fig, ax = plt.subplots(figsize=(8, 4), facecolor=THEME['bg_card'])
                bars = ax.bar(range(len(df_ref)), df_ref['Quantidade'], color=THEME['accent_red'], alpha=0.8)
                ax.set_xticks(range(len(df_ref)))
                ax.set_xticklabels(df_ref['Referência'], rotation=25, ha='right', fontsize=9)
                ax.set_ylabel("Quantidade de ARs")
                ax.set_title("Referências com Mais Rejeições")
                
                for bar, val in zip(bars, df_ref['Quantidade']):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(val), ha='center', va='bottom', fontsize=10, fontweight='bold')
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            
            # Evolução diária
            st.subheader("📅 Evolução Diária de ARs")
            
            datas_dict = {}
            for r in registros:
                if r.data:
                    data_str = r.data.strftime("%d/%m/%Y")
                    if data_str not in datas_dict:
                        datas_dict[data_str] = {'total': 0, 'abertos': 0, 'finalizados': 0}
                    datas_dict[data_str]['total'] += 1
                    if r.status == "ABERTO":
                        datas_dict[data_str]['abertos'] += 1
                    elif r.status == "FINALIZADO":
                        datas_dict[data_str]['finalizados'] += 1
            
            if datas_dict:
                datas_ordenadas = sorted(datas_dict.keys(), key=lambda x: datetime.strptime(x, "%d/%m/%Y"))
                totais = [datas_dict[d]['total'] for d in datas_ordenadas]
                abertos_dia = [datas_dict[d]['abertos'] for d in datas_ordenadas]
                finalizados_dia = [datas_dict[d]['finalizados'] for d in datas_ordenadas]
                
                fig, ax = plt.subplots(figsize=(10, 4), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "ARs por Dia", ylabel="Quantidade")
                
                x = range(len(datas_ordenadas))
                ax.plot(x, totais, marker='o', linewidth=2, color=THEME['accent_red'], label='Total ARs')
                ax.plot(x, abertos_dia, marker='s', linewidth=2, color=THEME['accent_orange'], label='Em Aberto')
                ax.plot(x, finalizados_dia, marker='^', linewidth=2, color=THEME['accent_lime'], label='Finalizados')
                
                ax.set_xticks(x)
                ax.set_xticklabels(datas_ordenadas, rotation=35, ha='right', fontsize=8)
                ax.legend(loc='upper left', fontsize=9)
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            
            # Tabela de registros recentes
            st.subheader("📋 Últimos 10 Registros")
            registros_recentes = sorted(registros, key=lambda x: x.data if x.data else datetime.min, reverse=True)[:10]
            
            dados_tabela = []
            for r in registros_recentes:
                dados_tabela.append({
                    "Nº": r.numero,
                    "Data": r.data.strftime("%d/%m/%Y") if r.data else "-",
                    "Referência": r.referencia[:35] + "..." if len(r.referencia) > 35 else r.referencia,
                    "Decisão": r.decisao,
                    "Status": r.status,
                    "Turno": r.turno,
                    "Emissor": r.emissor
                })
            
            if dados_tabela:
                df_tabela = pd.DataFrame(dados_tabela)
                st.dataframe(df_tabela, use_container_width=True, height=300)
        
        # ======================
        # NOVO REGISTRO
        # ======================
        if menu_ar == "📝 Novo Registro":
            st.subheader("Novo Aviso de Rejeição")
            st.info("⚠️ Data e hora serão preenchidas automaticamente no salvamento (Horário de Brasília)")
            
            if st.session_state.ar_mostrar_pdf and st.session_state.ar_pdf_bytes:
                st.success(f"✅ Registro salvo com sucesso!")
                if st.session_state.ar_ultimo_registro:
                    reg = st.session_state.ar_ultimo_registro
                    with st.expander("📋 Ver detalhes do registro salvo", expanded=True):
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            st.write(f"**Número:** {reg.numero}")
                            st.write(f"**Data:** {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                            st.write(f"**Hora:** {reg.hora}")
                            st.write(f"**Turno:** {reg.turno}")
                            st.write(f"**Código:** {reg.codigo}")
                            # Exibir informações da biblioteca se houver
                            if reg.defeito_biblioteca:
                                st.write(f"**📚 Defeito Biblioteca:** {reg.defeito_biblioteca}")
                        with col_d2:
                            st.write(f"**Emissor:** {reg.emissor}")
                            st.write(f"**Referência:** {reg.referencia[:50]}...")
                            st.write(f"**Decisão:** {reg.decisao}")
                            st.write(f"**Status:** {reg.status}")
                            if reg.sugestao_biblioteca:
                                st.write(f"**💡 Sugestão:** {reg.sugestao_biblioteca[:50]}...")
                            if reg.direcionamento_biblioteca:
                                st.write(f"**🎯 Direcionamento:** {reg.direcionamento_biblioteca[:50]}...")
                st.markdown("---")
                st.subheader("📋 Confirmações")
                
                if st.session_state.ar_etapa_confirmacao == 1:
                    st.markdown("#### 📧 Etapa 1 de 2")
                    st.write("Deseja enviar este documento por E-MAIL?")
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Sim, enviar e-mail", use_container_width=True):
                            st.session_state.ar_confirmar_email = True
                            st.session_state.ar_etapa_confirmacao = 2
                            st.rerun()
                    with col_btn2:
                        if st.button("❌ Não, pular", use_container_width=True):
                            st.session_state.ar_confirmar_email = False
                            st.session_state.ar_etapa_confirmacao = 2
                            st.rerun()
                elif st.session_state.ar_etapa_confirmacao == 2:
                    if st.session_state.ar_confirmar_email:
                        with st.spinner("Enviando e-mail..."):
                            assunto = f"Aviso de Rejeição - AR {st.session_state.ar_ultimo_registro.numero if st.session_state.ar_ultimo_registro else ''} - {datetime.now().strftime('%d/%m/%Y')}"
                            
                            # Construir corpo do e-mail com informações da biblioteca
                            corpo = f"""Prezados,
                            
Segue em anexo o Aviso de Rejeição.

Número: {st.session_state.ar_ultimo_registro.numero if st.session_state.ar_ultimo_registro else ''}
Data: {datetime.now().strftime('%d/%m/%Y')}
Referência: {st.session_state.ar_ultimo_registro.referencia if st.session_state.ar_ultimo_registro else ''}
"""
                            # Adicionar informações da biblioteca se houver
                            if st.session_state.ar_ultimo_registro and st.session_state.ar_ultimo_registro.defeito_biblioteca:
                                corpo += f"""
Defeito identificado: {st.session_state.ar_ultimo_registro.defeito_biblioteca}
"""
                            if st.session_state.ar_ultimo_registro and st.session_state.ar_ultimo_registro.sugestao_biblioteca:
                                corpo += f"""
Sugestão: {st.session_state.ar_ultimo_registro.sugestao_biblioteca}
"""
                            if st.session_state.ar_ultimo_registro and st.session_state.ar_ultimo_registro.direcionamento_biblioteca:
                                corpo += f"""
Direcionamento: {st.session_state.ar_ultimo_registro.direcionamento_biblioteca}
"""
                            
                            corpo += """
                            
Atenciosamente,
Sistema de Gestão da Qualidade - Luvidarte"""
                            
                            if enviar_email_ar(EMAIL_CONFIG_AR["destinatarios"], assunto, corpo, st.session_state.ar_pdf_bytes, st.session_state.ar_pdf_nome):
                                st.success("📧 E-mail enviado com sucesso!")
                            else:
                                st.error("❌ Erro ao enviar e-mail")
                    import time as time_module
                    time_module.sleep(1)
                    st.session_state.ar_etapa_confirmacao = 3
                    st.rerun()
                elif st.session_state.ar_etapa_confirmacao == 3:
                    st.markdown("#### 🖨️ Etapa 2 de 2")
                    st.write("Deseja IMPRIMIR uma cópia deste documento?")
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Sim, imprimir", use_container_width=True):
                            st.session_state.ar_confirmar_imprimir = True
                            st.session_state.ar_etapa_confirmacao = 4
                            st.rerun()
                    with col_btn2:
                        if st.button("❌ Não, pular", use_container_width=True):
                            st.session_state.ar_confirmar_imprimir = False
                            st.session_state.ar_etapa_confirmacao = 4
                            st.rerun()
                elif st.session_state.ar_etapa_confirmacao == 4:
                    if st.session_state.ar_confirmar_imprimir:
                        with st.spinner("Abrindo PDF para impressão..."):
                            success, msg = imprimir_pdf_ar(st.session_state.ar_pdf_bytes, st.session_state.ar_pdf_nome)
                            if success:
                                st.success(f"🖨️ {msg}")
                            else:
                                st.warning(f"⚠️ {msg}")
                    st.markdown("---")
                    st.subheader("✅ Processo concluído!")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(label="📥 Baixar PDF do Registro", data=st.session_state.ar_pdf_bytes, file_name=st.session_state.ar_pdf_nome, mime="application/pdf", use_container_width=True)
                    with col2:
                        if st.button("➕ Novo Registro", use_container_width=True):
                            st.session_state.ar_pdf_bytes = None
                            st.session_state.ar_pdf_nome = None
                            st.session_state.ar_mostrar_pdf = False
                            st.session_state.ar_ultimo_registro = None
                            st.session_state.ar_etapa_confirmacao = 1
                            st.session_state.ar_confirmar_email = None
                            st.session_state.ar_confirmar_imprimir = None
                            st.rerun()
            else:
                with st.form("novo_registro_ar_principal"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        proximo = obter_proximo_numero_ar()
                        st.info(f"📌 Próximo número disponível: {proximo}")
                        usar_auto = st.checkbox("Usar número automático", value=True)
                        if usar_auto:
                            numero = proximo
                            st.text_input("Número do AR", value=str(numero), disabled=True)
                        else:
                            numero = st.number_input("Número do AR", min_value=1, step=1)
                        turno = st.selectbox("Turno", OPCOES_TURNO_AR)
                    with col2:
                        codigo = st.text_input("Código*")
                        emissor = st.text_input("Emissor*")
                        referencia = st.text_area("Referência*", height=80)
                        decisao = st.selectbox("Decisão*", OPCOES_DECISAO_AR_MOD)
                    with col3:
                        status = st.selectbox("Status*", OPCOES_STATUS_AR)
                        descricao = st.text_area("Descrição do Problema*", height=120)
                        disposicao = st.text_area("Disposição", height=80)
                        data_finalizacao = st.date_input("Data de Finalização", datetime.now())
                    
                    # ===== BIBLIOTECA DE DEFEITOS CONHECIDOS =====
                    st.markdown("---")
                    st.markdown("### 📚 Biblioteca de Defeitos Conhecidos")
                    st.caption("Selecione um defeito da biblioteca para obter sugestões e direcionamentos (opcional)")
                    
                    # Carregar biblioteca
                    biblioteca_defeitos = carregar_biblioteca_defeitos()
                    opcoes_defeitos = [""] + sorted(list(biblioteca_defeitos.keys()))
                    
                    defeito_selecionado = st.selectbox(
                        "🔍 Defeito",
                        options=opcoes_defeitos,
                        key="ar_defeito_biblioteca",
                        help="Selecione um defeito conhecido da biblioteca"
                    )
                    
                    # Mostrar informações da biblioteca se um defeito foi selecionado
                    sugestao_bib = ""
                    direcionamento_bib = ""
                    defeito_bib = ""
                    
                    if defeito_selecionado and defeito_selecionado in biblioteca_defeitos:
                        info = biblioteca_defeitos[defeito_selecionado]
                        defeito_bib = defeito_selecionado
                        sugestao_bib = info.get('sugestao', '')
                        direcionamento_bib = info.get('direcionamento', '')
                        
                        if sugestao_bib:
                            st.info(f"💡 **Sugestão:** {sugestao_bib}")
                        if direcionamento_bib:
                            st.info(f"🎯 **Direcionamento:** {direcionamento_bib}")
                    
                    st.markdown("---")
                    
                    submitted = st.form_submit_button("💾 SALVAR REGISTRO", type="primary", use_container_width=True)
                    
                    if submitted:
                        if not codigo or not emissor or not referencia or not descricao:
                            st.error("❌ Preencha todos os campos obrigatórios (*)")
                        else:
                            agora_brasilia = get_horario_brasilia_ar()
                            
                            # Criar registro com os dados da biblioteca
                            registro = RegistroAR(
                                numero=numero, 
                                data=agora_brasilia.date(), 
                                hora=agora_brasilia.strftime("%H:%M:%S"), 
                                codigo=codigo, 
                                emissor=emissor, 
                                referencia=referencia, 
                                decisao=decisao, 
                                descricao=descricao, 
                                status=status, 
                                disposicao=disposicao, 
                                data_finalizacao=data_finalizacao, 
                                turno=turno,
                                # Campos da biblioteca
                                defeito_biblioteca=defeito_bib,
                                sugestao_biblioteca=sugestao_bib,
                                direcionamento_biblioteca=direcionamento_bib
                            )
                            
                            if salvar_registro_ar(registro, eh_alteracao=False):
                                st.success(f"✅ Registro {numero} salvo com sucesso!")
                                st.info(f"📅 Data: {agora_brasilia.strftime('%d/%m/%Y')} | ⏰ Hora: {agora_brasilia.strftime('%H:%M:%S')} (Horário de Brasília)")
                                
                                if defeito_bib:
                                    st.info(f"📚 Defeito da biblioteca: {defeito_bib}")
                                
                                pdf_bytes = gerar_pdf_ar(registro)
                                if pdf_bytes:
                                    st.session_state.ar_pdf_bytes = pdf_bytes
                                    st.session_state.ar_pdf_nome = sanitize_filename_ar(f"AR_{numero}_{referencia[:30]}") + ".pdf"
                                    st.session_state.ar_mostrar_pdf = True
                                    st.session_state.ar_ultimo_registro = registro
                                    st.session_state.ar_etapa_confirmacao = 1
                                    st.rerun()
        
        # ======================
        # VISUALIZAR REGISTROS (com filtros de Status, Decisão, Turno e Número)
        # ======================
        elif menu_ar == "📊 Visualizar Registros":
            st.subheader("Registros de Aviso de Rejeição")
            with st.spinner("Carregando registros..."):
                registros = carregar_registros_ar()
            if registros:
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                with col_f1:
                    filtro_status = st.selectbox("Filtrar por Status", ["Todos"] + OPCOES_STATUS_AR)
                with col_f2:
                    filtro_decisao = st.selectbox("Filtrar por Decisão", ["Todos"] + OPCOES_DECISAO_AR_MOD)
                with col_f3:
                    filtro_turno = st.selectbox("Filtrar por Turno", ["Todos"] + OPCOES_TURNO_AR)
                with col_f4:
                    filtro_numero = st.number_input("Filtrar por Nº", min_value=0, step=1, value=0)
                
                registros_filtrados = registros
                if filtro_status != "Todos":
                    registros_filtrados = [r for r in registros_filtrados if r.status == filtro_status]
                if filtro_decisao != "Todos":
                    registros_filtrados = [r for r in registros_filtrados if r.decisao == filtro_decisao]
                if filtro_turno != "Todos":
                    registros_filtrados = [r for r in registros_filtrados if r.turno == filtro_turno]
                if filtro_numero > 0:
                    registros_filtrados = [r for r in registros_filtrados if r.numero == filtro_numero]
                
                col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                with col_e1:
                    st.metric("Total Registros", len(registros))
                with col_e2:
                    st.metric("Em Aberto", len([r for r in registros if r.status == "ABERTO"]))
                with col_e3:
                    st.metric("Finalizados", len([r for r in registros if r.status == "FINALIZADO"]))
                with col_e4:
                    st.metric("Não Respondidos", len([r for r in registros if r.status == "NÃO RESPONDIDA"]))
                
                # NOVO GRÁFICO DE BARRAS POR TURNO (Visualização de Registros)
                if len(registros_filtrados) > 0:
                    st.markdown("---")
                    st.subheader("📊 Distribuição por Turno e Status")
                    
                    # Preparar dados para o gráfico
                    turno_status_reg = {}
                    for t in OPCOES_TURNO_AR:
                        regs_turno = [r for r in registros_filtrados if r.turno == t]
                        turno_status_reg[t] = {
                            'ABERTO': len([r for r in regs_turno if r.status == "ABERTO"]),
                            'FINALIZADO': len([r for r in regs_turno if r.status == "FINALIZADO"]),
                            'NÃO RESPONDIDA': len([r for r in regs_turno if r.status == "NÃO RESPONDIDA"])
                        }
                    
                    turnos = list(turno_status_reg.keys())
                    abertos_val = [turno_status_reg[t]['ABERTO'] for t in turnos]
                    finalizados_val = [turno_status_reg[t]['FINALIZADO'] for t in turnos]
                    nao_respondidos_val = [turno_status_reg[t]['NÃO RESPONDIDA'] for t in turnos]
                    
                    fig, ax = plt.subplots(figsize=(10, 5), facecolor=THEME['bg_card'])
                    apply_chart_style(ax, fig, "ARs por Turno e Status", ylabel="Quantidade")
                    
                    x = np.arange(len(turnos))
                    width = 0.25
                    
                    bars1 = ax.bar(x - width, abertos_val, width, label='🟡 Em Aberto', color='#ffc107', alpha=0.85, edgecolor='white', linewidth=1)
                    bars2 = ax.bar(x, finalizados_val, width, label='🟢 Finalizados', color='#28a745', alpha=0.85, edgecolor='white', linewidth=1)
                    bars3 = ax.bar(x + width, nao_respondidos_val, width, label='🔴 Não Respondidos', color='#dc3545', alpha=0.85, edgecolor='white', linewidth=1)
                    
                    for bars in [bars1, bars2, bars3]:
                        for bar in bars:
                            height = bar.get_height()
                            if height > 0:
                                ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                                        f'{int(height)}', ha='center', va='bottom', fontsize=9, fontweight='bold')
                    
                    ax.set_xticks(x)
                    ax.set_xticklabels(turnos, fontsize=11, fontweight='bold')
                    ax.set_ylabel("Quantidade", fontsize=11)
                    ax.legend(loc='upper right', fontsize=10)
                    ax.set_ylim(0, max(max(abertos_val), max(finalizados_val), max(nao_respondidos_val)) * 1.15 if any(v > 0 for v in abertos_val + finalizados_val + nao_respondidos_val) else 10)
                    
                    fig.tight_layout()
                    st.pyplot(fig)
                    plt.close(fig)
                
                st.markdown("---")
                
                dados = []
                for reg in registros_filtrados[:100]:
                    dados.append({
                        "Nº": reg.numero, 
                        "Data": reg.data.strftime("%d/%m/%Y") if reg.data else "-", 
                        "Hora": reg.hora, 
                        "Código": reg.codigo, 
                        "Emissor": reg.emissor, 
                        "Referência": reg.referencia[:40] + "..." if len(reg.referencia) > 40 else reg.referencia, 
                        "Decisão": reg.decisao, 
                        "Status": reg.status, 
                        "Turno": reg.turno
                    })
                df = pd.DataFrame(dados)
                st.dataframe(df, use_container_width=True, height=400)
            else:
                st.info("📭 Nenhum registro encontrado na planilha.")
        
        # ======================
        # BUSCAR/EDITAR/EXCLUIR
        # ======================
        elif menu_ar == "🔍 Buscar/Editar/Excluir":
            st.subheader("Buscar, Editar ou Excluir Registro")
            
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1:
                numero_busca = st.number_input("Digite o número do AR", min_value=1, step=1, key="busca_ar_principal")
            with col_b2:
                st.markdown("<br>", unsafe_allow_html=True)
                buscar_clicked = st.button("🔍 Buscar", key="buscar_ar_principal_btn", use_container_width=True)
            
            if buscar_clicked and numero_busca:
                with st.spinner("Buscando..."):
                    registros = carregar_registros_ar({"numero": numero_busca})
                if registros:
                    st.session_state.ar_registro_editando = registros[0]
                    st.rerun()
            
            if st.session_state.ar_registro_editando:
                reg = st.session_state.ar_registro_editando
                st.success(f"✅ Registro Nº {reg.numero} encontrado!")
                
                with st.expander("📋 Dados completos do registro", expanded=True):
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        st.write("**📅 Datas e Horários:**")
                        st.write(f"- Data: {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                        st.write(f"- Hora: {reg.hora}")
                        st.write(f"- Turno: {reg.turno}")
                        st.write(f"- Data Finalização: {reg.data_finalizacao.strftime('%d/%m/%Y') if reg.data_finalizacao else '-'}")
                        st.write("**📝 Informações do Produto:**")
                        st.write(f"- Código: {reg.codigo}")
                        st.write(f"- Emissor: {reg.emissor}")
                        st.write(f"- Referência: {reg.referencia}")
                    with col_d2:
                        st.write("**⚖️ Decisão e Status:**")
                        st.write(f"- Decisão: {reg.decisao}")
                        st.write(f"- Status: {reg.status}")
                        st.write("**📋 Descrições:**")
                        st.write(f"- Problema: {reg.descricao[:150]}...")
                        st.write(f"- Disposição: {reg.disposicao[:150]}...")
                
                tab_editar, tab_excluir, tab_acoes = st.tabs(["✏️ Editar Registro", "🗑️ Excluir Registro", "📄 Ações do PDF"])
                
                with tab_editar:
                    st.subheader("Editar Registro")
                    with st.form("editar_ar_principal"):
                        col_e1, col_e2, col_e3 = st.columns(3)
                        with col_e1:
                            data_edt = st.date_input("Data", reg.data if reg.data else datetime.now())
                            hora_edt = st.text_input("Hora", reg.hora)
                            turno_edt = st.selectbox("Turno", OPCOES_TURNO_AR, index=OPCOES_TURNO_AR.index(reg.turno) if reg.turno in OPCOES_TURNO_AR else 0)
                        with col_e2:
                            codigo_edt = st.text_input("Código", reg.codigo)
                            emissor_edt = st.text_input("Emissor", reg.emissor)
                            referencia_edt = st.text_area("Referência", reg.referencia, height=80)
                            decisao_edt = st.selectbox("Decisão", OPCOES_DECISAO_AR_MOD, index=OPCOES_DECISAO_AR_MOD.index(reg.decisao) if reg.decisao in OPCOES_DECISAO_AR_MOD else 0)
                        with col_e3:
                            status_edt = st.selectbox("Status", OPCOES_STATUS_AR, index=OPCOES_STATUS_AR.index(reg.status) if reg.status in OPCOES_STATUS_AR else 0)
                            descricao_edt = st.text_area("Descrição", reg.descricao, height=80)
                            disposicao_edt = st.text_area("Disposição", reg.disposicao, height=80)
                            data_fim_edt = st.date_input("Data Finalização", reg.data_finalizacao if reg.data_finalizacao else datetime.now())
                        
                        submitted_edit = st.form_submit_button("💾 SALVAR ALTERAÇÕES", type="primary", use_container_width=True)
                        
                        if submitted_edit:
                            if not codigo_edt or not emissor_edt or not referencia_edt or not descricao_edt:
                                st.error("❌ Preencha todos os campos obrigatórios")
                            else:
                                registro_atualizado = RegistroAR(
                                    numero=reg.numero, 
                                    data=data_edt, 
                                    hora=hora_edt, 
                                    codigo=codigo_edt, 
                                    emissor=emissor_edt, 
                                    referencia=referencia_edt, 
                                    decisao=decisao_edt, 
                                    descricao=descricao_edt, 
                                    status=status_edt, 
                                    disposicao=disposicao_edt, 
                                    data_finalizacao=data_fim_edt, 
                                    turno=turno_edt
                                )
                                if atualizar_registro_ar(registro_atualizado):
                                    st.success(f"✅ Registro {reg.numero} atualizado com sucesso!")
                                    st.session_state.ar_registro_editando = None
                                    st.rerun()
                                else:
                                    st.error("❌ Erro ao atualizar registro")
                
                with tab_excluir:
                    st.subheader("Excluir Registro")
                    st.error(f"⚠️ **ATENÇÃO!** Exclusão do Registro Nº {reg.numero}")
                    st.warning("Esta ação é **IRREVERSÍVEL** e não pode ser desfeita!")
                    
                    st.write("**Dados do registro que será excluído:**")
                    st.write(f"- Código: {reg.codigo}")
                    st.write(f"- Emissor: {reg.emissor}")
                    st.write(f"- Referência: {reg.referencia[:50]}...")
                    st.write(f"- Data: {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                    
                    confirmar = st.checkbox(f"✅ Confirmo que desejo EXCLUIR permanentemente o Registro Nº {reg.numero}")
                    
                    if confirmar:
                        if st.button("🗑️ CONFIRMAR EXCLUSÃO", type="primary", use_container_width=True):
                            with st.spinner(f"Excluindo registro {reg.numero}..."):
                                if excluir_registro_ar(reg.numero):
                                    st.success(f"✅ Registro {reg.numero} excluído com sucesso!")
                                    st.balloons()
                                    st.session_state.ar_registro_editando = None
                                    st.rerun()
                                else:
                                    st.error(f"❌ Erro ao excluir registro {reg.numero}")
                    else:
                        st.info("Marque a caixa de confirmação para habilitar a exclusão.")
                
                with tab_acoes:
                    st.subheader("Ações para este Registro")
                    
                    if st.button("📄 Gerar PDF", use_container_width=True):
                        pdf_bytes = gerar_pdf_ar(reg)
                        if pdf_bytes:
                            nome_pdf = sanitize_filename_ar(f"AR_{reg.numero}_{reg.referencia[:30]}") + ".pdf"
                            st.session_state.ar_pdf_bytes = pdf_bytes
                            st.session_state.ar_pdf_nome = nome_pdf
                            st.session_state.ar_ultimo_registro = reg
                            st.session_state.ar_etapa_confirmacao = 1
                            st.session_state.ar_mostrar_pdf = True
                            st.rerun()
                    
                    if st.session_state.ar_mostrar_pdf and st.session_state.ar_pdf_bytes:
                        st.markdown("---")
                        st.success("✅ PDF gerado com sucesso!")
                        
                        st.markdown("#### 📧 Enviar por E-mail")
                        if st.button("Enviar este PDF por E-mail", use_container_width=True):
                            with st.spinner("Enviando e-mail..."):
                                assunto = f"Aviso de Rejeição - AR {reg.numero} - {datetime.now().strftime('%d/%m/%Y')}"
                                corpo = f"""Prezados,\n\nSegue em anexo o Aviso de Rejeição.\n\nNúmero: {reg.numero}\nData: {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}\nReferência: {reg.referencia}\n\nAtenciosamente,\nSistema de Gestão da Qualidade - Luvidarte"""
                                if enviar_email_ar(EMAIL_CONFIG_AR["destinatarios"], assunto, corpo, st.session_state.ar_pdf_bytes, st.session_state.ar_pdf_nome):
                                    st.success("📧 E-mail enviado com sucesso!")
                                else:
                                    st.error("❌ Erro ao enviar e-mail")
                        
                        st.markdown("#### 🖨️ Imprimir")
                        if st.button("Imprimir este PDF", use_container_width=True):
                            with st.spinner("Abrindo PDF para impressão..."):
                                success, msg = imprimir_pdf_ar(st.session_state.ar_pdf_bytes, st.session_state.ar_pdf_nome)
                                if success:
                                    st.success(f"🖨️ {msg}")
                                else:
                                    st.warning(f"⚠️ {msg}")
                        
                        st.markdown("#### 📥 Salvar PDF")
                        st.download_button(label="Baixar PDF", data=st.session_state.ar_pdf_bytes, file_name=st.session_state.ar_pdf_nome, mime="application/pdf", use_container_width=True)
                
                if st.button("🔍 Nova Busca", use_container_width=True):
                    st.session_state.ar_registro_editando = None
                    st.rerun()
        
        # ======================
        # DASHBOARD AR
        # ======================
        elif menu_ar == "📈 Dashboard AR":
            st.subheader("📊 Dashboard - Avisos de Rejeição")
            st.caption(f"Análise estatística dos ARs cadastrados | Atualizado {get_horario_brasilia()}")
            
            with st.spinner("Carregando dados para o dashboard..."):
                registros = carregar_registros_ar()
            
            if registros:
                st.markdown("### 🔍 Filtros do Dashboard")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    data_ini_dash = st.date_input("Data Inicial", value=None, key="ar_dash_data_ini")
                with col_f2:
                    data_fim_dash = st.date_input("Data Final", value=None, key="ar_dash_data_fim")
                
                registros_filtrados = registros.copy()
                if data_ini_dash:
                    registros_filtrados = [r for r in registros_filtrados if r.data and r.data >= pd.to_datetime(data_ini_dash)]
                if data_fim_dash:
                    registros_filtrados = [r for r in registros_filtrados if r.data and r.data <= pd.to_datetime(data_fim_dash)]
                
                if data_ini_dash or data_fim_dash:
                    st.caption(f"📅 Período filtrado: {len(registros_filtrados)} de {len(registros)} registros")
                
                gerar_dashboard_ar(registros_filtrados)
            else:
                st.info("📭 Nenhum registro encontrado para gerar o dashboard.")
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        AVISO DE REJEIÇÃO · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)

   
# ==================================================================================================
# REQUISIÇÃO DE MANUTENÇÃO (RM)
# ==================================================================================================
elif aba_selecionada == 'REQUISIÇÃO MANUTENÇÃO':
    render_page_header("REQUISIÇÃO DE MANUTENÇÃO", f"MF-001 · Atualizado {get_horario_brasilia()}", THEME['accent_lime'])
    
    # Configurações do RM
    ID_PLANILHA_RM = ID_PLANILHA_AR  # Mesma planilha do AR
    ABA_RM = 'RM'  # Aba específica para RM
    
    # Opções
    OPCOES_CARATER_RM = [
        "1 - Risco Físico/Segurança",
        "2 - Impacto Imediato na Produção", 
        "3 - Impacto a Longo Prazo",
        "4 - Melhoria/Preventiva"
    ]
    OPCOES_SETORES_RM = ["Produção", "Corte", "Vidraria", "Rodaria", "Embalagem", "Expedição", "Qualidade", "Ferramentaria", "Manutenção", "Outros"]
    OPCOES_SETORES2_RM = ["Elétrica", "Mecânica", "Informática", "Ferramentaria", "Manutenção Geral"]
    OPCOES_STATUS_RM = ["ABERTO", "EM ANDAMENTO", "FINALIZADO", "CANCELADO"]
    
    # ====================== CONFIGURAÇÕES DE E-MAIL - LENDO DO SECRETS ======================
    try:
        EMAIL_CONFIG_RM = {
            "usuario": st.secrets["smtp_rm"]["usuario"],
            "senha": st.secrets["smtp_rm"]["senha"],
            "smtp_server": st.secrets["smtp_rm"]["smtp_server"],
            "smtp_port": int(st.secrets["smtp_rm"]["smtp_port"])
        }
        
        EMAILS_SETORES_RM = {
            "Elétrica": st.secrets["emails_rm"]["eletrica"],
            "Mecânica": st.secrets["emails_rm"]["mecanica"],
            "Informática": st.secrets["emails_rm"]["informatica"],
            "Ferramentaria": st.secrets["emails_rm"]["ferramentaria"],
            "Manutenção Geral": st.secrets["emails_rm"]["manutencao_geral"],
            "default": st.secrets["emails_rm"]["default"]
        }
        
        EMAIL_QUALIDADE_RM = st.secrets["emails_rm"]["qualidade"]
        
    except Exception as e:
        st.warning(f"Usando configurações de e-mail hardcoded. Erro ao ler secrets: {e}")
        EMAIL_CONFIG_RM = {
            "usuario": "erp@luvidarte.com.br",
            "senha": "Qualidade123#",
            "smtp_server": "email-ssl.com.br",
            "smtp_port": 465
        }
        EMAILS_SETORES_RM = {
            "Elétrica": "manutencaoeletrica@luvidarte.com.br",
            "Mecânica": "manutencao@luvidarte.com.br",
            "Informática": "alves.marcello@gmail.com",
            "Ferramentaria": "ferramentaria@luvidarte.com.br",
            "Manutenção Geral": "manutencaogeral@luvidarte.com.br",
            "default": "engenharia@luvidarte.com.br"
        }
        EMAIL_QUALIDADE_RM = "qualidade@luvidarte.com.br"
    
    @dataclass
    class RegistroRM:
        id: Optional[int] = None
        data: Optional[datetime] = None
        hora: str = ""
        emissor: str = ""
        equipamento: str = ""
        setor: str = ""
        caracter: str = ""
        setor2: str = ""
        problema: str = ""
        trabalho: str = ""
        analise: str = ""
        status: str = "ABERTO"
        data_finalizacao: Optional[datetime] = None
        emissor2: str = ""
    
    def obter_email_setor_rm(setor_destino: str) -> str:
        return EMAILS_SETORES_RM.get(setor_destino, EMAILS_SETORES_RM["default"])
    
    def enviar_email_rm(registro: RegistroRM, acao: str = "CRIAÇÃO", anexo_bytes: bytes = None, nome_anexo: str = None) -> bool:
        try:
            email_destino = obter_email_setor_rm(registro.setor2)
            destinatarios = [email_destino, EMAIL_QUALIDADE_RM, "engenharia@luvidarte.com.br"]
            destinatarios = list(dict.fromkeys(destinatarios))
            
            msg = MIMEMultipart()
            msg["From"] = EMAIL_CONFIG_RM["usuario"]
            msg["To"] = ", ".join(destinatarios)
            
            data_str = registro.data.strftime("%d/%m/%Y") if registro.data else ""
            data_fim_str = registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else ""
            
            if acao == "EXCLUSÃO":
                msg["Subject"] = f"RM {registro.id} - EXCLUÍDA - {registro.equipamento}"
                corpo = f"""
                <html><body>
                <h2 style="color: #E81123;">⚠️ REQUISIÇÃO DE MANUTENÇÃO EXCLUÍDA</h2>
                <p>A seguinte requisição foi <b>EXCLUÍDA</b> do sistema:</p>
                <table border="1" cellpadding="5">
                <tr><td><b>ID:</b></td><td>{registro.id}</td>
                <tr><td><b>Equipamento:</b></td><td colspan="3">{registro.equipamento}</td></tr>
                <tr><td><b>Data:</b></td><td>{data_str}</td><tr><td><b>Hora:</b></td><td>{registro.hora}</td></tr>
                <tr><td><b>Emissor:</b></td><td colspan="3">{registro.emissor}</td>
                <tr>
                <tr><td colspan="6"><b>📋 PROBLEMA:</b></td>
                <tr>
                <tr><td colspan="6">{registro.problema or "N/A"}</td>
                </table>
                <p>Email automático do Sistema de Requisições de Manutenção.</p>
                </body></html>
                """
            else:
                emoji = "🆕" if acao == "CRIAÇÃO" else "✏️" if acao == "ALTERAÇÃO" else "✅" if acao == "FINALIZAÇÃO" else "📧"
                cor = "#107C10" if acao == "FINALIZAÇÃO" else "#0078D4"
                msg["Subject"] = f"RM {registro.id} - {acao} - {registro.equipamento} - {registro.setor2}"
                corpo = f"""
                <html><body>
                <h2 style="color: {cor};">{emoji} REQUISIÇÃO DE MANUTENÇÃO #{registro.id} - {acao}</h2>
                <table border="1" cellpadding="5">
                <tr><td><b>ID:</b></td><td>{registro.id}</td><td><b>Data:</b></td><td>{data_str}</td><td><b>Hora:</b></td><td>{registro.hora}</td>
                <tr>
                <tr><td><b>Emissor:</b></td><td>{registro.emissor}</td><td><b>Equipamento:</b></td><td colspan="3">{registro.equipamento}</td>
                </tr>
                <tr><td><b>Setor Solicitante:</b></td><td>{registro.setor}</td><td><b>Setor Destino:</b></td><td colspan="3">{registro.setor2}</td>
                </tr>
                <tr><td><b>Caráter:</b></td><td colspan="5">{registro.caracter}</td>
                </tr>
                <tr><td><b>Status:</b></td><td colspan="5"><b style="color:{cor};">{registro.status}</b></td>
                </tr>
                <tr><td colspan="6"><b>📋 DESCRIÇÃO DO PROBLEMA:</b></td>
                </tr>
                <tr><td colspan="6">{registro.problema or "N/A"}</td>
                </tr>
                """
                if registro.trabalho:
                    corpo += f"""
                    <tr><td colspan="6"><b>🔧 TRABALHO REALIZADO:</b></td>
                    <tr>
                    <tr><td colspan="6">{registro.trabalho}</td>
                    </tr>
                    """
                if registro.analise:
                    corpo += f"""
                    <tr><td colspan="6"><b>📊 ANÁLISE DO SERVIÇO:</b></td>
                    <tr>
                    <tr><td colspan="6">{registro.analise}</td>
                    </tr>
                    """
                if registro.emissor2:
                    corpo += f"""
                    <tr><td><b>Emissor Técnico:</b></td><td colspan="5">{registro.emissor2}</td>
                    </tr>
                    """
                if data_fim_str:
                    corpo += f"""
                    <tr><td><b>Data Finalização:</b></td><td colspan="5">{data_fim_str}</td>
                    </tr>
                    """
                corpo += "</table><p>Email automático do Sistema.</p></body></html>"
            
            msg.attach(MIMEText(corpo, "html"))
            
            if anexo_bytes and nome_anexo:
                anexo = MIMEApplication(anexo_bytes, _subtype='pdf')
                anexo.add_header('Content-Disposition', 'attachment', filename=nome_anexo)
                msg.attach(anexo)
            
            with smtplib.SMTP_SSL(EMAIL_CONFIG_RM["smtp_server"], EMAIL_CONFIG_RM["smtp_port"], timeout=30) as server:
                server.login(EMAIL_CONFIG_RM["usuario"], EMAIL_CONFIG_RM["senha"])
                server.send_message(msg)
            return True
        except Exception as e:
            st.error(f"Erro ao enviar e-mail RM: {e}")
            return False
    
    def obter_proximo_id_rm():
        try:
            client = get_gspread_client()
            if client is None:
                return 1
            sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
            todos_dados = sheet.get_all_values()
            if len(todos_dados) < 2:
                return 1
            ids = []
            for row in todos_dados[1:]:
                if row and row[0].strip():
                    try:
                        ids.append(int(row[0]))
                    except:
                        pass
            return max(ids) + 1 if ids else 1
        except:
            return 1
    
    def carregar_registros_rm(filtros: Dict[str, Any] = None) -> List[RegistroRM]:
        registros = []
        try:
            client = get_gspread_client()
            if client is None:
                return registros
            sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
            todos_dados = sheet.get_all_values()
            if len(todos_dados) < 2:
                return registros
            for row in todos_dados[1:]:
                if len(row) < 14:
                    continue
                try:
                    registro = RegistroRM()
                    registro.id = int(row[0]) if row[0].strip() else None
                    registro.data = converter_data_br(row[1])
                    registro.hora = row[2] if len(row) > 2 else ""
                    registro.emissor = row[3] if len(row) > 3 else ""
                    registro.equipamento = row[4] if len(row) > 4 else ""
                    registro.setor = row[5] if len(row) > 5 else ""
                    registro.caracter = row[6] if len(row) > 6 else ""
                    registro.setor2 = row[7] if len(row) > 7 else ""
                    registro.problema = row[8] if len(row) > 8 else ""
                    registro.trabalho = row[9] if len(row) > 9 else ""
                    registro.analise = row[10] if len(row) > 10 else ""
                    registro.status = row[11] if len(row) > 11 else "ABERTO"
                    registro.data_finalizacao = converter_data_br(row[12]) if len(row) > 12 else None
                    registro.emissor2 = row[13] if len(row) > 13 else ""
                    
                    if filtros:
                        incluir = True
                        if filtros.get('id') and filtros['id'] != registro.id:
                            incluir = False
                        if filtros.get('equipamento') and filtros['equipamento'].lower() not in registro.equipamento.lower():
                            incluir = False
                        if filtros.get('status') and filtros['status'] != registro.status:
                            incluir = False
                        if filtros.get('setor2') and filtros['setor2'].upper() != registro.setor2.upper():
                            incluir = False
                    else:
                        incluir = True
                    
                    if incluir and registro.id is not None:
                        registros.append(registro)
                except:
                    continue
            registros.sort(key=lambda x: x.id if x.id else 0, reverse=True)
        except:
            pass
        return registros
    
    def salvar_registro_rm(registro: RegistroRM, eh_alteracao: bool = False) -> bool:
        try:
            client = get_gspread_client()
            if client is None:
                return False
            sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
            dados = [
                str(registro.id) if registro.id else "",
                registro.data.strftime("%d/%m/%Y") if registro.data else "",
                registro.hora, registro.emissor, registro.equipamento, registro.setor,
                registro.caracter, registro.setor2, registro.problema, registro.trabalho,
                registro.analise, registro.status,
                registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else "",
                registro.emissor2
            ]
            if eh_alteracao:
                cell = sheet.find(str(registro.id), in_column=1)
                if cell:
                    for col, valor in enumerate(dados, start=1):
                        sheet.update_cell(cell.row, col, valor)
                else:
                    sheet.append_row(dados)
            else:
                sheet.insert_row(dados, index=2)
                pdf_bytes = gerar_pdf_rm(registro)
                if pdf_bytes:
                    nome_pdf = sanitize_filename_ar(f"RM_{registro.id}_{registro.equipamento[:30]}") + ".pdf"
                    enviar_email_rm(registro, "CRIAÇÃO", pdf_bytes, nome_pdf)
            return True
        except:
            return False
    
    def excluir_registro_rm(id: int) -> bool:
        try:
            client = get_gspread_client()
            if client is None:
                return False
            sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
            registros = carregar_registros_rm({"id": id})
            if registros:
                enviar_email_rm(registros[0], "EXCLUSÃO", None, None)
            cell = sheet.find(str(id), in_column=1)
            if cell:
                sheet.delete_rows(cell.row)
                return True
            return False
        except:
            return False
    
    def gerar_pdf_rm(registro: RegistroRM) -> Optional[bytes]:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            elementos = []
            styles = getSampleStyleSheet()
            styleN = styles["Normal"]
            
            elementos.append(Paragraph("<b>REQUISIÇÃO DE MANUTENÇÃO</b>", ParagraphStyle(name='Titulo', parent=styles["Heading1"], fontSize=16, alignment=1, spaceAfter=12)))
            elementos.append(Paragraph("<b>MF-001 - Luvidarte</b>", ParagraphStyle(name='Subtitulo', parent=styles["Heading2"], fontSize=12, alignment=1, spaceAfter=24)))
            
            data_str = registro.data.strftime("%d/%m/%Y") if registro.data else ""
            data_fim_str = registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else ""
            
            tabela_dados = Table([
                ["ID:", registro.id, "Data:", data_str, "Hora:", registro.hora],
                ["Emissor:", registro.emissor, "Equipamento:", registro.equipamento, "Setor:", registro.setor],
                ["Caráter:", registro.caracter, "Setor Destino:", registro.setor2, "Status:", registro.status],
                ["Emissor Técnico:", registro.emissor2, "Data Finalização:", data_fim_str, "", ""],
            ], colWidths=[2.5*cm, 4*cm, 2.5*cm, 4*cm, 2*cm, 2.5*cm])
            
            tabela_dados.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, colors.black),
                ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("ALIGN", (0,0), (-1,-1), "LEFT"),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("PADDING", (0,0), (-1,-1), 6),
            ]))
            elementos.append(tabela_dados)
            elementos.append(Spacer(1, 24))
            
            elementos.append(Paragraph("<b>DESCRIÇÃO DO PROBLEMA:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
            elementos.append(Paragraph(registro.problema or "-", styleN))
            elementos.append(Spacer(1, 24))
            
            elementos.append(Paragraph("<b>TRABALHO REALIZADO:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
            elementos.append(Paragraph(registro.trabalho or "_________________________", styleN))
            elementos.append(Spacer(1, 24))
            
            elementos.append(Paragraph("<b>ANÁLISE DO SERVIÇO:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
            elementos.append(Paragraph(registro.analise or "_________________________", styleN))
            elementos.append(Spacer(1, 24))
            
            elementos.append(Paragraph("<b>ASSINATURAS:</b>", ParagraphStyle(name='SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
            tabela_assinatura = Table([
                ["Solicitante", "Responsável Técnico", "Conferência Qualidade"],
                ["_________________________", "_________________________", "_________________________"],
                ["Data: __/__/____", "Data: __/__/____", "Data: __/__/____"]
            ], colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
            tabela_assinatura.setStyle(TableStyle([
                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("PADDING", (0,0), (-1,-1), 10),
                ("FONTNAME", (0,0), (0,0), "Helvetica-Bold"),
                ("FONTNAME", (1,0), (1,0), "Helvetica-Bold"),
                ("FONTNAME", (2,0), (2,0), "Helvetica-Bold"),
            ]))
            elementos.append(tabela_assinatura)
            
            elementos.append(Spacer(1, 36))
            elementos.append(Paragraph(f"Documento gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ParagraphStyle(name='Rodape', parent=styleN, fontSize=8, alignment=2)))
            
            doc.build(elementos)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            st.error(f"Erro ao gerar PDF RM: {e}")
            return None
    
    def imprimir_pdf_rm(registro: RegistroRM) -> bool:
        try:
            pdf_bytes = gerar_pdf_rm(registro)
            if pdf_bytes:
                import base64
                import tempfile
                import webbrowser
                
                nome_pdf = sanitize_filename_ar(f"RM_{registro.id}_{registro.equipamento[:30]}") + ".pdf"
                pdf_base64 = base64.b64encode(pdf_bytes).decode()
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head><title>{nome_pdf}</title>
                <style>
                body{{margin:0;padding:0;height:100vh;display:flex;flex-direction:column;}}
                .toolbar{{background:#2c3e50;padding:10px;text-align:center;}}
                button{{padding:8px 20px;margin:0 10px;cursor:pointer;background:#3498db;color:white;border:none;border-radius:5px;}}
                embed{{width:100%;height:calc(100vh-50px);}}
                @media print{{.toolbar{{display:none;}}embed{{height:100vh;}}}}
                </style>
                </head>
                <body>
                <div class="toolbar"><button onclick="window.print()">🖨️ IMPRIMIR</button><button onclick="window.close()">❌ FECHAR</button></div>
                <embed src="data:application/pdf;base64,{pdf_base64}" type="application/pdf">
                <script>setTimeout(function(){{window.print();}},1000);</script>
                </body></html>
                """
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                    f.write(html_content)
                    temp_html = f.name
                webbrowser.open(f'file://{temp_html}')
                return True
            return False
        except:
            return False
    
    with st.container():
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%); padding: 15px 20px; border-radius: 10px; border-left: 4px solid {THEME['accent_lime']}; margin: 20px 0;">
            <span style="font-size: 20px; margin-right: 10px;">🔧</span>
            <span style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: bold; color: {THEME['accent_lime']};">REQUISIÇÃO DE MANUTENÇÃO - MF-001</span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {THEME['text_muted']}; margin-left: 15px;">Sistema de Gestão da Qualidade</span>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📌 **Tabela de Caráter - Níveis 1 a 4**", expanded=False):
            st.markdown("""
            | Nível | Descrição | Ação Recomendada |
            |-------|-----------|------------------|
            | 🚨 **1** | **Risco Físico/Segurança** | Risco iminente de acidente ou dano físico. Ação imediata! |
            | ⚠️ **2** | **Impacto Imediato na Produção** | Parada total ou parcial da produção. Resolver em até 4h |
            | 📊 **3** | **Impacto a Longo Prazo** | Pode afetar produção futura. Planejar em até 48h |
            | 🔧 **4** | **Melhoria/Preventiva** | Manutenção programada ou melhoria. Agendar conforme disponibilidade |
            """)
        
        menu_rm = st.radio("Opções:", ["📝 Nova Requisição", "📊 Visualizar Requisições", "🔍 Buscar/Editar/Excluir", "📈 Dashboard RM"], horizontal=True, key="menu_rm_principal")
        
        if 'rm_pdf_bytes' not in st.session_state:
            st.session_state.rm_pdf_bytes = None
        if 'rm_pdf_nome' not in st.session_state:
            st.session_state.rm_pdf_nome = None
        if 'rm_mostrar_pdf' not in st.session_state:
            st.session_state.rm_mostrar_pdf = False
        if 'rm_ultimo_registro' not in st.session_state:
            st.session_state.rm_ultimo_registro = None
        if 'rm_registro_editando' not in st.session_state:
            st.session_state.rm_registro_editando = None
        
        # ====================== NOVA REQUISIÇÃO ======================
        if menu_rm == "📝 Nova Requisição":
            st.subheader("Nova Requisição de Manutenção")
            st.info("⚠️ Data e hora serão preenchidas automaticamente no salvamento (Horário de Brasília)")
            
            if st.session_state.rm_mostrar_pdf and st.session_state.rm_pdf_bytes:
                st.success(f"✅ Requisição salva com sucesso!")
                if st.session_state.rm_ultimo_registro:
                    reg = st.session_state.rm_ultimo_registro
                    with st.expander("📋 Ver detalhes da requisição", expanded=True):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**ID:** {reg.id}")
                            st.write(f"**Data:** {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                            st.write(f"**Hora:** {reg.hora}")
                            st.write(f"**Emissor:** {reg.emissor}")
                            st.write(f"**Equipamento:** {reg.equipamento}")
                        with col2:
                            st.write(f"**Setor:** {reg.setor}")
                            st.write(f"**Caráter:** {reg.caracter}")
                            st.write(f"**Status:** {reg.status}")
                            st.write(f"**Setor Destino:** {reg.setor2}")
                st.markdown("---")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.download_button(label="📥 Baixar PDF", data=st.session_state.rm_pdf_bytes, file_name=st.session_state.rm_pdf_nome, mime="application/pdf", use_container_width=True)
                with col2:
                    if st.button("📧 Reenviar por E-mail", use_container_width=True):
                        if enviar_email_rm(reg, "REENVIO", st.session_state.rm_pdf_bytes, st.session_state.rm_pdf_nome):
                            st.success("📧 E-mail reenviado com sucesso!")
                        else:
                            st.error("❌ Erro ao enviar e-mail")
                with col3:
                    if st.button("➕ Nova Requisição", use_container_width=True):
                        st.session_state.rm_pdf_bytes = None
                        st.session_state.rm_pdf_nome = None
                        st.session_state.rm_mostrar_pdf = False
                        st.session_state.rm_ultimo_registro = None
                        st.rerun()
            else:
                with st.form("nova_requisicao_rm"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        proximo = obter_proximo_id_rm()
                        st.info(f"📌 Próximo ID: {proximo}")
                        usar_auto = st.checkbox("Usar ID automático", value=True)
                        if usar_auto:
                            id_reg = proximo
                            st.text_input("ID", value=str(id_reg), disabled=True)
                        else:
                            id_reg = st.number_input("ID", min_value=1, step=1)
                        emissor = st.text_input("Emissor*")
                        equipamento = st.text_input("Equipamento*")
                        setor = st.selectbox("Setor*", OPCOES_SETORES_RM)
                    with col2:
                        caracter = st.selectbox("Caráter*", OPCOES_CARATER_RM)
                        if "1 -" in caracter:
                            st.error("🚨 **RISCO FÍSICO!** Ação imediata necessária!")
                        elif "2 -" in caracter:
                            st.warning("⚠️ **IMPACTO IMEDIATO!** Resolver em até 4h")
                        elif "3 -" in caracter:
                            st.info("📊 **Impacto a longo prazo** - Planejar em até 48h")
                        else:
                            st.success("🔧 **Melhoria/Preventiva** - Agendar programação")
                        setor2 = st.selectbox("Setor Destino*", OPCOES_SETORES2_RM)
                        status = st.selectbox("Status*", OPCOES_STATUS_RM)
                        data_finalizacao = st.date_input("Data Finalização", datetime.now())
                    with col3:
                        problema = st.text_area("Descrição do Problema*", height=120)
                        trabalho = st.text_area("Trabalho Realizado", height=100)
                        analise = st.text_area("Análise do Serviço", height=100)
                        emissor2 = st.text_input("Emissor Técnico")
                    submitted = st.form_submit_button("💾 SALVAR REQUISIÇÃO", type="primary", use_container_width=True)
                    if submitted:
                        if not emissor or not equipamento or not problema:
                            st.error("❌ Preencha todos os campos obrigatórios (*)")
                        else:
                            agora_brasilia = get_horario_brasilia_obj()
                            registro = RegistroRM(
                                id=id_reg, data=agora_brasilia.date(), hora=agora_brasilia.strftime("%H:%M:%S"),
                                emissor=emissor, equipamento=equipamento, setor=setor, caracter=caracter,
                                setor2=setor2, problema=problema, trabalho=trabalho, analise=analise,
                                status=status, data_finalizacao=data_finalizacao, emissor2=emissor2
                            )
                            if salvar_registro_rm(registro, eh_alteracao=False):
                                st.success(f"✅ Requisição {id_reg} salva com sucesso!")
                                pdf_bytes = gerar_pdf_rm(registro)
                                if pdf_bytes:
                                    st.session_state.rm_pdf_bytes = pdf_bytes
                                    st.session_state.rm_pdf_nome = sanitize_filename_ar(f"RM_{id_reg}_{equipamento[:30]}") + ".pdf"
                                    st.session_state.rm_mostrar_pdf = True
                                    st.session_state.rm_ultimo_registro = registro
                                    st.rerun()
        
        # ====================== VISUALIZAR REQUISIÇÕES ======================
        elif menu_rm == "📊 Visualizar Requisições":
            st.subheader("Lista de Requisições de Manutenção")
            with st.spinner("Carregando registros..."):
                registros = carregar_registros_rm()
            
            if registros:
                # Obter lista única de setores destino para o filtro
                setores_destino_disponiveis = sorted(set([r.setor2 for r in registros if r.setor2]))
                opcoes_setores_destino = ["Todos"] + setores_destino_disponiveis
                
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    filtro_status = st.selectbox("Status", ["Todos"] + OPCOES_STATUS_RM)
                with col_f2:
                    filtro_caracter = st.selectbox("Caráter", ["Todos"] + OPCOES_CARATER_RM)
                with col_f3:
                    filtro_setor_destino = st.selectbox("Setor Destino", opcoes_setores_destino)
                
                # Aplicar filtros
                dados_filtrados = registros
                if filtro_status != "Todos":
                    dados_filtrados = [r for r in dados_filtrados if r.status == filtro_status]
                if filtro_caracter != "Todos":
                    dados_filtrados = [r for r in dados_filtrados if r.caracter == filtro_caracter]
                if filtro_setor_destino != "Todos":
                    dados_filtrados = [r for r in dados_filtrados if r.setor2 == filtro_setor_destino]
                
                # ===== CARDS COM VALORES FILTRADOS =====
                col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                with col_e1:
                    st.metric("📋 Total", len(dados_filtrados))
                with col_e2:
                    abertos = len([r for r in dados_filtrados if r.status == "ABERTO"])
                    st.metric("🟡 Em Aberto", abertos)
                with col_e3:
                    criticos = len([r for r in dados_filtrados if "1 -" in r.caracter])
                    st.metric("🚨 Nível 1 (Crítico)", criticos)
                with col_e4:
                    finalizados = len([r for r in dados_filtrados if r.status == "FINALIZADO"])
                    st.metric("✅ Finalizados", finalizados)
                
                # Exibir contagem de registros filtrados
                if len(dados_filtrados) < len(registros):
                    st.caption(f"🔍 Exibindo {len(dados_filtrados)} de {len(registros)} registros (filtros aplicados)")
                
                # Tabela de dados
                dados_tabela = []
                for reg in dados_filtrados[:100]:
                    emoji = "🚨" if "1 -" in reg.caracter else "⚠️" if "2 -" in reg.caracter else "📊" if "3 -" in reg.caracter else "🔧"
                    if reg.status == "FINALIZADO":
                        status_display = "✅ FINALIZADO"
                    elif reg.status == "ABERTO":
                        status_display = "🟡 ABERTO"
                    elif reg.status == "EM ANDAMENTO":
                        status_display = "🔄 EM ANDAMENTO"
                    else:
                        status_display = f"⛔ {reg.status}"
                    
                    dados_tabela.append({
                        "ID": reg.id,
                        "Data": reg.data.strftime("%d/%m/%Y") if reg.data else "-",
                        "Equipamento": reg.equipamento[:30] + "..." if len(reg.equipamento) > 30 else reg.equipamento,
                        "Caráter": f"{emoji} {reg.caracter}",
                        "Setor Destino": reg.setor2,
                        "Status": status_display,
                        "Emissor": reg.emissor
                    })
                df = pd.DataFrame(dados_tabela)
                st.dataframe(df, use_container_width=True, height=400)
            else:
                st.info("📭 Nenhuma requisição encontrada")
        
        # ====================== BUSCAR/EDITAR/EXCLUIR ======================
        elif menu_rm == "🔍 Buscar/Editar/Excluir":
            st.subheader("Buscar, Editar ou Excluir Requisição")
            
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1:
                id_busca = st.number_input("Digite o ID da requisição", min_value=1, step=1, key="busca_rm")
            with col_b2:
                buscar_clicked = st.button("🔍 Buscar", use_container_width=True)
            
            if buscar_clicked and id_busca:
                with st.spinner("Buscando..."):
                    registros = carregar_registros_rm({"id": id_busca})
                if registros:
                    st.session_state.rm_registro_editando = registros[0]
                    st.rerun()
                else:
                    st.error(f"❌ Requisição ID {id_busca} não encontrada!")
            
            if st.session_state.rm_registro_editando:
                reg = st.session_state.rm_registro_editando
                st.success(f"✅ Requisição ID {reg.id} encontrada!")
                
                with st.expander("📋 Dados completos da requisição", expanded=True):
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        st.write("**📅 Datas e Horários:**")
                        st.write(f"- Data: {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                        st.write(f"- Hora: {reg.hora}")
                        st.write(f"- Data Finalização: {reg.data_finalizacao.strftime('%d/%m/%Y') if reg.data_finalizacao else '-'}")
                        st.write("**📝 Informações:**")
                        st.write(f"- Emissor: {reg.emissor}")
                        st.write(f"- Equipamento: {reg.equipamento}")
                        st.write(f"- Setor: {reg.setor}")
                    with col_d2:
                        st.write("**⚖️ Caráter e Status:**")
                        st.write(f"- Caráter: {reg.caracter}")
                        st.write(f"- Status: {reg.status}")
                        st.write(f"- Setor Destino: {reg.setor2}")
                        st.write(f"- Emissor Técnico: {reg.emissor2}")
                        st.write("**📋 Descrição:**")
                        st.write(f"- Problema: {reg.problema[:150]}...")
                
                tab_editar, tab_excluir, tab_acoes = st.tabs(["✏️ Editar", "🗑️ Excluir", "📄 Ações PDF"])
                
                with tab_editar:
                    with st.form("editar_rm"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            data_edt = st.date_input("Data", reg.data if reg.data else datetime.now())
                            hora_edt = st.text_input("Hora", reg.hora)
                            emissor_edt = st.text_input("Emissor", reg.emissor)
                            equipamento_edt = st.text_input("Equipamento", reg.equipamento)
                            setor_edt = st.selectbox("Setor", OPCOES_SETORES_RM, index=OPCOES_SETORES_RM.index(reg.setor) if reg.setor in OPCOES_SETORES_RM else 0)
                        with col2:
                            caracter_edt = st.selectbox("Caráter", OPCOES_CARATER_RM, index=OPCOES_CARATER_RM.index(reg.caracter) if reg.caracter in OPCOES_CARATER_RM else 0)
                            setor2_edt = st.selectbox("Setor Destino", OPCOES_SETORES2_RM, index=OPCOES_SETORES2_RM.index(reg.setor2) if reg.setor2 in OPCOES_SETORES2_RM else 0)
                            status_edt = st.selectbox("Status", OPCOES_STATUS_RM, index=OPCOES_STATUS_RM.index(reg.status) if reg.status in OPCOES_STATUS_RM else 0)
                            data_fim_edt = st.date_input("Data Finalização", reg.data_finalizacao if reg.data_finalizacao else datetime.now())
                        with col3:
                            problema_edt = st.text_area("Descrição do Problema", reg.problema, height=120)
                            trabalho_edt = st.text_area("Trabalho Realizado", reg.trabalho, height=100)
                            analise_edt = st.text_area("Análise do Serviço", reg.analise, height=100)
                            emissor2_edt = st.text_input("Emissor Técnico", reg.emissor2)
                        
                        if st.form_submit_button("💾 SALVAR ALTERAÇÕES", type="primary"):
                            registro_atualizado = RegistroRM(
                                id=reg.id, data=data_edt, hora=hora_edt, emissor=emissor_edt,
                                equipamento=equipamento_edt, setor=setor_edt, caracter=caracter_edt,
                                setor2=setor2_edt, problema=problema_edt, trabalho=trabalho_edt,
                                analise=analise_edt, status=status_edt, data_finalizacao=data_fim_edt,
                                emissor2=emissor2_edt
                            )
                            if salvar_registro_rm(registro_atualizado, eh_alteracao=True):
                                st.success(f"✅ Requisição {reg.id} atualizada!")
                                st.session_state.rm_registro_editando = None
                                st.rerun()
                            else:
                                st.error("❌ Erro ao atualizar requisição")
                
                with tab_excluir:
                    st.error(f"⚠️ **ATENÇÃO!** Exclusão da Requisição ID {reg.id}")
                    st.warning("Esta ação é **IRREVERSÍVEL** e enviará um e-mail de notificação!")
                    confirmar = st.checkbox(f"Confirmo exclusão da requisição {reg.id}")
                    if confirmar and st.button("🗑️ EXCLUIR", type="primary"):
                        with st.spinner(f"Excluindo requisição {reg.id}..."):
                            if excluir_registro_rm(reg.id):
                                st.success(f"✅ Requisição {reg.id} excluída!")
                                st.info("📧 E-mail de notificação enviado para o setor destino e qualidade")
                                st.session_state.rm_registro_editando = None
                                st.rerun()
                            else:
                                st.error(f"❌ Erro ao excluir requisição {reg.id}")
                
                with tab_acoes:
                    st.subheader("📄 Ações do PDF")
                    st.info(f"📧 O e-mail será enviado para: **{obter_email_setor_rm(reg.setor2)}** e **{EMAIL_QUALIDADE_RM}**")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("📄 Gerar PDF", use_container_width=True):
                            with st.spinner("Gerando PDF..."):
                                pdf_bytes = gerar_pdf_rm(reg)
                                if pdf_bytes:
                                    st.session_state.rm_pdf_bytes = pdf_bytes
                                    st.session_state.rm_pdf_nome = sanitize_filename_ar(f"RM_{reg.id}_{reg.equipamento[:30]}") + ".pdf"
                                    st.session_state.rm_mostrar_pdf = True
                                    st.success("✅ PDF gerado com sucesso!")
                    with col2:
                        if st.session_state.get('rm_mostrar_pdf', False) and st.session_state.get('rm_pdf_bytes'):
                            st.download_button(label="📥 Baixar PDF", data=st.session_state.rm_pdf_bytes, file_name=st.session_state.rm_pdf_nome, mime="application/pdf", use_container_width=True)
                        else:
                            st.button("📥 Baixar PDF", disabled=True, use_container_width=True)
                    with col3:
                        if st.button("🖨️ Imprimir", use_container_width=True):
                            with st.spinner("Abrindo PDF para impressão..."):
                                if imprimir_pdf_rm(reg):
                                    st.success("🖨️ PDF aberto para impressão!")
                                else:
                                    st.error("❌ Erro ao abrir PDF")
                    
                    st.markdown("---")
                    st.subheader("📧 Envio de E-mail")
                    
                    if st.session_state.get('rm_mostrar_pdf', False) and st.session_state.get('rm_pdf_bytes'):
                        if st.button("📧 Enviar por E-mail (com PDF anexado)", use_container_width=True, type="primary"):
                            with st.spinner("Enviando e-mail..."):
                                if enviar_email_rm(reg, "REENVIO", st.session_state.rm_pdf_bytes, st.session_state.rm_pdf_nome):
                                    st.success(f"📧 E-mail enviado com sucesso!")
                                    st.caption(f"Destinatários: {obter_email_setor_rm(reg.setor2)}, {EMAIL_QUALIDADE_RM}")
                                else:
                                    st.error("❌ Erro ao enviar e-mail")
                    else:
                        if st.button("📧 Enviar por E-mail (gerar PDF primeiro)", use_container_width=True):
                            st.warning("⚠️ Clique em 'Gerar PDF' antes de enviar o e-mail")
                    
                    with st.expander("📋 Info: Destinatários do E-mail"):
                        st.markdown(f"""
                        - **Setor Destino ({reg.setor2})**: `{obter_email_setor_rm(reg.setor2)}`
                        - **Qualidade**: `{EMAIL_QUALIDADE_RM}`
                        - **Engenharia**: `engenharia@luvidarte.com.br`
                        """)
        
        # ====================== DASHBOARD RM ======================
        elif menu_rm == "📈 Dashboard RM":
            st.subheader("Dashboard de Manutenção")
            with st.spinner("Carregando dados..."):
                registros = carregar_registros_rm()
            if registros:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Requisições", len(registros))
                with col2:
                    abertos = len([r for r in registros if r.status == "ABERTO"])
                    st.metric("Em Aberto", abertos)
                with col3:
                    criticos = len([r for r in registros if "1 -" in r.caracter])
                    st.metric("Nível 1 (Crítico)", criticos)
                with col4:
                    finalizados = len([r for r in registros if r.status == "FINALIZADO"])
                    st.metric("Finalizados", finalizados)
                
                st.subheader("Distribuição por Caráter")
                caracter_counts = {}
                for c in OPCOES_CARATER_RM:
                    caracter_counts[c] = len([r for r in registros if r.caracter == c])
                fig, ax = plt.subplots(figsize=(10, 4), facecolor=THEME['bg_card'])
                cores = ['#E81123', '#FF8C00', '#FFB900', '#107C10']
                bars = ax.bar(range(len(caracter_counts)), list(caracter_counts.values()), color=cores, alpha=0.8)
                ax.set_xticks(range(len(caracter_counts)))
                ax.set_xticklabels([c.split(' - ')[1] for c in caracter_counts.keys()], rotation=0)
                ax.set_ylabel("Quantidade")
                ax.set_title("Requisições por Caráter")
                for bar, v in zip(bars, caracter_counts.values()):
                    if v > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(v), ha='center', va='bottom')
                st.pyplot(fig)
                plt.close(fig)
                
                st.subheader("Status das Requisições")
                status_counts = {}
                for s in OPCOES_STATUS_RM:
                    status_counts[s] = len([r for r in registros if r.status == s])
                fig2, ax2 = plt.subplots(figsize=(8, 4), facecolor=THEME['bg_card'])
                cores_status = ['#E81123' if s == 'ABERTO' else '#FF8C00' if s == 'EM ANDAMENTO' else '#107C10' for s in status_counts.keys()]
                bars2 = ax2.bar(range(len(status_counts)), list(status_counts.values()), color=cores_status, alpha=0.8)
                ax2.set_xticks(range(len(status_counts)))
                ax2.set_xticklabels(status_counts.keys())
                ax2.set_ylabel("Quantidade")
                ax2.set_title("Requisições por Status")
                for bar, v in zip(bars2, status_counts.values()):
                    if v > 0:
                        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(v), ha='center', va='bottom')
                st.pyplot(fig2)
                plt.close(fig2)
                
                st.subheader("🚨 Requisições Críticas (Nível 1)")
                criticas = [r for r in registros if "1 -" in r.caracter]
                if criticas:
                    dados_criticos = []
                    for reg in criticas:
                        dados_criticos.append({
                            "ID": reg.id,
                            "Data": reg.data.strftime("%d/%m/%Y") if reg.data else "-",
                            "Equipamento": reg.equipamento,
                            "Setor": reg.setor,
                            "Status": reg.status
                        })
                    st.dataframe(pd.DataFrame(dados_criticos), use_container_width=True)
                else:
                    st.success("✅ Nenhuma requisição crítica no momento!")
            else:
                st.info("Nenhuma requisição encontrada para análise.")
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        REQUISIÇÃO DE MANUTENÇÃO · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)

# ==================================================================================================
# FECHAMENTO TURNO - VERSÃO GOOGLE SHEETS (COM TRS BRUTO + ARs/RMs) - COM RELATÓRIO
# ==================================================================================================
elif aba_selecionada == 'FECHAMENTO TURNO':
    render_page_header("FECHAMENTO DE TURNO", f"Controle de Produção · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])
    
    # ======================
    # CONFIGURAÇÕES DAS PLANILHAS ONLINE
    # ======================
    ID_PLANILHA_FECHAMENTO = '1_HkKTRCSg24wDJ47v5wSd-UPBkbalLd6plV9IvlTY64'
    ID_PLANILHA_FALTAS = '1D4Wqixy60ZW5WPqO026rc1PTHjlVboq9ka0I3VktzDs'
    
    NOME_ABA_PRODUCAO = "PRODUÇÕES"
    NOME_ABA_CHECKLIST = "CHECK"
    NOME_ABA_FALTAS = "Controle de Faltas"
    
    # ======================
    # FUNÇÕES AUXILIARES
    # ======================
    def converter_data_sheets(data_str):
        """Converte string de data do Google Sheets para objeto date"""
        if data_str is None:
            return None
        if isinstance(data_str, (datetime, pd.Timestamp, date)):
            return data_str.date() if hasattr(data_str, 'date') else data_str
        
        data_str = str(data_str).strip()
        
        formatos = [
            "%d/%m/%Y",
            "%Y-%m-%d", 
            "%d-%m-%Y",
            "%m/%d/%Y",
        ]
        
        for fmt in formatos:
            try:
                return datetime.strptime(data_str, fmt).date()
            except:
                continue
        
        return None
    
    def time_to_str_ft(t):
        if t is None:
            return ""
        return str(t) if t else ""
    
    def str_time_to_minutes_ft(time_str: str) -> int:
        try:
            if not time_str or time_str == "00:00":
                return 0
            parts = time_str.split(":")
            if len(parts) >= 2:
                hours = int(parts[0]) if parts[0].isdigit() else 0
                minutes = int(parts[1]) if parts[1].isdigit() else 0
                return hours * 60 + minutes
            return 0
        except:
            return 0
    
    def minutos_para_horas_str(minutos):
        if pd.isna(minutos) or minutos is None or minutos == 0:
            return "00:00"
        horas = int(minutos) // 60
        mins = int(minutos) % 60
        return f"{horas:02d}:{mins:02d}"
    
    def get_turno_por_horario(inicio_str, fim_str, is_sabado=False):
        """
        Determina o turno com base nos horários de início e fim
        Manhã: 06:00 até 14:00
        Tarde: 14:00 até 22:00
        Noite: 22:00 até 06:00 (próximo dia)
        
        Para sábado:
        Manhã: 06:00 até 11:00
        Tarde: 11:00 até 16:00
        Sem turno Noite
        """
        try:
            if not inicio_str or not fim_str:
                return "Não definido"
            
            # Extrair horas
            if ':' in inicio_str:
                h_inicio = int(inicio_str.split(':')[0])
                m_inicio = int(inicio_str.split(':')[1]) if len(inicio_str.split(':')) > 1 else 0
            else:
                return "Não definido"
            
            if ':' in fim_str:
                h_fim = int(fim_str.split(':')[0])
                m_fim = int(fim_str.split(':')[1]) if len(fim_str.split(':')) > 1 else 0
            else:
                return "Não definido"
            
            minutos_inicio = h_inicio * 60 + m_inicio
            minutos_fim = h_fim * 60 + m_fim
            
            if is_sabado:
                # Sábado: Manhã 06:00-11:00, Tarde 11:00-16:00
                if 360 <= minutos_inicio < 660:  # 06:00 até 11:00
                    return "Manhã"
                elif 660 <= minutos_inicio < 960:  # 11:00 até 16:00
                    return "Tarde"
                else:
                    return "Fora do horário"
            else:
                # Dias normais
                if 360 <= minutos_inicio < 840:  # 06:00 até 14:00
                    return "Manhã"
                elif 840 <= minutos_inicio < 1320:  # 14:00 até 22:00
                    return "Tarde"
                elif minutos_inicio >= 1320 or minutos_inicio < 360:  # 22:00 até 06:00
                    return "Noite"
                else:
                    return "Fora do horário"
                    
        except Exception as e:
            return "Não definido"
    
    def get_carinha_trs(trs_value):
        """Retorna a carinha baseada no TRS Bruto"""
        if trs_value >= 100:
            return "😊"
        elif trs_value >= 80:
            return "🙂"
        else:
            return "😢"
    
    # ======================
    # FUNÇÕES DE CARREGAMENTO
    # ======================
    @st.cache_data(ttl=1200)
    def carregar_producoes_fechamento(data_selecionada: date):
        """Carrega produções do Google Sheets"""
        producoes = []
        try:
            client = get_gspread_client()
            if client is None:
                st.error("❌ Erro ao conectar ao Google Sheets")
                return producoes
            
            spreadsheet = client.open("Fechamento diario")
            sheet = spreadsheet.worksheet(NOME_ABA_PRODUCAO)
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return producoes
            
            for row in todos_dados[1:]:
                if len(row) < 2:
                    continue
                
                data_str = row[1] if len(row) > 1 else ""
                data_registro = converter_data_sheets(data_str)
                
                if data_registro and data_registro == data_selecionada:
                    try:
                        produzido_val = int(float(row[5])) if len(row) > 5 and row[5] else 0
                    except:
                        produzido_val = 0
                    
                    try:
                        meta_val = int(float(row[7])) if len(row) > 7 and row[7] else 0
                    except:
                        meta_val = 0
                    
                    # TRS BRUTO = (Produzido / Meta) * 100
                    trs_bruto = round((produzido_val / meta_val * 100), 1) if meta_val > 0 else 0
                    
                    # Verificar se é sábado (data_registro é um date)
                    is_sabado = False
                    if data_registro and hasattr(data_registro, 'weekday'):
                        is_sabado = data_registro.weekday() == 5  # Sábado = 5
                    
                    inicio = row[3] if len(row) > 3 else ""
                    fim = row[4] if len(row) > 4 else ""
                    
                    # Determinar turno baseado nos horários
                    turno_calculado = get_turno_por_horario(inicio, fim, is_sabado)
                    
                    producoes.append({
                        'id': row[0] if len(row) > 0 else "",
                        'data': data_registro,
                        'referencia': row[2] if len(row) > 2 else "",
                        'inicio': inicio,
                        'fim': fim,
                        'produzido': produzido_val,
                        'observacoes': row[6] if len(row) > 6 else "",
                        'meta': meta_val,
                        'id_prog': row[8] if len(row) > 8 else "",
                        'justificativa': row[9] if len(row) > 9 else "",
                        'setup': row[10] if len(row) > 10 else "",
                        'manut': row[11] if len(row) > 11 else "",
                        'trs_bruto': trs_bruto,
                        'turno': turno_calculado
                    })
            
        except Exception as e:
            st.error(f"Erro ao carregar produções: {e}")
        
        return producoes
    
    @st.cache_data(ttl=1200)
    def carregar_checklists_fechamento(data_selecionada: date):
        """Carrega checklists do Google Sheets"""
        checklists = {"manha": False, "tarde": False, "noite": False}
        detalhes = []
        
        try:
            client = get_gspread_client()
            if client is None:
                return checklists, detalhes
            
            spreadsheet = client.open("Fechamento diario")
            sheet = spreadsheet.worksheet(NOME_ABA_CHECKLIST)
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return checklists, detalhes
            
            for row in todos_dados[1:]:
                if len(row) < 2 or not row[0]:
                    continue
                
                data_registro = converter_data_sheets(row[0])
                if data_registro and data_registro == data_selecionada:
                    turno = str(row[1]).lower().strip() if len(row) > 1 else ""
                    if turno in checklists:
                        checklists[turno] = True
                    detalhes.append({
                        'turno': row[1] if len(row) > 1 else "",
                        'faltas': row[2] if len(row) > 2 else "",
                        'temp_forno': row[4] if len(row) > 4 else "",
                        'temp_obs': row[5] if len(row) > 5 else "",
                        'aspecto_vidro': row[6] if len(row) > 6 else "",
                        'aspecto_obs': row[7] if len(row) > 7 else ""
                    })
            
        except Exception as e:
            st.error(f"Erro ao carregar checklists: {e}")
        
        return checklists, detalhes
    
    @st.cache_data(ttl=1200)
    def carregar_faltas_fechamento(data_selecionada: date):
        """Carrega faltas do Google Sheets"""
        faltas = []
        try:
            client = get_gspread_client()
            if client is None:
                return faltas
            
            sheet = client.open_by_key(ID_PLANILHA_FALTAS).worksheet(NOME_ABA_FALTAS)
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return faltas
            
            for row in todos_dados[1:]:
                if len(row) < 7:
                    continue
                
                data_falta = converter_data_sheets(row[6]) if len(row) > 6 else None
                
                if data_falta and data_falta == data_selecionada:
                    faltas.append({
                        'id': row[1] if len(row) > 1 else "",
                        'chapa': row[2] if len(row) > 2 else "",
                        'nome': row[3] if len(row) > 3 else "",
                        'motivo': row[4] if len(row) > 4 else "",
                        'horas': row[5] if len(row) > 5 else "",
                        'justificativa': row[7] if len(row) > 7 else ""
                    })
            
        except Exception as e:
            st.error(f"Erro ao carregar faltas: {e}")
        
        return faltas
    
    @st.cache_data(ttl=1200)
    def carregar_ars_rms_fechamento(data_selecionada: date):
        """Carrega ARs e RMs das planilhas existentes filtradas por data"""
        ars = []
        rms = []
        
        try:
            client = get_gspread_client()
            if client is None:
                return ars, rms
            
            # ======================
            # CARREGAR ARs (Aviso de Rejeição)
            # ======================
            try:
                sheet_ar = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
                todos_dados_ar = sheet_ar.get_all_values()
                
                if len(todos_dados_ar) >= 2:
                    for row in todos_dados_ar[1:]:
                        if len(row) < 5:
                            continue
                        
                        data_ar_str = row[1] if len(row) > 1 else ""
                        data_ar = converter_data_sheets(data_ar_str)
                        
                        if data_ar and data_ar == data_selecionada:
                            ars.append({
                                'tipo': 'AR',
                                'numero': row[0] if len(row) > 0 else "",
                                'data_abertura': data_ar,
                                'hora': row[2] if len(row) > 2 else "",
                                'codigo': row[3] if len(row) > 3 else "",
                                'emissor': row[4] if len(row) > 4 else "",
                                'referencia': row[5] if len(row) > 5 else "",
                                'decisao': row[6] if len(row) > 6 else "",
                                'descricao': row[7] if len(row) > 7 else "",
                                'status': row[8] if len(row) > 8 else "ABERTO",
                                'disposicao': row[9] if len(row) > 9 else "",
                                'data_fechamento': converter_data_sheets(row[10]) if len(row) > 10 and row[10] else None,
                                'turno': row[11] if len(row) > 11 else "",
                                'setor_destino': 'Qualidade',
                                'responsavel': row[4] if len(row) > 4 else ""
                            })
            except Exception as e:
                pass
            
            # ======================
            # CARREGAR RMs (Requisição de Manutenção)
            # ======================
            try:
                sheet_rm = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
                todos_dados_rm = sheet_rm.get_all_values()
                
                if len(todos_dados_rm) >= 2:
                    for row in todos_dados_rm[1:]:
                        if len(row) < 10:
                            continue
                        
                        data_rm_str = row[1] if len(row) > 1 else ""
                        data_rm = converter_data_sheets(data_rm_str)
                        
                        if data_rm and data_rm == data_selecionada:
                            rms.append({
                                'tipo': 'RM',
                                'numero': row[0] if len(row) > 0 else "",
                                'data_abertura': data_rm,
                                'hora': row[2] if len(row) > 2 else "",
                                'emissor': row[3] if len(row) > 3 else "",
                                'equipamento': row[4] if len(row) > 4 else "",
                                'setor': row[5] if len(row) > 5 else "",
                                'carater': row[6] if len(row) > 6 else "",
                                'setor_destino': row[7] if len(row) > 7 else "",
                                'descricao': row[8] if len(row) > 8 else "",
                                'trabalho': row[9] if len(row) > 9 else "",
                                'analise': row[10] if len(row) > 10 else "",
                                'status': row[11] if len(row) > 11 else "ABERTO",
                                'data_fechamento': converter_data_sheets(row[12]) if len(row) > 12 and row[12] else None,
                                'responsavel': row[13] if len(row) > 13 else ""
                            })
            except Exception as e:
                pass
            
        except Exception as e:
            pass
        
        return ars, rms
    
    # ======================
    # FUNÇÃO PARA GERAR HTML DO RELATÓRIO PARA DOWNLOAD (MODO RETRATO)
    # ======================
    def gerar_html_relatorio(producoes, ars, rms, data_fechamento, turno_label, total_produzido, total_meta, 
                             eficiencia, total_setup_min, total_manut_min, total_ars, total_rms, 
                             ars_abertos, rms_abertos, itens_baixa):
        """
        Gera o HTML do relatório para download em modo retrato com fontes maiores
        """
        data_str = data_fechamento.strftime("%d/%m/%Y")
        
        # Gerar linhas da tabela de produção
        tabela_linhas = ""
        for p in producoes:
            trs = p.get('trs_bruto', 0)
            carinha = get_carinha_trs(trs)
            
            # Definir cor da linha baseada no TRS
            if trs >= 100:
                cor_linha = "#d4edda"
                cor_texto = "#155724"
            elif trs >= 80:
                cor_linha = "#fff3cd"
                cor_texto = "#856404"
            else:
                cor_linha = "#f8d7da"
                cor_texto = "#721c24"
            
            # Formatar valores
            meta_str = f"{p.get('meta', 0):,}".replace(",", ".")
            produzido_str = f"{p.get('produzido', 0):,}".replace(",", ".")
            data_prod = p.get('data', '').strftime('%d/%m/%Y') if p.get('data') else '-'
            referencia = p.get('referencia', '-')
            if len(referencia) > 20:
                referencia = referencia[:18] + '...'
            
            tabela_linhas += f"""
            <tr style="background-color: {cor_linha}; color: {cor_texto}; font-size: 11px;">
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{data_prod}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-size: 10px;">{referencia}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{p.get('inicio', '-')}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{p.get('fim', '-')}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: right;">{meta_str}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: right;">{produzido_str}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{p.get('setup', '-')}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{p.get('manut', '-')}</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-weight: bold; font-size: 11px;">{trs:.1f}%</td>
                <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-size: 18px;">{carinha}</td>
            </tr>
            """
        
        if not tabela_linhas:
            tabela_linhas = """
            <tr>
                <td colspan="10" style="padding: 15px; text-align: center; color: #999; font-size: 12px;">
                    Nenhuma produção registrada para este turno/data.
                </td>
            </tr>
            """
        
        # ======================
        # GERAR TABELA DE ARs E RMs
        # ======================
        tabela_ars_rms = ""
        todos_docs = ars + rms
        if todos_docs:
            for doc in todos_docs:
                tipo = doc.get('tipo', '')
                status = str(doc.get('status', '')).upper().strip()
                
                # Definir cor do status
                if status in ['FINALIZADO', 'FINALIZADA']:
                    status_display = "✅ FINALIZADO"
                    cor_status = "#28a745"
                elif status in ['ABERTO', 'EM ANDAMENTO']:
                    status_display = "🟡 ABERTO"
                    cor_status = "#ffc107"
                else:
                    status_display = "🔴 NÃO RESPONDIDO"
                    cor_status = "#dc3545"
                
                if tipo == 'AR':
                    referencia = doc.get('referencia', '-')
                    if len(referencia) > 25:
                        referencia = referencia[:23] + '...'
                    tabela_ars_rms += f"""
                    <tr style="font-size: 11px;">
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-weight: bold; color: #0078D4;">AR</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{doc.get('numero', '-')}</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-size: 10px;">{referencia}</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">-</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-weight: bold; color: {cor_status};">{status_display}</td>
                    </tr>
                    """
                else:  # RM
                    equipamento = doc.get('equipamento', '-')
                    if len(equipamento) > 25:
                        equipamento = equipamento[:23] + '...'
                    tabela_ars_rms += f"""
                    <tr style="font-size: 11px;">
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-weight: bold; color: #E86C2C;">RM</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{doc.get('numero', '-')}</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">-</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-size: 10px;">{equipamento}</td>
                        <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center; font-weight: bold; color: {cor_status};">{status_display}</td>
                    </tr>
                    """
        else:
            tabela_ars_rms = """
            <tr>
                <td colspan="5" style="padding: 15px; text-align: center; color: #999; font-size: 12px;">
                    Nenhum AR ou RM registrado para esta data.
                </td>
            </tr>
            """
        
        # Formatar valores para exibição
        total_produzido_str = f"{total_produzido:,}".replace(",", ".")
        total_meta_str = f"{total_meta:,}".replace(",", ".")
        
        # Cor da eficiência
        cor_eficiencia = "#28a745" if eficiencia >= 85 else "#ffc107" if eficiencia >= 70 else "#dc3545"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Resumo Produção - {data_str}</title>
            <style>
                @page {{
                    size: portrait;
                    margin: 10mm 10mm 10mm 10mm;
                }}
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 10px;
                    background-color: white;
                    font-size: 11px;
                }}
                .container {{
                    max-width: 100%;
                    margin: 0 auto;
                    background-color: white;
                }}
                .header {{
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    padding: 12px 20px;
                    border-radius: 8px;
                    margin-bottom: 12px;
                    color: white;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 700;
                    letter-spacing: 0.1em;
                    text-transform: uppercase;
                }}
                .header .subtitle {{
                    font-size: 16px;
                    color: #a0aec0;
                    margin-top: 4px;
                    font-weight: bold;
                }}
                .section-title {{
                    font-size: 15px;
                    font-weight: 700;
                    margin: 12px 0 8px 0;
                    padding-bottom: 5px;
                    border-bottom: 2px solid #e0e0e0;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 10px;
                    font-size: 10px;
                }}
                table th {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 5px 4px;
                    border: 1px solid #2c3e50;
                    text-align: center;
                    font-size: 10px;
                    font-weight: 700;
                }}
                table td {{
                    padding: 4px 4px;
                    border: 1px solid #ddd;
                    text-align: center;
                }}
                .cards {{
                    display: grid;
                    grid-template-columns: repeat(5, 1fr);
                    gap: 8px;
                    margin-bottom: 10px;
                }}
                .card {{
                    background: #f8f9fc;
                    padding: 8px 10px;
                    border-radius: 6px;
                    border-left: 4px solid #0078D4;
                    text-align: center;
                }}
                .card .label {{
                    font-size: 9px;
                    color: #666;
                    text-transform: uppercase;
                    font-weight: 600;
                    letter-spacing: 0.05em;
                }}
                .card .value {{
                    font-size: 18px;
                    font-weight: 700;
                    margin-top: 2px;
                    color: #1a1a2e;
                }}
                .card-green {{ border-left-color: #28a745; }}
                .card-red {{ border-left-color: #dc3545; }}
                .card-yellow {{ border-left-color: #ffc107; }}
                .card-purple {{ border-left-color: #6f42c1; }}
                .executive-cards {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 8px;
                    margin-top: 8px;
                }}
                .exec-card {{
                    background: #f8f9fc;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border-left: 4px solid #0078D4;
                    font-size: 10px;
                }}
                .exec-card .title {{
                    font-weight: 700;
                    font-size: 12px;
                    margin-bottom: 4px;
                }}
                .exec-card .line {{
                    font-size: 10px;
                    padding: 1px 0;
                }}
                .footer {{
                    margin-top: 10px;
                    padding-top: 8px;
                    border-top: 1px solid #e0e0e0;
                    text-align: center;
                    font-size: 9px;
                    color: #999;
                }}
                .ars-rms-cards {{
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 8px;
                    margin-bottom: 8px;
                }}
                .assinatura-section {{
                    margin-top: 20px;
                    padding-top: 15px;
                    border-top: 2px solid #2c3e50;
                    text-align: center;
                }}
                .assinatura-section .titulo {{
                    font-size: 13px;
                    font-weight: 700;
                    color: #1a1a2e;
                    margin-bottom: 15px;
                }}
                .assinatura-section .linha {{
                    display: flex;
                    justify-content: center;
                    gap: 40px;
                    flex-wrap: wrap;
                    margin-top: 10px;
                }}
                .assinatura-section .campo {{
                    text-align: center;
                    min-width: 200px;
                }}
                .assinatura-section .campo .linha-ass {{
                    border-bottom: 1px solid #333;
                    padding: 5px 30px;
                    margin: 5px 0;
                    min-width: 180px;
                }}
                .assinatura-section .campo .label-ass {{
                    font-size: 10px;
                    color: #666;
                    margin-top: 2px;
                }}
                .assinatura-section .data {{
                    margin-top: 15px;
                    font-size: 11px;
                    color: #555;
                }}
                @media print {{
                    body {{ margin: 5mm; padding: 0; }}
                    .container {{ box-shadow: none; }}
                    .header {{ background: #1a1a2e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                    .card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                    .exec-card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                    table th {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                }}
                @media screen {{
                    body {{ padding: 20px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- HEADER -->
                <div class="header">
                    <h1>📊 RESUMO DO DIA</h1>
                    <div class="subtitle">{data_str} • TURNO: {turno_label}</div>
                </div>
                
                <!-- TABELA DE PRODUÇÃO -->
                <div class="section-title">📋 REGISTRO DE PRODUÇÃO</div>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 10%;">Data</th>
                            <th style="width: 15%;">Referência</th>
                            <th style="width: 8%;">Início</th>
                            <th style="width: 8%;">Fim</th>
                            <th style="width: 10%;">Meta</th>
                            <th style="width: 10%;">Produzido</th>
                            <th style="width: 8%;">Setup</th>
                            <th style="width: 8%;">Manut.</th>
                            <th style="width: 10%;">TRS Bruto</th>
                            <th style="width: 6%;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tabela_linhas}
                    </tbody>
                </table>
                
                <!-- RESUMO DO DIA -->
                <div class="section-title">📊 RESUMO DO DIA</div>
                <div class="cards">
                    <div class="card">
                        <div class="label">📦 Produzido</div>
                        <div class="value">{total_produzido_str}</div>
                    </div>
                    <div class="card card-green">
                        <div class="label">🎯 Meta</div>
                        <div class="value">{total_meta_str}</div>
                    </div>
                    <div class="card card-yellow">
                        <div class="label">📈 Eficiência</div>
                        <div class="value" style="color: {cor_eficiencia};">{eficiencia:.1f}%</div>
                    </div>
                    <div class="card card-red">
                        <div class="label">🔧 Setup</div>
                        <div class="value">{minutos_para_horas_str(total_setup_min)}</div>
                    </div>
                    <div class="card card-red">
                        <div class="label">⚙️ Manutenção</div>
                        <div class="value">{minutos_para_horas_str(total_manut_min)}</div>
                    </div>
                </div>
                
                <!-- RESUMO ARs e RMs - CARDS -->
                <div class="section-title">🔧 RESUMO DE ARs E RMs</div>
                <div class="ars-rms-cards">
                    <div class="card card-purple">
                        <div class="label">📋 Total ARs</div>
                        <div class="value">{total_ars}</div>
                    </div>
                    <div class="card card-purple">
                        <div class="label">🔩 Total RMs</div>
                        <div class="value">{total_rms}</div>
                    </div>
                    <div class="card card-yellow">
                        <div class="label">🟡 ARs em Aberto</div>
                        <div class="value">{ars_abertos}</div>
                    </div>
                    <div class="card card-yellow">
                        <div class="label">🟡 RMs em Aberto</div>
                        <div class="value">{rms_abertos}</div>
                    </div>
                </div>
                
                <!-- TABELA DE ARs E RMs -->
                <div style="margin-top: 5px;">
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 10%;">Tipo</th>
                                <th style="width: 12%;">Nº</th>
                                <th style="width: 30%;">Ref. (AR) / Equip. (RM)</th>
                                <th style="width: 30%;">Equip. (RM) / Ref. (AR)</th>
                                <th style="width: 18%;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {tabela_ars_rms}
                        </tbody>
                    </table>
                </div>
                
                <!-- RESUMO EXECUTIVO -->
                <div class="section-title">📋 RESUMO EXECUTIVO</div>
                <div class="executive-cards">
                    <div class="exec-card" style="border-left-color: #0078D4;">
                        <div class="title" style="color: #0078D4;">🏭 PRODUÇÃO</div>
                        <div class="line">• Produzido: <b>{total_produzido_str}</b> un</div>
                        <div class="line">• Meta: <b>{total_meta_str}</b> un</div>
                        <div class="line">• Eficiência: <b>{eficiencia:.1f}%</b></div>
                    </div>
                    <div class="exec-card" style="border-left-color: #dc3545;">
                        <div class="title" style="color: #dc3545;">⚠️ PARADAS</div>
                        <div class="line">• Setup: <b>{minutos_para_horas_str(total_setup_min)}</b></div>
                        <div class="line">• Manutenção: <b>{minutos_para_horas_str(total_manut_min)}</b></div>
                        <div class="line">• Total: <b>{minutos_para_horas_str(total_setup_min + total_manut_min)}</b></div>
                    </div>
                    <div class="exec-card" style="border-left-color: #28a745;">
                        <div class="title" style="color: #28a745;">📊 INDICADORES</div>
                        <div class="line">• Baixa prod.: <b>{itens_baixa}</b></div>
                        <div class="line">• ARs/RMs: <b>{total_ars + total_rms}</b> ({ars_abertos + rms_abertos} abertos)</div>
                        <div class="line">• Eficiência: <b>{eficiencia:.1f}%</b></div>
                    </div>
                </div>
                
                <!-- ASSINATURA ÚNICA CENTRALIZADA -->
                <div class="assinatura-section">
                    <div class="titulo">📝 ASSINATURA DE RESPONSABILIDADE</div>
                    <div class="linha">
                        <div class="campo">
                            <div class="linha-ass">_________________________</div>
                            <div class="label-ass">Assinatura do Emissor</div>
                        </div>
                        <div class="campo">
                            <div class="linha-ass">_________________________</div>
                            <div class="label-ass">Assinatura do Líder SGQ</div>
                        </div>
                        <div class="campo">
                            <div class="linha-ass">_________________________</div>
                            <div class="label-ass">Assinatura da Qualidade</div>
                        </div>
                    </div>
                    <div class="data">
                        {data_str} • Luvidarte TRS Dashboard
                    </div>
                </div>
                
                <!-- FOOTER -->
                <div class="footer">
                    Relatório gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    # ======================
    # FUNÇÃO PARA GERAR RELATÓRIO RESUMO NA TELA
    # ======================
    def gerar_relatorio_resumo(producoes, ars, rms, turno_selecionado, data_fechamento):
        """
        Gera o relatório resumo com base nos dados fornecidos
        """
        st.markdown("---")
        
        # TÍTULO DO RELATÓRIO
        data_str = data_fechamento.strftime("%d/%m/%Y")
        turno_label = "GERAL" if turno_selecionado == "Todos" else turno_selecionado.upper()
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); 
                    padding: 20px 25px; border-radius: 12px; margin: 10px 0 25px 0;
                    border-left: 6px solid {THEME['accent_purple']};">
            <div style="font-family: 'Rajdhani', sans-serif; font-size: 28px; font-weight: 700; 
                        color: white; letter-spacing: 0.1em; text-transform: uppercase;">
                📊 RESUMO DO DIA
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 14px; 
                        color: #a0aec0; margin-top: 4px;">
                {data_str} • TURNO: {turno_label}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # ======================
        # FILTRAR PRODUÇÕES POR TURNO
        # ======================
        if turno_selecionado != "Todos":
            producoes_filtradas = [p for p in producoes if p.get('turno') == turno_selecionado]
        else:
            producoes_filtradas = producoes.copy()
        
        # ======================
        # CALCULAR TOTAIS PARA O RELATÓRIO
        # ======================
        total_produzido = sum(p.get('produzido', 0) for p in producoes_filtradas)
        total_meta = sum(p.get('meta', 0) for p in producoes_filtradas)
        eficiencia = (total_produzido / total_meta * 100) if total_meta > 0 else 0
        total_setup_min = sum(str_time_to_minutes_ft(p.get('setup', '')) for p in producoes_filtradas)
        total_manut_min = sum(str_time_to_minutes_ft(p.get('manut', '')) for p in producoes_filtradas)
        
        total_ars = len(ars)
        total_rms = len(rms)
        ars_abertos = sum(1 for a in ars if str(a.get('status', '')).upper().strip() in ['ABERTO', 'EM ANDAMENTO'])
        rms_abertos = sum(1 for r in rms if str(r.get('status', '')).upper().strip() in ['ABERTO', 'EM ANDAMENTO'])
        itens_baixa = sum(1 for p in producoes_filtradas if (p.get('produzido', 0) or 0) / max(p.get('meta', 1), 1) * 100 < 80)
        
        # ======================
        # TABELA DE PRODUÇÃO
        # ======================
        st.markdown(f"""
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: 600; 
                    color: {THEME['text_primary']}; margin: 20px 0 10px 0; 
                    border-bottom: 2px solid {THEME['border_bright']}; padding-bottom: 8px;">
            📋 REGISTRO DE PRODUÇÃO
        </div>
        """, unsafe_allow_html=True)
        
        if producoes_filtradas:
            # Preparar dados da tabela
            dados_tabela = []
            for p in producoes_filtradas:
                trs = p.get('trs_bruto', 0)
                carinha = get_carinha_trs(trs)
                
                dados_tabela.append({
                    'Data': p.get('data', '').strftime('%d/%m/%Y') if p.get('data') else '-',
                    'Referência': p.get('referencia', '-'),
                    'Início': p.get('inicio', '-'),
                    'Fim': p.get('fim', '-'),
                    'Meta': f"{p.get('meta', 0):,}".replace(",", "."),
                    'Produzido': f"{p.get('produzido', 0):,}".replace(",", "."),
                    'Setup': p.get('setup', '-'),
                    'Manutenção': p.get('manut', '-'),
                    'TRS Bruto (%)': f"{trs:.1f}%" if trs > 0 else "0%",
                    'Status': carinha
                })
            
            df_tabela = pd.DataFrame(dados_tabela)
            
            # Aplicar estilo à tabela
            def style_tabela(row):
                styles = [''] * len(row)
                try:
                    trs_str = row['TRS Bruto (%)'].replace('%', '').strip()
                    if trs_str:
                        trs_val = float(trs_str)
                        if trs_val >= 100:
                            styles[8] = 'color: #107C10; font-weight: bold; background-color: #d4edda;'
                            styles[9] = 'font-size: 20px;'
                        elif trs_val >= 80:
                            styles[8] = 'color: #FFB900; font-weight: bold; background-color: #fff3cd;'
                            styles[9] = 'font-size: 20px;'
                        else:
                            styles[8] = 'color: #E81123; font-weight: bold; background-color: #f8d7da;'
                            styles[9] = 'font-size: 20px;'
                except:
                    pass
                return styles
            
            styled_df = df_tabela.style.apply(style_tabela, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=400, hide_index=True)
        else:
            st.info("📭 Nenhuma produção registrada para este turno/data.")
        
        # ======================
        # CARDS - RESUMO DO DIA
        # ======================
        st.markdown("---")
        st.markdown(f"""
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: 600; 
                    color: {THEME['text_primary']}; margin: 20px 0 10px 0; 
                    border-bottom: 2px solid {THEME['border_bright']}; padding-bottom: 8px;">
            📊 RESUMO DO DIA
        </div>
        """, unsafe_allow_html=True)
        
        col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
        with col_c1:
            st.metric("📦 Total Produzido", f"{total_produzido:,}".replace(",", "."))
        with col_c2:
            st.metric("🎯 Meta", f"{total_meta:,}".replace(",", "."))
        with col_c3:
            cor_ef = "🟢" if eficiencia >= 85 else "🟡" if eficiencia >= 70 else "🔴"
            st.metric(f"{cor_ef} Eficiência", f"{eficiencia:.1f}%")
        with col_c4:
            st.metric("🔧 Setup Total", minutos_para_horas_str(total_setup_min))
        with col_c5:
            st.metric("⚙️ Manutenção Total", minutos_para_horas_str(total_manut_min))
        
        # ======================
        # CARDS - RESUMO ARs e RMs
        # ======================
        st.markdown("---")
        st.markdown(f"""
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: 600; 
                    color: {THEME['text_primary']}; margin: 20px 0 10px 0; 
                    border-bottom: 2px solid {THEME['border_bright']}; padding-bottom: 8px;">
            🔧 RESUMO DE ARs E RMs
        </div>
        """, unsafe_allow_html=True)
        
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        with col_a1:
            st.metric("📋 Total ARs", total_ars)
        with col_a2:
            st.metric("🔩 Total RMs", total_rms)
        with col_a3:
            st.metric("🟡 ARs em Aberto", ars_abertos)
        with col_a4:
            st.metric("🟡 RMs em Aberto", rms_abertos)
        
        # ======================
        # TABELA DE ARs E RMs
        # ======================
        st.markdown("---")
        st.markdown(f"""
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 16px; font-weight: 600; 
                    color: {THEME['text_primary']}; margin: 15px 0 10px 0; 
                    border-bottom: 2px solid {THEME['border_bright']}; padding-bottom: 8px;">
            📋 LISTA DE ARs E RMs DO DIA
        </div>
        """, unsafe_allow_html=True)
        
        todos_docs = ars + rms
        if todos_docs:
            dados_ars_rms = []
            for doc in todos_docs:
                tipo = doc.get('tipo', '')
                status = str(doc.get('status', '')).upper().strip()
                
                if status in ['FINALIZADO', 'FINALIZADA']:
                    status_display = "✅ FINALIZADO"
                elif status in ['ABERTO', 'EM ANDAMENTO']:
                    status_display = "🟡 ABERTO"
                else:
                    status_display = "🔴 NÃO RESPONDIDO"
                
                if tipo == 'AR':
                    dados_ars_rms.append({
                        'Tipo': 'AR',
                        'Nº': doc.get('numero', '-'),
                        'Ref. / Equip.': doc.get('referencia', '-'),
                        'Equip. / Ref.': '-',
                        'Status': status_display
                    })
                else:
                    dados_ars_rms.append({
                        'Tipo': 'RM',
                        'Nº': doc.get('numero', '-'),
                        'Ref. / Equip.': '-',
                        'Equip. / Ref.': doc.get('equipamento', '-'),
                        'Status': status_display
                    })
            
            df_ars_rms = pd.DataFrame(dados_ars_rms)
            
            # Aplicar estilo à tabela
            def style_ars_rms(row):
                styles = [''] * len(row)
                status = row['Status']
                if 'FINALIZADO' in status:
                    styles[4] = 'color: #28a745; font-weight: bold;'
                elif 'ABERTO' in status:
                    styles[4] = 'color: #ffc107; font-weight: bold;'
                else:
                    styles[4] = 'color: #dc3545; font-weight: bold;'
                return styles
            
            styled_ars_rms = df_ars_rms.style.apply(style_ars_rms, axis=1)
            st.dataframe(styled_ars_rms, use_container_width=True, hide_index=True, height=min(400, len(todos_docs) * 35 + 35))
        else:
            st.info("📭 Nenhum AR ou RM registrado para esta data.")
        
        # ======================
        # CARDS - RESUMO EXECUTIVO
        # ======================
        st.markdown("---")
        st.markdown(f"""
        <div style="font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: 600; 
                    color: {THEME['text_primary']}; margin: 20px 0 10px 0; 
                    border-bottom: 2px solid {THEME['border_bright']}; padding-bottom: 8px;">
            📋 RESUMO EXECUTIVO
        </div>
        """, unsafe_allow_html=True)
        
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            st.markdown(f"""
            <div style="background: {THEME['bg_card']}; padding: 15px; border-radius: 10px; 
                        border-left: 4px solid {THEME['accent_cyan']}; height: 100%;">
                <b style="color: {THEME['accent_cyan']};">🏭 PRODUÇÃO</b><br>
                • Total Produzido: <b>{total_produzido:,}</b> un<br>
                • Meta Total: <b>{total_meta:,}</b> un<br>
                • Eficiência Global: <b>{eficiencia:.1f}%</b>
            </div>
            """, unsafe_allow_html=True)
        
        with col_e2:
            st.markdown(f"""
            <div style="background: {THEME['bg_card']}; padding: 15px; border-radius: 10px; 
                        border-left: 4px solid {THEME['accent_red']}; height: 100%;">
                <b style="color: {THEME['accent_red']};">⚠️ PARADAS</b><br>
                • Setup Total: <b>{minutos_para_horas_str(total_setup_min)}</b><br>
                • Manutenção Total: <b>{minutos_para_horas_str(total_manut_min)}</b><br>
                • Total Paradas: <b>{minutos_para_horas_str(total_setup_min + total_manut_min)}</b>
            </div>
            """, unsafe_allow_html=True)
        
        with col_e3:
            st.markdown(f"""
            <div style="background: {THEME['bg_card']}; padding: 15px; border-radius: 10px; 
                        border-left: 4px solid {THEME['accent_lime']}; height: 100%;">
                <b style="color: {THEME['accent_lime']};">📊 INDICADORES</b><br>
                • Itens baixa prod.: <b>{itens_baixa}</b><br>
                • ARs/RMs do dia: <b>{total_ars + total_rms}</b> ({ars_abertos + rms_abertos} abertos)<br>
                • Eficiência: <b>{eficiencia:.1f}%</b>
            </div>
            """, unsafe_allow_html=True)
        
        # ======================
        # ASSINATURA ÚNICA CENTRALIZADA
        # ======================
        st.markdown("---")
        st.markdown(f"""
        <div style="text-align: center; margin-top: 30px; padding-top: 15px; border-top: 2px solid #2c3e50;">
            <div style="font-family: 'Rajdhani', sans-serif; font-size: 16px; font-weight: 700; 
                        color: {THEME['text_primary']}; margin-bottom: 15px;">
                📝 ASSINATURA DE RESPONSABILIDADE
            </div>
            <div style="display: flex; justify-content: center; gap: 40px; flex-wrap: wrap;">
                <div style="text-align: center; min-width: 180px;">
                    <div style="border-bottom: 1px solid #333; padding: 5px 20px; margin: 5px 0; min-width: 150px;">
                        _________________________
                    </div>
                    <div style="font-size: 11px; color: #666;">Assinatura do Emissor</div>
                </div>
                <div style="text-align: center; min-width: 180px;">
                    <div style="border-bottom: 1px solid #333; padding: 5px 20px; margin: 5px 0; min-width: 150px;">
                        _________________________
                    </div>
                    <div style="font-size: 11px; color: #666;">Assinatura do Supervisor</div>
                </div>
                <div style="text-align: center; min-width: 180px;">
                    <div style="border-bottom: 1px solid #333; padding: 5px 20px; margin: 5px 0; min-width: 150px;">
                        _________________________
                    </div>
                    <div style="font-size: 11px; color: #666;">Assinatura da Qualidade</div>
                </div>
            </div>
            <div style="margin-top: 10px; font-size: 12px; color: #555;">
                {data_str} • Luvidarte TRS Dashboard
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # ======================
        # BOTÃO PARA BAIXAR RELATÓRIO EM HTML
        # ======================
        st.markdown("---")
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            # Gerar HTML do relatório para download
            html_content = gerar_html_relatorio(
                producoes_filtradas, 
                ars,
                rms,
                data_fechamento, 
                turno_label,
                total_produzido, 
                total_meta, 
                eficiencia, 
                total_setup_min, 
                total_manut_min,
                total_ars, 
                total_rms, 
                ars_abertos, 
                rms_abertos,
                itens_baixa
            )
            
            st.download_button(
                label="📥 Baixar Relatório (HTML)",
                data=html_content,
                file_name=f"resumo_producao_{data_fechamento.strftime('%Y%m%d')}_{turno_label}.html",
                mime="text/html",
                use_container_width=True,
                type="primary"
            )
    
    # ======================
    # INTERFACE DO FECHAMENTO TURNO
    # ======================
    
    # ======================
    # HEADER COM DATA E BOTÃO GERAR RESUMO
    # ======================
    col_data1, col_data2, col_data3 = st.columns([1, 1, 2])
    
    with col_data1:
        st.markdown("#### 📅 Selecione a Data")
        data_fechamento = st.date_input(
            "Data do Fechamento",
            value=datetime.now().date(),
            key="fechamento_data"
        )
    
    with col_data2:
        st.markdown("#### 🕐 Selecione o Turno")
        # Verificar se é sábado para mostrar opções corretas
        is_sabado = data_fechamento.weekday() == 5
        if is_sabado:
            opcoes_turno = ["Todos", "Manhã", "Tarde"]
        else:
            opcoes_turno = ["Todos", "Manhã", "Tarde", "Noite"]
        
        turno_selecionado_rel = st.selectbox(
            "Turno",
            options=opcoes_turno,
            key="turno_selecionado_rel"
        )
    
    with col_data3:
        st.markdown("#### ⚙️ Ações")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            gerar_resumo = st.button("📊 Gerar Resumo", use_container_width=True, type="primary")
        with col_btn2:
            if st.button("🔄 Atualizar", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # ======================
    # CARREGAR DADOS
    # ======================
    with st.spinner("Carregando dados do Google Sheets..."):
        producoes = carregar_producoes_fechamento(data_fechamento)
        checklists, checklists_detalhes = carregar_checklists_fechamento(data_fechamento)
        faltas = carregar_faltas_fechamento(data_fechamento)
        ars, rms = carregar_ars_rms_fechamento(data_fechamento)
    
    # ======================
    # GERAR RELATÓRIO SE BOTÃO FOR CLICADO
    # ======================
    if gerar_resumo:
        gerar_relatorio_resumo(producoes, ars, rms, turno_selecionado_rel, data_fechamento)
        st.markdown("<hr>", unsafe_allow_html=True)
    
    # ======================
    # DASHBOARD RESUMIDO (MANTIDO PARA VISUALIZAÇÃO RÁPIDA)
    # ======================
    st.markdown("### 📊 Resumo Rápido do Dia")
    
    # KPIs do dia
    col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
    
    total_produzido = sum(p.get('produzido', 0) or 0 for p in producoes)
    total_meta = sum(p.get('meta', 0) or 0 for p in producoes)
    eficiencia = (total_produzido / total_meta * 100) if total_meta > 0 else 0
    
    total_setup_min = sum(str_time_to_minutes_ft(p.get('setup', '')) for p in producoes)
    total_manut_min = sum(str_time_to_minutes_ft(p.get('manut', '')) for p in producoes)
    
    with col_k1:
        st.metric("📦 Total Produzido", f"{total_produzido:,}".replace(",", "."))
    with col_k2:
        st.metric("🎯 Meta Total", f"{total_meta:,}".replace(",", "."))
    with col_k3:
        cor_eficiencia = "🟢" if eficiencia >= 85 else "🟡" if eficiencia >= 70 else "🔴"
        st.metric(f"{cor_eficiencia} Eficiência", f"{eficiencia:.1f}%")
    with col_k4:
        st.metric("🔧 Setup Total", minutos_para_horas_str(total_setup_min))
    with col_k5:
        st.metric("⚙️ Manutenção Total", minutos_para_horas_str(total_manut_min))
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # Tabs para visualização detalhada
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Produções do Dia", "✅ Checklists Turno", "🟥 Faltas", "🔧 ARs & RMs"])
    
    with tab1:
        st.subheader("Registros de Produção")
        if producoes:
            df_display = pd.DataFrame(producoes)
            
            colunas_exibir = ['referencia', 'inicio', 'fim', 'produzido', 'meta', 'setup', 'manut', 'observacoes', 'justificativa', 'trs_bruto', 'turno']
            colunas_existentes = [c for c in colunas_exibir if c in df_display.columns]
            
            if colunas_existentes:
                df_display = df_display[colunas_existentes]
                df_display.columns = ['Referência', 'Início', 'Fim', 'Produzido', 'Meta', 'Setup', 'Manut.', 'Observações', 'Justificativa', 'TRS Bruto (%)', 'Turno'][:len(colunas_existentes)]
                
                def color_trs(val):
                    if isinstance(val, (int, float)):
                        if val >= 85:
                            return 'background-color: #d4f5d4; color: #1e4620; font-weight: bold;'
                        elif val >= 70:
                            return 'background-color: #fff3cd; color: #856404; font-weight: bold;'
                        else:
                            return 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                    return ''
                
                styled_df = df_display.style.map(color_trs, subset=['TRS Bruto (%)']).format({
                    'Produzido': '{:,.0f}'.format,
                    'Meta': '{:,.0f}'.format,
                    'TRS Bruto (%)': '{:.1f}%'
                })
                
                st.dataframe(styled_df, use_container_width=True, height=400)
            else:
                st.dataframe(df_display, use_container_width=True, height=400)
        else:
            st.info("📭 Nenhuma produção registrada para esta data.")
    
    with tab2:
        st.subheader("Checklists de Início de Turno")
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            if checklists.get("manha"):
                st.success("✅ Turno da MANHÃ - Realizado")
            else:
                st.warning("⏳ Turno da MANHÃ - Pendente")
        with col_c2:
            if checklists.get("tarde"):
                st.success("✅ Turno da TARDE - Realizado")
            else:
                st.warning("⏳ Turno da TARDE - Pendente")
        with col_c3:
            if checklists.get("noite"):
                st.success("✅ Turno da NOITE - Realizado")
            else:
                st.warning("⏳ Turno da NOITE - Pendente")
        
        if checklists_detalhes:
            st.markdown("---")
            st.subheader("📋 Detalhes dos Checklists Realizados")
            for checklist in checklists_detalhes:
                with st.expander(f"📌 Checklist - Turno {checklist['turno']}"):
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        st.write(f"**Faltas:** {checklist.get('faltas', '-')}")
                        st.write(f"**Temperatura Forno:** {checklist.get('temp_forno', '-')}")
                        if checklist.get('temp_obs'):
                            st.write(f"**Obs Temperatura:** {checklist['temp_obs']}")
                    with col_d2:
                        st.write(f"**Aspecto Vidro:** {checklist.get('aspecto_vidro', '-')}")
                        if checklist.get('aspecto_obs'):
                            st.write(f"**Obs Aspecto:** {checklist['aspecto_obs']}")
    
    with tab3:
        st.subheader("Registro de Faltas")
        if faltas:
            df_faltas = pd.DataFrame(faltas)
            colunas_exibir_faltas = ['chapa', 'nome', 'motivo', 'justificativa']
            colunas_existentes_faltas = [c for c in colunas_exibir_faltas if c in df_faltas.columns]
            if colunas_existentes_faltas:
                df_faltas_display = df_faltas[colunas_existentes_faltas]
                df_faltas_display.columns = ['Chapa', 'Nome', 'Motivo', 'Justificativa'][:len(colunas_existentes_faltas)]
                st.dataframe(df_faltas_display, use_container_width=True, height=400)
                st.markdown(f"**Total de faltas no dia:** {len(faltas)}")
            else:
                st.dataframe(df_faltas, use_container_width=True, height=400)
        else:
            st.success(f"✅ Nenhuma falta registrada para esta data.")
    
    with tab4:
        st.subheader("🔧 ARs & RMs - Documentos do Dia")
        st.caption(f"Documentos abertos em {data_fechamento.strftime('%d/%m/%Y')}")
        
        todos_documentos = ars + rms
        
        if todos_documentos:
            total_ars = len(ars)
            total_rms = len(rms)
            
            status_normalizado = []
            for doc in todos_documentos:
                status = str(doc.get('status', '')).upper().strip()
                if status in ['FINALIZADO', 'FINALIZADA']:
                    status_normalizado.append('FINALIZADO')
                elif status in ['ABERTO', 'EM ANDAMENTO']:
                    status_normalizado.append('ABERTO')
                else:
                    status_normalizado.append('NÃO RESPONDIDO')
            
            abertas = status_normalizado.count('ABERTO')
            finalizadas = status_normalizado.count('FINALIZADO')
            nao_respondidas = status_normalizado.count('NÃO RESPONDIDO')
            
            col_a1, col_a2, col_a3, col_a4, col_a5 = st.columns(5)
            
            with col_a1:
                st.metric("📋 Total ARs", total_ars)
            with col_a2:
                st.metric("🔩 Total RMs", total_rms)
            with col_a3:
                st.metric("🟡 Em Aberto", abertas)
            with col_a4:
                st.metric("🟢 Finalizados", finalizadas)
            with col_a5:
                st.metric("🔴 Não Respondidos", nao_respondidas)
            
            st.markdown("---")
            
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                tipo_filtro = st.selectbox("📑 Filtrar por Tipo:", ["TODOS", "AR", "RM"], key="filtro_tipo_ft")
            with col_f2:
                status_filtro = st.selectbox("📊 Filtrar por Status:", ["TODOS", "ABERTO", "FINALIZADO", "NÃO RESPONDIDO"], key="filtro_status_ft")
            
            docs_filtrados = todos_documentos.copy()
            if tipo_filtro != "TODOS":
                docs_filtrados = [d for d in docs_filtrados if d.get('tipo') == tipo_filtro]
            if status_filtro != "TODOS":
                if status_filtro == "NÃO RESPONDIDO":
                    docs_filtrados = [d for d in docs_filtrados if str(d.get('status', '')).upper().strip() not in ['FINALIZADO', 'FINALIZADA', 'ABERTO', 'EM ANDAMENTO']]
                elif status_filtro == "ABERTO":
                    docs_filtrados = [d for d in docs_filtrados if str(d.get('status', '')).upper().strip() in ['ABERTO', 'EM ANDAMENTO']]
                else:
                    docs_filtrados = [d for d in docs_filtrados if str(d.get('status', '')).upper().strip() in ['FINALIZADO', 'FINALIZADA']]
            
            st.markdown(f"**Exibindo {len(docs_filtrados)} de {len(todos_documentos)} documentos**")
            st.markdown("---")
            
            if docs_filtrados:
                for doc in docs_filtrados:
                    status = str(doc.get('status', '')).upper().strip()
                    if status in ['FINALIZADO', 'FINALIZADA']:
                        borda_cor = '#28a745'
                        bg_status = '#d4edda'
                        texto_status = '#155724'
                        icone_status = '✅'
                    elif status in ['ABERTO', 'EM ANDAMENTO']:
                        borda_cor = '#ffc107'
                        bg_status = '#fff3cd'
                        texto_status = '#856404'
                        icone_status = '🟡'
                    else:
                        borda_cor = '#dc3545'
                        bg_status = '#f8d7da'
                        texto_status = '#721c24'
                        icone_status = '🔴'
                    
                    tipo = doc.get('tipo', '')
                    icone_tipo = '📋' if tipo == 'AR' else '🔩'
                    
                    if tipo == 'AR':
                        titulo = f"{icone_tipo} AR Nº {doc.get('numero', '-')} | {icone_status} {status} | Ref: {doc.get('referencia', '-')[:40]}"
                    else:
                        titulo = f"{icone_tipo} RM Nº {doc.get('numero', '-')} | {icone_status} {status} | {doc.get('equipamento', '-')[:40]}"
                    
                    with st.expander(titulo):
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.markdown(f"**📄 Tipo:** {tipo}")
                            st.markdown(f"**🔢 Número:** {doc.get('numero', '-')}")
                            st.markdown(f"**📅 Data Abertura:** {doc.get('data_abertura', '-')}")
                            st.markdown(f"**⏰ Hora:** {doc.get('hora', '-')}")
                            if tipo == 'AR':
                                st.markdown(f"**📦 Código:** {doc.get('codigo', '-')}")
                                st.markdown(f"**🏷️ Referência:** {doc.get('referencia', '-')}")
                                st.markdown(f"**⚖️ Decisão:** {doc.get('decisao', '-')}")
                            else:
                                st.markdown(f"**🏭 Equipamento:** {doc.get('equipamento', '-')}")
                                st.markdown(f"**📍 Setor:** {doc.get('setor', '-')}")
                                st.markdown(f"**⚠️ Caráter:** {doc.get('carater', '-')}")
                        with col_info2:
                            st.markdown(f"**👤 Emissor:** {doc.get('emissor', '-')}")
                            st.markdown(f"**🎯 Setor Destino:** {doc.get('setor_destino', '-')}")
                            st.markdown(f"**👷 Responsável:** {doc.get('responsavel', '-')}")
                            data_fim = doc.get('data_fechamento')
                            st.markdown(f"**📅 Data Fechamento:** {data_fim if data_fim else 'Pendente'}")
                            st.markdown(f"""
                            <div style="background: {bg_status}; padding: 5px 10px; border-radius: 5px; display: inline-block; margin-top: 5px;">
                                <span style="color: {texto_status}; font-weight: bold;">{icone_status} {status}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("---")
                        if tipo == 'AR':
                            st.markdown(f"**📝 Descrição do Problema:** {doc.get('descricao', '-')}")
                            if doc.get('disposicao'):
                                st.markdown(f"**📋 Disposição:** {doc.get('disposicao', '-')}")
                        else:
                            st.markdown(f"**📝 Problema:** {doc.get('descricao', '-')}")
                            if doc.get('trabalho'):
                                st.markdown(f"**🔧 Trabalho Realizado:** {doc.get('trabalho', '-')}")
                            if doc.get('analise'):
                                st.markdown(f"**📊 Análise:** {doc.get('analise', '-')}")
            else:
                st.info("📭 Nenhum documento encontrado com os filtros selecionados.")
        else:
            st.info("📭 Nenhuma AR ou RM encontrada para esta data.")
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        FECHAMENTO DE TURNO · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)

# ==================================================================================================
# MANUTENÇÃO PREVENTIVA - COM COLUNA ANÁLISE NA TABELA PRINCIPAL
# ==================================================================================================
elif aba_selecionada == 'MANUTENÇÃO PREVENTIVA':
    render_page_header("MANUTENÇÃO PREVENTIVA", f"Plano de Manutenção · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])
    
    # ======================
    # INICIALIZAR SESSION STATE
    # ======================
    if 'editando_registro' not in st.session_state:
        st.session_state.editando_registro = None
    
    if 'excluindo_registro' not in st.session_state:
        st.session_state.excluindo_registro = None
    
    if 'mes_calendario' not in st.session_state:
        st.session_state.mes_calendario = datetime.now().replace(day=1)
    
    if 'id_selecionado_novo' not in st.session_state:
        st.session_state.id_selecionado_novo = None
    
    if 'termo_busca_maquina' not in st.session_state:
        st.session_state.termo_busca_maquina = ""
    
    # ======================
    # CONSTANTES
    # ======================
    OPCOES_SETORES_PREVENTIVA = [
        "Produção", "Corte", "Vidraria", "Rodaria", "Embalagem", "Expedição", 
        "Qualidade", "Ferramentaria", "Manutenção", "Pintura", "Quimica", 
        "Escritório", "RH", "Portaria", "Loja", "Furação", "Fosco", 
        "Têmpera", "Area Externa", "Patio", "Outros"
    ]
    
    # ======================
    # CLASSES DE DADOS
    # ======================
    @dataclass
    class RegistroPreventiva:
        id: Optional[str] = None
        data: Optional[datetime] = None
        maquina: str = ""
        setor: str = ""
        descricao: str = ""
        execucao: str = ""
        analise: str = ""
        status: str = "PROGRAMADO"
        linha: Optional[int] = None
        eletrica: bool = False
        mecanica: bool = False
        liberado: bool = False
    
    @dataclass
    class CadastroMaquina:
        id: Optional[str] = None
        maquina: str = ""
        setor: str = ""
    
    # ======================
    # FUNÇÕES AUXILIARES
    # ======================
    def calcular_status_preventiva(data_agendada: date, analise: str, eletrica: bool, mecanica: bool) -> str:
        hoje = datetime.now().date()
        
        # Status FINALIZADO: tem análise E elétrica E mecânica
        if analise and analise.strip() and eletrica and mecanica:
            return "FINALIZADO"
        # Status EM ATRASO: data passou e não está finalizado
        elif data_agendada < hoje:
            return "EM ATRASO"
        # Status EM EXECUÇÃO: data atual
        elif data_agendada == hoje:
            return "EM EXECUÇÃO"
        else:
            return "PROGRAMADO"
    
    def encontrar_linha_preventiva(id_maquina: str, data_agendada: date) -> Optional[int]:
        try:
            client = get_gspread_client()
            if client is None:
                return None
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
            todos_dados = sheet.get_all_values()
            
            data_str = data_agendada.strftime("%d/%m/%Y")
            
            for idx, row in enumerate(todos_dados, start=1):
                if idx == 1:
                    continue
                if len(row) >= 2:
                    if row[0] == id_maquina and row[1] == data_str:
                        return idx
            return None
        except Exception as e:
            return None
    
    # ======================
    # FUNÇÕES DA PLANILHA PREVENTIVA
    # ======================
    @retry_on_quota()
    @st.cache_data(ttl=300)
    def carregar_preventivas(filtros: Dict[str, Any] = None) -> List[RegistroPreventiva]:
        registros = []
        
        try:
            client = get_gspread_client()
            if client is None:
                return registros
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            
            try:
                sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
            except Exception as e:
                sheet = spreadsheet.add_worksheet(title=ABA_PREVENTIVA, rows=1000, cols=20)
                cabecalho = ["ID", "DATA", "MÁQUINA", "SETOR", "DESCRIÇÃO", "EXECUÇÃO", "ANÁLISE", "STATUS", "ELÉTRICA", "MECÂNICA", "LIBERADO"]
                sheet.append_row(cabecalho)
                return registros
            
            todos_dados = sheet.get_all_values()
            
            for idx, row in enumerate(todos_dados[1:], start=2):
                if len(row) < 8 or not row[0] or not row[0].strip():
                    continue
                
                try:
                    registro = RegistroPreventiva()
                    registro.id = row[0].strip()
                    registro.linha = idx
                    
                    data_str = row[1].strip() if len(row) > 1 and row[1] else ""
                    if data_str:
                        try:
                            registro.data = datetime.strptime(data_str, "%d/%m/%Y")
                        except:
                            registro.data = converter_data_br(data_str)
                    
                    registro.maquina = row[2].strip() if len(row) > 2 else ""
                    registro.setor = row[3].strip() if len(row) > 3 else ""
                    registro.descricao = row[4].strip() if len(row) > 4 else ""
                    registro.execucao = row[5].strip() if len(row) > 5 else ""
                    registro.analise = row[6].strip() if len(row) > 6 else ""
                    
                    # Carregar checkboxes (se existirem as colunas)
                    if len(row) > 8:
                        registro.eletrica = row[8].strip().upper() == "TRUE" if len(row) > 8 else False
                    if len(row) > 9:
                        registro.mecanica = row[9].strip().upper() == "TRUE" if len(row) > 9 else False
                    if len(row) > 10:
                        registro.liberado = row[10].strip().upper() == "TRUE" if len(row) > 10 else False
                    
                    if registro.data:
                        registro.status = calcular_status_preventiva(registro.data.date(), registro.analise, registro.eletrica, registro.mecanica)
                    else:
                        registro.status = "PROGRAMADO"
                    
                    registros.append(registro)
                except Exception as e:
                    continue
            
            if filtros:
                registros_filtrados = []
                for r in registros:
                    incluir = True
                    if filtros.get('id') and filtros['id'].upper() != r.id.upper():
                        incluir = False
                    if filtros.get('maquina') and filtros['maquina'].lower() not in r.maquina.lower():
                        incluir = False
                    if filtros.get('setor') and filtros['setor'].upper() != r.setor.upper():
                        incluir = False
                    if filtros.get('status') and filtros['status'].upper() != r.status.upper():
                        incluir = False
                    if incluir:
                        registros_filtrados.append(r)
                return registros_filtrados
            
            return registros
        except Exception as e:
            return registros
    
    @retry_on_quota()
    @st.cache_data(ttl=600)
    def carregar_cadastro_maquinas() -> List[CadastroMaquina]:
        """Carrega o cadastro de máquinas do Google Sheets"""
        registros = []
        try:
            client = get_gspread_client()
            if client is None:
                st.error("❌ Não foi possível conectar ao Google Sheets")
                return registros
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            
            # Tentar abrir a aba CADASTRO
            try:
                sheet = spreadsheet.worksheet(ABA_CADASTRO_PREVENTIVA)
            except Exception as e:
                st.warning(f"Aba '{ABA_CADASTRO_PREVENTIVA}' não encontrada. Criando nova aba...")
                # Criar a aba se não existir
                sheet = spreadsheet.add_worksheet(title=ABA_CADASTRO_PREVENTIVA, rows=1000, cols=10)
                cabecalho = ["ID", "MÁQUINA", "SETOR"]
                sheet.append_row(cabecalho)
                return registros
            
            # Ler todos os dados
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                st.info("Nenhum dado encontrado na aba CADASTRO. Adicione máquinas para começar.")
                return registros
            
            # Processar linhas (pular cabeçalho)
            for row_idx, row in enumerate(todos_dados[1:], start=2):
                if len(row) < 3:
                    continue
                
                id_val = row[0].strip() if row[0] else ""
                maquina_val = row[1].strip() if len(row) > 1 and row[1] else ""
                setor_val = row[2].strip() if len(row) > 2 and row[2] else ""
                
                if not id_val or not maquina_val:
                    continue
                
                try:
                    registro = CadastroMaquina()
                    registro.id = id_val
                    registro.maquina = maquina_val
                    registro.setor = setor_val
                    registros.append(registro)
                except Exception as e:
                    continue
            
            return registros
            
        except Exception as e:
            st.error(f"Erro ao carregar cadastro de máquinas: {str(e)}")
            return registros
    
    def salvar_preventiva(registro: RegistroPreventiva) -> tuple:
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
            
            if registro.data:
                registro.status = calcular_status_preventiva(registro.data.date(), registro.analise, registro.eletrica, registro.mecanica)
            
            data_formatada = registro.data.strftime("%d/%m/%Y") if registro.data else ""
            
            dados = [
                registro.id, data_formatada, registro.maquina, registro.setor,
                registro.descricao, registro.execucao, registro.analise, registro.status,
                str(registro.eletrica).upper(), str(registro.mecanica).upper(), str(registro.liberado).upper()
            ]
            
            sheet.append_row(dados)
            st.cache_data.clear()
            return True, "✅ Manutenção salva com sucesso!"
        except Exception as e:
            return False, f"❌ Erro ao salvar: {str(e)}"
    
    def atualizar_preventiva(registro: RegistroPreventiva) -> tuple:
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
            
            # Atualizar liberado baseado nos checkboxes
            registro.liberado = registro.eletrica and registro.mecanica
            
            if registro.data:
                registro.status = calcular_status_preventiva(registro.data.date(), registro.analise, registro.eletrica, registro.mecanica)
            
            linha = encontrar_linha_preventiva(registro.id, registro.data.date())
            
            if not linha:
                return False, f"❌ Registro não encontrado: ID={registro.id}"
            
            data_formatada = registro.data.strftime("%d/%m/%Y") if registro.data else ""
            
            dados = [
                registro.id, data_formatada, registro.maquina, registro.setor,
                registro.descricao, registro.execucao, registro.analise, registro.status,
                str(registro.eletrica).upper(), str(registro.mecanica).upper(), str(registro.liberado).upper()
            ]
            
            for col, valor in enumerate(dados, start=1):
                sheet.update_cell(linha, col, valor)
            
            st.cache_data.clear()
            return True, "✅ Registro atualizado com sucesso!"
        except Exception as e:
            return False, f"❌ Erro ao atualizar: {str(e)}"
    
    def excluir_preventiva(id_maquina: str, data_agendada: date) -> tuple:
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
            
            linha = encontrar_linha_preventiva(id_maquina, data_agendada)
            
            if not linha:
                return False, f"❌ Registro não encontrado: ID={id_maquina}"
            
            sheet.delete_rows(linha)
            st.cache_data.clear()
            return True, "✅ Registro excluído com sucesso!"
        except Exception as e:
            return False, f"❌ Erro ao excluir: {str(e)}"
    
    def salvar_cadastro_maquina(registro: CadastroMaquina, eh_alteracao: bool = False) -> tuple:
        """Salva ou atualiza uma máquina no cadastro"""
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Não foi possível conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            
            # Garantir que a aba existe
            try:
                sheet = spreadsheet.worksheet(ABA_CADASTRO_PREVENTIVA)
            except:
                sheet = spreadsheet.add_worksheet(title=ABA_CADASTRO_PREVENTIVA, rows=1000, cols=10)
                cabecalho = ["ID", "MÁQUINA", "SETOR"]
                sheet.append_row(cabecalho)
            
            dados = [registro.id, registro.maquina, registro.setor]
            
            if eh_alteracao:
                # Buscar pela coluna ID (coluna 1)
                try:
                    cell = sheet.find(registro.id, in_column=1)
                    if cell:
                        # Atualizar linha existente
                        for col, valor in enumerate(dados, start=1):
                            sheet.update_cell(cell.row, col, valor)
                    else:
                        # Se não encontrou, adicionar nova linha
                        sheet.append_row(dados)
                except Exception as e:
                    print(f"Erro na busca: {e}")
                    sheet.append_row(dados)
            else:
                # Verificar se ID já existe
                try:
                    cell = sheet.find(registro.id, in_column=1)
                    if cell:
                        return False, f"❌ ID {registro.id} já existe!"
                except:
                    pass
                sheet.append_row(dados)
            
            st.cache_data.clear()
            return True, "✅ Cadastro salvo com sucesso!"
            
        except Exception as e:
            print(f"Erro ao salvar cadastro: {traceback.format_exc()}")
            return False, f"❌ Erro ao salvar cadastro: {str(e)}"
    
    def excluir_cadastro_maquina(id_maquina: str) -> tuple:
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
            sheet = spreadsheet.worksheet(ABA_CADASTRO_PREVENTIVA)
            
            cell = sheet.find(id_maquina, in_column=1)
            if cell:
                sheet.delete_rows(cell.row)
                st.cache_data.clear()
                return True, "✅ Cadastro excluído com sucesso!"
            return False, "❌ Cadastro não encontrado"
        except Exception as e:
            return False, f"❌ Erro ao excluir cadastro: {str(e)}"
    
    def enviar_email_preventiva(registro: RegistroPreventiva, acao: str = "CRIAÇÃO") -> bool:
        try:
            email_config = {
                "usuario": "erp@luvidarte.com.br",
                "senha": "Qualidade123#",
                "smtp_server": "email-ssl.com.br",
                "smtp_port": 465
            }
            
            destinatarios = [
                "manutencao@luvidarte.com.br",
                "engenharia@luvidarte.com.br",
                "qualidade@luvidarte.com.br"
            ]
            
            data_str = registro.data.strftime("%d/%m/%Y") if registro.data else "Não agendada"
            liberado_str = "✅ LIBERADO" if registro.liberado else "⏳ AGUARDANDO"
            
            msg = MIMEMultipart()
            msg["From"] = email_config["usuario"]
            msg["To"] = ", ".join(destinatarios)
            msg["Subject"] = f"[{acao}] Manutenção Preventiva - {registro.maquina} - {data_str}"
            
            corpo = f"""
            <html><body>
            <h2>{acao} - Manutenção Preventiva</h2>
            <p><strong>ID:</strong> {registro.id}</p>
            <p><strong>Máquina:</strong> {registro.maquina}</p>
            <p><strong>Setor:</strong> {registro.setor}</p>
            <p><strong>Data Agendada:</strong> {data_str}</p>
            <p><strong>Descrição:</strong> {registro.descricao}</p>
            <p><strong>Responsável:</strong> {registro.execucao or 'Não definido'}</p>
            <p><strong>Liberação Elétrica:</strong> {'✅ SIM' if registro.eletrica else '❌ NÃO'}</p>
            <p><strong>Liberação Mecânica:</strong> {'✅ SIM' if registro.mecanica else '❌ NÃO'}</p>
            <p><strong>Status Liberação:</strong> {liberado_str}</p>
            <p><strong>Status:</strong> {registro.status}</p>
            </body></html>
            """
            
            msg.attach(MIMEText(corpo, "html"))
            
            with smtplib.SMTP_SSL(email_config["smtp_server"], email_config["smtp_port"], timeout=30) as server:
                server.login(email_config["usuario"], email_config["senha"])
                server.send_message(msg)
            
            return True
        except Exception as e:
            return False
    
    # ======================
    # TABS PRINCIPAIS
    # ======================
    tab_agenda, tab_cadastro = st.tabs(["📅 Agenda de Manutenção", "🏭 Cadastro de Máquinas"])
    
    with tab_agenda:
        st.subheader("📅 Plano de Manutenção Preventiva")
        
        # FILTROS
        with st.expander("🔍 Filtros", expanded=False):
            cadastros_filtro = carregar_cadastro_maquinas()
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                opcoes_maquinas = ["(Todas)"] + [c.maquina for c in cadastros_filtro if c.maquina]
                filtro_maquina = st.selectbox("Máquina", opcoes_maquinas, key="filtro_maquina_pv")
            
            with col_f2:
                opcoes_setores = sorted(list(set([c.setor for c in cadastros_filtro if c.setor])))
                opcoes_setores = ["(Todos)"] + opcoes_setores
                filtro_setor = st.selectbox("Setor", opcoes_setores, key="filtro_setor_pv")
            
            with col_f3:
                opcoes_status = ["(Todos)", "PROGRAMADO", "EM EXECUÇÃO", "EM ATRASO", "FINALIZADO"]
                filtro_status = st.selectbox("Status", opcoes_status, key="filtro_status_pv")
        
        # Aplicar filtros
        filtros = {}
        if filtro_maquina != "(Todas)":
            filtros['maquina'] = filtro_maquina
        if filtro_setor != "(Todos)":
            filtros['setor'] = filtro_setor
        if filtro_status != "(Todos)":
            filtros['status'] = filtro_status
        
        with st.spinner("Carregando agenda..."):
            registros = carregar_preventivas(filtros if filtros else None)
        
        # ====================== CALENDÁRIO MENSAL ======================
        st.markdown("---")
        st.subheader("📆 Calendário Mensal")
        
        # Navegação do calendário
        col_cal1, col_cal2, col_cal3 = st.columns([1, 3, 1])
        with col_cal1:
            if st.button("◀ Mês Anterior", key="btn_mes_anterior", use_container_width=True):
                st.session_state.mes_calendario = st.session_state.mes_calendario - timedelta(days=1)
                st.session_state.mes_calendario = st.session_state.mes_calendario.replace(day=1)
                st.rerun()
        
        with col_cal2:
            st.markdown(f"<h3 style='text-align: center;'>{st.session_state.mes_calendario.strftime('%B %Y')}</h3>", unsafe_allow_html=True)
        
        with col_cal3:
            if st.button("Próximo Mês ▶", key="btn_mes_proximo", use_container_width=True):
                next_month = st.session_state.mes_calendario.replace(day=28) + timedelta(days=4)
                st.session_state.mes_calendario = next_month.replace(day=1)
                st.rerun()
        
        # Criar mapa de eventos por data
        eventos_por_data = {}
        for reg in registros:
            if reg.data:
                data_str = reg.data.strftime("%Y-%m-%d")
                if data_str not in eventos_por_data:
                    eventos_por_data[data_str] = []
                eventos_por_data[data_str].append(reg)
        
        # CSS do calendário
        st.markdown("""
        <style>
        .calendario-dia {
            min-height: 85px;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 5px;
            margin: 2px;
            background: #fafafa;
            transition: all 0.2s ease;
        }
        .calendario-dia:hover {
            transform: scale(1.02);
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            z-index: 10;
        }
        .calendario-dia-num {
            font-size: 13px;
            font-weight: bold;
            border-bottom: 1px solid #eee;
            padding-bottom: 3px;
            margin-bottom: 5px;
            color: #333;
        }
        .calendario-evento {
            font-size: 9px;
            padding: 3px 5px;
            margin: 2px 0;
            border-radius: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .calendario-evento:hover {
            opacity: 0.85;
            transform: scale(1.02);
        }
        .evento-programado { background: #0078D4; color: white; border-left: 3px solid #005a9e; }
        .evento-execucao { background: #FFB900; color: #333; border-left: 3px solid #d49c00; }
        .evento-atraso { background: #E81123; color: white; border-left: 3px solid #a80000; }
        .evento-finalizado { background: #107C10; color: white; border-left: 3px solid #0a5a0a; }
        .dia-hoje {
            background: #fff3cd !important;
            border: 2px solid #FFB900 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Gerar calendário
        import calendar
        cal = calendar.monthcalendar(st.session_state.mes_calendario.year, st.session_state.mes_calendario.month)
        dias_semana = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
        
        # Cabeçalho dos dias da semana
        cols_header = st.columns(7)
        for i, dia in enumerate(dias_semana):
            with cols_header[i]:
                st.markdown(f"<div style='text-align:center;font-weight:bold;padding:8px;background:#f0f0f0;border-radius:5px;'>{dia}</div>", unsafe_allow_html=True)
        
        # Dias do mês
        for semana in cal:
            cols = st.columns(7)
            for i, dia in enumerate(semana):
                with cols[i]:
                    if dia == 0:
                        st.markdown("<div class='calendario-dia' style='background:#f5f5f5;opacity:0.5;'></div>", unsafe_allow_html=True)
                    else:
                        data_atual = st.session_state.mes_calendario.replace(day=dia)
                        data_str = data_atual.strftime("%Y-%m-%d")
                        eventos = eventos_por_data.get(data_str, [])
                        
                        # Destacar dia atual
                        if data_atual.date() == datetime.now().date():
                            classe_hoje = "dia-hoje"
                        else:
                            classe_hoje = ""
                        
                        html_dia = f'<div class="calendario-dia {classe_hoje}">'
                        html_dia += f'<div class="calendario-dia-num">{dia}</div>'
                        
                        for evento in eventos[:3]:
                            if evento.status == "PROGRAMADO":
                                classe = "evento-programado"
                            elif evento.status == "EM EXECUÇÃO":
                                classe = "evento-execucao"
                            elif evento.status == "EM ATRASO":
                                classe = "evento-atraso"
                            else:
                                classe = "evento-finalizado"
                            
                            liberado_icon = "✅" if evento.liberado else "⏳"
                            titulo = f"{evento.maquina}: {evento.descricao[:35]} | {liberado_icon}"
                            html_dia += f'<div class="calendario-evento {classe}" title="{titulo}">🔧 {evento.maquina[:10]} {liberado_icon}</div>'
                        
                        if len(eventos) > 3:
                            html_dia += f'<div class="calendario-evento" style="background:#999;color:white;text-align:center;">+{len(eventos)-3}</div>'
                        
                        html_dia += '</div>'
                        st.markdown(html_dia, unsafe_allow_html=True)
        
        # Legenda do calendário
        st.markdown("---")
        col_leg1, col_leg2, col_leg3, col_leg4, col_leg5, col_leg6 = st.columns(6)
        with col_leg1:
            st.markdown("<span style='background:#0078D4; padding:2px 8px; border-radius:4px; color:white; font-size:11px;'>🔹 PROGRAMADO</span>", unsafe_allow_html=True)
        with col_leg2:
            st.markdown("<span style='background:#FFB900; padding:2px 8px; border-radius:4px; color:#333; font-size:11px;'>🔸 EM EXECUÇÃO</span>", unsafe_allow_html=True)
        with col_leg3:
            st.markdown("<span style='background:#E81123; padding:2px 8px; border-radius:4px; color:white; font-size:11px;'>🔴 EM ATRASO</span>", unsafe_allow_html=True)
        with col_leg4:
            st.markdown("<span style='background:#107C10; padding:2px 8px; border-radius:4px; color:white; font-size:11px;'>✅ FINALIZADO</span>", unsafe_allow_html=True)
        with col_leg5:
            st.markdown("<span style='background:#fff3cd; padding:2px 8px; border-radius:4px; color:#333; border:1px solid #FFB900; font-size:11px;'>📅 HOJE</span>", unsafe_allow_html=True)
        with col_leg6:
            st.markdown("<span style='font-size:11px;'>✅ Liberado | ⏳ Aguardando</span>", unsafe_allow_html=True)
        
        # ====================== TABELA DE REGISTROS DO MÊS ======================
        st.markdown("---")
        st.subheader(f"📋 Manutenções - {st.session_state.mes_calendario.strftime('%B %Y')}")
        
        ano_mes_atual = st.session_state.mes_calendario.strftime("%Y-%m")
        registros_mes = [r for r in registros if r.data and r.data.strftime("%Y-%m") == ano_mes_atual]
        
        if registros_mes:
            dados_tabela = []
            for reg in registros_mes:
                if reg.status == "PROGRAMADO":
                    status_display = "🟦 PROGRAMADO"
                elif reg.status == "EM EXECUÇÃO":
                    status_display = "🟡 EM EXECUÇÃO"
                elif reg.status == "EM ATRASO":
                    status_display = "🔴 EM ATRASO"
                else:
                    status_display = "✅ FINALIZADO"
                
                liberado_display = "✅ LIBERADO" if reg.liberado else "⏳ AGUARDANDO"
                analise_display = reg.analise[:40] + "..." if len(reg.analise) > 40 else reg.analise if reg.analise else "-"
                
                dados_tabela.append({
                    "ID": reg.id, 
                    "Data": reg.data.strftime("%d/%m/%Y"), 
                    "Máquina": reg.maquina,
                    "Setor": reg.setor, 
                    "Descrição": reg.descricao[:40] + "..." if len(reg.descricao) > 40 else reg.descricao,
                    "Análise": analise_display,
                    "Elétrica": "✅" if reg.eletrica else "❌",
                    "Mecânica": "✅" if reg.mecanica else "❌",
                    "Liberado": liberado_display,
                    "Status": status_display
                })
            
            df_tabela = pd.DataFrame(dados_tabela)
            st.dataframe(df_tabela, use_container_width=True, height=500)
            
            st.caption(f"Total: {len(registros_mes)} manutenções neste mês | 💡 Para FINALIZAR: marque Elétrica ✅ + Mecânica ✅ e preencha a Análise")
        else:
            st.info("📭 Nenhuma manutenção programada para este mês.")
        
        # ====================== CRUD - GERENCIAR MANUTENÇÕES ======================
        st.markdown("---")
        st.subheader("✏️ Gerenciar Manutenções")
        
        acao = st.radio("Ação:", ["➕ Nova Manutenção", "✏️ Editar Manutenção", "🗑️ Excluir Manutenção"], horizontal=True)
        
        # ====================== NOVA MANUTENÇÃO COM COMBOBOX DE PESQUISA ======================
        if acao == "➕ Nova Manutenção":
            with st.form("nova_preventiva"):
                # Carregar cadastro de máquinas
                cadastros_novo = carregar_cadastro_maquinas()
                
                if not cadastros_novo:
                    st.warning("⚠️ Nenhuma máquina cadastrada. Por favor, cadastre máquinas na aba 'Cadastro de Máquinas' primeiro.")
                    st.form_submit_button("💾 SALVAR MANUTENÇÃO", disabled=True, use_container_width=True)
                else:
                    # Criar dicionários para lookup rápido
                    dict_info_maquinas = {c.id: {"nome": c.maquina, "setor": c.setor} for c in cadastros_novo}
                    
                    # Opção de ordenar por nome para facilitar busca
                    maquinas_ordenadas = sorted(cadastros_novo, key=lambda x: x.maquina)
                    
                    # CSS personalizado para o campo de busca
                    st.markdown("""
                    <style>
                    div[data-testid="stTextInput"] input {
                        font-size: 14px;
                    }
                    .search-info {
                        font-size: 12px;
                        color: #666;
                        margin-top: -10px;
                        margin-bottom: 10px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    # Campo de busca com texto
                    st.markdown("### 🔍 Buscar Máquina")
                    st.caption("Digite parte do nome, ID ou setor da máquina")
                    
                    termo_busca = st.text_input(
                        "🔎 Pesquisar",
                        value=st.session_state.termo_busca_maquina,
                        key="campo_busca_maquina",
                        placeholder="Ex: Prensa, MAQ001, Produção...",
                        label_visibility="collapsed"
                    )
                    
                    # Atualizar session state
                    st.session_state.termo_busca_maquina = termo_busca
                    
                    # Filtrar máquinas baseado no termo de busca
                    if termo_busca:
                        termo_lower = termo_busca.lower()
                        maquinas_filtradas = [
                            m for m in maquinas_ordenadas 
                            if termo_lower in m.id.lower() 
                            or termo_lower in m.maquina.lower() 
                            or termo_lower in m.setor.lower()
                        ]
                    else:
                        maquinas_filtradas = maquinas_ordenadas
                    
                    # Mostrar resultado da busca
                    if termo_busca:
                        if maquinas_filtradas:
                            st.success(f"✅ Encontradas {len(maquinas_filtradas)} máquina(s)")
                        else:
                            st.warning(f"⚠️ Nenhuma máquina encontrada com '{termo_busca}'")
                            st.info("💡 Dica: Tente buscar por parte do nome, ID ou setor")
                    
                    # Selectbox com as máquinas filtradas
                    if maquinas_filtradas:
                        opcoes_select = [
                            f"{m.id} | {m.maquina} | {m.setor}" 
                            for m in maquinas_filtradas
                        ]
                        
                        selecao_formatada = st.selectbox(
                            "📋 Selecione a máquina",
                            options=opcoes_select,
                            key="select_maquina_nova",
                            help="Selecione a máquina desejada da lista filtrada"
                        )
                        
                        # Extrair o ID da seleção
                        if selecao_formatada:
                            id_selecionado = selecao_formatada.split(" | ")[0].strip()
                            st.session_state.id_selecionado_novo = id_selecionado
                            
                            # Buscar informações completas
                            info = dict_info_maquinas.get(id_selecionado, {})
                            maquina_selecionada = info.get("nome", "")
                            setor_selecionado = info.get("setor", "")
                        else:
                            id_selecionado = None
                            maquina_selecionada = ""
                            setor_selecionado = ""
                    else:
                        id_selecionado = None
                        maquina_selecionada = ""
                        setor_selecionado = ""
                    
                    # Linha divisória
                    st.markdown("---")
                    
                    # Campos do formulário
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("### 📋 Dados da Máquina")
                        
                        # ID (automático)
                        st.text_input(
                            "ID da Máquina*", 
                            value=id_selecionado if id_selecionado else "", 
                            disabled=True,
                            key="novo_id_display",
                            help="Selecionado automaticamente ao escolher a máquina"
                        )
                        
                        # Nome da Máquina (automático)
                        st.text_input(
                            "Máquina*", 
                            value=maquina_selecionada, 
                            disabled=True,
                            key="novo_maquina_display"
                        )
                        
                        # Setor (automático)
                        st.text_input(
                            "Setor*", 
                            value=setor_selecionado, 
                            disabled=True,
                            key="novo_setor_display"
                        )
                        
                        # Data agendada
                        data_agendada = st.date_input(
                            "📅 Data Agendada*", 
                            value=datetime.now().date(), 
                            key="novo_data"
                        )
                    
                    with col2:
                        st.markdown("### 🔧 Informações da Manutenção")
                        
                        descricao = st.text_area(
                            "📝 Descrição do Serviço*", 
                            height=100, 
                            key="novo_descricao",
                            placeholder="Descreva detalhadamente o serviço a ser executado..."
                        )
                        
                        execucao = st.text_input(
                            "👤 Responsável pela Execução", 
                            key="novo_execucao",
                            placeholder="Nome do técnico responsável"
                        )
                        
                        analise = st.text_area(
                            "📊 Análise / Resultado", 
                            height=80, 
                            key="novo_analise", 
                            placeholder="Preencha APÓS a execução da manutenção (resultados, observações, etc.)",
                            help="Este campo deve ser preenchido após a conclusão da manutenção"
                        )
                    
                    # Informação sobre liberações
                    st.info("ℹ️ **Nota:** As liberações Elétrica e Mecânica serão marcadas na edição, após a execução da manutenção.")
                    
                    # Botão de submit
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                    with col_btn2:
                        submitted = st.form_submit_button(
                            "💾 SALVAR MANUTENÇÃO", 
                            type="primary", 
                            use_container_width=True
                        )
                    
                    if submitted:
                        # Validações
                        if not id_selecionado:
                            st.error("❌ Selecione uma máquina na lista!")
                        elif not descricao or not descricao.strip():
                            st.error("❌ Preencha a descrição do serviço!")
                        elif not data_agendada:
                            st.error("❌ Selecione uma data válida!")
                        else:
                            # Criar registro
                            novo_registro = RegistroPreventiva(
                                id=id_selecionado, 
                                data=datetime.combine(data_agendada, datetime.min.time()),
                                maquina=maquina_selecionada, 
                                setor=setor_selecionado, 
                                descricao=descricao.strip(),
                                execucao=execucao.strip(), 
                                analise=analise.strip() if analise else "",
                                eletrica=False,
                                mecanica=False,
                                liberado=False
                            )
                            
                            # Salvar
                            sucesso, mensagem = salvar_preventiva(novo_registro)
                            
                            if sucesso:
                                st.success(mensagem)
                                # Tentar enviar email
                                try:
                                    enviar_email_preventiva(novo_registro, "CRIAÇÃO")
                                except:
                                    pass
                                
                                # Limpar campos da busca
                                st.session_state.termo_busca_maquina = ""
                                st.session_state.id_selecionado_novo = None
                                
                                # Recarregar página
                                st.rerun()
                            else:
                                st.error(mensagem)
        
        # ====================== EDITAR MANUTENÇÃO ======================
        elif acao == "✏️ Editar Manutenção":
            
            # Botão para cancelar edição
            if st.session_state.editando_registro is not None:
                if st.button("❌ Cancelar Edição", key="btn_cancelar_edicao", use_container_width=True):
                    st.session_state.editando_registro = None
                    st.rerun()
            
            # Formulário de busca
            if st.session_state.editando_registro is None:
                with st.form("buscar_para_editar"):
                    st.info("🔍 Informe o ID da Máquina e a Data da Manutenção para editar")
                    col1, col2 = st.columns(2)
                    with col1:
                        id_busca = st.text_input("ID da Máquina*", key="edit_busca_id")
                    with col2:
                        data_busca = st.date_input("Data da Manutenção*", value=datetime.now().date(), key="edit_busca_data")
                    
                    buscar_btn = st.form_submit_button("🔍 Buscar Registro", use_container_width=True)
                    
                    if buscar_btn and id_busca:
                        todos_registros = carregar_preventivas()
                        for reg in todos_registros:
                            if reg.id == id_busca and reg.data and reg.data.date() == data_busca:
                                st.session_state.editando_registro = reg
                                st.rerun()
                                break
                        else:
                            st.error(f"❌ Registro não encontrado para ID={id_busca} e data={data_busca.strftime('%d/%m/%Y')}")
            
            # Formulário de edição
            if st.session_state.editando_registro is not None:
                reg = st.session_state.editando_registro
                st.success(f"✅ Editando: {reg.maquina} - {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                
                with st.form("form_editar_registro"):
                    cadastros_edit = carregar_cadastro_maquinas()
                    dict_maquina_edit = {c.id: {"nome": c.maquina, "setor": c.setor} for c in cadastros_edit}
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("ID", value=reg.id, disabled=True, key="edit_id_display")
                        
                        if reg.id in dict_maquina_edit:
                            st.text_input("Máquina", value=dict_maquina_edit[reg.id]["nome"], disabled=True, key="edit_maquina_display")
                            st.text_input("Setor", value=dict_maquina_edit[reg.id]["setor"], disabled=True, key="edit_setor_display")
                            maquina_val = dict_maquina_edit[reg.id]["nome"]
                            setor_val = dict_maquina_edit[reg.id]["setor"]
                        else:
                            maquina_val = st.text_input("Máquina", value=reg.maquina, key="edit_maquina_input")
                            setor_val = st.text_input("Setor", value=reg.setor, key="edit_setor_input")
                        
                        data_edit = st.date_input("Data", value=reg.data.date() if reg.data else datetime.now().date(), key="edit_data_input")
                    
                    with col2:
                        descricao_edit = st.text_area("Descrição", value=reg.descricao, height=100, key="edit_descricao")
                        execucao_edit = st.text_input("Responsável", value=reg.execucao, key="edit_execucao")
                        analise_edit = st.text_area("Análise / Resultado", value=reg.analise, height=80, key="edit_analise")
                    
                    # Checkboxes de liberação
                    st.markdown("---")
                    st.markdown("### 🔓 Liberações para Finalização")
                    
                    col_check1, col_check2 = st.columns(2)
                    with col_check1:
                        eletrica_check = st.checkbox("✅ Elétrica - Liberado", value=reg.eletrica, key="edit_eletrica")
                    with col_check2:
                        mecanica_check = st.checkbox("✅ Mecânica - Liberado", value=reg.mecanica, key="edit_mecanica")
                    
                    # Mostrar status da liberação
                    liberado_status = eletrica_check and mecanica_check
                    if liberado_status and analise_edit and analise_edit.strip():
                        st.success("🎉 **Todas as condições atendidas! O status será alterado para FINALIZADO ao salvar.**")
                    elif liberado_status:
                        st.warning("⚠️ **Liberações marcadas, mas falta preencher a Análise para FINALIZAR.**")
                    elif analise_edit and analise_edit.strip():
                        st.warning("⚠️ **Análise preenchida, mas faltam as liberações Elétrica e Mecânica para FINALIZAR.**")
                    else:
                        st.warning("⚠️ **Para FINALIZAR a manutenção: marque Elétrica ✅ + Mecânica ✅ e preencha a Análise.**")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        salvar_btn = st.form_submit_button("💾 SALVAR ALTERAÇÕES", type="primary", use_container_width=True)
                    with col_btn2:
                        cancelar_btn = st.form_submit_button("❌ Cancelar", use_container_width=True)
                    
                    if salvar_btn:
                        registro_atualizado = RegistroPreventiva(
                            id=reg.id,
                            data=datetime.combine(data_edit, datetime.min.time()),
                            maquina=maquina_val,
                            setor=setor_val,
                            descricao=descricao_edit,
                            execucao=execucao_edit,
                            analise=analise_edit,
                            eletrica=eletrica_check,
                            mecanica=mecanica_check,
                            liberado=liberado_status
                        )
                        
                        sucesso, mensagem = atualizar_preventiva(registro_atualizado)
                        
                        if sucesso:
                            st.success(mensagem)
                            # Enviar e-mail de finalização se for o caso
                            if liberado_status and analise_edit and analise_edit.strip():
                                try:
                                    enviar_email_preventiva(registro_atualizado, "FINALIZAÇÃO")
                                except:
                                    pass
                            st.session_state.editando_registro = None
                            st.rerun()
                        else:
                            st.error(mensagem)
                    
                    if cancelar_btn:
                        st.session_state.editando_registro = None
                        st.rerun()
        
        # ====================== EXCLUIR MANUTENÇÃO ======================
        elif acao == "🗑️ Excluir Manutenção":
            
            # Botão para cancelar exclusão
            if st.session_state.excluindo_registro is not None:
                if st.button("❌ Cancelar Exclusão", key="btn_cancelar_exclusao_top", use_container_width=True):
                    st.session_state.excluindo_registro = None
                    st.rerun()
            
            # Formulário de busca
            if st.session_state.excluindo_registro is None:
                with st.form("buscar_para_excluir"):
                    st.info("🔍 Informe o ID da Máquina e a Data da Manutenção para excluir")
                    col1, col2 = st.columns(2)
                    with col1:
                        id_busca = st.text_input("ID da Máquina*", key="del_busca_id")
                    with col2:
                        data_busca = st.date_input("Data da Manutenção*", value=datetime.now().date(), key="del_busca_data")
                    
                    buscar_btn = st.form_submit_button("🔍 Buscar Registro", use_container_width=True)
                    
                    if buscar_btn and id_busca:
                        todos_registros = carregar_preventivas()
                        for reg in todos_registros:
                            if reg.id == id_busca and reg.data and reg.data.date() == data_busca:
                                st.session_state.excluindo_registro = reg
                                st.rerun()
                                break
                        else:
                            st.error(f"❌ Registro não encontrado para ID={id_busca} e data={data_busca.strftime('%d/%m/%Y')}")
            
            # Confirmação de exclusão
            if st.session_state.excluindo_registro is not None:
                reg = st.session_state.excluindo_registro
                
                st.error(f"⚠️ ATENÇÃO! Você está prestes a EXCLUIR:")
                st.markdown(f"""
                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid red; margin: 10px 0;">
                    <b>ID:</b> {reg.id}<br>
                    <b>Máquina:</b> {reg.maquina}<br>
                    <b>Data:</b> {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}<br>
                    <b>Descrição:</b> {reg.descricao[:100]}...
                </div>
                """, unsafe_allow_html=True)
                
                confirmar = st.checkbox("✅ Confirmo que desejo EXCLUIR permanentemente este registro", key="chk_confirmar_exclusao")
                
                if confirmar:
                    if st.button("🗑️ CONFIRMAR EXCLUSÃO", key="btn_confirmar_exclusao", type="primary", use_container_width=True):
                        sucesso, mensagem = excluir_preventiva(reg.id, reg.data.date() if reg.data else datetime.now().date())
                        if sucesso:
                            st.success(mensagem)
                            st.balloons()
                            st.session_state.excluindo_registro = None
                            st.rerun()
                        else:
                            st.error(mensagem)
                
                if st.button("❌ Cancelar", key="btn_cancelar_exclusao_bottom", use_container_width=True):
                    st.session_state.excluindo_registro = None
                    st.rerun()
    
    # ======================
    # TAB CADASTRO DE MÁQUINAS
    # ======================
    with tab_cadastro:
        st.subheader("🏭 Cadastro de Máquinas")
        
        cadastros = carregar_cadastro_maquinas()
        
        if cadastros:
            df_cadastro = pd.DataFrame([{"ID": c.id, "Máquina": c.maquina, "Setor": c.setor} for c in cadastros])
            st.dataframe(df_cadastro, use_container_width=True, height=300)
            
            st.caption(f"Total: {len(cadastros)} máquinas cadastradas")
        else:
            st.info("📭 Nenhuma máquina cadastrada. Cadastre uma máquina para começar.")
        
        st.markdown("---")
        acao_cadastro = st.radio("Ação:", ["➕ Nova Máquina", "✏️ Editar Máquina", "🗑️ Excluir Máquina"], horizontal=True)
        
        if acao_cadastro == "➕ Nova Máquina":
            with st.form("nova_maquina"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    id_novo = st.text_input("ID da Máquina*", placeholder="Ex: MAQ001", key="cad_id_novo")
                with col2:
                    maquina_nova = st.text_input("Nome da Máquina*", placeholder="Ex: Prensa Hidráulica", key="cad_maquina_nova")
                with col3:
                    setor_novo = st.selectbox("Setor", OPCOES_SETORES_PREVENTIVA, key="cad_setor_novo")
                
                if st.form_submit_button("💾 CADASTRAR", type="primary", use_container_width=True):
                    if not id_novo or not maquina_nova:
                        st.error("❌ Preencha ID e Nome da Máquina")
                    elif any(c.id.upper() == id_novo.upper() for c in cadastros):
                        st.error(f"❌ ID {id_novo} já existe!")
                    else:
                        sucesso, msg = salvar_cadastro_maquina(CadastroMaquina(id=id_novo.upper(), maquina=maquina_nova, setor=setor_novo))
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        
        elif acao_cadastro == "✏️ Editar Máquina":
            if cadastros:
                with st.form("editar_maquina"):
                    id_editar = st.selectbox("Selecione o ID", [c.id for c in cadastros], key="cad_id_editar")
                    maquina_atual = next((c for c in cadastros if c.id == id_editar), None)
                    
                    if maquina_atual:
                        col1, col2 = st.columns(2)
                        with col1:
                            maquina_edit = st.text_input("Nome da Máquina", value=maquina_atual.maquina, key="cad_maquina_edit")
                        with col2:
                            idx = OPCOES_SETORES_PREVENTIVA.index(maquina_atual.setor) if maquina_atual.setor in OPCOES_SETORES_PREVENTIVA else 0
                            setor_edit = st.selectbox("Setor", OPCOES_SETORES_PREVENTIVA, index=idx, key="cad_setor_edit")
                        
                        if st.form_submit_button("💾 SALVAR ALTERAÇÕES", type="primary", use_container_width=True):
                            sucesso, msg = salvar_cadastro_maquina(CadastroMaquina(id=id_editar, maquina=maquina_edit, setor=setor_edit), eh_alteracao=True)
                            if sucesso:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
            else:
                st.info("📭 Nenhuma máquina cadastrada")
        
        elif acao_cadastro == "🗑️ Excluir Máquina":
            if cadastros:
                with st.form("excluir_maquina"):
                    id_excluir = st.selectbox("Selecione o ID", [c.id for c in cadastros], key="cad_id_excluir")
                    maquina_excluir = next((c for c in cadastros if c.id == id_excluir), None)
                    
                    if maquina_excluir:
                        st.warning(f"⚠️ Excluir máquina: **{maquina_excluir.maquina}** (ID: {id_excluir})")
                        st.caption("⚠️ Esta ação NÃO remove as manutenções agendadas, apenas o cadastro da máquina.")
                        confirmar = st.checkbox("✅ Confirmo exclusão do cadastro", key="chk_confirmar_excluir_cadastro")
                        if confirmar and st.form_submit_button("🗑️ EXCLUIR CADASTRO", type="primary", use_container_width=True):
                            sucesso, msg = excluir_cadastro_maquina(id_excluir)
                            if sucesso:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
            else:
                st.info("📭 Nenhuma máquina cadastrada")
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        MANUTENÇÃO PREVENTIVA · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)
    
# ==================================================================================================
# MAPEAMENTO DE HABILIDADES
# ==================================================================================================
elif aba_selecionada == 'MAPEAMENTO DE HABILIDADES':
    render_page_header("MAPEAMENTO DE HABILIDADES", f"Desenvolvimento de Pessoas · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])
    
    # ======================
    # CONFIGURAÇÃO DA PLANILHA
    # ======================
    ID_PLANILHA_HABILIDADES = '1Kldu2rJKlGDWSAvztvgLUyZ0DwcifOlbWvekj6xhkl4'
    ABA_HABILIDADES = 'HABILIDADES'
    
    # ======================
    # COLUNAS ESPECÍFICAS DA PLANILHA
    # ======================
    # Hard Skills (lado esquerdo)
    HARD_SKILLS = [
        'LER_PLANTAS_TECNICAS',
        'INSPECAO_VISUAL',
        'CHOQUE_TERMICO',
        'MENTORIA',
        'NORMAS_QUALIDADE',
        'SITEMA_ERP',
        'EXPEDICAO',
        'TRS',
        'OPERACAO_MAQUINA',
        'PLANTAS_TECNICAS'
    ]
    
    # Soft Skills (lado direito)
    SOFT_SKILLS = [
        'COMUNICACAO',
        'LIDERANCA',
        'TRABALHO_EQUIPE',
        'CRIATIVIDADE',
        'RESOLUCAO_PROBLEMAS',
        'ADAPTABILIDADE',
        'AGILIDADE',
        'INTELIGENCIA_EMOCIONAL',
        'ASSIDUIDADE',
        'PONTUALIDADE',
        'PROATIVIDADE'
    ]
    
    # ======================
    # FUNÇÃO PARA CARREGAR DADOS DA PLANILHA
    # ======================
    @retry_on_quota()
    @st.cache_data(ttl=300)
    def carregar_dados_habilidades():
        """
        Carrega os dados da planilha de Mapeamento de Habilidades
        """
        try:
            client = get_gspread_client()
            if client is None:
                st.error("❌ Erro ao conectar ao Google Sheets")
                return pd.DataFrame(), [], []
            
            # Abrir planilha de Habilidades
            spreadsheet = client.open_by_key(ID_PLANILHA_HABILIDADES)
            
            # Tentar abrir a aba HABILIDADES
            try:
                sheet = spreadsheet.worksheet(ABA_HABILIDADES)
            except Exception as e:
                st.error(f"❌ Aba '{ABA_HABILIDADES}' não encontrada na planilha. Erro: {e}")
                return pd.DataFrame(), [], []
            
            # Ler todos os dados
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                st.info("📭 Nenhum dado encontrado na planilha.")
                return pd.DataFrame(), [], []
            
            # Cabeçalho na primeira linha
            cabecalho = todos_dados[0]
            valores = todos_dados[1:]
            
            # Criar DataFrame
            df = pd.DataFrame(valores, columns=cabecalho)
            
            # Limpar nomes das colunas (remover espaços e acentos)
            df.columns = df.columns.str.strip().str.upper()
            df.columns = df.columns.str.replace(' ', '_')
            df.columns = df.columns.str.replace('Ç', 'C')
            df.columns = df.columns.str.replace('Ã', 'A')
            df.columns = df.columns.str.replace('Á', 'A')
            df.columns = df.columns.str.replace('É', 'E')
            df.columns = df.columns.str.replace('Í', 'I')
            df.columns = df.columns.str.replace('Ó', 'O')
            df.columns = df.columns.str.replace('Ú', 'U')
            
            # Mapeamento de colunas esperadas
            colunas_esperadas = ['COLABORADOR', 'FUNCAO', 'TURNO', 'SETOR'] + HARD_SKILLS + SOFT_SKILLS
            
            # Verificar quais colunas existem
            colunas_existentes = [col for col in colunas_esperadas if col in df.columns]
            
            if not colunas_existentes:
                st.error("❌ Nenhuma coluna esperada encontrada na planilha.")
                st.write("Colunas encontradas:", list(df.columns)[:10])
                return pd.DataFrame(), [], []
            
            # Manter apenas colunas existentes
            df = df[colunas_existentes]
            
            # Converter colunas numéricas (Hard e Soft Skills)
            for col in HARD_SKILLS + SOFT_SKILLS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    # Limitar entre 0 e 10
                    df[col] = df[col].clip(0, 10)
            
            # Remover linhas sem colaborador
            if 'COLABORADOR' in df.columns:
                df = df[df['COLABORADOR'].astype(str).str.strip() != '']
                df = df[df['COLABORADOR'].astype(str).str.strip() != 'nan']
            else:
                st.warning("⚠️ Coluna 'COLABORADOR' não encontrada na planilha.")
                return pd.DataFrame(), [], []
            
            # Padronizar turno
            if 'TURNO' in df.columns:
                df['TURNO'] = df['TURNO'].astype(str).str.strip().str.upper()
                df['TURNO'] = df['TURNO'].apply(lambda x: 'M' if x in ['M', 'MANHÃ', 'MANHA'] else 'T' if x in ['T', 'TARDE'] else 'N' if x in ['N', 'NOITE'] else x)
            
            # Padronizar função e setor
            if 'FUNCAO' in df.columns:
                df['FUNCAO'] = df['FUNCAO'].astype(str).str.strip()
            
            if 'SETOR' in df.columns:
                df['SETOR'] = df['SETOR'].astype(str).str.strip()
            
            # Identificar quais Hard Skills existem
            hard_existentes = [col for col in HARD_SKILLS if col in df.columns]
            soft_existentes = [col for col in SOFT_SKILLS if col in df.columns]
            
            return df, hard_existentes, soft_existentes
            
        except Exception as e:
            st.error(f"❌ Erro ao carregar dados de habilidades: {e}")
            return pd.DataFrame(), [], []
    
    # ======================
    # FUNÇÃO PARA CRIAR GRÁFICO DE TEIA (RADAR) UNIFICADO - TAMANHO REDUZIDO
    # ======================
    def criar_grafico_teia_unificado(colaborador_data, nome, funcao, turno, setor, hard_cols, soft_cols):
        """
        Cria um único gráfico de teia (radar) com Hard Skills e Soft Skills
        Hard Skills do lado esquerdo, Soft Skills do lado direito
        """
        # Separar dados
        hard_values = [colaborador_data.get(col, 0) for col in hard_cols]
        soft_values = [colaborador_data.get(col, 0) for col in soft_cols]
        
        # Verificar se há dados
        if sum(hard_values) == 0 and sum(soft_values) == 0:
            return None
        
        # Unir todas as habilidades (Hard + Soft)
        all_skills = hard_cols + soft_cols
        all_values = hard_values + soft_values
        
        # Número total de variáveis
        N = len(all_skills)
        
        # Ângulos para cada variável
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]  # Fechar o polígono
        
        # Valores (fechar o polígono)
        values = all_values + all_values[:1]
        
        # Criar figura - TAMANHO REDUZIDO
        fig = plt.figure(figsize=(10, 8), facecolor=THEME['bg_card'])
        fig.patch.set_facecolor(THEME['bg_card'])
        
        # Criar subplot polar
        ax = fig.add_subplot(111, projection='polar')
        ax.set_facecolor(THEME['bg_card'])
        
        # Definir cores para Hard Skills e Soft Skills
        hard_colors = [THEME['accent_cyan'] for _ in range(len(hard_cols))]
        soft_colors = [THEME['accent_purple'] for _ in range(len(soft_cols))]
        all_colors = hard_colors + soft_colors
        
        # Plotar o polígono principal com degradê
        ax.plot(angles, values, 'o-', linewidth=2.5, color=THEME['accent_cyan'], alpha=0.8)
        
        # Preencher com cor personalizada (gradiente)
        for i in range(N):
            angle1 = angles[i]
            angle2 = angles[i+1] if i+1 < len(angles) else angles[0]
            value1 = values[i]
            value2 = values[i+1] if i+1 < len(values) else values[0]
            
            if i < len(hard_cols):
                color = THEME['accent_cyan']
                alpha_fill = 0.2
            else:
                color = THEME['accent_purple']
                alpha_fill = 0.2
            
            theta = np.linspace(angle1, angle2, 20)
            ax.fill_between(theta, 0, np.interp(theta, [angle1, angle2], [value1, value2]), 
                           color=color, alpha=alpha_fill)
        
        # Configurar labels
        ax.set_xticks(angles[:-1])
        
        labels = []
        for i, skill in enumerate(all_skills):
            label = skill.replace('_', ' ').title()
            labels.append(label)
        
        ax.set_xticklabels(labels, fontsize=8, fontweight='bold')
        
        # Colorir os labels
        for i, label in enumerate(ax.get_xticklabels()):
            if i < len(hard_cols):
                label.set_color(THEME['accent_cyan'])
            else:
                label.set_color(THEME['accent_purple'])
        
        # Limites - escala máxima 5
        ax.set_ylim(0, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_yticklabels(['1', '2', '3', '4', '5'], fontsize=7)
        ax.grid(True, alpha=0.3)
        
        # Adicionar valores nas pontas
        for i, (angle, value, skill) in enumerate(zip(angles[:-1], all_values, all_skills)):
            if value > 0:
                if i < len(hard_cols):
                    val_color = THEME['accent_cyan']
                else:
                    val_color = THEME['accent_purple']
                
                ax.annotate(f'{value:.0f}', 
                           xy=(angle, value),
                           xytext=(0, 6),
                           textcoords='offset points',
                           ha='center', va='center',
                           fontsize=7, fontweight='bold',
                           color=val_color,
                           bbox=dict(boxstyle='round,pad=0.15', 
                                    facecolor='white', alpha=0.85,
                                    edgecolor=val_color,
                                    linewidth=1))
        
        # ===== TÍTULO PRINCIPAL DA FIGURA =====
        titulo_principal = f"👤 {nome}"
        if funcao and str(funcao).strip() and str(funcao).strip().lower() != 'nan':
            titulo_principal += f" | 📋 {funcao}"
        if turno and str(turno).strip() and str(turno).strip().lower() != 'nan':
            titulo_principal += f" | 🕐 Turno: {turno}"
        if setor and str(setor).strip() and str(setor).strip().lower() != 'nan':
            titulo_principal += f" | 🏢 {setor}"
        
        fig.suptitle(titulo_principal, fontsize=15, fontweight='bold', 
                    color=THEME['text_primary'], y=1.02)
        
        # ===== ADICIONAR LEGENDA =====
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=THEME['accent_cyan'], alpha=0.3, label='🛠️ Hard Skills'),
            Patch(facecolor=THEME['accent_purple'], alpha=0.3, label='💡 Soft Skills')
        ]
        ax.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(1.08, 1.08), fontsize=9)
        
        # Adicionar médias no rodapé
        media_hard = sum(hard_values) / len(hard_values) if hard_values else 0
        media_soft = sum(soft_values) / len(soft_values) if soft_values else 0
        
        fig.text(0.5, 0.02, 
                f'📊 Média Hard Skills: {media_hard:.1f}/10  |  Média Soft Skills: {media_soft:.1f}/10', 
                fontsize=10, ha='center', color=THEME['text_muted'], fontweight='bold')
        
        plt.tight_layout()
        return fig
    
    # ======================
    # CARREGAR DADOS
    # ======================
    with st.spinner("Carregando dados de habilidades..."):
        df, hard_cols, soft_cols = carregar_dados_habilidades()
    
    if df.empty:
        st.warning("⚠️ Não foi possível carregar os dados. Verifique a planilha.")
        st.stop()
    
    # ======================
    # SIDEBAR FILTROS
    # ======================
    with st.sidebar:
        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;
            letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_purple']};margin:20px 0 10px;
            border-top:1px solid {THEME['border_bright']};padding-top:16px'>
            ▸ Filtros · Habilidades
        </div>
        """, unsafe_allow_html=True)
        
        # Filtro de Colaborador
        if 'COLABORADOR' in df.columns:
            colaboradores = sorted([str(c) for c in df['COLABORADOR'].dropna().unique() if str(c).strip() and str(c).strip().lower() != 'nan'])
            colaborador_selecionado = st.selectbox(
                "👤 Colaborador", 
                options=["(Todos)"] + colaboradores,
                key="habilidade_colaborador"
            )
        else:
            colaborador_selecionado = "(Todos)"
            st.warning("⚠️ Coluna 'COLABORADOR' não encontrada")
        
        # Filtro de Turno
        if 'TURNO' in df.columns:
            turnos = sorted([str(t) for t in df['TURNO'].dropna().unique() if str(t).strip() and str(t).strip().lower() != 'nan'])
            turno_selecionado = st.selectbox(
                "🕐 Turno", 
                options=["(Todos)"] + turnos,
                key="habilidade_turno"
            )
        else:
            turno_selecionado = "(Todos)"
        
        # Filtro de Função
        if 'FUNCAO' in df.columns:
            funcoes = sorted([str(f) for f in df['FUNCAO'].dropna().unique() if str(f).strip() and str(f).strip().lower() != 'nan'])
            funcao_selecionada = st.selectbox(
                "📋 Função", 
                options=["(Todos)"] + funcoes,
                key="habilidade_funcao"
            )
        else:
            funcao_selecionada = "(Todos)"
        
        # Filtro de Setor
        if 'SETOR' in df.columns:
            setores = sorted([str(s) for s in df['SETOR'].dropna().unique() if str(s).strip() and str(s).strip().lower() != 'nan'])
            setor_selecionado = st.selectbox(
                "🏢 Setor", 
                options=["(Todos)"] + setores,
                key="habilidade_setor"
            )
        else:
            setor_selecionado = "(Todos)"
        
        st.markdown("---")
        st.caption("📌 Selecione um colaborador ou use filtros para refinar")
        st.caption(f"📊 {len(df)} colaboradores cadastrados")
        
        # Informações das colunas detectadas
        if hard_cols:
            st.caption(f"🛠️ Hard Skills: {len(hard_cols)}")
        if soft_cols:
            st.caption(f"💡 Soft Skills: {len(soft_cols)}")
    
    # ======================
    # APLICAR FILTROS
    # ======================
    df_filtrado = df.copy()
    
    if colaborador_selecionado != "(Todos)":
        df_filtrado = df_filtrado[df_filtrado['COLABORADOR'].astype(str).str.strip() == colaborador_selecionado]
    
    if turno_selecionado != "(Todos)":
        df_filtrado = df_filtrado[df_filtrado['TURNO'].astype(str).str.strip() == turno_selecionado]
    
    if funcao_selecionada != "(Todos)":
        df_filtrado = df_filtrado[df_filtrado['FUNCAO'].astype(str).str.strip() == funcao_selecionada]
    
    if setor_selecionado != "(Todos)":
        df_filtrado = df_filtrado[df_filtrado['SETOR'].astype(str).str.strip() == setor_selecionado]
    
    # ======================
    # KPIS
    # ======================
    total_colaboradores = len(df_filtrado)
    media_hard = 0
    media_soft = 0
    
    if hard_cols and total_colaboradores > 0:
        media_hard = df_filtrado[hard_cols].mean().mean()
    if soft_cols and total_colaboradores > 0:
        media_soft = df_filtrado[soft_cols].mean().mean()
    
    col_k1, col_k2, col_k3 = st.columns(3)
    with col_k1:
        st.metric("👥 Colaboradores", f"{total_colaboradores:,}")
    with col_k2:
        st.metric("🛠️ Média Hard Skills", f"{media_hard:.1f}/10")
    with col_k3:
        st.metric("💡 Média Soft Skills", f"{media_soft:.1f}/10")
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # ======================
    # EXIBIR GRÁFICOS DE TEIA POR COLABORADOR (UNIFICADO)
    # ======================
    if df_filtrado.empty:
        st.warning("⚠️ Nenhum colaborador encontrado com os filtros selecionados.")
        st.stop()
    
    # Se um colaborador específico foi selecionado, mostrar apenas ele
    if colaborador_selecionado != "(Todos)":
        # Mostrar gráfico de teia do colaborador específico
        row = df_filtrado.iloc[0]
        nome = row.get('COLABORADOR', 'Não definido')
        funcao = row.get('FUNCAO', '')
        turno = row.get('TURNO', '')
        setor = row.get('SETOR', '')
        
        # Criar dicionário com dados do colaborador
        dados_colaborador = row.to_dict()
        
        # Criar gráfico de teia unificado
        fig = criar_grafico_teia_unificado(dados_colaborador, nome, funcao, turno, setor, hard_cols, soft_cols)
        
        if fig:
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info(f"📭 Nenhum dado de habilidade disponível para {nome}")
        
        # Mostrar tabela de habilidades detalhada
        with st.expander("📊 Ver detalhamento de habilidades", expanded=False):
            dados_habilidades = []
            
            for col in hard_cols + soft_cols:
                valor = row.get(col, 0)
                if valor > 0:
                    # Formatar nome da habilidade para exibição
                    nome_habilidade = col.replace('_', ' ').title()
                    tipo = '🛠️ Hard Skill' if col in hard_cols else '💡 Soft Skill'
                    dados_habilidades.append({
                        'Habilidade': nome_habilidade,
                        'Nível': f"{valor:.0f}/10",
                        'Tipo': tipo
                    })
            
            if dados_habilidades:
                df_detalhes = pd.DataFrame(dados_habilidades)
                # Ordenar por tipo e depois por nível
                df_detalhes = df_detalhes.sort_values(['Tipo', 'Nível'], ascending=[True, False])
                st.dataframe(df_detalhes, use_container_width=True, hide_index=True)
            else:
                st.info("📭 Nenhuma habilidade registrada")
    
    else:
        # Mostrar gráficos em grade para todos os colaboradores filtrados
        st.markdown(f"### 📊 Gráficos de Habilidades por Colaborador")
        st.caption(f"Exibindo {len(df_filtrado)} colaboradores")
        
        # Número de colunas por linha - 2 gráficos por linha para melhor visualização
        cols_per_row = 2
        
        # Criar uma lista de índices para iterar
        indices = list(range(len(df_filtrado)))
        
        # Agrupar de 2 em 2
        for i in range(0, len(indices), cols_per_row):
            # Criar colunas
            cols = st.columns(cols_per_row)
            
            # Para cada coluna, processar um colaborador
            for j in range(cols_per_row):
                idx = i + j
                if idx < len(df_filtrado):
                    row = df_filtrado.iloc[idx]
                    nome = row.get('COLABORADOR', 'Não definido')
                    funcao = row.get('FUNCAO', '')
                    turno = row.get('TURNO', '')
                    setor = row.get('SETOR', '')
                    
                    dados_colaborador = row.to_dict()
                    fig = criar_grafico_teia_unificado(dados_colaborador, nome, funcao, turno, setor, hard_cols, soft_cols)
                    
                    with cols[j]:
                        if fig:
                            st.pyplot(fig)
                            plt.close(fig)
                        else:
                            st.info(f"📭 Sem dados: {nome}")
        
        # Adicionar botão para expandir todos os gráficos
        with st.expander("📋 Ver todos os colaboradores em lista", expanded=False):
            # Criar tabela resumo
            dados_resumo = []
            for _, row in df_filtrado.iterrows():
                nome = row.get('COLABORADOR', 'Não definido')
                funcao = row.get('FUNCAO', '')
                turno = row.get('TURNO', '')
                setor = row.get('SETOR', '')
                
                # Calcular médias
                hard_vals = [row.get(col, 0) for col in hard_cols] if hard_cols else [0]
                soft_vals = [row.get(col, 0) for col in soft_cols] if soft_cols else [0]
                
                media_hard_col = sum(hard_vals) / len(hard_vals) if hard_vals else 0
                media_soft_col = sum(soft_vals) / len(soft_vals) if soft_vals else 0
                
                dados_resumo.append({
                    'Colaborador': nome,
                    'Função': funcao,
                    'Turno': turno,
                    'Setor': setor,
                    'Hard Skills': f"{media_hard_col:.1f}/10",
                    'Soft Skills': f"{media_soft_col:.1f}/10"
                })
            
            if dados_resumo:
                df_resumo = pd.DataFrame(dados_resumo)
                st.dataframe(df_resumo, use_container_width=True, hide_index=True)
    
    # ======================
    # ESTATÍSTICAS GERAIS
    # ======================
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("### 📊 Estatísticas Gerais")
    
    col_est1, col_est2 = st.columns(2)
    
    with col_est1:
        st.markdown("#### 🛠️ Hard Skills - Média por Colaborador")
        if hard_cols and not df_filtrado.empty:
            medias_hard = {}
            for col in hard_cols:
                if col in df_filtrado.columns:
                    medias_hard[col] = df_filtrado[col].mean()
            
            if medias_hard:
                df_medias_hard = pd.DataFrame(list(medias_hard.items()), columns=['Habilidade', 'Média'])
                df_medias_hard = df_medias_hard.sort_values('Média', ascending=False)
                
                # Formatar nomes para exibição
                df_medias_hard['Habilidade'] = df_medias_hard['Habilidade'].str.replace('_', ' ').str.title()
                
                fig, ax = plt.subplots(figsize=(8, 5), facecolor=THEME['bg_card'])
                ax.set_facecolor(THEME['bg_card'])
                
                bars = ax.barh(range(len(df_medias_hard)), df_medias_hard['Média'], 
                              color=THEME['accent_cyan'], alpha=0.8)
                
                ax.set_yticks(range(len(df_medias_hard)))
                ax.set_yticklabels(df_medias_hard['Habilidade'], fontsize=9)
                ax.set_xlabel('Média', fontsize=10)
                ax.set_title('Média das Hard Skills', fontweight='bold', fontsize=12)
                ax.set_xlim(0, 5)
                
                for bar, val in zip(bars, df_medias_hard['Média']):
                    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                           f'{val:.1f}', va='center', fontsize=9, fontweight='bold')
                
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("📭 Nenhuma Hard Skill encontrada")
        else:
            st.info("📭 Nenhuma Hard Skill encontrada")
    
    with col_est2:
        st.markdown("#### 💡 Soft Skills - Média por Colaborador")
        if soft_cols and not df_filtrado.empty:
            medias_soft = {}
            for col in soft_cols:
                if col in df_filtrado.columns:
                    medias_soft[col] = df_filtrado[col].mean()
            
            if medias_soft:
                df_medias_soft = pd.DataFrame(list(medias_soft.items()), columns=['Habilidade', 'Média'])
                df_medias_soft = df_medias_soft.sort_values('Média', ascending=False)
                
                # Formatar nomes para exibição
                df_medias_soft['Habilidade'] = df_medias_soft['Habilidade'].str.replace('_', ' ').str.title()
                
                fig, ax = plt.subplots(figsize=(8, 5), facecolor=THEME['bg_card'])
                ax.set_facecolor(THEME['bg_card'])
                
                bars = ax.barh(range(len(df_medias_soft)), df_medias_soft['Média'], 
                              color=THEME['accent_purple'], alpha=0.8)
                
                ax.set_yticks(range(len(df_medias_soft)))
                ax.set_yticklabels(df_medias_soft['Habilidade'], fontsize=9)
                ax.set_xlabel('Média', fontsize=10)
                ax.set_title('Média das Soft Skills', fontweight='bold', fontsize=12)
                ax.set_xlim(0, 5)
                
                for bar, val in zip(bars, df_medias_soft['Média']):
                    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                           f'{val:.1f}', va='center', fontsize=9, fontweight='bold')
                
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("📭 Nenhuma Soft Skill encontrada")
        else:
            st.info("📭 Nenhuma Soft Skill encontrada")
    
    # ======================
    # MATRIZ DE HABILIDADES (Tabela Geral)
    # ======================
    with st.expander("📋 Matriz de Habilidades - Todos os Colaboradores", expanded=False):
        if not df_filtrado.empty:
            # Selecionar colunas para exibir
            colunas_base = ['COLABORADOR', 'FUNCAO', 'TURNO', 'SETOR']
            colunas_base_existentes = [c for c in colunas_base if c in df_filtrado.columns]
            
            df_exibicao = df_filtrado[colunas_base_existentes].copy()
            
            # Renomear colunas para exibição
            rename_map = {
                'COLABORADOR': 'Colaborador',
                'FUNCAO': 'Função',
                'TURNO': 'Turno',
                'SETOR': 'Setor'
            }
            df_exibicao = df_exibicao.rename(columns={k: v for k, v in rename_map.items() if k in df_exibicao.columns})
            
            # Calcular médias
            if hard_cols:
                df_exibicao['Média Hard Skills'] = df_filtrado[hard_cols].mean(axis=1).round(1)
            if soft_cols:
                df_exibicao['Média Soft Skills'] = df_filtrado[soft_cols].mean(axis=1).round(1)
            
            # Ordenar por nome
            if 'Colaborador' in df_exibicao.columns:
                df_exibicao = df_exibicao.sort_values('Colaborador')
            
            st.dataframe(df_exibicao, use_container_width=True, hide_index=True, height=400)
            
            # Download da matriz
            csv = df_exibicao.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Baixar Matriz (CSV)",
                data=csv,
                file_name=f"matriz_habilidades_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("📭 Nenhum dado disponível")
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        MAPEAMENTO DE HABILIDADES · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)

# ==================================================================================================
# PRÊMIO PRENSADOS - SOMENTE NÍVEL 0
# ==================================================================================================
elif aba_selecionada == 'PRÊMIO PRENSADOS':
    # ===== VERIFICAÇÃO DE ACESSO - APENAS NÍVEL 0 =====
    nivel_usuario = st.session_state.get('nivel', '')
    
    if nivel_usuario != '0':
        st.error("⛔ **ACESSO NEGADO**")
        st.warning(f"""
        Esta seção é restrita a usuários com **Nível 0** (Administradores).
        
        **Seu nível atual:** `{nivel_usuario if nivel_usuario else 'Não definido'}`
        
        Para acessar esta funcionalidade, entre em contato com um administrador do sistema.
        """)
        if st.button("🔙 Voltar para página inicial"):
            st.rerun()
        st.stop()
    
    # ===== SE PASSOU NA VERIFICAÇÃO, EXECUTA O MÓDULO =====
    render_page_header("PRÊMIO PRENSADOS", f"Relatório de Prêmio · Atualizado {get_horario_brasilia()}", THEME['accent_lime'])
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%); 
                padding: 15px 20px; border-radius: 10px; 
                border-left: 4px solid {THEME['accent_lime']}; margin: 10px 0 20px 0;">
        <span style="font-size: 18px; margin-right: 10px;">📊</span>
        <span style="font-family: 'Rajdhani', sans-serif; font-size: 16px; font-weight: bold; color: {THEME['accent_lime']};">
            GERADOR DE RELATÓRIO DE PRÊMIO
        </span>
        <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {THEME['text_muted']}; margin-left: 15px;">
            Apenas registros com TRS > 100%
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    # ======================
    # FUNÇÃO PARA CONVERTER TIME PARA HORAS DECIMAIS (LOCAL)
    # ======================
    def time_to_decimal_local(time_val):
        """Converte time para horas decimais"""
        from datetime import time as dt_time
        
        if pd.isna(time_val):
            return 0.0
        if isinstance(time_val, dt_time):
            return time_val.hour + time_val.minute/60 + time_val.second/3600
        if isinstance(time_val, datetime):
            return time_val.hour + time_val.minute/60 + time_val.second/3600
        if isinstance(time_val, pd.Timestamp):
            return time_val.hour + time_val.minute/60 + time_val.second/3600
        if isinstance(time_val, str):
            try:
                for fmt in ["%H:%M:%S", "%H:%M", "%H:%M:%S.%f"]:
                    try:
                        t = datetime.strptime(time_val, fmt)
                        return t.hour + t.minute/60 + t.second/3600
                    except:
                        continue
                return float(time_val)
            except:
                return 0.0
        try:
            return float(time_val)
        except:
            return 0.0
    
    # ======================
    # FUNÇÃO PARA VERIFICAR SE ACERTOS É 02:45:00
    # ======================
    def is_acertos_245(time_val):
        """Verifica se o valor de ACERTOS é 02:45:00"""
        if pd.isna(time_val):
            return False
        
        # Converter para string para comparação
        time_str = str(time_val).strip()
        
        # Verificar se é 02:45:00 em diferentes formatos
        formatos_245 = ["02:45:00", "2:45:00", "02:45", "2:45"]
        for fmt in formatos_245:
            if fmt in time_str:
                return True
        
        # Verificar se é um objeto time com 2:45
        if isinstance(time_val, dt_time):
            if time_val.hour == 2 and time_val.minute == 45 and time_val.second == 0:
                return True
        
        return False
    
    # ======================
    # FUNÇÃO PARA CALCULAR HORAS PROGRAMADAS COM REGRA ESPECIAL
    # ======================
    def calcular_horas_programadas(row):
        """
        Calcula as horas programadas.
        Se ACERTOS = 02:45:00, retorna 5.0 horas (05:00:00)
        Caso contrário, usa: HORAS_TOTAIS_DEC + ACERTOS_DEC + MANUT_DEC + 0.25
        """
        # Verificar se ACERTOS é 02:45:00
        if 'ACERTOS' in row and is_acertos_245(row['ACERTOS']):
            return 5.0  # 05:00:00 em horas decimais
        
        # Caso contrário, calcula normalmente
        return row.get('HORAS_TOTAIS_DEC', 0.0) + row.get('ACERTOS_DEC', 0.0) + row.get('MANUT_DEC', 0.0) + 0.25
    
    # ======================
    # FILTROS NA INTERFACE
    # ======================
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    
    with col_f1:
        data_ini = st.date_input(
            "📅 Data Inicial",
            value=datetime.now().date() - timedelta(days=30),
            key="premio_data_ini"
        )
    
    with col_f2:
        data_fim = st.date_input(
            "📅 Data Final",
            value=datetime.now().date(),
            key="premio_data_fim"
        )
    
    with col_f3:
        turno_premio = st.selectbox(
            "🕐 Turno",
            options=["(Todos)", "M", "T", "N"],
            key="premio_turno"
        )
    
    with col_f4:
        prensa_tipo_premio = st.selectbox(
            "🏭 Tipo de Prensa",
            options=["(Todos)", "Semi-Automática", "Automática"],
            key="premio_prensa"
        )
    
    # ======================
    # REFERÊNCIA E OPÇÕES
    # ======================
    col_r1, col_r2 = st.columns([2, 1])
    
    with col_r1:
        referencia_premio = st.text_input(
            "🔍 Referência (parte do código)",
            placeholder="Digite parte da referência para filtrar...",
            key="premio_referencia"
        )
    
    with col_r2:
        st.markdown("<br>", unsafe_allow_html=True)
        gerar_por_mes_premio = st.checkbox(
            "📆 Separar por mês",
            value=False,
            key="premio_separar_mes"
        )
    
    # ======================
    # BOTÃO GERAR RELATÓRIO
    # ======================
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        gerar_relatorio_btn = st.button(
            "📊 GERAR RELATÓRIO",
            type="primary",
            use_container_width=True,
            key="btn_gerar_premio"
        )
    
    # ======================
    # FUNÇÃO PARA GERAR RELATÓRIO EM MEMÓRIA (PDF) COM COLUNAS AJUSTADAS
    # ======================
    def gerar_pdf_premio(df_dados, titulo_extra=""):
        """Gera PDF do relatório em memória e retorna os bytes"""
        from io import BytesIO
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import cm, mm
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        
        buffer = BytesIO()
        
        # Usar orientação paisagem para caber mais colunas
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=1.5*cm,
            rightMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )
        
        story = []
        
        styles = getSampleStyleSheet()
        style_title = ParagraphStyle(
            "title", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=14, spaceAfter=12, fontName='Helvetica-Bold'
        )
        style_subtitle = ParagraphStyle(
            "subtitle", parent=styles["Heading2"], alignment=TA_LEFT, fontSize=10, spaceAfter=8, spaceBefore=10, fontName='Helvetica-Bold'
        )
        style_filter = ParagraphStyle(
            "filter", parent=styles["Normal"], fontSize=8, alignment=TA_LEFT, spaceAfter=8
        )
        
        # TÍTULO - "Prêmio Por Produtividade Prensados"
        titulo = "Prêmio Por Produtividade Prensados"
        if titulo_extra:
            titulo += f" - {titulo_extra}"
        story.append(Paragraph(titulo, style_title))
        story.append(Spacer(1, 0.2 * cm))
        
        # FILTROS
        info_filtros = []
        if prensa_tipo_premio != "(Todos)":
            info_filtros.append(f"Tipo de Prensa: {prensa_tipo_premio}")
            if "Automática" in prensa_tipo_premio:
                info_filtros.append("(BOQUETA = 2)")
            elif "Semi" in prensa_tipo_premio:
                info_filtros.append("(BOQUETA = 1)")
        if turno_premio != "(Todos)":
            info_filtros.append(f"Turno: {turno_premio}")
        if referencia_premio:
            info_filtros.append(f"Referência: {referencia_premio}")
        if data_ini:
            info_filtros.append(f"Data inicial: {data_ini.strftime('%d/%m/%Y')}")
        if data_fim:
            info_filtros.append(f"Data final: {data_fim.strftime('%d/%m/%Y')}")
        info_filtros.append("✅ Apenas registros com TRS > 100%")
        
        if info_filtros:
            story.append(Paragraph("Filtros aplicados: " + " | ".join(info_filtros), style_filter))
            story.append(Spacer(1, 0.3 * cm))
        
        # ===== FUNÇÃO PARA GERAR TABELA COM COLUNAS AJUSTADAS =====
        def criar_tabela(df_tabela, titulo_mes=""):
            if df_tabela.empty:
                return None
            
            # Calcular TRS
            df_calc = df_tabela.copy()
            df_calc["TRS_%"] = 0.0
            mask_meta_positiva = df_calc["META"] > 0
            df_calc.loc[mask_meta_positiva, "TRS_%"] = (df_calc.loc[mask_meta_positiva, "APROVADO"] / df_calc.loc[mask_meta_positiva, "META"] * 100).round(2)
            df_calc["TRS_EXCESSO"] = 0.0
            df_calc.loc[mask_meta_positiva, "TRS_EXCESSO"] = (df_calc.loc[mask_meta_positiva, "TRS_%"] - 100).round(2)
            df_calc.loc[df_calc["TRS_EXCESSO"] < 0, "TRS_EXCESSO"] = 0
            df_calc["PRÊMIO"] = df_calc["APROVADO"] - df_calc["META"]
            
            # Calcular HORAS PROGRAMADAS com a regra especial
            # Se ACERTOS = 02:45:00, HORAS PROGRAMADAS = 05:00:00
            df_calc["HORAS_PROGRAMADAS_CALC"] = df_calc.apply(calcular_horas_programadas, axis=1)
            
            df_filtrado = df_calc[df_calc["TRS_%"] > 100]
            
            if df_filtrado.empty:
                return None
            
            # Cabeçalhos com quebras de linha para caber melhor
            headers = [
                "DATA", "TURNO", "REFERÊNCIA", "META\n(TRS 100%)", 
                "APROVADO", "TRS %\n(Excesso)", "HORAS\nTRABALHADAS", "HORAS\nPROGRAMADAS"
            ]
            
            dados_tabela = [headers]
            
            for _, row in df_filtrado.iterrows():
                horas_totais = row['HORAS_TOTAIS_DEC']
                horas_programadas = row['HORAS_PROGRAMADAS_CALC']  # Usar o valor calculado com a regra
                horas_totais_str = f"{int(horas_totais):02d}:{int((horas_totais % 1) * 60):02d}"
                horas_programadas_str = f"{int(horas_programadas):02d}:{int((horas_programadas % 1) * 60):02d}"
                
                dados_tabela.append([
                    row["DATA"].strftime("%d/%m/%Y"),
                    row["TURNO"],
                    row["REFERÊNCIA"],
                    f"{row['META']:,.0f}",
                    f"{row['APROVADO']:,.0f}",
                    f"{row['TRS_EXCESSO']:.2f}%",
                    horas_totais_str,
                    horas_programadas_str
                ])
            
            # Totais
            total_meta = df_filtrado['META'].sum()
            total_aprovado = df_filtrado['APROVADO'].sum()
            total_media_excesso = df_filtrado['TRS_EXCESSO'].mean()
            total_horas_trabalhadas = df_filtrado['HORAS_TOTAIS_DEC'].sum()
            total_horas_programadas = df_filtrado['HORAS_PROGRAMADAS_CALC'].sum()
            
            total_horas_trab_str = f"{int(total_horas_trabalhadas):02d}:{int((total_horas_trabalhadas % 1) * 60):02d}"
            total_horas_prog_str = f"{int(total_horas_programadas):02d}:{int((total_horas_programadas % 1) * 60):02d}"
            
            linha_total = [
                "TOTAL",
                "",
                "",
                f"{total_meta:,.0f}",
                f"{total_aprovado:,.0f}",
                f"{total_media_excesso:.2f}%",
                total_horas_trab_str,
                total_horas_prog_str
            ]
            dados_tabela.append(linha_total)
            
            # Larguras das colunas ajustadas para caber na página em paisagem
            col_widths = [55, 35, 110, 60, 60, 55, 60, 60]
            
            tabela = Table(dados_tabela, hAlign="LEFT", colWidths=col_widths)
            estilo = TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ])
            
            # Destacar cores
            for i, row in enumerate(df_filtrado.itertuples(), start=1):
                if row.PRÊMIO > 0:
                    estilo.add("TEXTCOLOR", (5, i), (5, i), colors.green)
                if row.TRS_EXCESSO > 0:
                    estilo.add("TEXTCOLOR", (5, i), (5, i), colors.green)
            
            estilo.add("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey)
            estilo.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
            estilo.add("FONTSIZE", (0, -1), (-1, -1), 8)
            tabela.setStyle(estilo)
            
            return tabela, df_filtrado
        
        # ===== GERAR RELATÓRIO =====
        if gerar_por_mes_premio:
            # Separar por mês
            meses_disponiveis = sorted(df_dados["MES_ANO"].unique())
            
            total_registros = 0
            total_meta_geral = 0
            total_aprovado_geral = 0
            total_horas_trab_geral = 0
            total_horas_prog_geral = 0
            total_excesso_geral = 0
            qtd_meses_com_dados = 0
            
            for mes_str in meses_disponiveis:
                df_mes = df_dados[df_dados["MES_ANO"] == mes_str].copy()
                resultado = criar_tabela(df_mes, mes_str)
                
                if resultado:
                    tabela, df_filtrado = resultado
                    story.append(Paragraph(f"MÊS: {mes_str}", style_subtitle))
                    story.append(tabela)
                    story.append(Spacer(1, 0.3 * cm))
                    
                    total_registros += len(df_filtrado)
                    total_meta_geral += df_filtrado['META'].sum()
                    total_aprovado_geral += df_filtrado['APROVADO'].sum()
                    total_horas_trab_geral += df_filtrado['HORAS_TOTAIS_DEC'].sum()
                    total_horas_prog_geral += df_filtrado['HORAS_PROGRAMADAS_CALC'].sum()
                    total_excesso_geral += df_filtrado['TRS_EXCESSO'].mean()
                    qtd_meses_com_dados += 1
            
            # Resumo geral
            if qtd_meses_com_dados > 0:
                story.append(Spacer(1, 0.5 * cm))
                story.append(Paragraph("-" * 80, styles["Normal"]))
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph("RESUMO GERAL DO PERÍODO", style_subtitle))
                story.append(Spacer(1, 0.2 * cm))
                
                total_excesso_medio = total_excesso_geral / qtd_meses_com_dados if qtd_meses_com_dados > 0 else 0
                total_horas_trab_str = f"{int(total_horas_trab_geral):02d}:{int((total_horas_trab_geral % 1) * 60):02d}"
                total_horas_prog_str = f"{int(total_horas_prog_geral):02d}:{int((total_horas_prog_geral % 1) * 60):02d}"
                
                dados_resumo = [
                    ["DATA", "TURNO", "REFERÊNCIA", "META\n(TRS 100%)", "APROVADO", "TRS %\n(Excesso)", "HORAS\nTRABALHADAS", "HORAS\nPROGRAMADAS"],
                    ["TOTAL GERAL", "", "", f"{total_meta_geral:,.0f}", f"{total_aprovado_geral:,.0f}", f"{total_excesso_medio:.2f}%", total_horas_trab_str, total_horas_prog_str]
                ]
                
                col_widths_resumo = [55, 35, 110, 60, 60, 55, 60, 60]
                tabela_resumo = Table(dados_resumo, hAlign="LEFT", colWidths=col_widths_resumo)
                tabela_resumo.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.blue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.lightgrey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(tabela_resumo)
        else:
            # Relatório consolidado
            resultado = criar_tabela(df_dados)
            if resultado:
                tabela, df_filtrado = resultado
                story.append(tabela)
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    
    # ======================
    # PROCESSAR DADOS E GERAR RELATÓRIO
    # ======================
    if gerar_relatorio_btn:
        with st.spinner("🔄 Carregando dados e processando relatório..."):
            # Carregar dados
            df_base = carregar_dados_prensados()
            
            if df_base.empty:
                st.error("❌ Não foi possível carregar os dados da planilha.")
                st.stop()
            
            # Aplicar filtros
            df_filtrado = df_base.copy()
            
            # Filtro de data
            if data_ini:
                df_filtrado = df_filtrado[df_filtrado["DATA"] >= pd.to_datetime(data_ini)]
            if data_fim:
                df_filtrado = df_filtrado[df_filtrado["DATA"] <= pd.to_datetime(data_fim)]
            
            # Filtro de turno
            if turno_premio != "(Todos)" and "TURNO" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["TURNO"] == turno_premio]
            
            # Filtro de referência
            if referencia_premio and "REFERÊNCIA" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["REFERÊNCIA"].fillna('').str.lower().str.contains(referencia_premio.lower())]
            
            # Filtro de tipo de prensa
            if prensa_tipo_premio != "(Todos)" and "BOQUETA" in df_filtrado.columns:
                if "Semi" in prensa_tipo_premio:
                    df_filtrado = df_filtrado[df_filtrado["BOQUETA"] == 1]
                elif "Auto" in prensa_tipo_premio:
                    df_filtrado = df_filtrado[df_filtrado["BOQUETA"] == 2]
            
            # Verificar se há dados
            if df_filtrado.empty:
                st.warning("⚠️ Nenhum dado encontrado com os filtros selecionados.")
                st.stop()
            
            # Preparar dados para o relatório
            df_relatorio = df_filtrado.copy()
            
            # Renomear colunas para compatibilidade
            if "APROVADO FINAL" in df_relatorio.columns:
                df_relatorio["APROVADO"] = df_relatorio["APROVADO FINAL"]
            
            # Garantir colunas necessárias
            colunas_necessarias = ["DATA", "TURNO", "REFERÊNCIA", "TRS 100%", "APROVADO", "HORAS TOTAIS", "ACERTOS", "MANUT."]
            for col in colunas_necessarias:
                if col not in df_relatorio.columns:
                    st.error(f"❌ Coluna '{col}' não encontrada na planilha!")
                    st.stop()
            
            # Renomear para o formato esperado
            df_relatorio = df_relatorio.rename(columns={"TRS 100%": "META"})
            
            # Converter DATA para datetime se não for
            if not pd.api.types.is_datetime64_any_dtype(df_relatorio["DATA"]):
                df_relatorio["DATA"] = pd.to_datetime(df_relatorio["DATA"])
            
            # Criar coluna de mês/ano
            df_relatorio["MES_ANO"] = df_relatorio["DATA"].dt.strftime("%m/%Y")
            
            # Converter horas usando a função local
            df_relatorio["HORAS_TOTAIS_DEC"] = df_relatorio["HORAS TOTAIS"].apply(time_to_decimal_local)
            df_relatorio["ACERTOS_DEC"] = df_relatorio["ACERTOS"].apply(time_to_decimal_local)
            df_relatorio["MANUT_DEC"] = df_relatorio["MANUT."].apply(time_to_decimal_local)
            
            # Gerar PDF em memória
            titulo_extra = f"{data_ini.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
            pdf_bytes = gerar_pdf_premio(df_relatorio, titulo_extra)
            
            if pdf_bytes:
                st.success(f"✅ Relatório gerado com sucesso! {len(df_relatorio)} registros processados.")
                
                # Mostrar preview dos dados com as mesmas colunas do relatório
                with st.expander("📋 Preview dos dados processados", expanded=True):
                    # Criar DataFrame de preview com as mesmas colunas do relatório
                    df_preview = df_relatorio.copy()
                    
                    # Calcular métricas para o preview
                    df_preview["TRS_%"] = 0.0
                    mask_meta = df_preview["META"] > 0
                    df_preview.loc[mask_meta, "TRS_%"] = (df_preview.loc[mask_meta, "APROVADO"] / df_preview.loc[mask_meta, "META"] * 100).round(2)
                    df_preview["TRS_EXCESSO"] = 0.0
                    df_preview.loc[mask_meta, "TRS_EXCESSO"] = (df_preview.loc[mask_meta, "TRS_%"] - 100).round(2)
                    df_preview.loc[df_preview["TRS_EXCESSO"] < 0, "TRS_EXCESSO"] = 0
                    
                    # Calcular HORAS PROGRAMADAS com a regra especial
                    df_preview["HORAS_PROGRAMADAS_CALC"] = df_preview.apply(calcular_horas_programadas, axis=1)
                    
                    # Formatar horas para exibição
                    df_preview["HORAS_TRABALHADAS_STR"] = df_preview["HORAS_TOTAIS_DEC"].apply(
                        lambda x: f"{int(x):02d}:{int((x % 1) * 60):02d}"
                    )
                    df_preview["HORAS_PROGRAMADAS_STR"] = df_preview["HORAS_PROGRAMADAS_CALC"].apply(
                        lambda x: f"{int(x):02d}:{int((x % 1) * 60):02d}"
                    )
                    
                    # Selecionar colunas para preview
                    colunas_preview = ["DATA", "TURNO", "REFERÊNCIA", "META", "APROVADO", "TRS_EXCESSO", "HORAS_TRABALHADAS_STR", "HORAS_PROGRAMADAS_STR"]
                    df_preview_display = df_preview[colunas_preview].copy()
                    
                    # Renomear colunas para exibição
                    df_preview_display.columns = ["DATA", "TURNO", "REFERÊNCIA", "META (TRS 100%)", "APROVADO", "TRS % (Excesso)", "HORAS TRABALHADAS", "HORAS PROGRAMADAS"]
                    
                    # Formatar a coluna TRS
                    df_preview_display["TRS % (Excesso)"] = df_preview_display["TRS % (Excesso)"].apply(lambda x: f"{x:.2f}%" if x > 0 else "0.00%")
                    
                    # Formatar datas
                    df_preview_display["DATA"] = pd.to_datetime(df_preview_display["DATA"]).dt.strftime("%d/%m/%Y")
                    
                    # Formatar números
                    for col in ["META (TRS 100%)", "APROVADO"]:
                        df_preview_display[col] = df_preview_display[col].apply(lambda x: f"{x:,.0f}".replace(",", "."))
                    
                    # Filtrar apenas TRS > 100% para o preview
                    df_preview_display = df_preview_display[df_preview_display["TRS % (Excesso)"] != "0.00%"]
                    
                    st.dataframe(df_preview_display.head(20), use_container_width=True, hide_index=True)
                    st.caption(f"Total: {len(df_relatorio)} registros | Exibindo apenas registros com TRS > 100%")
                
                # Botão de download
                nome_arquivo = f"Premio_Produtividade_Prensados_{datetime.now().strftime('%Y-%m-%d')}.pdf"
                
                col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
                with col_dl2:
                    st.download_button(
                        label="📥 BAIXAR RELATÓRIO PDF",
                        data=pdf_bytes,
                        file_name=nome_arquivo,
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )
            else:
                st.error("❌ Erro ao gerar o relatório PDF.")
    
    # ======================
    # INFORMAÇÕES ADICIONAIS
    # ======================
    with st.expander("ℹ️ Informações sobre o Relatório", expanded=False):
        st.markdown("""
        **📊 O que é este relatório?**
        
        Este relatório gera um documento PDF com os registros de produção que **ultrapassaram 100% de TRS**.
        
        **📋 Colunas do relatório:**
        - **DATA**: Data da produção
        - **TURNO**: Turno de produção (M, T, N)
        - **REFERÊNCIA**: Código da referência produzida
        - **META (TRS 100%)**: Meta de produção para TRS 100%
        - **APROVADO**: Quantidade aprovada
        - **TRS % (Excesso)**: Percentual que excedeu 100% (ex: 23.87% significa TRS 123.87%)
        - **HORAS TRABALHADAS**: Horas efetivamente trabalhadas
        - **HORAS PROGRAMADAS**: Se ACERTOS = 02:45:00, considera 05:00:00; caso contrário, HORAS TOTAIS + ACERTOS + MANUT + 15 min
        
        **🎯 Filtros disponíveis:**
        - Período (Data Inicial e Final)
        - Turno
        - Referência (busca parcial)
        - Tipo de Prensa (Semi-Automática ou Automática)
        
        **📆 Opção "Separar por mês":**
        Ao ativar esta opção, o relatório será organizado com uma seção para cada mês do período selecionado, facilitando a análise mensal.
        """)
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        PRÊMIO PRENSADOS · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)
# ==================================================================================================
# FERRAMENTARIA - GERENCIAMENTO DE MOLDES (VERSÃO FINAL CORRIGIDA)
# ==================================================================================================
elif aba_selecionada == 'FERRAMENTARIA':
    render_page_header("🛠️ FERRAMENTARIA", 
                       f"Gerenciamento de Moldes · Atualizado {get_horario_brasilia()}", 
                       THEME['accent_cyan'])
    
    # ======================
    # CONFIGURAÇÃO DA PLANILHA
    # ======================
    ID_PLANILHA_FERRAMENTARIA = '12xXYNhrGWP4PMvcdLSMFaMIM-CcLPYyvfBGD0I7Gibg'
    ABA_FERRAMENTARIA = 'MOLDES'
    
    # ======================
    # INICIALIZAR SESSION STATE
    # ======================
    if 'caminho_navegacao' not in st.session_state:
        st.session_state.caminho_navegacao = []
    
    if 'ferramental_selecionado' not in st.session_state:
        st.session_state.ferramental_selecionado = None
    
    if 'mostrar_formulario_novo' not in st.session_state:
        st.session_state.mostrar_formulario_novo = False
    
    def resetar_navegacao():
        st.session_state.caminho_navegacao = []
    
    def navegar_para_pasta(nome_pasta: str, pasta_id: str):
        st.session_state.caminho_navegacao.append({
            "nome": nome_pasta,
            "id": pasta_id
        })
    
    def voltar_nivel(indice: int):
        st.session_state.caminho_navegacao = st.session_state.caminho_navegacao[:indice]
    
    # ======================
    # FUNÇÃO PARA OBTER THUMBNAIL
    # ======================
    def obter_thumbnail(file_id: str, tamanho: str = "w400") -> str:
        if not file_id:
            return ""
        return f"https://drive.google.com/thumbnail?id={file_id}&sz={tamanho}"
    
    # ======================
    # FUNÇÃO PARA LISTAR CONTEÚDO DO GOOGLE DRIVE
    # ======================
    def listar_conteudo_drive(pasta_id: str) -> Dict[str, Any]:
        resultado = {
            "pastas": [],
            "arquivos": [],
            "erro": None,
            "nome_pasta": ""
        }
        
        if not pasta_id or pasta_id.strip() == "":
            resultado["erro"] = "ID da pasta vazio"
            return resultado
        
        try:
            from googleapiclient.discovery import build
            from google.oauth2.service_account import Credentials
            import re
            
            try:
                if 'gcp_service_account' in st.secrets:
                    creds_dict = dict(st.secrets["gcp_service_account"])
                    creds = Credentials.from_service_account_info(
                        creds_dict,
                        scopes=['https://www.googleapis.com/auth/drive.readonly']
                    )
                else:
                    caminhos_credenciais = [
                        r'C:\Users\elton\OneDrive\Documentos\dashboard-gerencial-492613-042470f98e27.json',
                        r'dashboard-gerencial-492613-042470f98e27.json',
                    ]
                    creds = None
                    for caminho in caminhos_credenciais:
                        try:
                            if os.path.exists(caminho):
                                creds = Credentials.from_service_account_file(
                                    caminho,
                                    scopes=['https://www.googleapis.com/auth/drive.readonly']
                                )
                                break
                        except:
                            pass
                    
                    if not creds:
                        resultado["erro"] = "Não foi possível carregar as credenciais"
                        return resultado
                
                drive_service = build('drive', 'v3', credentials=creds)
                
                try:
                    pasta_info = drive_service.files().get(
                        fileId=pasta_id,
                        fields="name"
                    ).execute()
                    resultado["nome_pasta"] = pasta_info.get('name', 'Pasta')
                except:
                    resultado["nome_pasta"] = "Pasta"
                
                query = f"'{pasta_id}' in parents and trashed = false"
                results = drive_service.files().list(
                    q=query,
                    fields="files(id, name, mimeType, webViewLink, size, modifiedTime, iconLink)",
                    pageSize=100
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    nome = item.get('name', '')
                    mime_type = item.get('mimeType', '')
                    
                    if mime_type == 'application/vnd.google-apps.folder':
                        resultado["pastas"].append({
                            "nome": nome,
                            "id": item.get('id'),
                            "link": f"https://drive.google.com/drive/folders/{item.get('id')}",
                            "tipo": "pasta"
                        })
                    else:
                        extensao = nome.split('.')[-1].upper() if '.' in nome else ''
                        icone = get_icone_arquivo(extensao)
                        web_link = item.get('webViewLink')
                        if not web_link:
                            web_link = f"https://drive.google.com/file/d/{item.get('id')}/view"
                        
                        is_imagem = extensao in ['JPG', 'JPEG', 'PNG', 'GIF', 'WEBP', 'SVG', 'BMP', 'ICO']
                        thumbnail = obter_thumbnail(item.get('id'), "w400") if is_imagem else ""
                        
                        resultado["arquivos"].append({
                            "nome": nome,
                            "id": item.get('id'),
                            "link": web_link,
                            "tipo": "arquivo",
                            "extensao": extensao,
                            "icone": icone,
                            "thumbnail": thumbnail,
                            "is_imagem": is_imagem,
                            "modificado": item.get('modifiedTime', '')
                        })
                
                resultado["pastas"] = sorted(resultado["pastas"], key=lambda x: x["nome"].lower())
                resultado["arquivos"] = sorted(resultado["arquivos"], key=lambda x: x["nome"].lower())
                
            except Exception as e:
                resultado["erro"] = f"Erro na API: {str(e)}"
        
        except Exception as e:
            resultado["erro"] = f"Erro geral: {str(e)}"
        
        return resultado
    
    def get_icone_arquivo(extensao: str) -> str:
        icones = {
            'PDF': '📄', 'DOC': '📝', 'DOCX': '📝',
            'XLS': '📊', 'XLSX': '📊',
            'PPT': '📽️', 'PPTX': '📽️',
            'JPG': '🖼️', 'JPEG': '🖼️', 'PNG': '🖼️',
            'GIF': '🖼️', 'WEBP': '🖼️', 'SVG': '🖼️',
            'MP4': '🎬', 'MP3': '🎵',
            'ZIP': '📦', 'RAR': '📦',
            'TXT': '📃', 'CSV': '📊',
            'PSD': '🎨', 'AI': '🎨',
        }
        return icones.get(extensao.upper(), '📎')
    
    # ======================
    # FUNÇÃO PARA EXTRAIR ID DO LINK
    # ======================
    def extrair_id_drive(link: str) -> str:
        if not link:
            return ""
        import re
        patterns = [
            r'\/d\/([a-zA-Z0-9_-]+)',
            r'\/folders\/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'([a-zA-Z0-9_-]{28,})'
        ]
        for pattern in patterns:
            match = re.search(pattern, link)
            if match:
                return match.group(1)
        return link
    
    # ======================
    # CSS COMPLETO - SEM BOTÕES VISÍVEIS
    # ======================
    st.markdown("""
    <style>
    .ferramentaria-container {
        max-width: 100%;
        padding: 5px 0;
    }
    
    /* Breadcrumb */
    .breadcrumb-profissional {
        display: flex;
        align-items: center;
        padding: 10px 16px;
        background: linear-gradient(135deg, #f8f9fc 0%, #eef1f5 100%);
        border-radius: 10px;
        margin-bottom: 16px;
        border: 1px solid #e0e4e8;
        flex-wrap: wrap;
        gap: 4px;
        font-size: 13px;
    }
    .breadcrumb-profissional .icone-inicio {
        font-size: 18px;
        margin-right: 6px;
        color: #666;
    }
    .breadcrumb-profissional .sep {
        color: #b0b8c0;
        margin: 0 2px;
        font-weight: 300;
    }
    .breadcrumb-profissional .atual {
        font-weight: 600;
        color: #1a1a2e;
        padding: 4px 10px;
        background: rgba(0,120,212,0.08);
        border-radius: 6px;
    }
    
    /* Grid de Pastas - Cards com links (SEM BOTÕES VISÍVEIS) */
    .pasta-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
        gap: 14px;
        margin: 12px 0;
    }
    .pasta-card {
        background: white;
        border: 1px solid #e4e8ed;
        border-radius: 12px;
        padding: 18px 12px;
        text-align: center;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        text-decoration: none;
        color: #1a1a2e;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
        position: relative;
        overflow: hidden;
        display: block;
        cursor: pointer;
    }
    .pasta-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #0078D4, #00a8ff);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    .pasta-card:hover::before {
        opacity: 1;
    }
    .pasta-card:hover {
        transform: translateY(-6px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.1);
        border-color: #0078D4;
    }
    .pasta-card .icone { font-size: 40px; display: block; margin-bottom: 6px; }
    .pasta-card .nome { font-size: 13px; font-weight: 600; word-break: break-word; }
    .pasta-card .desc { font-size: 11px; color: #888; margin-top: 4px; }
    .pasta-card .seta { 
        font-size: 12px; 
        color: #0078D4; 
        margin-top: 8px; 
        display: inline-block;
        opacity: 0.6;
        transition: opacity 0.2s ease;
    }
    .pasta-card:hover .seta { opacity: 1; }
    
    .pasta-entrada { border-left: 4px solid #28a745; }
    .pasta-saida { border-left: 4px solid #dc3545; }
    .pasta-forma { border-left: 4px solid #0078D4; }
    .pasta-data { border-left: 4px solid #f59e0b; }
    
    /* Grid de Arquivos com miniaturas */
    .arquivo-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 16px;
        margin: 12px 0;
    }
    .arquivo-card {
        background: white;
        border: 1px solid #e4e8ed;
        border-radius: 12px;
        padding: 12px;
        display: flex;
        flex-direction: column;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        text-decoration: none;
        color: #1a1a2e;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
        overflow: hidden;
    }
    .arquivo-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        border-color: #28a745;
    }
    .arquivo-card .thumbnail-container {
        width: 100%;
        height: 180px;
        background: #f0f2f5;
        border-radius: 8px;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 10px;
        position: relative;
    }
    .arquivo-card .thumbnail-container img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        background: #f8f9fa;
    }
    .arquivo-card .thumbnail-container .icone-grande {
        font-size: 56px;
        opacity: 0.3;
    }
    .arquivo-card .info {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 0 4px;
    }
    .arquivo-card .info .icone { font-size: 20px; flex-shrink: 0; }
    .arquivo-card .info .nome { font-size: 13px; font-weight: 500; flex: 1; word-break: break-word; line-height: 1.3; max-height: 36px; overflow: hidden; text-overflow: ellipsis; }
    .arquivo-card .info .ext { font-size: 10px; color: #888; background: #f0f2f5; padding: 2px 10px; border-radius: 4px; flex-shrink: 0; font-weight: 600; }
    .arquivo-card .info .link-icon { font-size: 16px; color: #0078D4; flex-shrink: 0; }
    
    /* Árvore Hierárquica - SEM DIV ESCAPADA */
    .arvore-container {
        background: white;
        border-radius: 10px;
        padding: 12px 16px;
        border: 1px solid #e4e8ed;
        margin-bottom: 12px;
    }
    .arvore-titulo {
        font-weight: 600;
        font-size: 13px;
        color: #666;
        margin-bottom: 8px;
    }
    .arvore-item {
        display: flex;
        align-items: center;
        padding: 4px 8px;
        border-radius: 6px;
        gap: 8px;
    }
    .arvore-item .nivel {
        color: #b0b8c0;
        font-size: 14px;
        width: 20px;
        text-align: center;
        flex-shrink: 0;
    }
    .arvore-item .icone { font-size: 18px; flex-shrink: 0; }
    .arvore-item .nome { font-size: 13px; color: #333; font-weight: 500; }
    .arvore-item .nome-atual { font-weight: 600; color: #0078D4; }
    .arvore-item .seta { color: #0078D4; margin-left: auto; font-size: 12px; opacity: 0.5; }
    .arvore-linha {
        display: flex;
        align-items: center;
        padding-left: 20px;
        border-left: 2px solid #e4e8ed;
        margin-left: 10px;
    }
    
    /* Botões de navegação (apenas Voltar e Raiz) */
    .nav-botoes {
        display: flex;
        gap: 12px;
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid #e4e8ed;
    }
    .nav-botoes button {
        flex: 1;
        padding: 10px 16px;
        border: 1px solid #dce0e5;
        border-radius: 8px;
        background: white;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 13px;
        font-weight: 500;
        color: #333;
    }
    .nav-botoes button:hover:not(:disabled) {
        background: #f0f2f5;
        border-color: #0078D4;
        color: #0078D4;
    }
    .nav-botoes button:disabled { opacity: 0.4; cursor: not-allowed; }
    
    /* Títulos */
    .titulo-secao {
        font-weight: 600;
        font-size: 15px;
        color: #1a1a2e;
        margin: 18px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .titulo-secao .badge {
        background: #e8ecf1;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 11px;
        color: #666;
        font-weight: 500;
    }
    .vazio-box {
        text-align: center;
        padding: 30px;
        color: #999;
        background: #f8f9fa;
        border-radius: 10px;
        border: 2px dashed #e0e0e0;
    }
    
    /* Esconder botões de navegação de pasta (deixar apenas o card) */
    .pasta-btn-hidden {
        display: none !important;
    }
    
    @media (max-width: 768px) {
        .pasta-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
        .arquivo-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
        .breadcrumb-profissional { font-size: 11px; padding: 8px 12px; }
        .arquivo-card .thumbnail-container { height: 140px; }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # ======================
    # FUNÇÃO RENDERIZAR ÁRVORE HIERÁRQUICA
    # ======================
    def renderizar_arvore_hierarquica():
        """Renderiza a árvore hierárquica de navegação"""
        
        if not st.session_state.caminho_navegacao:
            return
        
        st.markdown('<div class="arvore-container">', unsafe_allow_html=True)
        st.markdown('<div class="arvore-titulo">📂 Caminho atual</div>', unsafe_allow_html=True)
        
        # Raiz - usa botão estilizado como texto
        col_raiz1, col_raiz2 = st.columns([4, 1])
        with col_raiz1:
            st.markdown("""
            <div class="arvore-item">
                <span class="nivel">📁</span>
                <span class="icone">🏠</span>
                <span class="nome" style="color:#0078D4;cursor:pointer;">Raiz</span>
                <span class="seta">›</span>
            </div>
            """, unsafe_allow_html=True)
        with col_raiz2:
            if st.button("↩️", key="btn_raiz_arvore", help="Voltar para a raiz"):
                resetar_navegacao()
                st.rerun()
        
        # Itens do caminho
        for i, pasta in enumerate(st.session_state.caminho_navegacao):
            is_ultimo = (i == len(st.session_state.caminho_navegacao) - 1)
            
            nome_upper = pasta['nome'].upper()
            if nome_upper == "ENTRADA":
                icone = "📥"
            elif nome_upper == "SAÍDA":
                icone = "📤"
            elif "FORMA" in nome_upper or "MOLDE" in nome_upper:
                icone = "🔧"
            else:
                icone = "📅"
            
            classe_nome = "nome-atual" if is_ultimo else "nome"
            
            if is_ultimo:
                # Item atual - apenas texto
                st.markdown(f'''
                <div class="arvore-linha">
                    <div class="arvore-item">
                        <span class="nivel">├─</span>
                        <span class="icone">{icone}</span>
                        <span class="{classe_nome}">{pasta['nome']}</span>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            else:
                # Item que pode ser clicado para voltar
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f'''
                    <div class="arvore-linha">
                        <div class="arvore-item">
                            <span class="nivel">├─</span>
                            <span class="icone">{icone}</span>
                            <span class="{classe_nome}">{pasta['nome']}</span>
                            <span class="seta">›</span>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
                with col2:
                    if st.button("↩️", key=f"btn_arvore_{i}", help=f"Voltar para {pasta['nome']}"):
                        voltar_nivel(i + 1)
                        st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # ======================
    # FUNÇÃO RENDERIZAR EXPLORADOR HIERÁRQUICO
    # ======================
    def renderizar_explorador_hierarquico(link_pasta: str, nome_ferramental: str):
        """Renderiza um explorador hierárquico com navegação por pastas"""
        
        if not link_pasta or link_pasta.strip() == "":
            st.info("📭 Nenhuma pasta configurada.")
            return
        
        pasta_raiz_id = extrair_id_drive(link_pasta)
        
        if not pasta_raiz_id:
            st.warning("⚠️ Não foi possível identificar a pasta.")
            return
        
        if st.session_state.caminho_navegacao:
            pasta_atual_id = st.session_state.caminho_navegacao[-1]["id"]
            pasta_atual_nome = st.session_state.caminho_navegacao[-1]["nome"]
        else:
            pasta_atual_id = pasta_raiz_id
            pasta_atual_nome = "Raiz"
        
        # Breadcrumb
        st.markdown('<div class="breadcrumb-profissional">', unsafe_allow_html=True)
        st.markdown('<span class="icone-inicio">📂</span>', unsafe_allow_html=True)
        
        if st.button("🏠 Raiz", key="btn_raiz_breadcrumb"):
            resetar_navegacao()
            st.rerun()
        
        for i, pasta in enumerate(st.session_state.caminho_navegacao):
            st.markdown('<span class="sep">›</span>', unsafe_allow_html=True)
            if i == len(st.session_state.caminho_navegacao) - 1:
                st.markdown(f'<span class="atual">{pasta["nome"]}</span>', unsafe_allow_html=True)
            else:
                if st.button(pasta["nome"], key=f"bread_{i}"):
                    voltar_nivel(i + 1)
                    st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Árvore
        renderizar_arvore_hierarquica()
        
        # Conteúdo
        with st.spinner(f"📂 Carregando pasta: {pasta_atual_nome}..."):
            conteudo = listar_conteudo_drive(pasta_atual_id)
        
        if conteudo.get("erro"):
            st.warning(f"⚠️ Erro: {conteudo['erro']}")
            st.markdown(f"""
            <div style="text-align:center;margin:10px 0;">
                <a href="{link_pasta}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;">
                    <div style="background:#0078D4;color:white;padding:10px 20px;border-radius:8px;display:inline-block;">
                        📂 Abrir pasta no Google Drive
                    </div>
                </a>
            </div>
            """, unsafe_allow_html=True)
            return
        
        # ===== PASTAS - CARDS COM LINKS (SEM BOTÕES VISÍVEIS) =====
        if conteudo["pastas"]:
            st.markdown(f'<div class="titulo-secao">📁 Pastas <span class="badge">{len(conteudo["pastas"])}</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="pasta-grid">', unsafe_allow_html=True)
            
            for pasta in conteudo["pastas"]:
                nome_upper = pasta['nome'].upper()
                if nome_upper == "ENTRADA":
                    classe = "pasta-entrada"
                    icone = "📥"
                    desc = "Entrada de manutenção"
                elif nome_upper == "SAÍDA":
                    classe = "pasta-saida"
                    icone = "📤"
                    desc = "Saída de manutenção"
                elif "FORMA" in nome_upper or "MOLDE" in nome_upper:
                    classe = "pasta-forma"
                    icone = "🔧"
                    desc = "Ferramental"
                else:
                    classe = "pasta-data"
                    icone = "📅"
                    desc = "Pasta"
                
                # Card inteiro é clicável - usa onclick para navegar
                # Botão hidden com classe para esconder
                st.markdown(f"""
                <div class="pasta-card {classe}" onclick="document.getElementById('btn_pasta_{pasta['id']}').click();">
                    <span class="icone">{icone}</span>
                    <div class="nome">{pasta['nome']}</div>
                    <div class="desc">{desc}</div>
                    <span class="seta">▶ Clique para entrar</span>
                </div>
                """, unsafe_allow_html=True)
                
                # Botão hidden (invisível) que é acionado pelo clique no card
                st.markdown(f"""
                <div style="display:none;">
                    {st.button(f"Entrar", key=f"pasta_{pasta['id']}", help=f"Entrar em {pasta['nome']}")}
                </div>
                """, unsafe_allow_html=True)
                
                # Processar o clique do botão hidden
                if st.session_state.get(f"pasta_{pasta['id']}", False):
                    navegar_para_pasta(pasta['nome'], pasta['id'])
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # ===== ARQUIVOS =====
        if conteudo["arquivos"]:
            st.markdown(f'<div class="titulo-secao">📄 Arquivos <span class="badge">{len(conteudo["arquivos"])}</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="arquivo-grid">', unsafe_allow_html=True)
            
            for arquivo in conteudo["arquivos"]:
                tem_thumbnail = arquivo.get('is_imagem', False) and arquivo.get('thumbnail')
                
                st.markdown(f"""
                <a href="{arquivo['link']}" target="_blank" rel="noopener noreferrer" class="arquivo-card">
                    <div class="thumbnail-container">
                        {f'<img src="{arquivo["thumbnail"]}" alt="{arquivo["nome"]}" loading="lazy" onerror="this.style.display=\'none\'">' if tem_thumbnail else f'<span class="icone-grande">{arquivo["icone"]}</span>'}
                    </div>
                    <div class="info">
                        <span class="icone">{arquivo['icone']}</span>
                        <span class="nome">{arquivo['nome']}</span>
                        <span class="ext">{arquivo['extensao']}</span>
                        <span class="link-icon">↗</span>
                    </div>
                </a>
                """, unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        if not conteudo["pastas"] and not conteudo["arquivos"]:
            st.markdown('<div class="vazio-box">📭 Esta pasta está vazia.</div>', unsafe_allow_html=True)
        
        # Botões de navegação (Voltar e Raiz)
        st.markdown('<div class="nav-botoes">', unsafe_allow_html=True)
        
        if st.session_state.caminho_navegacao:
            if st.button("⬅️ Voltar", use_container_width=True):
                voltar_nivel(len(st.session_state.caminho_navegacao) - 1)
                st.rerun()
        else:
            st.button("⬅️ Voltar", disabled=True, use_container_width=True)
        
        if st.button("🏠 Ir para Raiz", use_container_width=True, key="btn_nav_raiz"):
            resetar_navegacao()
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # ======================
    # FUNÇÃO RENDERIZAR MANUTENÇÃO
    # ======================
    def renderizar_manutencao(link_manutencao: str, nome_ferramental: str):
        st.markdown("---")
        st.markdown("### 🔧 Manutenções do Ferramental")
        
        if not link_manutencao or link_manutencao.strip() == "":
            st.info("📭 Nenhuma pasta de manutenção configurada.")
            return
        
        if 'ferramental_atual' not in st.session_state or st.session_state.ferramental_atual != nome_ferramental:
            st.session_state.ferramental_atual = nome_ferramental
            resetar_navegacao()
        
        renderizar_explorador_hierarquico(link_manutencao, nome_ferramental)
    
    # ======================
    # DATACLASS
    # ======================
    @dataclass
    class Ferramental:
        id: str = ""
        pcp: str = ""
        cliente: str = ""
        descricao: str = ""
        data_inicial: str = ""
        avaliacao_inicial: str = ""
        desenho: str = ""
        gabarito: str = ""
        plano_controle: str = ""
        plano_acao: str = ""
        manutencao: str = ""
    
    # ======================
    # FUNÇÕES DE CARREGAMENTO
    # ======================
    @retry_on_quota()
    @st.cache_data(ttl=600)
    def carregar_ferramentais_dict(filtros: Dict[str, Any] = None) -> List[Dict]:
        registros = []
        try:
            client = get_gspread_client()
            if client is None:
                return registros
            
            spreadsheet = client.open_by_key(ID_PLANILHA_FERRAMENTARIA)
            sheet = spreadsheet.worksheet(ABA_FERRAMENTARIA)
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return registros
            
            for idx, row in enumerate(todos_dados[1:], start=2):
                if len(row) < 5:
                    continue
                try:
                    registro = {
                        'id': row[0].strip() if row[0] else f"FER-{idx:03d}",
                        'pcp': row[1].strip() if len(row) > 1 and row[1] else "",
                        'cliente': row[2].strip() if len(row) > 2 and row[2] else "",
                        'descricao': row[3].strip() if len(row) > 3 and row[3] else "",
                        'data_inicial': row[4].strip() if len(row) > 4 and row[4] else "",
                        'avaliacao_inicial': row[5].strip() if len(row) > 5 and row[5] else "",
                        'desenho': row[6].strip() if len(row) > 6 and row[6] else "",
                        'gabarito': row[7].strip() if len(row) > 7 and row[7] else "",
                        'plano_controle': row[8].strip() if len(row) > 8 and row[8] else "",
                        'plano_acao': row[9].strip() if len(row) > 9 and row[9] else "",
                        'manutencao': row[10].strip() if len(row) > 10 and row[10] else ""
                    }
                    registros.append(registro)
                except:
                    continue
            
            if filtros and registros:
                registros_filtrados = []
                for r in registros:
                    incluir = True
                    if filtros.get('pcp') and filtros['pcp'].upper() != r.get('pcp', '').upper():
                        incluir = False
                    if filtros.get('cliente') and filtros['cliente'].lower() not in r.get('cliente', '').lower():
                        incluir = False
                    if filtros.get('descricao') and filtros['descricao'].lower() not in r.get('descricao', '').lower():
                        incluir = False
                    if incluir:
                        registros_filtrados.append(r)
                return registros_filtrados
            return registros
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e):
                return registros
            return registros
    
    def dict_para_ferramental(data: dict) -> Ferramental:
        return Ferramental(
            id=data.get('id', ''),
            pcp=data.get('pcp', ''),
            cliente=data.get('cliente', ''),
            descricao=data.get('descricao', ''),
            data_inicial=data.get('data_inicial', ''),
            avaliacao_inicial=data.get('avaliacao_inicial', ''),
            desenho=data.get('desenho', ''),
            gabarito=data.get('gabarito', ''),
            plano_controle=data.get('plano_controle', ''),
            plano_acao=data.get('plano_acao', ''),
            manutencao=data.get('manutencao', '')
        )
    
    def salvar_ferramental(registro: Ferramental) -> tuple:
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar"
            sheet = client.open_by_key(ID_PLANILHA_FERRAMENTARIA).worksheet(ABA_FERRAMENTARIA)
            dados = [
                registro.id, registro.pcp, registro.cliente, registro.descricao,
                registro.data_inicial, registro.avaliacao_inicial, registro.desenho,
                registro.gabarito, registro.plano_controle, registro.plano_acao,
                registro.manutencao
            ]
            sheet.append_row(dados)
            st.cache_data.clear()
            return True, "✅ Salvo com sucesso!"
        except Exception as e:
            return False, f"❌ Erro: {e}"
    
    # ======================
    # FUNÇÃO RENDERIZAR LINK
    # ======================
    def renderizar_link_botao(link: str, label: str, icon: str, cor: str = None):
        if not link or link.strip() == "":
            st.markdown(f"""
            <div style="background:#f8f9fa;padding:10px;border-radius:8px;border:1px dashed #ddd;text-align:center;color:#999;">
                {icon} {label} <span style="font-size:11px;">(não disponível)</span>
            </div>
            """, unsafe_allow_html=True)
            return
        
        if cor is None:
            cor = THEME['accent_cyan']
        
        st.markdown(f"""
        <a href="{link}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;">
            <div style="background:white;padding:10px 15px;border-radius:8px;border:1px solid {cor};border-left:4px solid {cor};
                        transition:all 0.2s ease;display:flex;align-items:center;gap:10px;box-shadow:0 1px 3px rgba(0,0,0,0.05);cursor:pointer;">
                <span style="font-size:20px;">{icon}</span>
                <div style="flex:1;">
                    <div style="font-weight:600;font-size:14px;color:#333;">{label}</div>
                    <div style="font-size:11px;color:#666;word-break:break-all;">{link[:50]}{'...' if len(link) > 50 else ''}</div>
                </div>
                <span style="font-size:18px;color:{cor};">↗</span>
            </div>
        </a>
        """, unsafe_allow_html=True)
    
    # ======================
    # FUNÇÃO RENDERIZAR DETALHES
    # ======================
    def renderizar_detalhes_ferramental(registro: Ferramental):
        st.markdown(f"""
        <div style="background:{THEME['bg_card']};border-radius:12px;padding:20px;border:1px solid {THEME['border_bright']};
                    box-shadow:0 2px 8px rgba(0,0,0,0.05);margin-top:20px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                <div style="display:flex;align-items:center;gap:12px;">
                    <span style="font-size:28px;">🔧</span>
                    <div>
                        <div style="font-size:20px;font-weight:700;color:{THEME['text_primary']};">{registro.descricao or 'Sem descrição'}</div>
                        <div style="font-size:13px;color:{THEME['text_muted']};">ID: {registro.id} | PCP: {registro.pcp} | Cliente: {registro.cliente}</div>
                    </div>
                </div>
                <div style="font-size:13px;color:{THEME['text_muted']};">📅 {registro.data_inicial or 'N/A'}</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="font-weight:600;font-size:15px;margin:15px 0 10px 0;color:#333;border-bottom:1px solid #e0e0e0;padding-bottom:8px;">
            📄 Documentação do Ferramental
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            renderizar_link_botao(registro.avaliacao_inicial, "Avaliação Inicial", "📋", THEME['accent_cyan'])
            st.markdown("<br>", unsafe_allow_html=True)
            renderizar_link_botao(registro.desenho, "Desenho", "🎨", THEME['accent_purple'])
            st.markdown("<br>", unsafe_allow_html=True)
            renderizar_link_botao(registro.gabarito, "Gabarito", "📐", THEME['accent_yellow'])
        with col2:
            renderizar_link_botao(registro.plano_controle, "Plano Controle", "📋", THEME['accent_orange'])
            st.markdown("<br>", unsafe_allow_html=True)
            renderizar_link_botao(registro.plano_acao, "Plano Ação", "🎯", THEME['accent_red'])
        
        renderizar_manutencao(registro.manutencao, registro.descricao or 'Ferramental')
        st.markdown('</div>', unsafe_allow_html=True)
    
    # ======================
    # INTERFACE PRINCIPAL
    # ======================
    st.markdown("### 🔍 Filtros")
    
    with st.spinner("🔄 Carregando dados..."):
        dados_dict = carregar_ferramentais_dict()
        todos_ferramentais = [dict_para_ferramental(d) for d in dados_dict]
    
    if not todos_ferramentais:
        st.info("📭 Nenhum ferramental cadastrado. Cadastre um novo.")
    
    opcoes_pcp = sorted(set([f.pcp for f in todos_ferramentais if f.pcp]))
    opcoes_cliente = sorted(set([f.cliente for f in todos_ferramentais if f.cliente]))
    
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_pcp = st.selectbox("📋 PCP", options=["(Todos)"] + opcoes_pcp if opcoes_pcp else ["(Todos)"])
    with col_f2:
        filtro_cliente = st.selectbox("🏢 Cliente", options=["(Todos)"] + opcoes_cliente if opcoes_cliente else ["(Todos)"])
    with col_f3:
        filtro_descricao = st.text_input("🔎 Descrição", placeholder="Digite parte da descrição...")
    
    st.markdown("---")
    
    filtros = {}
    if filtro_pcp != "(Todos)": filtros['pcp'] = filtro_pcp
    if filtro_cliente != "(Todos)": filtros['cliente'] = filtro_cliente
    if filtro_descricao and filtro_descricao.strip(): filtros['descricao'] = filtro_descricao.strip()
    
    if filtros:
        ferramentais_filtrados = [dict_para_ferramental(d) for d in carregar_ferramentais_dict(filtros)]
    else:
        ferramentais_filtrados = todos_ferramentais
    
    col_count, col_add = st.columns([3, 1])
    with col_count:
        if ferramentais_filtrados:
            st.markdown(f"""
            <div style="font-size:14px;color:{THEME['text_muted']};padding:8px 0;">
                📊 <b>{len(ferramentais_filtrados)}</b> ferramentais encontrados
                {f' (filtrados de {len(todos_ferramentais)} totais)' if filtros else ''}
            </div>
            """, unsafe_allow_html=True)
    with col_add:
        if st.button("➕ NOVO FERRAMENTAL", type="primary", use_container_width=True):
            st.session_state.mostrar_formulario_novo = True
    
    if ferramentais_filtrados:
        st.markdown("""
        <div style="font-weight:600;font-size:16px;color:#333;margin:20px 0 10px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
            📋 Lista de Ferramentais
        </div>
        """, unsafe_allow_html=True)
        
        dados_tabela = []
        for f in ferramentais_filtrados:
            tem_docs = any([f.avaliacao_inicial, f.desenho, f.gabarito, f.plano_controle, f.plano_acao])
            dados_tabela.append({
                "ID": f.id,
                "PCP": f.pcp,
                "Cliente": f.cliente,
                "Descrição": f.descricao[:40] + "..." if len(f.descricao) > 40 else f.descricao,
                "Data": f.data_inicial,
                "📄": "✅" if tem_docs else "❌",
                "🔧": "✅" if f.manutencao else "❌"
            })
        df_tabela = pd.DataFrame(dados_tabela)
        
        for idx, row in df_tabela.iterrows():
            cols = st.columns([1, 1.2, 1.2, 3, 1.2, 0.6, 0.6, 1])
            with cols[0]: st.write(row["ID"])
            with cols[1]: st.write(row["PCP"])
            with cols[2]: st.write(row["Cliente"])
            with cols[3]: st.write(row["Descrição"])
            with cols[4]: st.write(row["Data"])
            with cols[5]: st.write(row["📄"])
            with cols[6]: st.write(row["🔧"])
            with cols[7]:
                if st.button("📊 Ver", key=f"btn_ver_{row['ID']}"):
                    resetar_navegacao()
                    st.session_state.ferramental_selecionado = row["ID"]
                    st.rerun()
            st.divider()
        
        if st.session_state.ferramental_selecionado:
            selecionado = next((f for f in ferramentais_filtrados if f.id == st.session_state.ferramental_selecionado), None)
            if selecionado:
                renderizar_detalhes_ferramental(selecionado)
                if st.button("❌ Fechar Detalhes", use_container_width=True):
                    st.session_state.ferramental_selecionado = None
                    resetar_navegacao()
                    st.rerun()
    
    else:
        if todos_ferramentais:
            st.info("📭 Nenhum ferramental encontrado com os filtros selecionados.")
    
    if st.session_state.mostrar_formulario_novo:
        st.markdown("---")
        st.markdown("### ➕ Novo Ferramental")
        
        with st.form("novo_ferramental"):
            col1, col2 = st.columns(2)
            with col1:
                novo_id = st.text_input("ID*", placeholder="Ex: FER-001")
                novo_pcp = st.text_input("PCP*", placeholder="Ex: MOLD-01")
                novo_cliente = st.text_input("Cliente*")
                novo_descricao = st.text_area("Descrição*", height=80)
                nova_data = st.text_input("Data Inicial", placeholder="DD/MM/AAAA")
            with col2:
                nova_avaliacao = st.text_input("Avaliação Inicial", placeholder="https://...")
                novo_desenho = st.text_input("Desenho", placeholder="https://...")
                novo_gabarito = st.text_input("Gabarito", placeholder="https://...")
                novo_plano_controle = st.text_input("Plano Controle", placeholder="https://...")
                novo_plano_acao = st.text_input("Plano Ação", placeholder="https://...")
                nova_manutencao = st.text_input("Manutenção", placeholder="https://drive.google.com/...")
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                submitted = st.form_submit_button("💾 SALVAR FERRAMENTAL", type="primary")
            
            if submitted:
                if not novo_id or not novo_pcp or not novo_cliente or not novo_descricao:
                    st.error("❌ Preencha todos os campos obrigatórios (*)")
                else:
                    registro = Ferramental(
                        id=novo_id, pcp=novo_pcp, cliente=novo_cliente,
                        descricao=novo_descricao, data_inicial=nova_data,
                        avaliacao_inicial=nova_avaliacao, desenho=novo_desenho,
                        gabarito=novo_gabarito, plano_controle=novo_plano_controle,
                        plano_acao=novo_plano_acao, manutencao=nova_manutencao
                    )
                    sucesso, mensagem = salvar_ferramental(registro)
                    if sucesso:
                        st.success(mensagem)
                        st.balloons()
                        st.session_state.mostrar_formulario_novo = False
                        st.rerun()
                    else:
                        st.error(mensagem)
        
        if st.button("❌ Cancelar", use_container_width=True):
            st.session_state.mostrar_formulario_novo = False
            st.rerun()
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;font-family:'JetBrains Mono',monospace;font-size:10px;color:{THEME['text_muted']};">
        🛠️ FERRAMENTARIA · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)

# ==================================================================================================
# REPASSES DE PRODUÇÃO - PEDIDOS EM ABERTO (CARTEIRA) COM CRUD DE REPASSES - VERSÃO CORRIGIDA
# ==================================================================================================
elif aba_selecionada == 'REPASSES DE PRODUÇÃO':
    render_page_header("REPASSES DE PRODUÇÃO", 
                       f"Carteira de Pedidos em Aberto · Atualizado {get_horario_brasilia()}", 
                       THEME['accent_orange'])
    
    # ======================
    # CONFIGURAÇÃO DA PLANILHA
    # ======================
    ID_PLANILHA_URGENCIAS = '1nyMCIeW5_EWkNOU5-6d_QMePq9gilvRaqvtTGekP5dk'
    ABA_CARTEIRA = 'CARTEIRA'
    ABA_REPASSE = 'REPASSE'
    
    # ======================
    # INICIALIZAR SESSION STATE
    # ======================
    if 'visao_repasses' not in st.session_state:
        st.session_state.visao_repasses = 'PEDIDOS_SISTEMA'
    
    if 'mostrar_formulario_repasse' not in st.session_state:
        st.session_state.mostrar_formulario_repasse = False
    
    if 'editando_repasse' not in st.session_state:
        st.session_state.editando_repasse = None
    
    if 'excluindo_repasse' not in st.session_state:
        st.session_state.excluindo_repasse = None
    
    if 'termo_busca_referencia' not in st.session_state:
        st.session_state.termo_busca_referencia = ""
    
    # ======================
    # DATACLASS PARA REPASSE
    # ======================
    @dataclass
    class RegistroRepasse:
        id: Optional[str] = None
        data: Optional[datetime] = None
        solicitante: str = ""
        referencia: str = ""
        cliente: str = ""
        quantidade: int = 0
        data_limite: Optional[datetime] = None
        status: str = "SOLICITADO"
    
    # ======================
    # FUNÇÕES DE CARREGAMENTO - CARTEIRA
    # ======================
    @retry_on_quota()
    @st.cache_data(ttl=600)
    def carregar_carteira_pedidos() -> pd.DataFrame:
        """Carrega os dados da aba CARTEIRA da planilha URGÊNCIAS"""
        try:
            client = get_gspread_client()
            if client is None:
                st.error("❌ Erro ao conectar ao Google Sheets")
                return pd.DataFrame()
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            
            try:
                sheet = spreadsheet.worksheet(ABA_CARTEIRA)
            except Exception as e:
                st.error(f"❌ Aba '{ABA_CARTEIRA}' não encontrada. Erro: {e}")
                return pd.DataFrame()
            
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                st.info("📭 Nenhum dado encontrado na aba CARTEIRA.")
                return pd.DataFrame()
            
            cabecalho = todos_dados[0]
            valores = todos_dados[1:]
            df = pd.DataFrame(valores, columns=cabecalho)
            df.columns = df.columns.str.strip()
            
            # Mapeamento inteligente de colunas
            mapa_colunas = {}
            for col in df.columns:
                col_upper = col.upper().strip()
                col_sem_acento = unicodedata.normalize('NFKD', col_upper).encode('ASCII', 'ignore').decode('ASCII')
                
                if col_sem_acento in ['CODIGO', 'COD', 'ID', 'CODIGO_SISTEMA']:
                    mapa_colunas[col] = 'CODIGO'
                elif col_sem_acento in ['REFERENCIA', 'REFERÊNCIA', 'REF', 'PRODUTO', 'NOME']:
                    mapa_colunas[col] = 'REFERENCIA'
                elif col_sem_acento in ['DESCRICAO', 'DESCRIÇÃO', 'DESC', 'DETALHE']:
                    mapa_colunas[col] = 'DESCRICAO'
                elif col_sem_acento in ['ESTOQUE', 'EST', 'QTD_ESTOQUE', 'SALDO']:
                    mapa_colunas[col] = 'ESTOQUE'
                elif col_sem_acento in ['PEDIDO_EM_ABERTO', 'PEDIDO', 'PED', 'QTD_PEDIDO', 'ABERTO']:
                    mapa_colunas[col] = 'PEDIDO_EM_ABERTO'
            
            if mapa_colunas:
                df = df.rename(columns=mapa_colunas)
            
            # Garantir colunas mínimas
            if 'REFERENCIA' not in df.columns and 'DESCRICAO' in df.columns:
                df['REFERENCIA'] = df['DESCRICAO']
            
            if 'PEDIDO_EM_ABERTO' not in df.columns:
                df['PEDIDO_EM_ABERTO'] = 0
            
            # Converter colunas numéricas
            colunas_numericas = ['ESTOQUE', 'PEDIDO_EM_ABERTO']
            for col in colunas_numericas:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace('.', '', regex=False)
                    df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                    df[col] = df[col].astype(str).str.replace(r'[^\d\.]', '', regex=True)
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    df[col] = df[col].astype(int)
            
            if 'CODIGO' in df.columns:
                df = df[df['CODIGO'].astype(str).str.strip() != '']
                df = df[df['CODIGO'].astype(str).str.strip() != 'nan']
            
            if 'ESTOQUE' in df.columns:
                df = df[df['ESTOQUE'] > 0]
            
            if 'CODIGO' in df.columns:
                df = df.sort_values('CODIGO', ascending=True)
            
            return df
            
        except Exception as e:
            st.error(f"❌ Erro ao carregar dados da carteira: {str(e)}")
            return pd.DataFrame()
    
    # ======================
    # FUNÇÕES DE CARREGAMENTO - REPASSES
    # ======================
    def obter_proximo_id_repasse() -> str:
        """Gera o próximo ID para repasse"""
        try:
            client = get_gspread_client()
            if client is None:
                return "REP-001"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            sheet = spreadsheet.worksheet(ABA_REPASSE)
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return "REP-001"
            
            ids = []
            for row in todos_dados[1:]:
                if row and row[0]:
                    ids.append(row[0].strip())
            
            if not ids:
                return "REP-001"
            
            numeros = []
            for id_str in ids:
                if id_str.startswith("REP-"):
                    try:
                        num = int(id_str.replace("REP-", ""))
                        numeros.append(num)
                    except:
                        pass
            
            if not numeros:
                return "REP-001"
            
            proximo = max(numeros) + 1
            return f"REP-{proximo:03d}"
            
        except:
            return "REP-001"
    
    @retry_on_quota()
    @st.cache_data(ttl=300)
    def carregar_referencias_consolidadas() -> List[str]:
        """Carrega as referências da aba CARTEIRA para o combobox"""
        try:
            client = get_gspread_client()
            if client is None:
                return []
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            sheet = spreadsheet.worksheet(ABA_CARTEIRA)
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return []
            
            cabecalho = todos_dados[0]
            idx_ref = None
            
            for i, col in enumerate(cabecalho):
                col_clean = str(col).strip().upper()
                if 'REFERENCIA' in col_clean or 'REFERÊNCIA' in col_clean or 'REF' in col_clean:
                    idx_ref = i
                    break
            
            if idx_ref is None:
                return []
            
            referencias = set()
            for row in todos_dados[1:]:
                if len(row) > idx_ref and row[idx_ref]:
                    ref = str(row[idx_ref]).strip()
                    if ref and ref.lower() != 'nan' and ref.lower() != 'none':
                        referencias.add(ref)
            
            return sorted(list(referencias))
            
        except Exception as e:
            print(f"Erro ao carregar referências: {e}")
            return []
    
    @retry_on_quota()
    @st.cache_data(ttl=300)
    def carregar_repasse() -> List[RegistroRepasse]:
        """Carrega todos os registros da aba REPASSE"""
        registros = []
        try:
            client = get_gspread_client()
            if client is None:
                return registros
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            
            try:
                sheet = spreadsheet.worksheet(ABA_REPASSE)
            except:
                sheet = spreadsheet.add_worksheet(title=ABA_REPASSE, rows=1000, cols=20)
                cabecalho = ["ID", "DATA", "SOLICITANTE", "REFERÊNCIA", "CLIENTE", "QUANTIDADE", "DATA_LIMITE", "STATUS"]
                sheet.append_row(cabecalho)
                return registros
            
            todos_dados = sheet.get_all_values()
            
            if len(todos_dados) < 2:
                return registros
            
            for idx, row in enumerate(todos_dados[1:], start=2):
                if len(row) < 8:
                    continue
                
                try:
                    registro = RegistroRepasse()
                    registro.id = row[0].strip() if row[0] else f"REP-{idx:03d}"
                    
                    if len(row) > 1 and row[1]:
                        try:
                            registro.data = datetime.strptime(row[1].strip(), "%d/%m/%Y")
                        except:
                            registro.data = converter_data_br(row[1])
                    
                    registro.solicitante = row[2].strip() if len(row) > 2 else ""
                    registro.referencia = row[3].strip() if len(row) > 3 else ""
                    registro.cliente = row[4].strip() if len(row) > 4 else ""
                    
                    if len(row) > 5 and row[5]:
                        try:
                            registro.quantidade = int(float(str(row[5]).strip().replace(',', '.')))
                        except:
                            registro.quantidade = 0
                    
                    if len(row) > 6 and row[6]:
                        try:
                            registro.data_limite = datetime.strptime(row[6].strip(), "%d/%m/%Y")
                        except:
                            registro.data_limite = converter_data_br(row[6])
                    
                    registro.status = row[7].strip() if len(row) > 7 else "SOLICITADO"
                    
                    registros.append(registro)
                except:
                    continue
            
            return registros
            
        except Exception as e:
            st.error(f"❌ Erro ao carregar repasses: {str(e)}")
            return registros
    
    # ======================
    # FUNÇÕES CRUD REPASSE
    # ======================
    def salvar_repasse(registro: RegistroRepasse) -> tuple:
        """Salva um novo repasse na planilha"""
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            sheet = spreadsheet.worksheet(ABA_REPASSE)
            
            dados = [
                registro.id,
                registro.data.strftime("%d/%m/%Y") if registro.data else "",
                registro.solicitante,
                registro.referencia,
                registro.cliente,
                str(registro.quantidade),
                registro.data_limite.strftime("%d/%m/%Y") if registro.data_limite else "",
                registro.status
            ]
            
            sheet.append_row(dados)
            st.cache_data.clear()
            return True, "✅ Repasse salvo com sucesso!"
            
        except Exception as e:
            return False, f"❌ Erro ao salvar: {str(e)}"
    
    def atualizar_repasse(registro: RegistroRepasse) -> tuple:
        """Atualiza um repasse existente"""
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            sheet = spreadsheet.worksheet(ABA_REPASSE)
            
            # Procurar a linha do registro
            cell = sheet.find(registro.id, in_column=1)
            if not cell:
                return False, f"❌ Repasse {registro.id} não encontrado"
            
            dados = [
                registro.id,
                registro.data.strftime("%d/%m/%Y") if registro.data else "",
                registro.solicitante,
                registro.referencia,
                registro.cliente,
                str(registro.quantidade),
                registro.data_limite.strftime("%d/%m/%Y") if registro.data_limite else "",
                registro.status
            ]
            
            for col, valor in enumerate(dados, start=1):
                sheet.update_cell(cell.row, col, valor)
            
            st.cache_data.clear()
            return True, "✅ Repasse atualizado com sucesso!"
            
        except Exception as e:
            return False, f"❌ Erro ao atualizar: {str(e)}"
    
    def excluir_repasse(id_repasse: str) -> tuple:
        """Exclui um repasse"""
        try:
            client = get_gspread_client()
            if client is None:
                return False, "❌ Erro ao conectar ao Google Sheets"
            
            spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
            sheet = spreadsheet.worksheet(ABA_REPASSE)
            
            cell = sheet.find(id_repasse, in_column=1)
            if not cell:
                return False, f"❌ Repasse {id_repasse} não encontrado"
            
            sheet.delete_rows(cell.row)
            st.cache_data.clear()
            return True, "✅ Repasse excluído com sucesso!"
            
        except Exception as e:
            return False, f"❌ Erro ao excluir: {str(e)}"
    
    # ======================
    # FUNÇÃO PARA GERAR GRÁFICOS
    # ======================
    def gerar_graficos_carteira(df: pd.DataFrame, visao: str = 'PEDIDOS_SISTEMA'):
        """Gera gráficos interativos com os dados da carteira"""
        
        if df.empty:
            st.info("📭 Sem dados para gerar gráficos.")
            return
        
        colunas_necessarias = ['REFERENCIA', 'ESTOQUE']
        if visao == 'PEDIDOS_SISTEMA':
            colunas_necessarias.append('PEDIDO_EM_ABERTO')
        
        colunas_faltando = [col for col in colunas_necessarias if col not in df.columns]
        
        if colunas_faltando:
            st.warning(f"⚠️ Colunas necessárias não encontradas: {', '.join(colunas_faltando)}")
            return
        
        df = df.copy()
        df['ESTOQUE'] = pd.to_numeric(df['ESTOQUE'], errors='coerce').fillna(0)
        df['REFERENCIA'] = df['REFERENCIA'].astype(str).fillna('Sem Referência')
        
        if visao == 'PEDIDOS_SISTEMA':
            df['PEDIDO_EM_ABERTO'] = pd.to_numeric(df['PEDIDO_EM_ABERTO'], errors='coerce').fillna(0)
            coluna_valor = 'PEDIDO_EM_ABERTO'
            titulo = 'Pedidos em Aberto no Sistema'
            cor = '#E86C2C'
            label = 'Pedido Sistema'
        else:
            coluna_valor = 'ESTOQUE'
            titulo = 'Estoque Atual'
            cor = '#0078D4'
            label = 'Estoque'
        
        df_com_valor = df[df[coluna_valor] > 0].copy()
        
        if df_com_valor.empty:
            st.info(f"📭 Nenhum dado com {label} > 0 para gerar gráficos.")
            return
        
        # Gráfico Top 10
        st.markdown("---")
        st.markdown(f"### 📊 Top 10 {titulo}")
        
        top10 = df_com_valor.nlargest(10, coluna_valor).copy()
        
        if not top10.empty and len(top10) > 0:
            try:
                top10['REFERENCIA'] = top10['REFERENCIA'].astype(str)
                top10[coluna_valor] = top10[coluna_valor].astype(float)
                
                fig = px.bar(
                    top10,
                    x='REFERENCIA',
                    y=coluna_valor,
                    color=coluna_valor,
                    color_continuous_scale='Oranges' if visao == 'PEDIDOS_SISTEMA' else 'Blues',
                    title=f'Top 10 Referências com Maior {titulo}',
                    labels={'REFERENCIA': 'Referência', coluna_valor: label},
                    text=coluna_valor
                )
                
                fig.update_layout(
                    height=400,
                    xaxis_tickangle=-45,
                    font=dict(size=12),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    coloraxis_showscale=False,
                    margin=dict(l=20, r=20, t=40, b=80)
                )
                
                fig.update_traces(
                    textposition='outside',
                    textfont=dict(size=11, color='#333'),
                    texttemplate='%{text:,.0f}',
                    marker_color=cor
                )
                
                st.plotly_chart(fig, use_container_width=True, key=f"grafico_top10_{visao}")
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível gerar o gráfico Top 10: {str(e)}")
        
        # Gráfico de distribuição
        st.markdown("### 📊 Distribuição dos Valores")
        
        def classificar_valor(row):
            valor = row.get(coluna_valor, 0)
            if valor == 0:
                return '✅ Sem Valor'
            elif valor <= 10:
                return '🟢 Baixo (1-10)'
            elif valor <= 50:
                return '🟡 Médio (11-50)'
            elif valor <= 100:
                return '🟠 Alto (51-100)'
            else:
                return '🔴 Muito Alto (>100)'
        
        df_status = df.copy()
        df_status['STATUS'] = df_status.apply(classificar_valor, axis=1)
        status_counts = df_status['STATUS'].value_counts()
        
        cores = {
            '✅ Sem Valor': '#28a745',
            '🟢 Baixo (1-10)': '#0078D4',
            '🟡 Médio (11-50)': '#FFB900',
            '🟠 Alto (51-100)': '#FF6B35',
            '🔴 Muito Alto (>100)': '#E81123'
        }
        
        if not status_counts.empty:
            try:
                status_counts = status_counts[status_counts > 0]
                
                if not status_counts.empty:
                    fig = px.pie(
                        status_counts,
                        values=status_counts.values,
                        names=status_counts.index,
                        title=f'Distribuição dos {label}s',
                        color=status_counts.index,
                        color_discrete_map=cores,
                        hole=0.4
                    )
                    
                    fig.update_layout(
                        height=380,
                        font=dict(size=12),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        legend=dict(
                            orientation='v',
                            yanchor='middle',
                            y=0.5,
                            xanchor='left',
                            x=1.1
                        ),
                        margin=dict(l=20, r=120, t=40, b=20)
                    )
                    
                    fig.update_traces(
                        textposition='inside',
                        textinfo='percent+label',
                        textfont=dict(size=11, color='white'),
                        hovertemplate='<b>%{label}</b><br>Quantidade: %{value}<br>Percentual: %{percent}<extra></extra>'
                    )
                    
                    st.plotly_chart(fig, use_container_width=True, key=f"grafico_pizza_{visao}")
                    
            except Exception as e:
                st.warning(f"⚠️ Não foi possível gerar o gráfico de pizza: {str(e)}")
    
    # ======================
    # FUNÇÃO PARA RENDERIZAR CRUD DE REPASSES (CORRIGIDA)
    # ======================
    def renderizar_crud_repasse():
        """Renderiza o CRUD completo da aba REPASSE"""
        
        st.markdown("---")
        st.markdown("### 📋 Gerenciamento de Repasses")
        
        # Botão Novo Repasse
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("➕ NOVO REPASSE", type="primary", use_container_width=True):
                st.session_state.mostrar_formulario_repasse = True
                st.session_state.editando_repasse = None
                st.rerun()
        
        # ===== FORMULÁRIO NOVO/EDITAR =====
        if st.session_state.mostrar_formulario_repasse:
            st.markdown("---")
            st.markdown("### ✏️ " + ("Editar Repasse" if st.session_state.editando_repasse else "Novo Repasse"))
            
            referencias_disponiveis = carregar_referencias_consolidadas()
            
            if st.session_state.editando_repasse:
                registro_edit = st.session_state.editando_repasse
                id_edit = registro_edit.id
                data_edit = registro_edit.data
                solicitante_edit = registro_edit.solicitante
                referencia_edit = registro_edit.referencia
                cliente_edit = registro_edit.cliente
                quantidade_edit = registro_edit.quantidade
                data_limite_edit = registro_edit.data_limite
                status_edit = registro_edit.status
            else:
                id_edit = obter_proximo_id_repasse()
                data_edit = datetime.now()
                solicitante_edit = ""
                referencia_edit = ""
                cliente_edit = ""
                quantidade_edit = 0
                data_limite_edit = None
                status_edit = "SOLICITADO"
            
            st.info(f"📌 ID: {id_edit}")
            
            with st.form("form_repasse"):
                col1, col2 = st.columns(2)
                
                with col1:
                    data_form = st.date_input(
                        "📅 Data",
                        value=data_edit if data_edit else datetime.now(),
                        key="data_repasse"
                    )
                    
                    solicitante_form = st.text_input(
                        "👤 Solicitante",
                        value=solicitante_edit,
                        key="solicitante_repasse"
                    )
                    
                    st.markdown("**🔍 Referência***")
                    
                    termo_busca = st.text_input(
                        "Pesquisar referência",
                        value=st.session_state.termo_busca_referencia,
                        placeholder="Digite para filtrar...",
                        key="busca_referencia_repasse",
                        label_visibility="collapsed"
                    )
                    st.session_state.termo_busca_referencia = termo_busca
                    
                    if termo_busca:
                        termo_lower = termo_busca.lower()
                        opcoes_filtradas = [r for r in referencias_disponiveis if termo_lower in r.lower()]
                    else:
                        opcoes_filtradas = referencias_disponiveis
                    
                    if opcoes_filtradas:
                        if referencia_edit and referencia_edit in opcoes_filtradas:
                            idx_default = opcoes_filtradas.index(referencia_edit)
                        else:
                            idx_default = 0
                        
                        referencia_form = st.selectbox(
                            "Selecione a referência",
                            options=opcoes_filtradas,
                            index=idx_default if referencia_edit and referencia_edit in opcoes_filtradas else 0,
                            key="referencia_repasse_select",
                            label_visibility="collapsed"
                        )
                    else:
                        referencia_form = st.text_input(
                            "Referência (digite manualmente)",
                            value=referencia_edit,
                            key="referencia_repasse_manual",
                            label_visibility="collapsed"
                        )
                    
                    cliente_form = st.text_input(
                        "🏢 Cliente",
                        value=cliente_edit,
                        key="cliente_repasse"
                    )
                
                with col2:
                    quantidade_form = st.number_input(
                        "📦 Quantidade",
                        min_value=0,
                        value=quantidade_edit,
                        step=1,
                        key="quantidade_repasse"
                    )
                    
                    data_limite_form = st.date_input(
                        "⏰ Data Limite",
                        value=data_limite_edit if data_limite_edit else datetime.now() + timedelta(days=7),
                        key="data_limite_repasse"
                    )
                    
                    status_form = st.selectbox(
                        "📊 Status",
                        options=["SOLICITADO", "PROGRAMADO", "PRODUZIDO"],
                        index=["SOLICITADO", "PROGRAMADO", "PRODUZIDO"].index(status_edit) if status_edit in ["SOLICITADO", "PROGRAMADO", "PRODUZIDO"] else 0,
                        key="status_repasse"
                    )
                    
                    if status_form == "SOLICITADO":
                        st.info("🟡 Aguardando programação")
                    elif status_form == "PROGRAMADO":
                        st.info("🟢 Programado para produção")
                    else:
                        st.success("✅ Produzido / Finalizado")
                
                st.markdown("---")
                col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                with col_btn2:
                    submitted = st.form_submit_button(
                        "💾 SALVAR REPASSE",
                        type="primary",
                        use_container_width=True
                    )
                
                if submitted:
                    if not referencia_form or not referencia_form.strip():
                        st.error("❌ A referência é obrigatória!")
                    elif quantidade_form <= 0:
                        st.error("❌ A quantidade deve ser maior que zero!")
                    else:
                        novo_registro = RegistroRepasse(
                            id=id_edit,
                            data=datetime.combine(data_form, datetime.min.time()),
                            solicitante=solicitante_form,
                            referencia=referencia_form.strip(),
                            cliente=cliente_form,
                            quantidade=quantidade_form,
                            data_limite=datetime.combine(data_limite_form, datetime.min.time()),
                            status=status_form
                        )
                        
                        if st.session_state.editando_repasse:
                            sucesso, msg = atualizar_repasse(novo_registro)
                        else:
                            sucesso, msg = salvar_repasse(novo_registro)
                        
                        if sucesso:
                            st.success(msg)
                            st.balloons()
                            st.session_state.mostrar_formulario_repasse = False
                            st.session_state.editando_repasse = None
                            st.session_state.termo_busca_referencia = ""
                            st.rerun()
                        else:
                            st.error(msg)
            
            if st.button("❌ Cancelar", use_container_width=True):
                st.session_state.mostrar_formulario_repasse = False
                st.session_state.editando_repasse = None
                st.session_state.termo_busca_referencia = ""
                st.rerun()
        
        # ===== LISTA DE REPASSES =====
        st.markdown("---")
        st.markdown("### 📋 Lista de Repasses")
        
        with st.spinner("Carregando repasses..."):
            repasses = carregar_repasse()
        
        if not repasses:
            st.info("📭 Nenhum repasse cadastrado.")
            return
        
        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_status = st.selectbox(
                "Filtrar por Status",
                ["(Todos)", "SOLICITADO", "PROGRAMADO", "PRODUZIDO"],
                key="filtro_status_repasse"
            )
        with col_f2:
            filtro_referencia_lista = st.text_input(
                "Filtrar por Referência",
                placeholder="Digite parte da referência...",
                key="filtro_ref_repasse"
            )
        with col_f3:
            filtro_solicitante = st.text_input(
                "Filtrar por Solicitante",
                placeholder="Digite o nome...",
                key="filtro_solicitante_repasse"
            )
        
        # Aplicar filtros
        repasses_filtrados = repasses.copy()
        if filtro_status != "(Todos)":
            repasses_filtrados = [r for r in repasses_filtrados if r.status == filtro_status]
        if filtro_referencia_lista:
            repasses_filtrados = [r for r in repasses_filtrados if filtro_referencia_lista.lower() in r.referencia.lower()]
        if filtro_solicitante:
            repasses_filtrados = [r for r in repasses_filtrados if filtro_solicitante.lower() in r.solicitante.lower()]
        
        # CARDS
        total_repasses = len(repasses_filtrados)
        total_solicitado = sum(r.quantidade for r in repasses_filtrados if r.status == "SOLICITADO")
        total_programado = sum(r.quantidade for r in repasses_filtrados if r.status == "PROGRAMADO")
        total_produzido = sum(r.quantidade for r in repasses_filtrados if r.status == "PRODUZIDO")
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1:
            st.metric("📋 Total de Repasses", f"{total_repasses:,}")
        with col_c2:
            st.metric("🟡 Solicitado", f"{total_solicitado:,}")
        with col_c3:
            st.metric("🟢 Programado", f"{total_programado:,}")
        with col_c4:
            st.metric("✅ Produzido", f"{total_produzido:,}")
        
        st.markdown("---")
        
        # ===== TABELA DE REPASSES - CORRIGIDA =====
        if repasses_filtrados:
            dados_tabela = []
            for r in repasses_filtrados:
                status_icons = {
                    "SOLICITADO": "🟡",
                    "PROGRAMADO": "🟢",
                    "PRODUZIDO": "✅"
                }
                
                dados_tabela.append({
                    "ID": r.id,
                    "Data": r.data.strftime("%d/%m/%Y") if r.data else "-",
                    "Solicitante": r.solicitante,
                    "Referência": r.referencia,
                    "Cliente": r.cliente,
                    "Quantidade": f"{r.quantidade:,}".replace(",", "."),
                    "Data Limite": r.data_limite.strftime("%d/%m/%Y") if r.data_limite else "-",
                    "Status": f"{status_icons.get(r.status, '📌')} {r.status}",
                    "_status_raw": r.status
                })
            
            df_repasses = pd.DataFrame(dados_tabela)
            
            # Aplicar estilo SEM remover a coluna _status_raw
            def estilo_status(row):
                # Acessar a coluna _status_raw que ainda está no DataFrame
                status = row['_status_raw']
                if status == "PRODUZIDO":
                    return ['background-color: #d4edda; color: #155724; font-weight: bold;'] * len(row)
                elif status == "PROGRAMADO":
                    return ['background-color: #fff3cd; color: #856404;'] * len(row)
                else:
                    return ['background-color: #f8d7da; color: #721c24;'] * len(row)
            
            # Aplicar estilo mantendo a coluna _status_raw
            styled_df = df_repasses.style.apply(estilo_status, axis=1)
            
            # Exibir a tabela com todas as colunas
            st.dataframe(styled_df, use_container_width=True, height=400, hide_index=True)
            
            # ===== AÇÕES =====
            st.markdown("---")
            st.markdown("### 🔧 Ações")
            
            opcoes_ids = [f"{r.id} - {r.referencia}" for r in repasses_filtrados]
            if opcoes_ids:
                selecao = st.selectbox(
                    "Selecione um repasse para editar ou excluir:",
                    options=opcoes_ids,
                    key="select_repasse_acao"
                )
                
                if selecao:
                    id_selecionado = selecao.split(" - ")[0]
                    registro_selecionado = next((r for r in repasses_filtrados if r.id == id_selecionado), None)
                    
                    if registro_selecionado:
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("✏️ Editar", use_container_width=True):
                                st.session_state.editando_repasse = registro_selecionado
                                st.session_state.mostrar_formulario_repasse = True
                                st.session_state.termo_busca_referencia = registro_selecionado.referencia
                                st.rerun()
                        
                        with col_btn2:
                            if st.button("🗑️ Excluir", use_container_width=True):
                                if st.session_state.excluindo_repasse == id_selecionado:
                                    if st.button("⚠️ CONFIRMAR EXCLUSÃO", type="primary", use_container_width=True):
                                        sucesso, msg = excluir_repasse(id_selecionado)
                                        if sucesso:
                                            st.success(msg)
                                            st.session_state.excluindo_repasse = None
                                            st.rerun()
                                        else:
                                            st.error(msg)
                                else:
                                    st.session_state.excluindo_repasse = id_selecionado
                                    st.warning(f"⚠️ Clique novamente em 'Excluir' para confirmar")
                                    st.rerun()
        else:
            st.info("📭 Nenhum repasse encontrado com os filtros selecionados.")
    
    # ======================
    # CARREGAR DADOS DA CARTEIRA
    # ======================
    with st.spinner("🔄 Carregando dados da carteira de pedidos..."):
        df_carteira = carregar_carteira_pedidos()
    
    # ======================
    # BOTÕES DE NAVEGAÇÃO
    # ======================
    st.markdown("### 📊 Selecione a Visualização")
    
    col_b1, col_b2, col_b3 = st.columns(3)
    
    with col_b1:
        if st.button(
            "📋 Pedidos Sistema", 
            use_container_width=True,
            type="primary" if st.session_state.visao_repasses == 'PEDIDOS_SISTEMA' else "secondary"
        ):
            st.session_state.visao_repasses = 'PEDIDOS_SISTEMA'
            st.rerun()
    
    with col_b2:
        if st.button(
            "🔄 Repasses", 
            use_container_width=True,
            type="primary" if st.session_state.visao_repasses == 'REPASSES' else "secondary"
        ):
            st.session_state.visao_repasses = 'REPASSES'
            st.rerun()
    
    with col_b3:
        if st.button(
            "📦 Estoque Atual", 
            use_container_width=True,
            type="primary" if st.session_state.visao_repasses == 'ESTOQUE_ATUAL' else "secondary"
        ):
            st.session_state.visao_repasses = 'ESTOQUE_ATUAL'
            st.rerun()
    
    st.markdown("---")
    
    # ======================
    # RENDERIZAR CONTEÚDO
    # ======================
    if st.session_state.visao_repasses == 'REPASSES':
        renderizar_crud_repasse()
    else:
        # ===== PEDIDOS_SISTEMA e ESTOQUE_ATUAL =====
        st.markdown("### 🔍 Filtros")
        
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            if not df_carteira.empty and 'REFERENCIA' in df_carteira.columns:
                opcoes_ref = ["(Todas)"] + sorted(df_carteira['REFERENCIA'].dropna().unique().tolist())
                filtro_referencia = st.selectbox(
                    "🔎 Referência",
                    options=opcoes_ref,
                    key="filtro_ref_repasses"
                )
            else:
                filtro_referencia = "(Todas)"
        
        with col_f2:
            if not df_carteira.empty and 'CODIGO' in df_carteira.columns:
                opcoes_codigo = ["(Todos)"] + sorted(df_carteira['CODIGO'].dropna().unique().tolist())
                filtro_codigo = st.selectbox(
                    "📋 Código Sistema",
                    options=opcoes_codigo,
                    key="filtro_codigo_repasses"
                )
            else:
                filtro_codigo = "(Todos)"
        
        df_filtrado = df_carteira.copy()
        
        if not df_filtrado.empty:
            if filtro_referencia != "(Todas)":
                df_filtrado = df_filtrado[df_filtrado['REFERENCIA'] == filtro_referencia]
            if filtro_codigo != "(Todos)":
                df_filtrado = df_filtrado[df_filtrado['CODIGO'] == filtro_codigo]
        
        if st.session_state.visao_repasses == 'PEDIDOS_SISTEMA':
            coluna_valor = 'PEDIDO_EM_ABERTO'
            label_valor = 'Pedido Sistema'
            icone_valor = '📋'
            titulo_tabela = 'PEDIDOS EM ABERTO NO SISTEMA LUVIDARTE'
        else:
            coluna_valor = 'ESTOQUE'
            label_valor = 'Estoque Atual'
            icone_valor = '📦'
            titulo_tabela = 'ESTOQUE ATUAL'
        
        total_valor = 0
        total_estoque = 0
        total_itens = 0
        itens_criticos = 0
        
        if not df_filtrado.empty:
            if coluna_valor in df_filtrado.columns:
                total_valor = int(df_filtrado[coluna_valor].sum())
            total_estoque = int(df_filtrado['ESTOQUE'].sum()) if 'ESTOQUE' in df_filtrado.columns else 0
            total_itens = len(df_filtrado)
            
            if coluna_valor in df_filtrado.columns and 'ESTOQUE' in df_filtrado.columns:
                itens_criticos = len(df_filtrado[df_filtrado[coluna_valor] > df_filtrado['ESTOQUE']])
        
        st.markdown("---")
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            st.metric(f"{icone_valor} Total {label_valor}", f"{total_valor:,.0f}".replace(",", "."))
        with col_k2:
            st.metric("📦 Estoque Total", f"{total_estoque:,.0f}".replace(",", "."))
        with col_k3:
            st.metric("📋 Itens na Carteira", f"{total_itens:,}".replace(",", "."))
        with col_k4:
            cor_critico = "🔴" if itens_criticos > 0 else "🟢"
            st.metric(f"{cor_critico} Itens Críticos", f"{itens_criticos:,}".replace(",", "."))
        
        st.markdown("---")
        st.markdown(f"### 📋 {titulo_tabela}")
        
        if df_filtrado.empty:
            st.info("📭 Nenhum dado encontrado com os filtros selecionados.")
        else:
            df_exibicao = df_filtrado.copy()
            
            if 'REFERENCIA' not in df_exibicao.columns and 'DESCRICAO' in df_exibicao.columns:
                df_exibicao['REFERENCIA'] = df_exibicao['DESCRICAO']
            
            mapa_exibicao = {
                'CODIGO': 'CÓDIGO SISTEMA',
                'REFERENCIA': 'REFERÊNCIA',
                'DESCRICAO': 'DESCRIÇÃO',
                'ESTOQUE': 'ESTOQUE ATUAL',
                'PEDIDO_EM_ABERTO': 'PEDIDO SISTEMA'
            }
            df_exibicao = df_exibicao.rename(columns=mapa_exibicao)
            
            if st.session_state.visao_repasses == 'PEDIDOS_SISTEMA':
                colunas_ordem = ['CÓDIGO SISTEMA', 'REFERÊNCIA', 'DESCRIÇÃO', 'ESTOQUE ATUAL', 'PEDIDO SISTEMA']
            else:
                colunas_ordem = ['CÓDIGO SISTEMA', 'REFERÊNCIA', 'DESCRIÇÃO', 'ESTOQUE ATUAL']
            
            colunas_existentes = [col for col in colunas_ordem if col in df_exibicao.columns]
            df_exibicao = df_exibicao[colunas_existentes]
            
            def definir_status(row):
                if coluna_valor == 'ESTOQUE':
                    estoque = row.get('ESTOQUE ATUAL', 0)
                    if estoque == 0:
                        return '🔴 ZERADO'
                    elif estoque <= 10:
                        return '🟡 BAIXO'
                    elif estoque <= 50:
                        return '🟢 NORMAL'
                    else:
                        return '🟣 ALTO'
                else:
                    valor = row.get('PEDIDO SISTEMA', 0) if 'PEDIDO SISTEMA' in row else 0
                    estoque = row.get('ESTOQUE ATUAL', 0)
                    if valor == 0:
                        return '✅ ZERADO'
                    elif estoque >= valor:
                        return '🟢 SUFICIENTE'
                    elif estoque >= valor * 0.5:
                        return '🟡 PARCIAL'
                    else:
                        return '🔴 CRÍTICO'
            
            df_exibicao['STATUS'] = df_exibicao.apply(definir_status, axis=1)
            
            colunas_formatar = ['ESTOQUE ATUAL']
            if 'PEDIDO SISTEMA' in df_exibicao.columns:
                colunas_formatar.append('PEDIDO SISTEMA')
            
            for col in colunas_formatar:
                if col in df_exibicao.columns:
                    df_exibicao[col] = df_exibicao[col].apply(lambda x: f"{int(x):,}".replace(",", "."))
            
            def estilo_tabela(row):
                status = row['STATUS']
                if '🔴' in status:
                    return ['background-color: #f8d7da; color: #721c24; font-weight: bold;'] * len(row)
                elif '🟡' in status:
                    return ['background-color: #fff3cd; color: #856404;'] * len(row)
                elif '🟢' in status:
                    return ['background-color: #d4edda; color: #155724;'] * len(row)
                elif '🟣' in status:
                    return ['background-color: #e8d4f8; color: #4a1a6b;'] * len(row)
                else:
                    return [''] * len(row)
            
            styled_df = df_exibicao.style.apply(estilo_tabela, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=500, hide_index=True)
            
            with st.expander("📊 Ver Gráficos Analíticos", expanded=False):
                gerar_graficos_carteira(df_filtrado, st.session_state.visao_repasses)
    
    # ======================
    # INFORMAÇÕES ADICIONAIS
    # ======================
    with st.expander("ℹ️ Sobre a Carteira de Pedidos", expanded=False):
        st.markdown("""
        **📊 O que é esta carteira?**
        
        Esta seção exibe os dados da carteira de pedidos no sistema Luvidarte.
        
        **📋 Visões disponíveis:**
        - **Pedidos Sistema**: Mostra os pedidos em aberto no sistema ERP
        - **Repasses**: CRUD completo para gerenciar repasses de produção
        - **Estoque Atual**: Mostra o estoque disponível
        
        **🎯 Classificação por Status:**
        - 🟢 **Suficiente**: Estoque >= Pedido
        - 🟡 **Parcial**: Estoque >= Pedido/2 e < Pedido
        - 🔴 **Crítico**: Estoque < Pedido/2
        
        **🔄 Atualização:** Os dados são carregados automaticamente a cada 10 minutos.
        """)
    
    st.markdown(f"""
    <div style="text-align:right;padding:16px 0 8px;
        font-family:'JetBrains Mono',monospace;font-size:10px;
        color:{THEME['text_muted']};letter-spacing:.1em;">
        REPASSES DE PRODUÇÃO · {get_horario_brasilia()}
    </div>
    """, unsafe_allow_html=True)  
    
# ==================================================================================================
# RENDERIZAR FAIXA DE ROLAGEM
# ==================================================================================================
if 'ID_PLANILHA_FECHAMENTO' not in dir():
    ID_PLANILHA_FECHAMENTO = '1_HkKTRCSg24wDJ47v5wSd-UPBkbalLd6plV9IvlTY64'

renderizar_faixa_rolagem()
