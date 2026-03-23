"""
test_identificador_cr.py — Tests de las funciones helper del identificador de CRs.

Solo se prueban funciones puras que no requieren ChromaDB ni LLM:
  - _deduplicar_docs
  - _extraer_denominacion
  - _extraer_via
  - _extraer_documentacion
  - _extraer_ars_raw
"""

from langchain_core.documents import Document

from proyecto_tecnico.agents.identificador_cr import (
    _deduplicar_docs,
    _extraer_denominacion,
    _extraer_via,
    _extraer_documentacion,
    _extraer_ars_raw,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

TEXTO_FICHA_COMPLETA = """CR 2.1: Modificación del motor
Denominación: Modificación del motor mediante sobrealimentación
Vía de tramitación: A
Documentación exigible:
- Proyecto Técnico
- Certificado de Conformidad

Actos Reglamentarios aplicables:
- Frenos (UNECE R13): M1: (1), M2: (1), N1: (1), N2: (2), N3: x
- Dirección (UNECE R79): M1: (2), M2: (2), N1: x, N2: -, N3: -
- Emisiones (UNECE R83): M1: (1), M2: -, N1: (1), N2: -, N3: -
---
Información adicional: Revisar también CR 4.4 si se modifica el sistema de escape."""

TEXTO_SIN_DENOMINACION = """CR 8.20: Alerón deportivo
Vía: A
---"""

TEXTO_SIN_VIA = """CR 5.1: Reforma X
Denominación: Algo
---"""

TEXTO_SIN_ARS = """CR 8.1: Cambio de color
Denominación: Cambio de color de la carrocería
Vía de tramitación: C
Documentación exigible:
- Certificado de Taller
---"""

TEXTO_SIN_DOCUMENTACION = """CR 2.1: Reforma test
Denominación: Test
Vía: B

Actos Reglamentarios aplicables:
- Motor (UNECE R85): M1: (1)
---"""


# ── _deduplicar_docs ──────────────────────────────────────────────────────────

class TestDeduplicarDocs:

    def test_elimina_duplicados_por_contenido(self):
        doc1 = Document(page_content="Texto de prueba para deduplicar", metadata={"cr": "2.1"})
        doc2 = Document(page_content="Texto de prueba para deduplicar", metadata={"cr": "2.1"})
        resultado = _deduplicar_docs([doc1, doc2])
        assert len(resultado) == 1

    def test_conserva_docs_distintos(self):
        doc1 = Document(page_content="Primer documento sobre CR 2.1 con suficiente texto", metadata={})
        doc2 = Document(page_content="Segundo documento sobre CR 4.4 con suficiente texto", metadata={})
        resultado = _deduplicar_docs([doc1, doc2])
        assert len(resultado) == 2

    def test_lista_vacia(self):
        assert _deduplicar_docs([]) == []

    def test_un_solo_doc(self):
        doc = Document(page_content="Solo un documento", metadata={})
        resultado = _deduplicar_docs([doc])
        assert len(resultado) == 1

    def test_deduplicacion_basada_en_primeros_100_chars(self):
        prefijo = "A" * 100
        doc1 = Document(page_content=prefijo + "texto extra 1", metadata={})
        doc2 = Document(page_content=prefijo + "texto extra 2 distinto", metadata={})
        # Mismo prefijo de 100 chars → se consideran duplicados
        resultado = _deduplicar_docs([doc1, doc2])
        assert len(resultado) == 1

    def test_preserva_orden_original(self):
        doc_a = Document(page_content="Documento A con contenido único A", metadata={})
        doc_b = Document(page_content="Documento B con contenido único B", metadata={})
        doc_c = Document(page_content="Documento C con contenido único C", metadata={})
        resultado = _deduplicar_docs([doc_a, doc_b, doc_c])
        assert resultado[0].page_content == doc_a.page_content
        assert resultado[2].page_content == doc_c.page_content


# ── _extraer_denominacion ─────────────────────────────────────────────────────

class TestExtraerDenominacion:

    def test_extrae_denominacion_correctamente(self):
        resultado = _extraer_denominacion(TEXTO_FICHA_COMPLETA, "2.1")
        assert resultado == "Modificación del motor mediante sobrealimentación"

    def test_fallback_cuando_no_hay_denominacion(self):
        resultado = _extraer_denominacion(TEXTO_SIN_DENOMINACION, "8.20")
        assert resultado == "Reforma 8.20"

    def test_texto_vacio_usa_fallback(self):
        resultado = _extraer_denominacion("", "5.1")
        assert resultado == "Reforma 5.1"

    def test_denominacion_con_espacios_en_blanco_limpiados(self):
        texto = "CR 3.1: Algo\nDenominación:   Suspensión modificada   \n"
        resultado = _extraer_denominacion(texto, "3.1")
        assert resultado == "Suspensión modificada"


# ── _extraer_via ──────────────────────────────────────────────────────────────

class TestExtraerVia:

    def test_extrae_via_a(self):
        resultado = _extraer_via(TEXTO_FICHA_COMPLETA)
        assert "A" in resultado

    def test_extrae_via_c(self):
        # El regex requiere "Vía: X" (no "Vía de tramitación: X")
        texto = "CR 8.1: Reforma\nVía: C\n---"
        resultado = _extraer_via(texto)
        assert "C" in resultado

    def test_fallback_a_cuando_no_hay_via(self):
        resultado = _extraer_via(TEXTO_SIN_VIA)
        assert resultado == "A"

    def test_via_multiple(self):
        texto = "CR X.X: Algo\nVía: A/B\n---"
        resultado = _extraer_via(texto)
        assert "A" in resultado


# ── _extraer_documentacion ────────────────────────────────────────────────────

class TestExtraerDocumentacion:

    def test_extrae_lista_de_docs(self):
        resultado = _extraer_documentacion(TEXTO_FICHA_COMPLETA)
        assert "Proyecto Técnico" in resultado
        assert "Certificado de Conformidad" in resultado
        assert len(resultado) == 2

    def test_sin_documentacion_devuelve_lista_vacia(self):
        resultado = _extraer_documentacion(TEXTO_SIN_DOCUMENTACION)
        assert resultado == []

    def test_texto_vacio_devuelve_lista_vacia(self):
        assert _extraer_documentacion("") == []

    def test_un_solo_documento(self):
        resultado = _extraer_documentacion(TEXTO_SIN_ARS)
        assert resultado == ["Certificado de Taller"]


# ── _extraer_ars_raw ──────────────────────────────────────────────────────────

class TestExtraerArsRaw:

    def test_extrae_ars_presentes(self):
        resultado = _extraer_ars_raw(TEXTO_FICHA_COMPLETA)
        assert len(resultado) == 3
        textos = [ar["texto"] for ar in resultado]
        assert any("Frenos" in t for t in textos)
        assert any("Dirección" in t for t in textos)
        assert any("Emisiones" in t for t in textos)

    def test_sin_ars_devuelve_lista_vacia(self):
        resultado = _extraer_ars_raw(TEXTO_SIN_ARS)
        assert resultado == []

    def test_cada_ar_tiene_clave_texto(self):
        resultado = _extraer_ars_raw(TEXTO_FICHA_COMPLETA)
        for ar in resultado:
            assert "texto" in ar

    def test_texto_vacio_devuelve_lista_vacia(self):
        assert _extraer_ars_raw("") == []

    def test_para_antes_del_separador(self):
        # Los ARs después de '---' no deben incluirse
        texto = """Actos Reglamentarios aplicables:
- Frenos: M1: (1)
---
- Motor: M1: (2)"""
        resultado = _extraer_ars_raw(texto)
        assert len(resultado) == 1
        assert "Frenos" in resultado[0]["texto"]
