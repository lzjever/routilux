"""
DSL (Domain Specific Language) module for Routilux.

Provides declarative workflow definition via YAML and JSON/dict formats.
"""

from routilux.dsl.loader import load_flow_from_spec
from routilux.dsl.spec_parser import parse_spec

__all__ = ["load_flow_from_spec", "parse_spec"]

