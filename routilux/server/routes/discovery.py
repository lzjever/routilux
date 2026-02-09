"""
Flow and job discovery API routes.

Provides endpoints to discover and register flows/jobs created outside the API.
"""

import logging

from fastapi import APIRouter, HTTPException

from routilux.server.dependencies import (
    get_flow_registry,
    get_job_storage,
    get_runtime,
    get_worker_registry,
)
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.flow import FlowListResponse
from routilux.server.models.job import JobListResponse
from routilux.server.routes.flows import _flow_to_response
from routilux.server.routes.jobs import _job_to_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/discovery/flows/sync", response_model=FlowListResponse, dependencies=[RequireAuth])
async def sync_flows():
    """
    Sync flows from global registry to API store.

    **Overview**:
    Discovers all flows from the global FlowRegistry and syncs them to the API store.
    This allows the API to monitor and manage flows that were created outside the API
    (e.g., programmatically or from DSL files). After syncing, these flows become
    available through the standard flow management endpoints.

    **Endpoint**: `POST /api/discovery/flows/sync`

    **Use Cases**:
    - Sync flows created programmatically
    - Import flows from external sources
    - Make flows available to API after creation
    - Discover flows created in other processes
    - Integrate with external flow creation tools

    **Request Example**:
    ```
    POST /api/discovery/flows/sync
    ```

    **Response Example**:
    ```json
    {
      "flows": [
        {
          "flow_id": "programmatic_flow",
          "routines": {...},
          "connections": [...]
        }
      ],
      "total": 1
    }
    ```

    **Behavior**:
    - Reads all flows from global FlowRegistry
    - Returns list of discovered flows
    - Flows are now accessible via standard API endpoints
    - Does not modify existing flows in API store

    **Error Responses**:
    - `500 Internal Server Error`: Failed to access flow registry or sync flows

    **Best Practices**:
    1. Sync flows after programmatic creation
    2. Use this endpoint to integrate external flow sources
    3. Check discovered flows: GET /api/discovery/flows
    4. Sync regularly if flows are created outside API

    **Related Endpoints**:
    - GET /api/discovery/flows - Discover flows without syncing
    - GET /api/flows - List all flows in API store
    - POST /api/flows - Create flows via API

    Returns:
        FlowListResponse: List of discovered flows with total count

    Raises:
        HTTPException: 500 if sync fails
    """
    try:
        flow_registry = get_flow_registry()
        registry_flows = flow_registry.list_all()

        return FlowListResponse(
            flows=[_flow_to_response(flow) for flow in registry_flows],
            total=len(registry_flows),
        )
    except Exception as e:
        logger.exception(f"Failed to sync flows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync flows: {str(e)}") from e


@router.get("/discovery/flows", response_model=FlowListResponse, dependencies=[RequireAuth])
async def discover_flows():
    """
    Discover flows from global registry.

    **Overview**:
    Returns flows from the global FlowRegistry that may not be in the API store.
    This is a read-only operation that does not modify the API store. Use this to
    discover flows created outside the API before deciding to sync them.

    **Endpoint**: `GET /api/discovery/flows`

    **Use Cases**:
    - Discover flows created programmatically
    - Check for flows not yet in API store
    - Inspect flows before syncing
    - Audit flow sources
    - Build flow discovery tools

    **Request Example**:
    ```
    GET /api/discovery/flows
    ```

    **Response Example**:
    ```json
    {
      "flows": [
        {
          "flow_id": "programmatic_flow",
          "routines": {...},
          "connections": [...]
        }
      ],
      "total": 1
    }
    ```

    **Behavior**:
    - Reads flows from global FlowRegistry
    - Returns list without modifying API store
    - Safe to call repeatedly
    - Does not sync flows to API store

    **Difference from Sync**:
    - **Discover** (GET): Read-only, does not modify API store
    - **Sync** (POST): Discovers and makes flows available via API

    **Error Responses**:
    - `500 Internal Server Error`: Failed to access flow registry

    **Best Practices**:
    1. Use discover to inspect flows before syncing
    2. Compare with API store: GET /api/flows
    3. Sync when ready: POST /api/discovery/flows/sync

    **Related Endpoints**:
    - POST /api/discovery/flows/sync - Sync discovered flows to API store
    - GET /api/flows - List flows in API store

    Returns:
        FlowListResponse: List of discovered flows with total count

    Raises:
        HTTPException: 500 if discovery fails
    """
    try:
        flow_registry = get_flow_registry()
        registry_flows = flow_registry.list_all()

        return FlowListResponse(
            flows=[_flow_to_response(flow) for flow in registry_flows],
            total=len(registry_flows),
        )
    except Exception as e:
        logger.exception(f"Failed to discover flows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to discover flows: {str(e)}") from e


