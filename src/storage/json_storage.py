import json
import os
import portalocker
from typing import Optional
from src.models.schemas import SessionState

class JSONStorage:
    def __init__(self, base_dir: str = "output"):
        self.base_dir = base_dir
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        self.sessions_file = os.path.join(base_dir, "sessions.json")
        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, "w") as f:
                json.dump({}, f)

    def save_session(self, session: SessionState):
        session_dir = os.path.join(self.base_dir, session.session_id)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
        
        # Сохранение индивидуального состояния сессии
        session_file = os.path.join(session_dir, "state.json")
        with open(session_file, "w") as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            f.write(session.model_dump_json(indent=4))
            portalocker.unlock(f)

        # Обновление общего индекса сессий
        with open(self.sessions_file, "r+") as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            data = json.load(f)
            data[session.session_id] = session_dir
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()
            portalocker.unlock(f)

    def get_session(self, session_id: str) -> Optional[SessionState]:
        session_file = os.path.join(self.base_dir, session_id, "state.json")
        if not os.path.exists(session_file):
            return None
        with open(session_file, "r") as f:
            portalocker.lock(f, portalocker.LOCK_SH)
            data = json.load(f)
            portalocker.unlock(f)
            return SessionState(**data)
