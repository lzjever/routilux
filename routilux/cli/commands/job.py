"""Job management CLI commands."""

import json

import click


@click.group()
def job():
    """Manage workflow jobs.

    \b
    Examples:
        # Submit a job locally
        $ routilux job submit --flow myflow --routine processor --data '{"x": 1}'

        # Submit to remote server
        $ routilux job submit --server http://localhost:8080 --flow myflow ...

        # Check job status
        $ routilux job status <job_id>

        # List jobs
        $ routilux job list --flow myflow
    """
    pass


@job.command("submit")
@click.option("--flow", "-f", required=True, help="Flow ID or name")
@click.option("--routine", "-r", required=True, help="Entry routine ID")
@click.option("--slot", "-s", default="input", help="Input slot name (default: input)")
@click.option("--data", "-d", required=True, help="Input data as JSON string")
@click.option("--server", help="Server URL for remote mode (e.g., http://localhost:8080)")
@click.option("--wait", is_flag=True, help="Wait for job completion")
@click.option("--timeout", default=60.0, type=float, help="Timeout in seconds")
@click.pass_context
def submit(ctx, flow, routine, slot, data, server, wait, timeout):
    """Submit a job to a flow.

    \b
    Examples:
        # Local mode (default)
        $ routilux job submit --flow myflow --routine proc --data '{"x": 1}'

        # Remote mode
        $ routilux job submit --server http://localhost:8080 --flow myflow --routine proc --data '{}'
    """
    quiet = ctx.obj.get("quiet", False)

    try:
        input_data = json.loads(data)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"Invalid JSON data: {e}", param_hint="--data")

    if server:
        # Remote mode - use HTTP API
        result = _submit_remote(server, flow, routine, slot, input_data, wait, timeout)
    else:
        # Local mode - use Runtime directly
        result = _submit_local(flow, routine, slot, input_data, wait, timeout)

    if not quiet:
        click.echo(json.dumps(result, indent=2))


def _submit_local(
    flow_id: str, routine_id: str, slot_name: str, data: dict, wait: bool, timeout: float
) -> dict:
    """Submit job locally using Runtime."""
    from routilux.monitoring.registry import FlowRegistry

    # Get the flow
    flow_registry = FlowRegistry.get_instance()
    flow = flow_registry.get(flow_id)

    if flow is None:
        raise click.ClickException(f"Flow '{flow_id}' not found. Make sure it's loaded.")

    from routilux.core.runtime import Runtime

    runtime = Runtime()

    worker_state, job_context = runtime.post(
        flow_name=flow_id,
        routine_name=routine_id,
        slot_name=slot_name,
        data=data,
        timeout=timeout,
    )

    result = {
        "job_id": job_context.job_id,
        "worker_id": worker_state.worker_id,
        "flow_id": flow_id,
        "status": job_context.status,
    }

    if wait:
        # Wait for completion
        import time

        start = time.time()
        while time.time() - start < timeout:
            if job_context.status in ("completed", "failed"):
                break
            time.sleep(0.1)

        result["status"] = job_context.status
        result["error"] = job_context.error

    return result


def _submit_remote(
    server_url: str,
    flow_id: str,
    routine_id: str,
    slot_name: str,
    data: dict,
    wait: bool,
    timeout: float,
) -> dict:
    """Submit job to remote server via HTTP API."""
    import urllib.error
    import urllib.request

    url = f"{server_url.rstrip('/')}/api/v1/jobs"

    payload = {
        "flow_id": flow_id,
        "routine_id": routine_id,
        "slot_name": slot_name,
        "data": data,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise click.ClickException(f"Server error {e.code}: {error_body}")


@job.command("status")
@click.argument("job_id")
@click.option("--server", help="Server URL for remote mode")
@click.pass_context
def status(ctx, job_id, server):
    """Check job status."""
    quiet = ctx.obj.get("quiet", False)

    if server:
        result = _get_job_status_remote(server, job_id)
    else:
        result = _get_job_status_local(job_id)

    if not quiet:
        click.echo(json.dumps(result, indent=2))


def _get_job_status_local(job_id: str) -> dict:
    """Get job status locally."""
    from routilux.monitoring.runtime_registry import RuntimeRegistry

    runtime_registry = RuntimeRegistry.get_instance()
    job = runtime_registry.get_job(job_id)

    if job is None:
        raise click.ClickException(f"Job '{job_id}' not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "error": job.error,
    }


def _get_job_status_remote(server_url: str, job_id: str) -> dict:
    """Get job status from remote server."""
    import urllib.error
    import urllib.request

    url = f"{server_url.rstrip('/')}/api/v1/jobs/{job_id}"

    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError:
        raise click.ClickException(f"Job not found: {job_id}")


@job.command("list")
@click.option("--flow", "-f", help="Filter by flow ID")
@click.option("--server", help="Server URL for remote mode")
@click.pass_context
def list_jobs(ctx, flow, server):
    """List jobs."""
    quiet = ctx.obj.get("quiet", False)

    if server:
        result = _list_jobs_remote(server, flow)
    else:
        result = _list_jobs_local(flow)

    if not quiet:
        click.echo(json.dumps(result, indent=2))


def _list_jobs_local(flow_id: str = None) -> list:
    """List jobs locally."""
    from routilux.monitoring.runtime_registry import RuntimeRegistry

    runtime_registry = RuntimeRegistry.get_instance()
    jobs = runtime_registry.list_jobs()

    if flow_id:
        jobs = [j for j in jobs if j.get("flow_id") == flow_id]

    return jobs


def _list_jobs_remote(server_url: str, flow_id: str = None) -> list:
    """List jobs from remote server."""
    import urllib.request

    url = f"{server_url.rstrip('/')}/api/v1/jobs"
    if flow_id:
        url += f"?flow_id={flow_id}"

    req = urllib.request.Request(url, method="GET")

    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())
        return data.get("jobs", [])
