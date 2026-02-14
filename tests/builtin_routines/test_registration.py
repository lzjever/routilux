"""Tests for built-in routine registration."""



def test_register_all_builtins_registers_all_routines():
    """Test that register_all_builtins registers all built-in routines."""
    from routilux.builtin_routines import register_all_builtins
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory()
    register_all_builtins(factory)

    # Check that all expected routines are registered
    expected = [
        "Mapper",
        "Filter",
        "SchemaValidator",
        "ConditionalRouter",
        "Aggregator",
        "Splitter",
        "Batcher",
        "Debouncer",
        "ResultExtractor",
        "RetryHandler",
    ]

    available = [r["name"] for r in factory.list_available()]
    for name in expected:
        assert name in available, f"Expected {name} to be registered"


def test_register_all_builtins_can_create_instances():
    """Test that registered routines can be instantiated."""
    from routilux.builtin_routines import register_all_builtins
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory()
    register_all_builtins(factory)

    # Should be able to create a Mapper instance
    mapper = factory.create("Mapper")
    assert mapper is not None
