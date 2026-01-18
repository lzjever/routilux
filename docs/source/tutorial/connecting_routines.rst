Connecting Routines with Runtime
=================================

In this tutorial, you'll learn about different connection patterns in Routilux,
including one-to-many, many-to-one, and complex branching patterns.

.. note:: **New Architecture**

   This tutorial uses the Runtime-based architecture. All execution goes through
   Runtime, not direct Flow.execute() calls.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Connect one event to multiple slots (fan-out)
- Connect multiple events to one slot (fan-in)
- Understand merge strategies for handling multiple inputs
- Build branching and converging workflows
- Register and execute flows with Runtime

Step 1: One-to-Many Connections (Fan-Out)
------------------------------------------

A single event can be connected to multiple slots. This is useful when you want
to send the same data to multiple processors:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def generate(slot_data, policy_message, job_state):
               trigger_list = slot_data.get("trigger", [])
               value = trigger_list[0].get("value", "test") if trigger_list else "test"
               self.emit("output", data=value)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class ProcessorA(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               print(f"Processor A received: {data_value}")

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   class ProcessorB(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               print(f"Processor B received: {data_value}")

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="fanout_flow")

   source = DataSource()
   processor_a = ProcessorA()
   processor_b = ProcessorB()

   flow.add_routine(source, "source")
   flow.add_routine(processor_a, "processor_a")
   flow.add_routine(processor_b, "processor_b")

   # Connect one event to multiple slots
   flow.connect("source", "output", "processor_a", "input")
   flow.connect("source", "output", "processor_b", "input")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("fanout_flow", flow)

   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("fanout_flow", entry_params={"value": "Hello"})
       runtime.wait_until_all_jobs_finished(timeout=5.0)
       print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Processor A received: Hello
   Processor B received: Hello
   Status: completed

**Key Points**:

- One event can connect to multiple slots
- All connected slots receive the same data
- Both processors execute when data arrives
- This pattern is called "fan-out"

Step 2: Many-to-One Connections (Fan-In)
----------------------------------------

Multiple events can connect to the same slot. This is useful for aggregating
data from multiple sources. By default, new data replaces old data:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class SourceA(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data", "source"])

           def generate(slot_data, policy_message, job_state):
               self.emit("output", data="Data from A", source="A")

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class SourceB(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data", "source"])

           def generate(slot_data, policy_message, job_state):
               self.emit("output", data="Data from B", source="B")

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class Aggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def aggregate(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               for item in input_list:
                   data = item.get("data", "")
                   source = item.get("source", "unknown")
                   print(f"Aggregator received: {data} from {source}")

                   # Store in JobState
                   job_state.shared_log.append({"from": source, "data": data})

           self.set_logic(aggregate)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="fanin_flow")

   source_a = SourceA()
   source_b = SourceB()
   aggregator = Aggregator()

   flow.add_routine(source_a, "source_a")
   flow.add_routine(source_b, "source_b")
   flow.add_routine(aggregator, "aggregator")

   # Connect multiple events to one slot
   flow.connect("source_a", "output", "aggregator", "input")
   flow.connect("source_b", "output", "aggregator", "input")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("fanin_flow", flow)

   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("fanin_flow")
       runtime.wait_until_all_jobs_finished(timeout=5.0)

       print(f"Status: {job_state.status}")
       print(f"Total records: {len(job_state.shared_log)}")

**Expected Output**:

.. code-block:: text

   Aggregator received: Data from A from A
   Aggregator received: Data from B from B
   Status: completed
   Total records: 2

**Key Points**:

- Multiple events can connect to the same slot
- By default, "override" strategy (new data replaces old in slot queue)
- Each event arrival triggers the routine
- Use JobState.shared_log to collect all results

.. warning:: **Event Ordering**

   The order of event processing is not guaranteed in concurrent mode.
   For guaranteed ordering, use sequential execution or implement
   explicit synchronization in your logic.

Step 3: Understanding Merge Strategies
---------------------------------------

Merge strategies control how data is handled when multiple events connect to one slot.
With activation policies, merge behavior is handled differently - the policy
decides what data to pass to the logic function.

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import all_slots_ready_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class Source1(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["value"])

           def generate(slot_data, policy_message, job_state):
               self.emit("output", value=1)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class Source2(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["value"])

           def generate(slot_data, policy_message, job_state):
               self.emit("output", value=2)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class AllReadyReceiver(Routine):
       """Receives data only when all slots have data"""
       def __init__(self):
           super().__init__()
           self.input1 = self.add_slot("input1")
           self.input2 = self.add_slot("input2")

           def receive(slot_data, policy_message, job_state):
               input1_list = slot_data.get("input1", [])
               input2_list = slot_data.get("input2", [])

               val1 = input1_list[0].get("value") if input1_list else None
               val2 = input2_list[0].get("value") if input2_list else None

               print(f"Received: val1={val1}, val2={val2}")

               # Store in JobState
               job_state.update_routine_state("receiver", {"received_both": True})

           self.set_logic(receive)
           self.set_activation_policy(all_slots_ready_policy())

   # Create flow
   flow = Flow(flow_id="merge_flow")

   source1 = Source1()
   source2 = Source2()
   receiver = AllReadyReceiver()

   flow.add_routine(source1, "source1")
   flow.add_routine(source2, "source2")
   flow.add_routine(receiver, "receiver")

   # Connect: both sources -> receiver
   flow.connect("source1", "output", "receiver", "input1")
   flow.connect("source2", "output", "receiver", "input2")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("merge_flow", flow)

   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("merge_flow")
       runtime.wait_until_all_jobs_finished(timeout=5.0)

       print(f"Status: {job_state.status}")
       receiver_state = job_state.get_routine_state("receiver", {})
       print(f"Receiver state: {receiver_state}")

**Expected Output**:

.. code-block:: text

   Received: val1=1, val2=2
   Status: completed
   Receiver state: {'received_both': True}

**Key Points**:

- Activation policies control when routines execute
- ``all_slots_ready_policy`` waits for all slots to have data
- Slot data is provided as a dictionary to the logic function
- Use ``slot_data.get("slot_name", [])`` pattern to access data

Step 4: Complex Branching Patterns
----------------------------------

You can create complex workflows with branching and converging paths:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def generate(slot_data, policy_message, job_state):
               trigger_list = slot_data.get("trigger", [])
               value = trigger_list[0].get("value", "test") if trigger_list else "test"
               self.emit("output", data=value)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class Processor1(Routine):
       def __init__(self):
           super().__init__()
           self.set_config(name="UPPER")
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               name = self.get_config("name", "P1")
               result = f"{name}: {data_value.upper()}"
               print(f"Processor1: {result}")
               self.emit("output", result=result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   class Processor2(Routine):
       def __init__(self):
           super().__init__()
           self.set_config(name="lower")
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               name = self.get_config("name", "P2")
               result = f"{name}: {data_value.lower()}"
               print(f"Processor2: {result}")
               self.emit("output", result=result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   class FinalAggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def aggregate(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               results = []
               for item in input_list:
                   result = item.get("result", "")
                   if result:
                       results.append(result)
                       print(f"Final Aggregator received: {result}")

               # Store all results
               job_state.update_routine_state("aggregator", {"results": results})

           self.set_logic(aggregate)
           self.set_activation_policy(immediate_policy())

   # Create flow with branching pattern
   flow = Flow(flow_id="branching_flow")

   source = DataSource()
   proc1 = Processor1()
   proc2 = Processor2()
   aggregator = FinalAggregator()

   flow.add_routine(source, "source")
   flow.add_routine(proc1, "processor1")
   flow.add_routine(proc2, "processor2")
   flow.add_routine(aggregator, "aggregator")

   # Branch: source -> processor1 and processor2
   flow.connect("source", "output", "processor1", "input")
   flow.connect("source", "output", "processor2", "input")

   # Converge: processor1 and processor2 -> aggregator
   flow.connect("processor1", "output", "aggregator", "input")
   flow.connect("processor2", "output", "aggregator", "input")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("branching_flow", flow)

   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("branching_flow", entry_params={"value": "Hello"})
       runtime.wait_until_all_jobs_finished(timeout=5.0)

       print(f"Status: {job_state.status}")
       agg_state = job_state.get_routine_state("aggregator", {})
       print(f"Collected {len(agg_state.get('results', []))} results")

**Expected Output**:

.. code-block:: text

   Processor1: UPPER: HELLO
   Processor2: lower: hello
   Final Aggregator received: UPPER: HELLO
   Final Aggregator received: lower: hello
   Status: completed
   Collected 2 results

**Key Points**:

- You can create complex branching and converging patterns
- Multiple processors can execute independently
- Aggregators can collect results from multiple sources
- Use JobState for collecting results across executions

Common Pitfalls
---------------

**Pitfall 1: Forgetting to register flows**

.. code-block:: python
   :emphasize-lines: 5

   flow = Flow(flow_id="my_flow")
   # ... add routines ...

   # Missing: FlowRegistry.get_instance().register_by_name("my_flow", flow)
   runtime = Runtime()
   job_state = runtime.exec("my_flow")  # ValueError!

**Solution**: Always register flows before execution.

**Pitfall 2: Not using activation policy**

.. code-block:: python
   :emphasize-lines: 6

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           # Missing: self.set_activation_policy(...)

**Solution**: Always set an activation policy.

**Pitfall 3: Wrong slot data access pattern**

.. code-block:: python
   :emphasize-lines: 3

   def logic(slot_data, policy_message, job_state):
       data = slot_data["input"]  # Might return None!
       value = data[0]["value"]  # IndexError if None!

**Solution**: Use safe access pattern:

.. code-block:: python

   def logic(slot_data, policy_message, job_state):
       input_list = slot_data.get("input", [])
       value = input_list[0].get("value", "") if input_list else ""

Best Practices
--------------

1. **Use descriptive routine IDs**: Makes connections clearer
2. **Always register flows**: With FlowRegistry before execution
3. **Always set activation policy**: Routines won't execute without it
4. **Use safe slot data access**: ``slot_data.get("slot_name", [])``
5. **Use JobState for results**: Store collected data in JobState
6. **Use context manager**: ``with Runtime() as runtime:`` for cleanup

Next Steps
----------

Now that you understand connections, let's move on to :doc:`data_flow` to learn
about data extraction, parameter mapping, and how data flows through your
workflows.
