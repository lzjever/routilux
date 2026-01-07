"""
DSL loader for creating Flow objects from specifications.
"""

from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.flow.flow import Flow


def load_flow_from_spec(spec: Dict[str, Any]) -> "Flow":
    """Create Flow from specification dictionary.
    
    Args:
        spec: Flow specification dictionary with structure:
            {
                "flow_id": "optional_flow_id",
                "routines": {
                    "routine_id": {
                        "class": "module.path.ClassName" or ClassObject,
                        "config": {...},
                        "error_handler": {...}
                    }
                },
                "connections": [
                    {"from": "r1.output", "to": "r2.input", "param_mapping": {...}}
                ],
                "execution": {
                    "strategy": "sequential",
                    "timeout": 300.0
                }
            }
    
    Returns:
        Constructed Flow object.
    """
    from routilux.flow.flow import Flow
    from routilux.dsl.spec_parser import parse_spec
    from routilux.error_handler import ErrorHandler, ErrorStrategy
    
    # Parse specification
    parsed = parse_spec(spec)
    
    # Create flow
    flow = Flow(flow_id=parsed.get("flow_id"))
    
    # Add routines
    for routine_id, routine_info in parsed["routines"].items():
        routine_class = routine_info["class"]
        routine = routine_class()
        
        # Apply config
        if routine_info["config"]:
            routine.set_config(**routine_info["config"])
        
        # Apply error handler
        if routine_info["error_handler"]:
            handler_spec = routine_info["error_handler"]
            if isinstance(handler_spec, dict):
                strategy_str = handler_spec.get("strategy", "stop")
                strategy = ErrorStrategy[strategy_str.upper()] if hasattr(ErrorStrategy, strategy_str.upper()) else ErrorStrategy.STOP
                handler = ErrorHandler(
                    strategy=strategy,
                    max_retries=handler_spec.get("max_retries"),
                    retry_delay=handler_spec.get("retry_delay"),
                    retry_backoff=handler_spec.get("retry_backoff"),
                    is_critical=handler_spec.get("is_critical", False),
                )
                routine.set_error_handler(handler)
            elif isinstance(handler_spec, ErrorHandler):
                routine.set_error_handler(handler_spec)
        
        flow.add_routine(routine, routine_id)
    
    # Add connections
    for conn in parsed["connections"]:
        from_path = conn["from"].split(".")
        to_path = conn["to"].split(".")
        
        if len(from_path) != 2 or len(to_path) != 2:
            raise ValueError(f"Invalid connection format: {conn['from']} -> {conn['to']}. Expected 'routine_id.event_name' -> 'routine_id.slot_name'")
        
        source_id = from_path[0]
        source_event = from_path[1]
        target_id = to_path[0]
        target_slot = to_path[1]
        
        flow.connect(source_id, source_event, target_id, target_slot, conn.get("param_mapping"))
    
    # Apply execution settings
    execution = parsed.get("execution", {})
    if "strategy" in execution:
        flow.set_execution_strategy(
            execution["strategy"],
            max_workers=execution.get("max_workers")
        )
    if "timeout" in execution:
        flow.execution_timeout = execution["timeout"]
    
    return flow

