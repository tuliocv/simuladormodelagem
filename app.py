# app.py
# Jogo: "Empresa Quebra ou Sobrevive?" (Streamlit)
# + Registro de respostas (alunos) + Login de admin (baixar CSV)
#
# Como rodar:
#   streamlit run app.py
#
# Para login admin, crie .streamlit/secrets.toml com:
#   ADMIN_PASSWORD="sua_senha_forte_aqui"

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
LOCK_PATH = LOG_PATH + ".lock"

os.makedirs(DATA_DIR, exist_ok=True)


# ----------------------------
# Helpers
# ----------------------------
def brl(x: float) -> str:
    s = f"{x:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_results(cf: float, cv: float, p: float, q: int, desconto_pct: float, juros_pct: float, emprestimo: float):
    p_desc = p * (1 - desconto_pct / 100.0)
    receita = p_desc * q
    custo_total = cf + cv * q

    # Juros simples no empréstimo (1 período)
    juros = emprestimo * (juros_pct / 100.0)
    lucro = receita - custo_total - juros

    margem_unit = p_desc - cv
    pe = None
    if margem_unit > 0:
        pe = cf / margem_unit

    return {
        "preco_com_desconto": p_desc,
        "receita": receita,
        "custo_total": custo_total,
        "juros": juros,
        "lucro": lucro,
        "margem_unitaria": margem_unit,
        "ponto_equilibrio": pe,
    }


def survival_score(lucro: float, caixa_inicial: float, caixa_minimo: float, risco: int, endividamento: float, receita: float):
    caixa_final = caixa_inicial + lucro

    if caixa_final < 0:
        caixa_pts = 0
    elif caixa_final < caixa_minimo:
        caixa_pts = 25
    else:
        caixa_pts = 40

    margem = (lucro / receita) if receita > 0 else -1
    if margem < -0.10:
        margem_pts = 0
    elif margem < 0:
        margem_pts = 10
    elif margem < 0.08:
        margem_pts = 20
    else:
        margem_pts = 30

    risco_pen = (risco - 1) * 4

    debt_ratio = (endividamento / receita) if receita > 0 else 1.5
    if debt_ratio <= 0.10:
        debt_pen = 0
    elif debt_ratio <= 0.25:
        debt_pen = 5
    elif debt_ratio <= 0.40:
        debt_pen = 10
    else:
        debt_pen = 18

    score = caixa_pts + margem_pts - risco_pen - debt_pen
    return int(clamp(score, 0, 100)), caixa_final, margem


def badge(score: int, caixa_final: float):
    if caixa_final < 0:
        return "☠️ QUEBROU", "A empresa ficou com caixa negativo."
    if score >= 80:
        return "🚀 SOBREVIVEU E CRESCE", "Decisões sólidas: margem e caixa saudáveis."
    if score >= 55:
        return "✅ SOBREVIVEU", "Passou raspando, mas ainda está de pé."
    if score >= 35:
        return "⚠️ NO LIMITE", "Sinais de alerta: ajuste preço, custo ou volume."
    return "🧨 RISCO ALTO", "Qualquer imprevisto pode derrubar a empresa."


def safe_append_jsonl(path: str, lock_path: str, payload: dict):
    payload = dict(payload)
    payload["ts"] = datetime.now().isoformat(timespec="seconds")

    # Lock cross-process/thread to support many concurrent writes
    with Lock(lock_path, timeout=10):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_history(limit: int = 5000) -> pd.DataFrame:
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame()

    rows = []
    # Lock for safe reads while others write
    with Lock(LOCK_PATH, timeout=10):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("ts", ascending=False).head(limit)
    return df


def admin_password() -> str:
    # Prefer secrets; fallback to env var
    return str(st.secrets.get("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", "")))


def is_admin() -> bool:
    return bool(st.session_state.get("is_admin", False))


