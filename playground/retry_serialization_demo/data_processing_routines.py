"""
Real-world data processing routines for retry demonstration.

These routines simulate actual system operations like:
- Data fetching from external APIs
- Data processing and transformation
- Data validation and storage
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from routilux import Routine
from serilux import register_serializable


@register_serializable
class DataFetchRoutine(Routine):
    """Simulates fetching data from an external API.
    
    This routine simulates a data fetching operation that:
    - Takes some time to complete
    - Generates structured data
    - Emits data with metadata
    """
    
    def __init__(self, fetch_duration: float = 1.0):
        """Initialize DataFetchRoutine.
        
        Args:
            fetch_duration: Duration in seconds for the fetch operation. Default: 1.0
        """
        super().__init__()
        self.fetch_duration = fetch_duration
        self.trigger_slot = self.define_slot("trigger", handler=self.fetch_data)
        self.output_event = self.define_event("output", ["data", "metadata", "timestamp"])
    
    def fetch_data(self, request_id: Optional[str] = None, **kwargs):
        """Fetch data from external API.
        
        Args:
            request_id: Optional request ID for tracking.
            **kwargs: Additional parameters.
        """
        request_id = request_id or str(uuid.uuid4())[:8]
        print(f"\n  📡 [DataFetchRoutine] Starting data fetch...")
        print(f"      Request ID: {request_id}")
        print(f"      Duration: {self.fetch_duration}s")
        
        # Simulate API call
        time.sleep(self.fetch_duration)
        
        # Generate mock data
        data = {
            "user_id": "user_12345",
            "items": [
                {"id": 1, "name": "Product A", "price": 29.99},
                {"id": 2, "name": "Product B", "price": 49.99},
                {"id": 3, "name": "Product C", "price": 19.99},
            ],
            "total_items": 3,
            "request_id": request_id,
        }
        
        metadata = {
            "source": "external_api",
            "fetch_time": self.fetch_duration,
            "status": "success",
        }
        
        timestamp = datetime.now().isoformat()
        
        print(f"  ✅ [DataFetchRoutine] Data fetched successfully")
        print(f"      Items: {data['total_items']}")
        print(f"      Timestamp: {timestamp}")
        
        self.emit("output", data=data, metadata=metadata, timestamp=timestamp)


@register_serializable
class DataProcessRoutine(Routine):
    """Simulates processing data with potential failures.
    
    This routine simulates a data processing operation that:
    - May fail due to transient errors (network, validation, etc.)
    - Processes data and transforms it
    - Emits processed data
    """
    
    def __init__(self, processing_delay: float = 0.5, failure_rate: float = 1.0):
        """Initialize DataProcessRoutine.
        
        Args:
            processing_delay: Delay in seconds before processing. Default: 0.5
            failure_rate: Rate of failures (1.0 = always fail for demo). Default: 1.0
        """
        super().__init__()
        self.processing_delay = processing_delay
        self.failure_rate = failure_rate
        self.attempt_count = 0
        self.processed_items = []
        
        self.input_slot = self.define_slot("input", handler=self.process_data)
        self.output_event = self.define_event("output", ["processed_data", "statistics", "timestamp"])
    
    def process_data(self, data: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs):
        """Process input data and potentially fail.
        
        Args:
            data: Input data dictionary.
            metadata: Optional metadata.
            **kwargs: Additional parameters.
        """
        self.attempt_count += 1
        attempt = self.attempt_count
        
        print(f"\n  🔄 [DataProcessRoutine] Attempt {attempt}: Starting data processing...")
        
        if data:
            print(f"      Input: {data.get('total_items', 0)} items")
            print(f"      Request ID: {data.get('request_id', 'N/A')}")
        
        # Simulate processing delay
        print(f"      Processing delay: {self.processing_delay}s...")
        time.sleep(self.processing_delay)
        
        # Simulate failure (for demo purposes, always fail)
        if self.failure_rate >= 1.0 or (self.attempt_count <= 4):
            error_msg = f"Transient processing error on attempt {attempt} (simulated network timeout)"
            print(f"  ❌ [DataProcessRoutine] Attempt {attempt}: {error_msg}")
            raise ValueError(error_msg)
        
        # Success path (won't be reached in demo, but shows what would happen)
        if data:
            processed_items = []
            total_value = 0.0
            for item in data.get("items", []):
                processed_item = {
                    "id": item["id"],
                    "name": item["name"],
                    "price": item["price"],
                    "discounted_price": item["price"] * 0.9,  # 10% discount
                    "processed_at": datetime.now().isoformat(),
                }
                processed_items.append(processed_item)
                total_value += processed_item["discounted_price"]
            
            processed_data = {
                "original_request_id": data.get("request_id"),
                "processed_items": processed_items,
                "total_value": round(total_value, 2),
                "processing_attempt": attempt,
            }
            
            statistics = {
                "items_processed": len(processed_items),
                "total_discount": round(total_value * 0.1, 2),
                "processing_time": self.processing_delay,
            }
            
            print(f"  ✅ [DataProcessRoutine] Processing completed successfully")
            print(f"      Items processed: {len(processed_items)}")
            print(f"      Total value: ${total_value:.2f}")
            
            self.emit("output", 
                     processed_data=processed_data, 
                     statistics=statistics,
                     timestamp=datetime.now().isoformat())


@register_serializable
class DataValidatorRoutine(Routine):
    """Simulates data validation.
    
    This routine validates processed data and ensures data quality.
    """
    
    def __init__(self):
        """Initialize DataValidatorRoutine."""
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.validate_data)
        self.output_event = self.define_event("output", ["validated_data", "validation_report", "timestamp"])
    
    def validate_data(self, processed_data: Optional[Dict[str, Any]] = None, **kwargs):
        """Validate processed data.
        
        Args:
            processed_data: Processed data to validate.
            **kwargs: Additional parameters.
        """
        print(f"\n  ✔️  [DataValidatorRoutine] Validating data...")
        
        if processed_data:
            items = processed_data.get("processed_items", [])
            print(f"      Validating {len(items)} items...")
            
            # Simulate validation
            time.sleep(0.2)
            
            validation_errors = []
            for item in items:
                if item.get("price", 0) < 0:
                    validation_errors.append(f"Item {item.get('id')}: Negative price")
                if not item.get("name"):
                    validation_errors.append(f"Item {item.get('id')}: Missing name")
            
            validated_data = {
                "original_request_id": processed_data.get("original_request_id"),
                "validated_items": items,
                "validation_passed": len(validation_errors) == 0,
            }
            
            validation_report = {
                "items_validated": len(items),
                "errors_found": len(validation_errors),
                "errors": validation_errors,
                "validation_timestamp": datetime.now().isoformat(),
            }
            
            if validation_errors:
                print(f"  ⚠️  [DataValidatorRoutine] Validation found {len(validation_errors)} errors")
            else:
                print(f"  ✅ [DataValidatorRoutine] All items validated successfully")
            
            self.emit("output",
                     validated_data=validated_data,
                     validation_report=validation_report,
                     timestamp=datetime.now().isoformat())


@register_serializable
class DataStorageRoutine(Routine):
    """Simulates storing data to database.
    
    This routine simulates storing validated data to a database.
    """
    
    def __init__(self):
        """Initialize DataStorageRoutine."""
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.store_data)
        self.output_event = self.define_event("output", ["storage_result", "timestamp"])
        self.stored_records = []
    
    def store_data(self, validated_data: Optional[Dict[str, Any]] = None, **kwargs):
        """Store validated data to database.
        
        Args:
            validated_data: Validated data to store.
            **kwargs: Additional parameters.
        """
        print(f"\n  💾 [DataStorageRoutine] Storing data to database...")
        
        if validated_data:
            items = validated_data.get("validated_items", [])
            print(f"      Storing {len(items)} items...")
            
            # Simulate database write
            time.sleep(0.3)
            
            storage_result = {
                "request_id": validated_data.get("original_request_id"),
                "records_stored": len(items),
                "storage_timestamp": datetime.now().isoformat(),
                "storage_id": str(uuid.uuid4())[:8],
            }
            
            self.stored_records.extend(items)
            
            print(f"  ✅ [DataStorageRoutine] Data stored successfully")
            print(f"      Storage ID: {storage_result['storage_id']}")
            print(f"      Records stored: {storage_result['records_stored']}")
            
            self.emit("output",
                     storage_result=storage_result,
                     timestamp=datetime.now().isoformat())

