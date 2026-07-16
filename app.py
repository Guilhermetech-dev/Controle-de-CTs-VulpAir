import streamlit as st
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="VULP AIR - Controle de CTs",
    page_icon="❄️",
    layout="wide"
)

st.title("❄️ VULP AIR - Controle de Instalações e Requisições")
st.markdown("Monitoramento inteligente de status das instalações baseado em **Consumo** e **Devolução** por Carga Térmica ou Tarefa.")

# --- INICIALIZAÇÃO DE ESTADO (MEMÓRIA) ---
if 'baixas_manuais' not in st.session_state:
    st.session_state['baixas_manuais'] = []

# --- FUNÇÃO DE PROCESSAMENTO DE DADOS ---
@st.cache_data
def processar_dados(arquivo):
    df = pd.read_excel(arquivo)
    
    # 1. Filtros essenciais
    df = df[df['Setor Requisitante'].str.contains("INSTALAÇÃO", na=False, case=False)]
    df = df[df['TipoRequisicao'].isin(['Consumo', 'Devolução'])]
    
    # 2. Funções de extração 
    def extrair_ct(obs):
        if pd.isna(obs): return None
        # Procura por CT+número, TAREFA+número, ou a frase "CT NAO TEM"
        match = re.search(r'(CT\d+|TAREFA\s*\d+|CT\s*N[AÃ]O\s*TEM)', str(obs), re.IGNORECASE)
        if match:
            resultado = match.group(1).upper()
            if "TAREFA" in resultado:
                resultado = resultado.replace(" ", "")
            return resultado
        return None

    def extrair_cliente(obs):
        if pd.isna(obs): return ""
        # Remove o código da CT/Tarefa do texto para isolar o que sobrou (o nome do cliente)
        texto_limpo = re.sub(r'(CT\d+|TAREFA\s*\d+|CT\s*N[AÃ]O\s*TEM)/?\n?', '', str(obs), flags=re.IGNORECASE)
        linhas = texto_limpo.split('\n')
        for linha in linhas:
            linha = linha.strip(" -/")
            if linha:
                return linha.upper()
        return ""

    df['CargaTermica'] = df['Observacao'].apply(extrair_ct)
    df['Cliente'] = df['Observacao'].apply(extrair_cliente)
    
    # Mantém apenas as linhas com CT/Tarefa identificada
    df_filtrado = df[df['CargaTermica'].notna()].copy()
    
    # 3. Lógica de Agrupamento - Carga Térmica como Chave Absoluta
    resumo_instalacoes = df_filtrado.groupby(['CargaTermica', 'Regional']).agg(
        # Procura o primeiro nome de cliente que não seja vazio. Se não achar nenhum, avisa na tela.
        Cliente=('Cliente', lambda x: next((nome for nome in x if str(nome).strip()), "NÃO INFORMADO (VINCULADO PELA CT)")),
        Num_Requisicoes=('Requisicao', lambda x: ", ".join(x.dropna().astype(int).astype(str).unique())),
        Tipos_Registrados=('TipoRequisicao', lambda x: list(x.unique()))
    ).reset_index()
    
    # Só mantém a Carga Térmica no painel se houver 'Consumo' registrado para ela
    resumo_instalacoes = resumo_instalacoes[resumo_instalacoes['Tipos_Registrados'].apply(lambda x: 'Consumo' in x)]
    
    # Lógica do Status (A Regra de Ouro)
    def definir_status(tipos):
        if 'Devolução' in tipos or 'Devolucao' in tipos:
            return '✅ Concluída (Devolução Realizada)'
        return '⚠️ Pendente (Apenas Consumo)'
        
    resumo_instalacoes['Status da Instalação'] = resumo_instalacoes['Tipos_Registrados'].apply(definir_status)
    
    # Organiza a ordem das colunas para a tabela ficar bonita
    resumo_instalacoes = resumo_instalacoes[['CargaTermica', 'Cliente', 'Regional', 'Num_Requisicoes', 'Tipos_Registrados', 'Status da Instalação']]
    
    return resumo_instalacoes, df_filtrado

