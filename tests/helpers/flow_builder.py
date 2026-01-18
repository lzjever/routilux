"""FlowBuilder helper class for user story tests.

Provides a fluent interface for building flows via API,
simulating interactive flow builder workflows.
"""

from typing import Any, Dict, List, Optional


class FlowBuilder:
    """Helper class for building flows via API.

    Provides a fluent interface for creating flows, adding routines,
    connecting them, validating, and exporting as DSL.

    Example:
        builder = FlowBuilder(client)
        flow = builder.create("my_flow") \
                      .add_routine("source", "data_source", {"count": 5}) \
                      .add_routine("processor", "data_transformer") \
                      .connect("source", "output", "processor", "input") \
                      .validate() \
                      .export_dsl()
    """

    def __init__(self, client, flow_id: Optional[str] = None):
        """Initialize FlowBuilder.

        Args:
            client: FastAPI TestClient instance
            flow_id: Optional flow ID to start with
        """
        self.client = client
        self.flow_id = flow_id
        self._routines: Dict[str, Dict[str, Any]] = {}
        self._connections: List[Dict[str, str]] = []

    def create_empty(self, flow_id: str) -> "FlowBuilder":
        """Create an empty flow.

        Args:
            flow_id: Unique flow identifier

        Returns:
            self for chaining
        """
        response = self.client.post(
            "/api/v1/flows",
            json={"flow_id": flow_id},
        )
        assert response.status_code == 201, f"Failed to create flow: {response.text}"
        self.flow_id = flow_id
        return self

    def create_from_dsl(self, flow_id: str, dsl: str, format: str = "yaml") -> "FlowBuilder":
        """Create a flow from DSL.

        Args:
            flow_id: Unique flow identifier
            dsl: DSL string (YAML or JSON)
            format: DSL format ("yaml" or "json")

        Returns:
            self for chaining
        """
        response = self.client.post(
            "/api/v1/flows",
            json={"flow_id": flow_id, "dsl": dsl},
        )
        assert response.status_code == 201, f"Failed to create flow from DSL: {response.text}"
        self.flow_id = flow_id
        return self

    def create_from_dsl_dict(self, flow_id: str, dsl_dict: Dict[str, Any]) -> "FlowBuilder":
        """Create a flow from DSL dictionary.

        Args:
            flow_id: Unique flow identifier
            dsl_dict: DSL as dictionary

        Returns:
            self for chaining
        """
        response = self.client.post(
            "/api/v1/flows",
            json={"flow_id": flow_id, "dsl_dict": dsl_dict},
        )
        assert response.status_code == 201, f"Failed to create flow from DSL dict: {response.text}"
        self.flow_id = flow_id
        return self

    def add_routine(
        self, routine_id: str, object_name: str, config: Optional[Dict[str, Any]] = None
    ) -> "FlowBuilder":
        """Add a routine to the flow.

        Args:
            routine_id: Unique routine identifier within flow
            object_name: Factory object name
            config: Optional routine configuration

        Returns:
            self for chaining
        """
        response = self.client.post(
            f"/api/v1/flows/{self.flow_id}/routines",
            json={"routine_id": routine_id, "object_name": object_name, "config": config or {}},
        )
        assert response.status_code == 200, f"Failed to add routine: {response.text}"
        self._routines[routine_id] = {"object_name": object_name, "config": config or {}}
        return self

    def add_connection(
        self,
        source_routine: str,
        source_event: str,
        target_routine: str,
        target_slot: str,
    ) -> "FlowBuilder":
        """Add a connection between routines.

        Args:
            source_routine: Source routine ID
            source_event: Source event name
            target_routine: Target routine ID
            target_slot: Target slot name

        Returns:
            self for chaining
        """
        response = self.client.post(
            f"/api/v1/flows/{self.flow_id}/connections",
            json={
                "source_routine": source_routine,
                "source_event": source_event,
                "target_routine": target_routine,
                "target_slot": target_slot,
            },
        )
        assert response.status_code == 200, f"Failed to add connection: {response.text}"
        self._connections.append(
            {
                "source_routine": source_routine,
                "source_event": source_event,
                "target_routine": target_routine,
                "target_slot": target_slot,
            }
        )
        return self

    def validate(self, allow_warnings: bool = True) -> "FlowBuilder":
        """Validate the flow structure.

        Args:
            allow_warnings: If True, warnings don't cause validation to fail

        Returns:
            self for chaining

        Raises:
            AssertionError: If flow validation fails (errors, or warnings if not allowed)
        """
        response = self.client.post(f"/api/v1/flows/{self.flow_id}/validate")
        assert response.status_code == 200, f"Validation request failed: {response.text}"
        data = response.json()

        # Check if there are errors (warnings are acceptable by default)
        if not data["valid"]:
            errors = data.get(
                "errors", [issue for issue in data.get("issues", []) if issue.startswith("Error:")]
            )
            if errors:
                raise AssertionError(f"Flow validation failed with errors: {errors}")
            elif not allow_warnings:
                warnings = data.get(
                    "warnings",
                    [issue for issue in data.get("issues", []) if issue.startswith("Warning:")],
                )
                if warnings:
                    raise AssertionError(f"Flow validation has warnings: {warnings}")
        return self

    def export_dsl(self, format: str = "yaml") -> str:
        """Export the flow as DSL.

        Args:
            format: Export format ("yaml" or "json")

        Returns:
            DSL string
        """
        response = self.client.get(f"/api/v1/flows/{self.flow_id}/dsl?format={format}")
        assert response.status_code == 200, f"Failed to export DSL: {response.text}"
        return response.json()["dsl"]

    def get_flow(self) -> Dict[str, Any]:
        """Get the complete flow information.

        Returns:
            Flow information dictionary
        """
        response = self.client.get(f"/api/v1/flows/{self.flow_id}")
        assert response.status_code == 200, f"Failed to get flow: {response.text}"
        return response.json()

    def get_routines(self) -> Dict[str, Dict[str, Any]]:
        """Get all routines in the flow.

        Returns:
            Dictionary of routine_id to routine info
        """
        response = self.client.get(f"/api/v1/flows/{self.flow_id}/routines")
        assert response.status_code == 200, f"Failed to get routines: {response.text}"
        return response.json()

    def get_connections(self) -> List[Dict[str, str]]:
        """Get all connections in the flow.

        Returns:
            List of connection info dictionaries
        """
        response = self.client.get(f"/api/v1/flows/{self.flow_id}/connections")
        assert response.status_code == 200, f"Failed to get connections: {response.text}"
        return response.json()

    def remove_routine(self, routine_id: str) -> "FlowBuilder":
        """Remove a routine from the flow.

        Args:
            routine_id: Routine ID to remove

        Returns:
            self for chaining
        """
        response = self.client.delete(f"/api/v1/flows/{self.flow_id}/routines/{routine_id}")
        assert response.status_code == 204, f"Failed to remove routine: {response.text}"
        self._routines.pop(routine_id, None)
        return self

    def remove_connection(self, connection_index: int) -> "FlowBuilder":
        """Remove a connection from the flow.

        Args:
            connection_index: Index of connection to remove

        Returns:
            self for chaining
        """
        response = self.client.delete(
            f"/api/v1/flows/{self.flow_id}/connections/{connection_index}"
        )
        assert response.status_code == 204, f"Failed to remove connection: {response.text}"
        if 0 <= connection_index < len(self._connections):
            self._connections.pop(connection_index)
        return self

    def delete(self) -> None:
        """Delete the flow."""
        response = self.client.delete(f"/api/v1/flows/{self.flow_id}")
        assert response.status_code == 204, f"Failed to delete flow: {response.text}"
        self.flow_id = None
        self._routines.clear()
        self._connections.clear()

    def build_pipeline(
        self,
        source_name: str = "source",
        processor_name: str = "processor",
        sink_name: str = "sink",
    ) -> "FlowBuilder":
        """Build a simple 3-stage pipeline: source -> processor -> sink.

        Args:
            source_name: ID for source routine
            processor_name: ID for processor routine
            sink_name: ID for sink routine

        Returns:
            self for chaining
        """
        return (
            self.add_routine(source_name, "data_source", {"count": 3})
            .add_routine(processor_name, "data_transformer")
            .add_routine(sink_name, "data_sink")
            .add_connection(source_name, "output", processor_name, "input")
            .add_connection(processor_name, "output", sink_name, "input")
        )

    def build_branching_flow(self) -> "FlowBuilder":
        """Build a flow with branching: source -> (processor1, processor2) -> sink.

        Returns:
            self for chaining
        """
        return (
            self.add_routine("source", "data_source", {"count": 3})
            .add_routine("processor1", "data_transformer")
            .add_routine("processor2", "data_transformer")
            .add_routine("sink", "data_sink")
            .add_connection("source", "output", "processor1", "input")
            .add_connection("source", "output", "processor2", "input")
            .add_connection("processor1", "output", "sink", "input")
            .add_connection("processor2", "output", "sink", "input")
        )
