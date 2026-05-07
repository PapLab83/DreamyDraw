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
            with open(self.sessions_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _clean_surrogates(self, obj):
        if isinstance(obj, str):
            return obj.encode('utf-8', 'replace').decode('utf-8')
        elif isinstance(obj, dict):
            return {k: self._clean_surrogates(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_surrogates(i) for i in obj]
        return obj

    def save_session(self, session: SessionState):
        session_dir = os.path.join(self.base_dir, session.session_id)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
        
        session_file = os.path.join(session_dir, "state.json")
        data = session.model_dump()
        data = self._clean_surrogates(data)
        
        with open(session_file, "w", encoding="utf-8", errors="replace") as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            json.dump(data, f, indent=4, ensure_ascii=False)
            portalocker.unlock(f)

        if os.path.exists(self.sessions_file):
            with open(self.sessions_file, "r+", encoding="utf-8", errors="replace") as f:
                portalocker.lock(f, portalocker.LOCK_EX)
                try:
                    index_data = json.load(f)
                except:
                    index_data = {}
                index_data[session.session_id] = session_dir
                f.seek(0)
                json.dump(index_data, f, indent=4, ensure_ascii=False)
                f.truncate()
                portalocker.unlock(f)

    def get_session(self, session_id: str) -> Optional[SessionState]:
        session_file = os.path.join(self.base_dir, session_id, "state.json")
        if not os.path.exists(session_file):
            return None
        with open(session_file, "r", encoding="utf-8", errors="replace") as f:
            portalocker.lock(f, portalocker.LOCK_SH)
            data = json.load(f)
            portalocker.unlock(f)
            return SessionState(**data)
