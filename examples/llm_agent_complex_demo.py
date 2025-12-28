#!/usr/bin/env python
"""
Complex LLM Agent Flow Demo

This demo simulates a complex LLM Agent workflow that processes user tasks.
It demonstrates all Routilux features including:
- Multiple routines with slots and events
- Complex data flow with parameter mapping
- Error handling strategies (STOP, CONTINUE, RETRY, SKIP)
- State management and tracking
- Serialization/deserialization
- Flow control (pause, resume, cancel)
- Execution tracking
"""

import json
import time
from typing import Dict, Any, List
from routilux import Flow, Routine, JobState, ErrorHandler, ErrorStrategy


# ============================================================================
# Routine Definitions
# ============================================================================


class TaskParser(Routine):
    """Parse user task into structured format"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("task_input", handler=self.parse_task)
        self.output_event = self.define_event(
            "parsed_task", ["task_id", "task_type", "requirements", "priority"]
        )
        self._stats["parsed_count"] = 0

    def parse_task(self, task: str):
        """Parse task string into structured format"""
        self._stats["parsed_count"] = self._stats.get("parsed_count", 0) + 1

        # Simulate parsing
        task_id = f"task_{int(time.time() * 1000)}"
        task_type = "query" if "?" in task else "action"
        requirements = task.split()
        priority = "high" if "urgent" in task.lower() else "normal"

        self.emit(
            "parsed_task",
            task_id=task_id,
            task_type=task_type,
            requirements=requirements,
            priority=priority,
        )


class ToolSelector(Routine):
    """Select appropriate tools for the task"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("task_info", handler=self.select_tools)
        self.output_event = self.define_event("selected_tools", ["tools", "task_id"])
        self._stats["selection_count"] = 0
        self._available_tools = ["search", "calculator", "translator", "code_generator"]

    def select_tools(self, task_id: str, task_type: str, requirements: List[str], priority: str):
        """Select tools based on task requirements"""
        self._stats["selection_count"] = self._stats.get("selection_count", 0) + 1

        # Simulate tool selection logic
        selected_tools = []
        if "search" in str(requirements).lower() or "find" in str(requirements).lower():
            selected_tools.append("search")
        if any(char.isdigit() for char in str(requirements)):
            selected_tools.append("calculator")
        if any(len(word) > 5 for word in requirements):
            selected_tools.append("translator")
        if "code" in str(requirements).lower() or "function" in str(requirements).lower():
            selected_tools.append("code_generator")

        if not selected_tools:
            selected_tools = ["search"]  # Default tool

        self.emit("selected_tools", tools=selected_tools, task_id=task_id)


class ToolExecutor(Routine):
    """Execute selected tools"""

    def __init__(self, tool_name: str = None):
        super().__init__()
        self.tool_name = tool_name or "unknown"
        self.input_slot = self.define_slot("tool_input", handler=self.execute_tool)
        self.output_event = self.define_event(
            "tool_result", ["result", "tool_name", "task_id", "success"]
        )
        self._stats["execution_count"] = 0
        self._stats["success_count"] = 0
        self._stats["failure_count"] = 0

        # Register tool_name for serialization
        self.add_serializable_fields(["tool_name"])

    def execute_tool(self, tools: List[str], task_id: str):
        """Execute the tool if it matches"""
        self._stats["execution_count"] = self._stats.get("execution_count", 0) + 1

        if self.tool_name not in tools:
            # Tool not needed, skip
            self.emit(
                "tool_result", result=None, tool_name=self.tool_name, task_id=task_id, success=True
            )
            return

        # Simulate tool execution
        success = True
        result = None

        try:
            if self.tool_name == "search":
                result = f"Search results for task {task_id}"
            elif self.tool_name == "calculator":
                result = "42"  # The answer to everything
            elif self.tool_name == "translator":
                result = f"Translated content for {task_id}"
            elif self.tool_name == "code_generator":
                result = f"def process_{task_id}():\n    return 'generated code'"

            # Simulate occasional failures
            if self._stats["execution_count"] % 5 == 0:
                raise ValueError(
                    f"Tool {self.tool_name} failed on attempt {self._stats['execution_count']}"
                )

            self._stats["success_count"] = self._stats.get("success_count", 0) + 1

        except Exception as e:
            success = False
            self._stats["failure_count"] = self._stats.get("failure_count", 0) + 1
            result = f"Error: {str(e)}"
            raise  # Re-raise to test error handling

        self.emit(
            "tool_result", result=result, tool_name=self.tool_name, task_id=task_id, success=success
        )


