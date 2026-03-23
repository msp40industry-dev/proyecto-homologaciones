"""
test_rag_chain.py — Tests de las funciones helper de la cadena RAG.

Solo se prueban funciones puras (sin llamadas a OpenAI ni ChromaDB).
Las funciones que requieren LLM se mockean donde es necesario.
"""

import pytest
from langchain_core.documents import Document

from rag.chain import (
    _filtrar_ars_por_categoria,
    _formatear_ficha,
    _construir_contexto,
    _extraer_fuentes,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

TEXTO_FICHA_CON_ARS = """CR 2.1: Modificación del motor
Denominación: Modificación del motor mediante sobrealimentación
Vía de tramitación: A
Documentación exigible: Proyecto Técnico, Certificado de Conformidad

Actos Reglamentarios aplicables:
- Frenos (UNECE R13): M1: (1), M2: (1), N1: (1), N2: (2), N3: x
- Dirección (UNECE R79): M1: (2), M2: (2), N1: x, N2: -, N3: -
- Emisiones (UNECE R83): M1: (1), M2: -, N1: (1), N2: -, N3: -
---
Información adicional: Revisar también CR 4.4 si se modifica el sistema de escape."""


@pytest.fixture
def doc_ficha_cr():
    return Document(
        page_content=TEXTO_FICHA_CON_ARS,
        metadata={"cr": "2.1", "via_tramitacion": "A", "pagina_inicio": 45},
    )


@pytest.fixture
def doc_preambulo():
    return Document(
        page_content="El Proyecto Técnico debe ser firmado por ingeniero colegiado.",
        metadata={"apartado": "proyecto_tecnico", "titulo": "Requisitos del Proyecto Técnico"},
    )


@pytest.fixture
def doc_reglamento():
    return Document(
        page_content="Los vehículos de categoría M1 son turismos con hasta 8 plazas.",
        metadata={"apartado": "art3", "titulo": "Artículo 3 — Definiciones"},
    )


# ── _filtrar_ars_por_categoria ────────────────────────────────────────────────

class TestFiltrarArsPorCategoria:

    def test_filtra_ars_de_categoria_m1(self):
        resultado = _filtrar_ars_por_categoria(TEXTO_FICHA_CON_ARS, "M1")
        assert "Actos Reglamentarios aplicables a M1" in resultado
        assert "Frenos" in resultado
        assert "Dirección" in resultado
        assert "Emisiones" in resultado

    def test_excluye_ars_con_x_o_guion(self):
        resultado = _filtrar_ars_por_categoria(TEXTO_FICHA_CON_ARS, "N3")
        # N3 tiene x en Frenos, - en Dirección y Emisiones → ninguno debe aparecer
        assert resultado == ""

    def test_filtra_correctamente_n1(self):
        resultado = _filtrar_ars_por_categoria(TEXTO_FICHA_CON_ARS, "N1")
        assert "Frenos" in resultado
        assert "Emisiones" in resultado
        # Dirección tiene x para N1 → no debe aparecer
        assert "Dirección" not in resultado

    def test_categoria_sin_ars_devuelve_vacio(self):
        texto_sin_ars = "CR 8.20: Elementos aerodinámicos\nVía: A\n---"
        resultado = _filtrar_ars_por_categoria(texto_sin_ars, "M1")
        assert resultado == ""

    def test_categoria_inexistente_devuelve_vacio(self):
        resultado = _filtrar_ars_por_categoria(TEXTO_FICHA_CON_ARS, "O4")
        assert resultado == ""


# ── _formatear_ficha ──────────────────────────────────────────────────────────

class TestFormatearFicha:

    def test_incluye_cabecera_con_cr_y_via(self, doc_ficha_cr):
        resultado = _formatear_ficha(doc_ficha_cr)
        assert "[CR 2.1 | Vía A]" in resultado

    def test_sin_categoria_mantiene_ars_originales(self, doc_ficha_cr):
        resultado = _formatear_ficha(doc_ficha_cr, categoria=None)
        assert "M1:" in resultado  # ARs completos sin filtrar

    def test_con_categoria_filtra_ars(self, doc_ficha_cr):
        resultado = _formatear_ficha(doc_ficha_cr, categoria="M1")
        assert "Actos Reglamentarios aplicables a M1" in resultado

    def test_metadata_faltante_usa_interrogacion(self):
        doc = Document(page_content="Texto de prueba.", metadata={})
        resultado = _formatear_ficha(doc)
        assert "[CR ? | Vía ?]" in resultado


# ── _construir_contexto ───────────────────────────────────────────────────────

class TestConstruirContexto:

    def test_sin_documentos_devuelve_mensaje(self):
        resultado = _construir_contexto({"fichas": [], "preambulo": [], "reglamento": []})
        assert resultado == "No se han encontrado documentos relevantes."

    def test_incluye_cabeceras_de_seccion(self, doc_ficha_cr, doc_preambulo, doc_reglamento):
        docs = {
            "fichas": [doc_ficha_cr],
            "preambulo": [doc_preambulo],
            "reglamento": [doc_reglamento],
        }
        resultado = _construir_contexto(docs)
        assert "=== FICHAS DE REFORMA ===" in resultado
        assert "=== PREÁMBULO DEL MANUAL ===" in resultado
        assert "=== REGLAMENTO (UE) 2018/858 ===" in resultado

    def test_solo_fichas(self, doc_ficha_cr):
        docs = {"fichas": [doc_ficha_cr], "preambulo": [], "reglamento": []}
        resultado = _construir_contexto(docs)
        assert "=== FICHAS DE REFORMA ===" in resultado
        assert "=== PREÁMBULO" not in resultado
        assert "=== REGLAMENTO" not in resultado


# ── _extraer_fuentes ──────────────────────────────────────────────────────────

class TestExtraerFuentes:

    def test_extrae_fuente_de_ficha_cr(self, doc_ficha_cr):
        docs = {"fichas": [doc_ficha_cr], "preambulo": [], "reglamento": []}
        fuentes = _extraer_fuentes(docs)
        assert len(fuentes) == 1
        assert fuentes[0]["tipo"] == "ficha_cr"
        assert fuentes[0]["cr"] == "2.1"
        assert fuentes[0]["via"] == "A"

    def test_extrae_fuente_de_preambulo(self, doc_preambulo):
        docs = {"fichas": [], "preambulo": [doc_preambulo], "reglamento": []}
        fuentes = _extraer_fuentes(docs)
        assert len(fuentes) == 1
        assert fuentes[0]["tipo"] == "preambulo"
        assert fuentes[0]["titulo"] == "Requisitos del Proyecto Técnico"

    def test_extrae_fuente_de_reglamento(self, doc_reglamento):
        docs = {"fichas": [], "preambulo": [], "reglamento": [doc_reglamento]}
        fuentes = _extraer_fuentes(docs)
        assert len(fuentes) == 1
        assert fuentes[0]["tipo"] == "reglamento_ue"
        assert fuentes[0]["titulo"] == "Artículo 3 — Definiciones"

    def test_sin_documentos_devuelve_lista_vacia(self):
        docs = {"fichas": [], "preambulo": [], "reglamento": []}
        fuentes = _extraer_fuentes(docs)
        assert fuentes == []

    def test_multiples_fuentes(self, doc_ficha_cr, doc_preambulo):
        docs = {"fichas": [doc_ficha_cr], "preambulo": [doc_preambulo], "reglamento": []}
        fuentes = _extraer_fuentes(docs)
        assert len(fuentes) == 2
        tipos = {f["tipo"] for f in fuentes}
        assert tipos == {"ficha_cr", "preambulo"}
