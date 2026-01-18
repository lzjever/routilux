Data Flow and Parameters
==========================

In this tutorial, you'll learn how data flows through Routilux workflows,
including parameter extraction, parameter mapping in connections, and best
practices for handling data.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Extract data from slot handler parameters correctly
- Use parameter mapping in connections to transform parameter names
- Understand how data is passed through events and slots
- Handle different data types and structures
- Debug data flow issues

Step 1: Understanding Parameter Extraction
------------------------------------------

Slot handlers receive data through keyword arguments. You need to extract the
data correctly:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["name", "age", "city"])
       
       def send(self, **kwargs):
           # Emit multiple parameters
           self.emit("output", name="Alice", age=30, city="New York")

   class DataReceiver(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, name=None, age=None, city=None, **kwargs):
           # Extract parameters with defaults
           name = name or kwargs.get("name", "Unknown")
           age = age or kwargs.get("age", 0)
           city = city or kwargs.get("city", "Unknown")
           
           print(f"Received: {name}, {age} years old, from {city}")

   flow = Flow(flow_id="param_flow")
   
   source = DataSource()
   receiver = DataReceiver()
   
   source_id = flow.add_routine(source, "source")
   receiver_id = flow.add_routine(receiver, "receiver")
   
   flow.connect(source_id, "output", receiver_id, "input")
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Received: Alice, 30 years old, from New York
   Status: completed

**Key Points**:

- Parameters are passed as keyword arguments to slot handlers
- Use the pattern ``param = param or kwargs.get("param", default)`` for safe extraction
- All parameters specified in ``add_event()`` are available in the handler

Step 2: Parameter Mapping in Connections
-----------------------------------------

You can map parameter names when connecting events to slots. This is useful
when you want to transform data or match different naming conventions:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class Source(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["user_name", "user_age"])
       
       def send(self, **kwargs):
           self.emit("output", user_name="Bob", user_age=25)

   class Target(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, name=None, age=None, **kwargs):
           # Expects "name" and "age", not "user_name" and "user_age"
           name = name or kwargs.get("name", "Unknown")
           age = age or kwargs.get("age", 0)
           print(f"Target received: name={name}, age={age}")

   flow = Flow(flow_id="mapping_flow")
   
   source = Source()
   target = Target()
   
   source_id = flow.add_routine(source, "source")
   target_id = flow.add_routine(target, "target")
   
   # Map parameters: user_name -> name, user_age -> age
   flow.connect(
       source_id, "output", target_id, "input",
       param_mapping={"user_name": "name", "user_age": "age"}
   )
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Target received: name=Bob, age=25
   Status: completed

**Key Points**:

- Use ``param_mapping`` in ``connect()`` to transform parameter names
- Mapping format: ``{"source_param": "target_param"}``
- Unmapped parameters are passed through unchanged
- This is useful for adapting different routine interfaces

Step 3: Handling Complex Data Structures
-----------------------------------------

You can pass complex data structures (dicts, lists) through events:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           # Send a complex data structure
           complex_data = {
               "users": [
                   {"name": "Alice", "scores": [85, 90, 88]},
                   {"name": "Bob", "scores": [92, 87, 91]}
               ],
               "metadata": {"version": "1.0", "timestamp": "2024-01-01"}
           }
           self.emit("output", data=complex_data)

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", {})
           
           # Process the complex data
           if isinstance(data_value, dict) and "users" in data_value:
               total_scores = []
               for user in data_value["users"]:
                   scores = user.get("scores", [])
                   total_scores.extend(scores)
               
               result = {
                   "total_users": len(data_value["users"]),
                   "average_score": sum(total_scores) / len(total_scores) if total_scores else 0,
                   "metadata": data_value.get("metadata", {})
               }
               
               print(f"Processed {result['total_users']} users")
               print(f"Average score: {result['average_score']:.2f}")
               
               self.emit("output", result=result)

   flow = Flow(flow_id="complex_flow")
   
   source = DataSource()
   processor = DataProcessor()
   
   source_id = flow.add_routine(source, "source")
   processor_id = flow.add_routine(processor, "processor")
   
   flow.connect(source_id, "output", processor_id, "input")
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Processed 2 users
   Average score: 88.83
   Status: completed

**Key Points**:

- You can pass any Python object through events (dicts, lists, custom objects)
- Always check data types and structure in handlers
- Complex data structures are passed by reference (not copied)
- Be careful with mutable objects - modifications affect all references

