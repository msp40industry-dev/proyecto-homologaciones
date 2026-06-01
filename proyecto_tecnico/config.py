"""
Configuración de modelos para el generador de proyectos técnicos.

Los tres roles están definidos por variables de entorno con defaults seguros.
Para cambiar de modelo solo hay que actualizar el .env — sin tocar código.

Roles:
  MODELO_RAZONAMIENTO — tareas de razonamiento normativo complejo (IdentificadorCR)
  MODELO_REDACCION    — redacción de texto técnico estructurado (todos los redactores)
  MODELO_EMBEDDING    — generación de embeddings para ChromaDB
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODELO_RAZONAMIENTO: str = os.environ.get("MODELO_RAZONAMIENTO", "gpt-4o")
MODELO_REDACCION:    str = os.environ.get("MODELO_REDACCION",    "gpt-4o-mini")
MODELO_EMBEDDING:    str = os.environ.get("MODELO_EMBEDDING",    "text-embedding-3-small")
