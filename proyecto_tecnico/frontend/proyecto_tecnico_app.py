"""
proyecto_tecnico_app.py — Interfaz Streamlit para el generador de proyectos técnicos Vía A.

Flujo de la interfaz:
  Paso 1: Formulario de entrada
  Paso 2: Generación (barra de progreso)
  Paso 3: Revisión sección por sección (tabs)
  Paso 4: Descarga del Word final
"""

import asyncio
import requests
import streamlit as st
from pathlib import Path
import sys

BACKEND_URL = "http://localhost:8000"

# Añadir raíz del proyecto al path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from proyecto_tecnico.models import (
    EntradaProyecto, DatosVehiculo, Componente, Taller, Ingeniero
)
from proyecto_tecnico.graph import grafo, crear_estado_inicial

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────

def _init_session():
    defaults = {
        "paso": 1,
        "estado_grafo": None,
        "config_grafo": None,
        "secciones": {},
        "revisiones": {},
        "docx_path": None,
        "error": None,
        "num_componentes": 1,
        "validacion_resultado": None,   # Resultado de /validar-crs
        "validacion_confirmada": False, # El usuario ha revisado y confirmado el resumen
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session()

# ─────────────────────────────────────────────
#  PASO 1 — FORMULARIO DE ENTRADA
# ─────────────────────────────────────────────

CATEGORIAS = {
    "M1 — Turismo / vehículo hasta 8 plazas": "M1",
    "N1 — Furgoneta / carga hasta 3,5t": "N1",
    "N2 — Camión 3,5t–12t": "N2",
    "N3 — Camión más de 12t": "N3",
    "M2 — Minibús": "M2",
    "M3 — Autobús": "M3",
    "O1/O2 — Remolque ligero": "O1",
    "O3/O4 — Semirremolque": "O3",
}

def _mostrar_resultado_validacion(val: dict):
    """
    Renderiza el resumen de validación de CRs y el botón de confirmación.
    val es el JSON devuelto por /proyecto-tecnico/validar-crs.
    """
    st.divider()
    st.subheader("📋 Resultado de la validación de CRs")

    # ── CRs incluidos en el proyecto ──────────
    if val["crs_incluidos"]:
        st.success(f"✅ **{len(val['crs_incluidos'])} CR(s) incluidos en el proyecto técnico (Vía A):**")
        for cr in val["crs_incluidos"]:
            etiqueta = " _(descubierto vía información adicional)_" if cr.get("es_adicional") else ""
            origen = f" — mencionado en CR {cr['cr_origen']}" if cr.get("cr_origen") else ""
            st.markdown(f"- **CR {cr['cr']}** (Vía {cr['via']}): {cr['descripcion']}{etiqueta}{origen}")

    # ── CRs excluidos ─────────────────────────
    if val["crs_excluidos"]:
        # Separar adicionales de los indicados directamente
        excluidos_directos = [c for c in val["crs_excluidos"] if not c.get("es_adicional")]
        excluidos_adicionales = [c for c in val["crs_excluidos"] if c.get("es_adicional")]

        if excluidos_directos:
            st.warning(f"⚠️ **{len(excluidos_directos)} CR(s) indicados que NO requieren Proyecto Técnico:**")
            for cr in excluidos_directos:
                st.markdown(f"- **CR {cr['cr']}** (Vía {cr['via']}): {cr['descripcion']}  \n  _{cr.get('motivo_exclusion', '')}_")

        if excluidos_adicionales:
            st.info(f"ℹ️ **{len(excluidos_adicionales)} CR(s) adicionales descubiertos que NO requieren Proyecto Técnico:**")
            for cr in excluidos_adicionales:
                st.markdown(
                    f"- **CR {cr['cr']}** (Vía {cr['via']}): {cr['descripcion']}  \n"
                    f"  _Mencionado en CR {cr.get('cr_origen', '?')} — {cr.get('motivo_exclusion', '')}_"
                )

    # ── CRs adicionales vía A descubiertos ────
    adicionales_via_a = [c for c in val.get("crs_adicionales", []) if c.get("incluido")]
    if adicionales_via_a:
        st.info(
            f"🔍 **Se han identificado {len(adicionales_via_a)} CR(s) adicionales vía A "
            f"a partir de la información adicional de las fichas:**"
        )
        for cr in adicionales_via_a:
            st.markdown(
                f"- **CR {cr['cr']}** (Vía A): {cr['descripcion']}  \n"
                f"  _Condición activada desde CR {cr.get('cr_origen', '?')}_"
            )

    # ── Botón de confirmación (solo si valido=True) ───
    if val["valido"] and not st.session_state.validacion_confirmada:
        st.divider()
        if val.get("crs_adicionales"):
            st.caption(
                "Revisa los CRs identificados arriba. "
                "Confirma para incluirlos en el proyecto técnico."
            )
        if st.button("✅ Confirmar y continuar con estos CRs", type="primary"):
            st.session_state.validacion_confirmada = True
            st.rerun()

    elif st.session_state.validacion_confirmada:
        st.success("✅ CRs confirmados. Pulsa **'Generar proyecto técnico'** para continuar.")

    st.divider()


def paso_formulario():
    st.header("Paso 1 — Datos del proyecto")

    col1, col2 = st.columns(2)

    # ── Datos del vehículo ────────────────────
    with col1:
        st.subheader("🚗 Vehículo")
        marca = st.text_input("Marca *", placeholder="Volkswagen")
        modelo = st.text_input("Modelo *", placeholder="Golf 2.0 TDI")
        bastidor = st.text_input("Número de bastidor (VIN) *", placeholder="WVWZZZ1KZAM123456", max_chars=17)
        matricula = st.text_input("Matrícula *", placeholder="1234 ABC")
        fecha_matriculacion = st.text_input("Fecha primera matriculación *", placeholder="15/03/2018")
        cat_label = st.selectbox("Categoría del vehículo *", list(CATEGORIAS.keys()))
        categoria = CATEGORIAS[cat_label]
        color = st.text_input("Color", placeholder="Blanco")
        kilometraje = st.text_input("Kilometraje", placeholder="85.000 km")

    # ── Ingeniero ─────────────────────────────
    with col2:
        st.subheader("👷 Ingeniero redactor")
        ing_nombre = st.text_input("Nombre *", placeholder="Juan")
        ing_apellidos = st.text_input("Apellidos *", placeholder="García Martínez")
        ing_titulacion = st.text_input("Titulación *", placeholder="Ingeniero Técnico Industrial")
        ing_colegiado = st.text_input("Nº colegiado *", placeholder="12345")
        ing_colegio = st.text_input("Colegio profesional *", placeholder="COGITI Madrid")
        ing_tel = st.text_input("Teléfono", placeholder="600 000 000")
        ing_email = st.text_input("Email", placeholder="juan.garcia@ingenieria.es")

    # ── Taller ────────────────────────────────
    st.subheader("🔧 Taller ejecutor")
    col3, col4 = st.columns(2)
    with col3:
        taller_nombre = st.text_input("Nombre del taller *", placeholder="Taller Mecánico López")
        taller_dir = st.text_input("Dirección *", placeholder="Calle Mayor, 10")
        taller_loc = st.text_input("Localidad *", placeholder="Madrid")
    with col4:
        taller_prov = st.text_input("Provincia *", placeholder="Madrid")
        taller_tel = st.text_input("Teléfono taller", placeholder="91 000 00 00")
        taller_aut = st.text_input("Nº autorización taller", placeholder="M-1234")

    # ── Reforma ───────────────────────────────
    st.subheader("⚙️ Descripción de la reforma")
    descripcion = st.text_area(
        "Describe detalladamente las reformas realizadas *",
        placeholder=(
            "Ej: Se ha realizado la instalación de un turbocompresor en el motor 1.6 TDI "
            "originalmente atmosférico, incluyendo la modificación del sistema de admisión "
            "y escape. Se ha instalado una centralita de gestión motor de mayor capacidad "
            "para adaptarse a la nueva configuración..."
        ),
        height=150,
    )

    # ── CRs ───────────────────────────────────
    st.info(
        "💡 ¿No sabes qué Códigos de Reforma aplican a tu reforma? "
        "Consulta primero el **[Asistente RAG](http://localhost:8501)** para identificarlos.",
        icon="🔍",
    )
    crs_texto = st.text_input(
        "CRs identificados (opcional)",
        placeholder="2.1, 8.20 — déjalo vacío si no los conoces",
        help=(
            "Introduce los códigos separados por coma. "
            "El sistema validará su vía de tramitación antes de generar el proyecto. "
            "Si los dejas vacíos, el sistema los identificará automáticamente."
        ),
    )
    crs_indicados = [cr.strip() for cr in crs_texto.split(",") if cr.strip()] if crs_texto else []

    # Reset validación si el usuario cambia los CRs o la descripción
    if (
        st.session_state.get("_crs_previos") != crs_texto
        or st.session_state.get("_desc_previa") != descripcion
    ):
        st.session_state.validacion_resultado = None
        st.session_state.validacion_confirmada = False
        st.session_state["_crs_previos"] = crs_texto
        st.session_state["_desc_previa"] = descripcion

    # ── Componentes ───────────────────────────
    st.subheader("🔩 Componentes instalados")
    num_comp = st.number_input("Número de componentes", min_value=0, max_value=20, value=st.session_state.num_componentes, step=1)
    st.session_state.num_componentes = num_comp

    componentes = []
    for i in range(int(num_comp)):
        with st.expander(f"Componente {i+1}", expanded=(i == 0)):
            cc1, cc2 = st.columns(2)
            with cc1:
                desc_c = st.text_input(f"Descripción *", key=f"comp_desc_{i}", placeholder="Turbocompresor")
                marca_c = st.text_input("Marca", key=f"comp_marca_{i}", placeholder="Garrett")
                modelo_c = st.text_input("Modelo", key=f"comp_modelo_{i}", placeholder="GT1749V")
            with cc2:
                ref_c = st.text_input("Referencia técnica", key=f"comp_ref_{i}", placeholder="700447-5008S")
                hom_c = st.text_input("Nº homologación", key=f"comp_hom_{i}", placeholder="e1*11R-01...")
            if desc_c:
                componentes.append(Componente(
                    descripcion=desc_c, marca=marca_c or None,
                    modelo=modelo_c or None, referencia=ref_c or None,
                    numero_homologacion=hom_c or None,
                ))

    # ── Datos del expediente ──────────────────
    st.subheader("📁 Datos del expediente")
    col5, col6 = st.columns(2)
    with col5:
        num_expediente = st.text_input("Nº expediente", placeholder="EXP-2026-001")
    with col6:
        fecha_proyecto = st.text_input("Fecha del proyecto", placeholder="11/03/2026")

    # ── Validación y generación ───────────────
    st.divider()
    campos_ok = all([marca, modelo, bastidor, matricula, fecha_matriculacion,
                     ing_nombre, ing_apellidos, ing_titulacion, ing_colegiado, ing_colegio,
                     taller_nombre, taller_dir, taller_loc, taller_prov, descripcion])

    if not campos_ok:
        st.info("Rellena todos los campos obligatorios (*) para continuar.")

    # ── Paso A: Validar CRs ───────────────────
    # Solo si hay CRs indicados y aún no se ha validado
    if campos_ok and crs_indicados and not st.session_state.validacion_resultado:
        if st.button("🔍 Validar CRs antes de generar", type="secondary"):
            with st.spinner("Consultando el Manual de Reformas DGT..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/proyecto-tecnico/validar-crs",
                        json={
                            "crs": crs_indicados,
                            "descripcion": descripcion,
                            "categoria": categoria,
                        },
                        timeout=60,
                    )
                    resp.raise_for_status()
                    st.session_state.validacion_resultado = resp.json()
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("❌ No se puede conectar con el backend (http://localhost:8000). ¿Está arrancado el servidor?")
                except Exception as e:
                    st.error(f"❌ Error en la validación: {e}")

    # ── Mostrar resultado de validación ──────
    val = st.session_state.validacion_resultado
    if val:
        _mostrar_resultado_validacion(val)

    # ── Paso B: Botón de generación ───────────
    # Se muestra si: no hay CRs (el sistema los identifica) O la validación pasó y el usuario confirmó
    puede_generar = campos_ok and (
        not crs_indicados                                          # sin CRs → identificación automática
        or (val and val["valido"] and st.session_state.validacion_confirmada)  # validación confirmada
    )

    # Bloqueo si la validación devuelve valido=False
    if val and not val["valido"]:
        st.error(val.get("mensaje_bloqueo", "No se puede generar el proyecto técnico con los CRs indicados."))
        if val.get("documentacion_requerida"):
            st.markdown("**Documentación requerida en su lugar:**")
            for k, v in val["documentacion_requerida"].items():
                st.markdown(f"- **{k}**: {v}")
        return  # Bloquear completamente

    if puede_generar:
        if st.button("🚀 Generar proyecto técnico", type="primary"):
            # Si había validación, usar los CRs validados (solo los incluidos)
            crs_finales = crs_indicados
            if val and val["valido"]:
                crs_finales = [c["cr"] for c in val["crs_incluidos"]]

            entrada = EntradaProyecto(
                vehiculo=DatosVehiculo(
                    marca=marca, modelo=modelo, bastidor=bastidor,
                    matricula=matricula, fecha_matriculacion=fecha_matriculacion,
                    categoria=categoria, color=color or None, kilometraje=kilometraje or None,
                ),
                descripcion_reforma=descripcion,
                crs_indicados=crs_finales,
                componentes=componentes,
                taller=Taller(
                    nombre=taller_nombre, direccion=taller_dir,
                    localidad=taller_loc, provincia=taller_prov,
                    telefono=taller_tel or None, numero_autorizacion=taller_aut or None,
                ),
                ingeniero=Ingeniero(
                    nombre=ing_nombre, apellidos=ing_apellidos,
                    titulacion=ing_titulacion, numero_colegiado=ing_colegiado,
                    colegio_profesional=ing_colegio,
                    telefono=ing_tel or None, email=ing_email or None,
                ),
                numero_expediente=num_expediente or None,
                fecha_proyecto=fecha_proyecto or None,
            )

            st.session_state.entrada = entrada
            st.session_state.paso = 2
            st.rerun()
    elif campos_ok and crs_indicados and not val:
        # Hay CRs pero aún no se ha validado
        st.info("Pulsa **'Validar CRs'** para verificar la tramitación antes de generar el proyecto.")


# ─────────────────────────────────────────────
#  PASO 2 — GENERACIÓN
# ─────────────────────────────────────────────

def paso_generacion():
    st.header("Paso 2 — Generando el proyecto técnico...")

    barra = st.progress(0, text="Iniciando...")
    estado_txt = st.empty()

    async def generar():
        entrada = st.session_state.entrada
        estado_inicial = crear_estado_inicial(entrada)
        config = {"configurable": {"thread_id": estado_inicial["proyecto_id"]}}
        st.session_state.config_grafo = config
        st.session_state.estado_grafo = estado_inicial

        barra.progress(10, text="🔍 Identificando CRs aplicables en la base de datos...")
        estado_txt.info("El sistema consulta el Manual de Reformas DGT para identificar los Códigos de Reforma.")

        # Ejecutar el grafo hasta el punto de interrupción (revision_humana)
        resultado = None
        async for chunk in grafo.astream(estado_inicial, config=config):
            node_name = list(chunk.keys())[0]
            if node_name == "identificador_cr":
                barra.progress(30, text="✅ CRs identificados. Redactando secciones...")
                estado_txt.info("Redactando memoria, pliego de condiciones y conclusiones en paralelo...")
            elif node_name in ("redactor_memoria", "redactor_pliego", "redactor_conclusiones"):
                barra.progress(70, text=f"✍️ Redactando {node_name.replace('_', ' ')}...")
            resultado = chunk

        barra.progress(100, text="✅ Proyecto generado. Revisión pendiente.")

        # Recuperar el estado final del grafo
        estado_final = grafo.get_state(config)
        st.session_state.estado_grafo = estado_final.values
        st.session_state.secciones = estado_final.values.get("secciones", {})
        st.session_state.paso = 3

    asyncio.run(generar())
    st.rerun()


# ─────────────────────────────────────────────
#  PASO 3 — REVISIÓN
# ─────────────────────────────────────────────

# Orden y configuración de las secciones en la interfaz
SECCIONES_CONFIG = {
    "peticionario":           {"titulo": "0. Peticionario",                    "adjunto": False},
    "objeto":                 {"titulo": "1.1 Objeto",                         "adjunto": False},
    "antecedentes":           {"titulo": "1.2 Antecedentes",                   "adjunto": False},
    "identificacion_vehiculo":{"titulo": "1.3.1 Identificación del vehículo",  "adjunto": False},
    "descripcion_reforma":    {"titulo": "1.4 Descripción de la reforma",       "adjunto": False},
    "calidad_materiales":     {"titulo": "3.1 Calidad de materiales",           "adjunto": False},
    "normas_ejecucion":       {"titulo": "3.2 Normas de ejecución",             "adjunto": False},
    "certificados":           {"titulo": "3.3 Certificados y autorizaciones",   "adjunto": False},
    "taller_ejecutor":        {"titulo": "3.4 Taller ejecutor",                 "adjunto": False},
    "conclusiones":           {"titulo": "8. Conclusiones",                     "adjunto": False},
    # Secciones con adjunto (las gestiona el ingeniero)
    "__calculos":             {"titulo": "2. Cálculos justificativos",          "adjunto": True,  "solo_adjunto": True},
    "__presupuesto":          {"titulo": "4. Presupuesto",                      "adjunto": True,  "solo_adjunto": True},
    "__planos":               {"titulo": "5. Planos",                           "adjunto": True,  "solo_adjunto": True},
    "__fotografias":          {"titulo": "6. Reportaje fotográfico",            "adjunto": True,  "solo_adjunto": True},
    "__documentacion":        {"titulo": "7. Documentación del vehículo",       "adjunto": True,  "solo_adjunto": True},
}

ESTADOS_ICONOS = {
    "pendiente":   "⏳",
    "aprobado":    "✅",
    "reescribir":  "✏️",
}


def paso_revision():
    st.header("Paso 3 — Revisión del proyecto técnico")

    secciones = st.session_state.secciones
    revisiones = st.session_state.revisiones

    if not secciones:
        st.error("No hay secciones generadas. Vuelve al paso 1.")
        return

    # ── Resumen de estado ──────────────────────
    total = len([k for k in SECCIONES_CONFIG if not k.startswith("__")])
    aprobadas = sum(1 for sid in secciones if revisiones.get(sid, {}).get("estado") == "aprobado")
    st.progress(aprobadas / total if total > 0 else 0, text=f"{aprobadas}/{total} secciones aprobadas")

    # ── Tabs por sección ───────────────────────
    ids_orden = [k for k in SECCIONES_CONFIG.keys()]
    nombres_tabs = []
    for sid in ids_orden:
        cfg = SECCIONES_CONFIG[sid]
        if sid.startswith("__"):
            nombres_tabs.append(f"📎 {cfg['titulo'][:20]}...")
        else:
            rev = revisiones.get(sid, {})
            icono = ESTADOS_ICONOS.get(rev.get("estado", "pendiente"), "⏳")
            nombres_tabs.append(f"{icono} {cfg['titulo'][:18]}...")

    tabs = st.tabs(nombres_tabs)

    for i, (sid, cfg) in enumerate(SECCIONES_CONFIG.items()):
        with tabs[i]:
            _render_tab_seccion(sid, cfg, secciones, revisiones)

    # ── Botones de acción ─────────────────────
    st.divider()
    cola, colb, colc = st.columns([2, 2, 1])

    todas_revisadas = all(
        revisiones.get(sid, {}).get("estado") in ("aprobado", "reescribir")
        for sid in secciones
    )
    hay_reescrituras = any(
        revisiones.get(sid, {}).get("estado") == "reescribir"
        for sid in secciones
    )

    with cola:
        if hay_reescrituras:
            if st.button("🔄 Regenerar secciones marcadas", type="primary"):
                _aplicar_revisiones_y_regenerar()
        elif todas_revisadas:
            if st.button("📄 Generar documento Word", type="primary"):
                st.session_state.paso = 4
                _generar_documento()
                st.rerun()

    with colb:
        if not todas_revisadas:
            if st.button("✅ Aprobar todas las secciones pendientes"):
                for sid in secciones:
                    if revisiones.get(sid, {}).get("estado") not in ("aprobado", "reescribir"):
                        st.session_state.revisiones[sid] = {"estado": "aprobado"}
                st.rerun()

    with colc:
        if st.button("↩️ Volver al paso 1"):
            for k in ["paso", "estado_grafo", "config_grafo", "secciones", "revisiones", "docx_path", "error"]:
                st.session_state[k] = [1, None, None, {}, {}, None, None][
                    ["paso", "estado_grafo", "config_grafo", "secciones", "revisiones", "docx_path", "error"].index(k)
                ]
            st.session_state.paso = 1
            st.rerun()


def _render_tab_seccion(sid: str, cfg: dict, secciones: dict, revisiones: dict):
    """Renderiza el contenido de una tab de sección."""

    # Secciones de adjunto puro (sin texto generado)
    if cfg.get("solo_adjunto"):
        st.subheader(cfg["titulo"])
        st.caption("Esta sección debe ser completada por el ingeniero.")
        archivo = st.file_uploader(
            f"Subir fichero para: {cfg['titulo']}",
            key=f"upload_{sid}",
            type=["pdf", "jpg", "jpeg", "png", "dwg", "xlsx"],
        )
        if archivo:
            # Guardar en session_state para el ensamblador
            if "adjuntos" not in st.session_state:
                st.session_state.adjuntos = {}
            st.session_state.adjuntos[sid] = {
                "bytes": archivo.read(),
                "nombre": archivo.name,
            }
            st.success(f"✅ Fichero adjuntado: {archivo.name}")
        return

    # Sección con texto generado
    if sid not in secciones:
        st.info("Esta sección no está disponible.")
        return

    sec = secciones[sid]
    rev = revisiones.get(sid, {"estado": "pendiente"})
    estado = rev.get("estado", "pendiente")

    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader(cfg["titulo"])
        if sec.revision.iteraciones > 0:
            st.caption(f"Versión {sec.revision.iteraciones + 1} (regenerada)")
    with col2:
        st.metric("Estado", ESTADOS_ICONOS.get(estado, "⏳") + " " + estado.capitalize())

    # Texto generado
    st.text_area(
        "Texto generado",
        value=sec.contenido,
        height=350,
        key=f"texto_{sid}",
        disabled=True,
    )

    # Botones de revisión
    st.caption("¿Es correcto el texto generado?")
    bc1, bc2 = st.columns(2)

    with bc1:
        if st.button("✅ Aprobar", key=f"aprobar_{sid}", type="primary" if estado == "pendiente" else "secondary"):
            st.session_state.revisiones[sid] = {"estado": "aprobado"}
            st.rerun()

    with bc2:
        if st.button("✏️ Solicitar reescritura", key=f"reescribir_{sid}"):
            st.session_state[f"mostrar_motivo_{sid}"] = True
            st.rerun()

    # Campo de motivo de reescritura
    if st.session_state.get(f"mostrar_motivo_{sid}") or estado == "reescribir":
        motivo = st.text_area(
            "Indica el motivo o qué debe corregirse:",
            value=rev.get("motivo", ""),
            key=f"motivo_{sid}",
            placeholder="Ej: El CR indicado no es correcto, en realidad es el CR 2.2...",
            height=100,
        )
        if st.button("Confirmar reescritura", key=f"confirmar_reescritura_{sid}"):
            if motivo.strip():
                st.session_state.revisiones[sid] = {"estado": "reescribir", "motivo": motivo}
                st.session_state[f"mostrar_motivo_{sid}"] = False
                st.success("Marcado para reescritura. Pulsa 'Regenerar secciones marcadas' cuando termines.")
                st.rerun()
            else:
                st.warning("Indica el motivo antes de confirmar.")

    # Adjunto opcional (si la sección lo permite)
    if cfg.get("adjunto"):
        st.divider()
        archivo = st.file_uploader(
            "Adjuntar fichero complementario",
            key=f"upload_opt_{sid}",
            type=["pdf", "jpg", "jpeg", "png"],
        )
        if archivo:
            sec.adjunto_bytes = archivo.read()
            sec.adjunto_nombre = archivo.name
            st.success(f"Fichero adjuntado: {archivo.name}")


def _aplicar_revisiones_y_regenerar():
    """Aplica las revisiones al estado del grafo y reanuda la ejecución."""
    import asyncio

    revisiones = st.session_state.revisiones
    secciones = st.session_state.secciones
    config = st.session_state.config_grafo

    # Actualizar el estado del grafo con las revisiones del ingeniero
    revisiones_para_grafo = {}
    for sid, rev in revisiones.items():
        revisiones_para_grafo[sid] = {
            "estado": rev["estado"],
            "motivo": rev.get("motivo"),
        }

    async def regenerar():
        # Determinar qué secciones necesitan regenerarse
        sids_a_regenerar = [
            sid for sid, rev in revisiones.items()
            if rev["estado"] == "reescribir"
        ]

        # Actualizar estado del grafo: secciones con revisiones + lista de regeneración
        grafo.update_state(
            config,
            {
                "secciones": {sid: sec for sid, sec in secciones.items()},
                "secciones_a_regenerar": sids_a_regenerar,
            },
            as_node="revision_humana",
        )

        # Reanudar el grafo (None para continuar desde el punto de interrupción)
        async for chunk in grafo.astream(
            None,
            config=config,
        ):
            pass

        # Recuperar el nuevo estado
        estado_nuevo = grafo.get_state(config)
        st.session_state.secciones = estado_nuevo.values.get("secciones", {})
        # Limpiar estados de reescritura procesados
        for sid in list(revisiones.keys()):
            if revisiones[sid]["estado"] == "reescribir":
                st.session_state.revisiones[sid] = {"estado": "pendiente"}

    asyncio.run(regenerar())
    st.rerun()


# ─────────────────────────────────────────────
#  PASO 4 — DESCARGA DEL DOCUMENTO
# ─────────────────────────────────────────────

def _generar_documento():
    import asyncio
    from proyecto_tecnico.agents.ensamblador import ensamblar_documento

    estado = st.session_state.estado_grafo
    if not estado:
        st.session_state.error = "No hay estado del proyecto disponible."
        return

    async def ensamblar():
        path = await ensamblar_documento(
            proyecto_id=estado["proyecto_id"],
            entrada=estado["entrada"],
            secciones=st.session_state.secciones,
            crs=estado["crs_identificados"],
            ars=estado["ars_filtrados"],
            adjuntos=st.session_state.get("adjuntos", {}),
        )
        st.session_state.docx_path = path

    asyncio.run(ensamblar())


def paso_descarga():
    st.header("Paso 4 — Proyecto técnico generado ✅")

    if st.session_state.error:
        st.error(f"Error: {st.session_state.error}")
        return

    if not st.session_state.docx_path:
        st.warning("Generando documento...")
        _generar_documento()
        st.rerun()
        return

    docx_path = Path(st.session_state.docx_path)
    if docx_path.exists():
        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        v = st.session_state.estado_grafo["entrada"].vehiculo
        nombre_fichero = f"ProyectoTecnico_{v.marca}_{v.modelo}_{v.bastidor[:8]}.docx".replace(" ", "_")

        st.success("El documento Word ha sido generado correctamente.")
        st.info(
            "El documento incluye:\n"
            "- Portada con datos del proyecto\n"
            "- Índice automático\n"
            "- Todas las secciones revisadas y aprobadas\n"
            "- Tablas de CRs y Actos Reglamentarios\n"
            "- Marcadores **[COMPLETAR]** en rojo para las secciones del ingeniero\n"
            "- Cabecera y pie de página con paginación"
        )

        st.download_button(
            label="⬇️ Descargar proyecto técnico (.docx)",
            data=docx_bytes,
            file_name=nombre_fichero,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )
    else:
        st.error("No se encontró el fichero generado.")

    if st.button("🔁 Generar otro proyecto"):
        for k in ["paso", "estado_grafo", "config_grafo", "secciones", "revisiones", "docx_path", "error", "entrada"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()


# ─────────────────────────────────────────────
#  PUNTO DE ENTRADA (modo embebido o standalone)
# ─────────────────────────────────────────────

def render():
    """Renderiza la app del generador de proyectos técnicos.
    Llamar desde el hub principal (frontend/app.py) o directamente."""

    st.title("📋 Generador de Proyectos Técnicos — Vía A")
    st.caption("Sistema de redacción asistida por IA para reformas de vehículos (Manual DGT Sección I)")

    _init_session()

    with st.sidebar:
        st.header("Progreso")
        pasos = ["Datos del proyecto", "Generación", "Revisión", "Documento final"]
        for i, nombre in enumerate(pasos, 1):
            icono = "✅" if i < st.session_state.paso else ("🔵" if i == st.session_state.paso else "⚪")
            st.markdown(f"{icono} **Paso {i}:** {nombre}")

        st.divider()
        st.caption("Sistema RAG — Manual de Reformas DGT")
        st.caption("Reglamento (UE) 2018/858")

    paso = st.session_state.paso
    if paso == 1:
        paso_formulario()
    elif paso == 2:
        paso_generacion()
    elif paso == 3:
        paso_revision()
    elif paso == 4:
        paso_descarga()


if __name__ == "__main__":
    st.set_page_config(
        page_title="Generador de Proyectos Técnicos",
        page_icon="📋",
        layout="wide",
    )
    render()
