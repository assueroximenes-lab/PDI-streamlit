import streamlit as st
import psycopg
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import altair as alt
from io import BytesIO
from docx import Document
from docx.shared import Inches
from datetime import datetime
from streamlit_oauth import OAuth2Component
import jwt

alt.data_transformers.disable_max_rows()

sns.set_theme(style="whitegrid", context="paper")

st.set_page_config(layout="wide")

st.markdown("""
<style>
table { font-size: 11px !important; }
thead tr th { font-size: 11px !important; }
tbody tr td { font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)


# ----------------------------
# CONFIG OAUTH GOOGLE
# ----------------------------

CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = "https://SEUAPP.streamlit.app"  # coloque seu domínio aqui

oauth2 = OAuth2Component(
    CLIENT_ID,
    CLIENT_SECRET,
    "https://accounts.google.com/o/oauth2/auth",
    "https://oauth2.googleapis.com/token",
)

def verificar_email_google(token):
    decoded = jwt.decode(token, options={"verify_signature": False})
    return decoded.get("email")

# =====================================================
# CONFIG OAUTH GOOGLE
# =====================================================

from streamlit_oauth import OAuth2Component
import jwt

CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["REDIRECT_URI"]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REFRESH_TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_TOKEN_URL = "https://oauth2.googleapis.com/revoke"

oauth2 = OAuth2Component(
    CLIENT_ID,
    CLIENT_SECRET,
    AUTHORIZE_URL,
    TOKEN_URL,
    REFRESH_TOKEN_URL,
    REVOKE_TOKEN_URL,
)

# ---------------------------
# CONTROLE DE SESSÃO
# ---------------------------

if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.email = None

# ---------------------------
# LOGIN GOOGLE OBRIGATÓRIO
# ---------------------------

if not st.session_state.logado:

    st.title("Painel Gerencial de Metas")

    result = oauth2.authorize_button(
        name="Entrar com Google (UFAPE)",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google_login"
    )

    if result and "token" in result:

        id_token = result["token"]["id_token"]
        decoded = jwt.decode(id_token, options={"verify_signature": False})
        email = decoded.get("email")

        if email and email.endswith("@ufape.edu.br"):
            st.session_state.logado = True
            st.session_state.email = email
            st.rerun()
        else:
            st.error("Acesso permitido apenas para e-mails institucionais @ufape.edu.br")

    st.stop()

# MOSTRAR USUÁRIO LOGADO
st.sidebar.success(f"Logado como: {st.session_state.email}")

if st.sidebar.button("Sair"):
    st.session_state.clear()
    st.rerun()



# --------------------------
# CONEXÃO
# --------------------------

import os

def conectar():
    # Se estiver na Cloud (tem DATABASE_URL)
    if "DATABASE_URL" in st.secrets:
        return psycopg.connect(
            st.secrets["DATABASE_URL"],
            sslmode="require"
        )

    # Se estiver local
    return psycopg.connect(
        host="localhost",
        dbname="metas_dev",
        user="postgres",
        password="240119",
        port="5432"
    )

def carregar_dados():
    conn = conectar()
    df = pd.read_sql("SELECT * FROM metas", conn)
    conn.close()
    return df


# ----------------------------
# Função segura para converter inteiro
# ----------------------------
def inteiro_seguro(valor):
    try:
        if valor is None:
            return None
        valor = str(valor).strip()
        if valor == "":
            return None
        return int(float(valor))
    except:
        return None


# ----------------------------
# Função de classificação
# ----------------------------
def classificar_execucao2(row):

    hoje = datetime.now().year

    execucao = row["execucao"]
    inicio = inteiro_seguro(row["Inicio"])
    fim = inteiro_seguro(row["Fim"])
    ano_conclusao = inteiro_seguro(row["Ano_Conclusao"])

    if execucao == "NÃO INICIADA" and inicio is not None and hoje >= inicio:
        return "EXECUÇÃO PENDENTE"

    if execucao != "CONCLUÍDA" and fim is not None and hoje > fim:
        return "ATRASADA"

    if execucao == "NÃO INICIADA" and inicio is not None and hoje < inicio:
        return "A EXECUTAR"

    if execucao in ["INICIADA", "EM ANDAMENTO", "AVANÇADA"]:
        if inicio is not None and fim is not None and inicio <= hoje <= fim:
            return "EM EXECUÇÃO"

    if execucao in ["INICIADA", "EM ANDAMENTO", "AVANÇADA"]:
        if inicio is not None and hoje < inicio:
            return "EXECUÇÃO ANTECIPADA"

    if execucao == "CONCLUÍDA" and ano_conclusao is not None:
        if inicio is not None and fim is not None and inicio <= ano_conclusao <= fim:
            return "CUMPRIDA NO PRAZO"

    if execucao == "CONCLUÍDA" and ano_conclusao is not None:
        if inicio is not None and ano_conclusao < inicio:
            return "CUMPRIDA ANTECIPADA"

    if execucao == "CONCLUÍDA" and ano_conclusao is not None:
        if fim is not None and ano_conclusao > fim:
            return "CUMPRIDA COM ATRASO"

    return "NÃO INICIADA"

def atualizar_execucao2():
    conn = conectar()
    cursor = conn.cursor()

    # verifica se coluna existe
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='metas'
        AND column_name='execucao2'
    """)
    existe = cursor.fetchall()

    if not existe:
        cursor.execute("ALTER TABLE metas ADD COLUMN execucao2 TEXT")
        conn.commit()

    df_temp = pd.read_sql("SELECT * FROM metas", conn)
    df_temp["execucao2"] = df_temp.apply(classificar_execucao2, axis=1)

    for _, row in df_temp.iterrows():
        cursor.execute(
            'UPDATE metas SET execucao2=%s WHERE "Ordem"=%s',
            (row["execucao2"], row["Ordem"])
        )

    conn.commit()
    conn.close()


