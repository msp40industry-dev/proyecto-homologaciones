"""
test_ensamblador.py — Tests de _construir_payload en el ensamblador de documentos.

Solo se prueba la función pura _construir_payload, que no requiere Node.js
ni subprocess. Se verifica la estructura y el contenido del dict devuelto.
"""

import pytest

from proyecto_tecnico.agents.ensamblador import _construir_payload
from proyecto_tecnico.models import (
    DatosVehiculo,
    Ingeniero,
    Taller,
    EntradaProyecto,
    SeccionGenerada,
    FichaCR,
    ARFiltrado,
    Componente,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def vehiculo():
    return DatosVehiculo(
        marca="Volkswagen",
        modelo="Golf 2.0 TDI",
        bastidor="WVWZZZ1KZAM123456",
        matricula="1234 ABC",
        fecha_matriculacion="15/03/2018",
        categoria="M1",
    )


@pytest.fixture
def ingeniero():
    return Ingeniero(
        nombre="Juan",
        apellidos="García Martínez",
        titulacion="Ingeniero Técnico Industrial",
        numero_colegiado="12345",
        colegio_profesional="COGITI Madrid",
    )


@pytest.fixture
def taller():
    return Taller(
        nombre="Taller López",
        direccion="Calle Mayor 10",
        localidad="Madrid",
        provincia="Madrid",
    )


@pytest.fixture
def entrada(vehiculo, ingeniero, taller):
    return EntradaProyecto(
        vehiculo=vehiculo,
        descripcion_reforma="Instalación de turbocompresor Garrett GT1749V en motor 1.6 TDI originalmente atmosférico.",
        taller=taller,
        ingeniero=ingeniero,
    )


@pytest.fixture
def seccion_objeto():
    return SeccionGenerada(
        id_seccion="objeto",
        titulo="1.1 Objeto del Proyecto",
        contenido="El presente proyecto técnico tiene por objeto...",
    )


@pytest.fixture
def ficha_cr():
    return FichaCR(
        codigo="2.1",
        denominacion="Modificación del motor mediante sobrealimentación",
        via="A",
        documentacion=["Proyecto Técnico", "Certificado de Conformidad"],
    )


@pytest.fixture
def ar_filtrado():
    return ARFiltrado(
        sistema="Frenos",
        referencia="(UNECE R13)",
        nivel_exigencia="(1)",
        descripcion_nivel="Se aplica en su última actualización en vigor",
        codigo_cr="2.1",
    )


# ── _construir_payload ────────────────────────────────────────────────────────

class TestConstruirPayload:

    def test_estructura_claves_principales(self, entrada, seccion_objeto, ficha_cr, ar_filtrado):
        payload = _construir_payload(
            proyecto_id="test-001",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[ficha_cr],
            ars=[ar_filtrado],
            adjuntos={},
            textos_manuales={},
        )
        assert "proyecto_id" in payload
        assert "metadata" in payload
        assert "crs" in payload
        assert "ars" in payload
        assert "secciones" in payload
        assert "adjuntos" in payload
        assert "textos_manuales" in payload

    def test_proyecto_id_correcto(self, entrada, seccion_objeto, ficha_cr, ar_filtrado):
        payload = _construir_payload(
            proyecto_id="abc-123",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[ficha_cr],
            ars=[ar_filtrado],
            adjuntos={},
            textos_manuales={},
        )
        assert payload["proyecto_id"] == "abc-123"

    def test_metadata_vehiculo(self, entrada, seccion_objeto):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos={},
            textos_manuales={},
        )
        meta = payload["metadata"]
        assert meta["vehiculo"] == "Volkswagen Golf 2.0 TDI"
        assert meta["bastidor"] == "WVWZZZ1KZAM123456"
        assert meta["matricula"] == "1234 ABC"
        assert meta["categoria"] == "M1"

    def test_metadata_ingeniero(self, entrada, seccion_objeto):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos={},
            textos_manuales={},
        )
        meta = payload["metadata"]
        assert "Juan" in meta["ingeniero"]
        assert "García Martínez" in meta["ingeniero"]
        assert meta["colegiado"] == "12345"
        assert meta["colegio"] == "COGITI Madrid"

    def test_crs_serializados(self, entrada, seccion_objeto, ficha_cr):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[ficha_cr],
            ars=[],
            adjuntos={},
            textos_manuales={},
        )
        assert len(payload["crs"]) == 1
        cr_payload = payload["crs"][0]
        assert cr_payload["codigo"] == "2.1"
        assert cr_payload["denominacion"] == "Modificación del motor mediante sobrealimentación"
        assert cr_payload["via"] == "A"

    def test_ars_serializados(self, entrada, seccion_objeto, ar_filtrado):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[ar_filtrado],
            adjuntos={},
            textos_manuales={},
        )
        assert len(payload["ars"]) == 1
        ar_payload = payload["ars"][0]
        assert ar_payload["sistema"] == "Frenos"
        assert ar_payload["referencia"] == "(UNECE R13)"
        assert ar_payload["nivel"] == "(1)"
        assert ar_payload["cr"] == "2.1"

    def test_secciones_con_contenido(self, entrada, seccion_objeto):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos={},
            textos_manuales={},
        )
        secciones = payload["secciones"]
        assert isinstance(secciones, list)
        # La sección "objeto" debe aparecer si está en _ORDEN_SECCIONES
        ids_presentes = [s["id"] for s in secciones]
        assert "objeto" in ids_presentes

    def test_textos_manuales_vacios_por_defecto(self, entrada, seccion_objeto):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos={},
            textos_manuales={},
        )
        tm = payload["textos_manuales"]
        assert tm["caracteristicas_antes"] == ""
        assert tm["caracteristicas_despues"] == ""

    def test_textos_manuales_se_incluyen(self, entrada, seccion_objeto):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos={},
            textos_manuales={
                "caracteristicas_antes": "Motor 1.6 TDI, 90 CV, inyección directa.",
                "caracteristicas_despues": "Motor 1.6 TDI con turbo Garrett, 120 CV.",
            },
        )
        tm = payload["textos_manuales"]
        assert tm["caracteristicas_antes"] == "Motor 1.6 TDI, 90 CV, inyección directa."
        assert tm["caracteristicas_despues"] == "Motor 1.6 TDI con turbo Garrett, 120 CV."

    def test_sin_crs_ni_ars(self, entrada, seccion_objeto):
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos={},
            textos_manuales={},
        )
        assert payload["crs"] == []
        assert payload["ars"] == []

    def test_adjuntos_se_pasan_directamente(self, entrada, seccion_objeto):
        adjuntos_test = {
            "plano_tecnico": {"nombre": "plano.jpg", "path": "/tmp/plano.jpg", "es_imagen": True}
        }
        payload = _construir_payload(
            proyecto_id="x",
            entrada=entrada,
            secciones={"objeto": seccion_objeto},
            crs=[],
            ars=[],
            adjuntos=adjuntos_test,
            textos_manuales={},
        )
        assert payload["adjuntos"] == adjuntos_test
