"""
Configuración centralizada del backend.
Todas las variables de entorno y paths se leen desde aquí.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

endpoint = os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT")
if endpoint:
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    os.environ["LANGSMITH_ENDPOINT"] = endpoint

# ─── Paths ────────────────────────────────────────────────────────────────────

# Estructura del proyecto:
#   backend/rag/config.py → parents[2] = raíz del proyecto
#   chroma_db está en scripts_index/chroma_db/ (mismo lugar que indexado.py)
BASE_DIR   = Path(__file__).resolve().parents[2]
CHROMA_DIR = BASE_DIR / "scripts_index" / "chroma_db"

# ─── OpenAI ───────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY no encontrada.\n"
        "Crea un fichero .env en el directorio raíz con:\n"
        "  OPENAI_API_KEY=sk-..."
    )

EMBEDDING_MODEL  = "text-embedding-3-small"
GENERATION_MODEL = "gpt-4o-mini"

# ─── LangSmith ────────────────────────────────────────────────────────────────
# Opcional — si no se configura, simplemente no hay trazas

LANGCHAIN_TRACING  = os.environ.get("LANGCHAIN_TRACING_V2", "false")
LANGCHAIN_API_KEY  = os.environ.get("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT  = os.environ.get("LANGCHAIN_PROJECT", "poc-reformas-vehiculos")

if LANGCHAIN_TRACING == "true" and not LANGCHAIN_API_KEY:
    print("⚠ LANGCHAIN_TRACING_V2=true pero LANGCHAIN_API_KEY no configurada — trazas desactivadas")

# ─── Chroma ───────────────────────────────────────────────────────────────────

COLECCION_FICHAS     = "fichas_cr"
COLECCION_PREAMBULO  = "preambulo"
COLECCION_REGLAMENTO = "reglamento_ue"

# Número de chunks a recuperar por colección en cada consulta
N_RESULTS_FICHAS     = 3
N_RESULTS_PREAMBULO  = 2
N_RESULTS_REGLAMENTO = 2

# Si las respuestas parecen incompletas, aumentamos el número.
# Si el contexto es demasiado largo y el modelo se pierde, bajamos el número.

# ─── RAG ──────────────────────────────────────────────────────────────────────

MAX_TOKENS_RESPUESTA = 1024
TEMPERATURE          = 0.0   # respuestas deterministas para dominio técnico-legal
