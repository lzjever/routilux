"""
Text renderer routine.

Renders objects (dicts, lists) into formatted text with XML-like tags.
"""

from __future__ import annotations

from typing import Any

from routilux.core import Routine


class TextRenderer(Routine):
    """Routine for rendering objects into formatted text.

    This routine converts dictionaries and lists into formatted text
    with XML-like tags, making structured data more readable.

    Features:
        - Recursively renders nested dictionaries and lists
        - Adds XML-like tags for structure
        - Handles primitive types (str, int, float, bool)
        - Configurable tag formatting

    Examples:
        >>> renderer = TextRenderer()
        >>> renderer.define_slot("input", handler=renderer.render)
        >>> renderer.define_event("output", ["rendered_text"])
        >>> # Render a dictionary
        >>> data = {"name": "test", "value": 42}
        >>> # Output: "<name>test</name>\\n<value>42</value>"
    """

    def __init__(self):
        """Initialize TextRenderer routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            tag_format="xml",  # "xml" or "markdown"
            indent="  ",  # Indentation for nested structures
            include_type_hints=False,
        )

        # Define input slot
        self.input_slot = self.add_slot("input")

        # Define output event
        self.output_event = self.add_event("output", ["rendered_text", "original_type"])

        # Set up activation policy and logic
        self.set_activation_policy(
            lambda slots, worker_state: (
                len(slots["input"]) > 0,
                {"input": slots["input"].consume_all_new()},
                "slot_activated",
            )
        )
        self.set_logic(self._handle_input)

    def _handle_input(self, data: Any = None, **kwargs):
        """Handle input data and render it.

        Args:
            data: Data to render (dict, list, or primitive type).
                Can be passed directly or via kwargs.
            **kwargs: Additional data from slot. If 'data' is not provided,
                will use kwargs or the first value.
        """
        # Extract data: use data parameter if provided, otherwise check 'data' key in kwargs
        if data is None:
            data = kwargs.get("data")
            if data is None and len(kwargs) == 1:
                data = next(iter(kwargs.values()))
            elif data is None and len(kwargs) > 1:
                data = kwargs

        # Track statistics
        # Operation tracking removed - use JobState for execution state

        original_type = type(data).__name__
        rendered_text = self._render_object(data)

        # Emit result
        self.emit("output", rendered_text=rendered_text, original_type=original_type)

    def _render_object(self, data: Any, indent_level: int = 0, visited: set | None = None) -> str:
        """Recursively render an object.

        Args:
            data: Object to render.
            indent_level: Current indentation level.
            visited: Set of visited object IDs to prevent circular references.

        Returns:
            Rendered text string.
        """
        # Initialize visited set on first call
        if visited is None:
            visited = set()

        # Prevent circular references
        obj_id = id(data)
        if obj_id in visited:
            return "[Circular Reference]"
        visited.add(obj_id)

        try:
            indent = self.get_config("indent", "  ") * indent_level
            tag_format = self.get_config("tag_format", "xml")

            if isinstance(data, dict):
                lines = []
                for key, value in data.items():
                    rendered_value = self._render_object(value, indent_level + 1, visited)

                    if tag_format == "xml":
                        lines.append(f"{indent}<{key}>{rendered_value}</{key}>")
                    else:  # markdown
                        lines.append(f"{indent}**{key}**: {rendered_value}")

                return "\n".join(lines) if lines else ""

            elif isinstance(data, list):
                lines = []
                for i, value in enumerate(data):
                    rendered_value = self._render_object(value, indent_level + 1, visited)

                    if tag_format == "xml":
                        lines.append(f"{indent}<item_{i}>{rendered_value}</item_{i}>")
                    else:  # markdown
                        lines.append(f"{indent}- {rendered_value}")

                return "\n".join(lines) if lines else ""

            else:
                # Primitive type
                return str(data)
        finally:
            # Remove from visited set when done with this branch
            visited.discard(obj_id)
