Testing with RoutineTester
============================

RoutineTester is a utility for testing routines in isolation without setting up a full Flow. It automatically creates a mock flow context and captures events for easy assertion.

When to Use RoutineTester
---------------------------

Use RoutineTester when:

* You want to write unit tests for individual routines
* You need to test routine logic without connection complexity
* You want to verify emitted events and their data
* You're doing TDD (Test-Driven Development)

Basic Usage
-----------

Setting up a Test:

.. code-block:: python

   import pytest
   from routilux import Routine
   from routilux.testing import RoutineTester

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.define_slot("input", handler=self.process)
           self.output_event = self.define_event("output", ["result"])

       def process(self, data=None, **kwargs):
           extracted_data = self._extract_input_data(data, **kwargs)
           result = f"Processed: {extracted_data}"
           self.emit("output", result=result)

   def test_my_routine():
       routine = MyRoutine()
       tester = RoutineTester(routine)

       # Call slot handler
       tester.call_slot("input", data="test")

       # Verify emitted event
       events = tester.get_captured_events()
       assert len(events) == 1
       assert events[0].name == "output"
       assert events[0].data == {"result": "Processed: test"}

Testing Slot Handlers
--------------------

.. code-block:: python

   def test_slot_handler_with_kwargs():
       routine = MyRoutine()
       tester = RoutineTester(routine)

       # Call with keyword arguments
       tester.call_slot("input", data="hello", extra="value")

       events = tester.get_captured_events()
       assert len(events) == 1
       assert events[0].data["result"] == "Processed: hello"

Testing Multiple Calls
----------------------

.. code-block:: python

   def test_multiple_calls():
       routine = MyRoutine()
       tester = RoutineTester(routine)

       # Multiple calls
       tester.call_slot("input", data="test1")
       tester.call_slot("input", data="test2")
       tester.call_slot("input", data="test3")

       events = tester.get_captured_events()
       assert len(events) == 3
       assert events[0].data["result"] == "Processed: test1"
       assert events[1].data["result"] == "Processed: test2"
       assert events[2].data["result"] == "Processed: test3"

Testing State Updates
---------------------

.. code-block:: python

   class CounterRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.define_slot("trigger", handler=self.increment)
           self.output_event = self.define_event("output", ["count"])

       def increment(self, **kwargs):
           ctx = self.get_execution_context()
           if ctx:
               current = ctx.job_state.get_routine_state(ctx.routine_id, {}).get("count", 0)
               ctx.job_state.update_routine_state(ctx.routine_id, {"count": current + 1})
               self.emit("output", count=current + 1)

   def test_state_updates():
       routine = CounterRoutine()
       tester = RoutineTester(routine)

       # First call
       tester.call_slot("trigger")
       events = tester.get_captured_events()
       assert events[0].data["count"] == 1

       # Second call
       tester.clear_captured_events()
       tester.call_slot("trigger")
       events = tester.get_captured_events()
       assert events[0].data["count"] == 2

Testing Error Handling
----------------------

.. code-block:: python

   class ErrorRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.define_slot("input", handler=self.process)

       def process(self, data):
           if data == "error":
               raise ValueError("Test error")
           self.emit("output", result="ok")

   def test_error_handling():
       routine = ErrorRoutine()
       tester = RoutineTester(routine)

       # Call with error data
       with pytest.raises(ValueError, match="Test error"):
           tester.call_slot("input", data="error")

       # Call with valid data
       tester.clear_captured_events()
       tester.call_slot("input", data="ok")
       events = tester.get_captured_events()
       assert len(events) == 1

Testing Multiple Slots
----------------------

.. code-block:: python

   class MultiSlotRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.slot1 = self.define_slot("slot1", handler=self.handle1)
           self.slot2 = self.define_slot("slot2", handler=self.handle2)
           self.output_event = self.define_event("output")

       def handle1(self, data):
           self.emit("output", source="slot1", data=data)

       def handle2(self, data):
           self.emit("output", source="slot2", data=data)

   def test_multiple_slots():
       routine = MultiSlotRoutine()
       tester = RoutineTester(routine)

       # Test slot1
       tester.call_slot("slot1", data="test1")
       events = tester.get_captured_events()
       assert events[0].data["source"] == "slot1"

       # Test slot2
       tester.clear_captured_events()
       tester.call_slot("slot2", data="test2")
       events = tester.get_captured_events()
       assert events[0].data["source"] == "slot2"

Testing Configuration
---------------------

