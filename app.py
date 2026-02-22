import streamlit as st
import os
import pandas as pd
import psycopg
from streamlit_oauth import OAuth2Component
import jwt

st.set_page_config(layout="wide")
# =====================================================
# CONFIG OAUTH GOOGLE
# =====================================================

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

# =====================================================
# CONEXÃO POSTGRESQL
# =====================================================

def conectar():
    if "DATABASE_URL" in st.secrets:
        return psycopg.connect(st.secrets["DATABASE_URL"])

    return psycopg.connect(
        host="localhost",
        dbname="metas_dev",
        user="postgres",
        password="240119",
        port="5432"
    )

# =====================================================
# BUSCAR RESPONSÁVEL
# =====================================================

def buscar_responsavel_por_email(email):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT usuario
        FROM responsaveis
        WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
    """, (email.strip(),))

    resultado = cursor.fetchone()
    conn.close()
    return resultado

# =====================================================
# CARREGAR METAS
# =====================================================

def carregar_metas(usuario):
    conn = conectar()

    query = """
    SELECT 
        "Ordem" as "ID",
        "Meta",
        "Descrição da Meta" as "Descricao",
        "execucao" as "Status",
        "Ano_Conclusao" as "Ano"
    FROM metas
    WHERE "Resp_1" = %s
    ORDER BY "Ordem"
    """

    df = pd.read_sql(query, conn, params=(usuario,))
    conn.close()

    if df.empty:
        return df

    df["Status"] = df["Status"].fillna("NÃO INICIADA")
    df["Ano"] = df["Ano"].fillna("")

    return df

# =====================================================
# ATUALIZAR STATUS
# =====================================================

def atualizar_status(id_meta, status, ano):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE metas
        SET "execucao" = %s,
            "Ano_Conclusao" = %s
        WHERE "Ordem" = %s
    """, (status, ano, id_meta))

    conn.commit()
    conn.close()

# =====================================================
# CONFIGURAÇÕES
# =====================================================

status_opcoes = [
    "NÃO INICIADA",
    "INICIADA",
    "EM ANDAMENTO",
    "AVANÇADA",
    "CONCLUÍDA"
]

anos_opcoes = ["2023", "2024", "2025", "2026"]

# =====================================================
# SESSÃO
# =====================================================

if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = None
    st.session_state.email = None

# =====================================================
# LOGIN
# =====================================================

if not st.session_state.logado:

    st.title("Sistema de Acompanhamento de Metas")

    result = oauth2.authorize_button(
        name="Entrar com Google",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google_login"
    )

    if result and "token" in result:

        id_token = result["token"]["id_token"]
        decoded = jwt.decode(id_token, options={"verify_signature": False})
        email = decoded.get("email")

        if email:
            responsavel = buscar_responsavel_por_email(email)

            if responsavel:
                st.session_state.logado = True
                st.session_state.usuario = responsavel[0]
                st.session_state.email = email
                st.rerun()
            else:
                st.error("E-mail não cadastrado como responsável.")

    st.stop()

# =====================================================
# TELA PRINCIPAL
# =====================================================

st.title(f"Metas do responsável: {st.session_state.usuario}")
st.caption(f"Logado como: {st.session_state.email}")

if st.button("Sair"):
    st.session_state.clear()
    st.rerun()

df = carregar_metas(st.session_state.usuario)

if df.empty:
    st.info("Nenhuma meta encontrada.")
    st.stop()

# =====================================================
# RESUMO
# =====================================================

st.subheader("Resumo geral das metas")

total_metas = len(df)

resumo = df["Status"].value_counts().reset_index()
resumo.columns = ["Status", "Quantidade"]
resumo["Percentual (%)"] = (resumo["Quantidade"] / total_metas * 100).round(1)

cols = st.columns(len(resumo) + 1)
cols[0].metric("Total de Metas", total_metas)

for i, row in resumo.iterrows():
    cols[i + 1].metric(
        row["Status"],
        int(row["Quantidade"]),
        f"{row['Percentual (%)']}%"
    )

st.divider()

# =====================================================
# METAS EDITÁVEIS
# =====================================================

metas_concluidas = df[df["Status"] == "CONCLUÍDA"].copy()
metas_editaveis = df[df["Status"] != "CONCLUÍDA"].copy()

st.subheader("Metas em andamento")

alteracoes = []

if not metas_editaveis.empty:

    h1, h2, h3, h4 = st.columns([2,4,2,2])
    h1.write("Meta")
    h2.write("Descrição")
    h3.write("Situação")
    h4.write("Ano")

    for _, row in metas_editaveis.iterrows():

        c1, c2, c3, c4 = st.columns([2,4,2,2])

        c1.write(row["Meta"])
        c2.write(row["Descricao"])

        novo_status = c3.selectbox(
            "",
            status_opcoes,
            index=status_opcoes.index(row["Status"]) if row["Status"] in status_opcoes else 0,
            key=f"status_{row['ID']}",
            label_visibility="collapsed"
        )

        ano_escolhido = ""

        if novo_status == "CONCLUÍDA":
            ano_escolhido = c4.selectbox(
                "",
                anos_opcoes,
                key=f"ano_{row['ID']}",
                label_visibility="collapsed"
            )
        else:
            c4.write("-")

        alteracoes.append((row["ID"], novo_status, ano_escolhido))

else:
    st.info("Não há metas em andamento.")

if st.button("Salvar alterações"):

    for id_meta, status, ano in alteracoes:
        atualizar_status(id_meta, status, ano)

    st.success("Alterações salvas com sucesso!")
    st.rerun()

if not metas_concluidas.empty:
    st.subheader("Metas concluídas")

    st.dataframe(
        metas_concluidas.drop(columns=["ID"]),
        use_container_width=True,
        hide_index=True
    )