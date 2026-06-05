import asyncio
import logging
from typing import Any

from fastapi import HTTPException

from .config import DOCKER_NETWORK, WORKSPACE_IMAGE
from .security import container_name

logger = logging.getLogger(__name__)


class DockerOrchestrator:
    """Spawn workspaces via argv-only subprocess (no shell).

    Security choices:
    - Never invoke a shell; arguments are a fixed argv list.
    - cap-drop ALL + no-new-privileges reduces container breakout impact.
    - code-server runs with --auth none because ONLY the gateway can reach
      the container on the internal Docker network; student auth is enforced
      at the gateway session + /lab proxy.
    """

    async def _run(self, *args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        return proc.returncode or 0, stdout_b.decode(), stderr_b.decode()

    async def ensure_network(self) -> None:
        code, _, err = await self._run(
            "docker",
            "network",
            "inspect",
            DOCKER_NETWORK,
        )
        if code == 0:
            return
        create_code, out, create_err = await self._run(
            "docker",
            "network",
            "create",
            DOCKER_NETWORK,
        )
        if create_code != 0 and "already exists" not in create_err.lower():
            logger.error("network create failed: %s %s", out, create_err)
            raise HTTPException(
                status_code=503,
                detail=f"Docker network unavailable: {create_err}",
            )

    async def container_running(self, name: str) -> bool:
        code, out, _ = await self._run(
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            name,
        )
        return code == 0 and out.strip().lower() == "true"

    async def deploy_workspace(self, username: str) -> dict[str, Any]:
        await self.ensure_network()
        name = container_name(username)
        if await self.container_running(name):
            return {"container_name": name, "already_running": True}

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--cpus",
            "0.25",
            "--memory",
            "512m",
            "--pids-limit",
            "128",
            "--network",
            DOCKER_NETWORK,
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            WORKSPACE_IMAGE,
            "--auth",
            "none",
            "--bind-addr",
            "0.0.0.0:8080",
        ]
        code, out, err = await self._run(*cmd)
        if code != 0:
            if "already in use" in err.lower() or "Conflict" in err:
                start_code, _, start_err = await self._run("docker", "start", name)
                if start_code != 0:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Workspace start failed: {start_err}",
                    )
                return {"container_name": name, "restarted": True}
            raise HTTPException(
                status_code=503,
                detail=f"Workspace deployment failed: {err or out}",
            )
        container_id = out.strip()[:12]
        return {
            "container_name": name,
            "container_id": container_id,
            "network": DOCKER_NETWORK,
        }

    async def ensure_running(self, username: str) -> None:
        name = container_name(username)
        if await self.container_running(name):
            return
        code, _, err = await self._run("docker", "start", name)
        if code != 0:
            raise HTTPException(
                status_code=503,
                detail=f"Could not start workspace: {err}",
            )

    async def stop_workspace(self, username: str) -> None:
        name = container_name(username)
        await self._run("docker", "stop", name)

    async def remove_workspace(self, username: str) -> None:
        name = container_name(username)
        await self._run("docker", "rm", "-f", name)


_orchestrator: DockerOrchestrator | None = None


def get_orchestrator() -> DockerOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DockerOrchestrator()
    return _orchestrator
