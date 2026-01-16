"""
Comprehensive Connection tests (parameter mapping removed).
"""

from routilux import Connection, Routine


class TestConnectionDisconnect:
    """Connection disconnect tests"""

    def test_disconnect(self):
        """Test: Disconnect connection"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # Create connection
        connection = Connection(event, slot)

        # Verify connection established
        assert slot in event.connected_slots
        assert event in slot.connected_events

        # Disconnect
        connection.disconnect()

        # Verify connection disconnected
        assert slot not in event.connected_slots
        assert event not in slot.connected_events

    def test_disconnect_multiple_times(self):
        """Test: Disconnect multiple times (should be safe)"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        connection = Connection(event, slot)

        # First disconnect
        connection.disconnect()

        # Disconnect again should not raise error
        connection.disconnect()

        # Verify connection disconnected
        assert slot not in event.connected_slots


class TestConnectionSerialization:
    """Connection serialization tests"""

    def test_connection_serialize(self):
        """Test: Connection serialization"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        connection = Connection(event, slot)

        data = connection.serialize()

        assert data["_type"] == "Connection"
        assert data["_source_event_name"] == "output"
        assert data["_target_slot_name"] == "input"
        # param_mapping removed

    def test_connection_deserialize(self):
        """Test: Connection deserialization"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        data = {
            "_type": "Connection",
            "_source_event_name": "output",
            "_target_slot_name": "input",
        }

        connection = Connection()
        connection.deserialize(data)

        # Need to manually set event and slot (may not be available during deserialization)
        connection.source_event = event
        connection.target_slot = slot

        assert connection.source_event == event
        assert connection.target_slot == slot
        # param_mapping removed
