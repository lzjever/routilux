#!/usr/bin/env python
"""Data Processing Pipeline Example.

This example demonstrates a realistic data processing workflow:
1. Ingest data from multiple sources
2. Validate and clean data
3. Transform data
4. Branch based on data quality
5. Aggregate results
"""

from routilux import Flow, Routine
from routilux.exceptions import RoutiluxError
from routilux.job_state import JobState


class DataIngestor(Routine):
    """Ingests data from sources."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.ingest)
        self.define_event("output", ["records", "record_count"])

    def ingest(self, records=None, **kwargs):
        """Ingest data from source."""
        records = records if records is not None else kwargs.get("records", [])
        print(f"Ingesting {len(records)} records...")
        self.emit("output", records=records, record_count=len(records))


class DataValidator(Routine):
    """Validates data quality."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.validate)
        self.define_event("output", ["valid", "record_count", "records"])

    def validate(self, records=None, record_count=0, **kwargs):
        """Validate incoming data."""
        records = records if records is not None else kwargs.get("records", [])
        errors = []

        if not records:
            errors.append("No records provided")
        elif not isinstance(records, list):
            errors.append("Records must be a list")
        else:
            # Validate each record
            for i, record in enumerate(records):
                if not isinstance(record, dict):
                    errors.append(f"Record {i} is not a dictionary")
                elif "id" not in record:
                    errors.append(f"Record {i} missing 'id' field")

        if errors:
            raise RoutiluxError(f"Validation failed: {errors}")

        print(f"Validated {len(records)} records successfully")
        self.emit("output", valid=True, record_count=len(records), records=records)


class DataTransformer(Routine):
    """Transforms data format."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.transform)
        self.define_event("output", ["transformed"])

    def transform(self, records=None, valid=None, record_count=0, **kwargs):
        """Transform validated data."""
        records = records if records is not None else kwargs.get("records", [])

        transformed = []
        for record in records:
            # Example transformation: normalize and enrich
            transformed_record = {
                "id": record.get("id"),
                "name": record.get("name", "").strip().lower() if isinstance(record.get("name"), str) else str(record.get("name", "")).lower(),
                "value": float(record.get("value", 0)) if str(record.get("value", "")).replace(".", "").replace("-", "").isdigit() else 0.0,
                "processed": True,
            }
            transformed.append(transformed_record)

        print(f"Transformed {len(transformed)} records")
        self.emit("output", transformed=transformed)


class QualityChecker(Routine):
    """Checks data quality and routes accordingly."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.check_quality)
        self.define_event("output", ["quality", "route", "score", "total", "valid"])

    def check_quality(self, transformed=None, **kwargs):
        """Check data quality and route accordingly."""
        transformed = transformed if transformed is not None else kwargs.get("transformed", [])

        # Calculate quality metrics
        valid_count = sum(1 for r in transformed if r.get("value", 0) > 0)
        quality_score = valid_count / len(transformed) if transformed else 0

        # Emit to different paths based on quality
        if quality_score >= 0.8:
            route = "publish"
            quality = "high"
        elif quality_score >= 0.5:
            route = "review"
            quality = "medium"
        else:
            route = "reject"
            quality = "low"

        print(f"Quality score: {quality_score:.2f} ({quality})")
        self.emit("output", quality=quality, route=route, score=quality_score, total=len(transformed), valid=valid_count)


class ResultAggregator(Routine):
    """Aggregates final results."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.aggregate)
        self.final_results = []

    def aggregate(self, quality=None, route=None, score=None, total=None, valid=None, **kwargs):
        """Aggregate final results."""
        result = {"quality": quality, "route": route, "score": score, "total": total, "valid": valid}
        self.final_results.append(result)
        print(f"Aggregated: Quality={quality}, Route={route}, Score={score:.2f} ({valid}/{total} valid)")


def main():
    """Run the data pipeline example."""
    # Create flow
    flow = Flow("data_pipeline")

    # Create routine instances
    ingestor = DataIngestor()
    validator = DataValidator()
    transformer = DataTransformer()
    quality_checker = QualityChecker()
    aggregator = ResultAggregator()

    # Add routines to flow
    ingest_id = flow.add_routine(ingestor, "ingestor")
    validate_id = flow.add_routine(validator, "validator")
    transform_id = flow.add_routine(transformer, "transformer")
    quality_id = flow.add_routine(quality_checker, "quality_checker")
    aggregate_id = flow.add_routine(aggregator, "aggregator")

    # Connect the pipeline
    flow.connect(ingest_id, "output", validate_id, "input")
    flow.connect(validate_id, "output", transform_id, "input")
    flow.connect(transform_id, "output", quality_id, "input")
    flow.connect(quality_id, "output", aggregate_id, "input")

    # Test data
    test_records = [
        {"id": 1, "name": "  Alice  ", "value": "100"},
        {"id": 2, "name": "BOB", "value": "200"},
        {"id": 3, "name": "Charlie", "value": "invalid"},
        {"id": 4, "name": "David", "value": "50"},
    ]

    # Execute pipeline
    print("\n=== Data Pipeline Example ===\n")
    job_state = flow.execute(ingest_id, entry_params={"records": test_records})
    JobState.wait_for_completion(flow, job_state, timeout=30.0)

    print(f"\nPipeline status: {job_state.status}")
    print(f"Final aggregated results: {aggregator.final_results}")


if __name__ == "__main__":
    main()