def require_admin_login_ui():
    st.subheader("🔐 Área do mediador (admin)")
    if is_admin():
        st.success("Você está logado como admin.")
        if st.button("Sair", use_container_width=True):
            st.session_state["is_admin"] = False
            st.rerun()
        return

    pw = st.text_input("Senha do mediador", type="password", placeholder="Digite a senha")
    if st.button("Entrar", type="primary", use_container_width=True):
        if not admin_password():
            st.error("ADMIN_PASSWORD não configurada. Crie .streamlit/secrets.toml (veja comentário no topo do arquivo).")
        elif pw == admin_password():
            st.session_state["is_admin"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")


# ----------------------------
# Cenários (Cartas)
# ----------------------------
SCENARIOS = [
    {
        "id": "S1",
        "nome": "Cafeteria do Campus ☕",
        "historia": "Você vende café e salgados. O fluxo de alunos oscila com provas e feriados.",
        "cf": 8500,
        "cv": 6.5,
        "p": 14.0,
        "caixa": 6000,
        "caixa_min": 1500,
        "risco": 3,
        "meta_score": 55,
        "missao": "Sobreviva mantendo o caixa acima do mínimo e evitando prejuízo.",
    },
    {
        "id": "S2",
        "nome": "Loja Online de Camisetas 👕",
        "historia": "Você depende de anúncios. Desconto aumenta vendas, mas aperta a margem.",
        "cf": 12000,
        "cv": 18.0,
        "p": 45.0,
        "caixa": 9000,
        "caixa_min": 2500,
        "risco": 4,
        "meta_score": 60,
        "missao": "Cresça sem ‘queimar’ margem. Desconto alto pode te derrubar.",
    },
    {
        "id": "S3",
        "nome": "Serviço de Manutenção Residencial 🔧",
        "historia": "Você tem poucos clientes, mas ticket maior. Se errar preço, fica sem demanda.",
        "cf": 7000,
        "cv": 55.0,
        "p": 130.0,
        "caixa": 5000,
        "caixa_min": 1200,
        "risco": 2,
        "meta_score": 55,
        "missao": "Ajuste o preço e o volume para não ficar no vermelho.",
    },
    {
        "id": "S4",
        "nome": "Hamburgueria Delivery 🍔",
        "historia": "Fim de mês o movimento cai. Você pensa em cupom de desconto.",
        "cf": 16000,
        "cv": 14.5,
        "p": 32.0,
        "caixa": 11000,
        "caixa_min": 3000,
        "risco": 5,
        "meta_score": 65,
        "missao": "Passe pelo mês difícil sem estourar caixa ou juros.",
    },
]

# ----------------------------
# UI
# ----------------------------
st.title("💸 Empresa: Quebra ou Sobrevive?")
st.caption("Simulação leve para decisões de preço, desconto, volume e empréstimo (juros simples).")

with st.expander("🎮 Como jogar (bem rápido)", expanded=False):
    st.markdown(
        """
- Escolha um **cenário** (a “carta” da empresa).
- Em grupo, decidam **quantidade**, **desconto**, e se precisa de **empréstimo**.
- Clique em **Simular** e depois em **Registrar resposta do grupo**.
- Meta: bater a pontuação mínima do cenário e não ficar com **caixa negativo**.
        """.strip()
    )

# Seleção de cenário
scenario_name = st.selectbox("Escolha o cenário", [f"{s['id']} — {s['nome']}" for s in SCENARIOS])
scenario_id = scenario_name.split("—")[0].strip()
sc = next(s for s in SCENARIOS if s["id"] == scenario_id)

st.divider()
st.subheader(f"🃏 {sc['nome']}")
st.write(sc["historia"])
cols = st.columns(3)
cols[0].metric("Custo fixo (mês)", brl(sc["cf"]))
cols[1].metric("Custo variável (unid.)", brl(sc["cv"]))
cols[2].metric("Preço base (unid.)", brl(sc["p"]))
cols2 = st.columns(3)
cols2[0].metric("Caixa inicial", brl(sc["caixa"]))
cols2[1].metric("Caixa mínimo", brl(sc["caixa_min"]))
cols2[2].metric("Risco (1–5)", str(sc["risco"]))

st.info(f"🎯 Missão: {sc['missao']}  \n🏁 Meta de pontuação: **{sc['meta_score']}**")

st.divider()
st.subheader("🧩 Suas decisões (em grupo)")

c1, c2 = st.columns(2)
with c1:
    q = st.slider("Quantidade vendida (unidades)", min_value=0, max_value=6000, value=3000, step=100)
    desconto = st.slider("Desconto (%)", min_value=0, max_value=30, value=10, step=1)
with c2:
    juros_pct = st.slider("Juros simples do empréstimo (%)", min_value=0.0, max_value=10.0, value=3.0, step=0.5)
    emprestimo = st.slider("Empréstimo (R$)", min_value=0, max_value=30000, value=0, step=1000)

# Identificação do grupo (obrigatório para registro)
st.subheader("🧑‍🤝‍🧑 Identificação do grupo (para registrar)")
grupo_id = st.text_input("Nome do grupo (obrigatório)", value="", placeholder="Ex.: Grupo 7 - Santo Amaro")
nomes_alunos = st.text_area(
    "Nomes dos integrantes (obrigatório)",
    value="",
    placeholder="Escreva 1 por linha. Ex:\nAna Silva\nBruno Souza\nCarla Santos",
    height=120,
)
justificativa = st.text_area(
    "Justificativa da decisão (curta e objetiva)",
    value="",
    placeholder="Por que escolhemos esse desconto/quantidade? O que queríamos otimizar (lucro, caixa, risco)?",
    height=120,
)

# Ajustes avançados (opcional)
with st.expander("⚙️ Ajustes avançados (opcional)", expanded=False):
    st.caption("Se quiser deixar ainda mais leve, ignore esta parte.")
    cf = st.number_input("Custo fixo", min_value=0.0, value=float(sc["cf"]), step=500.0)
    cv = st.number_input("Custo variável por unidade", min_value=0.0, value=float(sc["cv"]), step=0.5)
    p = st.number_input("Preço unitário (base)", min_value=0.0, value=float(sc["p"]), step=0.5)

    cf, cv, p = float(sc["cf"]), float(sc["cv"]), float(sc["p"])

st.divider()

# Sessão: guardar último resultado pra registrar
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None

# Simulação
if st.button("🚦 Simular agora", type="primary", use_container_width=True):
    res = compute_results(cf=cf, cv=cv, p=p, q=q, desconto_pct=desconto, juros_pct=juros_pct, emprestimo=emprestimo)
    score, caixa_final, margem_rel = survival_score(
        lucro=res["lucro"],
        caixa_inicial=float(sc["caixa"]),
        caixa_minimo=float(sc["caixa_min"]),
        risco=int(sc["risco"]),
        endividamento=float(emprestimo),
        receita=res["receita"],
    )
    status, msg = badge(score, caixa_final)

    st.session_state["last_result"] = {
        "res": res,
        "score": score,
        "caixa_final": caixa_final,
        "margem_rel": margem_rel,
        "status": status,
        "msg": msg,
        "inputs": {
            "cenario": sc["id"],
            "cenario_nome": sc["nome"],
            "q": int(q),
            "desconto_pct": float(desconto),
            "juros_pct": float(juros_pct),
            "emprestimo": float(emprestimo),
            "cf": float(cf),
            "cv": float(cv),
            "p": float(p),
        },
    }

# Mostrar resultados se já simulou
lr = st.session_state.get("last_result")
if lr:
    res = lr["res"]
    score = lr["score"]
    caixa_final = lr["caixa_final"]
    status = lr["status"]
    msg = lr["msg"]
    pe = res["ponto_equilibrio"]

    st.subheader("📈 Resultados")
    m1, m2, m3 = st.columns(3)
    m1.metric("Preço final", brl(res["preco_com_desconto"]))
    m2.metric("Receita", brl(res["receita"]))
    m3.metric("Custo total", brl(res["custo_total"]))

    m4, m5, m6 = st.columns(3)
    m4.metric("Juros (simples)", brl(res["juros"]))
    m5.metric("Lucro do mês", brl(res["lucro"]))
    m6.metric("Caixa final", brl(caixa_final))

    if pe is None:
        st.warning("⚠️ Margem unitária negativa/zero: cada venda piora o resultado.")
    else:
        st.caption(f"📌 Ponto de equilíbrio estimado: **{pe:.0f} unidades**")
        pct_pe = 0 if pe <= 0 else clamp(lr["inputs"]["q"] / pe, 0, 1.5)
        st.progress(min(1.0, pct_pe))

    st.subheader("🏁 Veredito")
    st.metric("Pontuação (0–100)", score)
    if caixa_final < 0:
        st.error(f"**{status}** — {msg}")
    elif score >= sc["meta_score"]:
        st.success(f"**{status}** — {msg}")
    else:
        st.warning(f"**{status}** — {msg}")

    st.subheader("🧠 Dicas rápidas")
    tips = []
    if res["lucro"] < 0:
        tips.append("🔻 Prejuízo: reduza desconto, aumente preço ou aumente volume.")
    if res["margem_unitaria"] <= 0:
        tips.append("❗ Preço final ≤ custo variável: cada venda aumenta o prejuízo.")
    if pe is not None and lr["inputs"]["q"] < pe:
        tips.append("📌 Você vendeu abaixo do ponto de equilíbrio.")
    if lr["inputs"]["emprestimo"] > 0 and res["juros"] > (0.1 * max(res["receita"], 1)):
        tips.append("💳 Juros estão pesando. Avalie reduzir empréstimo.")
    if lr["inputs"]["desconto_pct"] >= 20:
        tips.append("🏷️ Desconto alto aperta margem. Confirme se o lucro melhorou.")
    if not tips:
        tips.append("✅ Boa rodada. Tente otimizar: menos desconto com mesmo volume.")
    st.write("\n".join(tips))

    st.divider()

    # Registro de resposta (grava no jsonl com lock)
    st.subheader("📝 Registrar resposta do grupo")
    st.caption("Faça a simulação e registre. O mediador poderá baixar tudo em CSV depois.")

    can_submit = True
    if not grupo_id.strip():
        st.warning("Informe o **Nome do grupo** para registrar.")
        can_submit = False
    if not nomes_alunos.strip():
        st.warning("Informe os **nomes dos integrantes** para registrar.")
        can_submit = False

    if st.button("✅ Registrar resposta do grupo", disabled=not can_submit, use_container_width=True):
        alunos_lista = [x.strip() for x in nomes_alunos.splitlines() if x.strip()]
        payload = {
            "grupo": grupo_id.strip(),
            "alunos": alunos_lista,
            "justificativa": justificativa.strip(),
            **lr["inputs"],
            "preco_final": float(res["preco_com_desconto"]),
            "receita": float(res["receita"]),
            "custo_total": float(res["custo_total"]),
            "juros": float(res["juros"]),
            "lucro": float(res["lucro"]),
            "caixa_inicial": float(sc["caixa"]),
            "caixa_final": float(caixa_final),
            "ponto_equilibrio": None if pe is None else float(pe),
            "score": int(score),
            "meta_score": int(sc["meta_score"]),
            "status": status,
        }
        safe_append_jsonl(LOG_PATH, LOCK_PATH, payload)
        st.success("Registrado! ✅ (Seu mediador poderá baixar depois.)")

st.divider()

# ----------------------------
# Área do mediador (login + download)
# ----------------------------
with st.expander("🔐 Área do mediador (baixar respostas)", expanded=False):
    require_admin_login_ui()

    if is_admin():
        df = load_history(limit=10000)
        if df.empty:
            st.info("Ainda não há respostas registradas.")
        else:
            # Ajustes úteis p/ export
            if "alunos" in df.columns:
                df["alunos"] = df["alunos"].apply(lambda x: "\n".join(x) if isinstance(x, list) else str(x))
            # Ordena cronologicamente para export (mais antigo -> mais novo)
            df_export = df.sort_values("ts", ascending=True)

            st.subheader("📥 Baixar respostas")
            st.caption("Baixe em CSV para discutir depois em aula (Excel/Sheets).")

            csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Download CSV (todas as respostas)",
                data=csv_bytes,
                file_name="respostas_empresa_quebra_ou_sobrevive.csv",
                mime="text/csv",
                use_container_width=True,
            )

            st.subheader("🔎 Pré-visualização (últimas 50)")
            st.dataframe(df.head(50), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🧹 Administração")
            st.caption("Use apenas se precisar reiniciar a turma.")
            if st.button("Apagar todas as respostas (local)", type="secondary", use_container_width=True):
                with Lock(LOCK_PATH, timeout=10):
                    if os.path.exists(LOG_PATH):
                        os.remove(LOG_PATH)
                st.success("Respostas apagadas.")
                st.rerun()
