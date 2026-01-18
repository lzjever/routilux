Advanced Patterns
==================

In this tutorial, you'll learn advanced patterns for building complex workflows,
including aggregation patterns, conditional routing, and best practices for
real-world applications.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Implement proper aggregation patterns
- Use conditional routing for dynamic workflows
- Build complex branching and converging patterns
- Handle multiple data sources correctly
- Design scalable workflow architectures

Step 1: Aggregation Pattern - Collecting from Multiple Sources
---------------------------------------------------------------

A common pattern is collecting data from multiple sources before processing.
**Important**: Each ``execute()`` call creates an independent execution. To
collect data from multiple sources in a single execution, emit multiple times
from the same routine:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class MultiSourceEmitter(Routine):
       """Emit data from multiple sources in a single execution"""
       
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.emit_all)
           self.output_event = self.add_event("output", ["data", "source"])
       
       def emit_all(self, **kwargs):
           # Emit multiple times in the same execution
           sources = ["SourceA", "SourceB", "SourceC"]
           for source in sources:
               self.emit("output", data=f"Data from {source}", source=source)

   class Aggregator(Routine):
       """Collect and process aggregated data"""
       
       def __init__(self):
           super().__init__()
           # Store expected_count in _config (required for serialization)
           self.set_config(expected_count=3)
           self.input_slot = self.add_slot(
               "input",
               handler=self.aggregate,
               merge_strategy="append"  # Accumulate data
           )
           self.output_event = self.add_event("output", ["results"])
           self.set_stat("message_count", 0)
       
       def aggregate(self, data=None, source=None, **kwargs):
           # Count messages
           count = self.get_stat("message_count", 0) + 1
           self.set_stat("message_count", count)
           
           # With append strategy, data and source are lists
           data_value = data or kwargs.get("data", [])
           source_value = source or kwargs.get("source", [])
           
           # Extract latest values for display
           if isinstance(data_value, list) and data_value:
               data_str = data_value[-1]
           else:
               data_str = data_value
           if isinstance(source_value, list) and source_value:
               source_str = source_value[-1]
           else:
               source_str = source_value
           
           print(f"Received message {count}: {data_str} from {source_str}")
           
           # Check if we have enough data
           expected_count = self.get_config("expected_count", 3)
           if count >= expected_count:
               # Process all accumulated data
               all_data = self.input_slot._data
               print(f"All data collected: {all_data}")
               self.emit("output", results=all_data)
               
               # Reset for next batch
               self.input_slot._data = {}
               self.set_stat("message_count", 0)

   flow = Flow(flow_id="aggregation_flow")
   
   emitter = MultiSourceEmitter()
   aggregator = Aggregator()  # expected_count stored in _config
   
   emitter_id = flow.add_routine(emitter, "emitter")
   agg_id = flow.add_routine(aggregator, "aggregator")
   
   flow.connect(emitter_id, "output", agg_id, "input")
   
   job_state = flow.execute(emitter_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Received message 1: Data from SourceA from SourceA
   Received message 2: Data from SourceB from SourceB
   Received message 3: Data from SourceC from SourceC
   All data collected: {'data': ['Data from SourceA', 'Data from SourceB', 'Data from SourceC'], 'source': ['SourceA', 'SourceB', 'SourceC']}
   Status: completed

**Note**: With ``merge_strategy="append"``, the handler receives lists (accumulated values).
The example extracts the latest value from each list for display purposes.

**Key Points**:

- Emit multiple times from the same routine to collect in one execution
- Use ``merge_strategy="append"`` to accumulate data
- Track message count to know when aggregation is complete
- Reset state after processing for next batch

**Important**: Don't use multiple ``execute()`` calls for aggregation - each
creates an independent execution with separate JobState.

Step 2: Fan-Out and Fan-In Pattern
-----------------------------------

Combine fan-out (one-to-many) and fan-in (many-to-one) patterns:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           self.emit("output", data="test_data")

   class Processor1(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result", "processor"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           result = f"P1: {data_value.upper()}"
           self.emit("output", result=result, processor="P1")

   class Processor2(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result", "processor"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           result = f"P2: {data_value.lower()}"
           self.emit("output", result=result, processor="P2")

   class Aggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot(
               "input",
               handler=self.aggregate,
               merge_strategy="append"
           )
       
       def aggregate(self, result=None, processor=None, **kwargs):
           result_value = result or kwargs.get("result", "")
           proc = processor or kwargs.get("processor", "")
           print(f"Aggregated from {proc}: {result_value}")

   flow = Flow(flow_id="fanout_fanin_flow")
   
   source = DataSource()
   proc1 = Processor1()
   proc2 = Processor2()
   aggregator = Aggregator()
   
   source_id = flow.add_routine(source, "source")
   p1_id = flow.add_routine(proc1, "processor1")
   p2_id = flow.add_routine(proc2, "processor2")
   agg_id = flow.add_routine(aggregator, "aggregator")
   
   # Fan-out: source -> processor1 and processor2
   flow.connect(source_id, "output", p1_id, "input")
   flow.connect(source_id, "output", p2_id, "input")
   
   # Fan-in: processor1 and processor2 -> aggregator
   flow.connect(p1_id, "output", agg_id, "input")
   flow.connect(p2_id, "output", agg_id, "input")
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Aggregated from P1: P1: TEST_DATA
   Aggregated from P2: P2: test_data
   Status: completed

**Key Points**:

- Fan-out sends data to multiple processors
- Fan-in collects results from multiple sources
- Use merge_strategy="append" for fan-in
- Processors can run in parallel (with concurrent execution)

Step 4: Pipeline with Error Recovery
-------------------------------------

Build resilient pipelines with error recovery:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           self.emit("output", data="test_data")

   class UnreliableValidator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.validate)
           self.output_event = self.add_event("output", ["data", "valid"])
           self.call_count = 0
       
       def validate(self, data=None, **kwargs):
           self.call_count += 1
           data_value = data or kwargs.get("data", "")
           
           if self.call_count < 2:
               raise ValueError("Validation failed")
           
           self.emit("output", data=data_value, valid=True)

   class Processor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, valid=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           is_valid = valid if valid is not None else kwargs.get("valid", False)
           
           if is_valid:
               result = f"Processed: {data_value}"
               self.emit("output", result=result)
           else:
               raise ValueError("Cannot process invalid data")

   class Sink(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, result=None, **kwargs):
           result_value = result or kwargs.get("result", "")
           print(f"Final result: {result_value}")

   flow = Flow(flow_id="resilient_pipeline")
   
   source = DataSource()
   validator = UnreliableValidator()
   processor = Processor()
   sink = Sink()
   
   source_id = flow.add_routine(source, "source")
   validator_id = flow.add_routine(validator, "validator")
   processor_id = flow.add_routine(processor, "processor")
   sink_id = flow.add_routine(sink, "sink")
   
   flow.connect(source_id, "output", validator_id, "input")
   flow.connect(validator_id, "output", processor_id, "input")
   flow.connect(processor_id, "output", sink_id, "input")
   
   # Set error handlers
   validator.set_as_critical(max_retries=3, retry_delay=0.1)
   processor.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")
   print(f"Validator attempts: {validator.call_count}")

**Expected Output**:

.. code-block:: text

   Final result: Processed: test_data
   Status: completed
   Validator attempts: 2

**Key Points**:

- Combine error handling with pipeline patterns
- Use retry for transient failures
- Use continue for non-critical steps
- Build resilient workflows that recover from errors

Step 5: Complete Example - Data Processing Pipeline
------------------------------------------------------

Here's a complete example combining multiple advanced patterns:

.. code-block:: python
   :name: advanced_patterns_complete
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.generate)
           self.output_event = self.add_event("output", ["data"])
       
       def generate(self, count=5, **kwargs):
           count = count or kwargs.get("count", 5)
           for i in range(count):
               self.emit("output", data={"id": i, "value": i * 10})

   class Router(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.route)
           self.high_event = self.add_event("high", ["data"])
           self.low_event = self.add_event("low", ["data"])
       
       def route(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", {})
           value = data_value.get("value", 0)
           
           if value >= 30:
               self.emit("high", data=data_value)
           else:
               self.emit("low", data=data_value)

   class HighValueProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", {})
           result = f"HIGH: {data_value['value']}"
           self.emit("output", result=result)

   class LowValueProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", {})
           result = f"LOW: {data_value['value']}"
           self.emit("output", result=result)

   class Aggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot(
               "input",
               handler=self.aggregate,
               merge_strategy="append"
           )
           self.set_stat("count", 0)
       
       def aggregate(self, result=None, **kwargs):
           result_value = result or kwargs.get("result", "")
           count = self.get_stat("count", 0) + 1
           self.set_stat("count", count)
           print(f"[{count}] {result_value}")

   def main():
       flow = Flow(flow_id="advanced_pipeline")
       
       source = DataSource()
       router = Router()
       high_processor = HighValueProcessor()
       low_processor = LowValueProcessor()
       aggregator = Aggregator()
       
       source_id = flow.add_routine(source, "source")
       router_id = flow.add_routine(router, "router")
       high_id = flow.add_routine(high_processor, "high_processor")
       low_id = flow.add_routine(low_processor, "low_processor")
       agg_id = flow.add_routine(aggregator, "aggregator")
       
       # Connect pipeline
       flow.connect(source_id, "output", router_id, "input")
       flow.connect(router_id, "high", high_id, "input")
       flow.connect(router_id, "low", low_id, "input")
       flow.connect(high_id, "output", agg_id, "input")
       flow.connect(low_id, "output", agg_id, "input")
       
       # Set error handlers
       flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
       
       job_state = flow.execute(source_id, entry_params={"count": 5})
       
       print(f"\nStatus: {job_state.status}")
       print(f"Total aggregated: {aggregator.get_stat('count', 0)}")

   if __name__ == "__main__":
       main()

**Expected Output**:

.. code-block:: text

   [1] LOW: 0
   [2] LOW: 10
   [3] LOW: 20
   [4] HIGH: 30
   [5] HIGH: 40

   Status: completed
   Total aggregated: 5

**Key Points**:

- Combine routing, processing, and aggregation
- Use conditional routing for dynamic workflows
- Fan-in pattern collects results from multiple paths
- Error handling ensures resilience

Common Pitfalls
---------------

**Pitfall 1: Using multiple execute() calls for aggregation**

.. code-block:: python
   :emphasize-lines: 2-3

   # Wrong: Each execute() creates separate execution
   flow.execute(source1_id)  # JobState 1
   flow.execute(source2_id)  # JobState 2
   # Aggregator won't see both in same execution!

**Solution**: Emit multiple times from the same routine in a single execution.

**Pitfall 2: Not resetting aggregator state**

.. code-block:: python
   :emphasize-lines: 4

   def aggregate(self, **kwargs):
       # Accumulates data but never resets
       # Next batch will include old data!
       all_data = self.input_slot._data

**Solution**: Reset state after processing: ``self.input_slot._data = {}``

**Pitfall 3: Wrong merge strategy for aggregation**

.. code-block:: python
   :emphasize-lines: 3

   # Wrong: "override" replaces data instead of accumulating
   self.input_slot = self.add_slot("input", handler=self.aggregate)
   # Use "append" instead!

**Solution**: Use ``merge_strategy="append"`` for aggregation patterns.

Best Practices
--------------

1. **Use single execute() for aggregation**: Emit multiple times from one routine
2. **Reset aggregator state**: Clear data after processing each batch
3. **Use appropriate merge strategies**: "append" for accumulation, "override" for replacement
4. **Combine patterns thoughtfully**: Routing, processing, aggregation work well together
5. **Handle errors at appropriate levels**: Critical vs optional operations
6. **Test complex workflows**: Verify all paths work correctly

Next Steps
----------

Now that you understand advanced patterns, let's move on to :doc:`serialization`
to learn how to save and restore workflow state for persistence and recovery.

