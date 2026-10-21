#!/usr/bin/env python3
"""Start the genuine, isolated Butterfly Supabase preview without printing keys."""

import argparse
import copy
import http.client
import io
import json
import os
from pathlib import Path
import re
import signal
import secrets
import socket
import subprocess
import sys
import tarfile
import time
import tomllib
from urllib.request import Request, urlopen
from urllib.error import HTTPError


PROJECT = "butterfly-staff-preview"
SERVICES = ("db", "kong", "auth", "rest", "storage", "inbucket", "edge_runtime")
# The Edge CLI installs a generated main worker into the writable layer.
# The specialized Edge repair below preserves it before changing local routing.
REPAIR_SERVICES = ("auth", "storage")
EXCLUDE = "studio,vector,realtime,imgproxy,logflare,supavisor,postgres-meta"
REQUIRED_STATUS = ("API_URL", "ANON_KEY", "SERVICE_ROLE_KEY", "DB_URL", "JWT_SECRET")


class SetupError(Exception):
    """A sanitized error safe for the terminal."""


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode:
        raise SetupError("Docker operation failed; no credential-bearing output was printed.")
    return result


def inspect(name):
    result = docker("container", "inspect", name, check=False)
    if result.returncode:
        return None
    try:
        data = json.loads(result.stdout)
        return data[0] if isinstance(data, list) and data else None
    except (ValueError, IndexError):
        raise SetupError("Docker returned invalid container metadata.") from None


