"""Simple task and taskbar tests."""

import unittest
from datetime import datetime, timezone

from backend.taskbar import Task, Taskbar


class TaskModelTests(unittest.TestCase):
    def test_task_to_dict_serializes_dates(self):
        due_date = datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc)
        task = Task(title="Submit lab", due_date=due_date)

        payload = task.to_dict()

        self.assertEqual(payload["title"], "Submit lab")
        self.assertEqual(payload["due_date"], due_date.isoformat())
        self.assertFalse(payload["completed"])
        self.assertIn("created_at", payload)

    def test_task_to_dict_handles_missing_due_date(self):
        task = Task(title="Read notes")
        payload = task.to_dict()
        self.assertIsNone(payload["due_date"])


class TaskbarTests(unittest.TestCase):
    def setUp(self):
        self.taskbar = Taskbar()

    def test_add_task_stores_task_and_returns_id(self):
        task_id = self.taskbar.add_task("Study for exam", priority="high")

        self.assertIn(task_id, self.taskbar.tasks)
        self.assertEqual(self.taskbar.tasks[task_id].priority, "high")

    def test_edit_task_updates_multiple_fields(self):
        task_id = self.taskbar.add_task("Old title", description="Old desc")
        update = {"title": "New title", "description": "New desc", "priority": "low"}

        success = self.taskbar.edit_task(task_id, update)

        self.assertTrue(success)
        edited = self.taskbar.tasks[task_id]
        self.assertEqual(edited.title, "New title")
        self.assertEqual(edited.description, "New desc")
        self.assertEqual(edited.priority, "low")

    def test_edit_task_returns_false_for_missing_task(self):
        self.assertFalse(self.taskbar.edit_task("missing", {"title": "x"}))

    def test_remove_task_deletes_task(self):
        task_id = self.taskbar.add_task("Delete me")

        self.assertTrue(self.taskbar.remove_task(task_id))
        self.assertFalse(self.taskbar.remove_task(task_id))

    def test_list_tasks_returns_serialized_dicts(self):
        self.taskbar.add_task("Task 1")
        self.taskbar.add_task("Task 2", priority="high")

        tasks = self.taskbar.list_tasks()

        self.assertEqual(len(tasks), 2)
        self.assertTrue(all("id" in task for task in tasks))
        self.assertEqual({task["title"] for task in tasks}, {"Task 1", "Task 2"})

    def test_mark_task_completed_sets_completed_flag(self):
        task_id = self.taskbar.add_task("Complete me")

        success = self.taskbar.mark_task_completed(task_id)

        self.assertTrue(success)
        self.assertTrue(self.taskbar.tasks[task_id].completed)

    def test_mark_task_completed_returns_false_for_missing_task(self):
        self.assertFalse(self.taskbar.mark_task_completed("missing"))


if __name__ == "__main__":
    unittest.main()
