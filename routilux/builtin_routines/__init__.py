"""
Routilux built-in routines.

This package contains commonly used routines that are generic and reusable
across different business domains. Routines are organized by category:

- text_processing: Text manipulation and formatting routines
- utils: General utility routines
- data_processing: Data transformation and validation routines
- control_flow: Flow control and routing routines

All routines inherit from Routine which provides common utilities like
_extract_input_data() and _track_operation().
"""

from routilux.builtin_routines.control_flow import (
    ConditionalRouter,
)
from routilux.builtin_routines.data_processing import (
    DataTransformer,
    DataValidator,
)
from routilux.builtin_routines.text_processing import (
    ResultExtractor,
    TextClipper,
    TextRenderer,
)
from routilux.builtin_routines.utils import (
    DataFlattener,
    TimeProvider,
)

__all__ = [
    # Text processing
    "TextClipper",
    "TextRenderer",
    "ResultExtractor",
    # Utils
    "TimeProvider",
    "DataFlattener",
    # Data processing
    "DataTransformer",
    "DataValidator",
    # Control flow
    "ConditionalRouter",
]
