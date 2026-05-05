import pytest
import os
import shutil
from src.storage.json_storage import JSONStorage
from src.models.schemas import SessionState, GenerationRequest

@pytest.fixture
def temp_storage():
    test_dir = "tests/temp_output"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    storage = JSONStorage(base_dir=test_dir)
    yield storage
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

def test_save_and_get_session(temp_storage):
    req = GenerationRequest(topic="тест")
    session = SessionState(request=req)
    
    temp_storage.save_session(session)
    loaded = temp_storage.get_session(session.session_id)
    
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.request.topic == "тест"