Step 4: Using _extract_input_data Helper
------------------------------------------

Routilux provides a helper method ``_extract_input_data()`` for easier data
extraction:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data", "metadata"])
       
       def send(self, **kwargs):
           self.emit("output", data="test data", metadata={"source": "tutorial"})

   class DataReceiver(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, data=None, metadata=None, **kwargs):
           # Use helper method for cleaner extraction
           data_value = self._extract_input_data(data, **kwargs)
           metadata_value = self._extract_input_data(metadata, **kwargs)
           
           print(f"Data: {data_value}")
           print(f"Metadata: {metadata_value}")

   flow = Flow(flow_id="helper_flow")
   
   source = DataSource()
   receiver = DataReceiver()
   
   source_id = flow.add_routine(source, "source")
   receiver_id = flow.add_routine(receiver, "receiver")
   
   flow.connect(source_id, "output", receiver_id, "input")
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Data: test data
   Metadata: {'source': 'tutorial'}
   Status: completed

**Key Points**:

- ``_extract_input_data()`` is a convenience method for data extraction
- It handles both direct parameters and kwargs
- Use it for cleaner, more readable code

Step 5: Debugging Data Flow
---------------------------

When debugging data flow issues, it's helpful to inspect what data is being
passed:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class DebugSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["value", "extra"])
       
       def send(self, **kwargs):
           print(f"[DEBUG] Source emitting: value='test', extra='info'")
           self.emit("output", value="test", extra="info")

   class DebugReceiver(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, **kwargs):
           # Print all received kwargs for debugging
           print(f"[DEBUG] Receiver received kwargs: {kwargs}")
           
           # Extract specific values
           value = kwargs.get("value", "NOT_FOUND")
           extra = kwargs.get("extra", "NOT_FOUND")
           
           print(f"[DEBUG] Extracted: value={value}, extra={extra}")

   flow = Flow(flow_id="debug_flow")
   
   source = DebugSource()
   receiver = DebugReceiver()
   
   source_id = flow.add_routine(source, "source")
   receiver_id = flow.add_routine(receiver, "receiver")
   
   flow.connect(source_id, "output", receiver_id, "input")
   
   job_state = flow.execute(source_id)
   print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   [DEBUG] Source emitting: value='test', extra='info'
   [DEBUG] Receiver received kwargs: {'value': 'test', 'extra': 'info'}
   [DEBUG] Extracted: value=test, extra=info
   Status: completed

**Key Points**:

- Print kwargs in handlers to see what data is received
- Check parameter names match between ``add_event()`` and handler
- Verify connections are set up correctly
- Use debug prints during development

Common Pitfalls
---------------

**Pitfall 1: Not handling missing parameters**

.. code-block:: python
   :emphasize-lines: 3

   def process(self, data):
       # Assumes 'data' is always provided
       result = data.upper()  # May fail if data is None

**Solution**: Always use defaults: ``data = data or kwargs.get("data", "")``

**Pitfall 2: Wrong parameter names**

.. code-block:: python
   :emphasize-lines: 1, 4

   self.output_event = self.add_event("output", ["user_name"])  # Defined as "user_name"
   
   def receive(self, username=None, **kwargs):  # Looking for "username"!
       username = username or kwargs.get("username")  # Won't find it

**Solution**: Use exact parameter names from ``add_event()``, or use parameter mapping.

**Pitfall 3: Modifying mutable data structures**

.. code-block:: python
   :emphasize-lines: 3

   def process(self, data=None, **kwargs):
       data_value = data or kwargs.get("data", {})
       data_value["modified"] = True  # Modifies original object!

**Solution**: Create copies when modifying: ``data_value = dict(data_value)`` or
``data_value = data_value.copy()``

Best Practices
--------------

1. **Always use safe extraction pattern**: ``param = param or kwargs.get("param", default)``
2. **Use parameter mapping for interface adaptation**: Match different naming conventions
3. **Validate data types**: Check types before processing complex structures
4. **Use debug prints during development**: Inspect kwargs to understand data flow
5. **Document parameter names**: Make it clear what parameters events emit
6. **Copy mutable data when modifying**: Avoid side effects from shared references

Next Steps
----------

Now that you understand data flow, let's move on to :doc:`state_management` to
learn how to track execution state and monitor your workflows.

