# feature: F13
"""Stand-in container runtime and AWS Batch service for offline remote-execution checks.

These are stand-ins, not the real services. They speak the interfaces the
product is documented to use (the `docker` command line; the AWS Batch, STS and
CloudWatch Logs HTTP APIs reached through the AWS SDK's per-service endpoint
settings) and run each submitted container command as a separate local
process. Every request they receive is recorded so tests observe what the
product asked the service for, and every task body writes its own evidence
file, so a product that runs work in its own process instead of submitting it
is seen as not having used the service.
"""
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from velnora import task
from _helpers import candidate_cli_environment

MARKER = "F13_STAND_IN_CONTAINER"


def stop_client(process):
    """Stop this client's process group and reap it, even if it already exited."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # An exited process group already satisfies the cleanup request.
    process.wait(timeout=30)


# ------------------------------------------------------------------ authored work


@task(namespace="f13", cache=False)
def remote_area(width, height, evidence):
    """Record where the body ran, then compute from the supplied arguments."""
    record = {"pid": os.getpid(), "marker": os.environ.get(MARKER),
              "node": os.environ.get("AWS_BATCH_JOB_NODE_INDEX"),
              "args": [width, height]}
    path = Path(evidence) / ("{}-{}.json".format(os.getpid(), uuid.uuid4().hex))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))
    return {"area": width * height, "node": record["node"]}


@task(namespace="f13", cache=False)
def remote_failure(label):
    raise ValueError("remote failure " + label)


@task(namespace="f13", cache=False)
def local_sum(values):
    return sum(values)


def evidence_records(directory):
    directory = Path(directory)
    if not directory.exists():
        return []
    return [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]


# ------------------------------------------------------------------ shared environment


def _python_path():
    import velnora
    return os.pathsep.join([str(Path(__file__).resolve().parent),
                            str(Path(velnora.__file__).resolve().parent.parent),
                            os.environ.get("PYTHONPATH", "")])


@contextmanager
def patched_environment(values):
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _run_container_command(command, workdir, extra_env, log_path):
    """Run one container command as a separate process; return its exit status."""
    env = dict(os.environ)
    env.update(extra_env)
    env[MARKER] = "1"
    env["PYTHONPATH"] = _python_path()
    with open(log_path, "ab") as log:
        return subprocess.call(command, cwd=workdir, env=env, stdout=log, stderr=log)


# ------------------------------------------------------------------ docker stand-in


_DOCKER_SHIM = r'''#!{python}
import json, os, shlex, subprocess, sys, uuid
state = {state!r}
argv = sys.argv[1:]
with open(os.path.join(state, "calls.jsonl"), "a") as out:
    out.write(json.dumps(argv) + "\n")
command = argv[0] if argv else ""
containers = os.path.join(state, "containers")
os.makedirs(containers, exist_ok=True)
if command == "run":
    rest, options = argv[1:], {{"env": [], "volumes": [], "flags": []}}
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag in ("-e", "-v", "--cidfile", "--gpus"):
            value = rest.pop(0)
            if flag == "-e": options["env"].append(value)
            elif flag == "-v": options["volumes"].append(value)
            elif flag == "--cidfile": options["cidfile"] = value
        else:
            options["flags"].append(flag)
    image, cmd = rest[0], rest[1:]
    cid = uuid.uuid4().hex
    with open(os.path.join(state, "runs.jsonl"), "a") as out:
        out.write(json.dumps({{"id": cid, "image": image, "command": cmd, **options}}) + "\n")
    env = dict(os.environ)
    env[{marker!r}] = "1"
    forwarded = {{}}
    for item in options["env"]:
        name, separator, value = item.partition("=")
        if separator:
            forwarded[name] = value
        elif name in env:
            forwarded[name] = env[name]
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                 "AWS_DEFAULT_REGION"):
        env.pop(name, None)
    env.update(forwarded)
    env["PYTHONPATH"] = {pythonpath!r}
    env["PATH"] = {bindir!r} + os.pathsep + env.get("PATH", "")
    log = open(os.path.join(containers, cid + ".log"), "wb")
    done = os.path.join(containers, cid + ".done")
    wrapped = ["bash", "-c", '"$@"; status=$?; echo $status > ' + shlex.quote(done) + '; exit $status', "container"] + cmd
    process = subprocess.Popen(wrapped, cwd={workdir!r}, env=env, stdout=log, stderr=log,
                               start_new_session=True)
    open(os.path.join(containers, cid + ".id"), "w").close()
    if "-d" in options["flags"]:
        print(cid)
    else:
        status = process.wait()
        with open(options["cidfile"], "w") as out:
            out.write(cid)
        sys.exit(status)
elif command == "ps":
    print("CONTAINER ID   IMAGE   COMMAND")
    for name in os.listdir(containers):
        if name.endswith(".id") and not os.path.exists(os.path.join(containers, name[:-3] + ".done")):
            print(name[:-3] + "   image   cmd")
elif command == "logs":
    path = os.path.join(containers, argv[1] + ".log")
    sys.stdout.write(open(path).read())
elif command == "rm":
    print(argv[1])
else:
    sys.stderr.write("unsupported docker command: %r\n" % (argv,))
    sys.exit(2)
'''


@contextmanager
def docker_stand_in(workdir):
    """Put a stand-in `docker` first on PATH; yield a reader of recorded `run` calls."""
    state = Path(tempfile.mkdtemp(prefix="docker-stand-in-"))
    bindir = state / "bin"
    bindir.mkdir()
    shim = bindir / "docker"
    shim.write_text(_DOCKER_SHIM.format(
        python=sys.executable, state=str(state), marker=MARKER, pythonpath=_python_path(),
        bindir=os.path.dirname(sys.executable), workdir=str(workdir)))
    shim.chmod(0o755)

    def runs():
        path = state / "runs.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def wait(container_id, timeout=60):
        """Observe the real command's exit, retaining its complete diagnostics."""
        done = state / 'containers' / (container_id + '.done')
        log = state / 'containers' / (container_id + '.log')
        completed = wait_until(lambda: done.exists() and done.stat().st_size > 0, timeout)
        diagnostics = log.read_text()  # A missing log is an observation failure.
        assert completed, f'Worker {container_id} did not finish:\n{diagnostics}'
        status = int(done.read_text())
        assert status == 0, f'Worker {container_id} exited {status}:\n{diagnostics}'
        return diagnostics

    runs.wait = wait

    with candidate_cli_environment() as cli_env:
        with patched_environment({"PATH": str(bindir) + os.pathsep + cli_env["PATH"]}):
            yield runs


