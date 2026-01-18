"""
Runtime management API routes.

Provides endpoints to discover, register, and manage Runtime instances.
"""

from typing import List

from fastapi import APIRouter, HTTPException

from routilux.monitoring.runtime_registry import RuntimeRegistry
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.runtime import (
    RuntimeCreateRequest,
    RuntimeInfo,
    RuntimeListResponse,
    RuntimeResponse,
)

router = APIRouter()


def _runtime_to_info(runtime_id: str, runtime, is_default: bool) -> RuntimeInfo:
    """Convert Runtime instance to RuntimeInfo.

    Args:
        runtime_id: Runtime identifier.
        runtime: Runtime instance.
        is_default: Whether this is the default runtime.

    Returns:
        RuntimeInfo object.
    """
    # Get active job count from runtime
    active_job_count = 0
    if hasattr(runtime, "_active_jobs"):
        with runtime._job_lock:
            active_job_count = len(runtime._active_jobs)

    return RuntimeInfo(
        runtime_id=runtime_id,
        thread_pool_size=runtime.thread_pool_size,
        is_default=is_default,
        active_job_count=active_job_count,
        is_shutdown=runtime._shutdown,
    )


@router.get("/runtimes", response_model=RuntimeListResponse, dependencies=[RequireAuth])
async def list_runtimes():
    """List all registered Runtime instances.

    **Overview**:
    Returns a list of all Runtime instances registered in the system, including
    their configuration, status, and active job counts. Use this to discover
    available runtimes before starting a job.

    **Endpoint**: `GET /api/runtimes`

    **Use Cases**:
    - Discover available runtimes
    - Check runtime status and capacity
    - Build runtime selection UI
    - Monitor runtime health

    **Request Example**:
    ```
    GET /api/runtimes
    ```

    **Response Example**:
    ```json
    {
      "runtimes": [
        {
          "runtime_id": "production",
          "thread_pool_size": 20,
          "is_default": true,
          "active_job_count": 3,
          "is_shutdown": false
        },
        {
          "runtime_id": "development",
          "thread_pool_size": 5,
          "is_default": false,
          "active_job_count": 0,
          "is_shutdown": false
        }
      ],
      "total": 2,
      "default_runtime_id": "production"
    }
    ```

    **Response Fields**:
    - `runtimes`: List of RuntimeInfo objects
    - `total`: Total number of registered runtimes
    - `default_runtime_id`: ID of the default runtime

    **Runtime Information**:
    - `runtime_id`: Unique identifier (use this in JobStartRequest)
    - `thread_pool_size`: Maximum worker threads
    - `is_default`: Whether this is the default runtime
    - `active_job_count`: Number of currently running jobs
    - `is_shutdown`: Whether runtime is shut down

    **Related Endpoints**:
    - GET /api/runtimes/{runtime_id} - Get specific runtime details
    - POST /api/runtimes - Register a new runtime
    - POST /api/jobs - Start a job with a specific runtime

    Returns:
        RuntimeListResponse: List of all registered runtimes

    Raises:
        HTTPException: 500 if registry is not accessible
    """
    try:
        registry = RuntimeRegistry.get_instance()
        all_runtimes = registry.get_all()
        default_id = registry.get_default_id()

        runtime_infos: List[RuntimeInfo] = []
        for runtime_id, runtime in all_runtimes.items():
            is_default = runtime_id == default_id
            runtime_infos.append(_runtime_to_info(runtime_id, runtime, is_default))

        return RuntimeListResponse(
            runtimes=runtime_infos,
            total=len(runtime_infos),
            default_runtime_id=default_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list runtimes: {str(e)}") from e


@router.get("/runtimes/{runtime_id}", response_model=RuntimeResponse, dependencies=[RequireAuth])
async def get_runtime(runtime_id: str):
    """Get detailed information about a specific Runtime instance.

    **Overview**:
    Returns detailed information about a registered Runtime, including its
    configuration, status, and active job count. Use this to check if a runtime
    is available and healthy before starting a job.

    **Endpoint**: `GET /api/runtimes/{runtime_id}`

    **Use Cases**:
    - Check if a specific runtime exists
    - Verify runtime status before starting a job
    - Monitor runtime health
    - Get runtime configuration details

    **Request Example**:
    ```
    GET /api/runtimes/production
    ```

    **Response Example**:
    ```json
    {
      "runtime": {
        "runtime_id": "production",
        "thread_pool_size": 20,
        "is_default": true,
        "active_job_count": 3,
        "is_shutdown": false
      }
    }
    ```

    **Error Responses**:
    - `404 Not Found`: Runtime with this ID is not registered

    **Related Endpoints**:
    - GET /api/runtimes - List all runtimes
    - POST /api/runtimes - Register a new runtime
    - POST /api/jobs - Start a job with this runtime

    Args:
        runtime_id: Unique runtime identifier

    Returns:
        RuntimeResponse: Runtime information

    Raises:
        HTTPException: 404 if runtime not found
    """
    try:
        registry = RuntimeRegistry.get_instance()
        runtime = registry.get(runtime_id)
        if runtime is None:
            raise HTTPException(status_code=404, detail=f"Runtime '{runtime_id}' not found")

        default_id = registry.get_default_id()
        is_default = runtime_id == default_id

        return RuntimeResponse(runtime=_runtime_to_info(runtime_id, runtime, is_default))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get runtime: {str(e)}") from e


@router.post("/runtimes", response_model=RuntimeResponse, dependencies=[RequireAuth])
async def create_runtime(request: RuntimeCreateRequest):
    """Register a new Runtime instance.

    **Overview**:
    Creates and registers a new Runtime instance with the specified configuration.
    This allows you to create multiple runtimes for different environments (e.g.,
    production, development, testing) with different thread pool sizes.

    **Endpoint**: `POST /api/runtimes`

    **Use Cases**:
    - Create production runtime with large thread pool
    - Create development runtime with small thread pool
    - Create isolated runtime for testing
    - Set up multiple execution environments

    **Request Example**:
    ```json
    {
      "runtime_id": "production",
      "thread_pool_size": 20,
      "is_default": true
    }
    ```

    **Response Example**:
    ```json
    {
      "runtime": {
        "runtime_id": "production",
        "thread_pool_size": 20,
        "is_default": true,
        "active_job_count": 0,
        "is_shutdown": false
      }
    }
    ```

    **Error Responses**:
    - `400 Bad Request`: Runtime ID already exists or invalid parameters
    - `422 Validation Error`: Invalid request parameters

    **Thread Pool Size Guidelines**:
    - `0`: Use GlobalJobManager's thread pool (recommended for most cases)
    - `1-10`: Small workloads, development/testing
    - `10-50`: Medium workloads, production
    - `50-100`: Large workloads, high concurrency
    - `>100`: Not recommended (may cause resource issues)

    **Related Endpoints**:
    - GET /api/runtimes - List all runtimes
    - GET /api/runtimes/{runtime_id} - Get runtime details
    - POST /api/jobs - Start a job with this runtime

    Args:
        request: RuntimeCreateRequest with runtime configuration

    Returns:
        RuntimeResponse: Created runtime information

    Raises:
        HTTPException: 400 if runtime ID already exists
        HTTPException: 422 if validation fails
    """
    try:
        from routilux.core.runtime import Runtime

        registry = RuntimeRegistry.get_instance()

        # Check if runtime_id already exists
        if registry.get(request.runtime_id) is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Runtime '{request.runtime_id}' already exists",
            )

        # Create new Runtime instance
        runtime = Runtime(thread_pool_size=request.thread_pool_size)

        # Register runtime
        registry.register(
            runtime=runtime,
            runtime_id=request.runtime_id,
            is_default=request.is_default,
        )

        return RuntimeResponse(
            runtime=_runtime_to_info(request.runtime_id, runtime, request.is_default)
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create runtime: {str(e)}") from e
