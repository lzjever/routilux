"""
Pydantic models for Runtime API.

All models include detailed field descriptions and examples for frontend developers.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class RuntimeInfo(BaseModel):
    """Information about a registered Runtime instance.

    This model provides details about a Runtime, including its configuration,
    status, and active job count.
    """

    runtime_id: str = Field(
        ...,
        description="Unique identifier for this runtime. Use this ID when starting jobs.",
        example="production",
    )
    thread_pool_size: int = Field(
        ...,
        description="Maximum number of worker threads in the thread pool. "
        "0 means using GlobalJobManager's thread pool.",
        example=10,
    )
    is_default: bool = Field(
        ...,
        description="Whether this is the default runtime. "
        "If runtime_id is not specified when starting a job, the default runtime is used.",
        example=True,
    )
    active_job_count: int = Field(
        ...,
        description="Number of active jobs currently running in this runtime.",
        example=5,
    )
    is_shutdown: bool = Field(
        ...,
        description="Whether this runtime has been shut down.",
        example=False,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "runtime_id": "production",
                    "thread_pool_size": 20,
                    "is_default": True,
                    "active_job_count": 3,
                    "is_shutdown": False,
                },
                {
                    "runtime_id": "development",
                    "thread_pool_size": 5,
                    "is_default": False,
                    "active_job_count": 0,
                    "is_shutdown": False,
                },
            ]
        }
    }


class RuntimeListResponse(BaseModel):
    """Response model for listing all runtimes.

    Returns a list of all registered Runtime instances with their information.
    """

    runtimes: List[RuntimeInfo] = Field(
        ...,
        description="List of all registered Runtime instances.",
    )
    total: int = Field(
        ...,
        description="Total number of registered runtimes.",
        example=2,
    )
    default_runtime_id: Optional[str] = Field(
        None,
        description="ID of the default runtime. This is used when runtime_id is not specified.",
        example="production",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "runtimes": [
                        {
                            "runtime_id": "production",
                            "thread_pool_size": 20,
                            "is_default": True,
                            "active_job_count": 3,
                            "is_shutdown": False,
                        },
                        {
                            "runtime_id": "development",
                            "thread_pool_size": 5,
                            "is_default": False,
                            "active_job_count": 0,
                            "is_shutdown": False,
                        },
                    ],
                    "total": 2,
                    "default_runtime_id": "production",
                }
            ]
        }
    }


class RuntimeResponse(BaseModel):
    """Response model for getting a specific runtime.

    Returns detailed information about a single Runtime instance.
    """

    runtime: RuntimeInfo = Field(
        ...,
        description="Runtime information.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "runtime": {
                        "runtime_id": "production",
                        "thread_pool_size": 20,
                        "is_default": True,
                        "active_job_count": 3,
                        "is_shutdown": False,
                    }
                }
            ]
        }
    }


class RuntimeCreateRequest(BaseModel):
    """Request model for creating/registering a new runtime.

    This allows clients to register a new Runtime instance with a custom ID.
    """

    runtime_id: str = Field(
        ...,
        description="Unique identifier for this runtime. Must be unique across all runtimes.",
        example="production",
    )
    thread_pool_size: int = Field(
        10,
        description="Maximum number of worker threads in the thread pool. "
        "Set to 0 to use GlobalJobManager's thread pool. "
        "Default: 10. Maximum recommended: 100.",
        example=20,
        ge=0,
        le=1000,
    )
    is_default: bool = Field(
        False,
        description="Whether to set this runtime as the default. "
        "If True, this runtime will be used when runtime_id is not specified.",
        example=False,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "runtime_id": "production",
                    "thread_pool_size": 20,
                    "is_default": True,
                },
                {
                    "runtime_id": "development",
                    "thread_pool_size": 5,
                    "is_default": False,
                },
            ]
        }
    }