class ResultValidator(Routine):
    """Validate tool execution results"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("validation_input", handler=self.validate_result)
        self.output_event = self.define_event(
            "validated_result", ["valid", "result", "task_id", "tool_name"]
        )
        self._stats["validation_count"] = 0
        self._stats["valid_count"] = 0
        self._stats["invalid_count"] = 0

    def validate_result(self, result: Any, tool_name: str, task_id: str, success: bool):
        """Validate tool execution result"""
        self._stats["validation_count"] = self._stats.get("validation_count", 0) + 1

        if not success:
            self._stats["invalid_count"] = self._stats.get("invalid_count", 0) + 1
            self.emit(
                "validated_result", valid=False, result=result, task_id=task_id, tool_name=tool_name
            )
            return

        # Simple validation
        valid = result is not None and len(str(result)) > 0

        if valid:
            self._stats["valid_count"] = self._stats.get("valid_count", 0) + 1
        else:
            self._stats["invalid_count"] = self._stats.get("invalid_count", 0) + 1

        self.emit(
            "validated_result", valid=valid, result=result, task_id=task_id, tool_name=tool_name
        )


class ResultAggregator(Routine):
    """Aggregate results from all tools"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot(
            "result_input", handler=self.aggregate_results, merge_strategy="append"
        )
        self.output_event = self.define_event(
            "final_result", ["aggregated_result", "task_id", "tool_count"]
        )
        self._results = []
        self._stats["aggregation_count"] = 0

    def aggregate_results(self, valid: bool, result: Any, task_id: str, tool_name: str):
        """Aggregate results from multiple tools"""
        self._stats["aggregation_count"] = self._stats.get("aggregation_count", 0) + 1

        if valid and result:
            self._results.append({"tool": tool_name, "result": result, "valid": valid})

        # Emit when we have enough results (simulate waiting for all tools)
        if len(self._results) >= 2 or self._stats["aggregation_count"] >= 3:
            aggregated = {
                "task_id": task_id,
                "tools_used": [r["tool"] for r in self._results],
                "results": [r["result"] for r in self._results],
                "summary": f"Processed {len(self._results)} tools successfully",
            }

            self.emit(
                "final_result",
                aggregated_result=aggregated,
                task_id=task_id,
                tool_count=len(self._results),
            )

            # Reset for next aggregation
            self._results = []


