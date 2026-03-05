"""Beginner-friendly tests for calendar_manager.py."""

import unittest
from datetime import datetime, timedelta, timezone

from backend.tests._test_stubs import (
    FakeMongoClient,
    FakeObjectId,
    import_fresh,
    install_calendar_manager_import_stubs,
)


def utc(year, month, day, hour=0, minute=0):
    """Create a UTC datetime quickly."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# calendar_manager imports pymongo/bson at module import time,
# so we install stubs first.
install_calendar_manager_import_stubs()
calendar_manager_module = import_fresh("backend.calendar_manager")
Calendar = calendar_manager_module.Calendar
CalendarEvent = calendar_manager_module.CalendarEvent
CalendarManager = calendar_manager_module.CalendarManager


class AlwaysBusyCalendar:
    def check_availability(self, _start, _end):
        return False


class AlwaysFreeCalendar:
    def check_availability(self, _start, _end):
        return True


class OneHourFreeSlotCalendar:
    def find_free_slots(self, start, _end, _min_duration):
        return [(start, start + timedelta(hours=1))]


class FixedStatsCalendar:
    def get_statistics(self, _start, _end):
        return {"total_events": 7}


class CalendarEventTests(unittest.TestCase):
    def test_event_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            CalendarEvent(
                id="bad",
                user_id="u1",
                title="Bad Event",
                start_time=utc(2026, 3, 1, 10),
                end_time=utc(2026, 3, 1, 9),
                event_type="class",
            )

    def test_event_defaults_and_to_dict(self):
        event = CalendarEvent(
            id="e1",
            user_id="u1",
            title="Lecture",
            start_time=utc(2026, 3, 1, 9),
            end_time=utc(2026, 3, 1, 10),
            event_type="class",
        )

        event_dict = event.to_dict()

        self.assertEqual(event.reminders, [15, 60])
        self.assertEqual(event.duration_minutes(), 60)
        self.assertEqual(event_dict["title"], "Lecture")
        self.assertEqual(event_dict["duration_minutes"], 60)


class CalendarLogicTests(unittest.TestCase):
    def setUp(self):
        self.calendar = Calendar("u1")

    def make_event(self, event_id="e1", recurrence="none", recurrence_end_date=None, **overrides):
        payload = {
            "id": event_id,
            "user_id": "u1",
            "title": "Event",
            "start_time": utc(2026, 3, 1, 9),
            "end_time": utc(2026, 3, 1, 10),
            "event_type": "class",
            "recurrence": recurrence,
            "recurrence_end_date": recurrence_end_date,
        }
        payload.update(overrides)
        return CalendarEvent(**payload)

    def test_expand_none_recurrence(self):
        event = self.make_event()

        inside = self.calendar.expand_recurring_event(event, utc(2026, 3, 1, 8), utc(2026, 3, 1, 11))
        outside = self.calendar.expand_recurring_event(event, utc(2026, 3, 2, 8), utc(2026, 3, 2, 11))

        self.assertEqual(len(inside), 1)
        self.assertEqual(outside, [])

    def test_expand_daily_until_end_date(self):
        event = self.make_event(
            recurrence="daily",
            recurrence_end_date=utc(2026, 3, 4, 9),
        )

        instances = self.calendar.expand_recurring_event(
            event,
            utc(2026, 3, 1, 0),
            utc(2026, 3, 10, 0),
        )

        self.assertEqual(len(instances), 3)

    def test_expand_monthly_handles_december_to_january(self):
        event = self.make_event(
            start_time=utc(2025, 12, 15, 9),
            end_time=utc(2025, 12, 15, 10),
            recurrence="monthly",
            recurrence_end_date=utc(2026, 3, 1, 0),
        )

        instances = self.calendar.expand_recurring_event(
            event,
            utc(2025, 12, 1, 0),
            utc(2026, 3, 2, 0),
        )

        self.assertEqual([instance[0].month for instance in instances], [12, 1, 2])

    def test_get_events_for_range_returns_sorted(self):
        self.calendar.add_event(self.make_event(event_id="late", start_time=utc(2026, 3, 1, 14), end_time=utc(2026, 3, 1, 15)))
        self.calendar.add_event(self.make_event(event_id="early", start_time=utc(2026, 3, 1, 10), end_time=utc(2026, 3, 1, 11)))

        events = self.calendar.get_events_for_range(utc(2026, 3, 1, 0), utc(2026, 3, 2, 0))
        self.assertEqual([event[2].id for event in events], ["early", "late"])

    def test_check_availability(self):
        self.calendar.add_event(self.make_event())

        self.assertFalse(self.calendar.check_availability(utc(2026, 3, 1, 8, 30), utc(2026, 3, 1, 9, 30)))
        self.assertTrue(self.calendar.check_availability(utc(2026, 3, 1, 10, 0), utc(2026, 3, 1, 10, 30)))

    def test_find_free_slots_and_first_available(self):
        self.calendar.add_event(self.make_event(start_time=utc(2026, 3, 1, 9), end_time=utc(2026, 3, 1, 10)))

        slots = self.calendar.find_free_slots(
            start_date=utc(2026, 3, 1, 0),
            end_date=utc(2026, 3, 2, 0),
            min_duration=30,
        )
        first = self.calendar.find_first_available_slot(
            duration_minutes=45,
            start=utc(2026, 3, 1, 0),
            end=utc(2026, 3, 2, 0),
        )

        self.assertGreaterEqual(len(slots), 2)
        self.assertEqual(first[0].hour, 8)
        self.assertEqual((first[1] - first[0]).total_seconds() / 60, 45)

    def test_get_statistics_empty_and_non_empty(self):
        empty_stats = self.calendar.get_statistics(utc(2026, 3, 1), utc(2026, 3, 2))
        self.assertEqual(empty_stats["total_events"], 0)

        self.calendar.add_event(self.make_event(event_type="meeting"))
        populated = self.calendar.get_statistics(utc(2026, 3, 1), utc(2026, 3, 2))
        self.assertEqual(populated["total_events"], 1)
        self.assertEqual(populated["events_by_type"]["meeting"], 1)


class CalendarManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = CalendarManager(FakeMongoClient())

    def make_event_data(self, **overrides):
        payload = {
            "title": "Exam Review",
            "start_time": utc(2026, 3, 3, 11).isoformat(),
            "end_time": utc(2026, 3, 3, 12).isoformat(),
            "event_type": "meeting",
            "recurrence": "none",
        }
        payload.update(overrides)
        return payload

    def insert_event_directly(self, user_id="u1", **overrides):
        doc = {
            "_id": FakeObjectId(),
            "user_id": user_id,
            "title": "Stored Event",
            "start_time": utc(2026, 3, 5, 9),
            "end_time": utc(2026, 3, 5, 10),
            "event_type": "class",
            "recurrence": "none",
            "reminders": [15, 60],
        }
        doc.update(overrides)
        self.manager.collection.insert_one(doc)
        return str(doc["_id"])

    def test_parse_datetime_formats_and_errors(self):
        iso_value = CalendarManager._parse_datetime("2026-03-01T09:00:00Z")
        short_value = CalendarManager._parse_datetime("2026-03-01")
        us_value = CalendarManager._parse_datetime("03/01/2026 09:00:00")

        self.assertEqual(iso_value.tzinfo, timezone.utc)
        self.assertEqual(short_value.hour, 0)
        self.assertEqual(us_value.minute, 0)

        with self.assertRaises(ValueError):
            CalendarManager._parse_datetime("not-a-date")
        with self.assertRaises(TypeError):
            CalendarManager._parse_datetime(12345)

    def test_create_event_validates_required_fields(self):
        result = self.manager.create_event("u1", {"title": "Missing fields"})
        self.assertFalse(result["success"])
        self.assertIn("Missing field", result["error"])

    def test_create_event_rejects_invalid_time_order(self):
        result = self.manager.create_event(
            "u1",
            self.make_event_data(
                start_time=utc(2026, 3, 3, 13).isoformat(),
                end_time=utc(2026, 3, 3, 12).isoformat(),
            ),
        )
        self.assertFalse(result["success"])
        self.assertIn("Start time must be before end time", result["error"])

    def test_create_event_conflict_and_success_paths(self):
        self.manager.load_user_calendar = lambda _user_id: AlwaysBusyCalendar()
        conflict_result = self.manager.create_event("u1", self.make_event_data(recurrence="none"))
        self.assertFalse(conflict_result["success"])

        self.manager.load_user_calendar = lambda _user_id: AlwaysFreeCalendar()
        success_result = self.manager.create_event("u1", self.make_event_data())
        self.assertTrue(success_result["success"])
        self.assertEqual(len(self.manager.collection.docs), 1)

    def test_get_event_with_valid_and_invalid_ids(self):
        self.assertIsNone(self.manager.get_event("bad-id", "u1"))

        event_id = self.insert_event_directly(user_id="u1")
        found = self.manager.get_event(event_id, "u1")
        self.assertEqual(found["_id"], event_id)

    def test_get_user_events_filters_by_date_range(self):
        self.insert_event_directly(user_id="u1", start_time=utc(2026, 3, 5, 9), end_time=utc(2026, 3, 5, 10))
        self.insert_event_directly(user_id="u1", start_time=utc(2026, 3, 8, 9), end_time=utc(2026, 3, 8, 10))

        events = self.manager.get_user_events(
            "u1",
            start=utc(2026, 3, 4, 0),
            end=utc(2026, 3, 6, 23),
        )
        self.assertEqual(len(events), 1)

    def test_update_event_not_found_and_success(self):
        missing = self.manager.update_event(str(FakeObjectId()), "u1", {"title": "new"})
        self.assertFalse(missing["success"])
        self.assertEqual(missing["error"], "Event not found")

        event_id = self.insert_event_directly(user_id="u1")
        self.manager.load_user_calendar = lambda _user_id: Calendar("u1")
        updated = self.manager.update_event(event_id, "u1", {"title": "Renamed"})
        event = self.manager.get_event(event_id, "u1")
        self.assertTrue(updated["success"])
        self.assertEqual(event["title"], "Renamed")

    def test_delete_event_default_delete_future_and_truncate(self):
        normal_id = self.insert_event_directly(user_id="u1")
        deleted = self.manager.delete_event(normal_id, "u1")
        self.assertTrue(deleted["success"])
        self.assertFalse(self.manager.delete_event(normal_id, "u1")["success"])

        non_recurring_id = self.insert_event_directly(user_id="u1", recurrence="none")
        delete_future = self.manager.delete_event(
            non_recurring_id,
            "u1",
            delete_future=True,
            from_date=utc(2026, 3, 6, 0),
        )
        self.assertTrue(delete_future["success"])
        self.assertIsNone(self.manager.get_event(non_recurring_id, "u1"))

        recurring_id = self.insert_event_directly(
            user_id="u1",
            recurrence="weekly",
            start_time=utc(2026, 3, 1, 9),
            end_time=utc(2026, 3, 1, 10),
            recurrence_end_date=None,
        )
        from_date = utc(2026, 3, 20, 9)
        truncate = self.manager.delete_event(
            recurring_id,
            "u1",
            delete_future=True,
            from_date=from_date,
        )
        updated = self.manager.get_event(recurring_id, "u1")
        self.assertTrue(truncate["success"])
        self.assertEqual(updated["recurrence_end_date"], from_date - timedelta(microseconds=1))

    def test_load_user_calendar_skips_invalid_rows(self):
        valid_id = self.insert_event_directly(user_id="u1")
        self.manager.collection.insert_one(
            {
                "_id": FakeObjectId(),
                "user_id": "u1",
                "title": "Broken Row",
                "start_time": utc(2026, 3, 6, 9),
                "end_time": utc(2026, 3, 6, 10),
                # Missing event_type on purpose.
            }
        )

        calendar = self.manager.load_user_calendar("u1")

        self.assertIn(valid_id, calendar.events)
        self.assertEqual(len(calendar.events), 1)

    def test_find_free_slots_and_statistics_wrappers(self):
        self.manager.load_user_calendar = lambda _user_id: OneHourFreeSlotCalendar()
        free_slot_result = self.manager.find_free_slots("u1", utc(2026, 3, 1), utc(2026, 3, 2), 30)
        self.assertTrue(free_slot_result["success"])
        self.assertEqual(len(free_slot_result["free_slots"]), 1)

        self.manager.load_user_calendar = lambda _user_id: FixedStatsCalendar()
        stats_result = self.manager.get_statistics("u1", utc(2026, 3, 1), utc(2026, 3, 2))
        self.assertTrue(stats_result["success"])
        self.assertEqual(stats_result["statistics"]["total_events"], 7)


if __name__ == "__main__":
    unittest.main()
