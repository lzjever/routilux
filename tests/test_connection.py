"""
Connection test cases (parameter mapping removed).
"""

from routilux import Connection, Routine


class TestConnectionCreation:
    """Connection creation tests"""

    def test_create_connection(self):
        """Test: Create connection"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # Create connection
        connection = Connection(event, slot)

        # Verify connection object
        assert connection.source_event == event
        assert connection.target_slot == slot

    def test_connection_bidirectional_link(self):
        """Test: Connection establishes bidirectional link"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # Create connection
        connection = Connection(event, slot)

        # Verify bidirectional link
        assert slot in event.connected_slots
        assert event in slot.connected_events

    def test_disconnect(self):
        """Test: Disconnect connection"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # Create connection
        connection = Connection(event, slot)

        # Disconnect
        connection.disconnect()

        # Verify disconnection
        assert slot not in event.connected_slots
        assert event not in slot.connected_events