.. code-block:: python

   class ConfigurableRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.set_config(threshold=10, mode="strict")
           self.input_slot = self.define_slot("input", handler=self.process)
           self.output_event = self.define_event("output")

       def process(self, value):
           threshold = self.get_config("threshold", 0)
           mode = self.get_config("mode", "default")
           self.emit("output", value=value, threshold=threshold, mode=mode)

   def test_configuration():
       routine = ConfigurableRoutine()
       tester = RoutineTester(routine)

       tester.call_slot("input", value=5)
       events = tester.get_captured_events()
       assert events[0].data["threshold"] == 10
       assert events[0].data["mode"] == "strict"

Advanced Testing Patterns
------------------------

Testing with Fixtures:

.. code-block:: python

   @pytest.fixture
   def routine():
       return MyRoutine()

   @pytest.fixture
   def tester(routine):
       t = RoutineTester(routine)
       yield t
       t.cleanup()

   def test_with_fixture(tester):
       tester.call_slot("input", data="test")
       events = tester.get_captured_events()
       assert len(events) == 1

Testing Async Behavior:

.. code-block:: python

   def test_concurrent_calls():
       routine = MyRoutine()
       tester = RoutineTester(routine)

       # Simulate concurrent calls (though RoutineTester itself is synchronous)
       for i in range(10):
           tester.call_slot("input", data=f"test{i}")

       events = tester.get_captured_events()
       assert len(events) == 10

Testing Output Handlers:

.. code-block:: python

   import queue

   def test_output_handler():
       routine = MyRoutine()
       tester = RoutineTester(routine)

       # Set up output handler
       output_queue = queue.Queue()
       from routilux import QueueOutputHandler
       tester.job_state.set_output_handler(QueueOutputHandler())

       # Modify routine to send output
       class OutputRoutine(Routine):
           def __init__(self):
               super().__init__()
               self.input_slot = self.define_slot("input", handler=self.process)
               self.output_event = self.define_event("output")

           def process(self, data):
               self.send_output("result", data=data)
               self.emit("output", result=data)

       output_routine = OutputRoutine()
       tester2 = RoutineTester(output_routine)
       tester2.call_slot("input", data="test")

       # Check output handler
       output_data = tester2.job_state.output_handler.queue.get()
       assert output_data["data"] == "test"

Best Practices
--------------

1. **Clean up after each test**: Use clear_captured_events() or cleanup()
   .. code-block:: python

      tester = RoutineTester(routine)

      # First test
      tester.call_slot("input", data="test1")
      events = tester.get_captured_events()
      assert len(events) == 1

      # Clear for second test
      tester.clear_captured_events()
      tester.call_slot("input", data="test2")
      events = tester.get_captured_events()
      assert len(events) == 1

2. **Use fixtures for setup**: Avoid code duplication
   .. code-block:: python

      @pytest.fixture
      def my_routine():
          return MyRoutine()

      def test_case1(my_routine):
          tester = RoutineTester(my_routine)
          ...

3. **Test edge cases**: Include error cases and boundary conditions
   .. code-block:: python

      def test_edge_cases():
          routine = MyRoutine()
          tester = RoutineTester(routine)

          # Test None
          tester.call_slot("input", data=None)

          # Test empty
          tester.clear_captured_events()
          tester.call_slot("input", data="")

          # Test large data
          tester.clear_captured_events()
          tester.call_slot("input", data="x" * 10000)

4. **Verify all emitted events**: Don't just check count, verify data too
   .. code-block:: python

      def test_verify_event_data():
          routine = MyRoutine()
          tester = RoutineTester(routine)

          tester.call_slot("input", data="test")
          events = tester.get_captured_events()

          # Good: Check both count and data
          assert len(events) == 1
          assert events[0].name == "output"
          assert events[0].data["result"] == "Processed: test"

          # Bad: Only check count
          # assert len(events) == 1

Limitations
-----------

RoutineTester has some limitations:

* **No actual flow execution**: Routines are tested in isolation, not in a real flow
* **No connection testing**: Can't test connections between routines
* **No concurrency testing**: All calls are synchronous
* **Mock context**: Uses mock flow and job_state contexts

For full integration tests, use actual Flow objects:

.. code-block:: python

   def test_full_flow():
       flow = Flow(flow_id="test_flow")
       routine1 = MyRoutine()
       routine2 = MyRoutine()

       id1 = flow.add_routine(routine1, "routine1")
       id2 = flow.add_routine(routine2, "routine2")
       flow.connect(id1, "output", id2, "input")

       entry = EntryRoutine()
       entry_id = flow.add_routine(entry, "entry")
       flow.connect(entry_id, "output", id1, "input")

       job_state = flow.execute(entry_id, entry_params={"data": "test"})
       assert job_state.status == "completed"

See Also
--------

* :doc:`../api_reference/index` - Complete API reference
* :doc:`flows` - Flow class for workflow orchestration
* :doc:`routines` - Routine class documentation