# --- BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.header("📂 Upload e Filtros")
    arquivo_excel = st.file_uploader("Suba o relatório (Excel)", type=["xlsx", "xls"])

# --- LÓGICA PRINCIPAL DAS ABAS ---
if arquivo_excel is not None:
    df_instalacoes, df_detalhes = processar_dados(arquivo_excel)
    
    # Filtro de Regional na barra lateral
    regionais = df_instalacoes['Regional'].dropna().unique().tolist()
    regionais.insert(0, "Todas as Regionais")
    regional_selecionada = st.sidebar.selectbox("Filtro de Regional", regionais)
    
    if regional_selecionada != "Todas as Regionais":
        df_instalacoes = df_instalacoes[df_instalacoes['Regional'] == regional_selecionada]
    
    # Aplicando as baixas manuais (instalações 100% utilizadas)
    if st.session_state['baixas_manuais']:
        df_instalacoes.loc[df_instalacoes['CargaTermica'].isin(st.session_state['baixas_manuais']), 'Status da Instalação'] = '✅ Concluída (100% Utilizado - Manual)'

    # Separando as listas para cada aba
    instalacoes_pendentes = df_instalacoes[df_instalacoes['Status da Instalação'].str.contains('Pendente')]
    instalacoes_concluidas = df_instalacoes[df_instalacoes['Status da Instalação'].str.contains('Concluída')]

    # --- ABAS VISUAIS ---
    tab1, tab2, tab3 = st.tabs(["📊 Visão Geral", "⚠️ Instalações Pendentes", "✅ Concluídas & Baixa Manual"])
    
    # ABA 1: DASHBOARD
    with tab1:
        st.subheader("Panorama de Instalações (Cargas Térmicas)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Instalações (CTs)", len(df_instalacoes))
        col2.metric("Instalações Pendentes", len(instalacoes_pendentes))
        col3.metric("Instalações Concluídas", len(instalacoes_concluidas))
        
        st.markdown("---")
        st.write("Tabela Geral de Cargas Térmicas:")
        st.dataframe(df_instalacoes.drop(columns=['Tipos_Registrados']), use_container_width=True)

    # ABA 2: PENDÊNCIAS
    with tab2:
        st.subheader("Instalações Aguardando Retorno de Material")
        st.info("Aqui constam as Cargas Térmicas que registraram saída (Consumo), mas ainda não possuem requisição de Devolução.")
        st.dataframe(instalacoes_pendentes.drop(columns=['Tipos_Registrados']), use_container_width=True)

    # ABA 3: CONCLUÍDAS E BAIXA MANUAL
    with tab3:
        st.subheader("Instalações Concluídas")
        st.dataframe(instalacoes_concluidas.drop(columns=['Tipos_Registrados']), use_container_width=True)
        
        st.markdown("---")
        st.subheader("Resolver Pendência: Material 100% Utilizado")
        st.write("Selecione uma Carga Térmica pendente abaixo e marque-a como concluída caso todo o material tenha sido utilizado na instalação.")
        
        if not instalacoes_pendentes.empty:
            df_baixa = instalacoes_pendentes[['CargaTermica', 'Cliente', 'Regional']].copy()
            df_baixa.insert(0, "Baixar Instalação?", False)
            
            tabela_editavel = st.data_editor(
                df_baixa,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Baixar Instalação?": st.column_config.CheckboxColumn("Confirmar 100% Uso")
                }
            )
            
            if st.button("💾 Marcar como Concluída"):
                linhas_marcadas = tabela_editavel[tabela_editavel["Baixar Instalação?"] == True]
                
                if len(linhas_marcadas) > 0:
                    for index, row in linhas_marcadas.iterrows():
                        ct = row['CargaTermica']
                        if ct not in st.session_state['baixas_manuais']:
                            st.session_state['baixas_manuais'].append(ct)
                    st.success("Status atualizado! Instalações marcadas como concluídas.")
                    st.rerun()
                else:
                    st.warning("Selecione pelo menos uma instalação.")
        else:
            st.success("Não há instalações pendentes para dar baixa no momento.")
else:
    st.info("👈 Por favor, faça o upload do relatório no menu lateral para iniciar.")