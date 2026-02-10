"""
Text clipper routine.

Clips text to a maximum length while preserving important information.
"""

from __future__ import annotations

from typing import Any

from routilux.core import Routine


class TextClipper(Routine):
    """Routine for clipping text to a maximum length.

    This routine clips text content to a specified maximum length while
    preserving important information. It handles special cases like
    tracebacks and provides informative truncation messages.

    Features:
    - Preserves tracebacks completely (doesn't clip them)
    - Clips text line by line to respect line boundaries
    - Provides informative truncation messages
    - Configurable maximum length

    Examples:
        >>> clipper = TextClipper()
        >>> clipper.set_config(max_length=1000)
        >>> clipper.define_slot("input", handler=clipper.clip_text)
        >>> clipper.define_event("output", ["clipped_text"])
    """

    def __init__(self):
        """Initialize TextClipper routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            max_length=1000, preserve_tracebacks=True, truncation_message="...(省略了{remaining}行)"
        )

        # Define input slot
        self.input_slot = self.add_slot("input")

        # Define output event
        self.output_event = self.add_event(
            "output", ["clipped_text", "was_clipped", "original_length"]
        )

        # Set up activation policy and logic
        self.set_activation_policy(
            lambda slots, worker_state: (
                len(slots["input"]) > 0,
                {"input": slots["input"].consume_all_new()},
                "slot_activated",
            )
        )
        self.set_logic(self._handle_input)

    def _handle_input(self, text: Any = None, max_length: int | None = None, **kwargs):
        """Handle input text and clip if necessary.

        Args:
            text: Text content to clip. Can be passed directly or via kwargs.
            max_length: Optional maximum length override. If not provided,
                uses value from _config["max_length"].
            **kwargs: Additional data from slot. If 'text' is not provided,
                will try to extract from kwargs or use the first value.
        """
        # Extract text: use text parameter if provided, otherwise check 'data' key in kwargs
        data = text
        if data is None:
            data = kwargs.get("data")
            if data is None and len(kwargs) == 1:
                data = next(iter(kwargs.values()))
            elif data is None and len(kwargs) > 1:
                data = kwargs

        # Convert to string - handle various input types
        if isinstance(data, str):
            text = data
        elif isinstance(data, dict):
            # Try common keys for text content
            for key in ["text", "content", "message", "data"]:
                if key in data and isinstance(data[key], str):
                    text = data[key]
                    break
            else:
                # Try any string value
                for value in data.values():
                    if isinstance(value, str):
                        text = value
                        break
                else:
                    text = str(data)
        else:
            text = str(data)

        # Validate input
        if not isinstance(text, str):
            text = str(text)

        max_len = max_length or self.get_config("max_length", 1000)
        preserve_tracebacks = self.get_config("preserve_tracebacks", True)

        # Track statistics
        # Operation tracking removed - use JobState for execution state
        original_length = len(text)

        # Preserve tracebacks if configured
        if preserve_tracebacks and "Traceback" in text:
            clipped_text = text
            was_clipped = False
            # Statistics tracking removed - use JobState for execution state
        else:
            clipped_text, was_clipped = self._clip_text(text, max_len)
            if was_clipped:
                # Statistics tracking removed - use JobState for execution state
                pass

        # Emit result
        self.emit(
            "output",
            clipped_text=clipped_text,
            was_clipped=was_clipped,
            original_length=original_length,
        )

    def _clip_text(self, text: str, max_length: int) -> tuple[str, bool]:
        """Clip text to maximum length.

        Args:
            text: Text to clip.
            max_length: Maximum allowed length.

        Returns:
            Tuple of (clipped_text, was_clipped).
        """
        if len(text) <= max_length:
            return text, False

        lines = text.split("\n")
        head = []
        count = 0
        clipped = False

        for line in lines:
            line_length = len(line) + 1  # +1 for newline
            if count + line_length < max_length:
                count += line_length
                head.append(line)
            else:
                clipped = True
                break

        if not clipped:
            return "\n".join(head), False

        # Build truncation message
        remaining_lines = len(lines) - len(head)
        truncation_msg = self.get_config("truncation_message", "...(省略了{remaining}行)")
        truncation_msg = truncation_msg.format(remaining=remaining_lines)

        clipped_text = "\n".join(head) + "\n" + truncation_msg
        return clipped_text, True