# ------------------------------------------------------------------ AWS Batch stand-in


class BatchService:
    """In-memory AWS Batch: records requests and runs container commands as processes.

    Job definitions live in one registry per process, as they would in one
    account: a client may reuse a definition it registered earlier.
    """

    shared_definitions = {}

    def __init__(self, workdir, s3_environment):
        self.workdir = Path(workdir)
        self.s3_environment = s3_environment
        self.lock = threading.Lock()
        self.definitions = BatchService.shared_definitions
        self.jobs = {}
        self.submissions = []
        self.descriptions = []
        self.hold = threading.Event()
        self.hold.set()
        self.logdir = Path(tempfile.mkdtemp(prefix="batch-stand-in-"))
        self.invocations = []
        self.fail_before_start = False

    # -- operations
    def wait(self, job_id, timeout=60):
        """Observe service completion with original command diagnostics."""
        def finished():
            with self.lock:
                return self.jobs[job_id]['status'] in ('SUCCEEDED', 'FAILED')

        completed = wait_until(finished, timeout)
        diagnostics = (self.logdir / (job_id + '.log')).read_text()
        assert completed, f'Worker {job_id} did not finish:\n{diagnostics}'
        with self.lock:
            status = self.jobs[job_id]['status']
        assert status == 'SUCCEEDED', f'Worker {job_id} failed:\n{diagnostics}'
        return diagnostics

    def describe_job_definitions(self, body):
        name = body.get("jobDefinitionName")
        with self.lock:
            found = [d for d in self.definitions.values()
                     if name is None or d["jobDefinitionName"] == name]
        return {"jobDefinitions": found}

    def register_job_definition(self, body):
        with self.lock:
            revision = 1 + sum(1 for d in self.definitions.values()
                               if d["jobDefinitionName"] == body["jobDefinitionName"])
            arn = "arn:aws:batch:us-east-1:123456789012:job-definition/{}:{}".format(
                body["jobDefinitionName"], revision)
            definition = dict(body, jobDefinitionArn=arn, revision=revision, status="ACTIVE")
            self.definitions[arn] = definition
        return {"jobDefinitionName": body["jobDefinitionName"], "jobDefinitionArn": arn,
                "revision": revision}

    def submit_job(self, body):
        job_id = uuid.uuid4().hex
        with self.lock:
            definition = self.definitions.get(body["jobDefinition"])
            if definition is None:
                raise LookupError("Job definition does not exist")
            self.submissions.append({"jobId": job_id, "request": body, "definition": definition})
            job = {"jobId": job_id, "jobName": body["jobName"], "jobQueue": body["jobQueue"],
                   "status": "RUNNING", "jobDefinition": body["jobDefinition"],
                   "createdAt": int(time.time() * 1000), "attempts": [],
                   "container": {"logStreamName": job_id}}
            if "arrayProperties" in body:
                job["arrayProperties"] = {"size": body["arrayProperties"]["size"]}
            self.jobs[job_id] = job
            for index in range(body.get("arrayProperties", {}).get("size", 0)):
                child_id = job_id + ":" + str(index)
                self.jobs[child_id] = dict(job, jobId=child_id,
                    arrayProperties={"index": index},
                    container={"logStreamName": child_id})
        threading.Thread(target=self._run, args=(job_id, body, definition), daemon=True).start()
        return {"jobId": job_id, "jobName": body["jobName"], "jobArn": "arn:job/" + job_id}

    def _commands(self, body, definition):
        if "nodeOverrides" in body:
            overrides = body["nodeOverrides"]["nodePropertyOverrides"]
            count = definition["nodeProperties"]["numNodes"]
            main = next(o for o in overrides if o["targetNodes"] == "0")
            worker = next(o for o in overrides if o["targetNodes"] != "0")
            return [(main["containerOverrides"]["command"], {"AWS_BATCH_JOB_NODE_INDEX": "0",
                                                             "AWS_BATCH_JOB_MAIN_NODE_INDEX": "0"})] + [
                (worker["containerOverrides"]["command"],
                 {"AWS_BATCH_JOB_NODE_INDEX": str(index), "AWS_BATCH_JOB_MAIN_NODE_INDEX": "0"})
                for index in range(1, count)]
        command = body["containerOverrides"]["command"]
        size = body.get("arrayProperties", {}).get("size")
        if size:
            return [(command, {"AWS_BATCH_JOB_ARRAY_INDEX": str(index)}) for index in range(size)]
        return [(command, {})]

    def _run(self, job_id, body, definition):
        self.hold.wait(120)
        if self.fail_before_start:
            with self.lock:
                self.jobs[job_id].update(status="FAILED", attempts=[{
                    "container": {"reason": "Execution environment could not start"},
                    "statusReason": "Execution environment could not start"}])
            return
        environment = dict(self.s3_environment)
        statuses = []
        threads = []
        for index, (command, extra) in enumerate(self._commands(body, definition)):
            def work(command=command, extra=extra, index=index):
                child_id = (job_id + ":" + str(index)
                            if "arrayProperties" in body else job_id)
                workdir = Path(tempfile.mkdtemp(prefix="worker-", dir=self.logdir))
                log_path = self.logdir / (child_id + ".log")
                try:
                    status = _run_container_command(
                        command, workdir, {**environment, **extra}, log_path)
                except OSError:
                    # A failed process start is a service failure, with its
                    # original traceback retained rather than a lost thread.
                    diagnostics = traceback.format_exc()
                    with log_path.open("a") as log:
                        log.write(diagnostics)
                    with self.lock:
                        self.jobs[child_id]["attempts"] = [{
                            "container": {"reason": diagnostics},
                            "statusReason": diagnostics}]
                    status = 1
                with self.lock:
                    statuses.append(status)
                    self.jobs[child_id]["status"] = "SUCCEEDED" if status == 0 else "FAILED"
                    self.jobs[child_id]["stoppedAt"] = int(time.time() * 1000)
            thread = threading.Thread(target=work)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join(300)
        with self.lock:
            self.jobs[job_id]["status"] = (
                "SUCCEEDED" if statuses and all(s == 0 for s in statuses) else "FAILED")
            self.jobs[job_id]["stoppedAt"] = int(time.time() * 1000)

    def describe_jobs(self, body):
        with self.lock:
            self.descriptions.append(list(body["jobs"]))
            return {"jobs": [dict(self.jobs[j]) for j in body["jobs"] if j in self.jobs]}

    def list_jobs(self, body):
        statuses = {body.get("jobStatus")} if body.get("jobStatus") else None
        with self.lock:
            found = [{"jobId": j["jobId"], "jobName": j["jobName"], "status": j["status"],
                      "createdAt": j["createdAt"],
                      **({"arrayProperties": j["arrayProperties"]}
                         if "arrayProperties" in j else {})}
                     for j in self.jobs.values()
                     if ((body.get("arrayJobId") and
                          j["jobId"].startswith(body["arrayJobId"] + ":")) or
                         (not body.get("arrayJobId") and ":" not in j["jobId"] and
                          j["jobQueue"] == body.get("jobQueue"))) and
                     (statuses is None or j["status"] in statuses)]
        return {"jobSummaryList": found}

    def terminate_job(self, body):
        return {}


