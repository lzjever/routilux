"""
Routilux Tools - Utility modules for workflow development.

This package contains:
- factory: Object factory for creating Flow and Routine from templates
- dsl: Domain-specific language support (YAML/JSON workflow definitions)
- analysis: Workflow and routine analyzers
- testing: Testing utilities for routines

Example:
    >>> from routilux.tools.factory import ObjectFactory
    >>> from routilux.tools.dsl import load_flow_from_spec
    >>> from routilux.tools.testing import RoutineTester
"""

# Factory
# DSL
from routilux.tools.dsl import load_flow_from_spec, parse_spec
from routilux.tools.factory import ObjectFactory, ObjectMetadata

# Testing
from routilux.tools.testing import RoutineTester

# Analysis (optional - may have extra dependencies)
try:
    from routilux.tools.analysis import (
        D2Exporter,
        MarkdownExporter,
        RoutineAnalyzer,
        WorkflowAnalyzer,
    )

    _analysis_available = True
except ImportError:
    _analysis_available = False

__all__ = [
    # Factory
    "ObjectFactory",
    "ObjectMetadata",
    # DSL
    "load_flow_from_spec",
    "parse_spec",
    # Testing
    "RoutineTester",
]

# Add analysis exports if available
if _analysis_available:
    __all__.extend(
        [
            "RoutineAnalyzer",
            "WorkflowAnalyzer",
            "MarkdownExporter",
            "D2Exporter",
        ]
    )
