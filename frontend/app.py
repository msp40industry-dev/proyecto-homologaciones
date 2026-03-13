"""
Frontend Streamlit — POC Sistema RAG de Reformas de Vehículos
Conecta con el backend FastAPI en http://localhost:8000
"""

import requests
import streamlit as st

# ─── Config ───────────────────────────────────────────────────────────────────

BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Reformas de Vehículos",
    page_icon="🚗",
    layout="wide",
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_categorias() -> dict:
    try:
        r = requests.get(f"{BACKEND_URL}/categorias", timeout=5)
        return r.json()
    except Exception:
        return {"M": ["M1", "M2", "M3"], "N": ["N1", "N2", "N3"], "O": ["O1", "O2", "O3", "O4"]}


@st.cache_data(ttl=3600)
def get_vias() -> list:
    try:
        r = requests.get(f"{BACKEND_URL}/vias", timeout=5)
        return r.json()
    except Exception:
        return []


def consultar(
    pregunta: str,
    categoria: str | None,
    via: str | None,
    historial: list[dict],
) -> dict:
    # Construir historial solo con role y content (sin "fuentes")
    historial_limpio = [
        {"role": m["role"], "content": m["content"]}
        for m in historial
        if m["role"] in ("user", "assistant")
    ]

    payload = {
        "pregunta":  pregunta,
        "historial": historial_limpio,
    }
    if categoria:
        payload["categoria"] = categoria
    if via:
        payload["via"] = via

    r = requests.post(f"{BACKEND_URL}/consulta", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def badge_via(via: str) -> str:
    colores = {"A": "🔴", "B": "🟡", "C": "🟢", "D": "🔵"}
    return f"{colores.get(via, '⚪')} Vía {via}"


# ─── Layout ───────────────────────────────────────────────────────────────────

st.title("🚗 Consulta de Reformas de Vehículos")
st.caption("Manual de Reformas DGT — Sección I · Reglamento (UE) 2018/858")

# Sidebar — filtros
with st.sidebar:
    st.header("Filtros opcionales")
    st.caption("Aplica filtros para acotar la búsqueda a un tipo de vehículo o vía de tramitación específica.")

    categorias = get_categorias()
    opciones_cat = ["Todas"] + [c for grupo in categorias.values() for c in grupo]
    cat_sel = st.selectbox("Categoría de vehículo", opciones_cat)
    categoria = None if cat_sel == "Todas" else cat_sel

    vias = get_vias()
    opciones_via = ["Todas"] + [v["via"] for v in vias]
    via_sel = st.selectbox("Vía de tramitación", opciones_via)
    via = None if via_sel == "Todas" else via_sel

    if vias:
        st.divider()
        st.caption("**Vías de tramitación:**")
        for v in vias:
            st.caption(f"{badge_via(v['via'])} {v['descripcion']}")

    st.divider()
    if st.button("🗑 Limpiar conversación"):
        st.session_state.mensajes = []
        st.rerun()

# Inicializar historial
if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

# Mostrar historial
for msg in st.session_state.mensajes:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("fuentes"):
            with st.expander(f"📄 Fuentes consultadas ({len(msg['fuentes'])} documentos)"):
                for f in msg["fuentes"]:
                    if f["tipo"] == "ficha_cr":
                        st.markdown(f"- **CR {f['cr']}** {badge_via(f['via']) if f.get('via') else ''}")
                    elif f["tipo"] == "preambulo":
                        st.markdown(f"- Preámbulo — {f.get('titulo', f.get('apartado', ''))}")
                    elif f["tipo"] == "reglamento_ue":
                        st.markdown(f"- Reglamento UE — {f.get('titulo', f.get('apartado', ''))}")

# Input
if pregunta := st.chat_input("¿Qué reforma quieres consultar?"):

    # Mostrar mensaje del usuario
    st.session_state.mensajes.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    # Llamar al backend
    with st.chat_message("assistant"):
        with st.spinner("Consultando documentos..."):
            try:
                resultado = consultar(pregunta, categoria, via, st.session_state.mensajes)
                respuesta = resultado["respuesta"]
                fuentes   = resultado["fuentes"]

                st.markdown(respuesta)

                if fuentes:
                    with st.expander(f"📄 Fuentes consultadas ({len(fuentes)} documentos)"):
                        for f in fuentes:
                            if f["tipo"] == "ficha_cr":
                                st.markdown(f"- **CR {f['cr']}** {badge_via(f['via']) if f.get('via') else ''}")
                            elif f["tipo"] == "preambulo":
                                st.markdown(f"- Preámbulo — {f.get('titulo', f.get('apartado', ''))}")
                            elif f["tipo"] == "reglamento_ue":
                                st.markdown(f"- Reglamento UE — {f.get('titulo', f.get('apartado', ''))}")

                st.session_state.mensajes.append({
                    "role":    "assistant",
                    "content": respuesta,
                    "fuentes": fuentes,
                })

            except requests.exceptions.ConnectionError:
                msg = "❌ No se puede conectar con el backend. ¿Está corriendo `uvicorn main:app` en el directorio `backend/`?"
                st.error(msg)
            except Exception as e:
                msg = f"❌ Error: {str(e)}"
                st.error(msg)
