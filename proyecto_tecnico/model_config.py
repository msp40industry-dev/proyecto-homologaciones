"""Configuración compartida de modelos; no crea clientes ni realiza llamadas.

La lectura de .env corresponde a los puntos de entrada. Permite validar la
configuración sin cargar secretos ni depender de un SDK de proveedor.
"""

import os
from dataclasses import dataclass
from typing import Literal, Mapping


Provider = Literal["openai", "bedrock"]


@dataclass(frozen=True)
class ModelSelection:
    provider: Provider
    model: str


@dataclass(frozen=True)
class ModelConfiguration:
    reasoning: ModelSelection
    writing: ModelSelection
    embedding_model: str
    aws_region: str


def _selection(env: Mapping[str, str], role: str, default_model: str) -> ModelSelection:
    provider_key = f"PROVEEDOR_{role}"
    model_key = f"MODELO_{role}"
    provider = env.get(provider_key, "openai").strip().lower()
    if provider not in ("openai", "bedrock"):
        raise ValueError(f"{provider_key} debe ser 'openai' o 'bedrock'.")

    # Un proveedor Bedrock no debe heredar por omisión un nombre de modelo OpenAI.
    default = default_model if provider == "openai" else ""
    model = env.get(model_key, default).strip()
    if not model:
        raise ValueError(f"{model_key} debe indicar un modelo explícito para {provider}.")
    return ModelSelection(provider=provider, model=model)


def load_model_configuration(env: Mapping[str, str] | None = None) -> ModelConfiguration:
    """Lee ambos roles sin fallback entre proveedores ni validación remota de IDs."""
    env = os.environ if env is None else env
    region = env.get("AWS_REGION", env.get("AWS_DEFAULT_REGION", "eu-west-1")).strip()
    if not region:
        raise ValueError("AWS_REGION no puede estar vacía.")
    embedding_model = env.get("MODELO_EMBEDDING", "text-embedding-3-small").strip()
    if not embedding_model:
        raise ValueError("MODELO_EMBEDDING no puede estar vacío.")
    return ModelConfiguration(
        reasoning=_selection(env, "RAZONAMIENTO", "gpt-4o"),
        writing=_selection(env, "REDACCION", "gpt-4o-mini"),
        embedding_model=embedding_model,
        aws_region=region,
    )
