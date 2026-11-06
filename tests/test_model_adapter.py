"""Contrato del adaptador; clientes simulados, sin llamadas facturables."""

import unittest
import os
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from proyecto_tecnico.model_adapter import (
    ChatModelAdapter,
    ModelAdapterError,
    create_chat_model,
    get_reasoning_model,
    get_writing_model,
)
from proyecto_tecnico.model_config import ModelSelection, load_model_configuration


class ReformResult(BaseModel):
    cr: str
    aplica: bool


class AdapterTests(unittest.TestCase):
    def test_openai_configuration_and_no_bedrock_client(self):
        with patch("langchain_openai.ChatOpenAI") as openai, patch("langchain_aws.ChatBedrockConverse") as bedrock:
            create_chat_model(ModelSelection("openai", "gpt-4o"), max_tokens=123)
        openai.assert_called_once_with(model="gpt-4o", temperature=0.0, max_tokens=123)
        bedrock.assert_not_called()

    def test_bedrock_region_and_no_openai_client(self):
        with patch("langchain_openai.ChatOpenAI") as openai, patch("langchain_aws.ChatBedrockConverse") as bedrock:
            create_chat_model(ModelSelection("bedrock", "eu.anthropic.claude-sonnet-4-6"), region="eu-west-1", temperature=None)
        bedrock.assert_called_once_with(model="eu.anthropic.claude-sonnet-4-6", region_name="eu-west-1")
        openai.assert_not_called()

    def test_roles_select_independent_models(self):
        config = load_model_configuration({
            "PROVEEDOR_RAZONAMIENTO": "bedrock", "MODELO_RAZONAMIENTO": "reasoning-id",
            "MODELO_REDACCION": "writing-id",
        })
        with patch("proyecto_tecnico.model_adapter.create_chat_model") as factory:
            get_reasoning_model(config)
            self.assertEqual(factory.call_args.args[0], ModelSelection("bedrock", "reasoning-id"))
            get_writing_model(config)
            self.assertEqual(factory.call_args.args[0], ModelSelection("openai", "writing-id"))

    def test_invalid_provider_or_token_limit_fails_before_clients(self):
        with self.assertRaises(ValueError):
            create_chat_model(ModelSelection("typo", "model"))
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                create_chat_model(ModelSelection("openai", "model"), max_tokens=limit)

    def test_text_normalisation_preserves_usage_without_reasoning(self):
        message = AIMessage(
            content=[{"type": "reasoning_content", "text": "private reasoning"}, {"type": "text", "text": "Respuesta"}],
            usage_metadata={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            response_metadata={"request_id": "test-request"},
        )
        adapter = ChatModelAdapter(ModelSelection("bedrock", "model"), Mock(invoke=Mock(return_value=message)))
        result = adapter.invoke("Pregunta")
        self.assertEqual(result.content, "Respuesta")
        self.assertEqual(result.usage_metadata, message.usage_metadata)
        self.assertEqual(result.response_metadata, message.response_metadata)

    def test_plain_openai_message_preserves_text(self):
        client = Mock(invoke=Mock(return_value=AIMessage(content="Texto")))
        self.assertEqual(ChatModelAdapter(ModelSelection("openai", "model"), client).invoke("q").content, "Texto")

    def test_no_text_is_an_error_not_empty_success(self):
        client = Mock(invoke=Mock(return_value=AIMessage(content=[])))
        with self.assertRaises(ModelAdapterError):
            ChatModelAdapter(ModelSelection("bedrock", "model"), client).invoke("q")

    def test_invocation_failure_keeps_cause_and_does_not_fallback(self):
        failure = RuntimeError("simulated permission failure")
        client = Mock(invoke=Mock(side_effect=failure))
        adapter = ChatModelAdapter(ModelSelection("bedrock", "model"), client)
        with patch("langchain_openai.ChatOpenAI") as fallback:
            with self.assertRaises(ModelAdapterError) as error:
                adapter.invoke("q")
        self.assertIs(error.exception.__cause__, failure)
        fallback.assert_not_called()

    def test_structured_output_validates_and_openai_uses_tools(self):
        runnable = Mock(invoke=Mock(return_value={"cr": "2.1", "aplica": True}))
        client = Mock(with_structured_output=Mock(return_value=runnable))
        adapter = ChatModelAdapter(ModelSelection("openai", "model"), client)
        result = adapter.with_structured_output(ReformResult).invoke("q")
        self.assertIsInstance(result, ReformResult)
        client.with_structured_output.assert_called_once_with(ReformResult, method="function_calling")

    def test_bedrock_structured_output_and_invalid_result(self):
        runnable = Mock(invoke=Mock(return_value={"unexpected": "value"}))
        client = Mock(with_structured_output=Mock(return_value=runnable))
        adapter = ChatModelAdapter(ModelSelection("bedrock", "model"), client)
        with self.assertRaises(ModelAdapterError) as error:
            adapter.with_structured_output(ReformResult).invoke("q")
        self.assertIsInstance(error.exception.__cause__, ValidationError)
        client.with_structured_output.assert_called_once_with(ReformResult)

    def test_unsupported_structured_output_reports_capability(self):
        client = Mock(with_structured_output=Mock(side_effect=NotImplementedError))
        with self.assertRaisesRegex(ModelAdapterError, "salida estructurada"):
            ChatModelAdapter(ModelSelection("bedrock", "model"), client).with_structured_output(ReformResult)

    def test_structured_schema_must_be_pydantic_class(self):
        with self.assertRaises(TypeError):
            ChatModelAdapter(ModelSelection("openai", "model"), Mock()).with_structured_output({"type": "object"})


class AsyncAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_text_normalises_blocks_and_forwards_config(self):
        client = Mock(ainvoke=AsyncMock(return_value=AIMessage(content=[{"type": "text", "text": "Respuesta"}])))
        adapter = ChatModelAdapter(ModelSelection("bedrock", "model"), client)
        config = {"tags": ["test"]}
        result = await adapter.ainvoke("q", config=config)
        self.assertEqual(result.content, "Respuesta")
        client.ainvoke.assert_awaited_once_with("q", config=config)

    async def test_async_structured_output(self):
        runnable = Mock(ainvoke=AsyncMock(return_value=ReformResult(cr="2.1", aplica=True)))
        client = Mock(with_structured_output=Mock(return_value=runnable))
        result = await ChatModelAdapter(ModelSelection("bedrock", "model"), client).with_structured_output(ReformResult).ainvoke("q")
        self.assertEqual(result.cr, "2.1")

    async def test_async_errors_are_explicit(self):
        client = Mock(ainvoke=AsyncMock(side_effect=RuntimeError("simulated")))
        with self.assertRaises(ModelAdapterError):
            await ChatModelAdapter(ModelSelection("bedrock", "model"), client).ainvoke("q")


class ClientCompatibilityTests(unittest.TestCase):
    """Usa los clientes reales, sustituyendo solo el transporte de cada SDK."""

    def test_bedrock_converse_serialisation_and_usage(self):
        from botocore.stub import Stubber

        with patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_EC2_METADATA_DISABLED": "true",
        }):
            adapter = create_chat_model(ModelSelection("bedrock", "eu.anthropic.claude-sonnet-4-6"), max_tokens=99)
        response = {
            "output": {"message": {"role": "assistant", "content": [{"text": "Respuesta Bedrock"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 5, "outputTokens": 3, "totalTokens": 8},
            "metrics": {"latencyMs": 1},
        }
        with Stubber(adapter._client.client) as stub:
            stub.add_response("converse", response, {
                "modelId": "eu.anthropic.claude-sonnet-4-6",
                "messages": [{"role": "user", "content": [{"text": "Pregunta"}]}],
                "system": [{"text": "Usa solo el contexto"}],
                "inferenceConfig": {"temperature": 0.0, "maxTokens": 99},
            })
            result = adapter.invoke([SystemMessage(content="Usa solo el contexto"), HumanMessage(content="Pregunta")])
        self.assertEqual(result.content, "Respuesta Bedrock")
        self.assertEqual(result.usage_metadata["total_tokens"], 8)

    def test_bedrock_structured_tool_result_parsed_with_real_client(self):
        from botocore.stub import Stubber

        with patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_EC2_METADATA_DISABLED": "true",
        }):
            adapter = create_chat_model(ModelSelection("bedrock", "eu.anthropic.claude-sonnet-4-6"))
        response = {
            "output": {"message": {"role": "assistant", "content": [{
                "toolUse": {"toolUseId": "test-id", "name": "ReformResult", "input": {"cr": "2.1", "aplica": True}},
            }]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 5, "outputTokens": 3, "totalTokens": 8},
            "metrics": {"latencyMs": 1},
        }
        with Stubber(adapter._client.client) as stub:
            stub.add_response("converse", response)
            result = adapter.with_structured_output(ReformResult).invoke("Pregunta")
        self.assertEqual(result, ReformResult(cr="2.1", aplica=True))

    def test_openai_serialisation_and_usage(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-placeholder"}):
            adapter = create_chat_model(ModelSelection("openai", "gpt-4o-mini"))
        response = {
            "id": "test-id", "model": "gpt-4o-mini", "object": "chat.completion", "created": 0,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Respuesta OpenAI"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        with patch.object(adapter._client.client, "create", return_value=response) as request:
            result = adapter.invoke("Pregunta")
        self.assertEqual(result.content, "Respuesta OpenAI")
        self.assertEqual(result.usage_metadata["total_tokens"], 8)
        self.assertEqual(request.call_args.kwargs["model"], "gpt-4o-mini")
