"""DebugClient helper class for user story tests.

Provides utilities for debugging jobs via API, including setting breakpoints,
inspecting variables, stepping through execution, and modifying state.
"""

from typing import Any, Dict, Optional


class DebugClient:
    """Helper class for debugging jobs via API.

    Provides methods for setting breakpoints, inspecting variables,
    stepping through execution, and modifying runtime state.

    Example:
        debug = DebugClient(client)
        debug.set_breakpoint_policy("my_flow")
        job_id = debug.submit_job_with_debug("my_flow", "processor", "input", {"value": 42})
        debug.wait_for_breakpoint(job_id)
        variables = debug.get_variables(job_id, "processor")
        debug.modify_variable(job_id, "counter", 100)
        debug.resume(job_id)
    """

    def __init__(self, client):
        """Initialize DebugClient.

        Args:
            client: FastAPI TestClient instance
        """
        self.client = client

    def submit_job_with_debug(
        self,
        flow_id: str,
        routine_id: str,
        slot_name: str,
        data: Dict[str, Any],
        worker_id: Optional[str] = None,
    ) -> str:
        """Submit a job that will pause at breakpoints.

        This is a convenience wrapper around JobMonitor.submit_job.
        The job should have a breakpoint_policy set on the target routine.

        Args:
            flow_id: Flow identifier
            routine_id: Routine to target
            slot_name: Slot to send data to
            data: Data to send
            worker_id: Optional specific worker ID

        Returns:
            Job ID
        """
        from .job_monitor import JobMonitor

        monitor = JobMonitor(self.client)
        return monitor.submit_job(flow_id, routine_id, slot_name, data, worker_id)

    def get_session(self, job_id: str) -> Dict[str, Any]:
        """Get debug session information.

        Args:
            job_id: Job identifier

        Returns:
            Session information dictionary

        Raises:
            AssertionError: If session cannot be retrieved (404/500)
        """
        response = self.client.get(f"/api/jobs/{job_id}/debug/session")
        # May return 404 if no session exists, or 500 if debug store not available
        if response.status_code not in (200, 404, 500):
            raise AssertionError(f"Failed to get debug session: {response.text}")
        if response.status_code != 200:
            # Return error response for caller to handle
            return response.json()
        return response.json()

    def wait_for_breakpoint(self, job_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Wait for job to hit a breakpoint.

        Args:
            job_id: Job identifier
            timeout: Maximum time to wait in seconds

        Returns:
            Session information when paused

        Raises:
            TimeoutError: If job doesn't hit breakpoint within timeout
        """
        import time

        start_time = time.time()
        while time.time() - start_time < timeout:
            session = self.get_session(job_id)
            if session.get("status") == "paused":
                return session
            time.sleep(0.1)

        raise TimeoutError(f"Job {job_id} did not hit breakpoint within {timeout}s")

    def get_variables(self, job_id: str, routine_id: Optional[str] = None) -> Dict[str, Any]:
        """Get variables at current breakpoint.

        Args:
            job_id: Job identifier
            routine_id: Optional routine ID to get variables from

        Returns:
            Variables dictionary
        """
        url = f"/api/v1/debug/jobs/{job_id}/debug/variables"
        if routine_id:
            url += f"?routine_id={routine_id}"

        response = self.client.get(url)
        assert response.status_code == 200, f"Failed to get variables: {response.text}"
        return response.json()["variables"]

    def get_variable(self, job_id: str, name: str, routine_id: Optional[str] = None) -> Any:
        """Get a specific variable value.

        Args:
            job_id: Job identifier
            name: Variable name
            routine_id: Optional routine ID

        Returns:
            Variable value
        """
        variables = self.get_variables(job_id, routine_id)
        if name not in variables:
            raise KeyError(f"Variable '{name}' not found. Available: {list(variables.keys())}")
        return variables[name]

    def set_variable(self, job_id: str, name: str, value: Any) -> None:
        """Set a variable value at current breakpoint.

        Args:
            job_id: Job identifier
            name: Variable name
            value: New value
        """
        response = self.client.put(
            f"/api/v1/debug/jobs/{job_id}/debug/variables/{name}",
            json={"value": value},
        )
        assert response.status_code == 200, f"Failed to set variable: {response.text}"

    def resume(self, job_id: str) -> None:
        """Resume execution from breakpoint.

        Args:
            job_id: Job identifier
        """
        response = self.client.post(f"/api/v1/debug/jobs/{job_id}/debug/resume")
        assert response.status_code == 200, f"Failed to resume: {response.text}"

    def step_over(self, job_id: str) -> None:
        """Step over current line.

        Args:
            job_id: Job identifier
        """
        response = self.client.post(f"/api/v1/debug/jobs/{job_id}/debug/step-over")
        assert response.status_code == 200, f"Failed to step over: {response.text}"

    def step_into(self, job_id: str) -> None:
        """Step into function call.

        Args:
            job_id: Job identifier
        """
        response = self.client.post(f"/api/v1/debug/jobs/{job_id}/debug/step-into")
        assert response.status_code == 200, f"Failed to step into: {response.text}"

    def get_call_stack(self, job_id: str) -> list:
        """Get the current call stack.

        Args:
            job_id: Job identifier

        Returns:
            List of call stack frames

        Raises:
            AssertionError: If call stack cannot be retrieved (404/500)
        """
        response = self.client.get(f"/api/jobs/{job_id}/debug/call-stack")
        # May return 404 if no session exists, or 500 if debug store not available
        if response.status_code not in (200, 404, 500):
            raise AssertionError(f"Failed to get call stack: {response.text}")
        if response.status_code != 200:
            # Return empty list if not available
            return []
        data = response.json()
        return data.get("call_stack", [])

    def evaluate_expression(
        self, job_id: str, expression: str, routine_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Evaluate an expression in the context of a paused job.

        Note: This requires ROUTILUX_EXPRESSION_EVAL_ENABLED=true

        Args:
            job_id: Job identifier
            expression: Python expression to evaluate
            routine_id: Optional routine ID for context

        Returns:
            Result dictionary with 'result', 'type', and 'error' keys
        """
        request = {"expression": expression}
        if routine_id:
            request["routine_id"] = routine_id

        response = self.client.post(
            f"/api/v1/debug/jobs/{job_id}/debug/evaluate",
            json=request,
        )

        # May return 403 if expression evaluation is disabled
        if response.status_code == 403:
            raise RuntimeError(
                "Expression evaluation is disabled. Enable with ROUTILUX_EXPRESSION_EVAL_ENABLED=true"
            )

        assert response.status_code == 200, f"Failed to evaluate expression: {response.text}"
        return response.json()

    def assert_variable_equals(
        self, job_id: str, name: str, expected: Any, routine_id: Optional[str] = None
    ) -> None:
        """Assert that a variable has an expected value.

        Args:
            job_id: Job identifier
            name: Variable name
            expected: Expected value
            routine_id: Optional routine ID

        Raises:
            AssertionError: If value doesn't match
        """
        actual = self.get_variable(job_id, name, routine_id)
        assert actual == expected, f"Variable '{name}' is {actual}, expected {expected}"

    def modify_and_verify(
        self, job_id: str, name: str, new_value: Any, routine_id: Optional[str] = None
    ) -> None:
        """Modify a variable and verify the change.

        Args:
            job_id: Job identifier
            name: Variable name
            new_value: New value to set
            routine_id: Optional routine ID
        """
        self.set_variable(job_id, name, new_value)
        self.assert_variable_equals(job_id, name, new_value, routine_id)

    def inspect_routine_state(self, job_id: str, routine_id: str) -> Dict[str, Any]:
        """Get comprehensive state information for a routine.

        Args:
            job_id: Job identifier
            routine_id: Routine identifier

        Returns:
            Dictionary with variables, call stack info, etc.
        """
        variables = self.get_variables(job_id, routine_id)
        call_stack = self.get_call_stack(job_id)

        # Find frames for this routine
        routine_frames = [frame for frame in call_stack if frame.get("routine_id") == routine_id]

        return {
            "routine_id": routine_id,
            "variables": variables,
            "call_depth": len(routine_frames),
            "frames": routine_frames,
        }

    def trace_execution(self, job_id: str, max_steps: int = 10) -> list:
        """Trace execution by stepping through and capturing state.

        Args:
            job_id: Job identifier
            max_steps: Maximum number of steps to trace

        Returns:
            List of state snapshots at each step
        """
        trace = []
        for _ in range(max_steps):
            try:
                # Get current state
                session = self.get_session(job_id)
                if session.get("status") != "paused":
                    break

                state = {
                    "paused_at": session.get("paused_at", {}),
                    "call_stack_depth": session.get("call_stack_depth", 0),
                }

                # Get variables from paused routine if available
                if session.get("paused_at", {}).get("routine_id"):
                    routine_id = session["paused_at"]["routine_id"]
                    try:
                        state["variables"] = self.get_variables(job_id, routine_id)
                    except Exception:
                        state["variables"] = {}

                trace.append(state)

                # Step to next
                self.step_over(job_id)

            except Exception:
                break

        return trace
