#!/usr/bin/env python
"""
Example routines for analyzer demonstration.

This file contains various routine examples to demonstrate
the capabilities of routine_analyzer and workflow_analyzer.
"""

from routilux import Routine


class DataCollector(Routine):
    """Collects data from multiple sources and aggregates them.
    
    This routine demonstrates:
    - Trigger slot for entry point
    - Multiple output events
    - Configuration parameters
    """
    
    def __init__(self):
        super().__init__()
        # Set configuration
        self.set_config(
            collection_timeout=30,
            max_items=100,
            aggregation_mode="sum"
        )
        
        # Define trigger slot
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        
        # Define multiple output events
        self.data_event = self.define_event("data", ["collected_data", "count", "timestamp"])
        self.error_event = self.define_event("error", ["error_message", "error_code"])
    
    def _handle_trigger(self, source=None, **kwargs):
        """Handle trigger and collect data."""
        timeout = self.get_config("collection_timeout", 30)
        max_items = self.get_config("max_items", 100)
        
        # Simulate data collection
        collected_data = [f"item_{i}" for i in range(min(5, max_items))]
        
        self.emit("data", 
                 collected_data=collected_data,
                 count=len(collected_data),
                 timestamp="2024-01-01T00:00:00")


class DataProcessor(Routine):
    """Processes data with configurable transformations.
    
    This routine demonstrates:
    - Input slot with handler
    - Append merge strategy
    - Multiple processing methods
    """
    
    def __init__(self):
        super().__init__()
        # Configuration
        self.set_config(
            processing_mode="batch",
            batch_size=10,
            enable_validation=True
        )
        
        # Input slot with append strategy for aggregation
        self.input_slot = self.define_slot(
            "input",
            handler=self.process,
            merge_strategy="append"
        )
        
        # Output event
        self.output_event = self.define_event("output", ["processed_data", "status"])
    
    def process(self, data=None, **kwargs):
        """Process incoming data."""
        # Extract data
        if isinstance(data, dict):
            data_value = data.get("collected_data", data)
        else:
            data_value = data
        
        # Process based on configuration
        mode = self.get_config("processing_mode", "batch")
        if mode == "batch":
            processed = [f"processed_{item}" for item in data_value] if isinstance(data_value, list) else [f"processed_{data_value}"]
        else:
            processed = data_value
        
        self.emit("output", processed_data=processed, status="success")


class DataValidator(Routine):
    """Validates data according to rules.
    
    This routine demonstrates:
    - Multiple input slots
    - Conditional output events
    - Custom validation logic
    """
    
    def __init__(self):
        super().__init__()
        # Configuration
        self.set_config(
            validation_rules=["required", "type_check"],
            strict_mode=True
        )
        
        # Multiple input slots
        self.data_slot = self.define_slot("data", handler=self.validate)
        self.metadata_slot = self.define_slot("metadata", handler=self.validate)
        
        # Multiple output events
        self.valid_event = self.define_event("valid", ["validated_data", "score"])
        self.invalid_event = self.define_event("invalid", ["errors", "data"])
    
    def validate(self, data=None, **kwargs):
        """Validate incoming data."""
        if isinstance(data, dict):
            data_value = data.get("processed_data", data)
        else:
            data_value = data
        
        # Simple validation
        is_valid = data_value is not None and len(str(data_value)) > 0
        
        if is_valid:
            self.emit("valid", validated_data=data_value, score=1.0)
        else:
            self.emit("invalid", errors=["Validation failed"], data=data_value)


class DataAggregator(Routine):
    """Aggregates data from multiple sources.
    
    This routine demonstrates:
    - Custom merge strategy
    - Multiple input sources
    - Complex aggregation logic
    """
    
    def __init__(self):
        super().__init__()
        # Configuration
        self.set_config(
            aggregation_function="mean",
            include_metadata=True
        )
        
        # Input slot with custom merge
        self.input_slot = self.define_slot(
            "input",
            handler=self.aggregate,
            merge_strategy=self._custom_merge
        )
        
        # Output event
        self.result_event = self.define_event("result", ["aggregated_value", "sources_count"])
    
    def _custom_merge(self, old_data, new_data):
        """Custom merge strategy for aggregation."""
        if not old_data:
            return new_data
        if not isinstance(old_data, dict):
            old_data = {"value": old_data}
        if not isinstance(new_data, dict):
            new_data = {"value": new_data}
        
        # Merge lists
        merged = old_data.copy()
        for key, value in new_data.items():
            if key in merged:
                if isinstance(merged[key], list):
                    merged[key].extend(value if isinstance(value, list) else [value])
                else:
                    merged[key] = [merged[key], value] if not isinstance(value, list) else [merged[key]] + value
            else:
                merged[key] = value
        
        return merged
    
    def aggregate(self, data=None, **kwargs):
        """Aggregate incoming data."""
        # Extract data
        if isinstance(data, dict):
            values = data.get("value", data) if "value" in data else list(data.values())
        else:
            values = data
        
        # Simple aggregation
        if isinstance(values, list):
            aggregated = sum(len(str(v)) for v in values) / len(values) if values else 0
        else:
            aggregated = len(str(values))
        
        self.emit("result", aggregated_value=aggregated, sources_count=len(values) if isinstance(values, list) else 1)


class DataRouter(Routine):
    """Routes data based on conditions.
    
    This routine demonstrates:
    - Conditional routing
    - Multiple output events for routing
    - Decision logic
    """
    
    def __init__(self):
        super().__init__()
        # Configuration
        self.set_config(
            routing_rules={"high": ">10", "medium": ">5", "low": "<=5"},
            default_route="low"
        )
        
        # Input slot
        self.input_slot = self.define_slot("input", handler=self.route)
        
        # Multiple output events for routing
        self.high_priority_event = self.define_event("high_priority", ["data", "priority"])
        self.medium_priority_event = self.define_event("medium_priority", ["data", "priority"])
        self.low_priority_event = self.define_event("low_priority", ["data", "priority"])
    
    def route(self, data=None, **kwargs):
        """Route data based on priority."""
        # Extract data
        if isinstance(data, dict):
            value = data.get("aggregated_value", data.get("validated_data", 0))
        else:
            value = len(str(data)) if data else 0
        
        # Route based on value
        if value > 10:
            self.emit("high_priority", data=data, priority="high")
        elif value > 5:
            self.emit("medium_priority", data=data, priority="medium")
        else:
            self.emit("low_priority", data=data, priority="low")


class DataSink(Routine):
    """Final destination for processed data.
    
    This routine demonstrates:
    - Multiple input slots from different sources
    - Data storage/saving
    - Final output
    """
    
    def __init__(self):
        super().__init__()
        # Configuration
        self.set_config(
            output_format="json",
            save_to_file=False
        )
        
        # Multiple input slots
        self.high_input = self.define_slot("high_input", handler=self.save)
        self.medium_input = self.define_slot("medium_input", handler=self.save)
        self.low_input = self.define_slot("low_input", handler=self.save)
        
        # Optional output event for confirmation
        self.completed_event = self.define_event("completed", ["saved_count", "timestamp"])
    
    def save(self, data=None, **kwargs):
        """Save incoming data."""
        # Extract data
        if isinstance(data, dict):
            data_value = data.get("data", data)
        else:
            data_value = data
        
        # Simulate saving
        output_format = self.get_config("output_format", "json")
        print(f"Saving data in {output_format} format: {data_value}")
        
        # Emit completion
        self.emit("completed", saved_count=1, timestamp="2024-01-01T00:00:00")

