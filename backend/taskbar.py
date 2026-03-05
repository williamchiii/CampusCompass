"""
Taskbar Module for CampusCompass Backend

This module provides a fully functional taskbar system with the following features:
- Add a task
- Edit a task
- Change the priority of a task
- Remove a task
- List all tasks
- Mark a task as completed

Architecture:
  - Task: Data class for individual tasks
  - Taskbar: In-memory task management logic

Usage:
  taskbar = Taskbar()
  task_id = taskbar.add_task(task_data)
  taskbar.edit_task(task_id, updated_data)
  taskbar.list_tasks()
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import uuid

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Task:
    """
    Represents a task in the taskbar.

    Attributes:
        title: Task name
        id: Unique task identifier
        description: Additional details (optional)
        priority: Priority level (low, medium, high)
        due_date: When the task is due (optional)
        completed: Whether the task is completed
        created_at: When the task was created
    """
    title: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: Optional[str] = None
    priority: str = "medium"  # Default priority
    due_date: Optional[datetime] = None
    completed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        """Convert task to dictionary for JSON/DB storage."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'priority': self.priority,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'completed': self.completed,
            'created_at': self.created_at.isoformat()
        }

# ============================================================================
# Taskbar Logic (In-Memory)
# ============================================================================

class Taskbar:
    """
    In-memory taskbar for managing tasks.

    Features:
    - Add, edit, remove tasks
    - Change task priority
    - Mark tasks as completed
    - List all tasks
    """

    def __init__(self):
        """Initialize the taskbar."""
        self.tasks: Dict[str, Task] = {}

    def add_task(self, title: str, description: Optional[str] = None, priority: str = "medium", due_date: Optional[datetime] = None) -> str:
        """Add a new task to the taskbar."""
        task = Task(title=title, description=description, priority=priority, due_date=due_date)
        self.tasks[task.id] = task
        return task.id

    def edit_task(self, task_id: str, updated_data: Dict) -> bool:
        """Edit an existing task."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if 'title' in updated_data:
            task.title = updated_data['title']
        if 'description' in updated_data:
            task.description = updated_data['description']
        if 'priority' in updated_data:
            task.priority = updated_data['priority']
        if 'due_date' in updated_data:
            task.due_date = updated_data['due_date']
        if 'completed' in updated_data:
            task.completed = updated_data['completed']

        return True

    def remove_task(self, task_id: str) -> bool:
        """Remove a task from the taskbar."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

    def list_tasks(self) -> List[Dict]:
        """List all tasks in the taskbar."""
        return [task.to_dict() for task in self.tasks.values()]

    def mark_task_completed(self, task_id: str) -> bool:
        """Mark a task as completed."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        task.completed = True
        return True

# Example usage:
# taskbar = Taskbar()
# task_id = taskbar.add_task("Finish project", "Complete the backend module", "high", datetime(2025, 12, 10))
# taskbar.edit_task(task_id, {"priority": "medium"})
# taskbar.mark_task_completed(task_id)
# print(taskbar.list_tasks())