# --------------------------
# GERAR EXCEL
# --------------------------

def gerar_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Metas")
    return output.getvalue()

# --------------------------
# GERAR WORD (ACRESCENTADO)
# --------------------------

def gerar_relatorio_word(df):

    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from datetime import datetime

    document = Document()

    # -------------------
    # CAPA
    # -------------------

    document.add_heading("RELATÓRIO GERENCIAL DE METAS", level=0)

    p = document.add_paragraph()
    p.add_run("Sistema de Acompanhamento de Metas\n").bold = True
    p.add_run(f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    document.add_page_break()

    # -------------------
    # RESUMO GERAL
    # -------------------

    document.add_heading("1. Resumo Geral", level=1)

    resumo = (
        df.groupby("execucao")
        .size()
        .reset_index(name="Quantidade")
        .sort_values("Quantidade", ascending=False)
    )

    total = resumo["Quantidade"].sum()
    resumo["Percentual (%)"] = (resumo["Quantidade"] / total * 100).round(1)

    tabela = document.add_table(rows=1, cols=3)
    cab = tabela.rows[0].cells
    cab[0].text = "Situação"
    cab[1].text = "Quantidade"
    cab[2].text = "Percentual (%)"

    for _, row in resumo.iterrows():
        linha = tabela.add_row().cells
        linha[0].text = str(row["execucao"])
        linha[1].text = str(row["Quantidade"])
        linha[2].text = str(row["Percentual (%)"])

    # gráfico geral
    fig, ax = plt.subplots()
    ax.bar(resumo["execucao"], resumo["Quantidade"])
    ax.set_title("Situação Geral das Metas")
    plt.xticks(rotation=45)

    img_stream = BytesIO()
    plt.tight_layout()
    plt.savefig(img_stream, format="png")
    plt.close(fig)

    document.add_picture(img_stream, width=Inches(5))

    # -------------------
    # PERCENTUAL POR EIXO
    # -------------------

    if "Eixo" in df.columns:

        document.add_page_break()
        document.add_heading("2. Execução por Eixo", level=1)

        resumo_eixo = (
            df.groupby(["Eixo", "execucao"])
            .size()
            .reset_index(name="Quantidade")
        )

        tabela_eixo_total = (
            df.groupby("Eixo")
            .size()
            .reset_index(name="Total")
        )

        # gráfico comparativo por eixo
        fig, ax = plt.subplots()

        eixo_counts = df["Eixo"].value_counts()
        ax.bar(eixo_counts.index, eixo_counts.values)
        ax.set_title("Quantidade de Metas por Eixo")
        plt.xticks(rotation=45)

        img_stream = BytesIO()
        plt.tight_layout()
        plt.savefig(img_stream, format="png")
        plt.close(fig)

        document.add_picture(img_stream, width=Inches(5))

        # tabela de totais
        tabela = document.add_table(rows=1, cols=2)
        cab = tabela.rows[0].cells
        cab[0].text = "Eixo"
        cab[1].text = "Total de Metas"

        for _, row in tabela_eixo_total.iterrows():
            linha = tabela.add_row().cells
            linha[0].text = str(row["Eixo"])
            linha[1].text = str(row["Total"])

    # -------------------
    # RANKING RESPONSÁVEIS
    # -------------------

    if "Resp_1" in df.columns:

        document.add_page_break()
        document.add_heading("3. Ranking de Responsáveis", level=1)

        ranking = (
            df.groupby("Resp_1")
            .size()
            .reset_index(name="Quantidade")
            .sort_values("Quantidade", ascending=False)
        )

        tabela = document.add_table(rows=1, cols=2)
        cab = tabela.rows[0].cells
        cab[0].text = "Responsável"
        cab[1].text = "Total de Metas"

        for _, row in ranking.iterrows():
            linha = tabela.add_row().cells
            linha[0].text = str(row["Resp_1"])
            linha[1].text = str(row["Quantidade"])

        # gráfico ranking
        fig, ax = plt.subplots()
        ax.bar(ranking["Resp_1"], ranking["Quantidade"])
        ax.set_title("Ranking de Responsáveis")
        plt.xticks(rotation=45)

        img_stream = BytesIO()
        plt.tight_layout()
        plt.savefig(img_stream, format="png")
        plt.close(fig)

        document.add_picture(img_stream, width=Inches(5))

    # -------------------
    # FINALIZA
    # -------------------

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --------------------------
# CARREGAR DADOS
# --------------------------
atualizar_execucao2()
df_original = carregar_dados()


if df_original.empty:
    st.warning("Nenhuma meta encontrada no banco.")
    st.stop()

df_original["execucao"] = df_original["execucao"].replace("", None)
df_original["execucao"] = df_original["execucao"].fillna("NÃO INICIADA")

situacoes_padrao = [
    "NÃO INICIADA",
    "INICIADA",
    "EM ANDAMENTO",
    "AVANÇADA",
    "CONCLUÍDA"
]

paleta = {
    "NÃO INICIADA": "#9aa0a6",
    "INICIADA": "#4e79a7",
    "EM ANDAMENTO": "#f28e2b",
    "AVANÇADA": "#59a14f",
    "CONCLUÍDA": "#2ca02c"
}

situacoes_exec2 = [
    "A EXECUTAR",
    "EXECUÇÃO PENDENTE",
    "EM EXECUÇÃO",
    "EXECUÇÃO ANTECIPADA",
    "ATRASADA",
    "CUMPRIDA NO PRAZO",
    "CUMPRIDA ANTECIPADA",
    "CUMPRIDA COM ATRASO",
    "NÃO INICIADA"
]

paleta_exec2 = {
    "A EXECUTAR": "#4e79a7",
    "EXECUÇÃO PENDENTE": "#f28e2b",
    "EM EXECUÇÃO": "#59a14f",
    "EXECUÇÃO ANTECIPADA": "#76b7b2",
    "ATRASADA": "#e15759",
    "CUMPRIDA NO PRAZO": "#2ca02c",
    "CUMPRIDA ANTECIPADA": "#8cd17d",
    "CUMPRIDA COM ATRASO": "#ff9da7",
    "NÃO INICIADA": "#9aa0a6"
}


# --------------------------
# FILTROS
# --------------------------

st.sidebar.title("Filtros")

responsaveis = ["Todos"] + sorted(df_original["Resp_1"].dropna().unique())
situacoes = ["Todos"] + situacoes_padrao
eixos = ["Todos"] + sorted(df_original["Eixo"].dropna().unique())

responsavel_sel = st.sidebar.selectbox("Responsável", responsaveis)
situacao_sel = st.sidebar.selectbox("Situação", situacoes)
eixo_sel = st.sidebar.selectbox("Eixo", eixos)

# --------------------------
# DOWNLOAD EXCEL
# --------------------------

st.sidebar.markdown("---")
st.sidebar.subheader("Exportação")

excel_bytes = gerar_excel(df_original)

st.sidebar.download_button(
    label="Baixar base em Excel",
    data=excel_bytes,
    file_name="metas.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --------------------------
# BOTÃO WORD (ACRESCENTADO)
# --------------------------

word_bytes = gerar_relatorio_word(df_original)

st.sidebar.download_button(
    label="Baixar relatório em Word",
    data=word_bytes,
    file_name="relatorio_metas.docx",
    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# --------------------------
# APLICAR FILTROS
# --------------------------

df = df_original.copy()

if responsavel_sel != "Todos":
    df = df[df["Resp_1"] == responsavel_sel]

if situacao_sel != "Todos":
    df = df[df["execucao"] == situacao_sel]

if eixo_sel != "Todos":
    df = df[df["Eixo"] == eixo_sel]

# --------------------------
# DASHBOARD
# --------------------------

st.title("Painel Gerencial de Metas")

total_metas = len(df)
st.metric("Total de Metas", total_metas)

st.divider()

# --------------------------
# SITUAÇÃO DAS METAS
# --------------------------

st.subheader("Situação Geral das Metas")

dados = []
for s in situacoes_padrao:
    qtd = df[df["execucao"] == s].shape[0]
    perc = (qtd / total_metas * 100) if total_metas else 0
    dados.append([s, qtd, round(perc,1)])

tabela_situacao = pd.DataFrame(
    dados,
    columns=["Situação", "Quantidade", "Percentual (%)"]
)

cols = st.columns(5)

for i, row in tabela_situacao.iterrows():
    cols[i].metric(
        label=row["Situação"],
        value=row["Quantidade"],
        delta=f'{row["Percentual (%)"]}%'
    )

st.divider()

# --------------------------
# GRÁFICO SITUAÇÃO
# --------------------------

colA, colB = st.columns([1,1])

with colA:
    st.dataframe(tabela_situacao, use_container_width=True)

with colB:

    grafico1 = (
        alt.Chart(tabela_situacao)
        .mark_bar()
        .encode(
            y=alt.Y("Situação:N", sort="-x", title=None),
            x=alt.X("Quantidade:Q", title=None),
            color=alt.Color(
                "Situação:N",
                scale=alt.Scale(
                    domain=situacoes_padrao,
                    range=[paleta[s] for s in situacoes_padrao]
                ),
                legend=None
            ),
            tooltip=["Situação", "Quantidade", "Percentual (%)"]
        )
        .properties(height=400, width=700)
    )

    st.altair_chart(grafico1)

st.divider()

# --------------------------
# EXECUÇÃO POR RESPONSÁVEL
# --------------------------

st.subheader("Execução por Responsável")

tabela_resp = (
    df.groupby(["Resp_1", "execucao"])
    .size()
    .reset_index(name="Quantidade")
)

altura = max(200, 25 * tabela_resp["Resp_1"].nunique())

grafico = (
    alt.Chart(tabela_resp)
    .mark_bar()
    .encode(
        y=alt.Y(
            "Resp_1:N",
            sort="-x",
            title=None,
            axis=alt.Axis(labelLimit=1000, labelOverlap=False)
        ),
        x=alt.X("Quantidade:Q", title=None),
        color=alt.Color(
            "execucao:N",
            scale=alt.Scale(
                domain=situacoes_padrao,
                range=[paleta[s] for s in situacoes_padrao]
            ),
            legend=alt.Legend(orient="bottom", columns=3)
        ),
        tooltip=["Resp_1", "execucao", "Quantidade"]
    )
    .properties(height=altura)
)

st.altair_chart(grafico, use_container_width=True)

st.divider()

# --------------------------
# RESUMO POR EIXO E SITUAÇÃO
# --------------------------

st.subheader("Resumo de Metas por Eixo e Situação")

if "Eixo" not in df.columns:
    st.warning("A coluna 'Eixo' não existe na tabela metas.")
else:

    tabela_eixo = pd.pivot_table(
        df,
        index="Eixo",
        columns="execucao",
        values="Meta",
        aggfunc="count",
        fill_value=0
    )

    for s in situacoes_padrao:
        if s not in tabela_eixo.columns:
            tabela_eixo[s] = 0

    tabela_eixo = tabela_eixo[situacoes_padrao]
    tabela_eixo["TOTAL"] = tabela_eixo.sum(axis=1)

    st.dataframe(tabela_eixo, use_container_width=True)

# ---------------------------------------------
# METAS DETALHADAS GERAIS
# ---------------------------------------------

st.subheader("Metas Detalhadas (Visão Geral)")

colunas_exibir = ["Eixo", "Resp_1", "Meta", "Descrição da Meta", "execucao"]
colunas_existentes = [c for c in colunas_exibir if c in df.columns]

st.dataframe(df[colunas_existentes], use_container_width=True)

st.divider()
st.subheader("Situação Temporal por Responsável")
total_temporal = len(df)
st.metric("Total de Metas (Temporal)", total_temporal)

if "execucao2" in df.columns:

    total_temporal = len(df)

    dados_exec2 = []
    for s in situacoes_exec2:
        qtd = df[df["execucao2"] == s].shape[0]
        perc = (qtd / total_temporal * 100) if total_temporal else 0
        dados_exec2.append([s, qtd, round(perc, 1)])

    tabela_indicadores_exec2 = pd.DataFrame(
        dados_exec2,
        columns=["Situação", "Quantidade", "Percentual (%)"]
    )

    # cria colunas dinâmicas (3 por linha para não ficar esmagado)
    n_colunas = 3
    for i in range(0, len(tabela_indicadores_exec2), n_colunas):
        cols = st.columns(n_colunas)
        for j in range(n_colunas):
            if i + j < len(tabela_indicadores_exec2):
                row = tabela_indicadores_exec2.iloc[i + j]
                cols[j].metric(
                    label=row["Situação"],
                    value=row["Quantidade"],
                    delta=f'{row["Percentual (%)"]}%'
                )

    st.divider()



if "execucao2" in df.columns:

    tabela_exec2 = (
        df.groupby(["Resp_1", "execucao2"])
        .size()
        .reset_index(name="Quantidade")
    )

    altura2 = max(200, 25 * tabela_exec2["Resp_1"].nunique())

    grafico_exec2 = (
        alt.Chart(tabela_exec2)
        .mark_bar()
        .encode(
            y=alt.Y(
                "Resp_1:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=1000, labelOverlap=False)
            ),
            x=alt.X("Quantidade:Q", title=None),
            color=alt.Color(
                "execucao2:N",
                scale=alt.Scale(
                    domain=situacoes_exec2,
                    range=[paleta_exec2[s] for s in situacoes_exec2]
                ),
                legend=alt.Legend(orient="bottom", columns=3)
            ),
            tooltip=["Resp_1", "execucao2", "Quantidade"]
        )
        .properties(height=altura2)
    )

    st.altair_chart(grafico_exec2, use_container_width=True)

else:
    st.warning("A coluna execucao2 ainda não foi gerada.")



st.divider()


st.divider()
st.subheader("Situação Temporal por Responsável")

if "execucao2" in df.columns:
    tabela_exec2 = (
        df.groupby(["Resp_1", "execucao2"])
        .size()
        .reset_index(name="Quantidade")
    )
    st.dataframe(tabela_exec2, use_container_width=True)