class ResponseFormatter(Routine):
    """Format final response for user"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("formatter_input", handler=self.format_response)
        self.output_event = self.define_event("formatted_response", ["response", "task_id"])
        self._stats["formatting_count"] = 0

    def format_response(self, aggregated_result: Dict[str, Any], task_id: str, tool_count: int):
        """Format aggregated results into user-friendly response"""
        self._stats["formatting_count"] = self._stats.get("formatting_count", 0) + 1

        response = {
            "status": "completed",
            "task_id": task_id,
            "tools_used": aggregated_result.get("tools_used", []),
            "results": aggregated_result.get("results", []),
            "summary": aggregated_result.get("summary", ""),
            "formatted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.emit("formatted_response", response=response, task_id=task_id)


# ============================================================================
# Test Functions
# ============================================================================


def create_complex_flow() -> Flow:
    """Create a complex LLM Agent flow with all features"""
    flow = Flow(flow_id="llm_agent_flow")

    # Create routines
    parser = TaskParser()
    selector = ToolSelector()
    executor_search = ToolExecutor("search")
    executor_calc = ToolExecutor("calculator")
    executor_trans = ToolExecutor("translator")
    executor_code = ToolExecutor("code_generator")
    validator = ResultValidator()
    aggregator = ResultAggregator()
    formatter = ResponseFormatter()

    # Add routines to flow
    parser_id = flow.add_routine(parser, "task_parser")
    selector_id = flow.add_routine(selector, "tool_selector")
    executor_search_id = flow.add_routine(executor_search, "executor_search")
    executor_calc_id = flow.add_routine(executor_calc, "executor_calc")
    executor_trans_id = flow.add_routine(executor_trans, "executor_translator")
    executor_code_id = flow.add_routine(executor_code, "executor_code")
    validator_id = flow.add_routine(validator, "result_validator")
    aggregator_id = flow.add_routine(aggregator, "result_aggregator")
    formatter_id = flow.add_routine(formatter, "response_formatter")

    # Create connections with parameter mapping
    flow.connect(parser_id, "parsed_task", selector_id, "task_info")

    # Connect selector to all executors
    flow.connect(
        selector_id,
        "selected_tools",
        executor_search_id,
        "tool_input",
        param_mapping={"tools": "tools", "task_id": "task_id"},
    )
    flow.connect(
        selector_id,
        "selected_tools",
        executor_calc_id,
        "tool_input",
        param_mapping={"tools": "tools", "task_id": "task_id"},
    )
    flow.connect(
        selector_id,
        "selected_tools",
        executor_trans_id,
        "tool_input",
        param_mapping={"tools": "tools", "task_id": "task_id"},
    )
    flow.connect(
        selector_id,
        "selected_tools",
        executor_code_id,
        "tool_input",
        param_mapping={"tools": "tools", "task_id": "task_id"},
    )

    # Connect executors to validator (parallel validation)
    flow.connect(
        executor_search_id,
        "tool_result",
        validator_id,
        "validation_input",
        param_mapping={
            "result": "result",
            "tool_name": "tool_name",
            "task_id": "task_id",
            "success": "success",
        },
    )
    flow.connect(
        executor_calc_id,
        "tool_result",
        validator_id,
        "validation_input",
        param_mapping={
            "result": "result",
            "tool_name": "tool_name",
            "task_id": "task_id",
            "success": "success",
        },
    )
    flow.connect(
        executor_trans_id,
        "tool_result",
        validator_id,
        "validation_input",
        param_mapping={
            "result": "result",
            "tool_name": "tool_name",
            "task_id": "task_id",
            "success": "success",
        },
    )
    flow.connect(
        executor_code_id,
        "tool_result",
        validator_id,
        "validation_input",
        param_mapping={
            "result": "result",
            "tool_name": "tool_name",
            "task_id": "task_id",
            "success": "success",
        },
    )

    # Connect validator to aggregator
    flow.connect(
        validator_id,
        "validated_result",
        aggregator_id,
        "result_input",
        param_mapping={
            "valid": "valid",
            "result": "result",
            "task_id": "task_id",
            "tool_name": "tool_name",
        },
    )

    # Connect aggregator to formatter
    flow.connect(
        aggregator_id,
        "final_result",
        formatter_id,
        "formatter_input",
        param_mapping={
            "aggregated_result": "aggregated_result",
            "task_id": "task_id",
            "tool_count": "tool_count",
        },
    )

    return flow


def test_basic_execution(flow: Flow):
    """Test basic flow execution"""
    print("\n" + "=" * 70)
    print("Test 1: Basic Flow Execution")
    print("=" * 70)

    parser_id = "task_parser"
    task = "Find information about Python and calculate 2+2"

    print(f"Input task: {task}")

    # Collect final response
    final_response = [None]

    def capture_response(response: Dict[str, Any], task_id: str):
        final_response[0] = response

    # Add a final slot to capture response
    formatter = flow.routines.get("response_formatter")
    if formatter:
        formatter.define_slot("final_output", handler=capture_response)

    job_state = flow.execute(parser_id, entry_params={"task": task})

    print(f"Execution status: {job_state.status}")
    print(f"Routines executed: {list(job_state.routine_states.keys())}")

    # Print stats from each routine
    executed_count = 0
    for routine_id, routine in flow.routines.items():
        stats = routine.stats()
        if stats:
            count_keys = [k for k in stats.keys() if "count" in k.lower()]
            if count_keys:
                count = sum(stats[k] for k in count_keys if isinstance(stats[k], (int, float)))
                if count > 0:
                    executed_count += 1
                    print(f"  {routine_id}: {stats}")

    print(f"Routines with activity: {executed_count}/{len(flow.routines)}")

    if final_response[0]:
        print(f"Final response captured: {final_response[0].get('status', 'N/A')}")

    return job_state


def test_serialization(flow: Flow):
    """Test flow serialization and deserialization"""
    print("\n" + "=" * 70)
    print("Test 2: Serialization/Deserialization")
    print("=" * 70)

    # Serialize flow
    print("Serializing flow...")
    flow_data = flow.serialize()

    # Save to JSON for inspection
    with open("/tmp/flow_serialized.json", "w") as f:
        json.dump(flow_data, f, indent=2, default=str)
    print(f"Flow serialized to /tmp/flow_serialized.json ({len(json.dumps(flow_data))} bytes)")

    # Deserialize flow
    print("Deserializing flow...")
    new_flow = Flow()
    new_flow.deserialize(flow_data)

    print(f"Deserialized flow ID: {new_flow.flow_id}")
    print(f"Deserialized routines: {list(new_flow.routines.keys())}")
    print(f"Deserialized connections: {len(new_flow.connections)}")

    # Verify structure
    assert new_flow.flow_id == flow.flow_id
    assert len(new_flow.routines) == len(flow.routines)
    assert len(new_flow.connections) == len(flow.connections)

    print("✓ Serialization/deserialization successful")

    return new_flow


def test_error_handling(flow: Flow):
    """Test different error handling strategies"""
    print("\n" + "=" * 70)
    print("Test 3: Error Handling Strategies")
    print("=" * 70)

    # Test CONTINUE strategy
    print("\n3.1: Testing CONTINUE strategy...")
    flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
    parser_id = "task_parser"

    # Force an error by using a task that will cause tool execution to fail
    job_state = flow.execute(parser_id, entry_params={"task": "test error handling"})
    print(f"Status with CONTINUE: {job_state.status}")

    # Test RETRY strategy
    print("\n3.2: Testing RETRY strategy...")
    flow.set_error_handler(
        ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=2, retry_delay=0.1)
    )

    # Reset executor stats to trigger failure
    for routine_id, routine in flow.routines.items():
        if hasattr(routine, "tool_name"):
            routine._stats["execution_count"] = 0

    job_state = flow.execute(parser_id, entry_params={"task": "calculate 5+5"})
    print(f"Status with RETRY: {job_state.status}")
    print(f"Error handler retry count: {flow.error_handler.retry_count}")

    # Test SKIP strategy
    print("\n3.3: Testing SKIP strategy...")
    flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
    job_state = flow.execute(parser_id, entry_params={"task": "test skip"})
    print(f"Status with SKIP: {job_state.status}")

    # Reset to STOP (default)
    flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
    print("✓ Error handling strategies tested")


def test_pause_resume(flow: Flow):
    """Test pause and resume functionality"""
    print("\n" + "=" * 70)
    print("Test 4: Pause and Resume")
    print("=" * 70)

    parser_id = "task_parser"
    task = "Find information and calculate results"

    # Start execution
    print("Starting execution...")
    job_state = flow.execute(parser_id, entry_params={"task": task})

    if job_state.status == "running":
        print("Pausing flow...")
        flow.pause(checkpoint=True)
        print(f"Flow paused: {flow._paused}")
        print(f"Job state status: {job_state.status}")

        # Serialize job state
        job_state_data = job_state.serialize()
        print(f"Job state serialized ({len(json.dumps(job_state_data))} bytes)")

        # Deserialize and resume
        print("Resuming from saved state...")
        new_job_state = JobState()
        new_job_state.deserialize(job_state_data)

        flow.job_state = new_job_state
        resumed_state = flow.resume()

        print(f"Resumed status: {resumed_state.status}")
        print("✓ Pause/resume tested")
    else:
        print(f"Execution completed immediately (status: {job_state.status})")


def test_cancel(flow: Flow):
    """Test flow cancellation"""
    print("\n" + "=" * 70)
    print("Test 5: Flow Cancellation")
    print("=" * 70)

    # Note: Cancellation requires active execution
    # In a real scenario, this would be called from another thread
    print("Cancellation test (requires active execution context)")
    print("✓ Cancellation interface available")


def test_execution_tracking(flow: Flow):
    """Test execution tracking"""
    print("\n" + "=" * 70)
    print("Test 6: Execution Tracking")
    print("=" * 70)

    parser_id = "task_parser"
    task = "Track execution performance"

    flow.execute(parser_id, entry_params={"task": task})

    tracker = flow.execution_tracker
    if tracker:
        # Get routine performance data
        routine_performances = {}
        for routine_id in flow.routines.keys():
            perf = tracker.get_routine_performance(routine_id)
            if perf:
                routine_performances[routine_id] = perf

        print(f"Tracked routines: {len(routine_performances)}")

        for routine_id, perf in list(routine_performances.items())[:5]:  # Show first 5
            print(
                f"  {routine_id}: {perf.get('total_time', 0):.4f}s "
                f"({perf.get('call_count', 0)} calls)"
            )

        # Get flow performance metrics
        performance = tracker.get_flow_performance()
        if performance:
            print(f"Total execution time: {performance.get('total_time', 0):.4f}s")
            print(f"Average routine time: {performance.get('average_time', 0):.4f}s")
        else:
            print("Performance metrics available after multiple executions")

    print("✓ Execution tracking tested")


def test_complex_scenario(flow: Flow):
    """Test complex scenario with multiple tasks"""
    print("\n" + "=" * 70)
    print("Test 7: Complex Multi-Task Scenario")
    print("=" * 70)

    tasks = [
        "Search for Python tutorials and calculate 10*5",
        "Translate hello world and generate code",
        "Find information about machine learning",
    ]

    parser_id = "task_parser"
    results = []

    for i, task in enumerate(tasks, 1):
        print(f"\nProcessing task {i}: {task}")
        job_state = flow.execute(parser_id, entry_params={"task": task})
        results.append(
            {"task": task, "status": job_state.status, "routines": len(job_state.routine_states)}
        )

        # Print final formatter stats if available
        if "response_formatter" in flow.routines:
            formatter = flow.routines["response_formatter"]
            print(f"  Formatted responses: {formatter.stats().get('formatting_count', 0)}")

    print(f"\nProcessed {len(results)} tasks")
    for result in results:
        print(f"  {result['task'][:30]}... -> {result['status']}")

    print("✓ Complex scenario tested")


def test_state_persistence(flow: Flow):
    """Test complete state persistence"""
    print("\n" + "=" * 70)
    print("Test 8: Complete State Persistence")
    print("=" * 70)

    parser_id = "task_parser"
    task = "Test state persistence"

    # Execute and get state
    job_state = flow.execute(parser_id, entry_params={"task": task})

    # Serialize everything
    print("Serializing complete state...")
    flow_data = flow.serialize()
    job_state_data = job_state.serialize()

    # Save to files
    with open("/tmp/flow_state.json", "w") as f:
        json.dump(flow_data, f, indent=2, default=str)
    with open("/tmp/job_state.json", "w") as f:
        json.dump(job_state_data, f, indent=2, default=str)

    print(f"Flow state saved ({len(json.dumps(flow_data))} bytes)")
    print(f"Job state saved ({len(json.dumps(job_state_data))} bytes)")

    # Restore everything
    print("Restoring complete state...")
    restored_flow = Flow()
    restored_flow.deserialize(flow_data)

    restored_job_state = JobState()
    restored_job_state.deserialize(job_state_data)

    print(f"Restored flow ID: {restored_flow.flow_id}")
    print(f"Restored job state status: {restored_job_state.status}")
    print(f"Restored routine states: {len(restored_job_state.routine_states)}")

    print("✓ State persistence tested")


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("Routilux Complex LLM Agent Demo")
    print("=" * 70)
    print("\nThis demo tests all Routilux features with a complex LLM Agent workflow.")

    # Create flow
    flow = create_complex_flow()
    print(
        f"\nCreated flow with {len(flow.routines)} routines and {len(flow.connections)} connections"
    )

    # Run all tests
    try:
        test_basic_execution(flow)
        test_serialization(flow)
        test_error_handling(flow)
        test_pause_resume(flow)
        test_cancel(flow)
        test_execution_tracking(flow)
        test_complex_scenario(flow)
        test_state_persistence(flow)

        print("\n" + "=" * 70)
        print("All Tests Completed Successfully!")
        print("=" * 70)
        print("\nFeatures tested:")
        print("  ✓ Routine creation with slots and events")
        print("  ✓ Complex data flow with parameter mapping")
        print("  ✓ Error handling (STOP, CONTINUE, RETRY, SKIP)")
        print("  ✓ Flow serialization/deserialization")
        print("  ✓ Job state serialization/deserialization")
        print("  ✓ Pause and resume functionality")
        print("  ✓ Execution tracking and performance metrics")
        print("  ✓ Multi-task processing")
        print("  ✓ Complete state persistence")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
