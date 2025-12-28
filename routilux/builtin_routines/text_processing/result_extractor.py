"""
Result extractor routine.

Extracts and formats results from various output formats with extensible architecture.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Union, Tuple, Callable, Protocol
import json
import re
import logging
from routilux.routine import Routine


logger = logging.getLogger(__name__)


class ExtractorProtocol(Protocol):
    """Protocol for custom extractors."""

    def extract(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract data from input.

        Args:
            data: Input data to extract from.
            config: Configuration dictionary.

        Returns:
            Tuple of (extracted_result, format_type, metadata) if successful,
            None otherwise.
        """
        ...


class ResultExtractor(Routine):
    """Routine for extracting results from structured output.

    This routine provides a flexible, extensible system for extracting structured
    data from various formats. It supports multiple extraction strategies and
    allows custom extractors to be registered.

    Features:
        - Multiple built-in extractors (JSON, YAML, XML, CSV, code blocks)
        - Extensible architecture with custom extractor support
        - Chain-based extraction with fallback mechanisms
        - Intelligent type detection and conversion
        - Comprehensive error handling and reporting
        - Rich metadata about extraction process

    Extraction Strategies:
        - "auto": Try all extractors in order until one succeeds
        - "priority": Try extractors in priority order
        - "all": Extract using all applicable extractors
        - "first_match": Return first successful extraction

    Examples:
        >>> extractor = ResultExtractor()
        >>> extractor.set_config(strategy="auto")
        >>> extractor.input_slot.receive({"data": '```json\\n{"key": "value"}\\n```'})
        >>> # Register custom extractor
        >>> def my_extractor(data, config):
        ...     if isinstance(data, str) and data.startswith("CUSTOM:"):
        ...         return data[7:], "custom", {"method": "prefix"}
        ...     return None
        >>> extractor.register_extractor("custom", my_extractor)
    """

    def __init__(self):
        """Initialize ResultExtractor routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            # Extraction strategy
            strategy="auto",  # "auto", "priority", "all", "first_match"
            extractor_priority=[],  # Custom priority order for extractors
            # Built-in extractor settings
            extract_json_blocks=True,
            extract_code_blocks=True,
            extract_yaml_blocks=False,  # Requires pyyaml
            extract_xml_blocks=False,
            code_block_languages=["json", "python", "output", "yaml", "xml"],
            # Format-specific settings
            format_interpreter_output=True,
            parse_json_strings=True,  # Try to parse JSON from plain strings
            parse_yaml_strings=False,  # Try to parse YAML from plain strings
            detect_nested_structures=True,
            # Error handling
            continue_on_error=True,  # Continue trying other extractors on error
            return_original_on_failure=True,  # Return original data if all extractors fail
            log_errors=True,
        )

        # Register built-in extractors
        self._register_builtin_extractors()

        # Define input slot
        self.input_slot = self.define_slot("input", handler=self._handle_input)

        # Define output event
        self.output_event = self.define_event(
            "output", ["extracted_result", "format", "metadata", "confidence", "extraction_path"]
        )

    def _register_builtin_extractors(self):
        """Register built-in extractor functions."""
        if not hasattr(self, "_extractors"):
            self._extractors: Dict[str, Callable] = {}

        # Specialized extractors (higher priority)
        # Interpreter output extractor (should check before generic list)
        self._extractors["interpreter_output"] = self._format_interpreter_output

        # JSON extractors
        self._extractors["json_code_block"] = self._extract_json_code_block
        self._extractors["json_string"] = self._extract_json_string

        # Code block extractors
        self._extractors["code_block"] = self._extract_code_block

        # YAML extractors (if available)
        # Note: yaml is imported conditionally in the methods themselves
        try:
            import yaml  # noqa: F401

            # Only register if yaml is available
            self._extractors["yaml_code_block"] = self._extract_yaml_code_block
            self._extractors["yaml_string"] = self._extract_yaml_string
        except ImportError:
            pass

        # XML extractors
        self._extractors["xml_code_block"] = self._extract_xml_code_block

        # Type-based extractors (lower priority, fallback)
        self._extractors["dict_extractor"] = self._extract_dict
        self._extractors["list_extractor"] = self._extract_list

    def _handle_input(self, data: Union[str, List, Dict] = None, **kwargs):
        """Handle input data and extract results.

        Args:
            data: Data to extract results from. Can be:
                - String with code blocks or structured data
                - List of output dictionaries
                - Dictionary with structured data
            **kwargs: Additional data from slot. If 'data' is not provided,
                will use kwargs or the first value.
        """
        # Extract data using Routine helper method
        data = self._extract_input_data(data, **kwargs)
        if data == {}:
            data = ""  # Default to empty string for result extractor

        # Track statistics
        self._track_operation("extractions")

        # Perform extraction
        result = self._extract_with_strategy(data)

        # Emit result
        self.emit("output", **result)

    def _extract_with_strategy(self, data: Any) -> Dict[str, Any]:
        """Extract data using configured strategy.

        Args:
            data: Input data to extract from.

        Returns:
            Dictionary with extraction results and metadata.
        """
        strategy = self.get_config("strategy", "auto")
        continue_on_error = self.get_config("continue_on_error", True)
        return_original = self.get_config("return_original_on_failure", True)

        # Get extractor order
        extractors = self._get_extractor_order()

        results = []
        errors = []

        for extractor_name, extractor_func in extractors:
            try:
                result = extractor_func(data, self._config)
                if result is not None:
                    extracted_data, format_type, metadata = result

                    # Add extractor info to metadata
                    metadata["extractor"] = extractor_name
                    metadata["strategy"] = strategy

                    # Calculate confidence
                    confidence = self._calculate_confidence(extracted_data, format_type, metadata)

                    # Build extraction path
                    extraction_path = [extractor_name]

                    result_dict = {
                        "extracted_result": extracted_data,
                        "format": format_type,
                        "metadata": metadata,
                        "confidence": confidence,
                        "extraction_path": extraction_path,
                    }

                    if strategy in ("first_match", "auto", "priority"):
                        # For these strategies, return first successful match
                        # (auto and priority behave like first_match)
                        return result_dict

                    results.append(result_dict)

            except Exception as e:
                error_msg = f"Extractor '{extractor_name}' failed: {str(e)}"
                errors.append({"extractor": extractor_name, "error": error_msg})

                if self.get_config("log_errors", True):
                    logger.warning(error_msg, exc_info=True)

                if not continue_on_error:
                    break

        # Handle results based on strategy
        if results:
            if strategy == "all":
                # Return all successful extractions
                return {
                    "extracted_result": [r["extracted_result"] for r in results],
                    "format": "multi",
                    "metadata": {"extractions": results, "count": len(results), "errors": errors},
                    "confidence": max(r["confidence"] for r in results),
                    "extraction_path": [r["extraction_path"][0] for r in results],
                }
            else:
                # Return best result (highest confidence)
                return max(results, key=lambda x: x["confidence"])

        # All extractors failed
        if return_original:
            return {
                "extracted_result": data,
                "format": type(data).__name__.lower(),
                "metadata": {
                    "extraction_method": "none",
                    "errors": errors,
                    "original_type": type(data).__name__,
                },
                "confidence": 0.0,
                "extraction_path": [],
            }
        else:
            raise ValueError(f"All extractors failed. Errors: {errors}")

    def _get_extractor_order(self) -> List[Tuple[str, Callable]]:
        """Get extractors in the correct order based on configuration.

        Returns:
            List of (extractor_name, extractor_function) tuples.
        """
        priority = self.get_config("extractor_priority", [])
        all_extractors = list(self._extractors.items())

        if priority:
            # Sort by priority
            priority_map = {name: i for i, name in enumerate(priority)}
            all_extractors.sort(key=lambda x: priority_map.get(x[0], 999))
        else:
            # Default order: specialized extractors first, then generic ones
            # This ensures interpreter_output is tried before list_extractor
            specialized = [
                "interpreter_output",
                "json_code_block",
                "json_string",
                "yaml_code_block",
                "yaml_string",
                "xml_code_block",
                "code_block",
            ]
            generic = ["dict_extractor", "list_extractor"]

            def sort_key(item):
                name = item[0]
                if name in specialized:
                    return specialized.index(name) if name in specialized else 100
                elif name in generic:
                    return 50 + generic.index(name) if name in generic else 200
                else:
                    return 150  # Custom extractors in the middle

            all_extractors.sort(key=sort_key)

        return all_extractors

    def _calculate_confidence(self, data: Any, format_type: str, metadata: Dict[str, Any]) -> float:
        """Calculate confidence score for extraction result.

        Args:
            data: Extracted data.
            format_type: Detected format type.
            metadata: Extraction metadata.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        confidence = 0.5  # Base confidence

        # Increase confidence for structured data
        if isinstance(data, (dict, list)):
            confidence += 0.2

        # Increase confidence for code block extraction
        if "code_block" in metadata.get("extraction_method", ""):
            confidence += 0.1

        # Increase confidence for JSON/YAML (well-formed)
        if format_type in ("json", "yaml"):
            confidence += 0.1

        # Decrease confidence for empty results
        if not data or (isinstance(data, str) and not data.strip()):
            confidence -= 0.3

        return max(0.0, min(1.0, confidence))

    # Built-in extractors

    def _extract_json_code_block(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract JSON from markdown code blocks."""
        if not isinstance(data, str) or not config.get("extract_json_blocks", True):
            return None

        blocks = self._extract_code_blocks(data, "json")
        if not blocks:
            return None

        for block in reversed(blocks):  # Try last block first
            try:
                result = json.loads(block.strip())
                return (
                    result,
                    "json",
                    {
                        "extraction_method": "json_code_block",
                        "block_count": len(blocks),
                        "block_index": blocks.index(block),
                    },
                )
            except json.JSONDecodeError:
                continue

        return None

    def _extract_json_string(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract JSON from plain string."""
        if not isinstance(data, str) or not config.get("parse_json_strings", True):
            return None

        # Try to parse as JSON
        stripped = data.strip()
        if (stripped.startswith("{") or stripped.startswith("[")) and len(stripped) > 2:
            try:
                result = json.loads(stripped)
                return result, "json", {"extraction_method": "json_string"}
            except json.JSONDecodeError:
                pass

        return None

    def _extract_code_block(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract code blocks of various languages."""
        if not isinstance(data, str) or not config.get("extract_code_blocks", True):
            return None

        languages = config.get("code_block_languages", ["json", "python", "output"])

        for lang in languages:
            if lang == "json":  # Skip JSON, handled separately
                continue

            blocks = self._extract_code_blocks(data, lang)
            if blocks:
                return (
                    blocks[-1],
                    lang,
                    {"extraction_method": f"{lang}_code_block", "block_count": len(blocks)},
                )

        return None

    def _extract_yaml_code_block(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract YAML from markdown code blocks."""
        if not isinstance(data, str) or not config.get("extract_yaml_blocks", False):
            return None

        try:
            import yaml
        except ImportError:
            return None

        blocks = self._extract_code_blocks(data, "yaml")
        if not blocks:
            blocks = self._extract_code_blocks(data, "yml")

        if not blocks:
            return None

        for block in reversed(blocks):
            try:
                result = yaml.safe_load(block.strip())
                return (
                    result,
                    "yaml",
                    {"extraction_method": "yaml_code_block", "block_count": len(blocks)},
                )
            except Exception:
                continue

        return None

    def _extract_yaml_string(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract YAML from plain string."""
        if not isinstance(data, str) or not config.get("parse_yaml_strings", False):
            return None

        try:
            import yaml
        except ImportError:
            return None

        try:
            result = yaml.safe_load(data.strip())
            if result is not None:
                return result, "yaml", {"extraction_method": "yaml_string"}
        except Exception:
            pass

        return None

    def _extract_xml_code_block(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract XML from markdown code blocks."""
        if not isinstance(data, str) or not config.get("extract_xml_blocks", False):
            return None

        blocks = self._extract_code_blocks(data, "xml")
        if not blocks:
            return None

        # Return XML as string (parsing can be done by downstream routines)
        return (
            blocks[-1],
            "xml",
            {"extraction_method": "xml_code_block", "block_count": len(blocks)},
        )

    def _format_interpreter_output(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Format code interpreter output list.

        This extractor specifically handles lists of output dictionaries
        from code interpreters, which have a specific structure.
        """
        if not isinstance(data, list) or not config.get("format_interpreter_output", True):
            return None

        # Check if this looks like interpreter output (list of dicts with format/content)
        has_interpreter_structure = False
        lines = []
        output_count = 0

        for output in data:
            if isinstance(output, dict):
                # Check for interpreter output structure
                if "format" in output or "content" in output:
                    has_interpreter_structure = True
                    if output.get("format") == "output" and output.get("content"):
                        content = output["content"]
                        if content and len(str(content).strip()) > 0:
                            lines.append(str(content))
                            output_count += 1
            elif isinstance(output, str):
                # Plain strings in list - might be interpreter output
                if len(output.strip()) > 0:
                    lines.append(output)
                    output_count += 1

        # Only treat as interpreter output if we found the expected structure
        if has_interpreter_structure and lines:
            formatted_text = "\n".join(lines)
            return (
                formatted_text,
                "interpreter_output",
                {
                    "extraction_method": "interpreter_output",
                    "output_count": output_count,
                    "line_count": len(lines),
                },
            )

        return None

    def _extract_dict(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract from dictionary."""
        if isinstance(data, dict):
            return data, "dict", {"extraction_method": "direct", "key_count": len(data)}
        return None

    def _extract_list(
        self, data: Any, config: Dict[str, Any]
    ) -> Optional[Tuple[Any, str, Dict[str, Any]]]:
        """Extract from list."""
        if isinstance(data, list):
            return data, "list", {"extraction_method": "direct", "item_count": len(data)}
        return None

    def _extract_code_blocks(self, text: str, language: str) -> List[str]:
        """Extract code blocks of specified language from markdown text.

        Args:
            text: Text containing code blocks.
            language: Language identifier (e.g., "json", "python").

        Returns:
            List of extracted code block contents.
        """
        # Support both ```language and ```{language} formats
        patterns = [
            rf"```{re.escape(language)}\s*\n(.*?)```",
            rf"```\{{{re.escape(language)}\}}\s*\n(.*?)```",
        ]

        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            all_matches.extend(matches)

        return all_matches

    def register_extractor(
        self,
        name: str,
        extractor: Callable[[Any, Dict[str, Any]], Optional[Tuple[Any, str, Dict[str, Any]]]],
    ) -> None:
        """Register a custom extractor function.

        Args:
            name: Extractor name (must be unique).
            extractor: Extractor function that takes (data, config) and returns
                (extracted_data, format_type, metadata) or None.

        Examples:
            >>> def my_extractor(data, config):
            ...     if isinstance(data, str) and data.startswith("CUSTOM:"):
            ...         return data[7:], "custom", {"method": "prefix"}
            ...     return None
            >>> extractor.register_extractor("custom_prefix", my_extractor)
        """
        if not hasattr(self, "_extractors"):
            self._extractors = {}

        self._extractors[name] = extractor
        logger.info(f"Registered custom extractor: {name}")
