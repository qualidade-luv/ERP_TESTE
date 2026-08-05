# ==================================================================================================
# PARTE 1/5 - CONFIGURAÇÕES, IMPORTAÇÕES, TEMA E FUNÇÕES AUXILIARES
# ==================================================================================================

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, date, time as dt_time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import os
import numpy as np
import io
import unicodedata
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import traceback
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import time
import json
from functools import wraps
import plotly.express as px
import plotly.graph_objects as go
import hashlib
from datetime import timezone

# ==================================================================================================
# 1. CONFIGURAÇÕES DE SEGURANÇA E CONSTANTES
# ==================================================================================================

SESSAO_EXPIRACAO_MINUTOS = 10
TENTATIVAS_LOGIN_MAX = 5
BLOQUEIO_LOGIN_MINUTOS = 15

# ==================================================================================================
# 2. CONFIGURAÇÕES DAS PLANILHAS (IDs atualizados para produção)
# ==================================================================================================

ID_PLANILHA_PRENSADOS_SOPRO = '1Hjy4UGtgwIPJgqmcv46LyXNWOrYk_oeJWWV5vlfKF2k'
ID_PLANILHA_TEMPERA = '1GJegUHosaQLEJVMCH6QVuKjSjuaxrWkgzNEr9vM5Yio'
ID_PLANILHA_AR = '12pz6EE1KDo41szDyGEyTyK27mAOb9F1FyU77_M1kL0o'
ID_PLANILHA_RECADOS = '1R0V4HpmRNXAd2TxVv8c_dVVoc1tXDPBOVSFBX1JKHvs'
ID_PLANILHA_BIBLIOTECA = '1YbtwIajV3WpQB-fz3CqaZ69UNDPgcYyzjJw5Pyy1JGU'
ID_PLANILHA_PREVENTIVA = '1FOh8OT5NaqPV3OWZziQLlclwJdSnIdd7qkS1KbbUS40'
ID_PLANILHA_HABILIDADES = '1Kldu2rJKlGDWSAvztvgLUyZ0DwcifOlbWvekj6xhkl4'
ID_PLANILHA_FERRAMENTARIA = '12xXYNhrGWP4PMvcdLSMFaMIM-CcLPYyvfBGD0I7Gibg'
ID_PLANILHA_URGENCIAS = '1nyMCIeW5_EWkNOU5-6d_QMePq9gilvRaqvtTGekP5dk'
ID_PLANILHA_ENFORNADEIRA = '1Gfaf_J5OA0nHLMR2nPUPnEmIltfOoXA7j_7ARoD_U8Q'
ID_PLANILHA_FALTAS = '1D4Wqixy60ZW5WPqO026rc1PTHjlVboq9ka0I3VktzDs'
ID_PLANILHA_LOGIN = '1_54o1YFfG8GxqBJQ2stwWNpeQptJQHUc4SSzT4gV1QM'

ABA_AR = 'AR'
ABA_RM = 'RM'
ABA_RECADOS = 'Rodapé'
ABA_BIBLIOTECA = 'BIBLIOTECA'
ABA_PREVENTIVA = 'PREVENTIVA'
ABA_CADASTRO_PREVENTIVA = 'CADASTRO'
ABA_HABILIDADES = 'HABILIDADES'
ABA_FERRAMENTARIA = 'MOLDES'
ABA_CARTEIRA = 'CARTEIRA'
ABA_REPASSE = 'REPASSE'
ABA_ENFORNADEIRA = 'ENFORNADEIRA'
ABA_LOGIN = 'LOGIN'

PRACAS_NAO_SOPRO = ['GIL', 'GILSIMAR', 'ED CARLOS', 'EDI CARLOS', 'ROBÔ 2', 'ROBÔ-2', 'ROBÔ', 'ROBO']

ABAS = {
    'PRENSADOS': 'TRS_INDUSTRIAL',
    'SOPRO': 'TRS_SOPRO',
    'TÊMPERA': 'TRS_TEMPERA',
    'AVISO DE REJEIÇÃO': 'AR',
    'REQUISIÇÃO MANUTENÇÃO': 'RM',
    'FECHAMENTO TURNO': 'FT',
    'MANUTENÇÃO PREVENTIVA': 'MP',
    'MAPEAMENTO DE HABILIDADES': 'MH',
    'FERRAMENTARIA': 'FM',
    'PRÊMIO PRENSADOS': 'PP',
    'REPASSES DE PRODUÇÃO': 'RP',
    'CONTROLE DO FORNO': 'CF'
}

OPCOES_DECISAO_AR = ["APROVADO CONDICIONAL", "REPROVADO", "EM ANÁLISE", "NÃO RESPONDIDO"]
OPCOES_STATUS_AR = ["ABERTO", "FINALIZADO", "NÃO RESPONDIDA"]
OPCOES_TURNO_AR = ["Manhã", "Tarde", "Noite"]

OPCOES_CARATER_RM = ["1 - Risco Físico/Segurança", "2 - Impacto Imediato na Produção", 
                     "3 - Impacto a Longo Prazo", "4 - Melhoria/Preventiva"]
OPCOES_SETORES_RM = ["Produção", "Corte", "Vidraria", "Rodaria", "Embalagem", "Expedição", 
                     "Qualidade", "Ferramentaria", "Manutenção", "Outros"]
OPCOES_SETORES2_RM = ["Elétrica", "Mecânica", "Informática", "Ferramentaria", "Manutenção Geral"]
OPCOES_STATUS_RM = ["ABERTO", "EM ANDAMENTO", "FINALIZADO", "CANCELADO"]

OPCOES_SETORES_PREVENTIVA = [
    "Produção", "Corte", "Vidraria", "Rodaria", "Embalagem", "Expedição", 
    "Qualidade", "Ferramentaria", "Manutenção", "Pintura", "Quimica", 
    "Escritório", "RH", "Portaria", "Loja", "Furação", "Fosco", 
    "Têmpera", "Area Externa", "Patio", "Outros"
]

# ==================================================================================================
# 3. TEMA VISUAL (LIGHT MODE)
# ==================================================================================================

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

# ==================================================================================================
# 4. FUNÇÕES DE HASH E AUTENTICAÇÃO (CORRIGIDAS)
# ==================================================================================================

def hash_senha(senha: str) -> str:
    """Cria um hash SHA-256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

# ==================================================================================================
# SUBSTITUA A FUNÇÃO EXISTENTE POR ESTA VERSÃO HÍBRIDA
# ==================================================================================================

def verificar_login(user: str, senha: str) -> tuple:
    """
    Verifica as credenciais na planilha LOGIN.
    Compatível com senhas em texto puro OU com hash.
    """
    try:
        client = get_gspread_client()
        if client is None:
            return False, None, None, None, "❌ Erro de conexão com o banco de dados"
        
        spreadsheet = client.open_by_key(ID_PLANILHA_LOGIN)
        sheet = spreadsheet.worksheet(ABA_LOGIN)
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return False, None, None, None, "❌ Nenhum usuário cadastrado"
        
        for row in todos_dados[1:]:
            if len(row) < 6:
                continue
                
            usuario = row[1].strip()
            senha_armazenada = row[2].strip()
            nivel = row[3].strip()
            setor = row[4].strip()
            status = row[5].strip().upper()
            
            if usuario.lower() == user.lower():
                if status != "ATIVO":
                    return False, None, None, None, f"❌ Usuário bloqueado. Status: {status}"
                
                # ===== VERIFICAÇÃO HÍBRIDA =====
                # 1. Tentar como texto puro (senhas antigas)
                if senha == senha_armazenada:
                    return True, nivel, setor, status, "✅ Login realizado com sucesso!"
                
                # 2. Tentar como hash (senhas migradas)
                if len(senha_armazenada) == 64 and all(c in '0123456789abcdef' for c in senha_armazenada):
                    if hash_senha(senha) == senha_armazenada:
                        return True, nivel, setor, status, "✅ Login realizado com sucesso!"
                
                return False, None, None, None, "❌ Senha incorreta!"
        
        return False, None, None, None, "❌ Usuário não encontrado!"
        
    except Exception as e:
        return False, None, None, None, f"❌ Erro ao verificar login: {str(e)}"

def inicializar_sessao():
    """Inicializa a sessão do usuário"""
    st.session_state.logado = True
    st.session_state.usuario = st.session_state.user_input
    st.session_state.nivel = st.session_state.nivel_usuario
    st.session_state.setor = st.session_state.setor_usuario
    st.session_state.tempo_login = datetime.now()
    st.session_state.ultima_atividade = datetime.now()
    st.session_state.tentativas_login = 0

def verificar_expiracao_sessao():
    """Verifica se a sessão expirou"""
    if 'logado' not in st.session_state or not st.session_state.logado:
        return True
    if 'ultima_atividade' not in st.session_state:
        return True
    
    tempo_decorrido = (datetime.now() - st.session_state.ultima_atividade).total_seconds()
    tempo_limite = SESSAO_EXPIRACAO_MINUTOS * 60
    
    if tempo_decorrido > tempo_limite:
        st.session_state.logado = False
        st.session_state.mensagem_logout = "⏰ Sessão expirada! Faça login novamente."
        return True
    return False

def atualizar_atividade():
    """Atualiza o timestamp da última atividade"""
    if 'logado' in st.session_state and st.session_state.logado:
        st.session_state.ultima_atividade = datetime.now()

def fazer_logout():
    """Realiza o logout do usuário"""
    st.session_state.logado = False
    st.session_state.mensagem_logout = "👋 Logout realizado com sucesso!"
    if 'user_input' in st.session_state:
        st.session_state.user_input = ""
    if 'password_input' in st.session_state:
        st.session_state.password_input = ""
    st.cache_data.clear()
    st.rerun()

def verificar_acesso():
    """
    Verifica se o usuário está logado e se a sessão é válida.
    Retorna True se tudo ok, False se precisa fazer login.
    """
    if 'logado' not in st.session_state:
        st.session_state.logado = False
    
    if not st.session_state.logado:
        renderizar_tela_login()
        return False
    
    if st.session_state.get('nivel', '0') != '0':
        if verificar_expiracao_sessao():
            renderizar_tela_login()
            return False
    
    atualizar_atividade()
    return True

def verificar_acesso_modulo(nivel_requerido: int = 0):
    """Verifica se o usuário tem permissão para acessar um módulo específico"""
    try:
        nivel_usuario = int(st.session_state.get('nivel', '5'))
        if nivel_usuario > nivel_requerido:
            st.error("⛔ Acesso Negado. Você não tem permissão para acessar este módulo.")
            st.stop()
    except:
        st.error("⛔ Erro ao verificar permissões.")
        st.stop()

# ==================================================================================================
# 5. FUNÇÕES DE HORÁRIO
# ==================================================================================================

def get_horario_brasilia():
    """Retorna o horário de Brasília formatado"""
    utc_now = datetime.now(timezone.utc)
    brasilia_offset = timezone(timedelta(hours=-3))
    agora_brasilia = utc_now.astimezone(brasilia_offset)
    return agora_brasilia.strftime('%d/%m/%Y %H:%M')

def get_horario_brasilia_obj():
    """Retorna o objeto datetime do horário de Brasília"""
    utc_now = datetime.now(timezone.utc)
    brasilia_offset = timezone(timedelta(hours=-3))
    return utc_now.astimezone(brasilia_offset)

# ==================================================================================================
# 6. FUNÇÕES DE CONEXÃO COM GOOGLE SHEETS
# ==================================================================================================

@st.cache_resource
def get_gspread_client():
    """Retorna cliente autenticado do gspread (cacheado) - SEM CAMINHOS LOCAIS"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if 'gcp_service_account' in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro ao carregar credenciais do secrets: {e}")
    
    # Fallback apenas para desenvolvimento local (NÃO usado em produção)
    try:
        import json
        with open('dashboard-gerencial-492613-042470f98e27.json', 'r') as f:
            creds_dict = json.load(f)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
    except:
        pass
    
    return None

# ==================================================================================================
# 7. FUNÇÕES DE CONVERSÃO DE DADOS
# ==================================================================================================

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

def converter_hora_str(valor):
    """Converte string de hora para objeto time (aceita HH:MM ou HH:MM:SS)"""
    if pd.isna(valor) or valor is None:
        return None
    try:
        valor_str = str(valor).strip()
        if ':' in valor_str:
            partes = valor_str.split(':')
            if len(partes) >= 2:
                h = int(partes[0])
                m = int(partes[1])
                s = int(partes[2]) if len(partes) > 2 else 0
                if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
                    return dt_time(h, m, s)
        return None
    except:
        return None

def time_to_decimal_local(time_val):
    """Converte time para horas decimais"""
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

# ==================================================================================================
# 8. DECORATOR DE RETRY PARA ERROS DE QUOTA
# ==================================================================================================

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

# ==================================================================================================
# 9. FUNÇÃO DE LIMPEZA DE CACHE (SEM ARQUIVOS LOCAIS)
# ==================================================================================================

def limpar_cache_e_recarregar():
    """
    Limpa todo o cache do Streamlit e força o recarregamento dos dados
    SEM arquivos locais
    """
    try:
        st.cache_data.clear()
        st.cache_resource.clear()
        
        if "ultima_verificacao_popup" in st.session_state:
            st.session_state.ultima_verificacao_popup = datetime.now() - timedelta(minutes=5)
        
        if "ultima_atualizacao_mensagem" in st.session_state:
            st.session_state.ultima_atualizacao_mensagem = datetime.now() - timedelta(minutes=5)
        
        return True, "✅ Cache limpo com sucesso! Recarregando dados..."
        
    except Exception as e:
        return False, f"❌ Erro ao limpar cache: {str(e)}"

# ==================================================================================================
# 10. FUNÇÕES DE CONFIGURAÇÃO DE E-MAIL (DO SECRETS)
# ==================================================================================================

def get_email_config_ar():
    """Carrega configurações de e-mail do AR do st.secrets"""
    try:
        return {
            "usuario": st.secrets["smtp_ar"]["usuario"],
            "senha": st.secrets["smtp_ar"]["senha"],
            "destinatarios": st.secrets["smtp_ar"]["destinatarios"],
            "smtp_server": st.secrets["smtp_ar"]["smtp_server"],
            "smtp_port": int(st.secrets["smtp_ar"]["smtp_port"])
        }
    except:
        return None

def get_email_config_rm():
    """Carrega configurações de e-mail do RM do st.secrets"""
    try:
        return {
            "usuario": st.secrets["smtp_rm"]["usuario"],
            "senha": st.secrets["smtp_rm"]["senha"],
            "smtp_server": st.secrets["smtp_rm"]["smtp_server"],
            "smtp_port": int(st.secrets["smtp_rm"]["smtp_port"])
        }
    except:
        return None

def get_emails_setores_rm():
    """Carrega os e-mails dos setores do RM do st.secrets"""
    try:
        return {
            "Elétrica": st.secrets["emails_rm"]["eletrica"],
            "Mecânica": st.secrets["emails_rm"]["mecanica"],
            "Informática": st.secrets["emails_rm"]["informatica"],
            "Ferramentaria": st.secrets["emails_rm"]["ferramentaria"],
            "Manutenção Geral": st.secrets["emails_rm"]["manutencao_geral"],
            "default": st.secrets["emails_rm"]["default"],
            "qualidade": st.secrets["emails_rm"]["qualidade"]
        }
    except:
        return None

# ==================================================================================================
# 11. FUNÇÃO DE SANITIZAÇÃO DE NOMES DE ARQUIVO
# ==================================================================================================

def sanitize_filename(filename: str) -> str:
    """Sanitiza o nome do arquivo removendo caracteres especiais"""
    filename = unicodedata.normalize("NFKD", filename).encode("ASCII", "ignore").decode("ASCII")
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)
    return filename[:50]

# ==================================================================================================
# 12. CSS DA TELA DE LOGIN
# ==================================================================================================

LOGIN_CSS = """
<style>
.login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    font-family: 'Barlow', sans-serif;
    padding: 20px;
}
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
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
}
.login-logo { text-align: center; margin-bottom: 35px; }
.login-logo .icon { font-size: 48px; display: block; margin-bottom: 10px; }
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
.login-field { margin-bottom: 20px; }
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
.login-field .input-wrapper { position: relative; }
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
.login-field input::placeholder { color: #9ca3af; }
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
.login-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
.login-message {
    text-align: center;
    padding: 10px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    margin-top: 15px;
}
.login-message.error { background: #fee2e2; color: #dc2626; border: 1px solid #fecaca; }
.login-message.success { background: #d1fae5; color: #059669; border: 1px solid #a7f3d0; }
.login-footer {
    text-align: center;
    margin-top: 25px;
    font-size: 11px;
    color: #9ca3af;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.05em;
}
@media (max-width: 480px) {
    .login-card { padding: 30px 20px; }
    .login-logo h1 { font-size: 22px; }
}
</style>
"""

# ==================================================================================================
# 13. FUNÇÃO PARA RENDERIZAR TELA DE LOGIN
# ==================================================================================================

