"""Simple tests for the in-memory calendar manager."""

import unittest
from datetime import datetime, timezone

from backend.campus_calendar import InMemoryCalendarManager


def dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class InMemoryCalendarManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = InMemoryCalendarManager()
        self.user_id = "user-1"

    def _event_data(self, **overrides):
        base = {
            "title": "CS Lecture",
            "start_time": dt(2026, 3, 2, 9, 0).isoformat(),
            "end_time": dt(2026, 3, 2, 10, 0).isoformat(),
            "event_type": "class",
        }
        base.update(overrides)
        return base

    def test_create_event_success(self):
        result = self.manager.create_event(self.user_id, self._event_data())
        self.assertTrue(result["success"])
        self.assertIn("event_id", result)

        event = self.manager.get_event(result["event_id"], self.user_id)
        self.assertEqual(event["title"], "CS Lecture")
        self.assertEqual(event["color"], "#3498db")

    def test_create_event_missing_required_field(self):
        result = self.manager.create_event(self.user_id, {"title": "Missing fields"})
        self.assertFalse(result["success"])
        self.assertIn("Missing field", result["error"])

    def test_create_event_rejects_invalid_datetime(self):
        result = self.manager.create_event(
            self.user_id,
            self._event_data(start_time="not-a-date"),
        )
        self.assertFalse(result["success"])
        self.assertIn("Invalid datetime format", result["error"])

    def test_create_event_rejects_invalid_time_order(self):
        result = self.manager.create_event(
            self.user_id,
            self._event_data(
                start_time=dt(2026, 3, 2, 11, 0).isoformat(),
                end_time=dt(2026, 3, 2, 10, 0).isoformat(),
            ),
        )
        self.assertFalse(result["success"])
        self.assertIn("Start time must be before end time", result["error"])

    def test_create_event_rejects_conflicts(self):
        first = self.manager.create_event(self.user_id, self._event_data())
        self.assertTrue(first["success"])

        second = self.manager.create_event(
            self.user_id,
            self._event_data(
                title="Conflicting Event",
                start_time=dt(2026, 3, 2, 9, 30).isoformat(),
                end_time=dt(2026, 3, 2, 10, 30).isoformat(),
            ),
        )
        self.assertFalse(second["success"])
        self.assertIn("conflicts", second["error"])

    def test_get_user_events_with_date_filters(self):
        self.manager.create_event(self.user_id, self._event_data())
        self.manager.create_event(
            self.user_id,
            self._event_data(
                title="Evening Study",
                start_time=dt(2026, 3, 2, 18, 0).isoformat(),
                end_time=dt(2026, 3, 2, 19, 0).isoformat(),
            ),
        )

        filtered = self.manager.get_user_events(
            self.user_id,
            start=dt(2026, 3, 2, 12, 0),
            end=dt(2026, 3, 2, 20, 0),
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Evening Study")

    def test_update_event_modifies_existing_event(self):
        result = self.manager.create_event(self.user_id, self._event_data())
        event_id = result["event_id"]

        update_result = self.manager.update_event(event_id, self.user_id, {"title": "Updated"})
        updated_event = self.manager.get_event(event_id, self.user_id)

        self.assertTrue(update_result["success"])
        self.assertEqual(updated_event["title"], "Updated")

    def test_update_event_returns_not_found(self):
        result = self.manager.update_event("missing", self.user_id, {"title": "x"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Event not found")

    def test_delete_event_removes_event(self):
        created = self.manager.create_event(self.user_id, self._event_data())
        event_id = created["event_id"]

        deleted = self.manager.delete_event(event_id, self.user_id)
        missing = self.manager.delete_event(event_id, self.user_id)

        self.assertTrue(deleted["success"])
        self.assertFalse(missing["success"])

    def test_find_free_slots_returns_expected_gaps(self):
        self.manager.create_event(self.user_id, self._event_data())
        self.manager.create_event(
            self.user_id,
            self._event_data(
                title="Lab",
                start_time=dt(2026, 3, 2, 13, 0).isoformat(),
                end_time=dt(2026, 3, 2, 14, 0).isoformat(),
            ),
        )

        result = self.manager.find_free_slots(
            self.user_id,
            start=dt(2026, 3, 2, 8, 0),
            end=dt(2026, 3, 2, 15, 0),
            min_duration=30,
        )
        slots = result["free_slots"]

        self.assertTrue(result["success"])
        self.assertEqual(len(slots), 3)
        self.assertEqual(slots[0]["start"], dt(2026, 3, 2, 8, 0).isoformat())
        self.assertEqual(slots[0]["end"], dt(2026, 3, 2, 9, 0).isoformat())

    def test_find_free_slots_respects_min_duration(self):
        self.manager.create_event(
            self.user_id,
            self._event_data(
                start_time=dt(2026, 3, 2, 9, 45).isoformat(),
                end_time=dt(2026, 3, 2, 10, 0).isoformat(),
            ),
        )

        result = self.manager.find_free_slots(
            self.user_id,
            start=dt(2026, 3, 2, 9, 0),
            end=dt(2026, 3, 2, 10, 0),
            min_duration=60,
        )

        self.assertEqual(result["free_slots"], [])

    def test_get_statistics_counts_event_types(self):
        self.manager.create_event(self.user_id, self._event_data(event_type="class"))
        self.manager.create_event(
            self.user_id,
            self._event_data(
                title="Team meeting",
                event_type="meeting",
                start_time=dt(2026, 3, 2, 11, 0).isoformat(),
                end_time=dt(2026, 3, 2, 12, 0).isoformat(),
            ),
        )

        stats = self.manager.get_statistics(
            self.user_id, dt(2026, 3, 1), dt(2026, 3, 3)
        )

        self.assertTrue(stats["success"])
        self.assertEqual(stats["statistics"]["class"], 1)
        self.assertEqual(stats["statistics"]["meeting"], 1)

    def test_load_user_calendar_check_availability(self):
        created = self.manager.create_event(self.user_id, self._event_data())
        self.assertTrue(created["success"])

        calendar = self.manager.load_user_calendar(self.user_id)

        self.assertFalse(
            calendar.check_availability(
                dt(2026, 3, 2, 9, 15),
                dt(2026, 3, 2, 9, 45),
            )
        )
        self.assertTrue(
            calendar.check_availability(
                dt(2026, 3, 2, 10, 15),
                dt(2026, 3, 2, 11, 0),
            )
        )


if __name__ == "__main__":
    unittest.main()
