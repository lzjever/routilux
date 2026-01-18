"""
One-shot execution API route.

Provides a simple endpoint to execute a flow with optional waiting.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException

from routilux.server.errors import ErrorCode, create_error_response
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.execute import ExecuteRequest, ExecuteResponse
from routilux.server.dependencies import (
    get_runtime,
    get_job_storage,
    get_idempotency_backend,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=ExecuteResponse, dependencies=[RequireAuth])
async def execute_flow(request: ExecuteRequest):
    """
    One-shot flow execution.
    
    This is a convenience endpoint that:
    1. Creates a new Worker
    2. Submits a Job with the provided data
    3. Optionally waits for completion
    
    Use this for simple "submit and get result" workflows.
    For complex interactive workflows, use the Worker and Job endpoints directly.
    
    **Example Request (async)**:
    ```json
    {
      "flow_id": "data_processing_flow",
      "routine_id": "data_source",
      "slot_name": "input",
      "data": {"value": 42},
      "wait": false
    }
    ```
    
    **Example Request (sync)**:
    ```json
    {
      "flow_id": "data_processing_flow",
      "routine_id": "data_source",
      "slot_name": "input",
      "data": {"value": 42},
      "wait": true,
      "timeout": 30.0
    }
    ```
    """
    runtime = get_runtime()
    job_storage = get_job_storage()
    idempotency = get_idempotency_backend()
    
    start_time = time.time()
    
    # Check idempotency key
    if request.idempotency_key:
        cached = idempotency.get(request.idempotency_key)
        if cached is not None:
            return ExecuteResponse(**cached)
    
    try:
        # Submit job via Runtime.post() - this creates a new worker
        worker_state, job_context = runtime.post(
            flow_name=request.flow_id,
            routine_name=request.routine_id,
            slot_name=request.slot_name,
            data=request.data,
            worker_id=None,  # Always create new worker for one-shot
            metadata=request.metadata,
        )
        
        job_storage.save_job(job_context, flow_id=worker_state.flow_id)
        
        logger.info(f"Execute: created job {job_context.job_id} on worker {worker_state.worker_id}")
        
        if not request.wait:
            # Return immediately
            response = ExecuteResponse(
                job_id=job_context.job_id,
                worker_id=worker_state.worker_id,
                status=job_context.status,
            )
            
            if request.idempotency_key:
                idempotency.set(request.idempotency_key, response.model_dump(), ttl_seconds=86400)
            
            return response
        
        # Wait for completion
        timeout = request.timeout
        poll_interval = 0.1
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                response = ExecuteResponse(
                    job_id=job_context.job_id,
                    worker_id=worker_state.worker_id,
                    status="timeout",
                    error=f"Job did not complete within {timeout} seconds",
                    elapsed_seconds=elapsed,
                )
                
                if request.idempotency_key:
                    idempotency.set(request.idempotency_key, response.model_dump(), ttl_seconds=86400)
                
                return response
            
            # Check job status
            current_job = runtime.get_job(job_context.job_id)
            if current_job and current_job.status in ("completed", "failed"):
                # Get output
                output = None
                try:
                    from routilux.core.output import get_job_output
                    output = get_job_output(job_context.job_id, incremental=False)
                except Exception:
                    pass
                
                response = ExecuteResponse(
                    job_id=job_context.job_id,
                    worker_id=worker_state.worker_id,
                    status=current_job.status,
                    output=output if output else None,
                    result=current_job.data if current_job.data else None,
                    error=current_job.error,
                    elapsed_seconds=time.time() - start_time,
                )
                
                if request.idempotency_key:
                    idempotency.set(request.idempotency_key, response.model_dump(), ttl_seconds=86400)
                
                logger.info(f"Execute: job {job_context.job_id} completed with status {current_job.status}")
                return response
            
            await asyncio.sleep(poll_interval)
    
    except ValueError as e:
        error_msg = str(e)
        if "Flow" in error_msg:
            error_code = ErrorCode.FLOW_NOT_FOUND
        elif "Routine" in error_msg:
            error_code = ErrorCode.ROUTINE_NOT_FOUND
        elif "Slot" in error_msg:
            error_code = ErrorCode.SLOT_NOT_FOUND
        else:
            error_code = ErrorCode.JOB_SUBMISSION_FAILED
        
        raise HTTPException(
            status_code=404,
            detail=create_error_response(error_code, error_msg)
        )
    except RuntimeError as e:
        if "shutdown" in str(e).lower():
            raise HTTPException(
                status_code=503,
                detail=create_error_response(ErrorCode.RUNTIME_SHUTDOWN, str(e))
            )
        raise HTTPException(
            status_code=400,
            detail=create_error_response(ErrorCode.JOB_SUBMISSION_FAILED, str(e))
        )
