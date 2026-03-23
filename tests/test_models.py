"""
test_models.py — Validación de los modelos Pydantic del generador de proyectos técnicos.

Verifica que los modelos aceptan entradas válidas, rechazan las inválidas
y aplican los valores por defecto correctamente.
"""

import pytest
from pydantic import ValidationError

from proyecto_tecnico.models import (
    DatosVehiculo,
    Componente,
    Taller,
    Ingeniero,
    EntradaProyecto,
    SeccionGenerada,
    EstadoRevision,
    FichaCR,
    ARFiltrado,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def vehiculo_valido():
    return DatosVehiculo(
        marca="Volkswagen",
        modelo="Golf 2.0 TDI",
        bastidor="WVWZZZ1KZAM123456",
        matricula="1234 ABC",
        fecha_matriculacion="15/03/2018",
        categoria="M1",
    )


@pytest.fixture
def ingeniero_valido():
    return Ingeniero(
        nombre="Juan",
        apellidos="García Martínez",
        titulacion="Ingeniero Técnico Industrial",
        numero_colegiado="12345",
        colegio_profesional="COGITI Madrid",
    )


@pytest.fixture
def taller_valido():
    return Taller(
        nombre="Taller López",
        direccion="Calle Mayor 10",
        localidad="Madrid",
        provincia="Madrid",
    )


@pytest.fixture
def entrada_valida(vehiculo_valido, ingeniero_valido, taller_valido):
    return EntradaProyecto(
        vehiculo=vehiculo_valido,
        descripcion_reforma="Instalación de turbocompresor Garrett GT1749V en motor 1.6 TDI originalmente atmosférico.",
        taller=taller_valido,
        ingeniero=ingeniero_valido,
    )


# ── DatosVehiculo ─────────────────────────────────────────────────────────────

class TestDatosVehiculo:

    def test_campos_obligatorios_completos(self, vehiculo_valido):
        assert vehiculo_valido.marca == "Volkswagen"
        assert vehiculo_valido.categoria == "M1"

    def test_campos_opcionales_por_defecto_none(self, vehiculo_valido):
        assert vehiculo_valido.color is None
        assert vehiculo_valido.kilometraje is None

    def test_campos_opcionales_se_asignan(self):
        v = DatosVehiculo(
            marca="Seat", modelo="Ibiza", bastidor="VS6ZZZ6JZJR000001",
            matricula="5678 XYZ", fecha_matriculacion="01/01/2020",
            categoria="M1", color="Rojo", kilometraje="45.000 km",
        )
        assert v.color == "Rojo"
        assert v.kilometraje == "45.000 km"

    def test_falta_campo_obligatorio_lanza_error(self):
        with pytest.raises(ValidationError):
            DatosVehiculo(
                marca="Seat",
                # modelo falta
                bastidor="VS6ZZZ6JZJR000001",
                matricula="5678 XYZ",
                fecha_matriculacion="01/01/2020",
                categoria="M1",
            )


# ── Componente ────────────────────────────────────────────────────────────────

class TestComponente:

    def test_solo_descripcion_obligatoria(self):
        c = Componente(descripcion="Turbocompresor")
        assert c.descripcion == "Turbocompresor"
        assert c.marca is None
        assert c.numero_homologacion is None

    def test_todos_los_campos(self):
        c = Componente(
            descripcion="Turbocompresor",
            marca="Garrett",
            modelo="GT1749V",
            referencia="700447-5008S",
            numero_homologacion="e1*11R-01/0123*01",
        )
        assert c.referencia == "700447-5008S"


# ── EntradaProyecto ───────────────────────────────────────────────────────────

class TestEntradaProyecto:

    def test_entrada_valida_sin_crs(self, entrada_valida):
        assert entrada_valida.crs_indicados == []
        assert entrada_valida.componentes == []
        assert entrada_valida.numero_expediente is None

    def test_descripcion_muy_corta_lanza_error(self, vehiculo_valido, ingeniero_valido, taller_valido):
        with pytest.raises(ValidationError):
            EntradaProyecto(
                vehiculo=vehiculo_valido,
                descripcion_reforma="Corta",  # menos de 20 caracteres
                taller=taller_valido,
                ingeniero=ingeniero_valido,
            )

    def test_crs_indicados_se_asignan(self, vehiculo_valido, ingeniero_valido, taller_valido):
        entrada = EntradaProyecto(
            vehiculo=vehiculo_valido,
            descripcion_reforma="Instalación de turbocompresor en motor originalmente atmosférico.",
            taller=taller_valido,
            ingeniero=ingeniero_valido,
            crs_indicados=["2.1", "4.4"],
        )
        assert entrada.crs_indicados == ["2.1", "4.4"]

    def test_con_componentes(self, vehiculo_valido, ingeniero_valido, taller_valido):
        entrada = EntradaProyecto(
            vehiculo=vehiculo_valido,
            descripcion_reforma="Instalación de turbocompresor en motor originalmente atmosférico.",
            taller=taller_valido,
            ingeniero=ingeniero_valido,
            componentes=[Componente(descripcion="Turbocompresor", marca="Garrett")],
        )
        assert len(entrada.componentes) == 1
        assert entrada.componentes[0].marca == "Garrett"


# ── EstadoRevision y SeccionGenerada ──────────────────────────────────────────

class TestEstadoRevision:

    def test_estado_por_defecto(self):
        sec = SeccionGenerada(id_seccion="objeto", titulo="1.1 Objeto", contenido="Texto de prueba.")
        assert sec.revision.estado == "pendiente"
        assert sec.revision.iteraciones == 0
        assert sec.revision.motivo is None

    def test_estado_aprobado(self):
        rev = EstadoRevision(estado="aprobado", iteraciones=0)
        assert rev.estado == "aprobado"

    def test_estado_reescribir_con_motivo(self):
        rev = EstadoRevision(estado="reescribir", motivo="El CR indicado es incorrecto.", iteraciones=1)
        assert rev.motivo == "El CR indicado es incorrecto."
        assert rev.iteraciones == 1


# ── FichaCR y ARFiltrado ──────────────────────────────────────────────────────

class TestFichaCR:

    def test_ficha_cr_minima(self):
        ficha = FichaCR(codigo="2.1", denominacion="Modificación del motor", via="A")
        assert ficha.codigo == "2.1"
        assert ficha.ars == []
        assert ficha.documentacion == []

    def test_ficha_cr_completa(self):
        ficha = FichaCR(
            codigo="8.20",
            denominacion="Instalación de elementos aerodinámicos",
            via="A",
            documentacion=["Proyecto Técnico", "Certificado de Taller"],
            informacion_adicional="No aplica si la pieza es de serie.",
        )
        assert len(ficha.documentacion) == 2
        assert "No aplica" in ficha.informacion_adicional


class TestARFiltrado:

    def test_ar_filtrado(self):
        ar = ARFiltrado(
            sistema="Frenos",
            referencia="(UNECE R13)",
            nivel_exigencia="(1)",
            descripcion_nivel="Se aplica en su última actualización en vigor",
            codigo_cr="2.1",
        )
        assert ar.nivel_exigencia == "(1)"
        assert ar.codigo_cr == "2.1"
