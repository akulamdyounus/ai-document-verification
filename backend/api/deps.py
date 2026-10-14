from backend.models.database import get_db

# Re-export get_db for route dependencies
__all__ = ["get_db"]
