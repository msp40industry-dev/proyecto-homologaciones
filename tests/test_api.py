"""
test_api.py — Tests de los endpoints FastAPI del backend RAG.

Se usa TestClient de Starlette. Las llamadas a ChromaDB y OpenAI se mockean
para que los tests sean rápidos y sin dependencias externas.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from backend.main import app


# ── Cliente de tests ──────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_health_devuelve_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_contiene_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_contiene_version(self, client):
        data = client.get("/health").json()
        assert "version" in data


# ── /categorias ───────────────────────────────────────────────────────────────

class TestCategoriasEndpoint:

    def test_devuelve_categorias_m(self, client):
        data = client.get("/categorias").json()
        assert "M" in data
        assert "M1" in data["M"]

    def test_devuelve_categorias_n(self, client):
        data = client.get("/categorias").json()
        assert "N" in data
        assert "N1" in data["N"]

    def test_devuelve_categorias_o(self, client):
        data = client.get("/categorias").json()
        assert "O" in data
        assert "O4" in data["O"]


# ── /vias ─────────────────────────────────────────────────────────────────────

class TestViasEndpoint:

    def test_devuelve_lista_de_vias(self, client):
        data = client.get("/vias").json()
        assert isinstance(data, list)
        assert len(data) == 4

    def test_vias_tienen_campo_via_y_descripcion(self, client):
        data = client.get("/vias").json()
        for via in data:
            assert "via" in via
            assert "descripcion" in via

    def test_via_a_esta_en_lista(self, client):
        data = client.get("/vias").json()
        codigos = [v["via"] for v in data]
        assert "A" in codigos

    def test_todas_las_vias_presentes(self, client):
        data = client.get("/vias").json()
        codigos = {v["via"] for v in data}
        assert codigos == {"A", "B", "C", "D"}


# ── /consulta ─────────────────────────────────────────────────────────────────

class TestConsultaEndpoint:

    def _mock_consultar(self):
        return {
            "respuesta": "Para instalar un turbo en un M1 necesitas un Proyecto Técnico.",
            "fuentes": [
                {"tipo": "ficha_cr", "cr": "2.1", "via": "A", "apartado": None, "titulo": None, "paginas": None}
            ],
            "n_docs": 1,
        }

    def test_consulta_valida_devuelve_200(self, client):
        with patch("backend.main.consultar", return_value=self._mock_consultar()):
            response = client.post("/consulta", json={
                "pregunta": "¿Qué necesito para instalar un turbo en un M1?",
                "categoria": "M1",
                "via": None,
                "historial": [],
            })
        assert response.status_code == 200

    def test_consulta_devuelve_respuesta_y_fuentes(self, client):
        with patch("backend.main.consultar", return_value=self._mock_consultar()):
            data = client.post("/consulta", json={
                "pregunta": "¿Qué necesito para instalar un turbo en un M1?",
            }).json()
        assert "respuesta" in data
        assert "fuentes" in data
        assert "n_docs" in data

    def test_consulta_sin_pregunta_devuelve_422(self, client):
        response = client.post("/consulta", json={"categoria": "M1"})
        assert response.status_code == 422

    def test_consulta_pregunta_vacia_devuelve_422(self, client):
        response = client.post("/consulta", json={"pregunta": ""})
        assert response.status_code == 422

    def test_consulta_pregunta_demasiado_larga_devuelve_422(self, client):
        response = client.post("/consulta", json={"pregunta": "x" * 1001})
        assert response.status_code == 422

    def test_consulta_con_historial(self, client):
        with patch("backend.main.consultar", return_value=self._mock_consultar()):
            response = client.post("/consulta", json={
                "pregunta": "¿Y si es N1?",
                "historial": [
                    {"role": "user", "content": "¿Qué necesito para instalar un turbo?"},
                    {"role": "assistant", "content": "Necesitas un Proyecto Técnico."},
                ],
            })
        assert response.status_code == 200

    def test_consulta_n_docs_correcto(self, client):
        with patch("backend.main.consultar", return_value=self._mock_consultar()):
            data = client.post("/consulta", json={"pregunta": "¿Qué es el CR 2.1?"}).json()
        assert data["n_docs"] == 1

    def test_consulta_error_interno_devuelve_500(self, client):
        with patch("backend.main.consultar", side_effect=RuntimeError("Error de ChromaDB")):
            response = client.post("/consulta", json={"pregunta": "¿Qué es el CR 2.1?"})
        assert response.status_code == 500
