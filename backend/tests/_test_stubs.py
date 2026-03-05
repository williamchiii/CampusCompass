"""Small fake classes used by unit tests.

These stubs let us test backend logic without real third-party packages.
"""

import importlib
import string
import sys
import types
from uuid import uuid4


class FakeObjectId(str):
    """Small ObjectId stand-in that validates 24-char hex strings."""

    def __new__(cls, value=None):
        if value is None:
            value = uuid4().hex[:24]
        if not isinstance(value, str):
            raise TypeError("ObjectId must be a string")
        value = value.lower()
        if len(value) != 24 or any(ch not in string.hexdigits.lower() for ch in value):
            raise ValueError("Invalid ObjectId")
        return str.__new__(cls, value)


class FakeCursor(list):
    def sort(self, key, direction):
        reverse = direction == -1
        super().sort(key=lambda item: item.get(key), reverse=reverse)
        return self


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeUpdateResult:
    def __init__(self, modified_count, matched_count=0):
        self.modified_count = modified_count
        self.matched_count = matched_count


class FakeDeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.indexes = []

    def create_index(self, fields):
        self.indexes.append(tuple(fields))

    def _matches(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict):
                candidate = doc.get(key)
                if "$gte" in value and candidate < value["$gte"]:
                    return False
                if "$lte" in value and candidate > value["$lte"]:
                    return False
                continue

            if str(doc.get(key)) != str(value):
                return False
        return True

    def insert_one(self, doc):
        stored = dict(doc)
        stored.setdefault("_id", FakeObjectId())
        self.docs.append(stored)
        return FakeInsertResult(stored["_id"])

    def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query):
        return FakeCursor([dict(doc) for doc in self.docs if self._matches(doc, query)])

    def update_one(self, query, update):
        for doc in self.docs:
            if self._matches(doc, query):
                before = dict(doc)
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                modified = int(doc != before)
                return FakeUpdateResult(modified_count=modified, matched_count=1)
        return FakeUpdateResult(modified_count=0, matched_count=0)

    def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[index]
                return FakeDeleteResult(deleted_count=1)
        return FakeDeleteResult(deleted_count=0)


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class FakeMongoClient:
    def __init__(self):
        self.databases = {}

    def __getitem__(self, db_name):
        if db_name not in self.databases:
            self.databases[db_name] = FakeDatabase()
        return self.databases[db_name]


def install_calendar_manager_import_stubs():
    """Install fake pymongo/bson modules before importing calendar_manager."""
    pymongo_module = types.ModuleType("pymongo")
    pymongo_module.MongoClient = FakeMongoClient

    pymongo_errors = types.ModuleType("pymongo.errors")
    class PyMongoError(Exception):
        pass
    pymongo_errors.PyMongoError = PyMongoError
    pymongo_module.errors = pymongo_errors

    bson_module = types.ModuleType("bson")
    bson_objectid = types.ModuleType("bson.objectid")
    bson_objectid.ObjectId = FakeObjectId
    bson_module.objectid = bson_objectid

    sys.modules["pymongo"] = pymongo_module
    sys.modules["pymongo.errors"] = pymongo_errors
    sys.modules["bson"] = bson_module
    sys.modules["bson.objectid"] = bson_objectid


def install_ics_stub():
    """Install a tiny fake ics module with Calendar + Event objects."""
    ics_module = types.ModuleType("ics")

    class FakeIcsEvent:
        def __init__(self, name, location):
            self.name = name
            self.location = location

    class FakeIcsCalendar:
        def __init__(self, content):
            self.events = []
            for line in content.splitlines():
                clean = line.strip()
                if not clean:
                    continue
                event_name, _, location = clean.partition("|")
                normalized_location = location.strip() if location else None
                if normalized_location == "None":
                    normalized_location = None
                self.events.append(FakeIcsEvent(event_name.strip(), normalized_location))

    ics_module.Calendar = FakeIcsCalendar
    sys.modules["ics"] = ics_module


def install_db_helpers_import_stubs(ping_raises=False):
    """Install fake dotenv and pymongo modules for db_helpers tests."""
    state = {"dotenv_loaded": False, "clients": []}

    dotenv_module = types.ModuleType("dotenv")

    def load_dotenv():
        state["dotenv_loaded"] = True

    dotenv_module.load_dotenv = load_dotenv

    pymongo_mongo_client = types.ModuleType("pymongo.mongo_client")

    class StubMongoClient:
        def __init__(self, uri, server_api=None):
            self.uri = uri
            self.server_api = server_api
            self.closed = False
            state["clients"].append(self)

        @property
        def admin(self):
            return self

        def command(self, command_name):
            if ping_raises:
                raise RuntimeError("ping failed")
            return {"ok": 1, "command": command_name}

        def close(self):
            self.closed = True

    pymongo_mongo_client.MongoClient = StubMongoClient

    pymongo_server_api = types.ModuleType("pymongo.server_api")

    class ServerApi:
        def __init__(self, version):
            self.version = version

    pymongo_server_api.ServerApi = ServerApi

    sys.modules["dotenv"] = dotenv_module
    sys.modules["pymongo.mongo_client"] = pymongo_mongo_client
    sys.modules["pymongo.server_api"] = pymongo_server_api

    return state


def import_fresh(module_name):
    """Import a module after removing any previous copy from sys.modules."""
    if module_name in sys.modules:
        del sys.modules[module_name]
    return importlib.import_module(module_name)
