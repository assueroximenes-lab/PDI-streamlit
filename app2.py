import streamlit as st
st.set_page_config(layout="wide")

import sqlite3
import pandas as pd

# ---------------------------
# BANCO
# ---------------------------
def conectar():
    return sqlite3.connect("banco.db", check_same_thread=False)


def verificar_login(usuario, senha):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM responsaveis WHERE usuario=? AND senha=?",
        (usuario, senha)
    )

    resultado = cursor.fetchone()
    conn.close()
    return resultado


def carregar_metas(usuario):
    conn = conectar()

    query = """
    SELECT rowid as ID,
           Meta,
           `Descrição da Meta` as Descricao,
           execucao as Status,
           Ano_Conclusao as Ano
    FROM metas
    WHERE Resp_1 = ?
    """

    df = pd.read_sql(query, conn, params=(usuario,))
    conn.close()

    df["Status"] = df["Status"].fillna("NÃO INICIADA")
    df["Ano"] = df["Ano"].fillna("")
    return df


def atualizar_status(id_meta, status, ano):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE metas
        SET execucao=?, Ano_Conclusao=?
        WHERE rowid=?
    """, (status, ano, id_meta))

    conn.commit()
    conn.close()


# ---------------------------
# CONFIGURAÇÕES
# ---------------------------
status_opcoes = [
    "NÃO INICIADA",
    "INICIADA",
    "EM ANDAMENTO",
    "AVANÇADA",
    "CONCLUÍDA"
]

anos_opcoes = ["2023", "2024", "2025", "2026"]

# ---------------------------
# SESSÃO
# ---------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = None


# ---------------------------
# LOGIN
# ---------------------------
if not st.session_state.logado:

    st.title("Sistema de Acompanhamento de Metas")

    usuario = st.text_input("Responsável")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if verificar_login(usuario, senha):
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")


# ---------------------------
# TELA PRINCIPAL
# ---------------------------
else:

    st.title(f"Metas do responsável: {st.session_state.usuario}")

    if st.button("Sair"):
        st.session_state.logado = False
        st.session_state.usuario = None
        st.rerun()

    df = carregar_metas(st.session_state.usuario)

    if df.empty:
        st.info("Nenhuma meta encontrada.")
        st.stop()

    # ---------------------------
    # RESUMO GERAL (INÍCIO)
    # ---------------------------
    st.subheader("Resumo geral das metas")

    total_metas = len(df)

    # Conta corretamente
    resumo = df["Status"].value_counts().reset_index()
    resumo.columns = ["Status", "Quantidade"]

    # Garante que é número
    resumo["Quantidade"] = pd.to_numeric(resumo["Quantidade"])

    # Calcula percentual
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

    # ---------------------------
    # METAS EM ANDAMENTO
    # ---------------------------
    metas_concluidas = df[df["Status"] == "CONCLUÍDA"].copy()
    metas_editaveis = df[df["Status"] != "CONCLUÍDA"].copy()

    st.subheader("Metas em andamento")

    alteracoes = []

    if not metas_editaveis.empty:

        st.markdown("""
        <style>
        .cabecalho-tabela {
            background-color: #f0f2f6;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #e0e0e0;
            font-weight: 600;
        }
        </style>
        """, unsafe_allow_html=True)

        h1, h2, h3, h4 = st.columns([2,4,2,2])
        h1.markdown('<div class="cabecalho-tabela">Meta</div>', unsafe_allow_html=True)
        h2.markdown('<div class="cabecalho-tabela">Descrição</div>', unsafe_allow_html=True)
        h3.markdown('<div class="cabecalho-tabela">Situação</div>', unsafe_allow_html=True)
        h4.markdown('<div class="cabecalho-tabela">Ano</div>', unsafe_allow_html=True)

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

    # ---------------------------
    # BOTÃO SALVAR
    # ---------------------------
    if st.button("Salvar alterações"):

        for _, status, ano in alteracoes:
            if status == "CONCLUÍDA" and ano == "":
                st.warning("Informe o ano para todas as metas concluídas.")
                st.stop()

        for id_meta, status, ano in alteracoes:
            atualizar_status(id_meta, status, ano)

        st.success("Alterações salvas com sucesso!")
        st.rerun()

    # ---------------------------
    # METAS CONCLUÍDAS
    # ---------------------------
    if not metas_concluidas.empty:
        st.subheader("Metas concluídas")

        st.dataframe(
            metas_concluidas.drop(columns=["ID"]),
            use_container_width=True,
            hide_index=True
        )
