# app.py
# Empresa: Quebra ou Sobrevive?
# Versão simplificada (sem ajustes avançados)

import os
import json
from datetime import datetime

import pandas as pd
import streamlit as st
from portalocker import Lock

# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Empresa: Quebra ou Sobrevive?", page_icon="💸", layout="centered")

DATA_DIR = "data"
LOG_PATH = os.path.join(DATA_DIR, "rodadas.jsonl")
LOCK_PATH = os.path.join(DATA_DIR, "rodadas.lock")

os.makedirs(DATA_DIR, exist_ok=True)

# ----------------------------
# Helpers
# ----------------------------
def brl(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def compute_results(cf, cv, p, q, desconto, juros_pct, emprestimo):
    preco_final = p * (1 - desconto / 100)
    receita = preco_final * q
    custo_total = cf + cv * q
    juros = emprestimo * (juros_pct / 100)
    lucro = receita - custo_total - juros

    margem_unit = preco_final - cv
    pe = cf / margem_unit if margem_unit > 0 else None

    return preco_final, receita, custo_total, juros, lucro, margem_unit, pe

def survival_score(lucro, caixa_inicial, caixa_min, risco, emprestimo, receita):
    caixa_final = caixa_inicial + lucro

    caixa_pts = 40 if caixa_final >= caixa_min else 25 if caixa_final > 0 else 0

    margem_rel = (lucro / receita) if receita > 0 else -1
    if margem_rel < 0:
        margem_pts = 10
    elif margem_rel < 0.08:
        margem_pts = 20
    else:
        margem_pts = 30

    risco_pen = (risco - 1) * 4
    debt_ratio = (emprestimo / receita) if receita > 0 else 1.5
    debt_pen = 0 if debt_ratio <= 0.10 else 5 if debt_ratio <= 0.25 else 10

    score = caixa_pts + margem_pts - risco_pen - debt_pen
    return int(clamp(score, 0, 100)), caixa_final

def safe_append(payload):
    payload["ts"] = datetime.now().isoformat(timespec="seconds")
    with Lock(LOCK_PATH, timeout=10):
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def load_data():
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame()
    rows = []
    with Lock(LOCK_PATH, timeout=10):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                rows.append(json.loads(line))
    return pd.DataFrame(rows)

# ----------------------------
# Cenários
# ----------------------------
SCENARIOS = [
    {"id": "S1", "nome": "Cafeteria ☕", "cf": 8500, "cv": 6.5, "p": 14, "caixa": 6000, "caixa_min": 1500, "risco": 3, "meta": 55},
    {"id": "S2", "nome": "Loja Online 👕", "cf": 12000, "cv": 18, "p": 45, "caixa": 9000, "caixa_min": 2500, "risco": 4, "meta": 60},
]

# ----------------------------
# Interface
# ----------------------------
st.title("💸 Empresa: Quebra ou Sobrevive?")

scenario_name = st.selectbox("Escolha o cenário", [f"{s['id']} - {s['nome']}" for s in SCENARIOS])
scenario_id = scenario_name.split("-")[0].strip()
sc = next(s for s in SCENARIOS if s["id"] == scenario_id)

c1, c2, c3 = st.columns(3)
c1.metric("Custo fixo (CF)", brl(sc["cf"]))
c2.metric("Custo variável (CV)", brl(sc["cv"]))
c3.metric("Preço base (P)", brl(sc["p"]))

c4, c5, c6 = st.columns(3)
c4.metric("Caixa inicial", brl(sc["caixa"]))
c5.metric("Caixa mínimo", brl(sc["caixa_min"]))
c6.metric("Risco (1–5)", str(sc["risco"]))

q = st.slider("Quantidade", 0, 6000, 3000, 100)
desconto = st.slider("Desconto (%)", 0, 30, 10)
juros = st.slider("Juros (%)", 0.0, 10.0, 3.0)
emprestimo = st.slider("Empréstimo (R$)", 0, 30000, 0, 1000)

grupo = st.text_input("Nome do grupo")
alunos = st.text_area("Nomes dos alunos (1 por linha)")
justificativa = st.text_area("Justificativa")

if st.button("Simular"):
    preco_final, receita, custo_total, juros_val, lucro, margem_unit, pe = compute_results(
        sc["cf"], sc["cv"], sc["p"], q, desconto, juros, emprestimo
    )

    score, caixa_final = survival_score(
        lucro, sc["caixa"], sc["caixa_min"], sc["risco"], emprestimo, receita
    )

    st.metric("Lucro", brl(lucro))
    st.metric("Caixa final", brl(caixa_final))
    st.metric("Score", score)

    if grupo and alunos:
        payload = {
            "grupo": grupo,
            "alunos": alunos,
            "justificativa": justificativa,
            "cenario": sc["id"],
            "q": q,
            "desconto": desconto,
            "emprestimo": emprestimo,
            "lucro": lucro,
            "score": score,
        }
        safe_append(payload)
        st.success("Registrado!")

# ----------------------------
# Área Admin
# ----------------------------
st.divider()
with st.expander("🔐 Área do mediador"):
    senha = st.text_input("Senha", type="password")
    if senha == st.secrets.get("ADMIN_PASSWORD"):
        st.success("Admin logado")

        df = load_data()
        if not df.empty:
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Baixar CSV", csv, "respostas.csv", "text/csv")
            st.dataframe(df.tail(50))
