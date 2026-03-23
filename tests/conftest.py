"""
conftest.py — Fixtures y configuración global para pytest.

Se ejecuta antes de importar cualquier módulo del proyecto.
Establece variables de entorno mínimas para evitar que config.py
lance EnvironmentError al importarse sin una API key real.
"""

import os
import sys
from pathlib import Path

# Añadir la raíz del proyecto al path antes de cualquier import
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

# API key ficticia — los tests que llaman a la API real deben usar mocks
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
