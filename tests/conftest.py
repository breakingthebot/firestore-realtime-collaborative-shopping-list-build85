"""
Pytest test fixtures for Build 85.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.engine.firestore_client import reset_firestore_engine, get_firestore_engine


@pytest.fixture(autouse=True)
def clean_database():
    """
    Reset Firestore engine storage before and after each test.
    """
    reset_firestore_engine()
    yield
    reset_firestore_engine()


@pytest.fixture
def client():
    """
    HTTP test client fixture.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def engine():
    """
    Direct access to active Firestore engine.
    """
    return get_firestore_engine()