class DockerConnection(http.client.HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("localhost", timeout=60)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def create_container(name, config):
    host = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}").stdout.strip()
    if not host.startswith("unix://"):
        raise SetupError("This local repair requires the configured Unix Docker socket.")
    connection = DockerConnection(host.removeprefix("unix://"))
    try:
        body = json.dumps(config).encode()
        connection.request("POST", "/containers/create?name=" + name, body,
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        response.read()
        if response.status != 201:
            raise SetupError("Docker could not recreate the local service; original configuration retained.")
    finally:
        connection.close()


def assert_own(name, metadata):
    if name not in {f"supabase_{service}_{PROJECT}" for service in SERVICES}:
        raise SetupError("Refusing to change an unrelated container.")
    labels = metadata.get("Config", {}).get("Labels", {}) or {}
    if labels.get("com.supabase.cli.project") != PROJECT:
        raise SetupError("Local container project label does not match the expected preview.")


def endpoint_configs(metadata):
    result = {}
    for name, endpoint in metadata.get("NetworkSettings", {}).get("Networks", {}).items():
        if name != f"supabase_network_{PROJECT}":
            raise SetupError("Unexpected local service network; refusing to alter its configuration.")
        result[name] = {
            key: copy.deepcopy(endpoint[key])
            for key in ("IPAMConfig", "Links", "Aliases", "DriverOpts")
            if endpoint.get(key) is not None
        }
    if not result:
        raise SetupError("Expected local service network is absent.")
    return result


def repair_local_http_proxy(name):
    """Recreate only an owned service, preserving its image, mounts and probes."""
    original = inspect(name)
    if original is None:
        raise SetupError("Expected local service is absent; inspect the private startup log.")
    assert_own(name, original)
    env = dict(item.split("=", 1) for item in original["Config"].get("Env", []) if "=" in item)
    if "HTTP_PROXY" in env and "http_proxy" in env and not env["HTTP_PROXY"] and not env["http_proxy"]:
        return
    endpoints = endpoint_configs(original)
    config = copy.deepcopy(original["Config"])
    # Docker's managed default proxies apply when CLI drops empty variables.
    # Explicit empty HTTP bindings preserve internal HTTP health/API traffic.
    # All HTTPS proxy values and the original healthcheck remain unchanged.
    env["HTTP_PROXY"] = ""
    env["http_proxy"] = ""
    config["Env"] = [key + "=" + value for key, value in env.items()]
    config["HostConfig"] = copy.deepcopy(original["HostConfig"])
    config["NetworkingConfig"] = {"EndpointsConfig": endpoints}
    backup_name = name + "-before-proxy-repair-" + str(time.time_ns())
    docker("stop", name)
    docker("rename", name, backup_name)
    for network in endpoints:
        docker("network", "disconnect", network, backup_name)
    try:
        create_container(name, config)
        docker("start", name)
    except Exception:
        docker("rm", "--force", name, check=False)
        docker("rename", backup_name, name, check=False)
        # Network aliases and mount data were not removed or rewritten.
        for network, endpoint in endpoints.items():
            args = ["network", "connect"]
            for alias in endpoint.get("Aliases", []):
                args.extend(["--alias", alias])
            docker(*args, network, name, check=False)
        docker("start", name, check=False)
        raise SetupError("Local proxy repair failed; original service was restored.") from None
    # Do not use -v: named database/storage volumes must survive service changes.
    docker("rm", backup_name)
    print("Configured local HTTP routing:", name, flush=True)


def wait_for_health(timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = True
        for service in SERVICES:
            name = f"supabase_{service}_{PROJECT}"
            metadata = inspect(name)
            if metadata is None:
                ready = False
                continue
            assert_own(name, metadata)
            state = metadata["State"]
            if not state.get("Running") or state.get("Health", {}).get("Status", "healthy") != "healthy":
                ready = False
        if ready:
            return
        time.sleep(1)
    raise SetupError("Original local container healthchecks have not all passed; preview is not ready.")


def private_file(path):
    if path.is_symlink():
        raise SetupError("Refusing to write a private file through a symlink.")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "w")


def capture_status(cli, workdir, private_dir):
    command = [str(cli), "status", "--workdir", str(workdir), "-o", "json"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise SetupError("Local CLI status failed; credentials were not published.")
    try:
        status = json.loads(result.stdout)
        if not isinstance(status, dict) or any(not status.get(key) for key in REQUIRED_STATUS):
            raise ValueError("Missing required fields")
    except ValueError:
        raise SetupError("Local CLI status is incomplete; credentials were not published.") from None
    path = private_dir / "local-supabase.json"
    temporary = private_dir / "local-supabase.json.tmp"
    with private_file(temporary) as stream:
        json.dump(status, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return status


def require_api(status):
    headers = {"apikey": status["ANON_KEY"]}
    for path in ("/auth/v1/health", "/storage/v1/status", "/rest/v1/"):
        request = Request(status["API_URL"] + path, headers=headers)
        try:
            with urlopen(request, timeout=10) as response:
                body = response.read()
                if response.status != 200:
                    raise ValueError("Unexpected status")
                if path == "/auth/v1/health" and json.loads(body).get("name") != "GoTrue":
                    raise ValueError("Unexpected Auth service")
                if path == "/rest/v1/":
                    description = json.loads(body)
                    if not (description.get("openapi") or description.get("swagger")):
                        raise ValueError("Unexpected Data API service")
        except Exception:
            raise SetupError("Local API content readiness failed for " + path + ".") from None
        print("Verified actual local API:", path, flush=True)


def prepare_runtime(source, private_dir):
    """Keep generated CLI secrets outside the public checkout."""
    with private_file(private_dir / "local-function-build.log") as stream:
        build = subprocess.run(["node", str(source / "scripts/bundle-local-sdk.mjs")],
                               stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    if build.returncode:
        raise SetupError("Verified local function build failed; install pinned staff dependencies first.")
    runtime = private_dir / "local-runtime"
    supabase = runtime / "supabase"
    supabase.mkdir(mode=0o700, parents=True, exist_ok=True)
    text = (source / "supabase/config.toml").read_text()

    def local_function(match):
        name = match.group(2)
        if not (source / "supabase/functions/.env.local-preview" / name / "index.js").is_file():
            raise SetupError("Expected compiled local function is absent.")
        body = "\n".join(line for line in match.group(3).splitlines()
                         if not line.startswith(("entrypoint =", "import_map =")))
        return (match.group(1) + body + '\nentrypoint = "./functions/.env.local-preview/' + name + '/index.js"\n'
                'import_map = "./functions/.env.local-preview/compiled-import-map.json"\n')

    text, count = re.subn(r"(?ms)(^\[functions\.([a-z][a-z-]+)\]\n)(.*?)(?=^\[|\Z)", local_function, text)
    if count < 1:
        raise SetupError("Expected function configuration is absent.")
    with private_file(supabase / "config.toml") as stream:
        stream.write(text)
    for name in ("functions", "migrations"):
        target = supabase / name
        expected = source / "supabase" / name
        if target.is_symlink():
            if target.resolve() != expected.resolve():
                raise SetupError("Private runtime source link points to an unexpected location.")
        elif target.exists():
            raise SetupError("Private runtime source path already contains an unrelated file.")
        else:
            target.symlink_to(expected, target_is_directory=True)
    return runtime


def stop_managed_functions(private_dir, source, runtime):
    path = private_dir / "functions-serve.pid"
    if not path.exists():
        return
    try:
        pid = int(path.read_text().strip())
        process = Path("/proc", str(pid))
        if not process.exists() or (process / "stat").read_text().split()[2] == "Z":
            return
        args = (process / "cmdline").read_bytes().split(b"\0")
        if (b"functions" not in args or b"serve" not in args or
                not any(str(root).encode() in args for root in (source, runtime)) or
                os.getpgid(pid) != pid):
            raise SetupError("Refusing to stop an unrelated function-server process.")
        os.killpg(pid, signal.SIGINT)
        for _ in range(100):
            if not process.exists() or (process / "stat").read_text().split()[2] == "Z":
                return
            time.sleep(0.1)
        raise SetupError("Managed function server has not finished cleanup; no new instance started.")
    except (ValueError, ProcessLookupError):
        return


def serve_functions(cli, source, runtime, private_dir, process_env=None):
    stop_managed_functions(private_dir, source, runtime)
    # The CLI reuses an existing Edge container, including its old route/env
    # configuration. Recreate this stateless owned service to discover new routes.
    previous = inspect(f"supabase_edge_runtime_{PROJECT}")
    if previous:
        assert_own(f"supabase_edge_runtime_{PROJECT}", previous)
        docker("rm", "--force", f"supabase_edge_runtime_{PROJECT}")
    env_file = private_dir / "edge.env"
    if env_file.exists():
        # Preserve other private bindings; change only the proven local HTTP route.
        lines = [line for line in env_file.read_text().splitlines()
                 if not line.startswith(("HTTP_PROXY=", "http_proxy=", "DENO_CERT="))]
    else:
        lines = ["BUTTERFLY_STAFF_ORIGIN=http://127.0.0.1:5173",
                 "BUTTERFLY_STAFF_REDIRECT_URL=http://127.0.0.1:5173/staff/"]
    if not any(line.startswith("BUTTERFLY_PUBLIC_ORIGINS=") for line in lines):
        lines.append("BUTTERFLY_PUBLIC_ORIGINS=http://127.0.0.1:8000,http://127.0.0.1:8002,http://127.0.0.1:8003")
    if not any(line.startswith("BUTTERFLY_ENQUIRY_RATE_SECRET=") for line in lines):
        lines.append("BUTTERFLY_ENQUIRY_RATE_SECRET=" + secrets.token_urlsafe(48))
    lines.extend(["HTTP_PROXY=", "http_proxy="])
    with private_file(env_file) as stream:
        stream.write("\n".join(lines) + "\n")
    with private_file(private_dir / "functions-serve.log") as stream:
        process = subprocess.Popen([str(cli), "functions", "serve", "--workdir", str(runtime),
                                    "--env-file", str(env_file)], stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, env=process_env)
    with private_file(private_dir / "functions-serve.pid") as stream:
        stream.write(str(process.pid) + "\n")
    # CLI copies its generated main worker into the writable layer; compiled
    # function files remain bind mounts. Preserve the worker before replacing
    # the process-level HTTP proxy bindings; worker env alone is too late for
    # Rust's fetch client. No image commit, retag, or database change is involved.
    name = f"supabase_edge_runtime_{PROJECT}"
    required = ["/root/index.ts"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        original = inspect(name)
        if (original and original.get("State", {}).get("Running") and
                (original.get("Config", {}).get("Labels") or {}).get("com.supabase.cli.project") == PROJECT):
            captured = []
            for path in required:
                result = subprocess.run(["docker", "cp", name + ":" + path, "-"], capture_output=True)
                if result.returncode:
                    break
                with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
                    members = [member for member in archive.getmembers() if member.isfile()]
                    if len(members) != 1:
                        raise SetupError("Unexpected generated Edge bootstrap archive.")
                    member = members[0]
                    captured.append((path, member.mode, archive.extractfile(member).read()))
            if len(captured) == len(required):
                break
        if process.poll() is not None:
            raise SetupError("Local function bootstrap process exited before preparation completed.")
        time.sleep(0.5)
    else:
        raise SetupError("Local function bootstrap files were not created.")
    assert_own(name, original)
    endpoints = endpoint_configs(original)
    config = copy.deepcopy(original["Config"])
    env = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
    env["HTTP_PROXY"] = ""
    env["http_proxy"] = ""
    config["Env"] = [key + "=" + value for key, value in env.items()]
    config["HostConfig"] = copy.deepcopy(original["HostConfig"])
    config["NetworkingConfig"] = {"EndpointsConfig": endpoints}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        parents = set()
        for path, mode, data in captured:
            relative = Path(path.lstrip("/"))
            for parent in reversed(relative.parents):
                if str(parent) in (".", "root") or str(parent) in parents:
                    continue
                member = tarfile.TarInfo(str(parent))
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                archive.addfile(member)
                parents.add(str(parent))
            member = tarfile.TarInfo(str(relative))
            member.mode = mode
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    archive_path = private_dir / "edge-bootstrap.tar"
    descriptor = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(buffer.getvalue())
    stop_managed_functions(private_dir, source, runtime)
    previous = inspect(name)
    if previous:
        # CLI cleanup can remove project labels before removing the container.
        # Its captured ID was ownership-checked before stopping the CLI.
        if previous.get("Id") != original.get("Id"):
            assert_own(name, previous)
        docker("rm", "--force", name)
    create_container(name, config)
    restored = subprocess.run(["docker", "cp", "-", name + ":/"], input=buffer.getvalue(), capture_output=True)
    if restored.returncode:
        raise SetupError("Could not restore the exact generated Edge bootstrap before startup.")
    docker("start", name)
    print("Configured local Edge HTTP routing; exact generated bootstrap restored.", flush=True)


def require_function(status, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = Request(status["API_URL"] + "/functions/v1/invite-staff", method="POST", data=b"{}",
                          headers={"Origin": "http://127.0.0.1:5173", "Content-Type": "application/json",
                                   "apikey": status["ANON_KEY"]})
        try:
            with urlopen(request, timeout=5):
                raise SetupError("Anonymous invitation unexpectedly succeeded.")
        except HTTPError as error:
            try:
                body = json.loads(error.read())
            except ValueError:
                body = {}
            if error.code == 401 and body == {"error": "Sign in is required."}:
                if error.headers.get("Cache-Control") != "no-store":
                    raise SetupError("Invitation handler is missing its privacy response header.")
                print("Verified actual invitation handler: exact anonymous-denial payload and no-store.", flush=True)
                return
            if error.code == 503 and body.get("code") == "BOOT_ERROR":
                raise SetupError("Invitation worker could not compile; inspect its private log securely.") from None
            if error.code not in (404, 500, 502, 503):
                raise SetupError("Invitation function returned an unexpected readiness response.") from None
        except OSError:
            pass
        time.sleep(0.5)
    raise SetupError("Actual invitation function is not ready.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cli", type=Path, default=Path("/workspace/.butterfly-tools/supabase"))
    parser.add_argument("--private-dir", type=Path, default=Path("/workspace/.butterfly-private"))
    parser.add_argument("--repair-only", action="store_true", help="Repair an already retained local stack.")
    parser.add_argument("--stop", action="store_true", help="Stop only this local stack, preserving data volumes.")
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    if tomllib.loads((workdir / "supabase/config.toml").read_text()).get("project_id") != PROJECT:
        raise SetupError("Supabase project does not match the isolated preview.")
    private_dir = args.private_dir
    if private_dir.is_symlink():
        raise SetupError("Private directory cannot be a symlink.")
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_dir.chmod(0o700)
    version = subprocess.run([str(args.cli), "--version"], capture_output=True, text=True)
    if version.returncode or version.stdout.strip() != "2.121.0":
        raise SetupError("Install and activate the documented official CLI version 2.121.0 first.")
    runtime = prepare_runtime(workdir, private_dir)
    if args.stop:
        stop_managed_functions(private_dir, workdir, runtime)
        with private_file(private_dir / "supabase-local-stop.log") as stream:
            result = subprocess.run([str(args.cli), "stop", "--workdir", str(runtime)],
                                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SetupError("Local stack stop failed; inspect the private stop log securely.")
        print("Stopped only the local preview; database and Storage volumes preserved.")
        return
    if not args.repair_only:
        log = private_dir / "supabase-local-start.log"
        with private_file(log) as stream:
            result = subprocess.run([str(args.cli), "start", "--workdir", str(runtime),
                                     "--exclude", EXCLUDE, "--ignore-health-check"],
                                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SetupError("Local stack creation failed; inspect the private startup log securely.")
    for service in REPAIR_SERVICES:
        repair_local_http_proxy(f"supabase_{service}_{PROJECT}")
    serve_functions(args.cli, workdir, runtime, private_dir)
    wait_for_health()
    status = capture_status(args.cli, runtime, private_dir)
    require_api(status)
    require_function(status)
    print("Local Supabase services and actual invitation handler are ready; private status saved atomically.")
    print("Direct permissions, invitation delivery and recovery acceptance remain separate checks.")


if __name__ == "__main__":
    try:
        main()
    except SetupError as error:
        print("Local preview setup failed:", error, file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Local preview setup failed; no credential-bearing details were printed.", file=sys.stderr)
        raise SystemExit(1)
