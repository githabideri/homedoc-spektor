import unittest

from spektor.llm import DEFAULT_BASE_URL, DEFAULT_PORT, OllamaClient


class OllamaClientTests(unittest.TestCase):
    def test_client_preserves_default_base_url(self) -> None:
        client = OllamaClient()
        self.assertEqual(client.base_url, DEFAULT_BASE_URL.rstrip('/'))

    def test_client_appends_default_port_for_scheme_without_port(self) -> None:
        client = OllamaClient(base_url="http://example.com")
        self.assertEqual(client.base_url, f"http://example.com:{DEFAULT_PORT}")

    def test_client_normalises_host_without_scheme(self) -> None:
        client = OllamaClient(base_url="example.com")
        self.assertEqual(client.base_url, f"http://example.com:{DEFAULT_PORT}")


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
