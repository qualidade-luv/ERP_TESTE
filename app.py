import streamlit as st
import pandas as pd
import numpy as np
import re
from PIL import Image
import requests
from io import BytesIO
import base64
from datetime import datetime
import time
import urllib.parse
import hashlib
import secrets
import socket
import urllib3

# ============================================
# CONFIGURAÇÕES DE SEGURANÇA E PRIVACIDADE
# ============================================

# Desabilitar warnings de SSL (se necessário)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar timeout global
socket.setdefaulttimeout(30)

# Configurações de sessão - tempo limite (em segundos)
SESSION_TIMEOUT = 1800  # 30 minutos

# ============================================
# NOVO SISTEMA TRIBUTÁRIO 2026 - FUNÇÕES
# ============================================

def calcular_impostos_2026(valor_base: float, uf_origem: str, uf_destino: str, 
                           ncm: str = '', is_seletivo: bool = False) -> dict:
    """
    Calcula impostos conforme Reforma Tributária 2026
    
    Args:
        valor_base: Valor base do produto (sem impostos)
        uf_origem: UF de origem (ex: 'SP')
        uf_destino: UF de destino (ex: 'MG')
        ncm: Código NCM do produto (para verificar IS)
        is_seletivo: Se produto tem imposto seletivo (override)
    
    Returns:
        Dicionário com valores dos novos impostos
    """
    
    # Alíquotas de referência IBS (variam por UF) - valores aproximados para 2026
    ALIQUOTAS_IBS = {
        'SP': 0.178,   # 17.8%
        'MG': 0.175,   # 17.5%
        'RJ': 0.18,    # 18%
        'RS': 0.17,    # 17%
        'PR': 0.175,   # 17.5%
        'SC': 0.17,    # 17%
        'BA': 0.18,    # 18%
        'DF': 0.175,   # 17.5%
        'GO': 0.175,   # 17.5%
        'ES': 0.17,    # 17%
        'MT': 0.17,    # 17%
        'MS': 0.17,    # 17%
        'PA': 0.18,    # 18%
        'PE': 0.18,    # 18%
        'CE': 0.18,    # 18%
        'DEFAULT': 0.172  # 17.2% média nacional
    }
    
    # Alíquota CBS (federal - uniforme para 2026)
    ALIQUOTA_CBS = 0.12  # 12%
    
    # Alíquota do Imposto Seletivo (quando aplicável)
    ALIQUOTA_IS = 0.25  # 25% para produtos selecionados
    
    # Ajuste para operações interestaduais (diferencial de alíquota)
    aliquota_ibs_origem = ALIQUOTAS_IBS.get(uf_origem.upper(), ALIQUOTAS_IBS['DEFAULT'])
    aliquota_ibs_destino = ALIQUOTAS_IBS.get(uf_destino.upper(), ALIQUOTAS_IBS['DEFAULT'])
    
    # Se for interestadual, aplica split (50% para cada UF)
    if uf_origem.upper() != uf_destino.upper():
        aliquota_ibs_efetiva = (aliquota_ibs_origem + aliquota_ibs_destino) / 2
    else:
        aliquota_ibs_efetiva = aliquota_ibs_origem
    
    # Monta alíquota total
    aliquota_total = aliquota_ibs_efetiva + ALIQUOTA_CBS
    
    if is_seletivo:
        aliquota_total += ALIQUOTA_IS
    
    # Calcular preço final com imposto por dentro (IVA)
    # Fórmula: Preço final = Valor base / (1 - alíquota_total)
    if aliquota_total > 0 and aliquota_total < 1:
        preco_final = valor_base / (1 - aliquota_total)
    else:
        preco_final = valor_base
    
    # Calcular cada imposto individualmente sobre o preço final
    valor_ibs = preco_final * aliquota_ibs_efetiva
    valor_cbs = preco_final * ALIQUOTA_CBS
    valor_is = preco_final * ALIQUOTA_IS if is_seletivo else 0
    
    # Valor do imposto total
    valor_impostos = valor_ibs + valor_cbs + valor_is
    
    # Ajuste fino para garantir consistência
    if abs((preco_final - valor_base) - valor_impostos) > 0.01:
        valor_impostos = preco_final - valor_base
    
    return {
        'valor_base': valor_base,
        'preco_final': preco_final,
        'valor_ibs': valor_ibs,
        'valor_cbs': valor_cbs,
        'valor_is': valor_is,
        'valor_total_impostos': valor_impostos,
        'aliquota_ibs': aliquota_ibs_efetiva,
        'aliquota_cbs': ALIQUOTA_CBS,
        'aliquota_is': ALIQUOTA_IS if is_seletivo else 0,
        'aliquota_total': aliquota_total
    }

def buscar_produtos_com_is_seletivo(ncm: str, dados_is: pd.DataFrame) -> bool:
    """Verifica se o produto (NCM) está sujeito ao Imposto Seletivo"""
    if dados_is.empty or not ncm:
        return False
    
    ncm_limpo = str(ncm).replace(".", "").strip()
    
    # Buscar na planilha de IS se existir
    if 'NCM' in dados_is.columns:
        dados_is['NCM_LIMPO'] = dados_is['NCM'].astype(str).str.replace(".", "").str.strip()
        encontrou = dados_is[dados_is['NCM_LIMPO'] == ncm_limpo]
        if not encontrou.empty:
            return True
    
    # Lista de NCMs que pagam Imposto Seletivo (exemplo - pode ser expandida)
    ncm_seletivos = [
        '22030000',  # Cervejas
        '22040000',  # Vinhos
        '22060000',  # Outras bebidas fermentadas
        '24020000',  # Cigarros
        '22021000',  # Refrigerantes
        '22029000',  # Bebidas não alcoólicas açucaradas
    ]
    
    return ncm_limpo in ncm_seletivos

def calcular_precos_2026(produto, uf_destino, forma_pagamento, tabela_desconto,
                         cliente_isento, dados_is, dados_promo, uf_origem='SP'):
    """
    Calcula preços com novo sistema tributário 2026
    """
    
    # Verificar se é promoção
    is_promo = 'SIM' in str(produto.get('Promo', '')).strip().upper()
    preco_promo = None
    
    if is_promo and not dados_promo.empty:
        preco_promo = buscar_preco_promo(produto['Referência'], uf_destino, dados_promo)
    
    # Preço base (pode vir de promoção ou tabela normal)
    if is_promo and preco_promo is not None and preco_promo > 0:
        preco_base = preco_promo
        desconto_percentual = 0.0
        valor_desconto = 0.0
        preco_com_desconto = preco_base
        if cliente_isento:
            preco_final = preco_com_desconto * 1.10
        else:
            preco_final = preco_com_desconto
    else:
        preco_base = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
        if forma_pagamento != "PREÇO BASE":
            icms_uf = determinar_icms_por_uf(uf_destino)
            desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
            valor_desconto = preco_base * desconto_percentual
            preco_com_desconto = preco_base - valor_desconto
        else:
            desconto_percentual = 0.0
            valor_desconto = 0.0
            preco_com_desconto = preco_base
        preco_final = preco_com_desconto
    
    # Valor base para cálculo dos impostos
    valor_base = preco_final
    
    # Verificar se produto tem Imposto Seletivo
    ncm_produto = produto.get('NCM', '')
    is_seletivo = buscar_produtos_com_is_seletivo(ncm_produto, dados_is)
    
    # Calcular impostos 2026
    impostos = calcular_impostos_2026(
        valor_base=valor_base,
        uf_origem=uf_origem,
        uf_destino=uf_destino,
        ncm=ncm_produto,
        is_seletivo=is_seletivo
    )
    
    # Para cliente isento, remover CBS e parte do IBS (cliente final isento)
    if cliente_isento:
        # Cliente isento não paga IBS e CBS no novo sistema
        impostos['valor_ibs'] = 0
        impostos['valor_cbs'] = 0
        impostos['preco_final'] = impostos['valor_base'] + impostos['valor_is']
        impostos['valor_total_impostos'] = impostos['valor_is']
        valor_ibs = 0
        valor_cbs = 0
        ipi_percentual = 0
        aliquota_st = 0
        valor_ipi = 0
        valor_st = 0
    else:
        valor_ibs = impostos['valor_ibs']
        valor_cbs = impostos['valor_cbs']
        ipi_percentual = 0  # IPI é extinto no novo sistema
        aliquota_st = 0     # ST é extinto no novo sistema
        valor_ipi = 0
        valor_st = 0
    
    return {
        'preco_base': preco_base,
        'desconto_percentual': desconto_percentual,
        'valor_desconto': valor_desconto,
        'preco_com_desconto': preco_com_desconto,
        'preco_final': impostos['preco_final'],
        'valor_base': valor_base,
        'valor_ibs': valor_ibs,
        'valor_cbs': valor_cbs,
        'valor_is': impostos['valor_is'],
        'valor_impostos': impostos['valor_total_impostos'],
        'aliquota_ibs': impostos['aliquota_ibs'],
        'aliquota_cbs': impostos['aliquota_cbs'],
        'aliquota_is': impostos['aliquota_is'],
        'is_seletivo': is_seletivo,
        # Campos para compatibilidade com código existente
        'ipi_percentual': ipi_percentual,
        'valor_ipi': valor_ipi,
        'st_aliquota': aliquota_st,
        'valor_st': valor_st
    }

# ============================================
# FUNÇÕES DE SEGURANÇA
# ============================================

def gerar_id_sessao() -> str:
    """Gera um ID de sessão único e seguro"""
    return secrets.token_hex(16)

def mascarar_dados_sensiveis(texto: str, tipo: str = 'email') -> str:
    """Mascara dados sensíveis para logs"""
    if not texto:
        return ''
    if tipo == 'email':
        partes = texto.split('@')
        if len(partes) == 2:
            return f"{partes[0][:3]}***@{partes[1]}"
    elif tipo == 'telefone':
        if len(texto) >= 10:
            return f"{texto[:2]}*****{texto[-3:]}"
    elif tipo == 'cnpj':
        if len(texto) >= 14:
            return f"{texto[:3]}***{texto[-3:]}"
    return '***'

def limpar_dados_sensiveis():
    """Limpa dados sensíveis do session_state após timeout"""
    if 'ultimo_acesso' in st.session_state:
        tempo_decorrido = (datetime.now() - st.session_state.ultimo_acesso).total_seconds()
        if tempo_decorrido > SESSION_TIMEOUT:
            st.session_state.dados_cliente = {}
            st.session_state.form_data = {
                'razao_social': '',
                'cnpj': '',
                'inscricao_estadual': '',
                'email': '',
                'telefone': '',
                'endereco': '',
                'numero': '',
                'bairro': '',
                'cep': ''
            }
            st.session_state.carrinho = []
            st.warning("🔒 Sessão expirada por segurança. Seus dados foram removidos.")
            return True
    st.session_state.ultimo_acesso = datetime.now()
    return False

# ============================================
# POLÍTICA DE PRIVACIDADE E TERMOS DE USO
# ============================================

def mostrar_politica_privacidade():
    """Exibe a política de privacidade"""
    with st.expander("📋 Política de Privacidade - LGPD (Lei 13.709/2018)"):
        st.markdown("""
        ### POLÍTICA DE PRIVACIDADE LUVidarte
        
        **1. DADOS COLETADOS**
        - Nome/Razão Social
        - CNPJ/CPF
        - Inscrição Estadual
        - E-mail
        - Telefone/WhatsApp
        - Endereço completo (Logradouro, Número, Bairro, CEP)
        - UF (Estado)
        - Itens do orçamento selecionados
        
        **2. FINALIDADE DA COLETA (Art. 7º da LGPD)**
        Os dados são coletados exclusivamente para:
        - Elaboração de orçamentos personalizados
        - Contato comercial para finalização do pedido
        - Emissão de notas fiscais (quando aplicável)
        - Cálculo de tributos (ICMS, IPI, ST ou IBS, CBS, IS conforme sistema vigente)
        
        **3. BASES LEGAIS (Art. 7º e 11º)**
        - Execução de contrato ou procedimentos preliminares (Art. 7º, V)
        - Legítimo interesse do controlador (Art. 7º, IX)
        - Cumprimento de obrigação legal (Art. 7º, II)
        
        **4. ARMAZENAMENTO E RETENÇÃO**
        - Seus dados NÃO são armazenados em banco de dados persistente
        - Permanecem apenas durante a sessão do navegador
        - São automaticamente excluídos após 30 minutos de inatividade
        
        **5. COMPARTILHAMENTO**
        - Seus dados são compartilhados APENAS com a equipe LUVidarte via WhatsApp
        - Não compartilhamos com terceiros, plataformas de marketing ou publicidade
        
        **6. SISTEMA TRIBUTÁRIO**
        - Oferecemos dois sistemas tributários: Tradicional (ICMS/IPI/ST) e Reforma 2026 (IBS/CBS/IS)
        - O usuário pode escolher qual sistema utilizar para simulação
        
        **Data da última atualização:** 26/04/2026
        **Versão:** 2.0 (Inclui Reforma Tributária 2026)
        """)
        
        if st.button("✅ Aceito e Concordo com a Política de Privacidade", key="aceitar_privacidade", use_container_width=True):
            st.session_state.privacidade_aceita = True
            st.session_state.consentimento_data = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            st.rerun()

