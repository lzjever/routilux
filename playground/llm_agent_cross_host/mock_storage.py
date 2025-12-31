"""
Mock Cloud Storage Service for demonstration purposes.

This module simulates a cloud storage service (like S3, Redis, or a database).
In a real implementation, this would connect to actual cloud storage.
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class MockCloudStorage:
    """Mock cloud storage that uses local file system for simulation."""
    
    def __init__(self, base_path: str = "/tmp/routilux_playground_storage"):
        """Initialize mock cloud storage.
        
        Args:
            base_path: Base directory for storing files (simulates cloud storage).
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._storage: Dict[str, Dict[str, Any]] = {}
    
    def put(self, key: str, data: Dict[str, Any]) -> None:
        """Store data in cloud storage.
        
        Args:
            key: Storage key (e.g., "execution_state/job_123").
            data: Data dictionary to store.
        """
        # Store in memory
        self._storage[key] = data.copy()
        
        # Also save to file for persistence
        file_path = self.base_path / f"{key.replace('/', '_')}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        
        print(f"📦 [Storage] Saved to: {key} (file: {file_path})")
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve data from cloud storage.
        
        Args:
            key: Storage key.
        
        Returns:
            Data dictionary if found, None otherwise.
        """
        # Try memory first
        if key in self._storage:
            print(f"📦 [Storage] Loaded from memory: {key}")
            return self._storage[key].copy()
        
        # Try file
        file_path = self.base_path / f"{key.replace('/', '_')}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"📦 [Storage] Loaded from file: {key} (file: {file_path})")
            return data
        
        print(f"📦 [Storage] Key not found: {key}")
        return None
    
    def delete(self, key: str) -> bool:
        """Delete data from cloud storage.
        
        Args:
            key: Storage key.
        
        Returns:
            True if deleted, False if not found.
        """
        deleted = False
        
        # Delete from memory
        if key in self._storage:
            del self._storage[key]
            deleted = True
        
        # Delete file
        file_path = self.base_path / f"{key.replace('/', '_')}.json"
        if file_path.exists():
            file_path.unlink()
            deleted = True
        
        if deleted:
            print(f"📦 [Storage] Deleted: {key}")
        
        return deleted
    
    def list_keys(self, prefix: str = "") -> list:
        """List all keys with optional prefix.
        
        Args:
            prefix: Optional prefix to filter keys.
        
        Returns:
            List of keys.
        """
        keys = list(self._storage.keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return sorted(keys)
    
    def exists(self, key: str) -> bool:
        """Check if key exists.
        
        Args:
            key: Storage key.
        
        Returns:
            True if exists, False otherwise.
        """
        if key in self._storage:
            return True
        
        file_path = self.base_path / f"{key.replace('/', '_')}.json"
        return file_path.exists()


# Global instance for easy access
_storage = None


def get_storage() -> MockCloudStorage:
    """Get or create the global storage instance."""
    global _storage
    if _storage is None:
        _storage = MockCloudStorage()
    return _storage


def set_storage(storage: MockCloudStorage) -> None:
    """Set the global storage instance."""
    global _storage
    _storage = storage

