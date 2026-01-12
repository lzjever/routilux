"""
Demo of built-in routines usage.

This example demonstrates how to use the built-in routines in Routilux.
"""

from routilux import Flow
from routilux.builtin_routines import (
    ConditionalRouter,
    DataFlattener,
    DataTransformer,
    DataValidator,
    RetryHandler,
    TextClipper,
    TextRenderer,
    TimeProvider,
)


def demo_text_processing():
    """Demonstrate text processing routines."""
    print("=== Text Processing Demo ===")

    flow = Flow()

    # Create text clipper
    clipper = TextClipper()
    clipper.set_config(max_length=50)
    flow.add_routine(clipper, "clipper")

    # Create text renderer
    renderer = TextRenderer()
    renderer.set_config(tag_format="xml")
    flow.add_routine(renderer, "renderer")

    # Connect
    flow.connect("renderer", "output", "clipper", "input")

    # Create a simple source routine
    class SourceRoutine:
        def __init__(self):
            self.output_event = None

        def emit_data(self, flow):
            data = {"name": "test", "value": 42, "nested": {"key": "value"}}
            renderer.input_slot.receive(data)

    print("Text processing routines created and connected")


def demo_utility_routines():
    """Demonstrate utility routines."""
    print("=== Utility Routines Demo ===")

    flow = Flow()

    # Create time provider
    time_provider = TimeProvider()
    time_provider.set_config(format="formatted", include_weekday=True)
    flow.add_routine(time_provider, "time_provider")

    # Create data flattener
    flattener = DataFlattener()
    flattener.set_config(separator=".")
    flow.add_routine(flattener, "flattener")

    print("Utility routines created")


def demo_data_processing():
    """Demonstrate data processing routines."""
    print("=== Data Processing Demo ===")

    flow = Flow()

    # Create data transformer
    transformer = DataTransformer()
    transformer.set_config(transformations=["lowercase", "strip_whitespace"])
    flow.add_routine(transformer, "transformer")

    # Create data validator
    validator = DataValidator()
    validator.set_config(
        rules={"name": "not_empty", "age": lambda x: isinstance(x, int) and x > 0},
        required_fields=["name", "age"],
    )
    flow.add_routine(validator, "validator")

    # Connect
    flow.connect("transformer", "output", "validator", "input")

    print("Data processing routines created and connected")


def demo_control_flow():
    """Demonstrate control flow routines."""
    print("=== Control Flow Demo ===")

    flow = Flow()

    # Create conditional router
    router = ConditionalRouter()
    router.set_config(
        routes=[
            ("high", lambda x: isinstance(x, dict) and x.get("priority") == "high"),
            ("low", lambda x: isinstance(x, dict) and x.get("priority") == "low"),
        ],
        default_route="normal",
    )
    flow.add_routine(router, "router")

    # Create retry handler
    retry_handler = RetryHandler()
    retry_handler.set_config(max_retries=3, retry_delay=1.0, backoff_multiplier=2.0)
    flow.add_routine(retry_handler, "retry_handler")

    print("Control flow routines created")


def demo_complete_flow():
    """Demonstrate a complete flow using multiple routines."""
    print("=== Complete Flow Demo ===")

    flow = Flow()

    # Create routines
    time_provider = TimeProvider()
    time_provider.set_config(format="iso")
    flow.add_routine(time_provider, "time")

    renderer = TextRenderer()
    renderer.set_config(tag_format="xml")
    flow.add_routine(renderer, "renderer")

    clipper = TextClipper()
    clipper.set_config(max_length=200)
    flow.add_routine(clipper, "clipper")

    validator = DataValidator()
    validator.set_config(rules={"timestamp": "is_string"}, required_fields=["timestamp"])
    flow.add_routine(validator, "validator")

    router = ConditionalRouter()
    router.set_config(
        routes=[
            ("valid", lambda x: x.get("is_valid", False)),
        ],
        default_route="invalid",
    )
    flow.add_routine(router, "router")

    # Connect flow
    flow.connect("time", "output", "renderer", "input")
    flow.connect("renderer", "output", "clipper", "input")
    flow.connect("clipper", "output", "validator", "input")
    flow.connect("validator", "valid", "router", "input")

    print("Complete flow created with multiple routines")
    print("Flow structure:")
    print("  time -> renderer -> clipper -> validator -> router")


if __name__ == "__main__":
    demo_text_processing()
    demo_utility_routines()
    demo_data_processing()
    demo_control_flow()
    demo_complete_flow()

    print("\n=== All demos completed ===")
