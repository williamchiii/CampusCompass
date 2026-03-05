import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests
from calendar_manager import CalendarManager
from db_helpers import createMongoClient, loadEnvVariables
from campus_calendar import InMemoryCalendarManager
from taskbar import Taskbar
from uf_schedule import building_code_to_url
from pymongo import MongoClient

# Load environment variables
load_dotenv()

class Calendar(BaseModel):
    name: str

class Calendars(BaseModel):
    calendars: List[Calendar]

class GoogleAuthRequest(BaseModel):
    token: str

class AuthResponse(BaseModel):
    user_email: str
    user_name: str
    user_id: str

# Taskbar/Todo Models
class TaskCreate(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"  # low, medium, high
    due_date: Optional[str] = None  # ISO format

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    completed: Optional[bool] = None

class TaskResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str]
    priority: str
    due_date: Optional[str]
    completed: bool
    created_at: str

# Calendar Event Models
class EventCreate(BaseModel):
    user_id: str
    title: str
    start_time: str  # ISO format datetime string
    end_time: str    # ISO format datetime string
    event_type: str
    location: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = "#3498db"
    recurrence: Optional[str] = "none"
    recurrence_end_date: Optional[str] = None
    reminders: Optional[List[int]] = [15, 60]

class EventUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_type: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    recurrence: Optional[str] = None
    recurrence_end_date: Optional[str] = None
    reminders: Optional[List[int]] = None

class EventResponse(BaseModel):
    id: str
    user_id: str
    title: str
    start_time: str
    end_time: str
    event_type: str
    location: Optional[str] = None
    description: Optional[str] = None
    color: str
    recurrence: str
    recurrence_end_date: Optional[str] = None
    reminders: List[int]
    duration_minutes: Optional[int] = None

app = FastAPI()

# Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

# Initialize MongoDB and CalendarManager
mongo_client: Optional[MongoClient] = None
calendar_manager: Optional[CalendarManager] = None

# In-memory taskbars for each user (could be backed by MongoDB later)
user_taskbars: Dict[str, Taskbar] = {}

@app.on_event("startup")
async def startup_event():
    global mongo_client, calendar_manager
    try:
        uri = loadEnvVariables()
        mongo_client = createMongoClient(uri)
        calendar_manager = CalendarManager(mongo_client)
        print("CalendarManager initialized successfully")
    except Exception as e:
        print(f"Warning: Failed to initialize MongoDB/CalendarManager: {e}")
        print("Falling back to in-memory calendar manager (no persistence).")
        # Use an in-memory fallback so the app remains functional for adding events during local dev
        try:
            calendar_manager = InMemoryCalendarManager()
            print("In-memory CalendarManager initialized successfully")
        except Exception as e2:
            print(f"Failed to initialize in-memory calendar manager: {e2}")
            print("Calendar features will not be available")

@app.on_event("shutdown")
async def shutdown_event():
    global mongo_client
    if mongo_client:
        mongo_client.close()
        print("MongoDB connection closed")

