import sqlite3
import pandas as pd

# conectar ao banco já existente
conn = sqlite3.connect("banco.db")

# ler planilha
df = pd.read_excel("basegeral.xlsx")

# garantir que exista a coluna de execução
if "execucao" not in df.columns:
    df["execucao"] = ""

# gravar no banco
df.to_sql("metas", conn, if_exists="replace", index=False)

conn.close()

print("Tabela metas criada com sucesso.")