@router.post("/discovery/jobs/sync", response_model=JobListResponse, dependencies=[RequireAuth])
async def sync_jobs():
    """
    Sync jobs from Runtime to API storage.

    **Overview**:
    Discovers all jobs from the Runtime and syncs them to the API job storage.
    This allows the API to monitor and manage jobs that were started outside the API
    (e.g., programmatically or from other processes). After syncing, these jobs become
    available through the standard job management endpoints.

    **Endpoint**: `POST /api/discovery/jobs/sync`

    **Use Cases**:
    - Sync jobs started programmatically
    - Import jobs from external sources
    - Make jobs available to API after creation
    - Discover jobs created in other processes
    - Integrate with external job creation tools

    **Request Example**:
    ```
    POST /api/discovery/jobs/sync
    ```

    **Response Example**:
    ```json
    {
      "jobs": [
        {
          "job_id": "job_xyz789",
          "worker_id": "worker_abc123",
          "flow_id": "data_processing_flow",
          "status": "running",
          "created_at": 1705312800,
          "started_at": 1705312801,
          "completed_at": null,
          "error": null,
          "metadata": {}
        }
      ],
      "total": 1,
      "limit": 1,
      "offset": 0
    }
    ```

    **Behavior**:
    - Reads all jobs from Runtime
    - Syncs jobs to API job storage
    - Associates jobs with their workers and flows
    - Jobs are now accessible via standard API endpoints

    **Error Responses**:
    - `500 Internal Server Error`: Failed to access runtime or sync jobs

    **Best Practices**:
    1. Sync jobs after programmatic creation
    2. Use this endpoint to integrate external job sources
    3. Check discovered jobs: GET /api/discovery/jobs
    4. Sync regularly if jobs are created outside API

    **Related Endpoints**:
    - GET /api/discovery/jobs - Discover jobs without syncing
    - GET /api/jobs - List all jobs in API storage
    - POST /api/jobs - Create jobs via API

    Returns:
        JobListResponse: List of discovered jobs with total count

    Raises:
        HTTPException: 500 if sync fails
    """
    try:
        runtime = get_runtime()
        job_storage = get_job_storage()
        worker_registry = get_worker_registry()

        # Get all jobs from Runtime
        all_jobs = runtime.list_jobs()

        # Sync to storage
        for job in all_jobs:
            # Get flow_id from worker
            flow_id = ""
            worker = worker_registry.get(job.worker_id)
            if worker:
                flow_id = worker.flow_id
            job_storage.save_job(job, flow_id=flow_id)

        return JobListResponse(
            jobs=[
                _job_to_response(job, flow_id=job_storage.get_flow_id(job.job_id) or "")
                for job in all_jobs
            ],
            total=len(all_jobs),
            limit=len(all_jobs),
            offset=0,
        )
    except Exception as e:
        logger.exception(f"Failed to sync jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync jobs: {str(e)}") from e


@router.get("/discovery/jobs", response_model=JobListResponse, dependencies=[RequireAuth])
async def discover_jobs():
    """
    Discover jobs from Runtime.

    **Overview**:
    Returns jobs from the Runtime that may not be in the API job storage.
    This is a read-only operation that does not modify the storage. Use this to
    discover jobs started outside the API before deciding to sync them.

    **Endpoint**: `GET /api/discovery/jobs`

    **Use Cases**:
    - Discover jobs started programmatically
    - Check for jobs not yet in API storage
    - Inspect jobs before syncing
    - Audit job sources
    - Build job discovery tools

    **Request Example**:
    ```
    GET /api/discovery/jobs
    ```

    **Response Example**:
    ```json
    {
      "jobs": [
        {
          "job_id": "job_xyz789",
          "worker_id": "worker_abc123",
          "flow_id": "data_processing_flow",
          "status": "running",
          "created_at": 1705312800,
          "started_at": 1705312801,
          "completed_at": null,
          "error": null,
          "metadata": {}
        }
      ],
      "total": 1,
      "limit": 1,
      "offset": 0
    }
    ```

    **Behavior**:
    - Reads jobs from Runtime
    - Returns list without modifying API storage
    - Safe to call repeatedly
    - Does not sync jobs to API storage

    **Difference from Sync**:
    - **Discover** (GET): Read-only, does not modify API storage
    - **Sync** (POST): Discovers and syncs jobs to API storage

    **Error Responses**:
    - `500 Internal Server Error`: Failed to access runtime

    **Best Practices**:
    1. Use discover to inspect jobs before syncing
    2. Compare with API storage: GET /api/jobs
    3. Sync when ready: POST /api/discovery/jobs/sync

    **Related Endpoints**:
    - POST /api/discovery/jobs/sync - Sync discovered jobs to API storage
    - GET /api/jobs - List jobs in API storage

    Returns:
        JobListResponse: List of discovered jobs with total count

    Raises:
        HTTPException: 500 if discovery fails
    """
    try:
        runtime = get_runtime()
        worker_registry = get_worker_registry()
        get_job_storage()

        all_jobs = runtime.list_jobs()

        responses = []
        for job in all_jobs:
            flow_id = ""
            worker = worker_registry.get(job.worker_id)
            if worker:
                flow_id = worker.flow_id
            responses.append(_job_to_response(job, flow_id=flow_id))

        return JobListResponse(
            jobs=responses,
            total=len(all_jobs),
            limit=len(all_jobs),
            offset=0,
        )
    except Exception as e:
        logger.exception(f"Failed to discover jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to discover jobs: {str(e)}") from e