def mostrar_termos_uso():
    """Exibe os termos de uso"""
    with st.expander("📜 Termos de Uso - Orçamento Virtual"):
        st.markdown("""
        ### TERMOS DE USO - ORÇAMENTO VIRTUAL LUVidarte
        
        **1. NATUREZA DO ORÇAMENTO**
        - Este é um ORÇAMENTO VIRTUAL, NÃO uma compra finalizada
        - Os valores são estimativas e sujeitas à confirmação
        - Produtos sujeitos à disponibilidade em estoque
        
        **2. VALIDADE DO ORÇAMENTO**
        - O orçamento tem validade de 7 (sete) dias corridos
        
        **3. SISTEMA TRIBUTÁRIO**
        - O cliente pode optar por visualizar os valores no sistema tradicional (ICMS/IPI/ST)
        - Ou no novo sistema da Reforma Tributária 2026 (IBS/CBS/IS)
        - Os valores são estimativas e sujeitos à legislação vigente
        
        **4. FORO**
        - Fica eleito o foro da comarca de Ferraz de Vasconcelos - SP
        
        """)

def obter_consentimento_lgpd() -> bool:
    """Verifica se o usuário já consentiu com a LGPD"""
    if 'privacidade_aceita' not in st.session_state:
        st.session_state.privacidade_aceita = False
    
    if not st.session_state.privacidade_aceita:
        st.warning("🔒 **Aviso LGPD:** Coletamos seus dados pessoais para elaboração do orçamento conforme Lei 13.709/2018.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ Recusar e Sair", use_container_width=True):
                st.error("❌ Você recusou os termos de privacidade.")
                st.stop()
        
        with col2:
            st.info("✅ Para continuar, clique em 'Política de Privacidade' abaixo e aceite os termos.")
        
        mostrar_politica_privacidade()
        mostrar_termos_uso()
        
        return False
    return True

# ============================================
# FUNÇÕES EXISTENTES (MANTIDAS ORIGINAIS)
# ============================================

def formatar_moeda(valor):
    """Formata valor para moeda brasileira: R$ 49.984,56"""
    if valor is None or valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def calcular_desconto_volume(valor_base):
    """Calcula o percentual de desconto por volume baseado no valor base"""
    if valor_base >= 4000:
        return 0.15
    elif valor_base >= 2500:
        return 0.10
    else:
        return 0.0

def calcular_faltante_para_desconto(valor_base):
    """Calcula o valor faltante para o próximo desconto"""
    if valor_base < 2500:
        return 2500 - valor_base, 10
    elif valor_base < 4000:
        return 4000 - valor_base, 15
    else:
        return 0, 0

def recalcular_item_com_desconto_volume(item, desconto_volume_percentual):
    """Aplica o desconto por volume no item (compatível com ambos sistemas)"""
    
    sistema = st.session_state.get('sistema_tributario', 'ANTIGO')
    
    if sistema == 'NOVO_2026':
        valor_base_item = item.get('valor_base', item['preco_final'])
        valor_com_desconto_volume = valor_base_item * (1 - desconto_volume_percentual)
        
        aliquota_ibs = item.get('aliquota_ibs', 0.172)
        aliquota_cbs = item.get('aliquota_cbs', 0.12)
        aliquota_is = item.get('aliquota_is', 0)
        
        aliquota_total = aliquota_ibs + aliquota_cbs + aliquota_is
        if aliquota_total > 0 and aliquota_total < 1:
            novo_preco_final = valor_com_desconto_volume / (1 - aliquota_total)
        else:
            novo_preco_final = valor_com_desconto_volume
        
        novo_valor_ibs = novo_preco_final * aliquota_ibs
        novo_valor_cbs = novo_preco_final * aliquota_cbs
        novo_valor_is = novo_preco_final * aliquota_is
        
        return {
            'preco_final_com_desconto': valor_com_desconto_volume,
            'valor_ibs': novo_valor_ibs,
            'valor_cbs': novo_valor_cbs,
            'valor_is': novo_valor_is,
            'total_geral': novo_preco_final
        }
    else:
        # Sistema antigo
        valor_base_item = item['preco_final']
        valor_com_desconto_volume = valor_base_item * (1 - desconto_volume_percentual)
        
        ipi_aliquota_efetiva = item['valor_ipi'] / item['preco_final'] if item['preco_final'] > 0 else 0
        st_aliquota_efetiva = item['valor_st'] / item['preco_final'] if item['preco_final'] > 0 else 0
        
        novo_valor_ipi = valor_com_desconto_volume * ipi_aliquota_efetiva
        novo_valor_st = valor_com_desconto_volume * st_aliquota_efetiva
        novo_total_geral = valor_com_desconto_volume + novo_valor_ipi + novo_valor_st
        
        return {
            'preco_final_com_desconto': valor_com_desconto_volume,
            'valor_ipi': novo_valor_ipi,
            'valor_st': novo_valor_st,
            'total_geral': novo_total_geral
        }

