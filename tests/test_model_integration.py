"""Verifica que los flujos utilizan el grupo correcto sin LLM ni Chroma reales."""

import unittest
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from rag import chain, graph_retriever, retriever
from proyecto_tecnico import validador_crs
from proyecto_tecnico.agents import identificador_cr, redactor_conclusiones, redactor_memoria, redactor_pliego
from proyecto_tecnico.model_adapter import ChatModelAdapter
from proyecto_tecnico.model_config import load_model_configuration


SETTINGS = load_model_configuration({
    "PROVEEDOR_RAZONAMIENTO": "bedrock",
    "MODELO_RAZONAMIENTO": "eu.reasoning-test",
    "PROVEEDOR_REDACCION": "openai",
    "MODELO_REDACCION": "writing-test",
})


class ChatIntegrationTests(unittest.TestCase):
    def test_chatbot_selects_writing_group_and_returns_text(self):
        raw_client = Mock(invoke=Mock(return_value=AIMessage(content="Respuesta de prueba")))
        adapter = ChatModelAdapter(SETTINGS.writing, raw_client)
        with patch.object(chain.config, "MODEL_CONFIGURATION", SETTINGS), \
             patch.object(chain, "recuperar", return_value={"fichas": [], "preambulo": [], "reglamento": []}), \
             patch("proyecto_tecnico.model_adapter.create_chat_model", return_value=adapter) as factory:
            result = chain.consultar("¿Qué es una reforma?")
        self.assertEqual(result["respuesta"], "Respuesta de prueba")
        self.assertEqual(factory.call_args.args[0], SETTINGS.writing)
        self.assertEqual(factory.call_args.kwargs["max_tokens"], chain.config.MAX_TOKENS_RESPUESTA)

    def test_query_expansion_selects_configured_writing_model(self):
        adapter = Mock(invoke=Mock(return_value=AIMessage(content="sistema de suspensión")))
        with patch.object(retriever.config, "MODEL_CONFIGURATION", SETTINGS), \
             patch("proyecto_tecnico.model_adapter.create_chat_model", return_value=adapter) as factory:
            result = retriever._expandir_query("cambiar muelles")
        self.assertEqual(result, "cambiar muelles sistema de suspensión")
        self.assertEqual(factory.call_args.args[0], SETTINGS.writing)
        self.assertEqual(factory.call_args.kwargs["max_tokens"], 100)

    def test_directive_description_uses_the_provided_adapter(self):
        docs = [Document(page_content="Texto de la directiva", metadata={"titulo": "Título"})]
        collection = Mock(similarity_search=Mock(return_value=docs))
        adapter = Mock(invoke=Mock(return_value=AIMessage(content="Descripción")))
        with patch("langchain_chroma.Chroma", return_value=collection), \
             patch("langchain_openai.OpenAIEmbeddings"):
            result = chain._describir_directiva("70/156/CEE", adapter)
        self.assertIn("Descripción", result)
        adapter.invoke.assert_called_once()

    def test_redactor_factories_use_writing_group_lazily(self):
        for module in (redactor_memoria, redactor_pliego, redactor_conclusiones):
            with self.subTest(module=module.__name__):
                module._get_llm.cache_clear()
                try:
                    with patch.object(module, "MODEL_CONFIGURATION", SETTINGS), \
                         patch("proyecto_tecnico.model_adapter.create_chat_model") as factory:
                        module._get_llm()
                        module._get_llm()
                    factory.assert_called_once()
                    self.assertEqual(factory.call_args.args[0], SETTINGS.writing)
                finally:
                    module._get_llm.cache_clear()

    def test_identificador_builds_structured_reasoning_client_lazily(self):
        identificador_cr._get_llm_structured.cache_clear()
        try:
            with patch.object(identificador_cr, "MODEL_CONFIGURATION", SETTINGS), \
                 patch("proyecto_tecnico.model_adapter.create_chat_model") as factory:
                identificador_cr._get_llm_structured()
            self.assertEqual(factory.call_args.args[0], SETTINGS.reasoning)
            factory.return_value.with_structured_output.assert_called_once_with(identificador_cr._RespuestaCRs)
        finally:
            identificador_cr._get_llm_structured.cache_clear()


class ReasoningIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_kag_conditions_use_reasoning_and_pydantic_schema(self):
        evaluation = graph_retriever._EvaluacionCondiciones(evaluaciones=[
            graph_retriever._EvaluacionCondicion(indice=0, aplica=False, motivo="No aplica"),
        ])
        structured = Mock(ainvoke=AsyncMock(return_value=evaluation))
        adapter = Mock(with_structured_output=Mock(return_value=structured))
        with patch("proyecto_tecnico.config.MODEL_CONFIGURATION", SETTINGS), \
             patch("proyecto_tecnico.model_adapter.create_chat_model", return_value=adapter) as factory:
            result = await graph_retriever._evaluar_condiciones(["Si cambia el motor"], "M1", "Cambio de suspensión", "")
        self.assertEqual(result, [False])
        self.assertEqual(factory.call_args.args[0], SETTINGS.reasoning)
        adapter.with_structured_output.assert_called_once_with(graph_retriever._EvaluacionCondiciones)

    async def test_validator_moves_to_reasoning_without_touching_embeddings(self):
        doc = Document(
            page_content="CR 2.1: Motor\nInformación adicional: Revisar otras reformas si procede",
            metadata={"via_tramitacion": "A"},
        )
        adapter = Mock(invoke=Mock(return_value=AIMessage(content='{"crs_adicionales": []}')))
        with patch.object(validador_crs, "MODEL_CONFIGURATION", SETTINGS), \
             patch.object(validador_crs, "_get_coleccion"), \
             patch.object(validador_crs, "_recuperar_ficha_cr", return_value=doc), \
             patch("proyecto_tecnico.model_adapter.create_chat_model", return_value=adapter) as factory:
            result = await validador_crs.validar_crs(["2.1"], "Modificación del motor")
        self.assertTrue(result.valido)
        self.assertEqual(result.crs_incluidos[0].cr, "2.1")
        self.assertEqual(factory.call_args.args[0], SETTINGS.reasoning)
        adapter.invoke.assert_called_once()
