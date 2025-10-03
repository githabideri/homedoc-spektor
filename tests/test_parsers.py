import pathlib
import unittest

from spektor.sysprobe import _parse_lscpu, _parse_meminfo, _parse_os_release

DATA_DIR = pathlib.Path(__file__).parent / "data"


class ParserTests(unittest.TestCase):
    def test_os_release(self):
        data = _parse_os_release(str(DATA_DIR / "os-release"))
        self.assertEqual(data["name"], "Debian GNU/Linux")
        self.assertEqual(data["version"], "12")
        self.assertEqual(data["id"], "debian")
        self.assertIn("bookworm", data["pretty_name"])

    def test_lscpu(self):
        sample = (DATA_DIR / "lscpu.json").read_text(encoding="utf-8")
        parsed = _parse_lscpu(sample)
        self.assertEqual(parsed["Model name"], "Test CPU")
        self.assertEqual(parsed["Vendor ID"], "GenuineIntel")
        self.assertEqual(parsed["CPU(s)"], "8")
        self.assertIn("fpu", parsed["Flags"])

    def test_meminfo(self):
        sample = (DATA_DIR / "meminfo").read_text(encoding="utf-8")
        parsed = _parse_meminfo(sample)
        self.assertEqual(parsed["MemTotal"], 16332088 * 1024)
        self.assertEqual(parsed["SwapTotal"], 2097148 * 1024)


if __name__ == "__main__":
    unittest.main()
