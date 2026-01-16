"""
Debug operations API routes.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from routilux.api.models.debug import ExpressionEvalRequest, ExpressionEvalResponse
from routilux.api.security import SecurityError, TimeoutError, safe_evaluate
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import job_store

router = APIRouter()


class VariableSetRequest(BaseModel):
    """Request to set a variable."""

    value: Any


@router.get("/jobs/{job_id}/debug/session")
async def get_debug_session(job_id: str):
    """Get debug session information."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        return {"status": "no_session", "job_id": job_id}

    return {
        "session_id": session.session_id,
        "job_id": session.job_id,
        "status": session.status,
        "paused_at": {
            "routine_id": session.paused_at.routine_id if session.paused_at else None,
        }
        if session.paused_at
        else None,
        "call_stack_depth": len(session.call_stack),
    }


@router.post("/jobs/{job_id}/debug/resume")
async def resume_debug(job_id: str):
    """Resume execution from breakpoint."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No debug session for job '{job_id}'")

    session.resume()

    return {"status": "resumed", "job_id": job_id}


@router.post("/jobs/{job_id}/debug/step-over")
async def step_over(job_id: str):
    """Step over current line."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No debug session for job '{job_id}'")

    session.step_over()

    return {"status": "stepping", "job_id": job_id, "step_mode": "over"}


@router.post("/jobs/{job_id}/debug/step-into")
async def step_into(job_id: str):
    """Step into function."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No debug session for job '{job_id}'")

    session.step_into()

    return {"status": "stepping", "job_id": job_id, "step_mode": "into"}


@router.get("/jobs/{job_id}/debug/variables")
async def get_variables(job_id: str, routine_id: str = None):
    """Get variables at current breakpoint."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No debug session for job '{job_id}'")

    # Fix: Add validation for routine_id when call stack is empty
    if not routine_id and not session.call_stack:
        raise HTTPException(
            status_code=400,
            detail="routine_id must be specified when not paused at a breakpoint"
        )

    variables = session.get_variables(routine_id)

    return {
        "job_id": job_id,
        "routine_id": routine_id,
        "variables": variables,
    }


@router.put("/jobs/{job_id}/debug/variables/{name}")
async def set_variable(job_id: str, name: str, request: VariableSetRequest):
    """Set variable value at current breakpoint."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No debug session for job '{job_id}'")

    # Get routine_id from paused context
    routine_id = session.paused_at.routine_id if session.paused_at else None
    if not routine_id:
        raise HTTPException(status_code=400, detail="No paused context available")

    session.set_variable(routine_id, name, request.value)

    return {
        "job_id": job_id,
        "variable": name,
        "value": request.value,
    }


@router.get("/jobs/{job_id}/debug/call-stack")
async def get_call_stack(job_id: str):
    """Get call stack."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No debug session for job '{job_id}'")

    call_stack = session.get_call_stack()

    return {
        "job_id": job_id,
        "call_stack": [
            {
                "routine_id": frame.routine_id,
                "slot_name": frame.slot_name,
                "event_name": frame.event_name,
                "variables": list(frame.variables.keys()),
            }
            for frame in call_stack
        ],
    }


@router.post("/jobs/{job_id}/debug/evaluate", response_model=ExpressionEvalResponse)
async def evaluate_expression(job_id: str, request: ExpressionEvalRequest):
    """Evaluate an expression in the context of a paused job.

    Supports Python expressions with access to local and global variables
    from the specified routine and stack frame.

    **Security**: Expression evaluation is sandboxed and only allows safe operations.

    Args:
        job_id: Job identifier.
        request: Evaluation request with expression and context.

    Returns:
        ExpressionEvalResponse: Evaluation result or error.

    Raises:
        404: If job or debug session not found.
        400: If job is not paused.
        400: If expression is unsafe or times out.
    """
    import os

    # Check if expression evaluation is enabled
    if os.getenv("ROUTILUX_EXPRESSION_EVAL_ENABLED", "false").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail="Expression evaluation is disabled. Set ROUTILUX_EXPRESSION_EVAL_ENABLED=true to enable.",
        )

    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Get debug session
    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    debug_store = registry.debug_session_store

    if not debug_store:
        raise HTTPException(status_code=500, detail="Debug session store not available")

    session = debug_store.get(job_id)
    if not session:
        raise HTTPException(status_code=404, detail="No debug session for job '{job_id}'")

    # Check if job is paused
    if session.status != "paused":
        raise HTTPException(status_code=400, detail="Job must be paused to evaluate expressions")

    # Get variables from specified routine
    routine_id = request.routine_id
    if not routine_id and session.paused_at:
        routine_id = session.paused_at.routine_id

    if not routine_id:
        raise HTTPException(
            status_code=400,
            detail="No routine context available. Specify routine_id or ensure job is paused.",
        )

    variables = session.get_variables(routine_id)

    # Get timeout from config
    timeout = float(os.getenv("ROUTILUX_EXPRESSION_EVAL_TIMEOUT", "5.0"))

    # Evaluate expression
    try:
        result = safe_evaluate(expression=request.expression, variables=variables, timeout=timeout)
        return ExpressionEvalResponse(result=result["value"], type=result["type"], error=None)

    except SecurityError as e:
        return ExpressionEvalResponse(result=None, type=None, error=f"Security error: {str(e)}")

    except TimeoutError as e:
        return ExpressionEvalResponse(result=None, type=None, error=f"Timeout: {str(e)}")

    except ValueError as e:
        return ExpressionEvalResponse(result=None, type=None, error=f"Syntax error: {str(e)}")

    except Exception as e:
        return ExpressionEvalResponse(result=None, type=None, error=f"Evaluation error: {str(e)}")
