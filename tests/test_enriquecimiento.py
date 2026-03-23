"""
test_enriquecimiento.py — Tests de cargar_csv y enriquecer en enriquecimiento.py.

Se usan ficheros temporales (tmp_path) para no depender de ficheros reales del proyecto.
"""

import csv
import json
import pytest
from pathlib import Path

from scripts_enrich.enriquecimiento import cargar_csv, enriquecer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _crear_csv(path: Path, filas: list[dict]) -> Path:
    """Crea un CSV de keywords en path con las filas dadas."""
    csv_path = path / "keywords.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cr", "keyword"])
        writer.writeheader()
        writer.writerows(filas)
    return csv_path


def _crear_json_fichas(path: Path, fichas: list[dict]) -> Path:
    """Crea un JSON de fichas en path."""
    json_path = path / "fichas.json"
    data = {
        "metadata": {"version": "test", "ultimo_enriquecimiento": ""},
        "fichas": fichas,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return json_path


# ── cargar_csv ────────────────────────────────────────────────────────────────

class TestCargarCsv:

    def test_carga_keywords_correctamente(self, tmp_path):
        csv_path = _crear_csv(tmp_path, [
            {"cr": "2.1", "keyword": "turbocompresor"},
            {"cr": "2.1", "keyword": "sobrealimentación"},
            {"cr": "8.20", "keyword": "alerón"},
        ])
        resultado, errores = cargar_csv(csv_path)
        assert "2.1" in resultado
        assert "turbocompresor" in resultado["2.1"]
        assert "sobrealimentación" in resultado["2.1"]
        assert "alerón" in resultado["8.20"]

    def test_deduplica_keywords_case_insensitive(self, tmp_path):
        csv_path = _crear_csv(tmp_path, [
            {"cr": "2.1", "keyword": "Turbocompresor"},
            {"cr": "2.1", "keyword": "turbocompresor"},
            {"cr": "2.1", "keyword": "TURBOCOMPRESOR"},
        ])
        resultado, _ = cargar_csv(csv_path)
        assert len(resultado["2.1"]) == 1

    def test_ignora_filas_con_cr_vacio(self, tmp_path):
        csv_path = _crear_csv(tmp_path, [
            {"cr": "", "keyword": "turbo"},
            {"cr": "2.1", "keyword": "compresor"},
        ])
        resultado, errores = cargar_csv(csv_path)
        assert len(errores) >= 1
        assert "" not in resultado
        assert "2.1" in resultado

    def test_ignora_filas_con_keyword_vacia(self, tmp_path):
        csv_path = _crear_csv(tmp_path, [
            {"cr": "2.1", "keyword": ""},
            {"cr": "2.1", "keyword": "turbocompresor"},
        ])
        resultado, errores = cargar_csv(csv_path)
        assert len(errores) >= 1
        assert len(resultado["2.1"]) == 1

    def test_error_si_falta_columna_cr(self, tmp_path):
        csv_path = tmp_path / "mal.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["keyword"])
            writer.writeheader()
            writer.writerow({"keyword": "turbo"})
        with pytest.raises(ValueError, match="cr"):
            cargar_csv(csv_path)

    def test_error_si_falta_columna_keyword(self, tmp_path):
        csv_path = tmp_path / "mal.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["cr"])
            writer.writeheader()
            writer.writerow({"cr": "2.1"})
        with pytest.raises(ValueError, match="keyword"):
            cargar_csv(csv_path)

    def test_csv_vacio_devuelve_dict_vacio(self, tmp_path):
        csv_path = _crear_csv(tmp_path, [])
        resultado, errores = cargar_csv(csv_path)
        assert resultado == {}
        assert errores == []

    def test_multiples_crs(self, tmp_path):
        csv_path = _crear_csv(tmp_path, [
            {"cr": "2.1", "keyword": "turbo"},
            {"cr": "4.4", "keyword": "escape"},
            {"cr": "8.20", "keyword": "alerón"},
        ])
        resultado, _ = cargar_csv(csv_path)
        assert len(resultado) == 3


# ── enriquecer ────────────────────────────────────────────────────────────────

class TestEnriquecer:

    def test_añade_keywords_a_ficha_existente(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Modificación del motor", "keywords_reformas": []},
        ])
        keywords = {"2.1": ["turbocompresor", "sobrealimentación"]}
        data, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        ficha = next(f for f in data["fichas"] if f["cr"] == "2.1")
        assert "turbocompresor" in ficha["keywords_reformas"]
        assert "sobrealimentación" in ficha["keywords_reformas"]

    def test_no_duplica_keywords_existentes(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": ["turbocompresor"]},
        ])
        keywords = {"2.1": ["turbocompresor", "sobrealimentación"]}
        data, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        ficha = next(f for f in data["fichas"] if f["cr"] == "2.1")
        count = ficha["keywords_reformas"].count("turbocompresor")
        assert count == 1

    def test_stats_fichas_actualizadas(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": []},
            {"cr": "8.20", "denominacion": "Alerón", "keywords_reformas": []},
        ])
        keywords = {"2.1": ["turbo"]}
        _, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        assert stats["fichas_actualizadas"] == 1

    def test_stats_keywords_añadidas(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": []},
        ])
        keywords = {"2.1": ["turbo", "compresor", "sobrealimentación"]}
        _, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        assert stats["keywords_añadidas"] == 3

    def test_detecta_crs_que_no_existen(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": []},
        ])
        keywords = {"2.1": ["turbo"], "99.99": ["inexistente"]}
        _, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        assert "99.99" in stats["crs_no_encontrados"]

    def test_actualiza_metadata_fecha_enriquecimiento(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": []},
        ])
        keywords = {"2.1": ["turbo"]}
        data, _ = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        assert data["metadata"]["ultimo_enriquecimiento"] != ""

    def test_sin_keywords_para_fichas_no_las_modifica(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": ["existente"]},
        ])
        keywords = {}  # ninguna keyword
        data, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        ficha = next(f for f in data["fichas"] if f["cr"] == "2.1")
        assert ficha["keywords_reformas"] == ["existente"]
        assert stats["fichas_actualizadas"] == 0

    def test_no_duplica_case_insensitive(self, tmp_path):
        fichas_path = _crear_json_fichas(tmp_path, [
            {"cr": "2.1", "denominacion": "Motor", "keywords_reformas": ["Turbocompresor"]},
        ])
        keywords = {"2.1": ["turbocompresor"]}  # misma pero en minúscula
        data, stats = enriquecer(fichas_path, keywords, csv_path=fichas_path)
        ficha = next(f for f in data["fichas"] if f["cr"] == "2.1")
        count = sum(1 for k in ficha["keywords_reformas"] if k.lower() == "turbocompresor")
        assert count == 1
        assert stats["keywords_añadidas"] == 0
