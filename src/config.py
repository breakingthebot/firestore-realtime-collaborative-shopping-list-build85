"""
Configuration settings and Firestore collection paths.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()


class Settings:
    """
    Application and Firestore runtime configuration.
    """

    # Server configuration
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # Firestore configuration
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "local-shopping-list-project")
    FIRESTORE_DATABASE: str = os.getenv("FIRESTORE_DATABASE", "(default)")
    FIRESTORE_EMULATOR_HOST: str = os.getenv("FIRESTORE_EMULATOR_HOST", "").strip()
    USE_EMBEDDED_ENGINE: bool = os.getenv("USE_EMBEDDED_ENGINE", "true").lower() in ("true", "1", "yes")

    # Conflict resolution strategy: LAST_WRITE_WINS or REVISION_CHECK
    SYNC_CONFLICT_STRATEGY: str = os.getenv("SYNC_CONFLICT_STRATEGY", "LAST_WRITE_WINS")
    WS_HEARTBEAT_INTERVAL_SEC: int = int(os.getenv("WS_HEARTBEAT_INTERVAL_SEC", "30"))

    # Collection Names & Subcollection Paths
    COLLECTION_LISTS: str = "shopping_lists"
    SUBCOLLECTION_ITEMS: str = "items"
    SUBCOLLECTION_ACTIVITY: str = "activity"


settings = Settings()
