Aggregation Pattern
===================

The aggregation pattern allows a routine to wait for all expected messages
from multiple upstream routines before processing and emitting results. This
is useful for scenarios like aggregating search results from multiple sources,
collecting data from parallel tasks, or combining outputs from different
processors.

Overview
--------

When you need to collect data from multiple sources and process it together,
you can use the **append merge strategy** combined with a counter check in
the handler. This pattern ensures that:

1. All incoming messages are accumulated
2. The handler is called for each message
3. Processing only occurs when all expected messages are received
4. Results are emitted once after all data is collected

Key Concepts
------------

**Merge Strategy: "append"**
    With ``merge_strategy="append"``, each incoming message's values are
    appended to lists. This allows you to accumulate data over multiple
    receive operations.

**Message Counting**
    In the handler, check the length of any list field to determine how many
    messages have been received. When the count reaches the expected number,
    process all accumulated data.

**Single Processing**
    Use a flag to ensure processing only happens once, even if the handler
    is called multiple times with the same count.

Basic Example
-------------

Here's a simple aggregator that waits for 3 messages:

.. code-block:: python

   from routilux import Flow, Routine

   class SourceRoutine(Routine):
       def __init__(self, source_id: str):
           super().__init__()
           self.source_id = source_id
           self.output_event = self.add_event("output", ["data", "source_id"])
       
       def __call__(self, **kwargs):
           super().__call__(**kwargs)
           data = kwargs.get("data", f"data_from_{self.source_id}")
           self.emit("output", data=data, source_id=self.source_id)

   class AggregatorRoutine(Routine):
       """Aggregator that waits for all expected messages."""
       
       def __init__(self, expected_count: int = 3):
           super().__init__()
           self.expected_count = expected_count
           self.set_config(expected_count=expected_count)
           self.processed = False  # Flag to ensure single processing
           
           # Use append strategy to accumulate data
           self.input_slot = self.add_slot(
               "input",
               handler=self._handle_input,
               merge_strategy="append"  # Key: append strategy
           )
           self.output_event = self.add_event("aggregated", ["all_data", "count"])
       
       def _handle_input(self, **kwargs):
           """Handle input and check if all messages received."""
           # With append strategy, kwargs contains lists
           # Count messages using any list field
           received_count = 0
           if "source_id" in kwargs and isinstance(kwargs["source_id"], list):
               received_count = len(kwargs["source_id"])
           elif "data" in kwargs and isinstance(kwargs["data"], list):
               received_count = len(kwargs["data"])
           
           expected_count = self.get_config("expected_count", self.expected_count)
           
           # Process only when all messages received and not already processed
           if received_count >= expected_count and not self.processed:
               self.processed = True
               
               # Extract accumulated data
               all_data = []
               if "data" in kwargs and isinstance(kwargs["data"], list):
                   all_data = kwargs["data"]
               
               # Emit aggregated result
               self.emit("aggregated", all_data=all_data, count=len(all_data))
               
               # Reset for next aggregation (optional)
               self.input_slot._data = {}

   # Create flow
   flow = Flow(flow_id="aggregator_demo")
   
   # Create sources
   source1 = SourceRoutine("source1")
   source2 = SourceRoutine("source2")
   source3 = SourceRoutine("source3")
   
   # Create aggregator
   aggregator = AggregatorRoutine(expected_count=3)
   
   # Add to flow
   id1 = flow.add_routine(source1, "source1")
   id2 = flow.add_routine(source2, "source2")
   id3 = flow.add_routine(source3, "source3")
   agg_id = flow.add_routine(aggregator, "aggregator")
   
   # Connect all sources to aggregator
   flow.connect(id1, "output", agg_id, "input")
   flow.connect(id2, "output", agg_id, "input")
   flow.connect(id3, "output", agg_id, "input")
   
   # Execute sources
   flow.execute(id1, entry_params={"data": "data1"})
   flow.execute(id2, entry_params={"data": "data2"})
   flow.execute(id3, entry_params={"data": "data3"})
   
   # Aggregator will process when all 3 messages are received

How It Works
------------

1. **Append Strategy**: When ``merge_strategy="append"`` is used, each
   ``receive()`` call appends values to lists in ``slot._data``.

2. **Handler Invocation**: The handler is called after each ``receive()``
   with the accumulated data (where values are lists).

3. **Message Counting**: Check the length of any list field in ``kwargs``
   to count received messages.

4. **Conditional Processing**: Only process when:
   - Count reaches expected number
   - Not already processed (use a flag)

5. **Data Extraction**: Extract all accumulated data from the lists and
   process it together.

6. **Emission**: Emit the aggregated result once.