def _batch_handler(holder):
    names = {"/v1/describejobdefinitions": "describe_job_definitions",
             "/v1/registerjobdefinition": "register_job_definition",
             "/v1/submitjob": "submit_job", "/v1/describejobs": "describe_jobs",
             "/v1/listjobs": "list_jobs", "/v1/terminatejob": "terminate_job"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _reply(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b""
            target = self.headers.get("X-Amz-Target", "")
            if self.path in names:
                operation = getattr(holder["service"], names[self.path])
                try:
                    return self._reply(200, operation(json.loads(raw or b"{}")))
                except (LookupError, ValueError) as error:
                    return self._reply(400, {"__type": "ClientException", "message": str(error)})
            if self.path.startswith("/2015-03-31/functions/") and self.path.endswith("/invocations"):
                name = self.path[len("/2015-03-31/functions/"):-len("/invocations")]
                holder["service"].invocations.append({"function": name,
                                                      "payload": json.loads(raw or b"null")})
                return self._reply(200, b"null")
            if target.endswith("GetLogEvents"):
                return self._reply(200, {"events": [], "nextForwardToken": "f",
                                         "nextBackwardToken": "b"},
                                   "application/x-amz-json-1.1")
            if "GetCallerIdentity" in parse_qs(raw.decode()).get("Action", [""])[0]:
                return self._reply(200, (
                    b'<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
                    b"<GetCallerIdentityResult><Arn>arn:aws:iam::123456789012:user/acceptance</Arn>"
                    b"<UserId>ACCEPTANCE</UserId><Account>123456789012</Account>"
                    b"</GetCallerIdentityResult><ResponseMetadata><RequestId>1</RequestId>"
                    b"</ResponseMetadata></GetCallerIdentityResponse>"), "text/xml")
            return self._reply(400, {"message": "unsupported " + self.path})

    return Handler


_batch_server = {}


@contextmanager
def batch_stand_in(workdir, s3_environment):
    """Yield (service, environment) for a stand-in AWS Batch with STS, Logs and Lambda Invoke.

    One server runs per test process at a fixed endpoint, because the product
    may keep SDK clients bound to an endpoint for the life of the process; each
    use starts with no jobs and an empty submission record.
    """
    service = BatchService(workdir, s3_environment)
    if not _batch_server:
        holder = {"service": service}

        server = ThreadingHTTPServer(("127.0.0.1", 0), _batch_handler(holder))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _batch_server.update(holder=holder, endpoint="http://127.0.0.1:{}".format(
            server.server_port))
    _batch_server["holder"]["service"] = service
    endpoint = _batch_server["endpoint"]
    environment = {"AWS_ENDPOINT_URL_BATCH": endpoint, "AWS_ENDPOINT_URL_STS": endpoint,
                   "AWS_ENDPOINT_URL_CLOUDWATCH_LOGS": endpoint,
                   "AWS_ENDPOINT_URL_LAMBDA": endpoint}
    try:
        with candidate_cli_environment() as cli_env:
            with patched_environment({**environment, **cli_env}):
                yield service, environment
    finally:
        service.hold.set()


def batch_config(name, queue, scratch, **options):
    settings = {"type": "aws_batch", "image": "acceptance/worker:7", "queue": queue,
                "s3_scratch": scratch, "aws_region": "us-east-1", "role": "none",
                "job_monitor_interval": "0.2", "job_stale_time": "0.2", "code_package": "False"}
    settings.update({key: str(value) for key, value in options.items()})
    return {"executors." + name: settings}


@task(namespace="f13")
def gated_area(width, height, evidence, gate):
    """Record the run, then wait until the test opens the gate file."""
    record = {"pid": os.getpid(), "marker": os.environ.get(MARKER), "args": [width, height]}
    path = Path(evidence) / ("{}-{}.json".format(os.getpid(), uuid.uuid4().hex))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))
    deadline = time.time() + 120
    while not Path(gate).exists() and time.time() < deadline:
        time.sleep(0.1)
    return width * height + 1


