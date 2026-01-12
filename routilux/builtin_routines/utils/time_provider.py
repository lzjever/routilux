"""
Time provider routine.

Provides current time in various formats.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from routilux.routine import Routine


class TimeProvider(Routine):
    """Routine for providing current time information.

    This routine provides current time in various formats, useful for
    logging, timestamps, and time-based operations.

    Features:
    - Multiple time formats (ISO, formatted string, timestamp)
    - Configurable format strings
    - Timezone support
    - Locale-aware formatting

    Examples:
        >>> time_provider = TimeProvider()
        >>> time_provider.set_config(format="iso", include_weekday=True)
        >>> time_provider.define_slot("request", handler=time_provider.get_time)
        >>> time_provider.define_event("output", ["time_string", "timestamp", "datetime"])
    """

    def __init__(self):
        """Initialize TimeProvider routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            format="iso",  # "iso", "formatted", "timestamp", "custom"
            custom_format="%Y-%m-%d %H:%M:%S",
            include_weekday=True,
            locale="zh_CN",  # For weekday translation
        )

        # Define input slot (trigger slot - no data needed)
        self.trigger_slot = self.define_slot("request", handler=self._handle_request)

        # Define output event
        self.output_event = self.define_event(
            "output", ["time_string", "timestamp", "datetime", "formatted"]
        )

    def _handle_request(self, data: dict[str, Any] | None = None, **kwargs):
        """Handle time request.

        Args:
            data: Optional data dict. Can contain format override.
            **kwargs: Additional data from slot.
        """
        # Statistics tracking removed - use JobState for execution state

        # Get format from data or kwargs or config
        format_type = None
        if data and isinstance(data, dict):
            format_type = data.get("format")
        elif "format" in kwargs:
            format_type = kwargs["format"]

        format_type = format_type or self.get_config("format", "iso")

        # Get current time
        now = datetime.now()
        timestamp = time.time()

        # Format time string
        time_string = self._format_time(now, format_type)

        # Emit result
        self.emit(
            "output",
            time_string=time_string,
            timestamp=timestamp,
            datetime=now.isoformat(),
            formatted=now.strftime(self.get_config("custom_format", "%Y-%m-%d %H:%M:%S")),
        )

    def _format_time(self, dt: datetime, format_type: str) -> str:
        """Format datetime according to format type.

        Args:
            dt: Datetime object.
            format_type: Format type ("iso", "formatted", "timestamp", "custom").

        Returns:
            Formatted time string.
        """
        if format_type == "iso":
            return dt.isoformat()

        elif format_type == "timestamp":
            # Use timestamp() instead of mktime() to avoid timezone issues
            return str(dt.timestamp())

        elif format_type == "formatted":
            return self._format_with_locale(dt)

        elif format_type == "custom":
            custom_format = self.get_config("custom_format", "%Y-%m-%d %H:%M:%S")
            return dt.strftime(custom_format)

        else:
            # Default to ISO
            return dt.isoformat()

    def _format_with_locale(self, dt: datetime) -> str:
        """Format datetime with locale-aware weekday.

        Args:
            dt: Datetime object.

        Returns:
            Formatted string with locale-aware weekday.
        """
        locale = self.get_config("locale", "zh_CN")
        include_weekday = self.get_config("include_weekday", True)

        if locale == "zh_CN" and include_weekday:
            # Chinese format
            weekday_map = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
            weekday = weekday_map[dt.weekday()]
            time_str = dt.strftime(f"%Y年%m月%d日，星期{weekday}，%H:%M:%S")
            return time_str
        else:
            # English format
            if include_weekday:
                return dt.strftime("%A, %B %d, %Y %H:%M:%S")
            else:
                return dt.strftime("%Y-%m-%d %H:%M:%S")
