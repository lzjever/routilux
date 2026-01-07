"""
Flow Builder module.

Provides a fluent builder pattern for constructing Flow objects.
"""

from typing import Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.routine import Routine
    from routilux.error_handler import ErrorHandler
    from routilux.flow.flow import Flow


class FlowBuilder:
    """Fluent builder for Flow construction.
    
    This class provides a chainable API for building Flow objects, making
    it easier to construct complex workflows with less boilerplate.
    
    Examples:
        Basic usage:
            >>> from routilux import FlowBuilder
            >>> flow = FlowBuilder("my_flow") \\
            ...     .add_routine(DocxReader(), "docx_reader", config={"output_dir": "/tmp"}) \\
            ...     .add_routine(XmlChunkSplitter(), "xml_splitter") \\
            ...     .connect("docx_reader", "output", "xml_splitter", "input") \\
            ...     .validate() \\
            ...     .build()
        
        With error handlers:
            >>> from routilux import ErrorHandler, ErrorStrategy
            >>> flow = FlowBuilder() \\
            ...     .add_routine(
            ...         MyRoutine(),
            ...         "my_routine",
            ...         config={"timeout": 30},
            ...         error_handler=ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)
            ...     ) \\
            ...     .build()
    """
    
    def __init__(self, flow_id: Optional[str] = None):
        """Initialize FlowBuilder.
        
        Args:
            flow_id: Optional flow identifier. If None, Flow will generate one.
        """
        from routilux.flow.flow import Flow
        
        self.flow = Flow(flow_id=flow_id)
    
    def add_routine(
        self,
        routine: "Routine",
        routine_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        error_handler: Optional["ErrorHandler"] = None,
    ) -> "FlowBuilder":
        """Add routine with optional configuration.
        
        Args:
            routine: Routine instance to add.
            routine_id: Optional unique identifier for this routine in the flow.
            config: Optional configuration dictionary to apply to the routine.
            error_handler: Optional error handler to set for this routine.
            
        Returns:
            Self for method chaining.
        """
        rid = self.flow.add_routine(routine, routine_id)
        
        if config:
            routine.set_config(**config)
        
        if error_handler:
            routine.set_error_handler(error_handler)
        
        return self
    
    def connect(
        self,
        source_id: str,
        source_event: str,
        target_id: str,
        target_slot: str,
        param_mapping: Optional[Dict[str, str]] = None,
    ) -> "FlowBuilder":
        """Connect routines.
        
        Args:
            source_id: Identifier of the routine that emits the event.
            source_event: Name of the event to connect from.
            target_id: Identifier of the routine that receives the data.
            target_slot: Name of the slot to connect to.
            param_mapping: Optional dictionary mapping event parameter names to
                slot parameter names.
                
        Returns:
            Self for method chaining.
        """
        self.flow.connect(source_id, source_event, target_id, target_slot, param_mapping)
        return self
    
    def validate(self) -> "FlowBuilder":
        """Validate flow structure.
        
        This method calls Flow.validate() and raises an error if validation fails.
        It's useful to call this before build() to catch configuration errors early.
        
        Returns:
            Self for method chaining.
            
        Raises:
            ValueError: If flow validation fails.
        """
        issues = self.flow.validate()
        if issues:
            raise ValueError(f"Flow validation failed:\n" + "\n".join(issues))
        return self
    
    def build(self) -> "Flow":
        """Build and return the flow.
        
        Returns:
            The constructed Flow object.
        """
        return self.flow

