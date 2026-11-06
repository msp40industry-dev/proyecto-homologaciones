"""Interfaz de texto y salida Pydantic para OpenAI y Bedrock Converse.

No carga .env ni crea clientes al importar. Las credenciales las resuelve cada
SDK desde su entorno habitual; no se transfieren claves entre proveedores.
"""

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel

from proyecto_tecnico.model_config import (
    ModelConfiguration,
    ModelSelection,
    load_model_configuration,
)


class ModelAdapterError(RuntimeError):
    """Fallo de configuración/capacidad/invocación; nunca activa otro proveedor."""


def _normalise_message(message: AIMessage) -> AIMessage:
    """Conserva metadatos/consumo; extrae texto de los bloques de Bedrock.

    Los bloques de razonamiento no forman parte del texto entregado a los agentes.
    Un resultado sin texto es un error, no una respuesta vacía de aparente éxito.
    """
    if not isinstance(message, AIMessage):
        raise ModelAdapterError("El cliente no ha devuelto un mensaje de asistente.")
    if isinstance(message.content, str):
        text = message.content
    else:
        parts = []
        for block in message.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                value = block.get("text")
                if isinstance(value, str):
                    parts.append(value)
        text = "\n".join(parts)
    if not text.strip():
        raise ModelAdapterError("El modelo no ha devuelto contenido de texto utilizable.")
    return message.model_copy(update={"content": text})


def _invocation_error(selection: ModelSelection) -> ModelAdapterError:
    return ModelAdapterError(
        f"Fallo al invocar {selection.provider} / {selection.model}. "
        "Revisar credenciales, permisos, disponibilidad, parámetros y el error original."
    )


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class StructuredModelAdapter(Generic[T]):
    selection: ModelSelection
    _runnable: Runnable
    _schema: type[T]

    def invoke(self, messages: LanguageModelInput, config: RunnableConfig | None = None) -> T:
        try:
            result = self._runnable.invoke(messages, config=config)
            return self._schema.model_validate(result)
        except Exception as exc:
            raise _invocation_error(self.selection) from exc

    async def ainvoke(self, messages: LanguageModelInput, config: RunnableConfig | None = None) -> T:
        try:
            result = await self._runnable.ainvoke(messages, config=config)
            return self._schema.model_validate(result)
        except Exception as exc:
            raise _invocation_error(self.selection) from exc


@dataclass(frozen=True)
class ChatModelAdapter:
    selection: ModelSelection
    _client: Any

    def invoke(self, messages: LanguageModelInput, config: RunnableConfig | None = None) -> AIMessage:
        try:
            return _normalise_message(self._client.invoke(messages, config=config))
        except Exception as exc:
            raise _invocation_error(self.selection) from exc

    async def ainvoke(self, messages: LanguageModelInput, config: RunnableConfig | None = None) -> AIMessage:
        try:
            return _normalise_message(await self._client.ainvoke(messages, config=config))
        except Exception as exc:
            raise _invocation_error(self.selection) from exc

    def with_structured_output(self, schema: type[T]) -> StructuredModelAdapter[T]:
        if not isinstance(schema, type) or not issubclass(schema, BaseModel):
            raise TypeError("La salida estructurada requiere una clase Pydantic BaseModel.")
        try:
            if self.selection.provider == "openai":
                runnable = self._client.with_structured_output(schema, method="function_calling")
            else:
                runnable = self._client.with_structured_output(schema)
        except (NotImplementedError, ValueError) as exc:
            raise ModelAdapterError(
                f"No se puede configurar salida estructurada para "
                f"{self.selection.provider} / {self.selection.model}."
            ) from exc
        return StructuredModelAdapter(self.selection, runnable, schema)


def create_chat_model(
    selection: ModelSelection,
    *,
    region: str = "eu-west-1",
    temperature: float | None = 0.0,
    max_tokens: int | None = None,
) -> ChatModelAdapter:
    """Construye un cliente sin inferencia; la API valida las capacidades reales.

    Los modelos Bedrock deben admitir Converse. No todos los modelos del catálogo
    ofrecen esta API o salida estructurada. No se intenta otro modelo si falla.
    """
    if selection.provider not in ("openai", "bedrock"):
        raise ValueError("Proveedor no soportado: utilizar openai o bedrock.")
    if not selection.model.strip():
        raise ValueError("El identificador del modelo no puede estar vacío.")
    if max_tokens is not None and (isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0):
        raise ValueError("max_tokens debe ser un entero positivo.")
    options: dict[str, Any] = {"model": selection.model}
    if temperature is not None:
        options["temperature"] = temperature
    if max_tokens is not None:
        options["max_tokens"] = max_tokens

    if selection.provider == "openai":
        from langchain_openai import ChatOpenAI

        client = ChatOpenAI(**options)
    else:
        if not region.strip():
            raise ValueError("Bedrock requiere una región AWS.")
        from langchain_aws import ChatBedrockConverse

        # Sin profile ni claves explícitas: cadena de credenciales del SDK,
        # incluyendo perfil local o rol temporal del host en AWS.
        client = ChatBedrockConverse(region_name=region, **options)
    return ChatModelAdapter(selection, client)


def get_reasoning_model(
    configuration: ModelConfiguration | None = None,
    *,
    temperature: float | None = 0.0,
    max_tokens: int | None = None,
) -> ChatModelAdapter:
    settings = configuration if configuration is not None else load_model_configuration()
    return create_chat_model(settings.reasoning, region=settings.aws_region, temperature=temperature, max_tokens=max_tokens)


def get_writing_model(
    configuration: ModelConfiguration | None = None,
    *,
    temperature: float | None = 0.0,
    max_tokens: int | None = None,
) -> ChatModelAdapter:
    settings = configuration if configuration is not None else load_model_configuration()
    return create_chat_model(settings.writing, region=settings.aws_region, temperature=temperature, max_tokens=max_tokens)
