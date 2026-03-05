"""Beginner-friendly tests for db_helpers.py."""

import os
import unittest

from backend.tests._test_stubs import import_fresh, install_db_helpers_import_stubs


def load_db_helpers(ping_raises=False):
    """Load backend.db_helpers with stubbed third-party imports."""
    state = install_db_helpers_import_stubs(ping_raises=ping_raises)
    module = import_fresh("backend.db_helpers")
    return module, state


class DbHelpersTests(unittest.TestCase):
    def test_load_env_variables_calls_dotenv_and_returns_uri(self):
        module, state = load_db_helpers()
        os.environ["MONGODB_URI"] = "mongodb://example"
        try:
            value = module.loadEnvVariables()
        finally:
            os.environ.pop("MONGODB_URI", None)

        self.assertTrue(state["dotenv_loaded"])
        self.assertEqual(value, "mongodb://example")

    def test_create_mongo_client_rejects_missing_uri(self):
        module, _ = load_db_helpers()
        with self.assertRaises(ValueError):
            module.createMongoClient("")

    def test_create_mongo_client_success(self):
        module, state = load_db_helpers()
        client = module.createMongoClient("mongodb://ok")
        self.assertEqual(client.uri, "mongodb://ok")
        self.assertEqual(client.server_api.version, "1")
        self.assertEqual(len(state["clients"]), 1)

    def test_create_mongo_client_closes_and_raises_on_ping_failure(self):
        module, state = load_db_helpers(ping_raises=True)
        with self.assertRaises(RuntimeError):
            module.createMongoClient("mongodb://fails")

        self.assertTrue(state["clients"][0].closed)


if __name__ == "__main__":
    unittest.main()
