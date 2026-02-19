import sqlite3

# lista de responsáveis informados
responsaveis = [
    "ARG","CME","CPA","DAE","DCOM","DDP","DENS","DITE",
    "DPFIC","DQV","DRI","DRINT","PRAE","PREC","PREFEITURA",
    "PREG","PROAD","PROGEPE","PROPLAN","PRPPGI","REITORIA",
    "SECAC","SEMAS","SIB","STI"
]

conn = sqlite3.connect("banco.db")
cursor = conn.cursor()

# criar tabela de usuários
cursor.execute("""
CREATE TABLE IF NOT EXISTS responsaveis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE,
    senha TEXT
)
""")

# inserir usuários (senha padrão: 1234)
for resp in responsaveis:
    cursor.execute(
        "INSERT OR IGNORE INTO responsaveis (usuario, senha) VALUES (?, ?)",
        (resp, "1234")
    )

conn.commit()
conn.close()

print("Usuários criados com sucesso!")