@router.post("/discovery/workers/sync", dependencies=[RequireAuth])
async def sync_workers():
    """
    Sync workers from Runtime to WorkerRegistry.

    **Overview**:
    Discovers all active workers from the Runtime and ensures they are registered
    in the WorkerRegistry. This allows the API to monitor and manage workers that
    were created outside the API (e.g., programmatically). After syncing, these workers
    become available through the standard worker management endpoints.

    **Endpoint**: `POST /api/discovery/workers/sync`

    **Use Cases**:
    - Sync workers created programmatically
    - Import workers from external sources
    - Make workers available to API after creation
    - Discover workers created in other processes
    - Integrate with external worker creation tools

    **Request Example**:
    ```
    POST /api/discovery/workers/sync
    ```

    **Response Example**:
    ```json
    {
      "workers": [
        {
          "worker_id": "worker_abc123",
          "flow_id": "data_processing_flow",
          "status": "running"
        }
      ],
      "total": 1
    }
    ```

    **Behavior**:
    - Reads all active workers from Runtime
    - Registers workers in WorkerRegistry if not already registered
    - Returns list of discovered workers
    - Workers are now accessible via standard API endpoints

    **Error Responses**:
    - `500 Internal Server Error`: Failed to access runtime or sync workers

    **Best Practices**:
    1. Sync workers after programmatic creation
    2. Use this endpoint to integrate external worker sources
    3. Check worker status: GET /api/v1/workers/{worker_id}
    4. Sync regularly if workers are created outside API

    **Related Endpoints**:
    - GET /api/v1/workers - List all workers
    - GET /api/v1/workers/{worker_id} - Get worker details
    - POST /api/v1/workers - Create workers via API

    Returns:
        dict: List of discovered workers with total count

    Raises:
        HTTPException: 500 if sync fails
    """
    try:
        runtime = get_runtime()
        worker_registry = get_worker_registry()

        workers = []
        with runtime._worker_lock:
            for worker_state in runtime._active_workers.values():
                # Register in WorkerRegistry if not already
                if worker_registry.get(worker_state.worker_id) is None:
                    worker_registry.register(worker_state)

                workers.append(
                    {
                        "worker_id": worker_state.worker_id,
                        "flow_id": worker_state.flow_id,
                        "status": worker_state.status.value
                        if hasattr(worker_state.status, "value")
                        else str(worker_state.status),
                    }
                )

        return {
            "workers": workers,
            "total": len(workers),
        }
    except Exception as e:
        logger.exception(f"Failed to sync workers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync workers: {str(e)}") from e


@router.get("/discovery", dependencies=[RequireAuth])
async def get_discovery_status():
    """Get current discovery status.

    Returns information about discovered routines and configuration.

    **Response Example**:
    ```json
    {
      "routines_count": 42,
      "directories": ["./routines", "~/.routilux/routines"],
      "routines": [
        {
          "name": "my_processor",
          "category": "processing",
          "type": "routine"
        }
      ]
    }
    ```
    """
    import os
    from pathlib import Path
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    routines = factory.list_available()

    # Get routines directories from environment
    routines_dirs_str = os.getenv("ROUTILUX_ROUTINES_DIRS", "")
    directories = []
    if routines_dirs_str:
        directories = routines_dirs_str.split(":")

    return {
        "routines_count": len(routines),
        "directories": directories,
        "routines": [
            {
                "name": r["name"],
                "category": r.get("category", ""),
                "type": r.get("object_type", "routine"),
            }
            for r in routines
        ],
    }


@router.post("/dsl/file", dependencies=[RequireAuth])
async def load_dsl_from_file(request: dict):
    """Load DSL from file path.

    Alternative to POST /api/v1/flows with DSL in body.
    This endpoint loads DSL from a file path on the server.

    **Request Example**:
    ```json
    {
      "file_path": "/path/to/flow.yaml"
    }
    ```

    **Response**: Flow object (same as POST /api/v1/flows)
    """
    from pathlib import Path
    from routilux.tools.factory.factory import ObjectFactory
    from routilux.cli.commands.run import _load_dsl

    file_path = request.get("file_path")
    if not file_path:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="file_path is required")

    path = Path(file_path)
    if not path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Load DSL
    dsl_dict = _load_dsl(path)

    # Load flow from factory
    factory = ObjectFactory.get_instance()
    flow = factory.load_flow_from_dsl(dsl_dict)

    # Store flow
    from routilux.monitoring.storage import flow_store
    flow_store.add(flow)

    from routilux.server.routes.flows import _flow_to_response
    return _flow_to_response(flow)

