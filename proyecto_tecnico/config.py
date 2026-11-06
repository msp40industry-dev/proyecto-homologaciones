"""
Configuración de modelos para el generador de proyectos técnicos.

La selección se comparte con el backend mediante model_config.py.
Los clientes de texto se crean mediante el adaptador común de proveedores.

Roles:
  MODELO_RAZONAMIENTO — IdentificadorCR, condiciones KAG y Validador CR
  MODELO_REDACCION    — redacción de texto técnico estructurado (todos los redactores)
  MODELO_EMBEDDING    — generación de embeddings para ChromaDB
"""

from pathlib import Path
from dotenv import load_dotenv
from proyecto_tecnico.model_config import load_model_configuration

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL_CONFIGURATION = load_model_configuration()

PROVEEDOR_RAZONAMIENTO: str = MODEL_CONFIGURATION.reasoning.provider
MODELO_RAZONAMIENTO: str = MODEL_CONFIGURATION.reasoning.model
PROVEEDOR_REDACCION: str = MODEL_CONFIGURATION.writing.provider
MODELO_REDACCION: str = MODEL_CONFIGURATION.writing.model
MODELO_EMBEDDING: str = MODEL_CONFIGURATION.embedding_model
AWS_REGION: str = MODEL_CONFIGURATION.aws_region
