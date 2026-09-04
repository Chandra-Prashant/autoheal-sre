import os
import shutil
import subprocess
import tempfile

import docker
from docker.errors import DockerException, ImageNotFound

IMAGE = "autoheal-sandbox:latest"
DOCKERFILE_DIR = os.path.dirname(__file__)
TIMEOUT = 30


def capture_trace(repo_path: str, test_target: str) -> str:
    # runs directly on the host, not sandboxed - this is just to capture
    # what the failure looks like before the fix loop starts
    result = subprocess.run(
        ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", test_target],
        cwd=repo_path, capture_output=True, text=True,
    )
    return result.stdout + result.stderr


def apply_patch(repo_path: str, patch: str) -> str:
    workdir = tempfile.mkdtemp(prefix="autoheal-")
    shutil.copytree(repo_path, workdir, dirs_exist_ok=True)

    patch_file = os.path.join(workdir, "_autoheal.patch")
    with open(patch_file, "w") as f:
        f.write(patch)

    result = subprocess.run(
        ["patch", "-p1", "-i", patch_file], cwd=workdir, capture_output=True, text=True
    )
    os.remove(patch_file)
    if result.returncode != 0:
        shutil.rmtree(workdir, ignore_errors=True)
        raise ValueError(f"patch failed to apply:\n{result.stdout}{result.stderr}")
    return workdir


def _ensure_image(client):
    try:
        client.images.get(IMAGE)
    except ImageNotFound:
        client.images.build(path=DOCKERFILE_DIR, tag=IMAGE)


def run_tests(repo_path: str, test_cmd: str = "pytest -q -p no:cacheprovider") -> tuple[bool, str]:
    try:
        client = docker.from_env()
        _ensure_image(client)
    except DockerException as e:
        return False, f"docker not available: {e}"

    container = client.containers.run(
        IMAGE,
        command=["sh", "-c", test_cmd],
        volumes={os.path.abspath(repo_path): {"bind": "/workspace", "mode": "rw"}},
        working_dir="/workspace",
        network_mode="none",
        mem_limit="512m",
        read_only=True,
        tmpfs={"/tmp": "rw,size=64m"},
        detach=True,
    )
    try:
        result = container.wait(timeout=TIMEOUT)
        logs = container.logs().decode(errors="replace")
        passed = result["StatusCode"] == 0
    except Exception as e:
        passed = False
        logs = f"sandbox execution error: {e}"
    finally:
        container.remove(force=True)

    return passed, logs
