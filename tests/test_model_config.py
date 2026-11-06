"""Selección y validación de configuración; sin SDKs ni llamadas a proveedores."""

import unittest

from proyecto_tecnico.model_config import load_model_configuration


class ModelConfigurationTests(unittest.TestCase):
    def test_existing_configuration_keeps_openai_defaults(self):
        settings = load_model_configuration({})
        self.assertEqual((settings.reasoning.provider, settings.reasoning.model), ("openai", "gpt-4o"))
        self.assertEqual((settings.writing.provider, settings.writing.model), ("openai", "gpt-4o-mini"))
        self.assertEqual(settings.embedding_model, "text-embedding-3-small")

    def test_roles_can_select_different_providers(self):
        settings = load_model_configuration({
            "PROVEEDOR_RAZONAMIENTO": " BEDROCK ",
            "MODELO_RAZONAMIENTO": " eu.example-model ",
            "MODELO_REDACCION": "another-openai-model",
        })
        self.assertEqual((settings.reasoning.provider, settings.reasoning.model), ("bedrock", "eu.example-model"))
        self.assertEqual((settings.writing.provider, settings.writing.model), ("openai", "another-openai-model"))

    def test_unknown_provider_fails_instead_of_using_openai(self):
        for role in ("RAZONAMIENTO", "REDACCION"):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, f"PROVEEDOR_{role}"):
                load_model_configuration({f"PROVEEDOR_{role}": "bedrok"})

    def test_bedrock_requires_explicit_model_for_each_role(self):
        for role in ("RAZONAMIENTO", "REDACCION"):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, f"MODELO_{role}"):
                load_model_configuration({f"PROVEEDOR_{role}": "bedrock"})

    def test_empty_model_is_invalid(self):
        for key in ("MODELO_RAZONAMIENTO", "MODELO_REDACCION", "MODELO_EMBEDDING"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                load_model_configuration({key: "  "})

    def test_aws_region_precedence(self):
        self.assertEqual(load_model_configuration({}).aws_region, "eu-west-1")
        self.assertEqual(load_model_configuration({"AWS_DEFAULT_REGION": "eu-central-1"}).aws_region, "eu-central-1")
        self.assertEqual(load_model_configuration({
            "AWS_REGION": "eu-west-1", "AWS_DEFAULT_REGION": "eu-central-1",
        }).aws_region, "eu-west-1")
        with self.assertRaisesRegex(ValueError, "AWS_REGION"):
            load_model_configuration({"AWS_REGION": ""})

    def test_bedrock_does_not_change_embedding_model(self):
        settings = load_model_configuration({
            "PROVEEDOR_RAZONAMIENTO": "bedrock", "MODELO_RAZONAMIENTO": "some-bedrock-id",
            "PROVEEDOR_REDACCION": "bedrock", "MODELO_REDACCION": "another-bedrock-id",
        })
        self.assertEqual(settings.embedding_model, "text-embedding-3-small")


if __name__ == "__main__":
    unittest.main()