def gerar_html_orcamento(dados_cliente, itens_carrinho, uf, tipo_cliente, forma_pagamento, 
                         desconto_volume_percentual, valor_base_total, valor_desconto_volume,
                         total_final, total_ipi, total_st, sistema_tributario='ANTIGO'):
    """Gera um HTML com o orçamento detalhado (suporta ambos sistemas)"""
    
    novo_valor_base = valor_base_total - valor_desconto_volume
    
    data_geracao = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    id_documento = hashlib.sha256(f"{dados_cliente.get('cnpj', '')}{data_geracao}".encode()).hexdigest()[:8]
    
    # Título do sistema tributário
    if sistema_tributario == 'NOVO_2026':
        titulo_tributos = "IBS + CBS + IS (Reforma Tributária 2026)"
    else:
        titulo_tributos = "ICMS + IPI + ST (Sistema Tradicional)"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Orçamento LUVidarte - Confidencial</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .header h1 {{ color: #2E7D32; }}
            .section {{ margin-bottom: 20px; }}
            .section-title {{ color: #2E7D32; border-bottom: 2px solid #C9A03D; padding-bottom: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #2E7D32; color: white; }}
            .total {{ font-weight: bold; font-size: 18px; color: #D32F2F; text-align: right; }}
            .footer {{ margin-top: 30px; font-size: 12px; text-align: center; color: #666; }}
            .lgpd-notice {{ background-color: #FFF9E6; border-left: 4px solid #C9A03D; 
                           padding: 10px; margin: 20px 0; font-size: 11px; }}
            .confidencial {{ background-color: #FFEBEE; border-left: 4px solid #D32F2F;
                           padding: 10px; margin: 20px 0; font-size: 11px; }}
            .sistema-badge {{ background-color: #E3F2FD; border-left: 4px solid #2196F3;
                           padding: 8px; margin: 10px 0; font-size: 12px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="confidencial">
            🔒 <strong>DOCUMENTO CONFIDENCIAL</strong> - ID: {id_documento}<br>
            Gerado em: {data_geracao}
        </div>
        
        <div class="sistema-badge">
            📊 <strong>Sistema Tributário:</strong> {titulo_tributos}
        </div>
        
        <div class="header">
            <h1>LUVidarte - Orçamento Virtual</h1>
        </div>
        
        <div class="section">
            <h2 class="section-title">DADOS DO CLIENTE</h2>
            <p><strong>Razão Social:</strong> {dados_cliente.get('razao_social', '')}</p>
            <p><strong>CNPJ/CPF:</strong> {dados_cliente.get('cnpj', '')}</p>
            <p><strong>E-mail:</strong> {dados_cliente.get('email', '')}</p>
            <p><strong>Telefone:</strong> {dados_cliente.get('telefone', '')}</p>
            <p><strong>Endereço:</strong> {dados_cliente.get('endereco', '')}, {dados_cliente.get('numero', '')}</p>
            <p><strong>UF:</strong> {uf}</p>
        </div>
        
        <div class="section">
            <h2 class="section-title">INFORMAÇÕES DO ORÇAMENTO</h2>
            <p><strong>Data de Geração:</strong> {data_geracao}</p>
            <p><strong>Tipo de Cliente:</strong> {tipo_cliente}</p>
            <p><strong>Condição de Pagamento:</strong> {forma_pagamento}</p>
            <p><strong>Validade do Orçamento:</strong> 7 dias corridos</p>
        </div>
        
        <div class="section">
            <h2 class="section-title">ITENS DO ORÇAMENTO</h2>
            <table>
                <thead>
                    <tr>
                        <th>Código</th>
                        <th>Descrição</th>
                        <th>Qtd</th>
                        <th>Valor Unit.</th>
                        <th>Subtotal</th>
    """
    
    # Adicionar colunas específicas do sistema
    if sistema_tributario == 'NOVO_2026':
        html_content += """
                        <th>IBS</th>
                        <th>CBS</th>
                        <th>IS</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
        """
    else:
        html_content += """
                        <th>IPI</th>
                        <th>ST</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
        """
    
    total_ibs = 0
    total_cbs = 0
    total_is = 0
    total_ipi_exibido = 0
    total_st_exibido = 0
    
    for item in itens_carrinho:
        valor_base_item = item['preco_final']
        valor_com_desconto_item = valor_base_item * (1 - desconto_volume_percentual)
        
        if sistema_tributario == 'NOVO_2026':
            aliquota_ibs = item.get('aliquota_ibs', 0.172)
            aliquota_cbs = item.get('aliquota_cbs', 0.12)
            aliquota_is = item.get('aliquota_is', 0)
            
            aliquota_total = aliquota_ibs + aliquota_cbs + aliquota_is
            if aliquota_total > 0 and aliquota_total < 1:
                preco_final_item = valor_com_desconto_item / (1 - aliquota_total)
            else:
                preco_final_item = valor_com_desconto_item
            
            ibs_unitario = preco_final_item * aliquota_ibs
            cbs_unitario = preco_final_item * aliquota_cbs
            is_unitario = preco_final_item * aliquota_is
            
            subtotal_item = valor_com_desconto_item * item['quantidade']
            ibs_total = ibs_unitario * item['quantidade']
            cbs_total = cbs_unitario * item['quantidade']
            is_total = is_unitario * item['quantidade']
            total_item = preco_final_item * item['quantidade']
            
            total_ibs += ibs_total
            total_cbs += cbs_total
            total_is += is_total
            
            html_content += f"""
                        <tr>
                            <td>{item['referencia']}</td>
                            <td>{item['descricao'][:50]}</td>
                            <td style="text-align:center">{item['quantidade']}</td>
                            <td style="text-align:right">{formatar_moeda(preco_final_item)}</td>
                            <td style="text-align:right">{formatar_moeda(subtotal_item)}</td>
                            <td style="text-align:right">{formatar_moeda(ibs_total)}</td>
                            <td style="text-align:right">{formatar_moeda(cbs_total)}</td>
                            <td style="text-align:right">{formatar_moeda(is_total)}</td>
                            <td style="text-align:right">{formatar_moeda(total_item)}</td>
                        </tr>
            """
        else:
            ipi_aliquota_efetiva = item['valor_ipi'] / item['preco_final'] if item['preco_final'] > 0 else 0
            st_aliquota_efetiva = item['valor_st'] / item['preco_final'] if item['preco_final'] > 0 else 0
            
            novo_ipi_unitario = valor_com_desconto_item * ipi_aliquota_efetiva
            novo_st_unitario = valor_com_desconto_item * st_aliquota_efetiva
            
            subtotal_item = valor_com_desconto_item * item['quantidade']
            ipi_total_item = novo_ipi_unitario * item['quantidade']
            st_total_item = novo_st_unitario * item['quantidade']
            total_item = (valor_com_desconto_item + novo_ipi_unitario + novo_st_unitario) * item['quantidade']
            
            total_ipi_exibido += ipi_total_item
            total_st_exibido += st_total_item
            
            html_content += f"""
                        <tr>
                            <td>{item['referencia']}</td>
                            <td>{item['descricao'][:50]}</td>
                            <td style="text-align:center">{item['quantidade']}</td>
                            <td style="text-align:right">{formatar_moeda(valor_com_desconto_item)}</td>
                            <td style="text-align:right">{formatar_moeda(subtotal_item)}</td>
                            <td style="text-align:right">{formatar_moeda(ipi_total_item) if ipi_total_item > 0 else '-'}</td>
                            <td style="text-align:right">{formatar_moeda(st_total_item) if st_total_item > 0 else '-'}</td>
                            <td style="text-align:right">{formatar_moeda(total_item)}</td>
                        </tr>
            """
    
    html_content += """
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2 class="section-title">RESUMO FINAL</h2>
            <p><strong>Valor Base Original:</strong> {}</p>
            <p><strong>Desconto por Volume ({}%):</strong> -{}</p>
            <p><strong>Novo Valor Base:</strong> {}</p>
    """.format(
        formatar_moeda(valor_base_total),
        int(desconto_volume_percentual*100),
        formatar_moeda(valor_desconto_volume),
        formatar_moeda(novo_valor_base)
    )
    
    if sistema_tributario == 'NOVO_2026':
        html_content += f"""
            <p><strong>IBS Total:</strong> {formatar_moeda(total_ibs)}</p>
            <p><strong>CBS Total:</strong> {formatar_moeda(total_cbs)}</p>
            <p><strong>Imposto Seletivo Total:</strong> {formatar_moeda(total_is)}</p>
            <p class="total"><strong>TOTAL GERAL DO ORÇAMENTO:</strong> {formatar_moeda(total_final)}</p>
        """
    else:
        html_content += f"""
            <p><strong>IPI Total:</strong> {formatar_moeda(total_ipi_exibido)}</p>
            <p><strong>ST Total:</strong> {formatar_moeda(total_st_exibido)}</p>
            <p class="total"><strong>TOTAL GERAL DO ORÇAMENTO:</strong> {formatar_moeda(total_final)}</p>
        """
    
    html_content += f"""
        </div>
        
        <div class="lgpd-notice">
            🔒 <strong>LGPD - LEI GERAL DE PROTEÇÃO DE DADOS (Lei 13.709/2018)</strong><br><br>
            • Seus dados são tratados com confidencialidade e utilizados APENAS para este orçamento<br>
            • Você pode solicitar a exclusão dos seus dados a qualquer momento<br>
            • Este documento é de uso exclusivo da LUVidarte e do cliente<br><br>
            <strong>Encarregado (DPO):</strong> privacidade@luvidarte.com.br | (11) 4676-9000
        </div>
        
        <div class="footer">
            <p><strong>LUVidarte - Peças exclusivas em vidro e decoração</strong></p>
            <p>Rua Caetano Rubio, 213 - Ferraz de Vasconcelos - SP | CEP: 08533-060</p>
            <p>Tel: (11) 4676-9000 | WhatsApp: (11) 93011-9335</p>
            <p>⚠️ <strong>AVISO IMPORTANTE:</strong> Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada.</p>
            <p><strong>Validade do orçamento: 7 (sete) dias corridos.</strong></p>
            <p>© 2026 LUVidarte - Todos os direitos reservados</p>
        </div>
    </body>
    </html>
    """
    
    return html_content.encode('utf-8')

def formatar_mensagem_whatsapp(dados_cliente, uf, tipo_cliente, forma_pagamento, total_final,
                                desconto_volume_percentual, valor_desconto_volume, valor_base_total,
                                total_imposto1, total_imposto2, sistema_tributario='ANTIGO'):
    """Formata a mensagem para WhatsApp com resumo do orçamento"""
    
    msg = "🛍️ NOVO ORÇAMENTO LUVidarte 🛍️\n\n"
    msg += "━" * 30 + "\n\n"
    
    if sistema_tributario == 'NOVO_2026':
        msg += "📊 SISTEMA TRIBUTÁRIO: REFORMA 2026 (IBS + CBS + IS)\n\n"
    else:
        msg += "📊 SISTEMA TRIBUTÁRIO: TRADICIONAL (ICMS + IPI + ST)\n\n"
    
    msg += "DADOS DO CLIENTE\n"
    msg += f"🏢 Razão Social: {dados_cliente.get('razao_social', '')}\n"
    msg += f"📄 CNPJ/CPF: {dados_cliente.get('cnpj', '')}\n"
    msg += f"📧 E-mail: {dados_cliente.get('email', '')}\n"
    msg += f"📞 Telefone: {dados_cliente.get('telefone', '')}\n"
    msg += f"📍 Endereço: {dados_cliente.get('endereco', '')}, {dados_cliente.get('numero', '')}\n"
    msg += f"🗺️ UF: {uf}\n\n"
    msg += "━" * 30 + "\n\n"
    msg += "RESUMO DO ORÇAMENTO\n"
    msg += f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    msg += f"👤 Tipo Cliente: {tipo_cliente}\n"
    msg += f"💳 Pagamento: {forma_pagamento}\n"
    
    if desconto_volume_percentual > 0:
        novo_valor_base = valor_base_total - valor_desconto_volume
        msg += f"🎉 DESCONTO POR VOLUME: {int(desconto_volume_percentual*100)}%\n"
        msg += f"💰 Valor Base Original: {formatar_moeda(valor_base_total)}\n"
        msg += f"💰 Desconto: {formatar_moeda(valor_desconto_volume)}\n"
        msg += f"💰 Novo Valor Base: {formatar_moeda(novo_valor_base)}\n"
    
    msg += f"\n💰 TOTAL DO ORÇAMENTO: {formatar_moeda(total_final)}\n\n"
    msg += "📋 Próximos passos:\n"
    msg += "1️⃣ Aguarde o contato da nossa equipe\n"
    msg += "2️⃣ Confirmaremos disponibilidade dos produtos\n\n"
    msg += "✨ Agradecemos a preferência! ✨"
    
    return msg

# ============================================
# FUNÇÕES EXISTENTES (MANTIDAS ORIGINAIS)
# ============================================

def validar_cnpj(cnpj):
    """Valida se o CNPJ é válido"""
    cnpj = re.sub(r'[^0-9]', '', str(cnpj))
    if len(cnpj) != 14:
        return False
    if len(set(cnpj)) == 1:
        return False
    peso1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(int(cnpj[i]) * peso1[i] for i in range(12))
    digito1 = 11 - (soma1 % 11)
    if digito1 >= 10:
        digito1 = 0
    peso2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma2 = sum(int(cnpj[i]) * peso2[i] for i in range(13))
    digito2 = 11 - (soma2 % 11)
    if digito2 >= 10:
        digito2 = 0
    return int(cnpj[12]) == digito1 and int(cnpj[13]) == digito2

def validar_email(email):
    """Valida se o email tem formato correto"""
    padrao = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(padrao, email) is not None

def validar_telefone(telefone):
    """Valida se o telefone tem formato correto"""
    telefone = re.sub(r'[^0-9]', '', str(telefone))
    return len(telefone) >= 10 and len(telefone) <= 11

def validar_cep(cep):
    """Valida se o CEP tem formato correto"""
    cep = re.sub(r'[^0-9]', '', str(cep))
    return len(cep) == 8

# ============================================
# FUNÇÕES DE CARREGAMENTO (MANTIDAS ORIGINAIS)
# ============================================

@st.cache_data(ttl=600)
def carregar_planilha(id_planilha, nome_aba="base"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        if 'Codigo SISTEMA' in df.columns:
            df = df.rename(columns={'Codigo SISTEMA': 'Promo'})
        if 'Preço Bruto' in df.columns:
            df['Preço'] = df['Preço Bruto'].apply(converter_moeda_para_numero)
        df['GRUPO'] = df['GRUPO'].fillna('Outros')
        df['Descrição'] = df['Descrição'].fillna('Produto sem descrição')
        df['Referência'] = df['Referência'].fillna('').astype(str)
        if 'Promo' not in df.columns:
            df['Promo'] = ''
        if 'ml' in df.columns:
            df['ml'] = pd.to_numeric(df['ml'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar a planilha: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_planilha_promo(id_planilha, nome_aba="PROMO"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_base_st(id_planilha_st, nome_aba_st="BASE_ST"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha_st}/gviz/tq?tqx=out:csv&sheet={nome_aba_st}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_descontos_normal(id_planilha, nome_aba="NORMAL"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_descontos_isento(id_planilha, nome_aba="ISENTO"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_base_is(id_planilha, nome_aba_is="IMPOSTO_SELETIVO"):
    """Carrega produtos sujeitos ao Imposto Seletivo (2026)"""
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba_is}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

def converter_moeda_para_numero(valor):
    if pd.isna(valor) or valor == '' or valor is None:
        return np.nan
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    s = re.sub(r'[^0-9.]', '', s)
    try:
        return float(s)
    except:
        return np.nan

def converter_percentual_para_numero(valor):
    if pd.isna(valor) or valor == '' or valor is None:
        return 0.0
    s = str(valor).strip().replace('%', '').replace(',', '.')
    try:
        p = float(s)
        if p > 1 and p <= 100:
            p = p / 100
        return p
    except:
        return 0.0

def formatar_ml(valor):
    if pd.isna(valor) or valor == 0 or valor is None or valor == '':
        return None
    try:
        v = float(valor)
        if v >= 1000:
            return f"{v/1000:.3f} L"
        return f"{int(v)} ml" if v == int(v) else f"{v:.3f}".rstrip('0').rstrip('.') + " ml"
    except:
        return None

def buscar_preco_promo(referencia: str, uf: str, df_promo: pd.DataFrame) -> float:
    if df_promo.empty or not referencia:
        return None
    ref_limpa = str(referencia).strip()
    coluna_ref = df_promo.columns[0]
    df_promo[coluna_ref] = df_promo[coluna_ref].astype(str).str.strip()
    linha = df_promo[df_promo[coluna_ref] == ref_limpa]
    if linha.empty:
        linha = df_promo[df_promo[coluna_ref].str.contains(ref_limpa, case=False, na=False)]
        if linha.empty:
            return None
    uf_upper = uf.upper()
    if uf_upper == "SP":
        col_icms = "18%"
    elif uf_upper in ["MG", "RS", "SE", "PR", "RJ", "SC"]:
        col_icms = "12%"
    else:
        col_icms = "7%"
    col_preco = next((c for c in df_promo.columns if str(c).strip() == col_icms), None)
    if col_preco is None:
        return None
    valor = linha.iloc[0][col_preco]
    if pd.isna(valor):
        return None
    if isinstance(valor, str):
        valor = valor.strip().replace('.', '').replace(',', '.')
        try:
            valor = float(valor)
        except:
            return None
    return float(valor) if not pd.isna(valor) else None

def buscar_ipi(ncm: str, df_st: pd.DataFrame) -> float:
    if df_st.empty or not ncm:
        return 0.0
    ncm_limpo = str(ncm).replace(".", "").strip()
    df_st['NCM_LIMPO'] = df_st.iloc[:, 1].astype(str).str.replace(".", "").str.strip()
    linha = df_st[df_st['NCM_LIMPO'] == ncm_limpo]
    if linha.empty:
        return 0.0
    v = linha.iloc[0, 0]
    if pd.isna(v):
        return 0.0
    if isinstance(v, str):
        v = v.replace("%", "").replace(",", ".").strip()
    try:
        ipi = float(v)
        if ipi > 1 and ipi <= 100:
            ipi = ipi / 100
        return ipi
    except:
        return 0.0

def determinar_icms_por_uf(uf: str) -> float:
    u = uf.upper()
    if u == "SP":
        return 18.0
    elif u in ["MG", "RS", "SE", "PR", "RJ", "SC"]:
        return 12.0
    return 7.0

def buscar_aliquota_st(ncm: str, uf: str, df_st: pd.DataFrame) -> float:
    if df_st.empty or not ncm or not uf:
        return 0.0
    ncm_limpo = str(ncm).replace(".", "").strip()
    df_st['NCM_LIMPO'] = df_st.iloc[:, 1].astype(str).str.replace(".", "").str.strip()
    linha_ncm = df_st[df_st['NCM_LIMPO'] == ncm_limpo]
    if linha_ncm.empty:
        return 0.0
    uf_upper = uf.upper().strip()
    colunas_uf = {}
    for col in df_st.columns[2:]:
        col_clean = str(col).strip().upper()
        colunas_uf[col_clean] = col
    if uf_upper not in colunas_uf:
        for col_key in colunas_uf.keys():
            if uf_upper in col_key or col_key in uf_upper:
                nome_coluna = colunas_uf[col_key]
                break
        else:
            return 0.0
    else:
        nome_coluna = colunas_uf[uf_upper]
    valor = linha_ncm.iloc[0][nome_coluna]
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, str):
        valor = valor.replace("%", "").replace(",", ".").strip()
    try:
        aliquota = float(valor)
        if aliquota > 1 and aliquota <= 100:
            aliquota = aliquota / 100
        return aliquota
    except:
        return 0.0

def buscar_desconto(icms: float, forma_pagamento: str, df_desconto: pd.DataFrame) -> float:
    if df_desconto.empty or forma_pagamento == "PREÇO BASE":
        return 0.0
    df_temp = df_desconto.copy()
    df_temp['ICMS_LIMPO'] = pd.to_numeric(
        df_temp['ICMS'].astype(str).str.replace('%', '').str.replace(',', '.').str.strip(),
        errors='coerce'
    )
    df_temp['FORMA_LIMPO'] = df_temp['FORMA'].apply(lambda x: str(x).strip() if pd.notna(x) else "")
    forma_para_buscar = "" if forma_pagamento == "VISTA" else f"{float(forma_pagamento):.1f}"
    df_f = df_temp[(df_temp['ICMS_LIMPO'] == float(icms)) & (df_temp['FORMA_LIMPO'] == forma_para_buscar)]
    if not df_f.empty:
        return converter_percentual_para_numero(df_f.iloc[0]['DESCONTO'])
    return 0.0

def carregar_logo():
    url_drive = "https://drive.google.com/uc?export=download&id=1wiwp3txOXGsEMRrUgzdLFlxQL2188uTw"
    try:
        r = requests.get(url_drive, timeout=15)
        if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
            return Image.open(BytesIO(r.content))
    except:
        pass
    return None

def carregar_logo_favicon():
    url_drive = "https://drive.google.com/uc?export=download&id=1wiwp3txOXGsEMRrUgzdLFlxQL2188uTw"
    try:
        response = requests.get(url_drive, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img = img.resize((32, 32))
            return img
    except:
        pass
    return None

# ============================================
# FUNÇÕES DO CARRINHO
# ============================================

def adicionar_ao_carrinho(produto, quantidade, preco_bruto, desconto_percentual,
                           valor_desconto, preco_com_desconto, preco_final,
                           valor_ipi, valor_st, ipi_percentual, aliquota_st, valor_total,
                           sistema_tributario='ANTIGO'):
    
    sistema = st.session_state.get('sistema_tributario', 'ANTIGO')
    
    for item in st.session_state.carrinho:
        if item['referencia'] == produto['Referência']:
            item['quantidade'] += quantidade
            item['preco_total'] = item['preco_final'] * item['quantidade']
            if sistema == 'NOVO_2026':
                item['total_geral'] = item['preco_final'] * item['quantidade']
            else:
                item['ipi_total'] = item['valor_ipi'] * item['quantidade']
                item['st_total'] = item['valor_st'] * item['quantidade']
                item['total_geral'] = (item['preco_final'] + item['valor_ipi'] + item['valor_st']) * item['quantidade']
            return True
    
    # Item base para ambos sistemas
    item_base = {
        'referencia': produto['Referência'],
        'descricao': produto['Descrição'],
        'grupo': produto['GRUPO'],
        'quantidade': quantidade,
        'preco_bruto': preco_bruto,
        'desconto_percentual': desconto_percentual,
        'valor_desconto': valor_desconto,
        'preco_com_desconto': preco_com_desconto,
        'preco_final': preco_final,
        'preco_unitario': preco_final,
        'preco_total': preco_final * quantidade,
        'medidas': produto.get('Medidas', ''),
        'ml': produto.get('ml', ''),
        'imagem_url': produto.get('imagem_url', '')
    }
    
    if sistema == 'NOVO_2026':
        # Adiciona campos do novo sistema
        item_base.update({
            'valor_base': valor_total if valor_total else preco_final,
            'valor_ibs': valor_ipi,
            'valor_cbs': valor_st,
            'valor_is': 0,
            'aliquota_ibs': ipi_percentual if ipi_percentual else 0.172,
            'aliquota_cbs': aliquota_st if aliquota_st else 0.12,
            'aliquota_is': 0,
            'ipi_percentual': 0,
            'valor_ipi': 0,
            'st_aliquota': 0,
            'valor_st': 0,
            'total_geral': preco_final * quantidade
        })
    else:
        # Adiciona campos do sistema antigo
        item_base.update({
            'ipi_percentual': ipi_percentual,
            'valor_ipi': valor_ipi,
            'ipi_total': valor_ipi * quantidade,
            'st_aliquota': aliquota_st,
            'valor_st': valor_st,
            'st_total': valor_st * quantidade,
            'total_geral': (preco_final + valor_ipi + valor_st) * quantidade
        })
    
    st.session_state.carrinho.append(item_base)
    return True

def remover_do_carrinho(indice):
    if 0 <= indice < len(st.session_state.carrinho):
        st.session_state.carrinho.pop(indice)

def limpar_carrinho():
    st.session_state.carrinho = []
    st.session_state.mostrar_formulario_cliente = False
    st.session_state.mostrar_botoes_envio = False
    st.session_state.html_bytes = None

def atualizar_quantidade_carrinho(indice, nova_quantidade):
    if 0 <= indice < len(st.session_state.carrinho):
        item = st.session_state.carrinho[indice]
        item['quantidade'] = nova_quantidade
        item['preco_total'] = item['preco_final'] * nova_quantidade
        
        sistema = st.session_state.get('sistema_tributario', 'ANTIGO')
        if sistema == 'NOVO_2026':
            item['total_geral'] = item['preco_final'] * nova_quantidade
        else:
            item['ipi_total'] = item['valor_ipi'] * nova_quantidade
            item['st_total'] = item['valor_st'] * nova_quantidade
            item['total_geral'] = (item['preco_final'] + item['valor_ipi'] + item['valor_st']) * nova_quantidade
        return True
    return False

def recalcular_todo_carrinho(uf, cliente_isento, forma_pagamento,
                              dados_st, dados_promo, dados, dados_normal, dados_isento,
                              sistema_tributario='ANTIGO'):
    if not st.session_state.carrinho:
        return
    
    icms_uf = determinar_icms_por_uf(uf)
    tabela_desconto = dados_isento if cliente_isento else dados_normal
    
    for item in st.session_state.carrinho:
        referencia = item['referencia']
        produto_dados = dados[dados['Referência'] == referencia]
        if produto_dados.empty:
            continue
        produto = produto_dados.iloc[0]
        
        if sistema_tributario == 'NOVO_2026':
            # Usa novo sistema
            resultado = calcular_precos_2026(
                produto, uf, forma_pagamento, tabela_desconto,
                cliente_isento, pd.DataFrame(), dados_promo
            )
            
            item['preco_bruto'] = resultado['preco_base']
            item['desconto_percentual'] = resultado['desconto_percentual']
            item['valor_desconto'] = resultado['valor_desconto']
            item['preco_com_desconto'] = resultado['preco_com_desconto']
            item['preco_final'] = resultado['preco_final']
            item['valor_base'] = resultado['valor_base']
            item['valor_ibs'] = resultado['valor_ibs']
            item['valor_cbs'] = resultado['valor_cbs']
            item['valor_is'] = resultado['valor_is']
            item['aliquota_ibs'] = resultado['aliquota_ibs']
            item['aliquota_cbs'] = resultado['aliquota_cbs']
            item['aliquota_is'] = resultado['aliquota_is']
            item['total_geral'] = resultado['preco_final'] * item['quantidade']
        else:
            # Sistema antigo original
            is_promo = 'SIM' in str(produto.get('Promo', '')).strip().upper()
            preco_promo = None
            if is_promo and not dados_promo.empty:
                preco_promo = buscar_preco_promo(referencia, uf, dados_promo)
            
            if is_promo and preco_promo is not None and preco_promo > 0:
                preco_bruto = preco_promo
                desconto_percentual = 0.0
                valor_desconto = 0.0
                preco_com_desconto = preco_bruto
                if cliente_isento:
                    preco_final = preco_com_desconto * 1.10
                else:
                    preco_final = preco_com_desconto
            else:
                preco_bruto = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
                if forma_pagamento != "PREÇO BASE":
                    desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
                    valor_desconto = preco_bruto * desconto_percentual
                    preco_com_desconto = preco_bruto - valor_desconto
                else:
                    desconto_percentual = 0.0
                    valor_desconto = 0.0
                    preco_com_desconto = preco_bruto
                preco_final = preco_com_desconto
            
            ncm_produto = produto.get('NCM', '')
            ipi_percentual = buscar_ipi(ncm_produto, dados_st)
            valor_ipi = preco_final * ipi_percentual
            aliquota_st = buscar_aliquota_st(ncm_produto, uf, dados_st)
            valor_st = 0.0 if cliente_isento else preco_final * aliquota_st
            
            item['preco_bruto'] = preco_bruto
            item['desconto_percentual'] = desconto_percentual
            item['valor_desconto'] = valor_desconto
            item['preco_com_desconto'] = preco_com_desconto
            item['preco_final'] = preco_final
            item['preco_unitario'] = preco_final
            item['preco_total'] = preco_final * item['quantidade']
            item['ipi_percentual'] = ipi_percentual
            item['valor_ipi'] = valor_ipi
            item['ipi_total'] = valor_ipi * item['quantidade']
            item['st_aliquota'] = aliquota_st
            item['valor_st'] = valor_st
            item['st_total'] = valor_st * item['quantidade']
            item['total_geral'] = (preco_final + valor_ipi + valor_st) * item['quantidade']

def calcular_resumo_carrinho():
    if not st.session_state.carrinho:
        return {'total_itens': 0, 'total_geral': 0.0, 'total_ipi': 0.0,
                'total_st': 0.0, 'total_desconto': 0.0, 'total_bruto': 0.0}
    
    sistema = st.session_state.get('sistema_tributario', 'ANTIGO')
    
    valor_base_total = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
    desconto_vol = calcular_desconto_volume(valor_base_total)
    
    total_com_desconto = 0
    total_ipi = 0
    total_st = 0
    total_ibs = 0
    total_cbs = 0
    total_is = 0
    
    for item in st.session_state.carrinho:
        item_com_desconto = recalcular_item_com_desconto_volume(item, desconto_vol)
        
        if sistema == 'NOVO_2026':
            total_com_desconto += item_com_desconto['total_geral'] * item['quantidade']
            total_ibs += item.get('valor_ibs', 0) * item['quantidade']
            total_cbs += item.get('valor_cbs', 0) * item['quantidade']
            total_is += item.get('valor_is', 0) * item['quantidade']
        else:
            total_com_desconto += item_com_desconto['total_geral'] * item['quantidade']
            total_ipi += item.get('valor_ipi', 0) * item['quantidade']
            total_st += item.get('valor_st', 0) * item['quantidade']
    
    return {
        'total_itens': sum(i['quantidade'] for i in st.session_state.carrinho),
        'total_geral': total_com_desconto,
        'total_ipi': total_ipi,
        'total_st': total_st,
        'total_ibs': total_ibs,
        'total_cbs': total_cbs,
        'total_is': total_is,
        'total_desconto': sum(i.get('valor_desconto', 0) * i['quantidade'] for i in st.session_state.carrinho),
        'total_bruto': sum(i['preco_bruto'] * i['quantidade'] for i in st.session_state.carrinho),
        'desconto_volume_percentual': desconto_vol,
        'valor_base_total': valor_base_total,
        'valor_desconto_volume': valor_base_total * desconto_vol,
        'novo_valor_base': valor_base_total * (1 - desconto_vol)
    }

def abrir_carrinho():
    st.session_state.carrinho_aberto = True
    st.rerun()

def fechar_carrinho():
    st.session_state.carrinho_aberto = False
    st.rerun()

def mostrar_formulario():
    st.session_state.mostrar_formulario_cliente = True
    st.rerun()

def cancelar_formulario():
    st.session_state.mostrar_formulario_cliente = False
    st.session_state.mostrar_botoes_envio = False
    st.session_state.html_bytes = None
    st.rerun()

def gerar_botao_desconto_flutuante():
    """Gera o HTML/CSS para o botão flutuante de desconto"""
    
    if st.session_state.carrinho:
        valor_base_total = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
        desconto_percentual = calcular_desconto_volume(valor_base_total)
        faltante, prox_desconto = calcular_faltante_para_desconto(valor_base_total)
        
        if desconto_percentual == 0.15:
            mensagem = f"🏆 PARABÉNS! Você atingiu 15% de desconto máximo!"
            cor = "#FF9800"
            icone = "🏆"
            texto_desconto = "15% OFF"
        elif desconto_percentual == 0.10:
            mensagem = f"✅ Você já tem 10% de desconto! Faltam {formatar_moeda(faltante)} para 15%"
            cor = "#4CAF50"
            icone = "🎯"
            texto_desconto = "10% OFF"
        else:
            if faltante > 0:
                mensagem = f"📈 Adicione mais {formatar_moeda(faltante)} e ganhe {prox_desconto}% de desconto!"
            else:
                mensagem = f"💰 Adicione produtos para ganhar desconto por volume!"
            cor = "#2196F3"
            icone = "📈"
            texto_desconto = "0% OFF"
        
        if valor_base_total >= 4000:
            progresso = 100
        elif valor_base_total >= 2500:
            progresso = 75 + ((valor_base_total - 2500) / 1500) * 25
        else:
            progresso = (valor_base_total / 2500) * 75
        progresso = min(100, max(0, progresso))
    else:
        mensagem = "💰 Adicione produtos para ganhar desconto por volume!"
        faltante = 2500
        prox_desconto = 10
        cor = "#9E9E9E"
        icone = "💰"
        texto_desconto = "0% OFF"
        progresso = 0
    
    html = f"""
    <style>
    @keyframes slideInRight {{
        from {{ transform: translateX(100%); opacity: 0; }}
        to {{ transform: translateX(0); opacity: 1; }}
    }}
    
    @keyframes pulse {{
        0% {{ transform: scale(1); }}
        50% {{ transform: scale(1.05); }}
        100% {{ transform: scale(1); }}
    }}
    
    .desconto-float {{
        position: fixed;
        bottom: 100px;
        right: 20px;
        z-index: 99999;
        animation: slideInRight 0.5s ease-out;
        cursor: pointer;
    }}
    
    .desconto-card {{
        background: linear-gradient(135deg, #FFF, #F5F5F5);
        border-radius: 16px;
        padding: 12px 18px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        border-left: 4px solid {cor};
        min-width: 280px;
        max-width: 320px;
        transition: all 0.3s ease;
    }}
    
    .desconto-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 12px 28px rgba(0,0,0,0.2);
    }}
    
    .desconto-header {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
    }}
    
    .desconto-icon {{
        font-size: 28px;
        animation: pulse 2s infinite;
    }}
    
    .desconto-title {{
        font-size: 14px;
        font-weight: bold;
        color: #333;
        margin: 0;
    }}
    
    .desconto-message {{
        font-size: 12px;
        color: #555;
        margin: 8px 0;
        line-height: 1.4;
    }}
    
    .desconto-value {{
        font-size: 18px;
        font-weight: bold;
        color: {cor};
        margin: 5px 0;
    }}
    
    .progress-bar-container {{
        background-color: #E0E0E0;
        border-radius: 10px;
        height: 8px;
        margin: 10px 0;
        overflow: hidden;
    }}
    
    .progress-bar-fill {{
        background: linear-gradient(90deg, {cor}, #FF9800);
        width: {progresso}%;
        height: 100%;
        border-radius: 10px;
        transition: width 0.5s ease;
    }}
    
    .progress-labels {{
        display: flex;
        justify-content: space-between;
        font-size: 9px;
        color: #666;
        margin-top: 5px;
    }}
    
    .close-btn {{
        position: absolute;
        top: 5px;
        right: 10px;
        background: none;
        border: none;
        font-size: 16px;
        cursor: pointer;
        color: #999;
        transition: color 0.2s;
    }}
    
    .close-btn:hover {{
        color: #333;
    }}
    
    @media (max-width: 768px) {{
        .desconto-card {{
            min-width: 260px;
            padding: 10px 15px;
        }}
        .desconto-float {{
            bottom: 90px;
            right: 10px;
        }}
    }}
    </style>
    
    <div class="desconto-float" id="descontoFloat">
        <div class="desconto-card">
            <button class="close-btn" onclick="document.getElementById('descontoFloat').style.display='none'">✕</button>
            <div class="desconto-header">
                <div class="desconto-icon">{icone}</div>
                <div>
                    <div class="desconto-title">💎 DESCONTO POR VOLUME</div>
                    <div class="desconto-value">{texto_desconto}</div>
                </div>
            </div>
            <div class="desconto-message">{mensagem}</div>
            <div class="progress-bar-container">
                <div class="progress-bar-fill"></div>
            </div>
            <div class="progress-labels">
                <span>💰 R$ 0</span>
                <span>🎯 10% (R$ 2.500)</span>
                <span>🏆 15% (R$ 4.000)</span>
            </div>
        </div>
    </div>
    """
    return html

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================

# Verificar consentimento LGPD antes de continuar
if not obter_consentimento_lgpd():
    st.stop()

# Verificar timeout da sessão
limpar_dados_sensiveis()

favicon = carregar_logo_favicon()
if favicon:
    st.set_page_config(
        page_title="Luvidarte - Catálogo Virtual",
        page_icon=favicon,
        layout="wide"
    )
else:
    st.set_page_config(
        page_title="Luvidarte - Catálogo Virtual",
        page_icon="📦",
        layout="wide"
    )

# ============================================
# INICIALIZAR SESSION STATE
# ============================================
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = []
if 'pagina_atual' not in st.session_state:
    st.session_state.pagina_atual = 1
if 'carrinho_aberto' not in st.session_state:
    st.session_state.carrinho_aberto = False
if 'filtros_anteriores' not in st.session_state:
    st.session_state.filtros_anteriores = None
if 'quantidades' not in st.session_state:
    st.session_state.quantidades = {}
if 'dados_cliente' not in st.session_state:
    st.session_state.dados_cliente = {}
if 'mostrar_formulario_cliente' not in st.session_state:
    st.session_state.mostrar_formulario_cliente = False
if 'form_data' not in st.session_state:
    st.session_state.form_data = {
        'razao_social': '',
        'cnpj': '',
        'inscricao_estadual': '',
        'email': '',
        'telefone': '',
        'endereco': '',
        'numero': '',
        'bairro': '',
        'cep': ''
    }
if 'mostrar_botoes_envio' not in st.session_state:
    st.session_state.mostrar_botoes_envio = False
if 'html_bytes' not in st.session_state:
    st.session_state.html_bytes = None
if 'ultimo_acesso' not in st.session_state:
    st.session_state.ultimo_acesso = datetime.now()
if 'consentimento_data' not in st.session_state:
    st.session_state.consentimento_data = None
if 'sistema_tributario' not in st.session_state:
    st.session_state.sistema_tributario = 'ANTIGO'  # 'ANTIGO' ou 'NOVO_2026'

# ============================================
# CSS GLOBAL
# ============================================
st.markdown("""
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
.stDecoration { display: none; }
.stAppDeployButton { display: none !important; }
.main > div { padding-top: 0.5rem; }
.stApp { background-color: #F7F7F7; }

.main-banner {
    background-color: #FFF; border-radius: 16px; padding: 15px 20px;
    margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    display: flex; align-items: center; justify-content: space-between;
    gap: 15px; min-height: 90px; border: 1px solid #E0E0E0; flex-wrap: wrap;
}
.logo-img { max-height: 60px; width: auto; object-fit: contain; }
.banner-text { flex-grow: 1; text-align: center; }
.banner-text h1 { font-size: clamp(20px,5vw,38px); margin: 0; font-weight: bold; color: #000; }
.banner-text p { font-size: clamp(11px,3vw,15px); margin: 5px 0 0 0; color: #333; }

.legal-banner {
    background-color: #FFF9E6; border-left: 4px solid #C9A03D;
    border-radius: 8px; padding: 10px 15px; margin: 10px 0; font-size: 12px; color: #666;
}
.contato-central {
    text-align: center; margin: 10px 0 20px 0; padding: 10px;
    font-size: clamp(11px,3vw,13px); color: #666; background-color: #FFF;
    border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #E8E8E8;
}

.cart-link-top {
    text-align: right;
}
.cart-link-button {
    background: none !important;
    border: none !important;
    color: #2E7D32 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    cursor: pointer !important;
    padding: 0 !important;
    white-space: nowrap;
    text-decoration: none !important;
}
.cart-link-button:hover {
    color: #1B5E20 !important;
    text-decoration: underline !important;
}
.cart-link-badge {
    background: #D32F2F;
    color: white;
    border-radius: 50%;
    min-width: 20px;
    height: 20px;
    font-size: 11px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    padding: 0 4px;
}

.whatsapp-float-fixed { position: fixed; bottom: 20px; right: 20px; z-index: 99990; }
.whatsapp-float {
    background-color: #25D366; color: white; border-radius: 50px;
    padding: 10px 18px; font-size: 13px; font-weight: bold;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25); display: flex;
    align-items: center; gap: 8px; text-decoration: none; transition: all 0.3s ease;
}
.whatsapp-float:hover { transform: scale(1.05); background-color: #075E54; }

.formulario-cliente {
    background-color: #FFF;
    border-radius: 16px;
    padding: 25px;
    margin: 20px 0;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    border: 1px solid #E0E0E0;
}
.formulario-titulo {
    color: #2E7D32;
    font-size: 20px;
    font-weight: bold;
    margin-bottom: 20px;
    border-bottom: 2px solid #C9A03D;
    display: inline-block;
    padding-bottom: 5px;
}
.campo-obrigatorio {
    color: #D32F2F;
    font-size: 12px;
    margin-left: 5px;
}

.product-card {
    background-color: #FFF; border-radius: 12px; padding: 16px; margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); transition: all 0.2s ease; position: relative;
}
.product-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.product-card.promo-card { border: 1.5px solid #D32F2F; box-shadow: 0 2px 8px rgba(211,47,47,0.15); }
.product-card.normal-card { border: 1px solid #E0E0E0; }
.promo-badge {
    position: absolute; top: -8px; right: 10px;
    background: linear-gradient(135deg,#D32F2F,#B71C1C);
    color: white; font-size: 10px; font-weight: bold;
    padding: 4px 10px; border-radius: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); z-index: 10;
}
.tabela-badge {
    position: absolute; top: -8px; right: 10px;
    background: linear-gradient(135deg,#666,#444);
    color: white; font-size: 10px; font-weight: bold;
    padding: 4px 10px; border-radius: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); z-index: 10;
}
.ref { color: #666; font-size: 11px; font-weight: 500; text-transform: uppercase; display: block; }
.product-name { color: #000; font-size: 17px; font-weight: 600; margin: 8px 0 4px 0; }
.product-category { color: #666; font-size: 12px; margin-bottom: 12px; }
.product-detail { font-size: 13px; margin: 5px 0; min-height: 24px; }

.resumo-card {
    background-color: #FFF; border-radius: 12px; padding: 16px; margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #E0E0E0;
}
.resumo-title {
    font-size: 16px; font-weight: bold; color: #2E7D32; margin-bottom: 10px;
    border-bottom: 2px solid #C9A03D; display: inline-block; padding-bottom: 5px;
}
.resumo-line { display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; }
.resumo-line.total {
    font-weight: bold; font-size: 16px; border-top: 1px solid #E0E0E0;
    margin-top: 8px; padding-top: 8px; color: #D32F2F;
}
.desconto-vol-banner {
    background: linear-gradient(135deg,#E8F5E9,#C8E6C9); border: 2px solid #4CAF50;
    border-radius: 10px; padding: 12px 16px; margin: 12px 0;
    text-align: center; font-weight: bold; color: #1B5E20; font-size: 15px;
}
.prox-desconto-hint {
    background: linear-gradient(135deg,#E8F5E9,#C8E6C9); border: 1px solid #A5D6A7;
    border-radius: 8px; padding: 8px 12px; margin: 8px 0 12px 0;
    font-size: 12px; color: #2E7D32; text-align: center;
}

.social-links-container { text-align: center; margin: 15px 0; }
.social-title { color: #C9A03D; font-weight: bold; font-size: 14px; }
.social-links { display: flex; justify-content: center; gap: 25px; margin: 10px 0; flex-wrap: wrap; }
.social-link { text-decoration: none; font-size: 14px; font-weight: 500; padding: 5px 0; }
.contact-footer { text-align: center; font-size: 13px; color: #555; }
.footer-bottom {
    text-align: center; font-size: 12px; color: #666;
    padding: 15px 0;
    margin-top: 20px;
}
.horario-atendimento { text-align: center; margin: 10px 0; font-size: 13px; }
.horario-label { color: #C9A03D; font-weight: bold; }
.horario-text { color: #555; }

.sistema-badge {
    background: linear-gradient(135deg, #E3F2FD, #BBDEFB);
    border-radius: 8px;
    padding: 10px 15px;
    margin: 10px 0;
    text-align: center;
    font-weight: bold;
    color: #1565C0;
    border-left: 4px solid #2196F3;
}

@media (max-width: 768px) {
    .whatsapp-float-fixed { bottom: 15px; right: 15px; }
    .cart-link-button { font-size: 12px !important; white-space: normal; }
}
</style>
""", unsafe_allow_html=True)

# ============================================
# BANNER PRINCIPAL
# ============================================
logo_img = carregar_logo()
if logo_img:
    buffered = BytesIO()
    logo_img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode()
    st.markdown(f"""
    <div class='main-banner'>
        <div><img src='data:image/png;base64,{img_b64}' class='logo-img'></div>
        <div class='banner-text'>
            <h1>Catálogo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
        <div style='width:80px;'></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class='main-banner'>
        <div class='banner-text' style='width:100%;'>
            <h1>Catálogo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class='legal-banner'>
    ⚠️ <strong>AVISO LEGAL:</strong> Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada.
    Os valores são estimativas e sujeitos à confirmação de estoque e disponibilidade.
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='contato-central'>
    📍 Rua Caetano Rubio, 213 - Ferraz de Vasconcelos - SP &nbsp;|&nbsp;
    📞 (11) 4676-9000 &nbsp;|&nbsp;
    💬 (11) 93011-9335 &nbsp;|&nbsp;
    ✉️ sac@luvidarte.com.br
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ============================================
# CARREGAMENTO DE DADOS
# ============================================
ID_PLANILHA     = "1DCmwFzQvbQYDBsQft17VO9szjixgq1Bp09dYTfu142w"
NOME_ABA        = "base"
NOME_ABA_PROMO  = "PROMO"
NOME_ABA_ST     = "BASE_ST"
NOME_ABA_NORMAL = "NORMAL"
NOME_ABA_ISENTO = "ISENTO"
NOME_ABA_IS     = "IMPOSTO_SELETIVO"

with st.spinner("🔄 Carregando produtos..."):
    dados        = carregar_planilha(ID_PLANILHA, NOME_ABA)
    dados_promo  = carregar_planilha_promo(ID_PLANILHA, NOME_ABA_PROMO)
    dados_st     = carregar_base_st(ID_PLANILHA, NOME_ABA_ST)
    dados_normal = carregar_descontos_normal(ID_PLANILHA, NOME_ABA_NORMAL)
    dados_isento = carregar_descontos_isento(ID_PLANILHA, NOME_ABA_ISENTO)
    dados_is     = carregar_base_is(ID_PLANILHA, NOME_ABA_IS)

if dados.empty:
    st.error("""
    ❌ **Não foi possível carregar os produtos!**
    
    Verifique sua conexão com a internet e tente novamente.
    
    Se o problema persistir, entre em contato com nossa equipe:
    📞 (11) 4676-9000 | 💬 (11) 93011-9335
    """)
    
    if st.button("🔄 Tentar recarregar"):
        st.cache_data.clear()
        st.rerun()
    
    st.stop()

# ============================================
# SIDEBAR COM SELEÇÃO DO SISTEMA TRIBUTÁRIO
# ============================================
st.sidebar.header("🔍 FILTRAR PRODUTOS")
st.sidebar.markdown(f"📊 *Total:* {len(dados)} produtos")

# Seletor do sistema tributário
st.sidebar.markdown("---")
st.sidebar.markdown("### 📆 Sistema Tributário")

sistema_escolhido = st.sidebar.radio(
    "Escolha o sistema para cálculo dos impostos:",
    options=["Tradicional (ICMS + IPI + ST)", "Reforma 2026 (IBS + CBS + IS)"],
    index=0,
    help="O sistema tradicional simula os impostos atuais. O sistema 2026 simula a Reforma Tributária."
)

# Atualizar session state
novo_sistema = "NOVO_2026" if "Reforma 2026" in sistema_escolhido else "ANTIGO"
if st.session_state.get('sistema_tributario') != novo_sistema:
    st.session_state.sistema_tributario = novo_sistema
    # Limpar carrinho ao mudar de sistema para evitar inconsistências
    if st.session_state.carrinho:
        st.session_state.carrinho = []
        st.warning("🔄 Sistema tributário alterado. O carrinho foi limpo para evitar inconsistências nos cálculos.")
        st.rerun()

st.sidebar.markdown("---")

# Exibir badge do sistema atual
if st.session_state.sistema_tributario == 'NOVO_2026':
    st.markdown("""
    <div class='sistema-badge'>
        📊 SISTEMA TRIBUTÁRIO ATIVO: REFORMA 2026 (IBS + CBS + IS)<br>
        <small>Imposto Seletivo (IS) aplicado para produtos específicos conforme NCM</small>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class='sistema-badge'>
        📊 SISTEMA TRIBUTÁRIO ATIVO: TRADICIONAL (ICMS + IPI + ST)
    </div>
    """, unsafe_allow_html=True)

# Restante dos filtros do sidebar
uf_selecionada = st.sidebar.selectbox(
    "📍 UF (Destino)",
    options=["SP","MG","RS","SE","PR","RJ","SC","MT","AC","AL","AP","AM",
             "BA","CE","DF","ES","GO","MA","MS","PA","PB","PE","PI","RN","RO","RR","TO"],
    index=0
)

grupos = ["Todos"] + sorted(dados['GRUPO'].unique().tolist())
if "Promoção" not in grupos:
    grupos.insert(1, "Promoção")
grupo_escolhido = st.sidebar.selectbox("📦 Grupo", grupos)

busca_referencia = st.sidebar.text_input("🔎 Buscar Referência", placeholder="Ex: 510 P TR")

precos_validos = dados['Preço'].dropna()
if len(precos_validos) > 0:
    faixa_preco = st.sidebar.slider(
        "💰 Faixa de Preço",
        min_value=float(precos_validos.min()),
        max_value=float(precos_validos.max()),
        value=(float(precos_validos.min()), float(precos_validos.max()))
    )
else:
    faixa_preco = (0, 1000)

cliente_isento  = st.sidebar.checkbox("🏷️ Cliente Isento", value=False)
forma_pagamento = st.sidebar.radio("💳 Pagamento",
                                   options=["PREÇO BASE","VISTA","30","45","60"], index=0)

# Monitorar mudanças nos filtros
filtros_atual = (uf_selecionada, cliente_isento, forma_pagamento, st.session_state.sistema_tributario)
if st.session_state.filtros_anteriores != filtros_atual:
    st.session_state.filtros_anteriores = filtros_atual
    if st.session_state.carrinho:
        recalcular_todo_carrinho(uf_selecionada, cliente_isento, forma_pagamento,
                                 dados_st, dados_promo, dados, dados_normal, dados_isento,
                                 st.session_state.sistema_tributario)
        st.rerun()

# ============================================
# TELA DO CARRINHO
# ============================================
if st.session_state.get('carrinho_aberto', False):

    st.markdown("# 🛒 Meu Orçamento Virtual")
    st.markdown("Revise os itens do seu orçamento antes de enviar.")

    if st.button("← Voltar aos produtos"):
        fechar_carrinho()

    if not st.session_state.carrinho:
        st.info("Seu orçamento está vazio. Adicione produtos para continuar.")
        st.stop()

    sistema_atual = st.session_state.sistema_tributario
    
    # Calcular valor base total
    valor_base_total = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
    
    # Calcular desconto por volume
    desconto_volume_percentual = calcular_desconto_volume(valor_base_total)
    valor_desconto_volume = valor_base_total * desconto_volume_percentual
    novo_valor_base = valor_base_total - valor_desconto_volume

    # Variáveis para totais
    total_ipi_recalculado = 0
    total_st_recalculado = 0
    total_ibs_recalculado = 0
    total_cbs_recalculado = 0
    total_is_recalculado = 0
    total_geral_recalculado = 0
    total_desconto_geral = 0
    total_bruto_geral = 0

    for idx, item in enumerate(st.session_state.carrinho):
        if sistema_atual == 'NOVO_2026':
            valor_base_item_original = item.get('valor_base', item['preco_final'])
            valor_base_item_com_desconto = valor_base_item_original * (1 - desconto_volume_percentual)
            
            aliquota_ibs = item.get('aliquota_ibs', 0.172)
            aliquota_cbs = item.get('aliquota_cbs', 0.12)
            aliquota_is = item.get('aliquota_is', 0)
            
            aliquota_total = aliquota_ibs + aliquota_cbs + aliquota_is
            if aliquota_total > 0 and aliquota_total < 1:
                preco_final_item = valor_base_item_com_desconto / (1 - aliquota_total)
            else:
                preco_final_item = valor_base_item_com_desconto
            
            ibs_item = preco_final_item * aliquota_ibs
            cbs_item = preco_final_item * aliquota_cbs
            is_item = preco_final_item * aliquota_is
            
            total_ibs_recalculado += ibs_item * item['quantidade']
            total_cbs_recalculado += cbs_item * item['quantidade']
            total_is_recalculado += is_item * item['quantidade']
            total_geral_recalculado += preco_final_item * item['quantidade']
            
            valor_base_exibido = valor_base_item_com_desconto
            valor_total_exibido = preco_final_item
            
        else:
            # Sistema antigo
            ipi_aliquota_efetiva = item['valor_ipi'] / item['preco_final'] if item['preco_final'] > 0 else 0
            st_aliquota_efetiva = item['valor_st'] / item['preco_final'] if item['preco_final'] > 0 else 0
            
            valor_base_item_original = item['preco_final']
            valor_base_item_com_desconto = valor_base_item_original * (1 - desconto_volume_percentual)
            
            novo_ipi_item = valor_base_item_com_desconto * ipi_aliquota_efetiva
            novo_st_item = valor_base_item_com_desconto * st_aliquota_efetiva
            novo_total_item = (valor_base_item_com_desconto + novo_ipi_item + novo_st_item) * item['quantidade']
            
            total_ipi_recalculado += novo_ipi_item * item['quantidade']
            total_st_recalculado += novo_st_item * item['quantidade']
            total_geral_recalculado += novo_total_item
            
            valor_base_exibido = valor_base_item_com_desconto
            valor_total_exibido = valor_base_item_com_desconto + novo_ipi_item + novo_st_item
        
        total_desconto_geral += item.get('valor_desconto', 0) * item['quantidade']
        total_bruto_geral += item['preco_bruto'] * item['quantidade']
        
        c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
        with c1:
            img_url = item.get('imagem_url', '')
            if img_url and pd.notna(img_url) and str(img_url).strip():
                try:
                    st.image(img_url, width=80)
                except:
                    st.image("https://via.placeholder.com/80x80?text=Luvidarte", width=80)
            else:
                st.image("https://via.placeholder.com/80x80?text=Luvidarte", width=80)
        with c2:
            st.markdown(f"*{item['descricao']}*")
            st.markdown(f"🔖 REF: {item['referencia']}")
            st.markdown(f"📦 Grupo: {item['grupo']}")
            if item.get('medidas'):
                st.markdown(f"📐 {item['medidas']}")
        with c3:
            st.markdown(f"💰 *Preço Bruto:* {formatar_moeda(item['preco_bruto'])}")
            if item.get('desconto_percentual', 0) > 0:
                st.markdown(f"🎯 *Desconto:* {item['desconto_percentual']*100:.2f}% ({formatar_moeda(item.get('valor_desconto', 0))})")
                st.markdown(f"📉 *Valor c/ Desconto:* {formatar_moeda(item.get('preco_com_desconto', item['preco_bruto']))}")
            
            st.markdown(f"💰 *Valor unitário:* {formatar_moeda(valor_base_exibido)}")
            if desconto_volume_percentual > 0:
                st.caption(f"🎉 *Inclui {int(desconto_volume_percentual*100)}% desconto por volume*")
            
            col_qtd1, col_qtd2 = st.columns([1, 2])
            with col_qtd1:
                nova_qtd = st.number_input(
                    "Quantidade",
                    min_value=1,
                    max_value=999,
                    value=int(item['quantidade']),
                    step=1,
                    key=f"edit_qtd_{idx}",
                    label_visibility="collapsed"
                )
                if nova_qtd != item['quantidade']:
                    atualizar_quantidade_carrinho(idx, nova_qtd)
                    st.rerun()
            
            with col_qtd2:
                subtotal_item = valor_base_exibido * item['quantidade']
                st.markdown(f"💎 *Subtotal:* {formatar_moeda(subtotal_item)}")
            
            if sistema_atual == 'NOVO_2026':
                if ibs_item > 0:
                    st.markdown(f"🔷 IBS: {aliquota_ibs*100:.2f}% = {formatar_moeda(ibs_item * item['quantidade'])}")
                if cbs_item > 0:
                    st.markdown(f"🔶 CBS: {aliquota_cbs*100:.2f}% = {formatar_moeda(cbs_item * item['quantidade'])}")
                if is_item > 0:
                    st.markdown(f"⚠️ IS: {aliquota_is*100:.2f}% = {formatar_moeda(is_item * item['quantidade'])}")
            else:
                if item.get('ipi_percentual', 0) > 0:
                    st.markdown(f"🔷 IPI: {item['ipi_percentual']*100:.2f}% = {formatar_moeda(novo_ipi_item * item['quantidade'])}")
                if item.get('st_aliquota', 0) > 0:
                    st.markdown(f"🟣 ST: {formatar_moeda(novo_st_item * item['quantidade'])}")
        with c4:
            st.markdown("*Total Item*")
            st.markdown(f"### {formatar_moeda(valor_total_exibido * item['quantidade'])}")
            if st.button("🗑️ Remover", key=f"remove_{idx}"):
                remover_do_carrinho(idx)
                st.rerun()
        st.markdown("---")

    total_final_com_vol = total_geral_recalculado

    if desconto_volume_percentual > 0:
        st.markdown(f"""
        <div class='desconto-vol-banner'>
            🎉 Parabéns! Você ganhou <strong>{int(desconto_volume_percentual*100)}% de desconto</strong> por volume!<br>
            Economia de <strong>{formatar_moeda(valor_desconto_volume)}</strong> aplicada sobre o valor base.
        </div>""", unsafe_allow_html=True)
    elif 2500 - valor_base_total > 0:
        st.markdown(f"""
        <div class='prox-desconto-hint'>
            💡 Adicione mais <strong>{formatar_moeda(2500-valor_base_total)}</strong> em valor base e ganhe <strong>10% de desconto</strong>!
        </div>""", unsafe_allow_html=True)

    st.markdown("## 📋 Resumo do Orçamento")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
        <div class='resumo-card'>
            <div class='resumo-title'>📊 Resumo de Valores</div>
            <div class='resumo-line'>
                <span>💰 Valor Bruto Total:</span>
                <span><strong>{formatar_moeda(total_bruto_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🎯 Desconto (condição pagto):</span>
                <span><strong style='color:#D32F2F;'>- {formatar_moeda(total_desconto_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>📉 Valor com Desconto (base):</span>
                <span><strong>{formatar_moeda(total_bruto_geral - total_desconto_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>📊 Valor Base (p/ desconto volume):</span>
                <span><strong>{formatar_moeda(valor_base_total)}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        if sistema_atual == 'NOVO_2026':
            st.markdown(f"""
            <div class='resumo-card'>
                <div class='resumo-title'>🏷️ Tributos (Reforma 2026)</div>
                <div class='resumo-line'>
                    <span>🔷 IBS Total:</span>
                    <span><strong>{formatar_moeda(total_ibs_recalculado)}</strong></span>
                </div>
                <div class='resumo-line'>
                    <span>🔶 CBS Total:</span>
                    <span><strong>{formatar_moeda(total_cbs_recalculado)}</strong></span>
                </div>
                <div class='resumo-line'>
                    <span>⚠️ IS Total:</span>
                    <span><strong>{formatar_moeda(total_is_recalculado)}</strong></span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='resumo-card'>
                <div class='resumo-title'>🏷️ Tributos (Sistema Tradicional)</div>
                <div class='resumo-line'>
                    <span>🔷 IPI Total:</span>
                    <span><strong>{formatar_moeda(total_ipi_recalculado)}</strong></span>
                </div>
                <div class='resumo-line'>
                    <span>🟣 ST Total:</span>
                    <span><strong>{formatar_moeda(total_st_recalculado)}</strong></span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class='resumo-card'>
        <div class='resumo-title'>🎯 VALORES COM DESCONTO VOLUME</div>
        <div class='resumo-line' style='color:#2E7D32;'>
            <span>💰 Novo Valor Base (com {int(desconto_volume_percentual*100)}% OFF):</span>
            <span><strong>{formatar_moeda(novo_valor_base)}</strong></span>
        </div>
        <div class='resumo-line total'>
            <span>✅ TOTAL FINAL DO ORÇAMENTO:</span>
            <span><strong style='color:#D32F2F;'>{formatar_moeda(total_final_com_vol)}</strong></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    
    cb1, cb2, cb3 = st.columns(3)
    with cb1:
        if st.button("← Continuar comprando", use_container_width=True):
            fechar_carrinho()
    with cb2:
        if st.button("🗑️ Limpar Carrinho", use_container_width=True):
            limpar_carrinho()
            st.rerun()
    with cb3:
        if st.button("📋 Solicitar Orçamento", use_container_width=True):
            mostrar_formulario()
    
    if st.session_state.mostrar_formulario_cliente and not st.session_state.mostrar_botoes_envio:
        st.markdown("---")
        st.markdown('<div class="formulario-cliente">', unsafe_allow_html=True)
        st.markdown('<div class="formulario-titulo">📝 Dados do Cliente</div>', unsafe_allow_html=True)
        st.markdown('<p style="color:#D32F2F; font-size:12px; margin-bottom:15px;">* Campos obrigatórios</p>', unsafe_allow_html=True)
        
        with st.form(key="form_cliente"):
            col1, col2 = st.columns(2)
            with col1:
                razao_social = st.text_input("Razão Social *", value=st.session_state.form_data['razao_social'])
                cnpj = st.text_input("CNPJ/CPF *", value=st.session_state.form_data['cnpj'], help="Digite apenas números")
                inscricao_estadual = st.text_input("Inscrição Estadual", value=st.session_state.form_data['inscricao_estadual'])
                email = st.text_input("E-mail *", value=st.session_state.form_data['email'])
                telefone = st.text_input("Telefone/Contato *", value=st.session_state.form_data['telefone'], help="Com DDD")
            
            with col2:
                endereco = st.text_input("Endereço *", value=st.session_state.form_data['endereco'])
                numero = st.text_input("Número *", value=st.session_state.form_data['numero'])
                bairro = st.text_input("Bairro *", value=st.session_state.form_data['bairro'])
                cep = st.text_input("CEP *", value=st.session_state.form_data['cep'], help="Digite apenas números")
            
            enviar = st.form_submit_button("📤 Enviar Orçamento", use_container_width=True)
            
            if enviar:
                st.session_state.form_data = {
                    'razao_social': razao_social,
                    'cnpj': cnpj,
                    'inscricao_estadual': inscricao_estadual,
                    'email': email,
                    'telefone': telefone,
                    'endereco': endereco,
                    'numero': numero,
                    'bairro': bairro,
                    'cep': cep
                }
                
                erros = []
                if not razao_social:
                    erros.append("Razão Social")
                if not cnpj:
                    erros.append("CNPJ/CPF")
                elif not validar_cnpj(cnpj) and len(cnpj) != 11:
                    erros.append("CNPJ/CPF inválido")
                if not email:
                    erros.append("E-mail")
                elif not validar_email(email):
                    erros.append("E-mail inválido")
                if not telefone:
                    erros.append("Telefone")
                elif not validar_telefone(telefone):
                    erros.append("Telefone inválido")
                if not endereco:
                    erros.append("Endereço")
                if not numero:
                    erros.append("Número")
                if not bairro:
                    erros.append("Bairro")
                if not cep:
                    erros.append("CEP")
                elif not validar_cep(cep):
                    erros.append("CEP inválido")
                
                if erros:
                    st.error(f"❌ Por favor, preencha os campos obrigatórios: {', '.join(erros)}")
                else:
                    dados_cliente = {
                        'razao_social': razao_social,
                        'cnpj': cnpj,
                        'inscricao_estadual': inscricao_estadual,
                        'email': email,
                        'telefone': telefone,
                        'endereco': endereco,
                        'numero': numero,
                        'bairro': bairro,
                        'cep': cep
                    }
                    st.session_state.dados_cliente = dados_cliente
                    
                    tipo_cliente_str = "ISENTO" if cliente_isento else "NORMAL"
                    
                    if sistema_atual == 'NOVO_2026':
                        html_bytes = gerar_html_orcamento(
                            dados_cliente, st.session_state.carrinho, 
                            uf_selecionada, tipo_cliente_str, forma_pagamento,
                            desconto_volume_percentual, valor_base_total, valor_desconto_volume,
                            total_final_com_vol, total_ibs_recalculado, total_cbs_recalculado,
                            sistema_tributario='NOVO_2026'
                        )
                    else:
                        html_bytes = gerar_html_orcamento(
                            dados_cliente, st.session_state.carrinho, 
                            uf_selecionada, tipo_cliente_str, forma_pagamento,
                            desconto_volume_percentual, valor_base_total, valor_desconto_volume,
                            total_final_com_vol, total_ipi_recalculado, total_st_recalculado,
                            sistema_tributario='ANTIGO'
                        )
                    
                    if html_bytes:
                        st.session_state.html_bytes = html_bytes
                        st.session_state.mostrar_botoes_envio = True
                        st.rerun()
                    else:
                        st.error("❌ Erro ao gerar o orçamento. Tente novamente.")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state.mostrar_botoes_envio and st.session_state.html_bytes:
        tipo_cliente_str = "ISENTO" if cliente_isento else "NORMAL"
        
        if sistema_atual == 'NOVO_2026':
            msg_whatsapp = formatar_mensagem_whatsapp(
                st.session_state.dados_cliente, uf_selecionada, 
                tipo_cliente_str, forma_pagamento, total_final_com_vol,
                desconto_volume_percentual, valor_desconto_volume,
                valor_base_total, total_ibs_recalculado, total_cbs_recalculado,
                sistema_tributario='NOVO_2026'
            )
        else:
            msg_whatsapp = formatar_mensagem_whatsapp(
                st.session_state.dados_cliente, uf_selecionada, 
                tipo_cliente_str, forma_pagamento, total_final_com_vol,
                desconto_volume_percentual, valor_desconto_volume,
                valor_base_total, total_ipi_recalculado, total_st_recalculado,
                sistema_tributario='ANTIGO'
            )
            
        msg_codificada = urllib.parse.quote(msg_whatsapp)
        link_whatsapp = f"https://wa.me/5511930119335?text={msg_codificada}"
        
        st.markdown("---")
        st.success("✅ Dados validados com sucesso! Orçamento gerado conforme LGPD.")
        
        col_html, col_wpp, col_voltar = st.columns([1, 1, 1])
        with col_html:
            st.download_button(
                label="📄 Baixar Orçamento (HTML)",
                data=st.session_state.html_bytes,
                file_name=f"orcamento_luvidarte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                use_container_width=True
            )
        
        with col_wpp:
            st.markdown(f"""
            <a href="{link_whatsapp}" target="_blank" 
               style="background-color: #25D366; color: white; padding: 10px 20px; 
                      text-decoration: none; border-radius: 8px; font-weight: bold;
                      display: inline-flex; align-items: center; justify-content: center;
                      gap: 10px; width: 100%;">
                <span>💬</span> Enviar via WhatsApp
            </a>
            """, unsafe_allow_html=True)
        
        with col_voltar:
            if st.button("← Voltar ao carrinho", use_container_width=True):
                st.session_state.mostrar_botoes_envio = False
                st.session_state.mostrar_formulario_cliente = False
                st.rerun()
        
        st.caption("📎 *O orçamento completo está disponível para download. Conforme LGPD, seus dados não são armazenados em nosso sistema.*")

    st.stop()

# ============================================
# FILTROS
# ============================================
icms_uf         = determinar_icms_por_uf(uf_selecionada)
tabela_desconto = dados_isento if cliente_isento else dados_normal
tipo_cliente    = "ISENTO" if cliente_isento else "NORMAL"

dados_filtrados = dados.copy()
if grupo_escolhido == "Promoção":
    dados_filtrados = dados_filtrados[
        dados_filtrados['Promo'].astype(str).str.upper().str.contains('SIM', na=False)]
elif grupo_escolhido != "Todos":
    dados_filtrados = dados_filtrados[dados_filtrados['GRUPO'] == grupo_escolhido]
if len(precos_validos) > 0:
    dados_filtrados = dados_filtrados[
        (dados_filtrados['Preço'].isna()) |
        ((dados_filtrados['Preço'] >= faixa_preco[0]) & (dados_filtrados['Preço'] <= faixa_preco[1]))
    ]
if busca_referencia:
    dados_filtrados = dados_filtrados[
        dados_filtrados['Referência'].str.contains(busca_referencia, case=False, na=False)]

total_encontrados = len(dados_filtrados)

# ============================================
# HEADER COM LINK DO CARRINHO
# ============================================
resumo_header = calcular_resumo_carrinho()

col_titulo, col_link = st.columns([3, 1])

with col_titulo:
    st.markdown(f"## ✨ Produtos Encontrados: {total_encontrados}")

with col_link:
    if resumo_header['total_itens'] > 0:
        total_fmt_header = formatar_moeda(resumo_header['total_geral'])
        
        if st.button(
            f"🛒 Acessar meu carrinho ({resumo_header['total_itens']}) {total_fmt_header}",
            key="cart_link_top"
        ):
            abrir_carrinho()
    else:
        st.markdown(
            f'<div style="text-align:right; color:#2E7D32; opacity:0.6; font-size:14px;">'
            f'🛒 Acessar meu carrinho (0) R$ 0,00</div>',
            unsafe_allow_html=True
        )

st.markdown("---")

# ============================================
# PAGINAÇÃO
# ============================================
ITENS_POR_PAGINA = 9
total_paginas = max(1, (total_encontrados + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)
if st.session_state.pagina_atual > total_paginas:
    st.session_state.pagina_atual = total_paginas
indice_inicio = (st.session_state.pagina_atual - 1) * ITENS_POR_PAGINA
indice_fim    = min(indice_inicio + ITENS_POR_PAGINA, total_encontrados)
dados_pagina  = dados_filtrados.iloc[indice_inicio:indice_fim]

# ============================================
# INFO RÁPIDA (CORRIGIDO)
# ============================================
ci1, ci2, ci3, ci4 = st.columns(4)

with ci1:
    if st.session_state.sistema_tributario == 'ANTIGO':
        st.info(f"🏢 *UF:* {uf_selecionada} (ICMS {icms_uf}%)")
    else:
        st.info(f"🏢 *UF Destino:* {uf_selecionada}")

with ci2:
    st.info(f"📋 *Cliente:* {tipo_cliente}")

with ci3:
    if forma_pagamento == "PREÇO BASE":
        st.warning(f"💰 *Condição:* {forma_pagamento}")
    else:
        st.success(f"💰 *Condição:* {forma_pagamento} dias")

with ci4:
    if grupo_escolhido == "Promoção":
        st.success(f"🏷️ *Grupo:* {grupo_escolhido} - Ofertas!")
    else:
        st.info(f"📦 *Grupo:* {grupo_escolhido}")

st.markdown("---")

# ============================================
# BOTÃO FLUTUANTE DE DESCONTO
# ============================================
st.markdown(gerar_botao_desconto_flutuante(), unsafe_allow_html=True)

# ============================================
# GRID DE PRODUTOS
# ============================================
if dados_filtrados.empty:
    st.warning("😕 Nenhum produto encontrado.")
else:
    desconto_volume_atual = 0
    valor_base_carrinho = 0
    if st.session_state.carrinho:
        valor_base_carrinho = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
        desconto_volume_atual = calcular_desconto_volume(valor_base_carrinho)
    
    colunas = st.columns(3)

    for posicao, (indice, produto) in enumerate(dados_pagina.iterrows()):
        
        if st.session_state.sistema_tributario == 'NOVO_2026':
            # Usar novo sistema para cálculo
            resultado = calcular_precos_2026(
                produto, uf_selecionada, forma_pagamento, tabela_desconto,
                cliente_isento, dados_is, dados_promo
            )
            
            preco_bruto = resultado['preco_base']
            desconto_percentual = resultado['desconto_percentual']
            valor_desconto = resultado['valor_desconto']
            preco_com_desconto = resultado['preco_com_desconto']
            preco_final = resultado['preco_final']
            valor_base = resultado['valor_base']
            valor_ibs = resultado['valor_ibs']
            valor_cbs = resultado['valor_cbs']
            valor_is = resultado['valor_is']
            ipi_percentual = resultado['ipi_percentual']
            aliquota_st = resultado['st_aliquota']
            valor_total = preco_final
            
            # Para desconto volume
            preco_com_desconto_volume = valor_base * (1 - desconto_volume_atual)
            
            # Recalcular impostos com desconto volume
            aliquota_total = resultado['aliquota_ibs'] + resultado['aliquota_cbs'] + resultado['aliquota_is']
            if aliquota_total > 0 and aliquota_total < 1:
                preco_final_com_volume = preco_com_desconto_volume / (1 - aliquota_total)
            else:
                preco_final_com_volume = preco_com_desconto_volume
            
        else:
            # Sistema antigo original
            is_promo    = 'SIM' in str(produto.get('Promo', '')).strip().upper()
            preco_promo = None
            if is_promo and not dados_promo.empty:
                preco_promo = buscar_preco_promo(produto['Referência'], uf_selecionada, dados_promo)

            if is_promo and preco_promo is not None and preco_promo > 0:
                preco_bruto = preco_promo
                desconto_percentual = 0.0
                valor_desconto = 0.0
                preco_com_desconto = preco_bruto
                if cliente_isento:
                    preco_final = preco_com_desconto * 1.10
                else:
                    preco_final = preco_com_desconto
            else:
                preco_bruto = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
                if forma_pagamento != "PREÇO BASE":
                    desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
                    valor_desconto = preco_bruto * desconto_percentual
                    preco_com_desconto = preco_bruto - valor_desconto
                else:
                    desconto_percentual = 0.0
                    valor_desconto = 0.0
                    preco_com_desconto = preco_bruto
                preco_final = preco_com_desconto

            ncm_produto = produto.get('NCM', '')
            ipi_percentual = buscar_ipi(ncm_produto, dados_st)
            valor_ipi = preco_final * ipi_percentual
            aliquota_st = buscar_aliquota_st(ncm_produto, uf_selecionada, dados_st)
            valor_st = 0.0 if cliente_isento else preco_final * aliquota_st
            valor_total = preco_final + valor_ipi + valor_st
            
            preco_com_desconto_volume = preco_final * (1 - desconto_volume_atual)
            valor_base = preco_final
            valor_ibs = 0
            valor_cbs = 0
            valor_is = 0

        produto_carrinho = {
            'Referência': produto['Referência'],
            'Descrição':  produto['Descrição'],
            'GRUPO':      produto['GRUPO'],
            'Medidas':    produto.get('Medidas', ''),
            'ml':         produto.get('ml', ''),
            'imagem_url': produto.get('imagem_url', '')
        }

        with colunas[posicao % 3]:
            is_promo = 'SIM' in str(produto.get('Promo', '')).strip().upper()
            card_class = "product-card promo-card" if is_promo else "product-card normal-card"

            badge_html = (
                "<div class='promo-badge'>🔥 PROMOÇÃO</div>"
                if is_promo else
                "<div class='tabela-badge'>📋 TABELA</div>"
            )
            st.markdown(
                f"<div class='{card_class}'>"
                f"{badge_html}"
                f"<span class='ref'>🔖 REF: {produto['Referência']}</span>"
                f"<div class='product-name'>{produto['Descrição']}</div>"
                f"<div class='product-category'>{produto['GRUPO']}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

            img_url = str(produto.get('imagem_url', '')).strip()
            if img_url and pd.notna(produto.get('imagem_url')):
                try:
                    st.image(img_url, use_container_width=True)
                except:
                    st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)
            else:
                st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)

            ml_fmt = formatar_ml(produto.get('ml'))
            st.markdown(
                f'<div class="product-detail">📏 <strong>{ml_fmt if ml_fmt else "--"}</strong></div>',
                unsafe_allow_html=True
            )

            med = produto.get('Medidas', '')
            if pd.notna(med) and str(med).strip():
                st.markdown(f'<div class="product-detail">📐 {med}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="product-detail">📐 <strong>--</strong></div>', unsafe_allow_html=True)

            # Exibir preços
            if desconto_volume_atual > 0:
                st.markdown(f"💰 *Preço Bruto:* {formatar_moeda(preco_bruto)}")
                if desconto_percentual > 0:
                    st.markdown(f"🎯 *Desconto:* {desconto_percentual*100:.2f}% ({formatar_moeda(valor_desconto)})")
                    st.markdown(f"📉 *Valor c/ Desconto:* {formatar_moeda(preco_com_desconto)}")
                st.markdown(f"💰 *Valor unitário:* {formatar_moeda(preco_com_desconto_volume)}")
                st.caption(f"🎉 *Inclui {int(desconto_volume_atual*100)}% desconto por volume acumulado no carrinho*")
            else:
                st.markdown(f"💰 *Preço Bruto:* {formatar_moeda(preco_bruto)}")
                if desconto_percentual > 0:
                    st.markdown(f"🎯 *Desconto:* {desconto_percentual*100:.2f}% ({formatar_moeda(valor_desconto)})")
                    st.markdown(f"📉 *Valor c/ Desconto:* {formatar_moeda(preco_com_desconto)}")
                st.markdown(f"💰 *Valor unitário:* {formatar_moeda(valor_base)}")
            
            # Exibir impostos conforme sistema
            if st.session_state.sistema_tributario == 'NOVO_2026':
                if resultado['aliquota_ibs'] > 0:
                    st.markdown(f"🔷 *IBS:* {resultado['aliquota_ibs']*100:.2f}% = {formatar_moeda(valor_ibs)}")
                if resultado['aliquota_cbs'] > 0:
                    st.markdown(f"🔶 *CBS:* {resultado['aliquota_cbs']*100:.2f}% = {formatar_moeda(valor_cbs)}")
                if resultado['is_seletivo']:
                    st.markdown(f"⚠️ *IMPOSTO SELETIVO:* {resultado['aliquota_is']*100:.2f}% = {formatar_moeda(valor_is)}")
                
                if desconto_volume_atual > 0:
                    st.markdown(f"✅ *TOTAL COM IMPOSTOS:* {formatar_moeda(preco_final_com_volume)}")
                else:
                    st.markdown(f"✅ *TOTAL COM IMPOSTOS:* {formatar_moeda(valor_total)}")
            else:
                if ipi_percentual > 0:
                    st.markdown(f"🔷 *IPI:* {ipi_percentual*100:.2f}% = {formatar_moeda(valor_ipi)}")
                else:
                    st.markdown("🔷 *IPI:* Não aplicável")
                
                if cliente_isento:
                    st.markdown(f"🟣 *ST ({uf_selecionada}):* Cliente Isento — ST não aplicada")
                    if desconto_volume_atual > 0:
                        novo_total_com_desconto = preco_com_desconto_volume + (valor_ipi * (1 - desconto_volume_atual))
                        st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(novo_total_com_desconto)}")
                    else:
                        st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(preco_final + valor_ipi)}")
                elif aliquota_st > 0:
                    st.markdown(f"🟣 *Alíq. ST ({uf_selecionada}):* {aliquota_st*100:.2f}%")
                    if desconto_volume_atual > 0:
                        novo_total_com_desconto = preco_com_desconto_volume + (valor_ipi * (1 - desconto_volume_atual)) + (valor_st * (1 - desconto_volume_atual))
                        st.markdown(f"📊 *Valor ST:* {formatar_moeda(valor_st)}")
                        st.markdown(f"✅ *TOTAL COM IPI + ST:* {formatar_moeda(novo_total_com_desconto)}")
                    else:
                        st.markdown(f"📊 *Valor ST:* {formatar_moeda(valor_st)}")
                        st.markdown(f"✅ *TOTAL COM IPI + ST:* {formatar_moeda(valor_total)}")
                else:
                    st.markdown(f"🟣 *ST ({uf_selecionada}):* Não aplicável")
                    if desconto_volume_atual > 0:
                        novo_total_com_desconto = preco_com_desconto_volume + (valor_ipi * (1 - desconto_volume_atual))
                        st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(novo_total_com_desconto)}")
                    else:
                        st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(preco_final + valor_ipi)}")

            st.markdown("---")

            qtd_key = f"qtd_{indice}"
            if qtd_key not in st.session_state.quantidades:
                st.session_state.quantidades[qtd_key] = 1

            col_qtd, col_btn = st.columns([1, 2])

            with col_qtd:
                nova_qtd = st.number_input(
                    "Quantidade",
                    min_value=1,
                    max_value=999,
                    value=st.session_state.quantidades[qtd_key],
                    step=1,
                    key=f"num_{indice}",
                    label_visibility="collapsed"
                )
                if nova_qtd != st.session_state.quantidades[qtd_key]:
                    st.session_state.quantidades[qtd_key] = nova_qtd

            with col_btn:
                qtd_atual = st.session_state.quantidades[qtd_key]
                if st.button("🛒 Adicionar", key=f"add_{indice}", use_container_width=True):
                    if st.session_state.sistema_tributario == 'NOVO_2026':
                        sucesso = adicionar_ao_carrinho(
                            produto_carrinho, qtd_atual,
                            preco_bruto, desconto_percentual, valor_desconto,
                            preco_com_desconto, preco_final,
                            valor_ibs, valor_cbs,
                            resultado['aliquota_ibs'], resultado['aliquota_cbs'], valor_total,
                            sistema_tributario='NOVO_2026'
                        )
                    else:
                        sucesso = adicionar_ao_carrinho(
                            produto_carrinho, qtd_atual,
                            preco_bruto, desconto_percentual, valor_desconto,
                            preco_com_desconto, preco_final,
                            valor_ipi, valor_st, ipi_percentual, aliquota_st, valor_total,
                            sistema_tributario='ANTIGO'
                        )
                    if sucesso:
                        st.success(f"✅ Produto adicionado ao orçamento! Quantidade: {qtd_atual}")
                        time.sleep(0.5)
                        st.rerun()

            st.markdown("---")

    if total_paginas > 1:
        st.markdown("---")
        _, cpag, _ = st.columns([1, 2, 1])
        with cpag:
            pag_sel = st.selectbox(
                "📄 Página",
                options=list(range(1, total_paginas + 1)),
                index=st.session_state.pagina_atual - 1,
                key="pagina_select"
            )
            if pag_sel != st.session_state.pagina_atual:
                st.session_state.pagina_atual = pag_sel
                st.rerun()
            st.markdown(
                f'<div style="text-align:center;font-size:12px;">'
                f'Mostrando {indice_inicio+1}–{min(indice_fim,total_encontrados)} '
                f'de {total_encontrados}</div>',
                unsafe_allow_html=True
            )
        st.progress(
            st.session_state.pagina_atual / total_paginas,
            text=f"Página {st.session_state.pagina_atual} de {total_paginas}"
        )

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown("""
<div class='horario-atendimento'>
    <span class='horario-label'>🕒 Horário:</span>
    <span class='horario-text'> Segunda a Quinta: 07:00 às 17:00 | Sexta: 07:00 às 16:00</span>
</div>""", unsafe_allow_html=True)

st.markdown("""
<div class='social-links-container'>
    <div class='social-title'>Siga nossas redes sociais:</div>
    <div class='social-links'>
        <a href='https://www.facebook.com/luvidarte' target='_blank'
           class='social-link' style='color:#3b5998;'>Facebook</a>
        <a href='https://www.instagram.com/luvidartevidros/' target='_blank'
           class='social-link' style='color:#E4405F;'>Instagram</a>
        <a href='https://www.linkedin.com/company/luvidarte/' target='_blank'
           class='social-link' style='color:#0077b5;'>LinkedIn</a>
        <a href='https://www.youtube.com/@luvidartevidros7291' target='_blank'
           class='social-link' style='color:#ff0000;'>YouTube</a>
        <a href='https://wa.me/5511930119335?text=Olá! Gostaria de informações sobre os produtos Luvidarte'
           target='_blank' class='social-link' style='color:#25D366;'>WhatsApp</a>
    </div>
</div>""", unsafe_allow_html=True)

st.markdown("""
<div class='contact-footer'>
    📞 (11) 4676-9000 | 💬 (11) 93011-9335 | ✉️ sac@luvidarte.com.br | 🔒 DPO: privacidade@luvidarte.com.br
</div>""", unsafe_allow_html=True)

st.markdown("""
<div class='footer-bottom'>
    © 2026 Luvidarte - Catálogo Virtual |
    <em>Os valores são estimativos e sujeitos à confirmação</em><br>
    <small>Conforme LGPD (Lei 13.709/2018), seus dados são tratados com confidencialidade.</small>
</div>
""", unsafe_allow_html=True)

# ============================================
# WHATSAPP FLUTUANTE
# ============================================
st.markdown("""
<div class="whatsapp-float-fixed">
    <a href="https://wa.me/5511930119335?text=Olá! Gostaria de informações sobre os produtos Luvidarte"
       target="_blank" class="whatsapp-float">
        💬 WhatsApp (11) 93011-9335
    </a>
</div>
""", unsafe_allow_html=True)