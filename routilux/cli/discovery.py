# routilux/cli/discovery.py
"""Routine auto-discovery system for scanning and registering routines."""

import importlib.util
import logging
import sys
import warnings
from pathlib import Path
from typing import List, Optional, Union

from routilux.tools.factory.factory import ObjectFactory

logger = logging.getLogger(__name__)


class RoutineDiscovery:
    """Discovers and registers routines from Python files."""

    def __init__(self, factory: Optional[ObjectFactory] = None):
        """Initialize discovery system.

        Args:
            factory: ObjectFactory instance. Uses global singleton if None.
        """
        self.factory = factory or ObjectFactory.get_instance()
        self._registered_routines = set()

    def scan_directory(self, directory: Path) -> List[Path]:
        """Scan directory for Python files.

        Args:
            directory: Directory path to scan

        Returns:
            List of Python file paths found

        Raises:
            ValueError: If directory doesn't exist
        """
        if not directory.exists():
            raise ValueError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        return list(directory.rglob("*.py"))

    def load_module(self, file_path: Path) -> Optional[object]:
        """Load a Python module from file path.

        Args:
            file_path: Path to Python file

        Returns:
            Module object or None if loading failed
        """
        try:
            # Create unique module name based on file path
            module_name = f"routilux_discovery_{file_path.stem}_{id(file_path)}"

            # Load module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for {file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            spec.loader.exec_module(module)
            return module

        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")
            return None

    def discover_from_directory(
        self,
        directory: Path,
        on_error: str = "warn"
    ) -> int:
        """Discover and register routines from a directory.

        Args:
            directory: Directory to scan
            on_error: Error handling strategy - "warn", "raise", or "ignore"

        Returns:
            Number of routines registered

        Raises:
            ValueError: If on_error="raise" and discovery fails
        """
        count = 0
        files = self.scan_directory(directory)

        for file_path in files:
            try:
                module = self.load_module(file_path)
                if module is not None:
                    # The module's decorators should have registered routines
                    count += 1
            except Exception as e:
                if on_error == "raise":
                    raise ValueError(f"Failed to discover from {file_path}: {e}") from e
                elif on_error == "warn":
                    warnings.warn(f"Skipping {file_path}: {e}")
                # else: ignore

        return count


def discover_routines(
    directories: List[Path],
    factory: Optional[ObjectFactory] = None,
    on_error: str = "warn"
) -> ObjectFactory:
    """Discover and register routines from multiple directories.

    Args:
        directories: List of directory paths to scan
        factory: ObjectFactory instance. Uses global singleton if None.
        on_error: Error handling strategy

    Returns:
        The ObjectFactory instance

    Raises:
        ValueError: If directories are invalid or discovery fails
    """
    discovery = RoutineDiscovery(factory)

    for directory in directories:
        directory = Path(directory)
        try:
            discovery.discover_from_directory(directory, on_error=on_error)
        except ValueError as e:
            if on_error == "raise":
                raise
            warnings.warn(str(e))

    return discovery.factory


def get_default_routines_dirs() -> List[Path]:
    """Get default routines directories.

    Returns:
        List of default directory paths
    """
    dirs = []

    # Project-local directory
    local_dir = Path.cwd() / "routines"
    if local_dir.exists():
        dirs.append(local_dir)

    # User-global directory
    from pathlib import Path
    home = Path.home()
    global_dir = home / ".routilux" / "routines"
    if global_dir.exists():
        dirs.append(global_dir)

    return dirs
