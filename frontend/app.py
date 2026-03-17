"""
Frontend Streamlit — Hub principal
Menú central para elegir entre el asistente RAG y el generador de proyectos técnicos.
"""

import sys
from pathlib import Path

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKEND_URL = "http://localhost:8000"

# ─── Config ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Sistema de Reformas de Vehículos",
    page_icon="🚗",
    layout="wide",
)

# ─── Estado de navegación ─────────────────────────────────────────────────────

if "modo" not in st.session_state:
    st.session_state.modo = None

# ─── Menú central ─────────────────────────────────────────────────────────────

if st.session_state.modo is None:
    st.markdown("<br><br>", unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("🚗 Sistema de Reformas de Vehículos")
        st.caption("Manual de Reformas DGT · Reglamento (UE) 2018/858")
        st.markdown("---")
        st.subheader("¿Qué quieres hacer?")
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(
            "💬  Asistente RAG — Consulta el manual de reformas",
            use_container_width=True,
            type="primary",
        ):
            st.session_state.modo = "chatbot"
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(
            "📋  Generador de Proyectos Técnicos (Vía A)",
            use_container_width=True,
            type="primary",
        ):
            st.session_state.modo = "generador"
            st.rerun()

    st.stop()

# ─── Botón de volver en sidebar ───────────────────────────────────────────────

with st.sidebar:
    if st.button("← Volver al menú principal"):
        st.session_state.modo = None
        st.rerun()
    st.divider()

# ─── Modo: Asistente RAG ──────────────────────────────────────────────────────

if st.session_state.modo == "chatbot":

    # Helpers
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

    def consultar(pregunta, categoria, via, historial):
        historial_limpio = [
            {"role": m["role"], "content": m["content"]}
            for m in historial
            if m["role"] in ("user", "assistant")
        ]
        payload = {"pregunta": pregunta, "historial": historial_limpio}
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

    # Layout
    st.title("💬 Asistente RAG — Reformas de Vehículos")
    st.caption("Manual de Reformas DGT — Sección I · Reglamento (UE) 2018/858")

    with st.sidebar:
        st.header("Filtros opcionales")
        st.caption("Aplica filtros para acotar la búsqueda.")

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

    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

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

    if pregunta := st.chat_input("¿Qué reforma quieres consultar?"):
        st.session_state.mensajes.append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)

        with st.chat_message("assistant"):
            with st.spinner("Consultando documentos..."):
                try:
                    resultado = consultar(pregunta, categoria, via, st.session_state.mensajes)
                    respuesta = resultado["respuesta"]
                    fuentes = resultado["fuentes"]

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
                        "role": "assistant",
                        "content": respuesta,
                        "fuentes": fuentes,
                    })

                except requests.exceptions.ConnectionError:
                    st.error("❌ No se puede conectar con el backend. ¿Está corriendo `uvicorn backend.main:app`?")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

# ─── Modo: Generador de proyectos técnicos ────────────────────────────────────

elif st.session_state.modo == "generador":
    from proyecto_tecnico.frontend.proyecto_tecnico_app import render as render_generador
    render_generador()