def renderizar_tela_login():
    """Renderiza a tela de login profissional com controle de tentativas"""
    
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    
    # Verificar bloqueio por tentativas
    if 'tentativas_login' not in st.session_state:
        st.session_state.tentativas_login = 0
    
    if 'ultimo_bloqueio' not in st.session_state:
        st.session_state.ultimo_bloqueio = None
    
    # Verificar se está bloqueado
    if st.session_state.ultimo_bloqueio:
        tempo_bloqueado = (datetime.now() - st.session_state.ultimo_bloqueio).total_seconds()
        if tempo_bloqueado < BLOQUEIO_LOGIN_MINUTOS * 60:
            minutos_restantes = int((BLOQUEIO_LOGIN_MINUTOS * 60 - tempo_bloqueado) / 60)
            st.error(f"🔒 Conta temporariamente bloqueada. Aguarde {minutos_restantes + 1} minutos.")
            st.stop()
        else:
            st.session_state.ultimo_bloqueio = None
            st.session_state.tentativas_login = 0
    
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
        
        if 'mensagem_login' in st.session_state:
            tipo = st.session_state.mensagem_login.get('tipo', 'error')
            texto = st.session_state.mensagem_login.get('texto', '')
            if texto:
                st.markdown(f"""
                <div class="login-message {tipo}">
                    {texto}
                </div>
                """, unsafe_allow_html=True)
        
        submitted = st.form_submit_button(
            "🔐 ENTRAR",
            use_container_width=True,
            type="primary"
        )
        
        st.markdown("""
        <div class="login-footer">
            Sistema protegido © 2026 Luvidarte<br>
            <span style="font-size: 10px;">Versão 2.0</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div></div>", unsafe_allow_html=True)
    
    if submitted:
        if not user:
            st.session_state.mensagem_login = {'tipo': 'error', 'texto': '❌ Por favor, digite seu usuário!'}
            st.rerun()
        elif not senha:
            st.session_state.mensagem_login = {'tipo': 'error', 'texto': '❌ Por favor, digite sua senha!'}
            st.rerun()
        else:
            sucesso, nivel, setor, status, mensagem = verificar_login(user, senha)
            
            if sucesso:
                st.session_state.logado = True
                st.session_state.usuario = user
                st.session_state.nivel = nivel
                st.session_state.setor = setor
                st.session_state.nivel_usuario = nivel
                st.session_state.setor_usuario = setor
                st.session_state.tempo_login = datetime.now()
                st.session_state.ultima_atividade = datetime.now()
                st.session_state.tentativas_login = 0
                st.session_state.mensagem_login = {'tipo': 'success', 'texto': f'✅ Bem-vindo, {user}!'}
                st.rerun()
            else:
                st.session_state.tentativas_login += 1
                if st.session_state.tentativas_login >= TENTATIVAS_LOGIN_MAX:
                    st.session_state.ultimo_bloqueio = datetime.now()
                    st.session_state.mensagem_login = {
                        'tipo': 'error',
                        'texto': f'🔒 Número máximo de tentativas excedido. Aguarde {BLOQUEIO_LOGIN_MINUTOS} minutos.'
                    }
                else:
                    st.session_state.mensagem_login = {
                        'tipo': 'error',
                        'texto': f'{mensagem} (Tentativa {st.session_state.tentativas_login}/{TENTATIVAS_LOGIN_MAX})'
                    }
                st.rerun()

# ==================================================================================================
# 14. CSS GLOBAL
# ==================================================================================================

def get_global_css():
    """Retorna o CSS global do sistema"""
    return f"""
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
    
    /* Estilo para cards de KPI personalizados */
    .kpi-card {{
        background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%);
        border: 1px solid {THEME['border_bright']};
        border-radius: 8px;
        padding: 18px 22px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        height: 100%;
    }}
    .kpi-card .line {{
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, {THEME['accent_cyan']}, transparent);
    }}
    .kpi-card .label {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        letter-spacing: 0.2em;
        text-transform: uppercase;
        color: {THEME['text_muted']};
        margin-bottom: 8px;
    }}
    .kpi-card .value {{
        font-family: 'Rajdhani', sans-serif;
        font-size: 34px;
        font-weight: 700;
        color: {THEME['accent_cyan']};
        letter-spacing: 0.03em;
        line-height: 1;
    }}
    </style>
    """
    # ==================================================================================================
# PARTE 2/5 - SISTEMA DE NOTIFICAÇÕES, FAIXA DE ROLAGEM, UI E MÓDULOS PRENSADOS/SOPRO
# ==================================================================================================

# ==================================================================================================
# 1. SISTEMA DE NOTIFICAÇÕES - POPUP SIMPLES
# ==================================================================================================

class SistemaNotificacao:
    """Sistema simples de notificações - só mostra registros novos do dia atual"""
    
    def __init__(self):
        self.notificacoes_enviadas = self.carregar_notificacoes()
    
    def carregar_notificacoes(self):
        """Carrega lista de registros já notificados do session_state"""
        if "notificacoes_enviadas" not in st.session_state:
            st.session_state.notificacoes_enviadas = {"ar": [], "rm": [], "data_ultima_limpeza": ""}
        return st.session_state.notificacoes_enviadas
    
    def salvar_notificacoes(self):
        """Salva lista de registros notificados no session_state"""
        st.session_state.notificacoes_enviadas = self.notificacoes_enviadas
    
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
        
        self.limpar_notificacoes_antigas()
        
        # Verificar ARs
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
        except:
            pass
        
        # Verificar RMs
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
        except:
            pass
        
        if novos_ar or novos_rm:
            self.salvar_notificacoes()
        
        return novos_ar, novos_rm

# CSS para popups
NOTIFICACAO_CSS = """
<style>
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
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
@keyframes fadeOut {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(100%); visibility: hidden; }
}
.simple-popup.fade-out { animation: fadeOut 0.3s ease-out forwards; }
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
.popup-close:hover { color: #ef4444; }
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
                <div class="popup-line"><span class="popup-label">Nº:</span><span class="popup-value">{notificacao['numero']}</span></div>
                <div class="popup-line"><span class="popup-label">Ref:</span><span class="popup-value">{notificacao['referencia']}</span></div>
                <div class="popup-line"><span class="popup-label">Emissor:</span><span class="popup-value">{notificacao['emissor']}</span></div>
                <div class="popup-line"><span class="popup-label">Hora:</span><span class="popup-value">{notificacao['hora']}</span></div>
            </div>
            <div class="popup-footer">{timestamp}</div>
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
                <div class="popup-line"><span class="popup-label">ID:</span><span class="popup-value">{notificacao['id']}</span></div>
                <div class="popup-line"><span class="popup-label">Equip:</span><span class="popup-value">{notificacao['equipamento']}</span></div>
                <div class="popup-line"><span class="popup-label">Emissor:</span><span class="popup-value">{notificacao['emissor']}</span></div>
                <div class="popup-line"><span class="popup-label">Hora:</span><span class="popup-value">{notificacao['hora']}</span></div>
            </div>
            <div class="popup-footer">{timestamp}</div>
        </div>
        '''
    
    return html, popup_id

# Controlar última verificação de popups
if "ultima_verificacao_popup" not in st.session_state:
    st.session_state.ultima_verificacao_popup = datetime.now()

sistema_notificacao = SistemaNotificacao()

def verificar_e_exibir_popups():
    """Função principal que verifica novos registros e exibe popups, limitada a cada 60 segundos"""
    aba_atual = st.session_state.get("aba_selecionada", "")
    if aba_atual in ["AVISO DE REJEIÇÃO", "REQUISIÇÃO MANUTENÇÃO"]:
        return
    
    agora = datetime.now()
    if (agora - st.session_state.ultima_verificacao_popup).total_seconds() < 60:
        return
    
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

# ==================================================================================================
# 2. FAIXA DE ROLAGEM (MARQUEE)
# ==================================================================================================

MARQUEE_CSS = """
<style>
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
.marquee-content {
    display: inline-block;
    animation: scrollMarquee 45s linear infinite;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 1px;
    transform: translateX(100%);
}
.marquee-content span {
    display: inline-block;
    margin-right: 100px;
}
@keyframes scrollMarquee {
    0% { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
}
.marquee-container:hover .marquee-content {
    animation-play-state: paused;
}
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
@media (max-width: 768px) {
    .marquee-content { font-size: 11px; animation-duration: 35s; }
    .marquee-container { padding: 6px 0; }
}
.marquee-spacer { height: 55px; }
</style>
"""

@st.cache_data(ttl=240)
def carregar_mensagens_rodape():
    """Carrega as mensagens da planilha Recados - aba Rodapé"""
    try:
        client = get_gspread_client()
        if client is None:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        spreadsheet = client.open_by_key(ID_PLANILHA_RECADOS)
        
        try:
            sheet = spreadsheet.worksheet(ABA_RECADOS)
        except:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        cabecalho = todos_dados[0]
        idx_data = None
        idx_mensagem = None
        
        for i, col in enumerate(cabecalho):
            col_clean = str(col).strip().upper()
            if col_clean == 'DATA':
                idx_data = i
            elif col_clean == 'MENSAGEM':
                idx_mensagem = i
        
        if idx_data is None or idx_mensagem is None:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        hoje = datetime.now().date()
        mensagens_validas = []
        
        for row in todos_dados[1:]:
            if len(row) <= max(idx_data, idx_mensagem):
                continue
            
            data_str = row[idx_data].strip() if row[idx_data] else ""
            mensagem = row[idx_mensagem].strip() if idx_mensagem < len(row) else ""
            
            if not mensagem:
                continue
            
            data_mensagem = None
            
            if '/' in data_str:
                try:
                    partes = data_str.split('/')
                    if len(partes) == 3:
                        dia = int(partes[0])
                        mes = int(partes[1])
                        ano = int(partes[2])
                        data_mensagem = date(ano, mes, dia)
                except:
                    pass
            
            if data_mensagem is None:
                formatos = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]
                for fmt in formatos:
                    try:
                        data_mensagem = datetime.strptime(data_str, fmt).date()
                        break
                    except:
                        continue
            
            if data_mensagem and data_mensagem == hoje:
                mensagens_validas.append(mensagem)
        
        if not mensagens_validas:
            return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]
        
        return mensagens_validas
        
    except Exception as e:
        return ["📢 Sistema TRS Dashboard - Acompanhamento de Produção"]

def renderizar_faixa_rolagem():
    """Renderiza a faixa de rolagem no rodapé da página"""
    mensagens = carregar_mensagens_rodape()
    
    total_mensagens = len(mensagens)
    
    if total_mensagens == 1:
        texto_faixa = f"✨ {mensagens[0]} ✨"
    else:
        partes = []
        for i, msg in enumerate(mensagens, start=1):
            partes.append(f"[{i}/{total_mensagens}] {msg}")
        texto_faixa = " ✨ | ✨ ".join(partes)
        texto_faixa = f"✨ {texto_faixa} ✨"
    
    st.markdown(MARQUEE_CSS, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="marquee-container">
        <div class="marquee-content" id="marquee-content">
            <span>{texto_faixa}</span>
        </div>
    </div>
    <div class="marquee-spacer"></div>
    """, unsafe_allow_html=True)
    
    if "ultima_atualizacao_mensagem" not in st.session_state:
        st.session_state.ultima_atualizacao_mensagem = datetime.now()
    
    agora = datetime.now()
    if (agora - st.session_state.ultima_atualizacao_mensagem).total_seconds() > 60:
        st.session_state.ultima_atualizacao_mensagem = agora
        st.cache_data.clear()
        st.rerun()

# ==================================================================================================
# 3. FUNÇÕES DE RENDERIZAÇÃO DE UI
# ==================================================================================================

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
    <div class="kpi-card">
        <div class="line" style="background: linear-gradient(90deg, {accent}, transparent);"></div>
        <div class="label">{icon} {label}</div>
        <div class="value" style="color: {accent};">{value}</div>
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

# ==================================================================================================
# 4. FUNÇÕES DE CARREGAMENTO DE DADOS - PRENSADOS E SOPRO
# ==================================================================================================

@retry_on_quota()
@st.cache_data(ttl=1200)
def carregar_dados_prensados():
    """Carrega dados da planilha TRS_INDUSTRIAL"""
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
    """Carrega dados da planilha TRS_SOPRO"""
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

# ==================================================================================================
# 5. MÓDULO PRENSADOS - FUNÇÃO COMPLETA
# ==================================================================================================

def render_prensados():
    """Renderiza o módulo PRENSADOS"""
    with st.spinner("Carregando dados..."):
        df_base = carregar_dados_prensados()

    if df_base.empty:
        st.warning("Não foi possível carregar os dados.")
        st.stop()

    # Processamento inicial
    df_base_calc = df_base.copy()
    
    colunas_numericas = ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%', 'REFUGADO']
    for col in colunas_numericas:
        if col in df_base_calc.columns:
            df_base_calc[col] = pd.to_numeric(df_base_calc[col], errors='coerce').fillna(0)

    if 'AP_TEMPERA' in df_base_calc.columns:
        df_base_calc['TEMPERADO'] = pd.to_numeric(df_base_calc['AP_TEMPERA'], errors='coerce').fillna(0)
    else:
        df_base_calc['TEMPERADO'] = 0

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

    # Sidebar filtros
    with st.sidebar:
        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_cyan']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>
            ▸ Filtros · Prensados
        </div>
        """, unsafe_allow_html=True)
        
        data_ini = st.date_input("Data inicial", value=None, key="prensados_data_ini")
        data_fim = st.date_input("Data final", value=None, key="prensados_data_fim")
        turno = st.selectbox("Turno", options=["(Todos)", "M", "T", "N"], key="prensados_turno")
        referencia = st.text_input("Referência (parte do código)", key="prensados_ref")
        prensa_tipo = st.selectbox("Tipo de prensa", ["(Todos)", "Semi-Automática", "Automática"], key="prensados_tipo")
        
        st.markdown("---")
        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_yellow']};'>
            ▸ Filtro TRS
        </div>
        """, unsafe_allow_html=True)
        
        faixa_trs = st.selectbox(
            "Faixa de TRS Final",
            ["(Todas)", "Excelente (>85%)", "Bom (70-85%)", "Regular (50-70%)", "Crítico (<50%)"],
            key="prensados_faixa_trs"
        )
        
        st.markdown("---")
        mostrar_defeitos = st.checkbox("Somatório de Defeitos", value=True, key="prensados_defeitos")
        qtd = st.number_input("Linhas na tabela (0 = todas)", min_value=0, max_value=5000, value=0, step=10, key="prensados_qtd")

    # Aplicar filtros
    df = df_base_calc.copy()
    
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
    
    if faixa_trs != "(Todas)" and 'TRS FINAL (%)' in df.columns:
        if faixa_trs == "Excelente (>85%)":
            df = df[df['TRS FINAL (%)'] > 85]
        elif faixa_trs == "Bom (70-85%)":
            df = df[(df['TRS FINAL (%)'] >= 70) & (df['TRS FINAL (%)'] <= 85)]
        elif faixa_trs == "Regular (50-70%)":
            df = df[(df['TRS FINAL (%)'] >= 50) & (df['TRS FINAL (%)'] < 70)]
        elif faixa_trs == "Crítico (<50%)":
            df = df[df['TRS FINAL (%)'] < 50]

    # KPIs
    if not df.empty:
        for col in ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%', 'REFUGADO', 'TEMPERADO']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        total_prod = int(df['PRODUZIDO'].sum())
        total_apro = int(df['APROVADO'].sum())
        total_embal = int(df['EMBALADO'].sum()) if 'EMBALADO' in df.columns else 0
        total_meta = int(df['TRS 100%'].sum()) if 'TRS 100%' in df.columns else 0
        total_temperado = int(df['TEMPERADO'].sum()) if 'TEMPERADO' in df.columns else 0
        
        trs_primeira_escolha = (total_apro / total_meta * 100) if total_meta else 0
        trs_final_total = (total_embal / total_meta * 100) if total_meta else 0
    else:
        total_prod = total_apro = total_embal = total_meta = total_temperado = trs_primeira_escolha = trs_final_total = 0

    # Page header
    render_page_header("PRENSADOS", f"Industrial · {len(df):,} registros carregados · Atualizado {get_horario_brasilia()}", THEME['accent_cyan'])

    # KPIs (7 cards)
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    with c1: render_kpi_card("Produzido", f"{total_prod:,}".replace(",","."), THEME['accent_cyan'], "◈")
    with c2: render_kpi_card("Aprovado", f"{total_apro:,}".replace(",","."), THEME['accent_lime'], "◈")
    with c3: render_kpi_card("Meta Líquida", f"{total_meta:,}".replace(",","."), THEME['accent_purple'], "◈")
    with c4: render_kpi_card("Embalado", f"{total_embal:,}".replace(",","."), THEME['accent_yellow'], "◈")
    with c5: render_kpi_card("Temperado", f"{total_temperado:,}".replace(",","."), THEME['accent_orange'], "🔥")
    with c6:
        trs_primeira_cor = THEME['accent_lime'] if trs_primeira_escolha >= 85 else THEME['accent_orange'] if trs_primeira_escolha >= 70 else THEME['accent_red']
        render_kpi_card("TRS 1ª Escolha", f"{trs_primeira_escolha:.1f}%", trs_primeira_cor, "◎")
    with c7:
        trs_final_cor = THEME['accent_yellow'] if trs_final_total >= 85 else THEME['accent_orange'] if trs_final_total >= 70 else THEME['accent_red']
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
    df_view = df_sorted if qtd == 0 else df_sorted.head(qtd)

    if not df_view.empty:
        df_display = df_view.copy()
        df_display['DATA'] = pd.to_datetime(df_display['DATA']).dt.strftime('%d/%m/%Y')

        for col in ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'REFUGADO', 'TRS 100%', 'TEMPERADO']:
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(lambda x: int(round(x)) if pd.notnull(x) else 0)
                df_display[col] = df_display[col].apply(lambda x: f"{x:,}".replace(",", "."))
        
        if 'TRS 1ª ESCOLHA (%)' in df_display.columns:
            df_display['TRS 1ª ESCOLHA (%)'] = df_display['TRS 1ª ESCOLHA (%)'].apply(lambda x: f"{x:.2f}%")
        if 'TRS FINAL (%)' in df_display.columns:
            df_display['TRS FINAL (%)'] = df_display['TRS FINAL (%)'].apply(lambda x: f"{x:.2f}%")

        colunas_exibir = ['DATA', 'REFERÊNCIA', 'TURNO', 'PRODUZIDO', 'APROVADO', 'TEMPERADO', 'TRS 100%', 'EMBALADO', 'REFUGADO', 'TRS 1ª ESCOLHA (%)', 'TRS FINAL (%)']
        if 'ANALISE' in df_display.columns:
            colunas_exibir.append('ANALISE')
        colunas_exibir = [col for col in colunas_exibir if col in df_display.columns]

        st.dataframe(df_display[colunas_exibir], use_container_width=True, height=400)

    # Gráfico TRS Diário
    render_section_header("Evolução Diária do TRS", "▸")

    if not df.empty and 'TRS 100%' in df.columns:
        colunas_agg = {}
        for col in ['PRODUZIDO', 'APROVADO', 'EMBALADO', 'TRS 100%']:
            if col in df.columns:
                colunas_agg[col] = 'sum'
        if 'TEMPERADO' in df.columns:
            colunas_agg['TEMPERADO'] = 'sum'
        
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

    # Gráfico por turno
    if not df.empty and 'TURNO' in df.columns:
        render_section_header("TRS por Turno", "▸")
        turno_data = []
        mapeamento_turnos = {'M': 'Manhã', 'T': 'Tarde', 'N': 'Noite'}
        
        for t in df['TURNO'].unique():
            df_t = df[df['TURNO'] == t]
            te = df_t['EMBALADO'].sum() if 'EMBALADO' in df_t.columns else 0
            ta = df_t['APROVADO'].sum()
            tm = df_t['TRS 100%'].sum()
            turno_data.append({
                'Turno': mapeamento_turnos.get(t, t),
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
            ax.set_xticks(x)
            ax.set_xticklabels(df_tt['Turno'], fontsize=11)
            ax.legend(loc='upper right', fontsize=9)
            ax.set_ylim(0, 105)
            
            fig.tight_layout(pad=1.5)
            st.pyplot(fig)
            plt.close(fig)

    # Seção de defeitos
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
        
        if defeitos_existentes:
            defeitos_existentes = list(dict.fromkeys(defeitos_existentes))
            df_def = df[defeitos_existentes].apply(pd.to_numeric, errors='coerce').fillna(0)
            df_def_sum = df_def.sum().sort_values(ascending=False)
            df_def_sum = df_def_sum[df_def_sum > 0]
            
            if not df_def_sum.empty:
                altura_grafico = max(4, len(df_def_sum) * 0.35)
                fig, ax = plt.subplots(figsize=(12, altura_grafico), facecolor=THEME['bg_card'])
                apply_chart_style(ax, fig, "Defeitos de Prensados — Somatório", ylabel="Quantidade")
                
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
                st.caption(f"**Total de defeitos de Prensados:** {int(total_def):,}".replace(",","."))

# ==================================================================================================
# 6. MÓDULO SOPRO - FUNÇÃO COMPLETA
# ==================================================================================================

def render_sopro():
    """Renderiza o módulo SOPRO"""
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

    # Sidebar filtros
    with st.sidebar:
        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_lime']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>
            ▸ Filtros · Sopro
        </div>
        """, unsafe_allow_html=True)
        
        data_ini = st.date_input("Data inicial", value=None, key="sopro_data_ini")
        data_fim = st.date_input("Data final", value=None, key="sopro_data_fim")
        
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

    # Aplicar filtros
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

    total_prod = int(df['PRODUZIDO'].sum()) if 'PRODUZIDO' in df.columns else 0
    total_refugo = int(df['REFUGADO'].sum()) if 'REFUGADO' in df.columns else 0
    total_apro = int(df['APROVADO'].sum()) if 'APROVADO' in df.columns else 0
    trs_liq_med = df['TRS_BRUTO'].mean() * 100 if 'TRS_BRUTO' in df.columns and not df.empty else 0
    
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

    # KPIs
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

# ==================================================================================================
# 7. SIDEBAR - NAVEGAÇÃO E INFORMAÇÕES DO USUÁRIO
# ==================================================================================================

def render_sidebar():
    """Renderiza a sidebar com navegação e informações do usuário"""
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align: center; padding: 20px 0 16px; border-bottom: 1px solid {THEME['border_bright']}; margin-bottom: 20px;">
            <div style="font-family: 'Rajdhani', sans-serif; font-size: 24px; font-weight: 700; color: {THEME['accent_cyan']}; letter-spacing: 0.2em;">⚙ ERP - Luvidarte</div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: {THEME['text_muted']}; letter-spacing: 0.2em; text-transform: uppercase;">Aqui tem Café no bule</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_cyan']};margin-bottom:8px'>
            ▸ Setor
        </div>
        """, unsafe_allow_html=True)
        
        aba_selecionada = st.radio("", list(ABAS.keys()), label_visibility="collapsed")
        st.session_state.aba_selecionada = aba_selecionada
        
        # Informações do usuário
        st.markdown("---")
        
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
        
        # Botão para limpar cache
        st.markdown("---")
        
        if "ultima_atualizacao_cache" not in st.session_state:
            st.session_state.ultima_atualizacao_cache = datetime.now()
        
        st.caption(f"🔄 Última atualização: {st.session_state.ultima_atualizacao_cache.strftime('%H:%M:%S')}")
        
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
        
        if st.button("📊 Recarregar Dados Apenas", use_container_width=True):
            with st.spinner("🔄 Recarregando dados..."):
                st.cache_data.clear()
                st.session_state.ultima_atualizacao_cache = datetime.now()
                st.success("✅ Dados recarregados!")
                time.sleep(0.3)
                st.rerun()
        
        st.markdown("---")
        st.caption(f"""
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 8px; color: {THEME['text_muted']}; text-align: center;">
            TRS Dashboard v2.0<br>
            {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        </div>
        """, unsafe_allow_html=True)
    
    return aba_selecionada

# ==================================================================================================
# 8. MAIN - ROTEADOR PRINCIPAL
# ==================================================================================================

def main():
    """Função principal do aplicativo"""
    
    # Configuração da página
    st.set_page_config(
        page_title="TRS Dashboard",
        page_icon="⚙️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Aplicar CSS global
    st.markdown(get_global_css(), unsafe_allow_html=True)
    st.markdown(NOTIFICACAO_CSS, unsafe_allow_html=True)
    
    # Verificação de acesso
    if not verificar_acesso():
        st.stop()
    
    if 'mensagem_login' in st.session_state:
        del st.session_state.mensagem_login
    
    # Renderizar popups e verificar novos registros
    renderizar_popups_pendentes()
    verificar_e_exibir_popups()
    
    # Renderizar sidebar e obter aba selecionada
    aba_selecionada = render_sidebar()
    
    # Roteamento para os módulos
    if aba_selecionada == 'PRENSADOS':
        render_prensados()
    elif aba_selecionada == 'SOPRO':
        render_sopro()
    # Os demais módulos serão adicionados nas partes seguintes
    else:
        # Placeholder para os demais módulos
        render_page_header(aba_selecionada, "Módulo em desenvolvimento...", THEME['accent_purple'])
        st.info(f"O módulo '{aba_selecionada}' será disponibilizado em breve.")
    
    # Renderizar faixa de rolagem no rodapé
    renderizar_faixa_rolagem()

# Ponto de entrada do aplicativo
if __name__ == "__main__":
    main()

# ==================================================================================================
# PARTE 3/5 - MÓDULOS TÊMPERA, AVISO DE REJEIÇÃO (AR) E REQUISIÇÃO DE MANUTENÇÃO (RM)
# ==================================================================================================

# ==================================================================================================
# 1. MÓDULO TÊMPERA - FUNÇÕES DE CARREGAMENTO E PROCESSAMENTO
# ==================================================================================================

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

def processar_dados_tempera(todos_dados):
    """Processa os dados brutos da planilha e retorna DataFrame processado"""
    if len(todos_dados) < 2:
        return pd.DataFrame()
    
    cabecalho = todos_dados[0]
    valores = todos_dados[1:]
    df = pd.DataFrame(valores, columns=cabecalho)
    
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
            df[col] = df[col].apply(safe_float_tempera)
    
    # Converter C2 (tempo)
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
    
    # Identificar colunas de posições
    colunas_posicoes_validas = []
    for col in df.columns:
        try:
            num = float(str(col).strip())
            if 19 <= num <= 70:
                colunas_posicoes_validas.append(col)
        except:
            pass
    
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
    
    # Processar cada linha
    for idx, row in df.iterrows():
        defeitos_contagem = {codigo: 0 for codigo in MAPEAMENTO_DEFEITOS.keys()}
        
        for col in colunas_posicoes_validas:
            try:
                val = row[col]
                if pd.notna(val) and str(val).strip():
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

@retry_on_quota()
@st.cache_data(ttl=1200)
def carregar_dados_tempera():
    """Carrega dados da têmpera com validação"""
    try:
        client = get_gspread_client()
        if client is None:
            st.error("❌ Não foi possível conectar ao Google Sheets")
            return pd.DataFrame()
        
        sheet = client.open_by_key(ID_PLANILHA_TEMPERA).worksheet('TRS_TEMPERA')
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            st.warning("⚠️ A planilha está vazia ou não tem dados suficientes.")
            return pd.DataFrame()
        
        df = processar_dados_tempera(todos_dados)
        
        if df.empty:
            st.warning("⚠️ Nenhum dado válido encontrado na planilha.")
            return pd.DataFrame()
        
        return df
        
    except Exception as e:
        if "429" in str(e) or "Quota exceeded" in str(e):
            st.warning("⚠️ Limite de requisições ao Google Sheets atingido.")
            return pd.DataFrame()
        else:
            st.error(f"❌ Erro ao carregar dados: {str(e)}")
            return pd.DataFrame()

def safe_mean_tempera(df, col):
    """Calcula média ignorando valores zero e NaN"""
    if col in df.columns:
        valores = df[col][(df[col] > 0) & (pd.notna(df[col]))]
        if len(valores) > 0:
            return valores.mean()
    return 0

def render_tempera():
    """Renderiza o módulo TÊMPERA"""
    ABA = 'TRS_TEMPERA'

    with st.spinner("Carregando dados da Têmpera..."):
        df_base = carregar_dados_tempera()

    if df_base.empty:
        st.error("❌ Não foi possível carregar os dados da Têmpera.")
        st.stop()

    # Sidebar filtros
    with st.sidebar:
        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_purple']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>
            ▸ Filtros · Têmpera
        </div>
        """, unsafe_allow_html=True)
        
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
        if st.button("🔄 Recarregar Dados", key="btn_recarregar_tempera", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Aplicar filtros
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

    # KPIs
    total_registros = len(df)
    total_pecas = total_registros * 40
    total_aprovado = int(df['APROVADO'].sum())
    total_defeitos = int(df['TOTAL_DEFEITOS'].sum())
    trs_medio = (total_aprovado / total_pecas * 100) if total_pecas > 0 else 0
    
    temp_sup = safe_mean_tempera(df, 'SUPERIOR')
    temp_meio = safe_mean_tempera(df, 'MEIO')
    temp_inf = safe_mean_tempera(df, 'INFERIOR')
    temp_entrada = safe_mean_tempera(df, 'A1')
    tempo_c2 = safe_mean_tempera(df, 'C2')
    humidade = safe_mean_tempera(df, 'C4')
    pressao_ar = safe_mean_tempera(df, 'A e B')

    render_page_header("TÊMPERA", f"Industrial · {total_registros:,} registros · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])

    # KPIs principais
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi_card("Total Peças", f"{total_pecas:,}".replace(",","."), THEME['accent_cyan'])
    with c2: render_kpi_card("Aprovadas", f"{total_aprovado:,}".replace(",","."), THEME['accent_lime'])
    with c3: render_kpi_card("Defeitos", f"{total_defeitos:,}".replace(",","."), THEME['accent_red'])
    with c4:
        trs_color = THEME['accent_lime'] if trs_medio >= 80 else THEME['accent_orange'] if trs_medio >= 70 else THEME['accent_red']
        render_kpi_card("TRS Médio", f"{trs_medio:.1f}%", trs_color)

    # Temperaturas
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi_card("Temp. Superior", f"{temp_sup:.0f}°C" if temp_sup > 0 else "N/A", THEME['accent_orange'])
    with c2: render_kpi_card("Temp. Meio", f"{temp_meio:.0f}°C" if temp_meio > 0 else "N/A", THEME['accent_orange'])
    with c3: render_kpi_card("Temp. Inferior", f"{temp_inf:.0f}°C" if temp_inf > 0 else "N/A", THEME['accent_orange'])

    # Processo
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-family:JetBrains Mono,monospace;font-size:10px;color:{THEME['accent_purple']};">
        ▸ PROCESSO - MÉDIAS DO PERÍODO (ignorando zeros)
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi_card("Temp. Entrada (A1)", f"{temp_entrada:.0f}°C" if temp_entrada > 0 else "N/A", THEME['accent_cyan'])
    with c2: render_kpi_card("Tempo (C2)", f"{tempo_c2:.0f}s" if tempo_c2 > 0 else "N/A", THEME['accent_lime'])
    with c3: render_kpi_card("Humidade (C4)", f"{humidade:.1f}%" if humidade > 0 else "N/A", THEME['accent_orange'])
    with c4: render_kpi_card("Pressão Ar (A e B)", f"{pressao_ar:.1f}" if pressao_ar > 0 else "N/A", THEME['accent_purple'])

    st.markdown("<hr>", unsafe_allow_html=True)

    # Tabela
    render_section_header("Registros de Têmpera", "▸", THEME['accent_purple'])
    
    df_display = df.sort_values(by="DATA", ascending=False).head(qtd if qtd > 0 else 100).copy()
    df_display['DATA'] = pd.to_datetime(df_display['DATA']).dt.strftime('%d/%m/%Y')
    df_display['TRS (%)'] = df_display['TRS (%)'].round(1).astype(str) + '%'
    
    colunas = ['DATA', 'TURNO_TEMP', 'PRODUTO', 'GANCHEIRA', 'APROVADO', 'TOTAL_DEFEITOS', 'TRS (%)']
    colunas = [c for c in colunas if c in df_display.columns]
    
    st.dataframe(df_display[colunas], use_container_width=True, height=400)

    # Gráfico TRS Diário
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

    # Padrão de Excelência
    st.markdown("<hr>", unsafe_allow_html=True)
    render_section_header("🏆 PADRÃO DE EXCELÊNCIA (Média Top 15)", "▸", THEME['accent_purple'])
    
    TOP_N = 15
    
    if 'A e B' in df.columns:
        df_validos = df[df['A e B'] > 0].copy()
    else:
        df_validos = df.copy()
    
    if len(df_validos) >= TOP_N:
        df_top = df_validos.nlargest(TOP_N, ['APROVADO', 'TRS (%)'])
        
        media_aprovadas = df_top['APROVADO'].mean()
        media_trs = df_top['TRS (%)'].mean()
        media_defeitos = df_top['TOTAL_DEFEITOS'].mean()
        
        media_temp_sup = df_top['SUPERIOR'].mean()
        media_temp_meio = df_top['MEIO'].mean()
        media_temp_inf = df_top['INFERIOR'].mean()
        media_temp_entrada = df_top['A1'].mean()
        media_tempo_c2 = df_top['C2'].mean()
        media_humidade = df_top['C4'].mean()
        media_pressao_ar = df_top['A e B'].mean()
        
        std_trs = df_top['TRS (%)'].std()
        criticas_top = df_top['IS_CRITICO'].sum()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("📊 TRS Médio (Top 15)", f"{media_trs:.1f}%", f"±{std_trs:.1f}%" if std_trs > 0 else "estável")
        with col2: st.metric("✅ Aprovadas (Média)", f"{media_aprovadas:.1f}/40")
        with col3: st.metric("❌ Defeitos (Média)", f"{media_defeitos:.1f}")
        with col4: st.metric("⚠️ Produções Críticas", f"{criticas_top}/{TOP_N}")
        
        st.markdown("#### 🔥 Temperaturas do Forno (Média)")
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Superior", f"{media_temp_sup:.0f}°C" if pd.notna(media_temp_sup) else "N/A")
        with col2: st.metric("Meio", f"{media_temp_meio:.0f}°C" if pd.notna(media_temp_meio) else "N/A")
        with col3: st.metric("Inferior", f"{media_temp_inf:.0f}°C" if pd.notna(media_temp_inf) else "N/A")
        
    # Ranking de Gancheiras
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
            
            ranking_gancheiras.append({
                'Gancheira': str(gancheira),
                'Reg': total_registros_g,
                'Defeitos': total_defeitos_g,
                'Média': total_defeitos_g / total_registros_g if total_registros_g > 0 else 0,
                'TRS': f"{trs_g:.1f}%"
            })
        
        df_ranking = pd.DataFrame(ranking_gancheiras)
        df_ranking = df_ranking.sort_values('Defeitos', ascending=False)
        df_ranking['Pos'] = range(1, len(df_ranking) + 1)
        
        if not df_ranking.empty:
            piores = df_ranking.head(3)
            st.warning(f"⚠️ **Piores gancheiras:** {', '.join(piores['Gancheira'].tolist())}")
            
            df_tabela = df_ranking[['Pos', 'Gancheira', 'Reg', 'Defeitos', 'Média', 'TRS']].copy()
            df_tabela['Média'] = df_tabela['Média'].round(1)
            st.dataframe(df_tabela, use_container_width=True, height=250)

# ==================================================================================================
# 2. MÓDULO AVISO DE REJEIÇÃO (AR) - DATACLASS E FUNÇÕES
# ==================================================================================================

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
    defeito_biblioteca: str = ""
    sugestao_biblioteca: str = ""
    direcionamento_biblioteca: str = ""
    # Campos de auditoria
    criado_por: str = ""
    criado_em: Optional[datetime] = None
    alterado_por: str = ""
    alterado_em: Optional[datetime] = None
    excluido: bool = False
    excluido_por: str = ""
    excluido_em: Optional[datetime] = None

@st.cache_data(ttl=3600)
def carregar_biblioteca_defeitos():
    """Carrega a biblioteca de defeitos conhecidos do Google Sheets"""
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
        for row in todos_dados[1:]:
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
        return {}

@retry_on_quota()
def carregar_registros_ar_sem_cache() -> List[RegistroAR]:
    """Carrega registros AR sem cache (para notificações)"""
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
                # Campos da biblioteca
                registro.defeito_biblioteca = row[12] if len(row) > 12 else ""
                registro.sugestao_biblioteca = row[13] if len(row) > 13 else ""
                registro.direcionamento_biblioteca = row[14] if len(row) > 14 else ""
                # Campos de auditoria
                registro.excluido = False  # Por padrão, não está excluído
                registros.append(registro)
            except:
                continue
        
        # Filtrar registros excluídos (soft delete)
        registros = [r for r in registros if not r.excluido]
        registros.sort(key=lambda x: x.data if x.data else datetime.min, reverse=True)
    except:
        pass
    return registros

@st.cache_data(ttl=1200)
def carregar_registros_ar(filtros: Dict[str, Any] = None) -> List[RegistroAR]:
    """Carrega registros AR com cache"""
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

def obter_proximo_numero_ar():
    """Obtém o próximo número disponível para AR"""
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

def salvar_registro_ar(registro: RegistroAR, eh_alteracao: bool = False) -> bool:
    """Salva ou atualiza um registro AR com auditoria"""
    try:
        client = get_gspread_client()
        if client is None:
            return False
        
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
        agora = get_horario_brasilia_obj()
        usuario = st.session_state.get('usuario', 'SISTEMA')
        
        if eh_alteracao:
            registro.alterado_por = usuario
            registro.alterado_em = agora
        else:
            registro.criado_por = usuario
            registro.criado_em = agora
        
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
            registro.defeito_biblioteca,
            registro.sugestao_biblioteca,
            registro.direcionamento_biblioteca,
            registro.criado_por if not eh_alteracao else "",
            registro.criado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.criado_em and not eh_alteracao else "",
            registro.alterado_por if eh_alteracao else "",
            registro.alterado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.alterado_em and eh_alteracao else "",
            "FALSE"  # excluido
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
        
        st.cache_data.clear()
        return True
    except:
        return False

def excluir_registro_ar(numero: int) -> bool:
    """Realiza soft delete de um registro AR"""
    try:
        client = get_gspread_client()
        if client is None:
            return False
        
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_AR)
        cell = sheet.find(str(numero), in_column=1)
        if cell:
            usuario = st.session_state.get('usuario', 'SISTEMA')
            agora = get_horario_brasilia_obj()
            # Marcar como excluído
            sheet.update_cell(cell.row, 19, "TRUE")  # excluido
            sheet.update_cell(cell.row, 20, usuario)  # excluido_por
            sheet.update_cell(cell.row, 21, agora.strftime("%d/%m/%Y %H:%M:%S"))  # excluido_em
            st.cache_data.clear()
            return True
        return False
    except:
        return False

def gerar_pdf_ar(registro: RegistroAR) -> Optional[bytes]:
    """Gera PDF do AR em memória"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        
        buffer = io.BytesIO()
        
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
        
        style_titulo = ParagraphStyle('Titulo', parent=styleN, fontSize=14, alignment=1, spaceAfter=8, fontName='Helvetica-Bold')
        style_subtitulo = ParagraphStyle('Subtitulo', parent=styleN, fontSize=11, alignment=1, spaceAfter=12)
        style_titulo_secao = ParagraphStyle('TituloSecao', parent=styleN, fontSize=11, spaceAfter=4, fontName='Helvetica-Bold')
        style_descricao = ParagraphStyle('Descricao', parent=styleN, fontSize=11, leading=14, spaceAfter=8)
        
        elementos.append(Paragraph("<b>AVISO DE REJEIÇÃO</b>", style_titulo))
        elementos.append(Paragraph("<b>CQ-018 REV004 - Luvidarte</b>", style_subtitulo))
        
        data_str = registro.data.strftime("%d/%m/%Y") if registro.data else ""
        data_fim_str = registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else ""
        
        dados_tabela = [
            ["Nº Controle:", str(registro.numero) if registro.numero else "", "Data:", data_str],
            ["Hora:", registro.hora, "Turno:", registro.turno],
            ["Código:", registro.codigo, "Status:", registro.status],
            ["Emissor:", registro.emissor, "", ""],
            ["Referência:", registro.referencia, "", ""],
            ["Situação:", registro.decisao, "Data Finalização:", data_fim_str]
        ]
        
        tabela = Table(dados_tabela, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
        tabela.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (0,0), (-1,-1), "LEFT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("PADDING", (0,0), (-1,-1), 5),
            ("SPAN", (2,3), (3,3)),
            ("SPAN", (2,4), (3,4)),
        ]))
        elementos.append(tabela)
        elementos.append(Spacer(1, 12))
        
        elementos.append(Paragraph("<b>DESCRIÇÃO DO PROBLEMA:</b>", style_titulo_secao))
        texto_descricao = ""
        if registro.defeito_biblioteca and str(registro.defeito_biblioteca).strip():
            texto_descricao += f"<b>DEFEITO IDENTIFICADO: {str(registro.defeito_biblioteca).strip()}</b>"
            if registro.descricao and registro.descricao.strip():
                texto_descricao += "<br/><br/>"
        if registro.descricao and registro.descricao.strip():
            texto_descricao += str(registro.descricao).strip()
        if not texto_descricao:
            texto_descricao = "-"
        elementos.append(Paragraph(texto_descricao, style_descricao))
        elementos.append(Spacer(1, 8))
        
        if registro.sugestao_biblioteca and str(registro.sugestao_biblioteca).strip():
            elementos.append(Paragraph("<b>SUGESTÃO PARA SOLUCIONAR PROBLEMA:</b>", style_titulo_secao))
            sugestao_texto = str(registro.sugestao_biblioteca)
            partes = sugestao_texto.split('*')
            for parte in partes:
                parte_limpa = parte.strip()
                if parte_limpa:
                    elementos.append(Paragraph(f"• {parte_limpa}", style_descricao))
            elementos.append(Spacer(1, 6))
        
        if registro.direcionamento_biblioteca and str(registro.direcionamento_biblioteca).strip():
            elementos.append(Paragraph("<b>DIRECIONAMENTO AO INSPETOR:</b>", style_titulo_secao))
            elementos.append(Paragraph(str(registro.direcionamento_biblioteca), style_descricao))
            elementos.append(Spacer(1, 8))
        
        elementos.append(Paragraph("<b>DISPOSIÇÃO / AÇÕES TOMADAS:</b>", style_titulo_secao))
        elementos.append(Paragraph(registro.disposicao or "-", style_descricao))
        elementos.append(Spacer(1, 8))
        
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
        
        elementos.append(Spacer(1, 12))
        elementos.append(Paragraph(f"Documento gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", 
                                   ParagraphStyle('Rodape', parent=styleN, fontSize=7, alignment=2)))
        
        doc.build(elementos)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        return None

def enviar_email_ar(destinatarios, assunto, corpo, anexo_bytes=None, nome_anexo=None):
    """Envia e-mail com anexo PDF"""
    config = get_email_config_ar()
    if config is None:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = config["usuario"]
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain'))
        
        if anexo_bytes and nome_anexo:
            anexo = MIMEApplication(anexo_bytes, _subtype='pdf')
            anexo.add_header('Content-Disposition', 'attachment', filename=nome_anexo)
            msg.attach(anexo)
        
        with smtplib.SMTP_SSL(config["smtp_server"], config["smtp_port"], timeout=30) as server:
            server.login(config["usuario"], config["senha"])
            server.send_message(msg)
        return True
    except Exception as e:
        return False

# ==================================================================================================
# 3. MÓDULO REQUISIÇÃO DE MANUTENÇÃO (RM) - DATACLASS E FUNÇÕES
# ==================================================================================================

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
    # Campos de auditoria
    criado_por: str = ""
    criado_em: Optional[datetime] = None
    alterado_por: str = ""
    alterado_em: Optional[datetime] = None
    excluido: bool = False
    excluido_por: str = ""
    excluido_em: Optional[datetime] = None

@retry_on_quota()
def carregar_registros_rm_sem_cache() -> List[RegistroRM]:
    """Carrega registros RM sem cache"""
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
                registro.excluido = False
                
                if registro.id is not None:
                    registros.append(registro)
            except:
                continue
        
        registros = [r for r in registros if not r.excluido]
        registros.sort(key=lambda x: x.id if x.id else 0, reverse=True)
    except:
        pass
    return registros

@st.cache_data(ttl=1200)
def carregar_registros_rm(filtros: Dict[str, Any] = None) -> List[RegistroRM]:
    """Carrega registros RM com cache"""
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
            if filtros.get('setor2') and filtros['setor2'].upper() != r.setor2.upper():
                incluir = False
            if incluir:
                registros_filtrados.append(r)
        return registros_filtrados
    return registros

def obter_proximo_id_rm():
    """Obtém o próximo ID disponível para RM"""
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

def salvar_registro_rm(registro: RegistroRM, eh_alteracao: bool = False) -> bool:
    """Salva ou atualiza um registro RM com auditoria"""
    try:
        client = get_gspread_client()
        if client is None:
            return False
        
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
        agora = get_horario_brasilia_obj()
        usuario = st.session_state.get('usuario', 'SISTEMA')
        
        if eh_alteracao:
            registro.alterado_por = usuario
            registro.alterado_em = agora
        else:
            registro.criado_por = usuario
            registro.criado_em = agora
        
        dados = [
            str(registro.id) if registro.id else "",
            registro.data.strftime("%d/%m/%Y") if registro.data else "",
            registro.hora,
            registro.emissor,
            registro.equipamento,
            registro.setor,
            registro.caracter,
            registro.setor2,
            registro.problema,
            registro.trabalho,
            registro.analise,
            registro.status,
            registro.data_finalizacao.strftime("%d/%m/%Y") if registro.data_finalizacao else "",
            registro.emissor2,
            registro.criado_por if not eh_alteracao else "",
            registro.criado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.criado_em and not eh_alteracao else "",
            registro.alterado_por if eh_alteracao else "",
            registro.alterado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.alterado_em and eh_alteracao else "",
            "FALSE"
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
            # Envia e-mail de criação
            try:
                enviar_email_rm(registro, "CRIAÇÃO")
            except:
                pass
        
        st.cache_data.clear()
        return True
    except:
        return False

def excluir_registro_rm(id_registro: int) -> bool:
    """Realiza soft delete de um registro RM"""
    try:
        client = get_gspread_client()
        if client is None:
            return False
        
        sheet = client.open_by_key(ID_PLANILHA_AR).worksheet(ABA_RM)
        cell = sheet.find(str(id_registro), in_column=1)
        if cell:
            usuario = st.session_state.get('usuario', 'SISTEMA')
            agora = get_horario_brasilia_obj()
            sheet.update_cell(cell.row, 18, "TRUE")
            sheet.update_cell(cell.row, 19, usuario)
            sheet.update_cell(cell.row, 20, agora.strftime("%d/%m/%Y %H:%M:%S"))
            st.cache_data.clear()
            return True
        return False
    except:
        return False

def obter_email_setor_rm(setor_destino: str) -> str:
    """Obtém o e-mail do setor destino"""
    emails = get_emails_setores_rm()
    if emails is None:
        return ""
    return emails.get(setor_destino, emails.get("default", ""))

def enviar_email_rm(registro: RegistroRM, acao: str = "CRIAÇÃO") -> bool:
    """Envia e-mail de notificação de RM"""
    config = get_email_config_rm()
    emails_setores = get_emails_setores_rm()
    
    if config is None or emails_setores is None:
        return False
    
    try:
        email_destino = obter_email_setor_rm(registro.setor2)
        destinatarios = [email_destino, emails_setores.get("qualidade", ""), "engenharia@luvidarte.com.br"]
        destinatarios = list(dict.fromkeys([d for d in destinatarios if d]))
        
        if not destinatarios:
            return False
        
        msg = MIMEMultipart()
        msg["From"] = config["usuario"]
        msg["To"] = ", ".join(destinatarios)
        
        data_str = registro.data.strftime("%d/%m/%Y") if registro.data else ""
        
        if acao == "EXCLUSÃO":
            msg["Subject"] = f"RM {registro.id} - EXCLUÍDA - {registro.equipamento}"
            corpo = f"""
            <html><body>
            <h2 style="color: #E81123;">⚠️ REQUISIÇÃO DE MANUTENÇÃO EXCLUÍDA</h2>
            <p>A requisição <b>{registro.id}</b> foi excluída do sistema.</p>
            <p><b>Equipamento:</b> {registro.equipamento}</p>
            <p><b>Data:</b> {data_str}</p>
            </body></html>
            """
        else:
            emoji = "🆕" if acao == "CRIAÇÃO" else "✏️"
            cor = "#0078D4"
            msg["Subject"] = f"RM {registro.id} - {acao} - {registro.equipamento}"
            corpo = f"""
            <html><body>
            <h2 style="color: {cor};">{emoji} REQUISIÇÃO DE MANUTENÇÃO #{registro.id} - {acao}</h2>
            <p><b>Equipamento:</b> {registro.equipamento}</p>
            <p><b>Setor:</b> {registro.setor}</p>
            <p><b>Caráter:</b> {registro.caracter}</p>
            <p><b>Status:</b> {registro.status}</p>
            <p><b>Problema:</b> {registro.problema}</p>
            </body></html>
            """
        
        msg.attach(MIMEText(corpo, "html"))
        
        with smtplib.SMTP_SSL(config["smtp_server"], config["smtp_port"], timeout=30) as server:
            server.login(config["usuario"], config["senha"])
            server.send_message(msg)
        return True
    except Exception as e:
        return False

def gerar_pdf_rm(registro: RegistroRM) -> Optional[bytes]:
    """Gera PDF do RM em memória"""
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
        
        elementos.append(Paragraph("<b>REQUISIÇÃO DE MANUTENÇÃO</b>", 
                                  ParagraphStyle('Titulo', parent=styles["Heading1"], fontSize=16, alignment=1, spaceAfter=12)))
        elementos.append(Paragraph("<b>MF-001 - Luvidarte</b>", 
                                  ParagraphStyle('Subtitulo', parent=styles["Heading2"], fontSize=12, alignment=1, spaceAfter=24)))
        
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
        
        elementos.append(Paragraph("<b>DESCRIÇÃO DO PROBLEMA:</b>", 
                                  ParagraphStyle('SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        elementos.append(Paragraph(registro.problema or "-", styleN))
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>TRABALHO REALIZADO:</b>", 
                                  ParagraphStyle('SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        elementos.append(Paragraph(registro.trabalho or "_________________________", styleN))
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>ANÁLISE DO SERVIÇO:</b>", 
                                  ParagraphStyle('SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
        elementos.append(Paragraph(registro.analise or "_________________________", styleN))
        elementos.append(Spacer(1, 24))
        
        elementos.append(Paragraph("<b>ASSINATURAS:</b>", 
                                  ParagraphStyle('SubtituloSecao', parent=styleN, fontSize=12, spaceAfter=6)))
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
        elementos.append(Paragraph(f"Documento gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", 
                                  ParagraphStyle('Rodape', parent=styleN, fontSize=8, alignment=2)))
        
        doc.build(elementos)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        return None

# ==================================================================================================
# 4. FUNÇÕES DE RENDERIZAÇÃO DOS MÓDULOS AR E RM
# ==================================================================================================

def render_ar():
    """Renderiza o módulo AVISO DE REJEIÇÃO"""
    render_page_header("AVISO DE REJEIÇÃO", f"CQ-018 REV004 · Atualizado {get_horario_brasilia()}", THEME['accent_red'])
    
    # Inicializar session state
    if 'ar_etapa_confirmacao' not in st.session_state:
        st.session_state.ar_etapa_confirmacao = 1
    if 'ar_pdf_bytes' not in st.session_state:
        st.session_state.ar_pdf_bytes = None
    if 'ar_ultimo_registro' not in st.session_state:
        st.session_state.ar_ultimo_registro = None
    
    menu_ar = st.radio("Opções do AR:", ["📝 Novo Registro", "📊 Visualizar Registros", "🔍 Buscar/Editar/Excluir", "📈 Dashboard AR"], 
                      horizontal=True, key="menu_ar_principal")
    
    if menu_ar == "📝 Novo Registro":
        st.subheader("Novo Aviso de Rejeição")
        st.info("⚠️ Data e hora serão preenchidas automaticamente (Horário de Brasília)")
        
        if st.session_state.ar_pdf_bytes and st.session_state.ar_ultimo_registro:
            st.success(f"✅ Registro salvo com sucesso!")
            reg = st.session_state.ar_ultimo_registro
            
            with st.expander("📋 Ver detalhes do registro", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Número:** {reg.numero}")
                    st.write(f"**Data:** {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                    st.write(f"**Turno:** {reg.turno}")
                with col2:
                    st.write(f"**Emissor:** {reg.emissor}")
                    st.write(f"**Referência:** {reg.referencia[:50]}...")
                    st.write(f"**Status:** {reg.status}")
            
            st.download_button(
                label="📥 Baixar PDF",
                data=st.session_state.ar_pdf_bytes,
                file_name=f"AR_{reg.numero}_{sanitize_filename(reg.referencia[:30])}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            if st.button("➕ Novo Registro", use_container_width=True):
                st.session_state.ar_pdf_bytes = None
                st.session_state.ar_ultimo_registro = None
                st.rerun()
        else:
            with st.form("novo_registro_ar"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    proximo = obter_proximo_numero_ar()
                    st.info(f"📌 Próximo número: {proximo}")
                    numero = st.number_input("Número do AR", value=proximo, min_value=1, step=1, disabled=True)
                    turno = st.selectbox("Turno", OPCOES_TURNO_AR)
                with col2:
                    codigo = st.text_input("Código*")
                    emissor = st.text_input("Emissor*")
                    referencia = st.text_area("Referência*", height=80)
                    decisao = st.selectbox("Decisão*", OPCOES_DECISAO_AR)
                with col3:
                    status = st.selectbox("Status*", OPCOES_STATUS_AR)
                    descricao = st.text_area("Descrição do Problema*", height=120)
                    disposicao = st.text_area("Disposição", height=80)
                    data_finalizacao = st.date_input("Data de Finalização", datetime.now())
                
                st.markdown("---")
                st.markdown("### 📚 Biblioteca de Defeitos")
                
                biblioteca_defeitos = carregar_biblioteca_defeitos()
                opcoes_defeitos = [""] + sorted(list(biblioteca_defeitos.keys()))
                
                defeito_selecionado = st.selectbox("Defeito (opcional)", options=opcoes_defeitos)
                
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
                
                submitted = st.form_submit_button("💾 SALVAR REGISTRO", type="primary", use_container_width=True)
                
                if submitted:
                    if not codigo or not emissor or not referencia or not descricao:
                        st.error("❌ Preencha todos os campos obrigatórios (*)")
                    else:
                        agora = get_horario_brasilia_obj()
                        usuario = st.session_state.get('usuario', 'SISTEMA')
                        
                        registro = RegistroAR(
                            numero=numero,
                            data=agora.date(),
                            hora=agora.strftime("%H:%M:%S"),
                            codigo=codigo,
                            emissor=emissor,
                            referencia=referencia,
                            decisao=decisao,
                            descricao=descricao,
                            status=status,
                            disposicao=disposicao,
                            data_finalizacao=data_finalizacao,
                            turno=turno,
                            defeito_biblioteca=defeito_bib,
                            sugestao_biblioteca=sugestao_bib,
                            direcionamento_biblioteca=direcionamento_bib,
                            criado_por=usuario,
                            criado_em=agora
                        )
                        
                        if salvar_registro_ar(registro, eh_alteracao=False):
                            st.success(f"✅ Registro {numero} salvo com sucesso!")
                            pdf_bytes = gerar_pdf_ar(registro)
                            if pdf_bytes:
                                st.session_state.ar_pdf_bytes = pdf_bytes
                                st.session_state.ar_ultimo_registro = registro
                                st.rerun()
    
    elif menu_ar == "📊 Visualizar Registros":
        st.subheader("Registros de Aviso de Rejeição")
        
        with st.spinner("Carregando registros..."):
            registros = carregar_registros_ar()
        
        if registros:
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            with col_f1:
                filtro_status = st.selectbox("Status", ["Todos"] + OPCOES_STATUS_AR)
            with col_f2:
                filtro_decisao = st.selectbox("Decisão", ["Todos"] + OPCOES_DECISAO_AR)
            with col_f3:
                filtro_turno = st.selectbox("Turno", ["Todos"] + OPCOES_TURNO_AR)
            with col_f4:
                filtro_numero = st.number_input("Nº", min_value=0, step=1, value=0)
            
            registros_filtrados = registros
            if filtro_status != "Todos":
                registros_filtrados = [r for r in registros_filtrados if r.status == filtro_status]
            if filtro_decisao != "Todos":
                registros_filtrados = [r for r in registros_filtrados if r.decisao == filtro_decisao]
            if filtro_turno != "Todos":
                registros_filtrados = [r for r in registros_filtrados if r.turno == filtro_turno]
            if filtro_numero > 0:
                registros_filtrados = [r for r in registros_filtrados if r.numero == filtro_numero]
            
            dados = []
            for reg in registros_filtrados[:100]:
                dados.append({
                    "Nº": reg.numero,
                    "Data": reg.data.strftime("%d/%m/%Y") if reg.data else "-",
                    "Hora": reg.hora,
                    "Emissor": reg.emissor,
                    "Referência": reg.referencia[:40] + "..." if len(reg.referencia) > 40 else reg.referencia,
                    "Decisão": reg.decisao,
                    "Status": reg.status,
                    "Turno": reg.turno
                })
            df = pd.DataFrame(dados)
            st.dataframe(df, use_container_width=True, height=400)

def render_rm():
    """Renderiza o módulo REQUISIÇÃO DE MANUTENÇÃO"""
    render_page_header("REQUISIÇÃO DE MANUTENÇÃO", f"MF-001 · Atualizado {get_horario_brasilia()}", THEME['accent_lime'])
    
    # Inicializar session state
    if 'rm_etapa_confirmacao' not in st.session_state:
        st.session_state.rm_etapa_confirmacao = 1
    if 'rm_pdf_bytes' not in st.session_state:
        st.session_state.rm_pdf_bytes = None
    if 'rm_ultimo_registro' not in st.session_state:
        st.session_state.rm_ultimo_registro = None
    
    menu_rm = st.radio("Opções:", ["📝 Nova Requisição", "📊 Visualizar Requisições", "🔍 Buscar/Editar/Excluir", "📈 Dashboard RM"], 
                      horizontal=True, key="menu_rm_principal")
    
    if menu_rm == "📝 Nova Requisição":
        st.subheader("Nova Requisição de Manutenção")
        st.info("⚠️ Data e hora serão preenchidas automaticamente (Horário de Brasília)")
        
        if st.session_state.rm_pdf_bytes and st.session_state.rm_ultimo_registro:
            st.success(f"✅ Requisição salva com sucesso!")
            reg = st.session_state.rm_ultimo_registro
            
            with st.expander("📋 Ver detalhes", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**ID:** {reg.id}")
                    st.write(f"**Data:** {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                    st.write(f"**Equipamento:** {reg.equipamento}")
                with col2:
                    st.write(f"**Emissor:** {reg.emissor}")
                    st.write(f"**Setor Destino:** {reg.setor2}")
                    st.write(f"**Status:** {reg.status}")
            
            st.download_button(
                label="📥 Baixar PDF",
                data=st.session_state.rm_pdf_bytes,
                file_name=f"RM_{reg.id}_{sanitize_filename(reg.equipamento[:30])}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            if st.button("➕ Nova Requisição", use_container_width=True):
                st.session_state.rm_pdf_bytes = None
                st.session_state.rm_ultimo_registro = None
                st.rerun()
        else:
            with st.form("nova_requisicao_rm"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    proximo = obter_proximo_id_rm()
                    st.info(f"📌 Próximo ID: {proximo}")
                    id_reg = st.number_input("ID", value=proximo, min_value=1, step=1, disabled=True)
                    emissor = st.text_input("Emissor*")
                    equipamento = st.text_input("Equipamento*")
                    setor = st.selectbox("Setor*", OPCOES_SETORES_RM)
                with col2:
                    caracter = st.selectbox("Caráter*", OPCOES_CARATER_RM)
                    if "1 -" in caracter:
                        st.error("🚨 **RISCO FÍSICO!** Ação imediata necessária!")
                    elif "2 -" in caracter:
                        st.warning("⚠️ **IMPACTO IMEDIATO!** Resolver em até 4h")
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
                        agora = get_horario_brasilia_obj()
                        usuario = st.session_state.get('usuario', 'SISTEMA')
                        
                        registro = RegistroRM(
                            id=id_reg,
                            data=agora.date(),
                            hora=agora.strftime("%H:%M:%S"),
                            emissor=emissor,
                            equipamento=equipamento,
                            setor=setor,
                            caracter=caracter,
                            setor2=setor2,
                            problema=problema,
                            trabalho=trabalho,
                            analise=analise,
                            status=status,
                            data_finalizacao=data_finalizacao,
                            emissor2=emissor2,
                            criado_por=usuario,
                            criado_em=agora
                        )
                        
                        if salvar_registro_rm(registro, eh_alteracao=False):
                            st.success(f"✅ Requisição {id_reg} salva com sucesso!")
                            pdf_bytes = gerar_pdf_rm(registro)
                            if pdf_bytes:
                                st.session_state.rm_pdf_bytes = pdf_bytes
                                st.session_state.rm_ultimo_registro = registro
                                st.rerun()

# ==================================================================================================
# 5. ADICIONAR ROTEAMENTO NA MAIN (ATUALIZAR A FUNÇÃO MAIN DA PARTE 2)
# ==================================================================================================

"""
ATUALIZAÇÃO DA FUNÇÃO MAIN - ADICIONAR ESTES CASOS:

No roteador da função main(), adicionar:

elif aba_selecionada == 'TÊMPERA':
    render_tempera()
elif aba_selecionada == 'AVISO DE REJEIÇÃO':
    render_ar()
elif aba_selecionada == 'REQUISIÇÃO MANUTENÇÃO':
    render_rm()

"""

# ==================================================================================================
# FIM DA PARTE 3/5
# ==================================================================================================

# ==================================================================================================
# PARTE 4/5 - MÓDULOS FECHAMENTO DE TURNO, MANUTENÇÃO PREVENTIVA E MAPEAMENTO DE HABILIDADES
# ==================================================================================================

# ==================================================================================================
# 1. MÓDULO FECHAMENTO DE TURNO - FUNÇÕES AUXILIARES
# ==================================================================================================

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

def get_turno_por_horario(inicio_str, fim_str, is_sabado=False):
    """
    Determina o turno com base nos horários de início e fim
    Manhã: 06:00 até 14:00
    Tarde: 14:00 até 22:00
    Noite: 22:00 até 06:00 (próximo dia)
    """
    try:
        if not inicio_str or not fim_str:
            return "Não definido"
        
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
            if 360 <= minutos_inicio < 660:
                return "Manhã"
            elif 660 <= minutos_inicio < 960:
                return "Tarde"
            else:
                return "Fora do horário"
        else:
            if 360 <= minutos_inicio < 840:
                return "Manhã"
            elif 840 <= minutos_inicio < 1320:
                return "Tarde"
            elif minutos_inicio >= 1320 or minutos_inicio < 360:
                return "Noite"
            else:
                return "Fora do horário"
    except:
        return "Não definido"

def get_carinha_trs(trs_value):
    if trs_value >= 100:
        return "😊"
    elif trs_value >= 80:
        return "🙂"
    else:
        return "😢"

# ==================================================================================================
# 2. FUNÇÕES DE CARREGAMENTO - FECHAMENTO DE TURNO
# ==================================================================================================

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
        sheet = spreadsheet.worksheet("PRODUÇÕES")
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
                
                trs_bruto = round((produzido_val / meta_val * 100), 1) if meta_val > 0 else 0
                
                is_sabado = False
                if data_registro and hasattr(data_registro, 'weekday'):
                    is_sabado = data_registro.weekday() == 5
                
                inicio = row[3] if len(row) > 3 else ""
                fim = row[4] if len(row) > 4 else ""
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
        sheet = spreadsheet.worksheet("CHECK")
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
        
        sheet = client.open_by_key(ID_PLANILHA_FALTAS).worksheet("Controle de Faltas")
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
    """Carrega ARs e RMs filtrados por data"""
    ars = []
    rms = []
    
    try:
        client = get_gspread_client()
        if client is None:
            return ars, rms
        
        # CARREGAR ARs
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
                            'turno': row[11] if len(row) > 11 else "",
                            'setor_destino': 'Qualidade'
                        })
        except:
            pass
        
        # CARREGAR RMs
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
                            'status': row[11] if len(row) > 11 else "ABERTO"
                        })
        except:
            pass
        
    except Exception as e:
        pass
    
    return ars, rms

# ==================================================================================================
# 3. FUNÇÃO PARA GERAR HTML DO RELATÓRIO (MODO RETRATO)
# ==================================================================================================

def gerar_html_relatorio_fechamento(producoes, ars, rms, data_fechamento, turno_label, 
                                    total_produzido, total_meta, eficiencia, 
                                    total_setup_min, total_manut_min, total_ars, total_rms, 
                                    ars_abertos, rms_abertos, itens_baixa):
    """Gera HTML do relatório para download"""
    data_str = data_fechamento.strftime("%d/%m/%Y")
    
    # Gerar linhas da tabela de produção
    tabela_linhas = ""
    for p in producoes:
        trs = p.get('trs_bruto', 0)
        carinha = get_carinha_trs(trs)
        
        if trs >= 100:
            cor_linha = "#d4edda"
            cor_texto = "#155724"
        elif trs >= 80:
            cor_linha = "#fff3cd"
            cor_texto = "#856404"
        else:
            cor_linha = "#f8d7da"
            cor_texto = "#721c24"
        
        meta_str = f"{p.get('meta', 0):,}".replace(",", ".")
        produzido_str = f"{p.get('produzido', 0):,}".replace(",", ".")
        referencia = p.get('referencia', '-')
        if len(referencia) > 20:
            referencia = referencia[:18] + '...'
        
        tabela_linhas += f"""
        <tr style="background-color: {cor_linha}; color: {cor_texto}; font-size: 11px;">
            <td style="padding: 4px 6px; border: 1px solid #ddd; text-align: center;">{p.get('data', '').strftime('%d/%m/%Y') if p.get('data') else '-'}</td>
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
    
    # Gerar tabela de ARs e RMs
    tabela_ars_rms = ""
    todos_docs = ars + rms
    if todos_docs:
        for doc in todos_docs:
            tipo = doc.get('tipo', '')
            status = str(doc.get('status', '')).upper().strip()
            
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
            else:
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
    
    total_produzido_str = f"{total_produzido:,}".replace(",", ".")
    total_meta_str = f"{total_meta:,}".replace(",", ".")
    cor_eficiencia = "#28a745" if eficiencia >= 85 else "#ffc107" if eficiencia >= 70 else "#dc3545"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Resumo Produção - {data_str}</title>
        <style>
            @page {{ size: portrait; margin: 10mm 10mm 10mm 10mm; }}
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 10px; background-color: white; font-size: 11px; }}
            .container {{ max-width: 100%; margin: 0 auto; background-color: white; }}
            .header {{
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                padding: 12px 20px;
                border-radius: 8px;
                margin-bottom: 12px;
                color: white;
            }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }}
            .header .subtitle {{ font-size: 16px; color: #a0aec0; margin-top: 4px; font-weight: bold; }}
            .section-title {{
                font-size: 15px;
                font-weight: 700;
                margin: 12px 0 8px 0;
                padding-bottom: 5px;
                border-bottom: 2px solid #e0e0e0;
            }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 10px; }}
            table th {{
                background-color: #2c3e50;
                color: white;
                padding: 5px 4px;
                border: 1px solid #2c3e50;
                text-align: center;
                font-size: 10px;
                font-weight: 700;
            }}
            table td {{ padding: 4px 4px; border: 1px solid #ddd; text-align: center; }}
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
            .card .label {{ font-size: 9px; color: #666; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }}
            .card .value {{ font-size: 18px; font-weight: 700; margin-top: 2px; color: #1a1a2e; }}
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
            .exec-card .title {{ font-weight: 700; font-size: 12px; margin-bottom: 4px; }}
            .exec-card .line {{ font-size: 10px; padding: 1px 0; }}
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
            @media print {{
                body {{ margin: 5mm; padding: 0; }}
                .header {{ background: #1a1a2e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                .card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                .exec-card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                table th {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 RESUMO DO DIA</h1>
                <div class="subtitle">{data_str} • TURNO: {turno_label}</div>
            </div>
            
            <div class="section-title">📋 REGISTRO DE PRODUÇÃO</div>
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Referência</th>
                        <th>Início</th>
                        <th>Fim</th>
                        <th>Meta</th>
                        <th>Produzido</th>
                        <th>Setup</th>
                        <th>Manut.</th>
                        <th>TRS Bruto</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {tabela_linhas}
                </tbody>
            </table>
            
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
            
            <table>
                <thead>
                    <tr>
                        <th>Tipo</th>
                        <th>Nº</th>
                        <th>Ref. (AR) / Equip. (RM)</th>
                        <th>Equip. (RM) / Ref. (AR)</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {tabela_ars_rms}
                </tbody>
            </table>
            
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
                <div class="data">{data_str} • Luvidarte TRS Dashboard</div>
            </div>
            
            <div class="footer">
                Relatório gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ==================================================================================================
# 4. RENDERIZAÇÃO DO MÓDULO FECHAMENTO DE TURNO
# ==================================================================================================

def render_fechamento_turno():
    """Renderiza o módulo FECHAMENTO DE TURNO"""
    render_page_header("FECHAMENTO DE TURNO", f"Controle de Produção · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])
    
    # Interface
    col_data1, col_data2, col_data3 = st.columns([1, 1, 2])
    
    with col_data1:
        data_fechamento = st.date_input("Data do Fechamento", value=datetime.now().date(), key="fechamento_data")
    
    with col_data2:
        is_sabado = data_fechamento.weekday() == 5
        if is_sabado:
            opcoes_turno = ["Todos", "Manhã", "Tarde"]
        else:
            opcoes_turno = ["Todos", "Manhã", "Tarde", "Noite"]
        turno_selecionado = st.selectbox("Turno", options=opcoes_turno, key="turno_selecionado_rel")
    
    with col_data3:
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            gerar_resumo = st.button("📊 Gerar Resumo", use_container_width=True, type="primary")
        with col_btn2:
            if st.button("🔄 Atualizar", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # Carregar dados
    with st.spinner("Carregando dados do Google Sheets..."):
        producoes = carregar_producoes_fechamento(data_fechamento)
        checklists, checklists_detalhes = carregar_checklists_fechamento(data_fechamento)
        faltas = carregar_faltas_fechamento(data_fechamento)
        ars, rms = carregar_ars_rms_fechamento(data_fechamento)
    
    if gerar_resumo:
        # Filtrar produções por turno
        if turno_selecionado != "Todos":
            producoes_filtradas = [p for p in producoes if p.get('turno') == turno_selecionado]
        else:
            producoes_filtradas = producoes.copy()
        
        # Calcular totais
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
        
        # Gerar relatório
        turno_label = "GERAL" if turno_selecionado == "Todos" else turno_selecionado.upper()
        html_content = gerar_html_relatorio_fechamento(
            producoes_filtradas, ars, rms, data_fechamento, turno_label,
            total_produzido, total_meta, eficiencia, total_setup_min, total_manut_min,
            total_ars, total_rms, ars_abertos, rms_abertos, itens_baixa
        )
        
        st.download_button(
            label="📥 Baixar Relatório (HTML)",
            data=html_content,
            file_name=f"resumo_producao_{data_fechamento.strftime('%Y%m%d')}_{turno_label}.html",
            mime="text/html",
            use_container_width=True,
            type="primary"
        )
        
        st.markdown("<hr>", unsafe_allow_html=True)
    
    # Dashboard rápido
    st.markdown("### 📊 Resumo Rápido do Dia")
    
    total_produzido = sum(p.get('produzido', 0) or 0 for p in producoes)
    total_meta = sum(p.get('meta', 0) or 0 for p in producoes)
    eficiencia = (total_produzido / total_meta * 100) if total_meta > 0 else 0
    total_setup_min = sum(str_time_to_minutes_ft(p.get('setup', '')) for p in producoes)
    total_manut_min = sum(str_time_to_minutes_ft(p.get('manut', '')) for p in producoes)
    
    col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
    with col_k1: st.metric("📦 Total Produzido", f"{total_produzido:,}".replace(",", "."))
    with col_k2: st.metric("🎯 Meta Total", f"{total_meta:,}".replace(",", "."))
    with col_k3:
        cor_eficiencia = "🟢" if eficiencia >= 85 else "🟡" if eficiencia >= 70 else "🔴"
        st.metric(f"{cor_eficiencia} Eficiência", f"{eficiencia:.1f}%")
    with col_k4: st.metric("🔧 Setup Total", minutos_para_horas_str(total_setup_min))
    with col_k5: st.metric("⚙️ Manutenção Total", minutos_para_horas_str(total_manut_min))

# ==================================================================================================
# 5. MÓDULO MANUTENÇÃO PREVENTIVA - DATACLASSES E FUNÇÕES
# ==================================================================================================

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
    # Campos de auditoria
    criado_por: str = ""
    criado_em: Optional[datetime] = None
    alterado_por: str = ""
    alterado_em: Optional[datetime] = None

@dataclass
class CadastroMaquina:
    id: Optional[str] = None
    maquina: str = ""
    setor: str = ""

def calcular_status_preventiva(data_agendada: date, analise: str, eletrica: bool, mecanica: bool) -> str:
    hoje = datetime.now().date()
    if analise and analise.strip() and eletrica and mecanica:
        return "FINALIZADO"
    elif data_agendada < hoje:
        return "EM ATRASO"
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
    except:
        return None

@retry_on_quota()
@st.cache_data(ttl=300)
def carregar_preventivas(filtros: Dict[str, Any] = None) -> List[RegistroPreventiva]:
    registros = []
    try:
        client = get_gspread_client()
        if client is None:
            return registros
        
        spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
        sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
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
            except:
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
    except:
        return registros

@retry_on_quota()
@st.cache_data(ttl=600)
def carregar_cadastro_maquinas() -> List[CadastroMaquina]:
    registros = []
    try:
        client = get_gspread_client()
        if client is None:
            return registros
        
        spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
        
        try:
            sheet = spreadsheet.worksheet(ABA_CADASTRO_PREVENTIVA)
        except:
            sheet = spreadsheet.add_worksheet(title=ABA_CADASTRO_PREVENTIVA, rows=1000, cols=10)
            cabecalho = ["ID", "MÁQUINA", "SETOR"]
            sheet.append_row(cabecalho)
            return registros
        
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return registros
        
        for row in todos_dados[1:]:
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
            except:
                continue
        
        return registros
    except:
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
        agora = get_horario_brasilia_obj()
        usuario = st.session_state.get('usuario', 'SISTEMA')
        
        if not registro.criado_por:
            registro.criado_por = usuario
            registro.criado_em = agora
        
        dados = [
            registro.id, data_formatada, registro.maquina, registro.setor,
            registro.descricao, registro.execucao, registro.analise, registro.status,
            str(registro.eletrica).upper(), str(registro.mecanica).upper(), str(registro.liberado).upper(),
            registro.criado_por, registro.criado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.criado_em else ""
        ]
        
        sheet.append_row(dados)
        st.cache_data.clear()
        return True, "✅ Manutenção salva com sucesso!"
    except:
        return False, "❌ Erro ao salvar"

def atualizar_preventiva(registro: RegistroPreventiva) -> tuple:
    try:
        client = get_gspread_client()
        if client is None:
            return False, "❌ Erro ao conectar ao Google Sheets"
        
        spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
        sheet = spreadsheet.worksheet(ABA_PREVENTIVA)
        
        registro.liberado = registro.eletrica and registro.mecanica
        
        if registro.data:
            registro.status = calcular_status_preventiva(registro.data.date(), registro.analise, registro.eletrica, registro.mecanica)
        
        linha = encontrar_linha_preventiva(registro.id, registro.data.date())
        
        if not linha:
            return False, f"❌ Registro não encontrado: ID={registro.id}"
        
        agora = get_horario_brasilia_obj()
        usuario = st.session_state.get('usuario', 'SISTEMA')
        registro.alterado_por = usuario
        registro.alterado_em = agora
        
        data_formatada = registro.data.strftime("%d/%m/%Y") if registro.data else ""
        
        dados = [
            registro.id, data_formatada, registro.maquina, registro.setor,
            registro.descricao, registro.execucao, registro.analise, registro.status,
            str(registro.eletrica).upper(), str(registro.mecanica).upper(), str(registro.liberado).upper(),
            registro.criado_por or "", registro.criado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.criado_em else "",
            registro.alterado_por, registro.alterado_em.strftime("%d/%m/%Y %H:%M:%S") if registro.alterado_em else ""
        ]
        
        for col, valor in enumerate(dados, start=1):
            sheet.update_cell(linha, col, valor)
        
        st.cache_data.clear()
        return True, "✅ Registro atualizado com sucesso!"
    except:
        return False, "❌ Erro ao atualizar"

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
    except:
        return False, "❌ Erro ao excluir"

def salvar_cadastro_maquina(registro: CadastroMaquina, eh_alteracao: bool = False) -> tuple:
    try:
        client = get_gspread_client()
        if client is None:
            return False, "❌ Não foi possível conectar ao Google Sheets"
        
        spreadsheet = client.open_by_key(ID_PLANILHA_PREVENTIVA)
        
        try:
            sheet = spreadsheet.worksheet(ABA_CADASTRO_PREVENTIVA)
        except:
            sheet = spreadsheet.add_worksheet(title=ABA_CADASTRO_PREVENTIVA, rows=1000, cols=10)
            cabecalho = ["ID", "MÁQUINA", "SETOR"]
            sheet.append_row(cabecalho)
        
        dados = [registro.id, registro.maquina, registro.setor]
        
        if eh_alteracao:
            try:
                cell = sheet.find(registro.id, in_column=1)
                if cell:
                    for col, valor in enumerate(dados, start=1):
                        sheet.update_cell(cell.row, col, valor)
                else:
                    sheet.append_row(dados)
            except:
                sheet.append_row(dados)
        else:
            try:
                cell = sheet.find(registro.id, in_column=1)
                if cell:
                    return False, f"❌ ID {registro.id} já existe!"
            except:
                pass
            sheet.append_row(dados)
        
        st.cache_data.clear()
        return True, "✅ Cadastro salvo com sucesso!"
    except:
        return False, "❌ Erro ao salvar cadastro"

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
    except:
        return False, "❌ Erro ao excluir cadastro"

# ==================================================================================================
# 6. RENDERIZAÇÃO DO MÓDULO MANUTENÇÃO PREVENTIVA
# ==================================================================================================

def render_manutencao_preventiva():
    """Renderiza o módulo MANUTENÇÃO PREVENTIVA"""
    render_page_header("MANUTENÇÃO PREVENTIVA", f"Plano de Manutenção · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])
    
    # Inicializar session state
    if 'mes_calendario' not in st.session_state:
        st.session_state.mes_calendario = datetime.now().replace(day=1)
    if 'editando_registro' not in st.session_state:
        st.session_state.editando_registro = None
    
    tab_agenda, tab_cadastro = st.tabs(["📅 Agenda de Manutenção", "🏭 Cadastro de Máquinas"])
    
    with tab_agenda:
        st.subheader("📅 Plano de Manutenção Preventiva")
        
        # Calendário
        st.markdown("### 📆 Calendário Mensal")
        
        col_cal1, col_cal2, col_cal3 = st.columns([1, 3, 1])
        with col_cal1:
            if st.button("◀ Mês Anterior"):
                st.session_state.mes_calendario = st.session_state.mes_calendario - timedelta(days=1)
                st.session_state.mes_calendario = st.session_state.mes_calendario.replace(day=1)
                st.rerun()
        with col_cal2:
            st.markdown(f"<h3 style='text-align: center;'>{st.session_state.mes_calendario.strftime('%B %Y')}</h3>", unsafe_allow_html=True)
        with col_cal3:
            if st.button("Próximo Mês ▶"):
                next_month = st.session_state.mes_calendario.replace(day=28) + timedelta(days=4)
                st.session_state.mes_calendario = next_month.replace(day=1)
                st.rerun()
        
        # Carregar registros do mês
        with st.spinner("Carregando agenda..."):
            registros = carregar_preventivas()
        
        eventos_por_data = {}
        for reg in registros:
            if reg.data:
                data_str = reg.data.strftime("%Y-%m-%d")
                if data_str not in eventos_por_data:
                    eventos_por_data[data_str] = []
                eventos_por_data[data_str].append(reg)
        
        # Exibir calendário simplificado
        import calendar
        cal = calendar.monthcalendar(st.session_state.mes_calendario.year, st.session_state.mes_calendario.month)
        dias_semana = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
        
        cols_header = st.columns(7)
        for i, dia in enumerate(dias_semana):
            with cols_header[i]:
                st.markdown(f"<div style='text-align:center;font-weight:bold;padding:8px;background:#f0f0f0;border-radius:5px;'>{dia}</div>", unsafe_allow_html=True)
        
        for semana in cal:
            cols = st.columns(7)
            for i, dia in enumerate(semana):
                with cols[i]:
                    if dia == 0:
                        st.markdown("<div style='background:#f5f5f5;padding:10px;border-radius:5px;'>&nbsp;</div>", unsafe_allow_html=True)
                    else:
                        data_atual = st.session_state.mes_calendario.replace(day=dia)
                        data_str = data_atual.strftime("%Y-%m-%d")
                        eventos = eventos_por_data.get(data_str, [])
                        
                        bg_color = "#fff3cd" if data_atual.date() == datetime.now().date() else "#fafafa"
                        
                        html_dia = f"<div style='background:{bg_color};padding:8px;border-radius:5px;min-height:60px;border:1px solid #e0e0e0;'>"
                        html_dia += f"<div style='font-weight:bold;font-size:14px;'>{dia}</div>"
                        
                        for evento in eventos[:2]:
                            cor = "#0078D4" if evento.status == "PROGRAMADO" else "#FFB900" if evento.status == "EM EXECUÇÃO" else "#E81123" if evento.status == "EM ATRASO" else "#107C10"
                            html_dia += f"<div style='font-size:9px;background:{cor};color:white;padding:2px 4px;border-radius:3px;margin:2px 0;'>🔧 {evento.maquina[:12]}</div>"
                        
                        if len(eventos) > 2:
                            html_dia += f"<div style='font-size:9px;color:#666;'>+{len(eventos)-2}</div>"
                        
                        html_dia += "</div>"
                        st.markdown(html_dia, unsafe_allow_html=True)
        
        # CRUD
        st.markdown("---")
        st.subheader("✏️ Gerenciar Manutenções")
        
        acao = st.radio("Ação:", ["➕ Nova Manutenção", "✏️ Editar Manutenção", "🗑️ Excluir Manutenção"], horizontal=True)
        
        if acao == "➕ Nova Manutenção":
            with st.form("nova_preventiva"):
                cadastros = carregar_cadastro_maquinas()
                if not cadastros:
                    st.warning("⚠️ Nenhuma máquina cadastrada.")
                    st.form_submit_button("💾 SALVAR", disabled=True)
                else:
                    opcoes = [f"{c.id} - {c.maquina}" for c in cadastros]
                    selecao = st.selectbox("Máquina", opcoes)
                    if selecao:
                        id_selecionado = selecao.split(" - ")[0]
                        maquina_selecionada = next((c for c in cadastros if c.id == id_selecionado), None)
                        
                        if maquina_selecionada:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.text_input("ID", value=maquina_selecionada.id, disabled=True)
                                st.text_input("Máquina", value=maquina_selecionada.maquina, disabled=True)
                                st.text_input("Setor", value=maquina_selecionada.setor, disabled=True)
                                data_agendada = st.date_input("Data Agendada*", value=datetime.now().date())
                            with col2:
                                descricao = st.text_area("Descrição do Serviço*", height=100)
                                execucao = st.text_input("Responsável pela Execução")
                                analise = st.text_area("Análise / Resultado", height=80)
                            
                            if st.form_submit_button("💾 SALVAR MANUTENÇÃO", type="primary"):
                                if not descricao:
                                    st.error("❌ Preencha a descrição!")
                                else:
                                    novo = RegistroPreventiva(
                                        id=maquina_selecionada.id,
                                        data=datetime.combine(data_agendada, datetime.min.time()),
                                        maquina=maquina_selecionada.maquina,
                                        setor=maquina_selecionada.setor,
                                        descricao=descricao,
                                        execucao=execucao,
                                        analise=analise
                                    )
                                    sucesso, msg = salvar_preventiva(novo)
                                    if sucesso:
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
        
        elif acao == "✏️ Editar Manutenção":
            if st.session_state.editando_registro:
                reg = st.session_state.editando_registro
                st.success(f"✅ Editando: {reg.maquina} - {reg.data.strftime('%d/%m/%Y') if reg.data else '-'}")
                
                with st.form("form_editar_preventiva"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("ID", value=reg.id, disabled=True)
                        st.text_input("Máquina", value=reg.maquina, disabled=True)
                        st.text_input("Setor", value=reg.setor, disabled=True)
                        data_edit = st.date_input("Data", value=reg.data.date() if reg.data else datetime.now().date())
                    with col2:
                        descricao_edit = st.text_area("Descrição", value=reg.descricao, height=100)
                        execucao_edit = st.text_input("Responsável", value=reg.execucao)
                        analise_edit = st.text_area("Análise", value=reg.analise, height=80)
                    
                    st.markdown("---")
                    st.markdown("### 🔓 Liberações")
                    col_check1, col_check2 = st.columns(2)
                    with col_check1:
                        eletrica_check = st.checkbox("✅ Elétrica", value=reg.eletrica)
                    with col_check2:
                        mecanica_check = st.checkbox("✅ Mecânica", value=reg.mecanica)
                    
                    if st.form_submit_button("💾 SALVAR ALTERAÇÕES", type="primary"):
                        reg_atualizado = RegistroPreventiva(
                            id=reg.id,
                            data=datetime.combine(data_edit, datetime.min.time()),
                            maquina=reg.maquina,
                            setor=reg.setor,
                            descricao=descricao_edit,
                            execucao=execucao_edit,
                            analise=analise_edit,
                            eletrica=eletrica_check,
                            mecanica=mecanica_check
                        )
                        sucesso, msg = atualizar_preventiva(reg_atualizado)
                        if sucesso:
                            st.success(msg)
                            st.session_state.editando_registro = None
                            st.rerun()
                        else:
                            st.error(msg)
                
                if st.button("❌ Cancelar Edição"):
                    st.session_state.editando_registro = None
                    st.rerun()
            else:
                with st.form("buscar_editar_preventiva"):
                    id_busca = st.text_input("ID da Máquina")
                    data_busca = st.date_input("Data", value=datetime.now().date())
                    if st.form_submit_button("🔍 Buscar"):
                        registros_busca = carregar_preventivas({"id": id_busca})
                        for r in registros_busca:
                            if r.data and r.data.date() == data_busca:
                                st.session_state.editando_registro = r
                                st.rerun()
                                break
                        else:
                            st.error("❌ Registro não encontrado")
        
        elif acao == "🗑️ Excluir Manutenção":
            with st.form("excluir_preventiva"):
                id_busca = st.text_input("ID da Máquina")
                data_busca = st.date_input("Data", value=datetime.now().date())
                
                if st.form_submit_button("🔍 Buscar e Excluir", type="primary"):
                    registros_busca = carregar_preventivas({"id": id_busca})
                    encontrado = False
                    for r in registros_busca:
                        if r.data and r.data.date() == data_busca:
                            encontrado = True
                            st.warning(f"⚠️ Excluir: {r.maquina} - {r.data.strftime('%d/%m/%Y')}")
                            if st.button("🗑️ CONFIRMAR EXCLUSÃO", type="primary"):
                                sucesso, msg = excluir_preventiva(r.id, r.data.date())
                                if sucesso:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            break
                    if not encontrado:
                        st.error("❌ Registro não encontrado")
    
    with tab_cadastro:
        st.subheader("🏭 Cadastro de Máquinas")
        
        cadastros = carregar_cadastro_maquinas()
        if cadastros:
            df_cadastro = pd.DataFrame([{"ID": c.id, "Máquina": c.maquina, "Setor": c.setor} for c in cadastros])
            st.dataframe(df_cadastro, use_container_width=True, height=300)
        
        acao_cadastro = st.radio("Ação:", ["➕ Nova Máquina", "✏️ Editar Máquina", "🗑️ Excluir Máquina"], horizontal=True)
        
        if acao_cadastro == "➕ Nova Máquina":
            with st.form("nova_maquina"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    id_novo = st.text_input("ID*")
                with col2:
                    maquina_nova = st.text_input("Nome da Máquina*")
                with col3:
                    setor_novo = st.selectbox("Setor", OPCOES_SETORES_PREVENTIVA)
                
                if st.form_submit_button("💾 CADASTRAR", type="primary"):
                    if not id_novo or not maquina_nova:
                        st.error("❌ Preencha ID e Nome")
                    else:
                        sucesso, msg = salvar_cadastro_maquina(CadastroMaquina(id=id_novo.upper(), maquina=maquina_nova, setor=setor_novo))
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

# ==================================================================================================
# 7. MÓDULO MAPEAMENTO DE HABILIDADES
# ==================================================================================================

@retry_on_quota()
@st.cache_data(ttl=300)
def carregar_dados_habilidades():
    """Carrega dados da planilha de Habilidades"""
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame(), [], []
        
        spreadsheet = client.open_by_key(ID_PLANILHA_HABILIDADES)
        
        try:
            sheet = spreadsheet.worksheet(ABA_HABILIDADES)
        except:
            return pd.DataFrame(), [], []
        
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return pd.DataFrame(), [], []
        
        cabecalho = todos_dados[0]
        valores = todos_dados[1:]
        df = pd.DataFrame(valores, columns=cabecalho)
        df.columns = df.columns.str.strip().str.upper()
        df.columns = df.columns.str.replace(' ', '_')
        df.columns = df.columns.str.replace('Ç', 'C')
        df.columns = df.columns.str.replace('Ã', 'A')
        df.columns = df.columns.str.replace('Á', 'A')
        df.columns = df.columns.str.replace('É', 'E')
        df.columns = df.columns.str.replace('Í', 'I')
        df.columns = df.columns.str.replace('Ó', 'O')
        df.columns = df.columns.str.replace('Ú', 'U')
        
        hard_skills = [
            'LER_PLANTAS_TECNICAS', 'INSPECAO_VISUAL', 'CHOQUE_TERMICO', 'MENTORIA',
            'NORMAS_QUALIDADE', 'SITEMA_ERP', 'EXPEDICAO', 'TRS', 'OPERACAO_MAQUINA', 'PLANTAS_TECNICAS'
        ]
        soft_skills = [
            'COMUNICACAO', 'LIDERANCA', 'TRABALHO_EQUIPE', 'CRIATIVIDADE',
            'RESOLUCAO_PROBLEMAS', 'ADAPTABILIDADE', 'AGILIDADE', 'INTELIGENCIA_EMOCIONAL',
            'ASSIDUIDADE', 'PONTUALIDADE', 'PROATIVIDADE'
        ]
        
        colunas_esperadas = ['COLABORADOR', 'FUNCAO', 'TURNO', 'SETOR'] + hard_skills + soft_skills
        colunas_existentes = [col for col in colunas_esperadas if col in df.columns]
        
        if not colunas_existentes:
            return pd.DataFrame(), [], []
        
        df = df[colunas_existentes]
        
        for col in hard_skills + soft_skills:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                df[col] = df[col].clip(0, 10)
        
        if 'COLABORADOR' in df.columns:
            df = df[df['COLABORADOR'].astype(str).str.strip() != '']
            df = df[df['COLABORADOR'].astype(str).str.strip() != 'nan']
        
        hard_existentes = [col for col in hard_skills if col in df.columns]
        soft_existentes = [col for col in soft_skills if col in df.columns]
        
        return df, hard_existentes, soft_existentes
        
    except Exception as e:
        return pd.DataFrame(), [], []

def render_habilidades():
    """Renderiza o módulo MAPEAMENTO DE HABILIDADES"""
    render_page_header("MAPEAMENTO DE HABILIDADES", f"Desenvolvimento de Pessoas · Atualizado {get_horario_brasilia()}", THEME['accent_purple'])
    
    with st.spinner("Carregando dados..."):
        df, hard_cols, soft_cols = carregar_dados_habilidades()
    
    if df.empty:
        st.warning("⚠️ Não foi possível carregar os dados.")
        st.stop()
    
    with st.sidebar:
        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
            color:{THEME['accent_purple']};margin:20px 0 10px;border-top:1px solid {THEME['border_bright']};padding-top:16px'>
            ▸ Filtros · Habilidades
        </div>
        """, unsafe_allow_html=True)
        
        if 'COLABORADOR' in df.columns:
            colaboradores = sorted([str(c) for c in df['COLABORADOR'].dropna().unique() if str(c).strip()])
            colaborador_selecionado = st.selectbox("👤 Colaborador", options=["(Todos)"] + colaboradores)
        else:
            colaborador_selecionado = "(Todos)"
    
    df_filtrado = df.copy()
    if colaborador_selecionado != "(Todos)":
        df_filtrado = df_filtrado[df_filtrado['COLABORADOR'].astype(str).str.strip() == colaborador_selecionado]
    
    # KPIs
    total_colaboradores = len(df_filtrado)
    media_hard = 0
    media_soft = 0
    
    if hard_cols and total_colaboradores > 0:
        media_hard = df_filtrado[hard_cols].mean().mean()
    if soft_cols and total_colaboradores > 0:
        media_soft = df_filtrado[soft_cols].mean().mean()
    
    col_k1, col_k2, col_k3 = st.columns(3)
    with col_k1: st.metric("👥 Colaboradores", f"{total_colaboradores:,}")
    with col_k2: st.metric("🛠️ Média Hard Skills", f"{media_hard:.1f}/10")
    with col_k3: st.metric("💡 Média Soft Skills", f"{media_soft:.1f}/10")
    
    # Matriz de habilidades
    st.markdown("### 📊 Matriz de Habilidades")
    
    colunas_base = ['COLABORADOR', 'FUNCAO', 'TURNO', 'SETOR']
    colunas_base_existentes = [c for c in colunas_base if c in df_filtrado.columns]
    
    df_exibicao = df_filtrado[colunas_base_existentes].copy()
    
    rename_map = {'COLABORADOR': 'Colaborador', 'FUNCAO': 'Função', 'TURNO': 'Turno', 'SETOR': 'Setor'}
    df_exibicao = df_exibicao.rename(columns={k: v for k, v in rename_map.items() if k in df_exibicao.columns})
    
    if hard_cols:
        df_exibicao['Média Hard Skills'] = df_filtrado[hard_cols].mean(axis=1).round(1)
    if soft_cols:
        df_exibicao['Média Soft Skills'] = df_filtrado[soft_cols].mean(axis=1).round(1)
    
    if 'Colaborador' in df_exibicao.columns:
        df_exibicao = df_exibicao.sort_values('Colaborador')
    
    st.dataframe(df_exibicao, use_container_width=True, height=400, hide_index=True)

# ==================================================================================================
# 8. ATUALIZAÇÃO DO ROTEADOR MAIN
# ==================================================================================================

"""
No roteador da função main(), adicionar após os módulos existentes:

elif aba_selecionada == 'FECHAMENTO TURNO':
    render_fechamento_turno()
elif aba_selecionada == 'MANUTENÇÃO PREVENTIVA':
    render_manutencao_preventiva()
elif aba_selecionada == 'MAPEAMENTO DE HABILIDADES':
    render_habilidades()
"""

# ==================================================================================================
# FIM DA PARTE 4/5
# ==================================================================================================

# ==================================================================================================
# PARTE 5/5 - MÓDULOS FERRAMENTARIA, PRÊMIO PRENSADOS, REPASSES DE PRODUÇÃO E CONTROLE DO FORNO
# ==================================================================================================

# ==================================================================================================
# 1. MÓDULO FERRAMENTARIA - DATACLASS E FUNÇÕES
# ==================================================================================================

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
    except:
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
    except:
        return False, "❌ Erro ao salvar"

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

def listar_conteudo_drive(pasta_id: str) -> Dict[str, Any]:
    resultado = {"pastas": [], "arquivos": [], "erro": None, "nome_pasta": ""}
    
    if not pasta_id or pasta_id.strip() == "":
        resultado["erro"] = "ID da pasta vazio"
        return resultado
    
    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials
        
        try:
            if 'gcp_service_account' in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=['https://www.googleapis.com/auth/drive.readonly']
                )
            else:
                return resultado
        except:
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
            fields="files(id, name, mimeType, webViewLink, size, modifiedTime)",
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
                web_link = item.get('webViewLink')
                if not web_link:
                    web_link = f"https://drive.google.com/file/d/{item.get('id')}/view"
                
                resultado["arquivos"].append({
                    "nome": nome,
                    "id": item.get('id'),
                    "link": web_link,
                    "tipo": "arquivo",
                    "extensao": extensao
                })
        
        resultado["pastas"] = sorted(resultado["pastas"], key=lambda x: x["nome"].lower())
        resultado["arquivos"] = sorted(resultado["arquivos"], key=lambda x: x["nome"].lower())
        
    except Exception as e:
        resultado["erro"] = str(e)
    
    return resultado

# ==================================================================================================
# 2. RENDERIZAÇÃO DO MÓDULO FERRAMENTARIA
# ==================================================================================================

def render_ferramentaria():
    """Renderiza o módulo FERRAMENTARIA"""
    render_page_header("🛠️ FERRAMENTARIA", f"Gerenciamento de Moldes · Atualizado {get_horario_brasilia()}", THEME['accent_cyan'])
    
    # Inicializar session state
    if 'caminho_navegacao' not in st.session_state:
        st.session_state.caminho_navegacao = []
    if 'ferramental_selecionado' not in st.session_state:
        st.session_state.ferramental_selecionado = None
    if 'mostrar_formulario_novo' not in st.session_state:
        st.session_state.mostrar_formulario_novo = False
    
    def resetar_navegacao():
        st.session_state.caminho_navegacao = []
    
    def navegar_para_pasta(nome_pasta: str, pasta_id: str):
        st.session_state.caminho_navegacao.append({"nome": nome_pasta, "id": pasta_id})
    
    def voltar_nivel(indice: int):
        st.session_state.caminho_navegacao = st.session_state.caminho_navegacao[:indice]
    
    # Carregar dados
    with st.spinner("🔄 Carregando dados..."):
        dados_dict = carregar_ferramentais_dict()
        todos_ferramentais = [dict_para_ferramental(d) for d in dados_dict]
    
    # Filtros
    st.markdown("### 🔍 Filtros")
    
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
    
    # Aplicar filtros
    filtros = {}
    if filtro_pcp != "(Todos)": filtros['pcp'] = filtro_pcp
    if filtro_cliente != "(Todos)": filtros['cliente'] = filtro_cliente
    if filtro_descricao and filtro_descricao.strip(): filtros['descricao'] = filtro_descricao.strip()
    
    if filtros:
        ferramentais_filtrados = [dict_para_ferramental(d) for d in carregar_ferramentais_dict(filtros)]
    else:
        ferramentais_filtrados = todos_ferramentais
    
    # Botão Novo Ferramental
    col_count, col_add = st.columns([3, 1])
    with col_count:
        st.markdown(f"📊 <b>{len(ferramentais_filtrados)}</b> ferramentais encontrados", unsafe_allow_html=True)
    with col_add:
        if st.button("➕ NOVO FERRAMENTAL", type="primary", use_container_width=True):
            st.session_state.mostrar_formulario_novo = True
    
    # Lista de ferramentais
    if ferramentais_filtrados:
        for f in ferramentais_filtrados:
            cols = st.columns([1, 1.2, 1.2, 3, 1, 0.8])
            with cols[0]: st.write(f.id)
            with cols[1]: st.write(f.pcp)
            with cols[2]: st.write(f.cliente)
            with cols[3]: st.write(f.descricao[:40] + "..." if len(f.descricao) > 40 else f.descricao)
            with cols[4]: st.write(f.data_inicial)
            with cols[5]:
                if st.button("📊", key=f"btn_ver_{f.id}"):
                    resetar_navegacao()
                    st.session_state.ferramental_selecionado = f.id
                    st.rerun()
            st.divider()
        
        # Detalhes do ferramental selecionado
        if st.session_state.ferramental_selecionado:
            selecionado = next((f for f in ferramentais_filtrados if f.id == st.session_state.ferramental_selecionado), None)
            if selecionado:
                st.markdown(f"""
                <div style="background:{THEME['bg_card']};border-radius:12px;padding:20px;border:1px solid {THEME['border_bright']};margin-top:20px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                        <div>
                            <div style="font-size:20px;font-weight:700;">🔧 {selecionado.descricao or 'Sem descrição'}</div>
                            <div style="font-size:13px;color:{THEME['text_muted']};">ID: {selecionado.id} | PCP: {selecionado.pcp} | Cliente: {selecionado.cliente}</div>
                        </div>
                        <div style="font-size:13px;color:{THEME['text_muted']};">📅 {selecionado.data_inicial or 'N/A'}</div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Documentos
                st.markdown("### 📄 Documentação")
                col1, col2 = st.columns(2)
                with col1:
                    if selecionado.avaliacao_inicial:
                        st.markdown(f"✅ [Avaliação Inicial]({selecionado.avaliacao_inicial})")
                    else:
                        st.markdown("❌ Avaliação Inicial")
                    if selecionado.desenho:
                        st.markdown(f"✅ [Desenho]({selecionado.desenho})")
                    else:
                        st.markdown("❌ Desenho")
                with col2:
                    if selecionado.gabarito:
                        st.markdown(f"✅ [Gabarito]({selecionado.gabarito})")
                    else:
                        st.markdown("❌ Gabarito")
                    if selecionado.plano_controle:
                        st.markdown(f"✅ [Plano Controle]({selecionado.plano_controle})")
                    else:
                        st.markdown("❌ Plano Controle")
                
                # Manutenção - explorador Google Drive
                if selecionado.manutencao:
                    st.markdown("### 🔧 Manutenções")
                    pasta_raiz_id = extrair_id_drive(selecionado.manutencao)
                    
                    if st.session_state.caminho_navegacao:
                        pasta_atual_id = st.session_state.caminho_navegacao[-1]["id"]
                    else:
                        pasta_atual_id = pasta_raiz_id
                    
                    # Breadcrumb
                    breadcrumb = "📂 "
                    if st.button("🏠 Raiz"):
                        resetar_navegacao()
                        st.rerun()
                    
                    for i, pasta in enumerate(st.session_state.caminho_navegacao):
                        st.markdown(" › ", unsafe_allow_html=True)
                        if i == len(st.session_state.caminho_navegacao) - 1:
                            st.markdown(f"**{pasta['nome']}**", unsafe_allow_html=True)
                        else:
                            if st.button(pasta['nome'], key=f"bread_{i}"):
                                voltar_nivel(i + 1)
                                st.rerun()
                    
                    # Listar conteúdo
                    with st.spinner("Carregando..."):
                        conteudo = listar_conteudo_drive(pasta_atual_id)
                    
                    if conteudo.get("erro"):
                        st.warning(f"⚠️ Erro ao carregar: {conteudo['erro']}")
                    else:
                        # Pastas
                        if conteudo["pastas"]:
                            cols_pastas = st.columns(min(4, len(conteudo["pastas"])))
                            for i, pasta in enumerate(conteudo["pastas"]):
                                with cols_pastas[i % len(cols_pastas)]:
                                    if st.button(f"📁 {pasta['nome']}", use_container_width=True):
                                        navegar_para_pasta(pasta['nome'], pasta['id'])
                                        st.rerun()
                        
                        # Arquivos
                        if conteudo["arquivos"]:
                            for arquivo in conteudo["arquivos"]:
                                st.markdown(f"📄 [{arquivo['nome']}]({arquivo['link']})")
                    
                    # Voltar
                    if st.session_state.caminho_navegacao:
                        if st.button("⬅️ Voltar"):
                            voltar_nivel(len(st.session_state.caminho_navegacao) - 1)
                            st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                if st.button("❌ Fechar Detalhes", use_container_width=True):
                    st.session_state.ferramental_selecionado = None
                    resetar_navegacao()
                    st.rerun()
    
    # Formulário novo ferramental
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
            
            if st.form_submit_button("💾 SALVAR FERRAMENTAL", type="primary"):
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
                    sucesso, msg = salvar_ferramental(registro)
                    if sucesso:
                        st.success(msg)
                        st.session_state.mostrar_formulario_novo = False
                        st.rerun()
                    else:
                        st.error(msg)
        
        if st.button("❌ Cancelar", use_container_width=True):
            st.session_state.mostrar_formulario_novo = False
            st.rerun()

# ==================================================================================================
# 3. MÓDULO PRÊMIO PRENSADOS - FUNÇÕES DE CÁLCULO
# ==================================================================================================

def is_acertos_245(time_val):
    """Verifica se o valor de ACERTOS é 02:45:00"""
    if pd.isna(time_val):
        return False
    
    time_str = str(time_val).strip()
    formatos_245 = ["02:45:00", "2:45:00", "02:45", "2:45"]
    for fmt in formatos_245:
        if fmt in time_str:
            return True
    
    if isinstance(time_val, dt_time):
        if time_val.hour == 2 and time_val.minute == 45 and time_val.second == 0:
            return True
    
    return False

def calcular_horas_programadas(row):
    """
    Calcula as horas programadas.
    Se ACERTOS = 02:45:00, retorna 5.0 horas
    Caso contrário: HORAS_TOTAIS_DEC + ACERTOS_DEC + MANUT_DEC + 0.25
    """
    if 'ACERTOS' in row and is_acertos_245(row['ACERTOS']):
        return 5.0
    return row.get('HORAS_TOTAIS_DEC', 0.0) + row.get('ACERTOS_DEC', 0.0) + row.get('MANUT_DEC', 0.0) + 0.25

def gerar_pdf_premio(df_dados, titulo_extra=""):
    """Gera PDF do relatório de prêmio em memória"""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.5*cm, rightMargin=1.5*cm,
                               topMargin=1.5*cm, bottomMargin=1.5*cm)
        story = []
        styles = getSampleStyleSheet()
        
        style_title = ParagraphStyle("title", parent=styles["Heading1"], alignment=1, fontSize=14, spaceAfter=12)
        style_filter = ParagraphStyle("filter", parent=styles["Normal"], fontSize=8, alignment=0, spaceAfter=8)
        
        titulo = "Prêmio Por Produtividade Prensados"
        if titulo_extra:
            titulo += f" - {titulo_extra}"
        story.append(Paragraph(f"<b>{titulo}</b>", style_title))
        story.append(Spacer(1, 0.2 * cm))
        
        # Calcular TRS
        df_calc = df_dados.copy()
        df_calc["TRS_%"] = 0.0
        mask_meta = df_calc["META"] > 0
        df_calc.loc[mask_meta, "TRS_%"] = (df_calc.loc[mask_meta, "APROVADO"] / df_calc.loc[mask_meta, "META"] * 100).round(2)
        df_calc["TRS_EXCESSO"] = 0.0
        df_calc.loc[mask_meta, "TRS_EXCESSO"] = (df_calc.loc[mask_meta, "TRS_%"] - 100).round(2)
        df_calc.loc[df_calc["TRS_EXCESSO"] < 0, "TRS_EXCESSO"] = 0
        df_calc["HORAS_PROGRAMADAS_CALC"] = df_calc.apply(calcular_horas_programadas, axis=1)
        
        df_filtrado = df_calc[df_calc["TRS_%"] > 100]
        
        if df_filtrado.empty:
            story.append(Paragraph("Nenhum registro com TRS > 100% encontrado.", styles["Normal"]))
            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()
        
        # Cabeçalhos
        headers = ["DATA", "TURNO", "REFERÊNCIA", "META", "APROVADO", "TRS % (Excesso)", "HORAS TRAB.", "HORAS PROG."]
        dados_tabela = [headers]
        
        for _, row in df_filtrado.iterrows():
            horas_totais = row['HORAS_TOTAIS_DEC']
            horas_programadas = row['HORAS_PROGRAMADAS_CALC']
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
        total_excesso = df_filtrado['TRS_EXCESSO'].mean()
        total_horas_trab = df_filtrado['HORAS_TOTAIS_DEC'].sum()
        total_horas_prog = df_filtrado['HORAS_PROGRAMADAS_CALC'].sum()
        
        linha_total = ["TOTAL", "", "", f"{total_meta:,.0f}", f"{total_aprovado:,.0f}", 
                      f"{total_excesso:.2f}%", 
                      f"{int(total_horas_trab):02d}:{int((total_horas_trab % 1) * 60):02d}",
                      f"{int(total_horas_prog):02d}:{int((total_horas_prog % 1) * 60):02d}"]
        dados_tabela.append(linha_total)
        
        col_widths = [55, 35, 110, 60, 60, 55, 60, 60]
        tabela = Table(dados_tabela, colWidths=col_widths)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.grey),
            ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("FONTSIZE", (0,0), (-1,-1), 7),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("BACKGROUND", (0,-1), (-1,-1), colors.lightgrey),
            ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
        ]))
        
        story.append(tabela)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        return None

# ==================================================================================================
# 4. RENDERIZAÇÃO DO MÓDULO PRÊMIO PRENSADOS
# ==================================================================================================

def render_premio_prensados():
    """Renderiza o módulo PRÊMIO PRENSADOS - Restrito a nível 0"""
    # Verificação de acesso
    verificar_acesso_modulo(nivel_requerido=0)
    
    render_page_header("PRÊMIO PRENSADOS", f"Relatório de Prêmio · Atualizado {get_horario_brasilia()}", THEME['accent_lime'])
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {THEME['bg_card']} 0%, {THEME['bg_card2']} 100%); 
                padding: 15px 20px; border-radius: 10px; border-left: 4px solid {THEME['accent_lime']}; margin: 10px 0 20px 0;">
        <span style="font-size: 18px; margin-right: 10px;">📊</span>
        <span style="font-family: 'Rajdhani', sans-serif; font-size: 16px; font-weight: bold; color: {THEME['accent_lime']};">
            GERADOR DE RELATÓRIO DE PRÊMIO
        </span>
        <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {THEME['text_muted']}; margin-left: 15px;">
            Apenas registros com TRS > 100%
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    # Filtros
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    
    with col_f1:
        data_ini = st.date_input("Data Inicial", value=datetime.now().date() - timedelta(days=30), key="premio_data_ini")
    with col_f2:
        data_fim = st.date_input("Data Final", value=datetime.now().date(), key="premio_data_fim")
    with col_f3:
        turno_premio = st.selectbox("Turno", options=["(Todos)", "M", "T", "N"], key="premio_turno")
    with col_f4:
        prensa_tipo_premio = st.selectbox("Tipo de Prensa", options=["(Todos)", "Semi-Automática", "Automática"], key="premio_prensa")
    
    col_r1, col_r2 = st.columns([2, 1])
    with col_r1:
        referencia_premio = st.text_input("Referência (parte do código)", placeholder="Digite parte da referência...", key="premio_referencia")
    with col_r2:
        st.markdown("<br>", unsafe_allow_html=True)
        gerar_por_mes = st.checkbox("📆 Separar por mês", value=False, key="premio_separar_mes")
    
    if st.button("📊 GERAR RELATÓRIO", type="primary", use_container_width=True):
        with st.spinner("🔄 Carregando dados..."):
            df_base = carregar_dados_prensados()
            
            if df_base.empty:
                st.error("❌ Não foi possível carregar os dados.")
                st.stop()
            
            # Aplicar filtros
            df_filtrado = df_base.copy()
            if data_ini:
                df_filtrado = df_filtrado[df_filtrado["DATA"] >= pd.to_datetime(data_ini)]
            if data_fim:
                df_filtrado = df_filtrado[df_filtrado["DATA"] <= pd.to_datetime(data_fim)]
            if turno_premio != "(Todos)" and "TURNO" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["TURNO"] == turno_premio]
            if referencia_premio and "REFERÊNCIA" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["REFERÊNCIA"].fillna('').str.lower().str.contains(referencia_premio.lower())]
            if prensa_tipo_premio != "(Todos)" and "BOQUETA" in df_filtrado.columns:
                if "Semi" in prensa_tipo_premio:
                    df_filtrado = df_filtrado[df_filtrado["BOQUETA"] == 1]
                elif "Auto" in prensa_tipo_premio:
                    df_filtrado = df_filtrado[df_filtrado["BOQUETA"] == 2]
            
            if df_filtrado.empty:
                st.warning("⚠️ Nenhum dado encontrado com os filtros selecionados.")
                st.stop()
            
            # Preparar dados
            df_relatorio = df_filtrado.copy()
            if "APROVADO FINAL" in df_relatorio.columns:
                df_relatorio["APROVADO"] = df_relatorio["APROVADO FINAL"]
            
            df_relatorio = df_relatorio.rename(columns={"TRS 100%": "META"})
            
            if not pd.api.types.is_datetime64_any_dtype(df_relatorio["DATA"]):
                df_relatorio["DATA"] = pd.to_datetime(df_relatorio["DATA"])
            
            df_relatorio["MES_ANO"] = df_relatorio["DATA"].dt.strftime("%m/%Y")
            df_relatorio["HORAS_TOTAIS_DEC"] = df_relatorio["HORAS TOTAIS"].apply(time_to_decimal_local)
            df_relatorio["ACERTOS_DEC"] = df_relatorio["ACERTOS"].apply(time_to_decimal_local)
            df_relatorio["MANUT_DEC"] = df_relatorio["MANUT."].apply(time_to_decimal_local)
            
            # Gerar PDF
            titulo_extra = f"{data_ini.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
            pdf_bytes = gerar_pdf_premio(df_relatorio, titulo_extra)
            
            if pdf_bytes:
                st.success(f"✅ Relatório gerado com sucesso!")
                nome_arquivo = f"Premio_Produtividade_Prensados_{datetime.now().strftime('%Y-%m-%d')}.pdf"
                st.download_button(
                    label="📥 BAIXAR RELATÓRIO PDF",
                    data=pdf_bytes,
                    file_name=nome_arquivo,
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )
            else:
                st.error("❌ Erro ao gerar o relatório.")

# ==================================================================================================
# 5. MÓDULO REPASSES DE PRODUÇÃO - DATACLASS E FUNÇÕES
# ==================================================================================================

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

def unificar_codigo_base(df: pd.DataFrame) -> pd.DataFrame:
    """Unifica registros com mesmo CÓDIGO_BASE"""
    if df.empty:
        return df
    
    if 'CODIGO_BASE' not in df.columns:
        df['CODIGO_BASE'] = df['CODIGO'] if 'CODIGO' in df.columns else ''
    
    if 'PEDIDO_EM_ABERTO' not in df.columns:
        df['PEDIDO_EM_ABERTO'] = 0
    
    if 'ESTOQUE' not in df.columns:
        df['ESTOQUE'] = 0
    
    df['CODIGO_BASE_NORM'] = df['CODIGO_BASE'].astype(str).str.strip()
    df['CODIGO_BASE_NORM'] = df['CODIGO_BASE_NORM'].replace(['', 'nan', 'None', '0'], '')
    
    counts = df['CODIGO_BASE_NORM'].value_counts()
    codigos_para_unificar = counts[counts > 1].index.tolist()
    codigos_para_unificar = [c for c in codigos_para_unificar if c != '']
    
    if not codigos_para_unificar:
        return df
    
    df_para_unificar = df[df['CODIGO_BASE_NORM'].isin(codigos_para_unificar)].copy()
    df_nao_unificar = df[~df['CODIGO_BASE_NORM'].isin(codigos_para_unificar)].copy()
    
    df_resultado = []
    
    for codigo_base in codigos_para_unificar:
        subset = df_para_unificar[df_para_unificar['CODIGO_BASE_NORM'] == codigo_base].copy()
        
        reg_principal = subset[subset['CODIGO'].astype(str).str.strip() == codigo_base]
        if reg_principal.empty:
            reg_principal = subset.iloc[0:1]
        
        nova_linha = {
            'CODIGO': reg_principal.iloc[0]['CODIGO'] if not reg_principal.empty else codigo_base,
            'CODIGO_BASE': codigo_base,
            'REFERENCIA': reg_principal.iloc[0].get('REFERENCIA', codigo_base) if not reg_principal.empty else codigo_base,
            'DESCRICAO': reg_principal.iloc[0].get('DESCRICAO', '') if not reg_principal.empty else '',
            'ESTOQUE': reg_principal.iloc[0].get('ESTOQUE', 0) if not reg_principal.empty else 0,
            'PEDIDO_EM_ABERTO': int(subset['PEDIDO_EM_ABERTO'].sum()),
        }
        df_resultado.append(pd.DataFrame([nova_linha]))
    
    if not df_nao_unificar.empty:
        df_resultado.append(df_nao_unificar)
    
    if df_resultado:
        df_final = pd.concat(df_resultado, ignore_index=True)
        if 'CODIGO_BASE_NORM' in df_final.columns:
            df_final = df_final.drop(columns=['CODIGO_BASE_NORM'])
        df_final = df_final.sort_values('CODIGO', ascending=True)
        return df_final
    
    return df

@retry_on_quota()
@st.cache_data(ttl=600)
def carregar_carteira_pedidos() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame()
        
        spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
        sheet = spreadsheet.worksheet(ABA_CARTEIRA)
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return pd.DataFrame()
        
        cabecalho = todos_dados[0]
        valores = todos_dados[1:]
        df = pd.DataFrame(valores, columns=cabecalho)
        df.columns = df.columns.str.strip()
        
        mapa_colunas = {}
        for col in df.columns:
            col_upper = col.upper().strip()
            col_sem_acento = unicodedata.normalize('NFKD', col_upper).encode('ASCII', 'ignore').decode('ASCII')
            
            if col_sem_acento in ['CODIGO', 'COD', 'ID']:
                mapa_colunas[col] = 'CODIGO'
            elif col_sem_acento in ['CODIGO_BASE', 'COD_BASE', 'BASE']:
                mapa_colunas[col] = 'CODIGO_BASE'
            elif col_sem_acento in ['REFERENCIA', 'REFERÊNCIA', 'REF']:
                mapa_colunas[col] = 'REFERENCIA'
            elif col_sem_acento in ['DESCRICAO', 'DESCRIÇÃO', 'DESC']:
                mapa_colunas[col] = 'DESCRICAO'
            elif col_sem_acento in ['ESTOQUE', 'EST', 'SALDO']:
                mapa_colunas[col] = 'ESTOQUE'
            elif col_sem_acento in ['PEDIDO_EM_ABERTO', 'PEDIDO', 'ABERTO']:
                mapa_colunas[col] = 'PEDIDO_EM_ABERTO'
        
        if mapa_colunas:
            df = df.rename(columns=mapa_colunas)
        
        if 'PEDIDO_EM_ABERTO' not in df.columns:
            df['PEDIDO_EM_ABERTO'] = 0
        
        if 'CODIGO_BASE' not in df.columns:
            df['CODIGO_BASE'] = df['CODIGO'] if 'CODIGO' in df.columns else ''
        
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
        
        return df
    except:
        return pd.DataFrame()

@retry_on_quota()
@st.cache_data(ttl=300)
def carregar_repasse() -> List[RegistroRepasse]:
    registros = []
    try:
        client = get_gspread_client()
        if client is None:
            return registros
        
        spreadsheet = client.open_by_key(ID_PLANILHA_URGENCIAS)
        
        try:
            sheet = spreadsheet.worksheet(ABA_REPASSE)
        except:
            return registros
        
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return registros
        
        for row in todos_dados[1:]:
            if len(row) < 8:
                continue
            
            try:
                registro = RegistroRepasse()
                registro.id = row[0].strip() if row[0] else ""
                
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
    except:
        return registros

def obter_proximo_id_repasse() -> str:
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

def salvar_repasse(registro: RegistroRepasse) -> tuple:
    try:
        client = get_gspread_client()
        if client is None:
            return False, "❌ Erro ao conectar"
        
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
    except:
        return False, "❌ Erro ao salvar"

# ==================================================================================================
# 6. RENDERIZAÇÃO DO MÓDULO REPASSES DE PRODUÇÃO
# ==================================================================================================

def render_repasses_producao():
    """Renderiza o módulo REPASSES DE PRODUÇÃO"""
    render_page_header("REPASSES DE PRODUÇÃO", f"Carteira de Pedidos · Atualizado {get_horario_brasilia()}", THEME['accent_orange'])
    
    # Inicializar session state
    if 'visao_repasses' not in st.session_state:
        st.session_state.visao_repasses = 'PEDIDOS_SISTEMA'
    if 'unificar_codigo_base' not in st.session_state:
        st.session_state.unificar_codigo_base = False
    
    # Carregar dados
    with st.spinner("🔄 Carregando dados..."):
        df_carteira = carregar_carteira_pedidos()
    
    if df_carteira.empty:
        st.warning("⚠️ Não foi possível carregar os dados da carteira.")
        return
    
    # Botões de navegação
    st.markdown("### 📊 Selecione a Visualização")
    col_b1, col_b2, col_b3 = st.columns(3)
    
    with col_b1:
        if st.button("📋 Pedidos Sistema", use_container_width=True, 
                    type="primary" if st.session_state.visao_repasses == 'PEDIDOS_SISTEMA' else "secondary"):
            st.session_state.visao_repasses = 'PEDIDOS_SISTEMA'
            st.rerun()
    
    with col_b2:
        if st.button("🔄 Repasses", use_container_width=True,
                    type="primary" if st.session_state.visao_repasses == 'REPASSES' else "secondary"):
            st.session_state.visao_repasses = 'REPASSES'
            st.rerun()
    
    with col_b3:
        if st.button("📦 Estoque Atual", use_container_width=True,
                    type="primary" if st.session_state.visao_repasses == 'ESTOQUE_ATUAL' else "secondary"):
            st.session_state.visao_repasses = 'ESTOQUE_ATUAL'
            st.rerun()
    
    st.markdown("---")
    
    if st.session_state.visao_repasses == 'REPASSES':
        # CRUD de Repasses
        st.subheader("📋 Gerenciamento de Repasses")
        
        if st.button("➕ NOVO REPASSE", type="primary", use_container_width=True):
            st.session_state.mostrar_formulario_repasse = True
        
        if st.session_state.get('mostrar_formulario_repasse', False):
            with st.form("form_repasse"):
                st.info(f"📌 Novo Repasse")
                
                col1, col2 = st.columns(2)
                with col1:
                    solicitante = st.text_input("Solicitante")
                    referencia = st.text_input("Referência*")
                    cliente = st.text_input("Cliente")
                with col2:
                    quantidade = st.number_input("Quantidade*", min_value=0, value=0, step=1)
                    data_limite = st.date_input("Data Limite", value=datetime.now() + timedelta(days=7))
                    status = st.selectbox("Status", ["SOLICITADO", "PROGRAMADO", "PRODUZIDO"])
                
                if st.form_submit_button("💾 SALVAR REPASSE", type="primary"):
                    if not referencia or quantidade <= 0:
                        st.error("❌ Preencha referência e quantidade!")
                    else:
                        novo = RegistroRepasse(
                            id=obter_proximo_id_repasse(),
                            data=datetime.now(),
                            solicitante=solicitante,
                            referencia=referencia,
                            cliente=cliente,
                            quantidade=quantidade,
                            data_limite=datetime.combine(data_limite, datetime.min.time()),
                            status=status
                        )
                        sucesso, msg = salvar_repasse(novo)
                        if sucesso:
                            st.success(msg)
                            st.session_state.mostrar_formulario_repasse = False
                            st.rerun()
                        else:
                            st.error(msg)
            
            if st.button("❌ Cancelar", use_container_width=True):
                st.session_state.mostrar_formulario_repasse = False
                st.rerun()
        
        # Listar repasses
        repasses = carregar_repasse()
        if repasses:
            dados = []
            for r in repasses:
                dados.append({
                    "ID": r.id,
                    "Data": r.data.strftime("%d/%m/%Y") if r.data else "-",
                    "Solicitante": r.solicitante,
                    "Referência": r.referencia,
                    "Qtd": f"{r.quantidade:,}".replace(",", "."),
                    "Status": r.status
                })
            df_repasses = pd.DataFrame(dados)
            st.dataframe(df_repasses, use_container_width=True, height=300, hide_index=True)
    
    else:
        # Carteira de pedidos
        st.markdown("### 🔍 Filtros")
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            if 'REFERENCIA' in df_carteira.columns:
                filtro_ref = st.selectbox("Referência", ["(Todas)"] + sorted(df_carteira['REFERENCIA'].dropna().unique().tolist()))
            else:
                filtro_ref = "(Todas)"
        
        with col_f2:
            if 'CODIGO' in df_carteira.columns:
                filtro_cod = st.selectbox("Código", ["(Todos)"] + sorted(df_carteira['CODIGO'].dropna().unique().tolist()))
            else:
                filtro_cod = "(Todos)"
        
        with col_f3:
            if 'CODIGO_BASE' in df_carteira.columns:
                unificar = st.checkbox("🔗 Unificar por CÓDIGO BASE", value=st.session_state.unificar_codigo_base)
                if unificar != st.session_state.unificar_codigo_base:
                    st.session_state.unificar_codigo_base = unificar
                    st.rerun()
        
        df_filtrado = df_carteira.copy()
        if filtro_ref != "(Todas)":
            df_filtrado = df_filtrado[df_filtrado['REFERENCIA'] == filtro_ref]
        if filtro_cod != "(Todos)":
            df_filtrado = df_filtrado[df_filtrado['CODIGO'] == filtro_cod]
        
        if st.session_state.unificar_codigo_base and 'CODIGO_BASE' in df_filtrado.columns:
            df_filtrado = unificar_codigo_base(df_filtrado)
        
        if st.session_state.visao_repasses == 'PEDIDOS_SISTEMA':
            coluna_valor = 'PEDIDO_EM_ABERTO'
            label_valor = 'Pedido Sistema'
            titulo_tabela = 'PEDIDOS EM ABERTO'
        else:
            coluna_valor = 'ESTOQUE'
            label_valor = 'Estoque Atual'
            titulo_tabela = 'ESTOQUE ATUAL'
        
        # KPIs
        total_valor = int(df_filtrado[coluna_valor].sum()) if coluna_valor in df_filtrado.columns else 0
        total_itens = len(df_filtrado)
        
        col_k1, col_k2 = st.columns(2)
        with col_k1:
            st.metric(f"📊 Total {label_valor}", f"{total_valor:,.0f}".replace(",", "."))
        with col_k2:
            st.metric("📋 Itens", f"{total_itens:,}".replace(",", "."))
        
        # Tabela
        st.markdown(f"### 📋 {titulo_tabela}")
        df_exibicao = df_filtrado.copy()
        
        mapa_exibicao = {
            'CODIGO': 'Código',
            'CODIGO_BASE': 'Código Base',
            'REFERENCIA': 'Referência',
            'DESCRICAO': 'Descrição',
            'ESTOQUE': 'Estoque',
            'PEDIDO_EM_ABERTO': 'Pedido'
        }
        
        for old, new in mapa_exibicao.items():
            if old in df_exibicao.columns:
                df_exibicao = df_exibicao.rename(columns={old: new})
        
        colunas_base = ['Código', 'Código Base', 'Referência', 'Descrição', 'Estoque']
        if 'Pedido' in df_exibicao.columns and st.session_state.visao_repasses == 'PEDIDOS_SISTEMA':
            colunas_base.append('Pedido')
        
        colunas_existentes = [c for c in colunas_base if c in df_exibicao.columns]
        df_exibicao = df_exibicao[colunas_existentes]
        
        st.dataframe(df_exibicao, use_container_width=True, height=400, hide_index=True)

# ==================================================================================================
# 7. MÓDULO CONTROLE DO FORNO - CONSTANTES E FUNÇÕES
# ==================================================================================================

# Configurações do forno
ALARMES_CONFIG = {
    'nivel_min': 75,
    'nivel_max': 85,
    'tiragem_meta': 350,
    'relacao_o2_gas_ideal': 2.0,
    'relacao_o2_gas_min': 1.8,
    'relacao_o2_gas_max': 2.2,
    'consumo_gas_alerta': 500,
    'consumo_oxi_alerta': 400,
    'diferenca_temp_max': 20,
}

BOQUETAS_CONFIG = {
    'BOQUETA_1': {'min': 1220, 'max': 1240, 'display': 'BOQUETA-1', 'cor': '#0078D4'},
    'BOQUETA_2': {'min': 1270, 'max': 1280, 'display': 'BOQUETA-2', 'cor': '#E86C2C'},
    'BOQUETA_3': {'min': 1240, 'max': 1260, 'display': 'BOQUETA-3', 'cor': '#FFB900'},
    'BOQUETA_4': {'min': 1220, 'max': 1240, 'display': 'BOQUETA-4', 'cor': '#107C10'},
    'BOQUETA_5': {'min': 1250, 'max': 1270, 'display': 'BOQUETA-5', 'cor': '#6B46C1'},
}

def get_faixa_boqueta(nome_boqueta: str) -> tuple:
    config = BOQUETAS_CONFIG.get(nome_boqueta, {})
    return config.get('min', 0), config.get('max', 0)

def converter_datetime_completo(data_val, hora_val):
    if pd.isna(data_val) or pd.isna(hora_val):
        return pd.NaT
    
    try:
        if isinstance(data_val, (datetime, pd.Timestamp)):
            data_obj = data_val
        elif isinstance(data_val, date):
            data_obj = datetime.combine(data_val, dt_time.min)
        else:
            data_obj = converter_data_br(data_val)
            if data_obj is None:
                return pd.NaT
        
        hora_str = str(hora_val).strip()
        if ':' in hora_str:
            partes = hora_str.split(':')
            if len(partes) >= 2:
                h = int(partes[0])
                m = int(partes[1])
                s = int(partes[2]) if len(partes) > 2 else 0
                if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
                    return datetime(data_obj.year, data_obj.month, data_obj.day, h, m, s)
        return data_obj
    except:
        return pd.NaT

@retry_on_quota()
@st.cache_data(ttl=300)
def carregar_dados_enfornadeira() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame()
        
        spreadsheet = client.open_by_key(ID_PLANILHA_ENFORNADEIRA)
        
        try:
            sheet = spreadsheet.worksheet(ABA_ENFORNADEIRA)
        except:
            return pd.DataFrame()
        
        todos_dados = sheet.get_all_values()
        
        if len(todos_dados) < 2:
            return pd.DataFrame()
        
        cabecalho = todos_dados[0]
        valores = todos_dados[1:]
        df = pd.DataFrame(valores, columns=cabecalho)
        
        mapa_colunas = {}
        for col in df.columns:
            col_str = str(col).strip()
            col_upper = col_str.upper()
            col_sem_acento = unicodedata.normalize('NFKD', col_upper).encode('ASCII', 'ignore').decode('ASCII')
            
            if col_sem_acento in ['DATA', 'DATE']:
                mapa_colunas[col] = 'DATA'
            elif col_sem_acento in ['HORA', 'TIME']:
                mapa_colunas[col] = 'HORA'
            elif col_sem_acento in ['NIVEL', 'NÍVEL']:
                mapa_colunas[col] = 'NIVEL'
            elif 'CICLO' in col_sem_acento:
                mapa_colunas[col] = 'CICLO'
            elif col_sem_acento in ['VOLTAS', 'VOLTA']:
                mapa_colunas[col] = 'VOLTAS'
            elif 'TIRAGEM' in col_sem_acento:
                mapa_colunas[col] = 'TIRAGEM_KG'
            elif 'OXI' in col_sem_acento and '1' in col_sem_acento:
                mapa_colunas[col] = 'OXI_1'
            elif 'GAS' in col_sem_acento and '1' in col_sem_acento:
                mapa_colunas[col] = 'GAS_1'
            elif 'OXI' in col_sem_acento and '2' in col_sem_acento:
                mapa_colunas[col] = 'OXI_2'
            elif 'GAS' in col_sem_acento and '2' in col_sem_acento:
                mapa_colunas[col] = 'GAS_2'
            elif 'BOQUETA-1' in col_sem_acento or 'BOQUETA_1' in col_sem_acento:
                mapa_colunas[col] = 'BOQUETA_1'
            elif 'BOQUETA-2' in col_sem_acento or 'BOQUETA_2' in col_sem_acento:
                mapa_colunas[col] = 'BOQUETA_2'
            elif 'BOQUETA-3' in col_sem_acento or 'BOQUETA_3' in col_sem_acento:
                mapa_colunas[col] = 'BOQUETA_3'
            elif 'BOQUETA-4' in col_sem_acento or 'BOQUETA_4' in col_sem_acento:
                mapa_colunas[col] = 'BOQUETA_4'
            elif 'BOQUETA-5' in col_sem_acento or 'BOQUETA_5' in col_sem_acento:
                mapa_colunas[col] = 'BOQUETA_5'
        
        if mapa_colunas:
            df = df.rename(columns=mapa_colunas)
        
        if 'DATA' in df.columns:
            df['DATA'] = df['DATA'].apply(converter_data_br)
            df = df.dropna(subset=['DATA'])
        
        if 'HORA' in df.columns:
            df['HORA_OBJ'] = df['HORA'].apply(converter_hora_str)
            df['HORA_DEC'] = df['HORA_OBJ'].apply(lambda x: x.hour + x.minute/60 + x.second/3600 if x else 0)
        
        colunas_numericas = ['NIVEL', 'CICLO', 'VOLTAS', 'TIRAGEM_KG', 
                           'OXI_1', 'GAS_1', 'OXI_2', 'GAS_2',
                           'BOQUETA_1', 'BOQUETA_2', 'BOQUETA_3', 'BOQUETA_4', 'BOQUETA_5']
        
        for col in colunas_numericas:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.')
                df[col] = df[col].astype(str).str.replace(r'[^\d\.]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Calcular colunas derivadas
        boquetas = ['BOQUETA_1', 'BOQUETA_2', 'BOQUETA_3', 'BOQUETA_4', 'BOQUETA_5']
        boquetas_existentes = [b for b in boquetas if b in df.columns]
        
        if boquetas_existentes:
            df_temp = df[boquetas_existentes].replace(0, np.nan)
            df['TEMP_MEDIA'] = df_temp.mean(axis=1, skipna=True).fillna(0)
            df['TEMP_MAX'] = df_temp.max(axis=1, skipna=True).fillna(0)
            df['TEMP_MIN'] = df_temp.min(axis=1, skipna=True).fillna(0)
            df['TEMP_DIFERENCA'] = (df['TEMP_MAX'] - df['TEMP_MIN']).fillna(0)
        
        if 'OXI_1' in df.columns and 'OXI_2' in df.columns:
            df['OXI_TOTAL'] = df['OXI_1'] + df['OXI_2']
        
        if 'GAS_1' in df.columns and 'GAS_2' in df.columns:
            df['GAS_TOTAL'] = df['GAS_1'] + df['GAS_2']
        
        if 'OXI_TOTAL' in df.columns and 'GAS_TOTAL' in df.columns:
            df['ENERGIA_TOTAL'] = df['OXI_TOTAL'] + df['GAS_TOTAL']
            df['RELACAO_O2_GAS'] = df['OXI_TOTAL'] / df['GAS_TOTAL'].replace(0, np.nan)
            df['RELACAO_O2_GAS'] = df['RELACAO_O2_GAS'].fillna(0)
        
        if 'HORA_DEC' in df.columns:
            def classificar_turno(hora):
                if pd.isna(hora):
                    return 'N/A'
                if 6 <= hora < 14:
                    return 'MANHÃ'
                elif 14 <= hora < 22:
                    return 'TARDE'
                else:
                    return 'NOITE'
            df['TURNO'] = df['HORA_DEC'].apply(classificar_turno)
        
        if 'DATA' in df.columns and 'HORA' in df.columns:
            df['DATETIME'] = df.apply(
                lambda row: converter_datetime_completo(row['DATA'], row['HORA']),
                axis=1
            )
            mask_invalid = df['DATETIME'].isna()
            if mask_invalid.any():
                df.loc[mask_invalid, 'DATETIME'] = df.loc[mask_invalid, 'DATA']
        
        if 'DATETIME' in df.columns:
            df = df.sort_values('DATETIME', ascending=True)
        
        return df
    except:
        return pd.DataFrame()

def salvar_registro_enfornadeira(dados: Dict) -> tuple:
    try:
        client = get_gspread_client()
        if client is None:
            return False, "❌ Erro ao conectar"
        
        spreadsheet = client.open_by_key(ID_PLANILHA_ENFORNADEIRA)
        
        try:
            sheet = spreadsheet.worksheet(ABA_ENFORNADEIRA)
        except:
            cabecalho = ["DATA", "HORA", "NÍVEL", "CICLO(SEG)", "VOLTAS", "TIRAGEM KG", 
                        "OXI M³ - 1", "GÁS M³ - 1", "OXI M³ - 2", "GÁS M³ - 2", 
                        "BOQUETA-1", "BOQUETA-2", "BOQUETA-3", "BOQUETA-4", "BOQUETA-5"]
            sheet = spreadsheet.add_worksheet(title=ABA_ENFORNADEIRA, rows=1000, cols=20)
            sheet.append_row(cabecalho)
        
        agora = get_horario_brasilia_obj()
        data_str = agora.strftime("%d/%m/%Y")
        hora_str = agora.strftime("%H:%M:%S")
        
        linha = [
            data_str, hora_str,
            str(dados.get('nivel', '')),
            str(dados.get('ciclo', '')),
            str(dados.get('voltas', '')),
            str(dados.get('tiragem', '')),
            str(dados.get('oxi_1', '')),
            str(dados.get('gas_1', '')),
            str(dados.get('oxi_2', '')),
            str(dados.get('gas_2', '')),
            str(dados.get('boqueta_1', '')),
            str(dados.get('boqueta_2', '')),
            str(dados.get('boqueta_3', '')),
            str(dados.get('boqueta_4', '')),
            str(dados.get('boqueta_5', ''))
        ]
        
        sheet.append_row(linha)
        st.cache_data.clear()
        return True, "✅ Registro salvo com sucesso!"
    except:
        return False, "❌ Erro ao salvar"

def gerar_alertas_sugestoes(dados: Dict) -> List[Dict]:
    alertas = []
    
    nivel = dados.get('nivel', 0)
    if nivel < ALARMES_CONFIG['nivel_min']:
        alertas.append({
            'tipo': 'CRÍTICO',
            'cor': '#E81123',
            'mensagem': f"🔴 NÍVEL ABAIXO: {nivel} cm (ideal: {ALARMES_CONFIG['nivel_min']}-{ALARMES_CONFIG['nivel_max']} cm)",
            'sugestao': f"AUMENTE a alimentação para elevar o nível."
        })
    elif nivel > ALARMES_CONFIG['nivel_max']:
        alertas.append({
            'tipo': 'ALERTA',
            'cor': '#FFB900',
            'mensagem': f"🟡 NÍVEL ACIMA: {nivel} cm (ideal: {ALARMES_CONFIG['nivel_min']}-{ALARMES_CONFIG['nivel_max']} cm)",
            'sugestao': f"REDUZA a alimentação para baixar o nível."
        })
    
    for i in range(1, 6):
        temp = dados.get(f'boqueta_{i}', 0)
        if temp > 0:
            nome_boqueta = f'BOQUETA_{i}'
            nome_display = f'BOQUETA-{i}'
            temp_min, temp_max = get_faixa_boqueta(nome_boqueta)
            
            if temp < temp_min:
                alertas.append({
                    'tipo': 'CRÍTICO',
                    'cor': '#E81123',
                    'mensagem': f"🔴 {nome_display} ABAIXO: {temp} °C (ideal: {temp_min}-{temp_max} °C)",
                    'sugestao': f"AUMENTE a vazão de gás para esta boqueta."
                })
            elif temp > temp_max:
                alertas.append({
                    'tipo': 'ALERTA',
                    'cor': '#FFB900',
                    'mensagem': f"🟡 {nome_display} ACIMA: {temp} °C (ideal: {temp_min}-{temp_max} °C)",
                    'sugestao': f"REDUZA a vazão de gás para esta boqueta."
                })
    
    tiragem = dados.get('tiragem', 0)
    if tiragem < ALARMES_CONFIG['tiragem_meta']:
        alertas.append({
            'tipo': 'ALERTA',
            'cor': '#FFB900',
            'mensagem': f"🟡 TIRAGEM ABAIXO: {tiragem:.1f} kg/h (máx: {ALARMES_CONFIG['tiragem_meta']} kg/h)",
            'sugestao': "Aumente a alimentação se necessário."
        })
    
    oxi_total = dados.get('oxi_1', 0) + dados.get('oxi_2', 0)
    gas_total = dados.get('gas_1', 0) + dados.get('gas_2', 0)
    
    if gas_total > 0:
        relacao = oxi_total / gas_total
        if relacao < ALARMES_CONFIG['relacao_o2_gas_min']:
            alertas.append({
                'tipo': 'CRÍTICO',
                'cor': '#E81123',
                'mensagem': f"🔴 O₂/GÁS BAIXA: {relacao:.2f} (ideal: 2.0 - faixa: 1.8-2.2)",
                'sugestao': "AUMENTE oxigênio ou DIMINUA gás."
            })
        elif relacao > ALARMES_CONFIG['relacao_o2_gas_max']:
            alertas.append({
                'tipo': 'ALERTA',
                'cor': '#FFB900',
                'mensagem': f"🟡 O₂/GÁS ALTA: {relacao:.2f} (ideal: 2.0 - faixa: 1.8-2.2)",
                'sugestao': "DIMINUA oxigênio ou AUMENTE gás."
            })
    
    return alertas

# ==================================================================================================
# 8. RENDERIZAÇÃO DO MÓDULO CONTROLE DO FORNO
# ==================================================================================================

def render_controle_forno():
    """Renderiza o módulo CONTROLE DO FORNO"""
    render_page_header("CONTROLE DO FORNO", f"Controle do Forno de Fusão · Atualizado {get_horario_brasilia()}", THEME['accent_red'])
    
    # Inicializar session state
    if 'enfornadeira_confirmar_salvar' not in st.session_state:
        st.session_state.enfornadeira_confirmar_salvar = False
    if 'enfornadeira_dados_lancamento' not in st.session_state:
        st.session_state.enfornadeira_dados_lancamento = {}
    
    # Carregar dados
    with st.spinner("🔄 Carregando dados do Forno..."):
        df = carregar_dados_enfornadeira()
    
    if df.empty:
        st.warning("⚠️ Não foi possível carregar os dados do Forno.")
    
    # Formulário de lançamento
    st.markdown("---")
    st.markdown("### ✏️ Lançamento de Apontamentos")
    
    agora = get_horario_brasilia_obj()
    st.info(f"📅 Data: {agora.strftime('%d/%m/%Y %H:%M:%S')} (Horário de Brasília)")
    
    with st.form("form_lancamento_forno"):
        col1, col2, col3 = st.columns(3)
        with col1:
            nivel = st.number_input("Nível do Vidro (cm)*", min_value=0.0, max_value=120.0, value=0.0, step=0.5)
            ciclo = st.number_input("Ciclo (segundos)*", min_value=0.0, max_value=60.0, value=0.0, step=0.1)
        with col2:
            voltas = st.number_input("Voltas*", min_value=0.0, max_value=50.0, value=0.0, step=0.5)
            tiragem = st.number_input("Tiragem (kg/h)*", min_value=0.0, max_value=600.0, value=0.0, step=5.0)
        with col3:
            oxi_1 = st.number_input("O₂ M³ - 1*", min_value=0.0, max_value=600.0, value=0.0, step=1.0)
            gas_1 = st.number_input("Gás M³ - 1*", min_value=0.0, max_value=600.0, value=0.0, step=1.0)
            oxi_2 = st.number_input("O₂ M³ - 2*", min_value=0.0, max_value=600.0, value=0.0, step=1.0)
            gas_2 = st.number_input("Gás M³ - 2*", min_value=0.0, max_value=600.0, value=0.0, step=1.0)
        
        st.markdown("### 🌡️ Temperaturas das Boquetas")
        col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
        with col_b1:
            boqueta_1 = st.number_input("BOQUETA-1 (°C)", min_value=0.0, max_value=1350.0, value=0.0, step=5.0)
        with col_b2:
            boqueta_2 = st.number_input("BOQUETA-2 (°C)", min_value=0.0, max_value=1350.0, value=0.0, step=5.0)
        with col_b3:
            boqueta_3 = st.number_input("BOQUETA-3 (°C)", min_value=0.0, max_value=1350.0, value=0.0, step=5.0)
        with col_b4:
            boqueta_4 = st.number_input("BOQUETA-4 (°C)", min_value=0.0, max_value=1350.0, value=0.0, step=5.0)
        with col_b5:
            boqueta_5 = st.number_input("BOQUETA-5 (°C)", min_value=0.0, max_value=1350.0, value=0.0, step=5.0)
        
        if st.form_submit_button("💾 SALVAR REGISTRO", type="primary", use_container_width=True):
            campos_obrigatorios = {
                'Nível': nivel, 'Ciclo': ciclo, 'Voltas': voltas,
                'Tiragem': tiragem, 'O₂-1': oxi_1, 'Gás-1': gas_1,
                'O₂-2': oxi_2, 'Gás-2': gas_2
            }
            
            campos_vazios = [nome for nome, valor in campos_obrigatorios.items() if valor <= 0]
            
            if campos_vazios:
                st.error(f"❌ Preencha: {', '.join(campos_vazios)}")
            else:
                dados_lancamento = {
                    'nivel': nivel, 'boqueta_1': boqueta_1, 'boqueta_2': boqueta_2,
                    'boqueta_3': boqueta_3, 'boqueta_4': boqueta_4, 'boqueta_5': boqueta_5,
                    'ciclo': ciclo, 'voltas': voltas, 'tiragem': tiragem,
                    'oxi_1': oxi_1, 'gas_1': gas_1, 'oxi_2': oxi_2, 'gas_2': gas_2
                }
                
                alertas = gerar_alertas_sugestoes(dados_lancamento)
                
                if alertas:
                    st.warning("⚠️ Alertas identificados!")
                    for alerta in alertas:
                        st.markdown(f"<div style='background:{alerta['cor']}10;padding:8px;border-left:4px solid {alerta['cor']};margin:5px 0;'>{alerta['mensagem']}<br><span style='font-size:12px;color:#666;'>💡 {alerta['sugestao']}</span></div>", unsafe_allow_html=True)
                
                if st.button("✅ CONFIRMAR SALVAMENTO", type="primary"):
                    sucesso, msg = salvar_registro_enfornadeira(dados_lancamento)
                    if sucesso:
                        st.success(msg)
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(msg)
    
    # Dashboard se houver dados
    if not df.empty:
        st.markdown("---")
        st.markdown("### 📊 Dashboard do Forno")
        
        # KPIs
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            nivel_atual = df['NIVEL'].iloc[-1] if 'NIVEL' in df.columns and not df.empty else 0
            st.metric("📊 Nível Atual", f"{nivel_atual:.1f} cm")
        with col_k2:
            tiragem_media = df['TIRAGEM_KG'].mean() if 'TIRAGEM_KG' in df.columns else 0
            st.metric("📦 Tiragem Média", f"{tiragem_media:.1f} kg/h")
        with col_k3:
            temp_media = df['TEMP_MEDIA'].mean() if 'TEMP_MEDIA' in df.columns else 0
            st.metric("🌡️ Temp. Média", f"{temp_media:.0f} °C")
        with col_k4:
            relacao = df['RELACAO_O2_GAS'].mean() if 'RELACAO_O2_GAS' in df.columns else 0
            st.metric("⚖️ O₂/Gás Médio", f"{relacao:.2f}")
        
        # Gráfico de temperaturas
        if 'BOQUETA_1' in df.columns:
            st.markdown("#### 🌡️ Temperaturas das Boquetas")
            
            boquetas = ['BOQUETA_1', 'BOQUETA_2', 'BOQUETA_3', 'BOQUETA_4', 'BOQUETA_5']
            boquetas_existentes = [b for b in boquetas if b in df.columns]
            
            if boquetas_existentes:
                df_plot = df[['DATETIME'] + boquetas_existentes].copy()
                df_plot = df_plot.dropna(subset=boquetas_existentes, how='all')
                
                if not df_plot.empty:
                    fig = px.line(
                        df_plot.tail(100),
                        x='DATETIME',
                        y=boquetas_existentes,
                        title='Evolução das Temperaturas das Boquetas',
                        labels={'value': 'Temperatura (°C)', 'variable': 'Boqueta'},
                        color_discrete_sequence=['#0078D4', '#E86C2C', '#FFB900', '#107C10', '#6B46C1']
                    )
                    
                    # Adicionar faixas ideais
                    for i, boqueta in enumerate(boquetas_existentes):
                        min_val, max_val = get_faixa_boqueta(boqueta)
                        fig.add_hrect(
                            y0=min_val, y1=max_val,
                            line_width=1,
                            line_color='green',
                            opacity=0.1,
                            annotation_text=f"{boqueta.replace('_', '-')}: {min_val}-{max_val}°C",
                            annotation_position="top left",
                            annotation_font_size=8
                        )
                    
                    fig.update_layout(height=350, legend=dict(orientation='h', yanchor='bottom', y=1.02))
                    fig.update_yaxes(range=[1150, 1350])
                    st.plotly_chart(fig, use_container_width=True)

# ==================================================================================================
# 9. ATUALIZAÇÃO FINAL DO ROTEADOR MAIN
# ==================================================================================================

"""
No roteador da função main(), adicionar após os módulos existentes:

elif aba_selecionada == 'FERRAMENTARIA':
    render_ferramentaria()
elif aba_selecionada == 'PRÊMIO PRENSADOS':
    render_premio_prensados()
elif aba_selecionada == 'REPASSES DE PRODUÇÃO':
    render_repasses_producao()
elif aba_selecionada == 'CONTROLE DO FORNO':
    render_controle_forno()

E no final da função main(), após todos os módulos:
renderizar_faixa_rolagem()

"""

# ==================================================================================================
# 10. MAIN COMPLETA - ROTEADOR FINAL
# ==================================================================================================

def main():
    """Função principal do aplicativo - VERSÃO COMPLETA"""
    
    st.set_page_config(
        page_title="TRS Dashboard",
        page_icon="⚙️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.markdown(get_global_css(), unsafe_allow_html=True)
    st.markdown(NOTIFICACAO_CSS, unsafe_allow_html=True)
    
    if not verificar_acesso():
        st.stop()
    
    if 'mensagem_login' in st.session_state:
        del st.session_state.mensagem_login
    
    renderizar_popups_pendentes()
    verificar_e_exibir_popups()
    
    aba_selecionada = render_sidebar()
    
    # Roteamento para todos os módulos
    if aba_selecionada == 'PRENSADOS':
        render_prensados()
    elif aba_selecionada == 'SOPRO':
        render_sopro()
    elif aba_selecionada == 'TÊMPERA':
        render_tempera()
    elif aba_selecionada == 'AVISO DE REJEIÇÃO':
        render_ar()
    elif aba_selecionada == 'REQUISIÇÃO MANUTENÇÃO':
        render_rm()
    elif aba_selecionada == 'FECHAMENTO TURNO':
        render_fechamento_turno()
    elif aba_selecionada == 'MANUTENÇÃO PREVENTIVA':
        render_manutencao_preventiva()
    elif aba_selecionada == 'MAPEAMENTO DE HABILIDADES':
        render_habilidades()
    elif aba_selecionada == 'FERRAMENTARIA':
        render_ferramentaria()
    elif aba_selecionada == 'PRÊMIO PRENSADOS':
        render_premio_prensados()
    elif aba_selecionada == 'REPASSES DE PRODUÇÃO':
        render_repasses_producao()
    elif aba_selecionada == 'CONTROLE DO FORNO':
        render_controle_forno()
    else:
        render_page_header(aba_selecionada, "Módulo em desenvolvimento...", THEME['accent_purple'])
        st.info(f"O módulo '{aba_selecionada}' será disponibilizado em breve.")
    
    renderizar_faixa_rolagem()

if __name__ == "__main__":
    main()

# ==================================================================================================
# FIM DA PARTE 5/5 - SISTEMA COMPLETO
# ==================================================================================================