7. **Reset (Optional)**: Clear ``slot._data`` to prepare for the next
   aggregation cycle.

Complete Example: Search Result Aggregation
-------------------------------------------

Here's a complete example that aggregates search results from multiple
search engines:

.. literalinclude:: ../../../examples/aggregator_demo.py
   :language: python
   :linenos:

Key Points
----------

**Handler is Called for Each Message**
    The handler is called immediately after each message is received.
    You check the count inside the handler to decide when to process.

**Append Strategy Behavior**
    With ``merge_strategy="append"``:
    
    - First message: ``kwargs = {"data": ["data1"], "source_id": ["source1"]}``
    - Second message: ``kwargs = {"data": ["data1", "data2"], "source_id": ["source1", "source2"]}``
    - Third message: ``kwargs = {"data": ["data1", "data2", "data3"], "source_id": ["source1", "source2", "source3"]}``

**Counting Messages**
    Use any field that appears in every message to count:
    
    .. code-block:: python
       
       if "source_id" in kwargs and isinstance(kwargs["source_id"], list):
           count = len(kwargs["source_id"])
       elif "data" in kwargs and isinstance(kwargs["data"], list):
           count = len(kwargs["data"])

**Preventing Duplicate Processing**
    Use a flag to ensure processing only happens once:
    
    .. code-block:: python
       
       if count >= expected_count and not self.processed:
           self.processed = True
           # Process and emit

**Resetting for Next Cycle**
    After processing, optionally reset the slot data:
    
    .. code-block:: python
       
       self.input_slot._data = {}

Concurrent Execution
--------------------

The aggregation pattern works the same way in concurrent execution mode.
However, be aware that:

- Handler calls may be interleaved across threads
- Use thread-safe operations if handlers share state
- The total number of calls remains the same as sequential mode

Example with concurrent execution:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent", max_workers=5)
   
   # Same setup as before
   # ...
   
   # Execute sources concurrently
   flow.execute(id1, entry_params={"data": "data1"})
   flow.execute(id2, entry_params={"data": "data2"})
   flow.execute(id3, entry_params={"data": "data3"})
   
   # Wait for completion
   from routilux.job_state import JobState
   JobState.wait_for_completion(flow, job_state, timeout=10.0)
   
   # Aggregator will still process when all 3 messages are received

Best Practices
--------------

1. **Use Configuration**: Store ``expected_count`` in ``_config`` for
   flexibility:
   
   .. code-block:: python
      
      self.set_config(expected_count=expected_count)

2. **Check List Type**: Always check if a value is a list before using
   ``len()``:
   
   .. code-block:: python
      
      if "field" in kwargs and isinstance(kwargs["field"], list):
          count = len(kwargs["field"])

3. **Prevent Duplicate Processing**: Use a flag to ensure processing
   happens only once:
   
   .. code-block:: python
      
      if count >= expected_count and not self.processed:
          self.processed = True
          # Process

4. **Reset After Processing**: Clear slot data after processing to prepare
   for the next aggregation cycle:
   
   .. code-block:: python
      
      self.input_slot._data = {}

5. **Handle Edge Cases**: Consider what happens if:
   - Fewer messages arrive than expected (timeout handling)
   - More messages arrive than expected
   - Messages arrive out of order

6. **Thread Safety**: In concurrent mode, if you need to share state
   between handlers, use thread-safe operations (locks, atomic operations).

Common Patterns
---------------

**Timeout Handling**
    Add timeout logic to process even if not all messages arrive:
    
    .. code-block:: python
       
       import time
       
       def __init__(self, expected_count: int = 3, timeout: float = 10.0):
           # ...
           self.start_time = None
           self.set_config(timeout=timeout)
       
       def _handle_input(self, **kwargs):
           if self.start_time is None:
               self.start_time = time.time()
           
           # ... count messages ...
           
           timeout = self.get_config("timeout", 10.0)
           elapsed = time.time() - self.start_time
           
           if (count >= expected_count) or (elapsed >= timeout):
               # Process with available data

**Dynamic Expected Count**
    Allow the expected count to be set dynamically:
    
    .. code-block:: python
       
       def set_expected_count(self, count: int):
           self.set_config(expected_count=count)
           self.expected_count = count

**Multiple Aggregation Cycles**
    Reset properly to support multiple aggregation cycles:
    
    .. code-block:: python
       
       def _handle_input(self, **kwargs):
           # ... check count ...
           if count >= expected_count and not self.processed:
               self.processed = True
               # Process
               self.input_slot._data = {}
               self.processed = False  # Reset for next cycle

See Also
--------

- :doc:`routines` - Working with routines
- :doc:`connections` - Connecting routines
- :doc:`flows` - Flow execution and concurrent mode

