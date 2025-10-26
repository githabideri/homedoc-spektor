import unittest

from spektor.cli import create_parser, default_namespace
from spektor.llm import DEFAULT_BASE_URL, DEFAULT_MODEL
from spektor.util import DEFAULT_TIMEOUT


class CliDefaultsTests(unittest.TestCase):
    def test_default_namespace_matches_constants(self) -> None:
        defaults = default_namespace()
        self.assertEqual(defaults.timeout, DEFAULT_TIMEOUT)
        self.assertEqual(defaults.model, DEFAULT_MODEL)
        self.assertEqual(defaults.server, DEFAULT_BASE_URL)

    def test_create_parser_collect_defaults(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--collect"])
        self.assertTrue(args.collect)
        self.assertFalse(args.report)
        self.assertEqual(args.timeout, DEFAULT_TIMEOUT)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