origins = [
    "http://localhost:3000",
    "http://localhost:5173"  # Vite default port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

memory_db = {"calendars":[]}

@app.post("/api/auth/google", response_model=AuthResponse)
async def google_auth(auth_request: GoogleAuthRequest):
    try:
        # Verify the Google token
        idinfo = id_token.verify_oauth2_token(
            auth_request.token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        # Token is valid, extract user information
        user_email = idinfo.get("email")
        user_name = idinfo.get("name")
        user_id = idinfo.get("sub")

        # Optional: Restrict to UFL emails only
        # if not user_email.endswith("@ufl.edu"):
        #     raise HTTPException(status_code=403, detail="Only UFL email addresses are allowed")

        # Here you can also save/update user in your database
        # e.g., save user_id, user_email, user_name to MongoDB

        return AuthResponse(
            user_email=user_email,
            user_name=user_name,
            user_id=user_id
        )

    except ValueError as e:
        # Invalid token
        raise HTTPException(status_code=401, detail=f"Invalid authentication credentials: {str(e)}")

@app.get("/calendars", response_model=Calendars)
def get_calendars():
    # return the in-memory calendars list in the response model shape
    return {"calendars": memory_db["calendars"]}

@app.post("/calendars", response_model=Calendar)
def add_calendar(calendar: Calendar):
    memory_db["calendars"].append(calendar)
    return calendar

# Calendar API Endpoints
@app.get("/api/calendar/events")
async def get_events(
    user_id: str = Query(..., description="User ID"),
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)")
):
    """Get events for a user, optionally filtered by date range."""
    if not calendar_manager:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    
    try:
        start_dt = None
        if start:
            start_clean = start.replace('Z', '+00:00') if 'Z' in start else start
            start_dt = datetime.fromisoformat(start_clean)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt = None
        if end:
            end_clean = end.replace('Z', '+00:00') if 'Z' in end else end
            end_dt = datetime.fromisoformat(end_clean)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        
        events = calendar_manager.get_user_events(user_id, start_dt, end_dt)
        
        # Transform MongoDB documents to match API response format
        formatted_events = []
        for event in events:
            formatted_event = {
                'id': event.get('_id', ''),
                'user_id': event.get('user_id', ''),
                'title': event.get('title', ''),
                'start_time': event['start_time'].isoformat() if isinstance(event.get('start_time'), datetime) else str(event.get('start_time', '')),
                'end_time': event['end_time'].isoformat() if isinstance(event.get('end_time'), datetime) else str(event.get('end_time', '')),
                'event_type': event.get('event_type', ''),
                'location': event.get('location'),
                'description': event.get('description'),
                'color': event.get('color', '#3498db'),
                'recurrence': event.get('recurrence', 'none'),
                'recurrence_end_date': event['recurrence_end_date'].isoformat() if event.get('recurrence_end_date') and isinstance(event['recurrence_end_date'], datetime) else (event.get('recurrence_end_date') if event.get('recurrence_end_date') else None),
                'reminders': event.get('reminders', [15, 60])
            }
            formatted_events.append(formatted_event)
        
        return formatted_events
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching events: {str(e)}")

@app.post("/api/calendar/events")
async def create_event(event_data: EventCreate):
    """Create a new calendar event."""
    if not calendar_manager:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    
    try:
        event_dict = event_data.dict()
        result = calendar_manager.create_event(event_data.user_id, event_dict)
        
        if result['success']:
            # Fetch and return the created event
            event = calendar_manager.get_event(result['event_id'], event_data.user_id)
            if event:
                # Format the event the same way as get_events
                formatted_event = {
                    'id': event.get('_id', ''),
                    'user_id': event.get('user_id', ''),
                    'title': event.get('title', ''),
                    'start_time': event['start_time'].isoformat() if isinstance(event.get('start_time'), datetime) else str(event.get('start_time', '')),
                    'end_time': event['end_time'].isoformat() if isinstance(event.get('end_time'), datetime) else str(event.get('end_time', '')),
                    'event_type': event.get('event_type', ''),
                    'location': event.get('location'),
                    'description': event.get('description'),
                    'color': event.get('color', '#3498db'),
                    'recurrence': event.get('recurrence', 'none'),
                    'recurrence_end_date': event['recurrence_end_date'].isoformat() if event.get('recurrence_end_date') and isinstance(event['recurrence_end_date'], datetime) else (event.get('recurrence_end_date') if event.get('recurrence_end_date') else None),
                    'reminders': event.get('reminders', [15, 60])
                }
                return formatted_event
            return {"success": True, "event_id": result['event_id']}
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to create event'))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating event: {str(e)}")

@app.put("/api/calendar/events/{event_id}")
async def update_event(event_id: str, event_data: EventUpdate, user_id: str = Query(..., description="User ID")):
    """Update an existing calendar event."""
    if not calendar_manager:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    
    try:
        # Only include fields that are provided (not None)
        update_dict = {k: v for k, v in event_data.dict().items() if v is not None}
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = calendar_manager.update_event(event_id, user_id, update_dict)
        
        if result['success']:
            return {"success": True}
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to update event'))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating event: {str(e)}")

@app.delete("/api/calendar/events/{event_id}")
async def delete_event(
    event_id: str,
    user_id: str = Query(..., description="User ID"),
    delete_future: bool = Query(False, description="If true, delete this event and future occurrences (for recurring events)"),
    from_date: Optional[str] = Query(None, description="ISO datetime to begin deleting future occurrences from; defaults to now")
):
    """Delete a calendar event."""
    if not calendar_manager:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    
    try:
        # Support deleting only future occurrences for recurring events
        parsed_from = None
        if delete_future:
            if from_date:
                # normalize ISO string
                from_clean = from_date.replace('Z', '+00:00') if 'Z' in from_date else from_date
                parsed_from = datetime.fromisoformat(from_clean)
                if parsed_from.tzinfo is None:
                    parsed_from = parsed_from.replace(tzinfo=timezone.utc)
            else:
                parsed_from = datetime.now(timezone.utc)

        result = calendar_manager.delete_event(event_id, user_id, delete_future=delete_future, from_date=parsed_from)
        
        if result['success']:
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail="Event not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting event: {str(e)}")

@app.get("/api/calendar/free-slots")
async def get_free_slots(
    user_id: str = Query(..., description="User ID"),
    start: str = Query(..., description="Start date (ISO format)"),
    end: str = Query(..., description="End date (ISO format)"),
    min_duration: int = Query(30, description="Minimum duration in minutes")
):
    """Find free time slots for a user in a date range."""
    if not calendar_manager:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    
    try:
        start_clean = start.replace('Z', '+00:00') if 'Z' in start else start
        end_clean = end.replace('Z', '+00:00') if 'Z' in end else end
        start_dt = datetime.fromisoformat(start_clean)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_clean)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        
        result = calendar_manager.find_free_slots(user_id, start_dt, end_dt, min_duration)
        
        if result['success']:
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to find free slots'))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding free slots: {str(e)}")

