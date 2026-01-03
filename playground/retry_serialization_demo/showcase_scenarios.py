"""
Showcase scenarios for retry and serialization demonstration.

This module provides additional interesting scenarios to demonstrate
various aspects of retry and serialization functionality.
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from routilux import Routine, Flow
from routilux.error_handler import ErrorHandler, ErrorStrategy
from serilux import register_serializable


@register_serializable
class APICallRoutine(Routine):
    """Simulates an API call that may fail.
    
    This routine simulates calling an external API with:
    - Network latency
    - Potential timeouts
    - Retry capability
    """
    
    def __init__(self, api_name: str = "external_api", latency: float = 0.3):
        """Initialize APICallRoutine.
        
        Args:
            api_name: Name of the API being called.
            latency: Network latency in seconds.
        """
        super().__init__()
        self.api_name = api_name
        self.latency = latency
        self.attempt_count = 0
        self.trigger_slot = self.define_slot("trigger", handler=self.call_api)
        self.output_event = self.define_event("output", ["response", "status", "metadata"])
    
    def call_api(self, endpoint: Optional[str] = None, **kwargs):
        """Call external API.
        
        Args:
            endpoint: API endpoint to call.
            **kwargs: Additional parameters.
        """
        self.attempt_count += 1
        attempt = self.attempt_count
        endpoint = endpoint or "/api/v1/data"
        
        print(f"\n  🌐 [APICallRoutine] Attempt {attempt}: Calling {self.api_name}")
        print(f"      Endpoint: {endpoint}")
        print(f"      Network latency: {self.latency}s")
        
        # Simulate network call
        time.sleep(self.latency)
        
        # Simulate failure (for demo)
        if attempt <= 4:
            error_msg = f"API timeout on attempt {attempt} (simulated network issue)"
            print(f"  ❌ [APICallRoutine] Attempt {attempt}: {error_msg}")
            raise ConnectionError(error_msg)
        
        # Success path
        response = {
            "status": "success",
            "data": {
                "user_id": "user_123",
                "items": [{"id": i, "name": f"Item {i}"} for i in range(1, 6)],
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        print(f"  ✅ [APICallRoutine] API call successful")
        print(f"      Response: {len(response['data']['items'])} items")
        
        self.emit("output",
                 response=response,
                 status=200,
                 metadata={"api": self.api_name, "endpoint": endpoint, "attempt": attempt})


@register_serializable
class DatabaseWriteRoutine(Routine):
    """Simulates writing to a database.
    
    This routine simulates database operations with:
    - Transaction handling
    - Potential deadlocks
    - Retry capability
    """
    
    def __init__(self, db_name: str = "main_db"):
        """Initialize DatabaseWriteRoutine.
        
        Args:
            db_name: Name of the database.
        """
        super().__init__()
        self.db_name = db_name
        self.attempt_count = 0
        self.input_slot = self.define_slot("input", handler=self.write_to_db)
        self.output_event = self.define_event("output", ["write_result", "transaction_id", "timestamp"])
    
    def write_to_db(self, response: Optional[Dict[str, Any]] = None, **kwargs):
        """Write data to database.
        
        Args:
            response: Response data from previous routine.
            **kwargs: Additional parameters.
        """
        self.attempt_count += 1
        attempt = self.attempt_count
        
        print(f"\n  💾 [DatabaseWriteRoutine] Attempt {attempt}: Writing to {self.db_name}")
        
        if response:
            items = response.get("data", {}).get("items", [])
            print(f"      Writing {len(items)} items...")
        
        # Simulate database write delay
        time.sleep(0.2)
        
        # Simulate failure (for demo)
        if attempt <= 3:
            error_msg = f"Database deadlock on attempt {attempt} (simulated)"
            print(f"  ❌ [DatabaseWriteRoutine] Attempt {attempt}: {error_msg}")
            raise RuntimeError(error_msg)
        
        # Success path
        transaction_id = str(uuid.uuid4())[:8]
        write_result = {
            "status": "committed",
            "records_written": len(response.get("data", {}).get("items", [])) if response else 0,
            "transaction_id": transaction_id,
        }
        
        print(f"  ✅ [DatabaseWriteRoutine] Write successful")
        print(f"      Transaction ID: {transaction_id}")
        
        self.emit("output",
                 write_result=write_result,
                 transaction_id=transaction_id,
                 timestamp=datetime.now().isoformat())


@register_serializable
class NotificationRoutine(Routine):
    """Simulates sending notifications.
    
    This routine sends notifications after successful operations.
    """
    
    def __init__(self):
        """Initialize NotificationRoutine."""
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.send_notification)
        self.output_event = self.define_event("output", ["notification_result", "timestamp"])
    
    def send_notification(self, write_result: Optional[Dict[str, Any]] = None, **kwargs):
        """Send notification.
        
        Args:
            write_result: Write result from previous routine.
            **kwargs: Additional parameters.
        """
        print(f"\n  📧 [NotificationRoutine] Sending notification...")
        
        if write_result:
            transaction_id = write_result.get("transaction_id", "N/A")
            print(f"      Transaction ID: {transaction_id}")
        
        # Simulate notification send
        time.sleep(0.1)
        
        notification_result = {
            "status": "sent",
            "recipient": "admin@example.com",
            "message": f"Data processing completed successfully",
            "timestamp": datetime.now().isoformat(),
        }
        
        print(f"  ✅ [NotificationRoutine] Notification sent")
        print(f"      Recipient: {notification_result['recipient']}")
        
        self.emit("output",
                 notification_result=notification_result,
                 timestamp=datetime.now().isoformat())


def create_api_to_db_flow() -> Tuple[Flow, str]:
    """Create a flow: API Call → Database Write → Notification.
    
    This flow demonstrates:
    - API calls with retry
    - Database writes with retry
    - Notification after success
    
    Returns:
        Tuple of (Flow, entry_routine_id)
    """
    print("=" * 80)
    print("🏗️  Creating API-to-Database Flow")
    print("=" * 80)
    
    flow = Flow(flow_id="api_to_db_flow", execution_strategy="sequential")
    
    # Create routines
    api_call = APICallRoutine(api_name="user_service_api", latency=0.3)
    db_write = DatabaseWriteRoutine(db_name="user_database")
    notification = NotificationRoutine()
    
    # Add routines to flow
    api_id = flow.add_routine(api_call, "api_call")
    db_id = flow.add_routine(db_write, "db_write")
    notification_id = flow.add_routine(notification, "notification")
    
    # Configure retry for API call
    print(f"\n⚙️  Configuring retry for 'api_call' routine:")
    print(f"   - Strategy: RETRY")
    print(f"   - Max retries: 4")
    print(f"   - Retry delay: 0.3s")
    print(f"   - Retry backoff: 1.5x")
    
    api_error_handler = ErrorHandler(
        strategy=ErrorStrategy.RETRY,
        max_retries=4,
        retry_delay=0.3,
        retry_backoff=1.5,
        retryable_exceptions=(ConnectionError,),
    )
    api_call.set_error_handler(api_error_handler)
    
    # Configure retry for database write
    print(f"\n⚙️  Configuring retry for 'db_write' routine:")
    print(f"   - Strategy: RETRY")
    print(f"   - Max retries: 3")
    print(f"   - Retry delay: 0.2s")
    print(f"   - Retry backoff: 2.0x")
    
    db_error_handler = ErrorHandler(
        strategy=ErrorStrategy.RETRY,
        max_retries=3,
        retry_delay=0.2,
        retry_backoff=2.0,
        retryable_exceptions=(RuntimeError,),
    )
    db_write.set_error_handler(db_error_handler)
    
    # Connect routines
    flow.connect(api_id, "output", db_id, "input")
    flow.connect(db_id, "output", notification_id, "input")
    
    print(f"\n✅ Flow created:")
    print(f"   - Flow ID: {flow.flow_id}")
    print(f"   - Routines: {list(flow.routines.keys())}")
    print(f"   - Entry routine: {api_id}")
    print(f"   - Flow structure: api_call (retry) → db_write (retry) → notification")
    
    return flow, api_id

