from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4


class InMemoryCalendarManager:
    """Simple in-memory calendar manager used as a fallback when MongoDB isn't available.

    Implements the minimal API used by the FastAPI endpoints in `main.py`:
    - create_event(user_id, event_dict)
    - get_event(event_id, user_id)
    - get_user_events(user_id, start, end)
    - update_event(event_id, user_id, update_dict)
    - delete_event(event_id, user_id, ...)
    - find_free_slots(user_id, start, end, min_duration)
    - get_statistics(user_id, start, end)
    - load_user_calendar(user_id)
    """

    def __init__(self):
        self.store: Dict[str, List[Dict]] = {}

    def _now_utc(self):
        return datetime.now(timezone.utc)

    def create_event(self, user_id: str, event_data: Dict) -> Dict:
        required = ['title', 'start_time', 'end_time', 'event_type']
        for field in required:
            if field not in event_data:
                return {'success': False, 'error': f"Missing field: {field}"}

        # Parse ISO strings
        try:
            start = datetime.fromisoformat(event_data['start_time'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(event_data['end_time'].replace('Z', '+00:00'))
        except Exception as e:
            return {'success': False, 'error': f'Invalid datetime format: {e}'}

        if start >= end:
            return {'success': False, 'error': 'Start time must be before end time'}

        # Conflict check
        user_events = self.store.setdefault(user_id, [])
        for ev in user_events:
            ev_start = datetime.fromisoformat(ev['start_time'].replace('Z', '+00:00'))
            ev_end = datetime.fromisoformat(ev['end_time'].replace('Z', '+00:00'))
            if not (end <= ev_start or start >= ev_end):
                return {'success': False, 'error': 'Time slot conflicts with existing event'}

        event_id = str(uuid4())
        doc = {
            '_id': event_id,
            'user_id': user_id,
            'title': event_data['title'],
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'event_type': event_data.get('event_type', ''),
            'location': event_data.get('location'),
            'description': event_data.get('description'),
            'color': event_data.get('color', '#3498db'),
            'recurrence': event_data.get('recurrence', 'none'),
            'recurrence_end_date': event_data.get('recurrence_end_date'),
            'reminders': event_data.get('reminders', [15, 60]),
            'created_at': self._now_utc().isoformat()
        }

        user_events.append(doc)
        return {'success': True, 'event_id': event_id}

    def get_event(self, event_id: str, user_id: str) -> Optional[Dict]:
        for ev in self.store.get(user_id, []):
            if ev.get('_id') == event_id:
                return ev
        return None

    def get_user_events(self, user_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[Dict]:
        events = []
        for ev in self.store.get(user_id, []):
            events.append(ev)
        # naive filtering by iso strings if requested
        if start or end:
            filtered = []
            for ev in events:
                ev_start = datetime.fromisoformat(ev['start_time'].replace('Z', '+00:00'))
                ev_end = datetime.fromisoformat(ev['end_time'].replace('Z', '+00:00'))
                if start and ev_end < start:
                    continue
                if end and ev_start > end:
                    continue
                filtered.append(ev)
            return filtered
        return events

    def update_event(self, event_id: str, user_id: str, update_data: Dict) -> Dict:
        ev = self.get_event(event_id, user_id)
        if not ev:
            return {'success': False, 'error': 'Event not found'}
        ev.update(update_data)
        return {'success': True}

    def delete_event(self, event_id: str, user_id: str, delete_future: bool = False, from_date: Optional[datetime] = None) -> Dict:
        events = self.store.get(user_id, [])
        for i, ev in enumerate(events):
            if ev.get('_id') == event_id:
                del events[i]
                return {'success': True}
        return {'success': False, 'error': 'Event not found'}

    def find_free_slots(self, user_id: str, start: datetime, end: datetime, min_duration: int = 30) -> Dict:
        # Very simple free-slot finder: returns the gaps between sorted events
        events = self.get_user_events(user_id)
        parsed = []
        for ev in events:
            parsed.append((datetime.fromisoformat(ev['start_time'].replace('Z', '+00:00')),
                           datetime.fromisoformat(ev['end_time'].replace('Z', '+00:00'))))
        parsed.sort()
        slots = []
        cursor = start
        for s, e in parsed:
            if s > cursor and (s - cursor).total_seconds() / 60 >= min_duration:
                slots.append((cursor.isoformat(), s.isoformat()))
            cursor = max(cursor, e)
        if end > cursor and (end - cursor).total_seconds() / 60 >= min_duration:
            slots.append((cursor.isoformat(), end.isoformat()))
        return {'success': True, 'free_slots': [{'start': a, 'end': b} for a, b in slots]}

    def get_statistics(self, user_id: str, start: datetime, end: datetime) -> Dict:
        # Minimal stub: return counts by event_type
        events = self.get_user_events(user_id, start, end)
        counts = {}
        for ev in events:
            et = ev.get('event_type', 'other')
            counts[et] = counts.get(et, 0) + 1
        return {'success': True, 'statistics': counts}

    def load_user_calendar(self, user_id: str):
        # Not needed by fallback paths in current endpoints; return a simple object with check_availability
        class SimpleCalendar:
            def __init__(self, events):
                self.events = events

            def check_availability(self, start, end):
                for ev in self.events:
                    ev_start = datetime.fromisoformat(ev['start_time'].replace('Z', '+00:00'))
                    ev_end = datetime.fromisoformat(ev['end_time'].replace('Z', '+00:00'))
                    if not (end <= ev_start or start >= ev_end):
                        return False
                return True

        return SimpleCalendar(self.get_user_events(user_id))
