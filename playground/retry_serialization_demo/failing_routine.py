"""
Routine that fails with delay for retry demonstration.

This routine intentionally fails after a delay to demonstrate retry behavior
and serialization/recovery across hosts.
"""

import time
from routilux import Routine
from serilux import register_serializable


@register_serializable
class FailingRoutine(Routine):
    """Routine that fails after a delay.
    
    This routine simulates a long-running operation that may fail.
    It delays for a specified time, then raises an exception.
    The delay allows for serialization during execution.
    
    Attributes:
        delay: Delay in seconds before raising exception.
        attempt_count: Number of times this routine has been called.
    """
    
    def __init__(self, delay: float = 0.5):
        """Initialize FailingRoutine.
        
        Args:
            delay: Delay in seconds before raising exception. Default: 0.5
        """
        super().__init__()
        self.delay = delay
        self.attempt_count = 0
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
    
    def process(self, data=None, **kwargs):
        """Process input and fail after delay.
        
        This method increments attempt_count, waits for delay seconds,
        then raises a ValueError. This simulates a transient failure
        that might succeed on retry.
        
        Args:
            data: Optional input data.
            **kwargs: Additional keyword arguments.
        """
        self.attempt_count += 1
        attempt = self.attempt_count
        
        print(f"  [FailingRoutine] Attempt {attempt}: Starting processing...")
        print(f"  [FailingRoutine] Attempt {attempt}: Waiting {self.delay}s before failure...")
        
        # Delay before failure (allows time for serialization)
        time.sleep(self.delay)
        
        # Always fail (for demo purposes)
        error_msg = f"Simulated failure on attempt {attempt}"
        print(f"  [FailingRoutine] Attempt {attempt}: ❌ {error_msg}")
        raise ValueError(error_msg)


@register_serializable
class LongRunningRoutine(Routine):
    """Routine that takes a long time to complete.
    
    This routine simulates a long-running operation that takes
    several seconds to complete. It's used to create a flow that
    runs for a while, allowing serialization during execution.
    """
    
    def __init__(self, duration: float = 2.0):
        """Initialize LongRunningRoutine.
        
        Args:
            duration: Duration in seconds for the operation. Default: 2.0
        """
        super().__init__()
        self.duration = duration
        self.trigger_slot = self.define_slot("trigger", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
    
    def process(self, data=None, **kwargs):
        """Process input with long delay.
        
        Args:
            data: Optional input data.
            **kwargs: Additional keyword arguments.
        """
        print(f"  [LongRunningRoutine] Starting long operation (duration: {self.duration}s)...")
        time.sleep(self.duration)
        result = f"Long operation completed after {self.duration}s"
        print(f"  [LongRunningRoutine] ✅ {result}")
        self.emit("output", result=result)


@register_serializable
class SuccessRoutine(Routine):
    """Simple routine that always succeeds.
    
    This routine is used as a downstream routine to verify
    that the flow can continue after retries are exhausted.
    """
    
    def __init__(self):
        """Initialize SuccessRoutine."""
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
    
    def process(self, data=None, **kwargs):
        """Process input and succeed.
        
        Args:
            data: Optional input data.
            **kwargs: Additional keyword arguments.
        """
        print(f"  [SuccessRoutine] Processing input: {data}")
        result = f"Successfully processed: {data}"
        print(f"  [SuccessRoutine] ✅ {result}")
        self.emit("output", result=result)