@app.get("/api/calendar/statistics")
async def get_statistics(
    user_id: str = Query(..., description="User ID"),
    start: str = Query(..., description="Start date (ISO format)"),
    end: str = Query(..., description="End date (ISO format)")
):
    """Get event statistics for a user in a date range."""
    if not calendar_manager:
        raise HTTPException(status_code=503, detail="Calendar service unavailable")
    
    try:
        start_clean = start.replace('Z', '+00:00') if 'Z' in start else start
        end_clean = end.replace('Z', '+00:00') if 'Z' in end else end
        start_dt = datetime.fromisoformat(start_clean)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_clean)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        
        result = calendar_manager.get_statistics(user_id, start_dt, end_dt)
        
        if result['success']:
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to get statistics'))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")

# ============================================================================
# Taskbar/Todo Endpoints
# ============================================================================

@app.post("/api/tasks")
async def create_task(task_data: TaskCreate):
    """Create a new task."""
    try:
        user_id = task_data.user_id
        if user_id not in user_taskbars:
            user_taskbars[user_id] = Taskbar()

        taskbar = user_taskbars[user_id]
        due_date = None
        if task_data.due_date:
            due_date = datetime.fromisoformat(task_data.due_date.replace('Z', '+00:00'))

        task_id = taskbar.add_task(
            title=task_data.title,
            description=task_data.description,
            priority=task_data.priority,
            due_date=due_date
        )

        task = taskbar.tasks[task_id]
        return TaskResponse(
            id=task.id,
            user_id=user_id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            due_date=task.due_date.isoformat() if task.due_date else None,
            completed=task.completed,
            created_at=task.created_at.isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating task: {str(e)}")

@app.get("/api/tasks")
async def get_tasks(user_id: str = Query(..., description="User ID")):
    """Get all tasks for a user."""
    try:
        if user_id not in user_taskbars:
            user_taskbars[user_id] = Taskbar()

        taskbar = user_taskbars[user_id]
        tasks = taskbar.list_tasks()

        result = []
        for task_dict in tasks:
            result.append(TaskResponse(
                id=task_dict['id'],
                user_id=user_id,
                title=task_dict['title'],
                description=task_dict['description'],
                priority=task_dict['priority'],
                due_date=task_dict['due_date'],
                completed=task_dict['completed'],
                created_at=task_dict['created_at']
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tasks: {str(e)}")

@app.put("/api/tasks/{task_id}")
async def update_task(task_id: str, user_id: str = Query(..., description="User ID"), task_data: TaskUpdate = None):
    """Update a task."""
    try:
        if user_id not in user_taskbars:
            raise HTTPException(status_code=404, detail="User not found")

        taskbar = user_taskbars[user_id]
        update_dict = {}

        if task_data and task_data.title is not None:
            update_dict['title'] = task_data.title
        if task_data and task_data.description is not None:
            update_dict['description'] = task_data.description
        if task_data and task_data.priority is not None:
            update_dict['priority'] = task_data.priority
        if task_data and task_data.due_date is not None:
            update_dict['due_date'] = datetime.fromisoformat(task_data.due_date.replace('Z', '+00:00'))
        if task_data and task_data.completed is not None:
            update_dict['completed'] = task_data.completed

        success = taskbar.edit_task(task_id, update_dict)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")

        task = taskbar.tasks[task_id]
        return TaskResponse(
            id=task.id,
            user_id=user_id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            due_date=task.due_date.isoformat() if task.due_date else None,
            completed=task.completed,
            created_at=task.created_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating task: {str(e)}")

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, user_id: str = Query(..., description="User ID")):
    """Delete a task."""
    try:
        if user_id not in user_taskbars:
            raise HTTPException(status_code=404, detail="User not found")

        taskbar = user_taskbars[user_id]
        success = taskbar.remove_task(task_id)

        if not success:
            raise HTTPException(status_code=404, detail="Task not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting task: {str(e)}")

@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, user_id: str = Query(..., description="User ID")):
    """Mark a task as completed."""
    try:
        if user_id not in user_taskbars:
            raise HTTPException(status_code=404, detail="User not found")

        taskbar = user_taskbars[user_id]
        success = taskbar.mark_task_completed(task_id)

        if not success:
            raise HTTPException(status_code=404, detail="Task not found")

        task = taskbar.tasks[task_id]
        return TaskResponse(
            id=task.id,
            user_id=user_id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            due_date=task.due_date.isoformat() if task.due_date else None,
            completed=task.completed,
            created_at=task.created_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error completing task: {str(e)}")

# ============================================================================
# Campus Map Endpoint
# ============================================================================

@app.get("/api/campus-map")
async def get_campus_map():
    """Get the main UF campus map URL."""
    return {"map_url": "https://campusmap.ufl.edu/"}

@app.get("/api/campus-map/building/{building_code}")
async def get_building_map(building_code: str):
    """Get the campus map URL for a specific building code."""
    building_code_upper = building_code.upper()
    if building_code_upper not in building_code_to_url:
        raise HTTPException(status_code=404, detail=f"Building code '{building_code}' not found")
    return {"map_url": building_code_to_url[building_code_upper]}

if __name__ == "__main__":
    uvicorn.run(app, host = "0.0.0.0", port = 8000)

#http://localhost:8000/docs
#http://localhost:8000/calendars