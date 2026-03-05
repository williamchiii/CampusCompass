"""Simple tests for parsing schedule files."""

import tempfile
import unittest
from pathlib import Path

from backend.tests._test_stubs import import_fresh, install_ics_stub


install_ics_stub()
uf_schedule = import_fresh("backend.uf_schedule")


class UfScheduleTests(unittest.TestCase):
    def _write_temp_schedule(self, content):
        # We write fake "event|location" lines.
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".ics", delete=False, encoding="utf-8")
        handle.write(content)
        handle.close()
        return Path(handle.name)

    def test_process_ics_file_maps_known_building_code(self):
        path = self._write_temp_schedule("Physics|PHY 100\n")
        try:
            result = uf_schedule.process_ics_file(str(path))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(result[0]["event"], "Physics")
        self.assertEqual(result[0]["location_code"], "PHY")
        self.assertIn("campusmap.ufl.edu", result[0]["location_url"])

    def test_process_ics_file_handles_unknown_building_code(self):
        path = self._write_temp_schedule("Unknown|ZZZ 999\nNoLocation|None\n")
        try:
            result = uf_schedule.process_ics_file(str(path))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(result[0]["location_code"], "ZZZ")
        self.assertEqual(result[0]["location_url"], "No URL found for this location code")
        self.assertEqual(result[1]["location_code"], "")


if __name__ == "__main__":
    unittest.main()
