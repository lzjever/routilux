"""
Health check API routes.

Provides endpoints for Kubernetes-style health checks:
- /health/live: Liveness probe
- /health/ready: Readiness probe
"""

import logging

from fastapi import APIRouter

from routilux.server.dependencies import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health/live")
async def liveness():
    """
    Kubernetes liveness probe.
    
    Returns 200 if the process is alive.
    Use this for container orchestration to detect unresponsive processes.
    
    **Response**:
    ```json
    {"status": "ok"}
    ```
    """
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """
    Kubernetes readiness probe.
    
    Returns 200 if the service is ready to accept traffic.
    
    Checks:
    - Runtime is not shut down
    - Can access core components
    
    **Response (ready)**:
    ```json
    {
      "status": "ready",
      "runtime": {
        "shutdown": false,
        "active_workers": 5
      }
    }
    ```
    
    **Response (not ready)**:
    ```json
    {
      "status": "not_ready",
      "reason": "runtime_shutdown"
    }
    ```
    """
    try:
        runtime = get_runtime()
        
        if runtime._shutdown:
            return {
                "status": "not_ready",
                "reason": "runtime_shutdown"
            }
        
        # Get worker count
        with runtime._worker_lock:
            active_workers = len(runtime._active_workers)
        
        return {
            "status": "ready",
            "runtime": {
                "shutdown": runtime._shutdown,
                "active_workers": active_workers
            }
        }
    except Exception as e:
        logger.warning(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "reason": str(e)
        }


@router.get("/health/stats")
async def health_stats():
    """
    Get detailed health statistics.
    
    Returns comprehensive statistics about the system's health and performance.
    """
    try:
        runtime = get_runtime()
        
        # Collect statistics
        with runtime._worker_lock:
            active_workers = len(runtime._active_workers)
            worker_statuses = {}
            for worker in runtime._active_workers.values():
                status = worker.status.value if hasattr(worker.status, "value") else str(worker.status)
                worker_statuses[status] = worker_statuses.get(status, 0) + 1
        
        with runtime._jobs_lock:
            total_jobs = sum(len(jobs) for jobs in runtime._active_jobs.values())
        
        return {
            "status": "ok",
            "runtime": {
                "shutdown": runtime._shutdown,
                "active_workers": active_workers,
                "worker_statuses": worker_statuses,
                "active_jobs": total_jobs,
            }
        }
    except Exception as e:
        logger.warning(f"Health stats failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