CLIENT = r'''
import json, sys
from velnora import Scheduler
from velnora.config import Config
from F13_helpers import gated_area
settings = json.loads(sys.argv[1])
config = Config(settings["config"])
scheduler = Scheduler(config=config)
scheduler.load()
expression = gated_area.options(executor="batch", cache_scope=settings["scope"])(
    *settings["args"])
result = scheduler.run(expression, cache=settings["cache"])
print("RESULT " + json.dumps(result))
'''


def start_client(workdir, config, args, scope="BACKEND", cache=True):
    """Start a separate workflow client process; return the Popen object."""
    env = dict(os.environ)
    env["PYTHONPATH"] = _python_path()
    return subprocess.Popen(
        [sys.executable, "-c", CLIENT,
         json.dumps({"config": config, "args": args, "scope": scope, "cache": cache})],
        cwd=workdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)


def wait_until(predicate, timeout=60, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


EVALUATE = r'''
import json, sys
from velnora import Scheduler
from velnora.config import Config
import F13_helpers
from velnora import script
F13_helpers.script = script
settings = json.loads(sys.argv[1])
scheduler = Scheduler(config=Config(settings["config"]))
scheduler.load()
expression = eval(settings["expression"], vars(F13_helpers))
try:
    result = scheduler.run(expression)
except Exception as error:
    if settings["error_details"]:
        print("ERROR " + json.dumps({"type": type(error).__name__, "message": error.message}))
    else:
        print("ERROR " + type(error).__name__)
else:
    print("RESULT " + json.dumps(result))
'''


def run_in_client(workdir, config, expression, timeout=180, error_details=False):
    """Run one workflow in a fresh client process (fresh SDK clients and caches).

    `expression` is Python source evaluated against F13_helpers. Returns
    ("RESULT", value) or ("ERROR", exception class name).
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = _python_path()
    completed = subprocess.run(
        [sys.executable, "-c", EVALUATE, json.dumps({"config": config, "expression": expression, "error_details": error_details})],
        cwd=workdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=timeout)
    assert completed.returncode == 0, completed.stdout
    for line in completed.stdout.splitlines():
        if line.startswith("RESULT "):
            return "RESULT", json.loads(line[len("RESULT "):])
        if line.startswith("ERROR "):
            payload = line[len("ERROR "):]
            return "ERROR", json.loads(payload) if error_details else payload
    raise AssertionError("client produced no outcome:\n" + completed.stdout[-3000:])


@task(namespace="f13", cache=False)
def remote_environment():
    """Compute from the worker's actual credential environment."""
    import hashlib
    names = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
             "AWS_DEFAULT_REGION")
    values = [os.environ.get(name) for name in names]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()
