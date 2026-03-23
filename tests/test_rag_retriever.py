"""
test_rag_retriever.py — Tests de las funciones puras del retriever RAG.

Se prueban únicamente las funciones que no dependen de ChromaDB ni OpenAI:
  - _necesita_preambulo
  - _necesita_reglamento
  - _filtro_fichas
"""

import pytest
from langchain_core.documents import Document

from rag.retriever import (
    _necesita_preambulo,
    _necesita_reglamento,
    _filtro_fichas,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ficha_via_a():
    return Document(
        page_content="CR 2.1: Modificación del motor",
        metadata={"cr": "2.1", "via_tramitacion": "A"},
    )


@pytest.fixture
def ficha_via_c():
    return Document(
        page_content="CR 8.1: Cambio de color",
        metadata={"cr": "8.1", "via_tramitacion": "C"},
    )


@pytest.fixture
def ficha_sin_via():
    return Document(
        page_content="CR 3.5: Reforma genérica",
        metadata={"cr": "3.5"},
    )


# ── _necesita_preambulo ───────────────────────────────────────────────────────

class TestNecesitaPreambulo:

    def test_keyword_proyecto_tecnico_activa_preambulo(self, ficha_sin_via):
        assert _necesita_preambulo("¿qué es un proyecto técnico?", [ficha_sin_via]) is True

    def test_keyword_documentacion_activa_preambulo(self, ficha_sin_via):
        assert _necesita_preambulo("qué documentación necesito para tramitar", [ficha_sin_via]) is True

    def test_keyword_cfo_activa_preambulo(self, ficha_sin_via):
        assert _necesita_preambulo("¿necesito un CFO?", [ficha_sin_via]) is True

    def test_ficha_via_a_activa_preambulo(self, ficha_via_a):
        assert _necesita_preambulo("instalación de turbo", [ficha_via_a]) is True

    def test_ficha_via_b_activa_preambulo(self):
        ficha_b = Document(
            page_content="CR X.X",
            metadata={"via_tramitacion": "B"},
        )
        assert _necesita_preambulo("modificación de frenos", [ficha_b]) is True

    def test_ficha_via_c_no_activa_preambulo_sin_keyword(self, ficha_via_c):
        assert _necesita_preambulo("instalación de sistema de audio", [ficha_via_c]) is False

    def test_sin_fichas_y_sin_keyword_no_activa(self):
        assert _necesita_preambulo("instalación de llanta de aleación", []) is False

    def test_lista_vacia_y_sin_keyword(self):
        # "pintar" no contiene ninguna keyword de KEYWORDS_PREAMBULO como subcadena
        assert _necesita_preambulo("pintar la carrocería de azul", []) is False

    def test_keyword_ic_activa_preambulo(self):
        assert _necesita_preambulo("¿qué es el IC?", []) is True

    def test_keyword_certificado_taller_activa_preambulo(self):
        assert _necesita_preambulo("¿necesito certificado de taller?", []) is True

    def test_keyword_como_tramita_activa_preambulo(self):
        assert _necesita_preambulo("cómo se tramita la reforma", []) is True


# ── _necesita_reglamento ──────────────────────────────────────────────────────

class TestNecesitaReglamento:

    def test_categoria_m1_activa_reglamento(self):
        assert _necesita_reglamento("vehículo de categoría m1") is True

    def test_categoria_n1_activa_reglamento(self):
        assert _necesita_reglamento("¿aplica para n1?") is True

    def test_categoria_o4_activa_reglamento(self):
        assert _necesita_reglamento("es un remolque o4") is True

    def test_palabra_turismo_activa_reglamento(self):
        assert _necesita_reglamento("es un turismo de 5 plazas") is True

    def test_palabra_furgoneta_activa_reglamento(self):
        assert _necesita_reglamento("la furgoneta tiene MMA superior a 3.5t") is True

    def test_palabra_categoria_activa_reglamento(self):
        assert _necesita_reglamento("¿qué categoría es un camión?") is True

    def test_query_sin_categoria_no_activa(self):
        assert _necesita_reglamento("instalar un turbocompresor en el motor") is False

    def test_query_generica_no_activa(self):
        assert _necesita_reglamento("¿qué documentos necesito?") is False

    def test_case_insensitive(self):
        assert _necesita_reglamento("¿Cuáles son los vehículos M2?") is True


# ── _filtro_fichas ────────────────────────────────────────────────────────────

class TestFiltroFichas:

    def test_via_a_devuelve_filtro(self):
        filtro = _filtro_fichas(categoria=None, via="A")
        assert filtro == {"via_tramitacion": "A"}

    def test_via_minuscula_se_convierte_a_mayuscula(self):
        filtro = _filtro_fichas(categoria=None, via="b")
        assert filtro == {"via_tramitacion": "B"}

    def test_sin_via_devuelve_none(self):
        assert _filtro_fichas(categoria=None, via=None) is None

    def test_solo_categoria_devuelve_none(self):
        # La categoría no aplica como filtro de metadatos en fichas
        assert _filtro_fichas(categoria="M1", via=None) is None

    def test_categoria_y_via_usa_via(self):
        filtro = _filtro_fichas(categoria="M1", via="C")
        assert filtro == {"via_tramitacion": "C"}
