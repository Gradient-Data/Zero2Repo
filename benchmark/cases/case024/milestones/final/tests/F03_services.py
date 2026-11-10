# feature: F03
"""Simulated S3 and Google Cloud Storage services for offline storage checks.

These are stand-ins, not the real providers: S3 is moto's model over HTTP and
GCS is a small hand-written subset of the JSON API. They show the product's
storage work reaches a service through the SDK protocol; they do not show
behaviour against the real providers. Each listens on 127.0.0.1. The product
reaches it only through the providers' standard SDK environment settings
(AWS_ENDPOINT_URL_S3 with AWS credentials; STORAGE_EMULATOR_HOST with Google
application-default credentials). Tests observe stored objects through an
independent provider SDK client of the same service, never through the product,
so an implementation that keeps data anywhere else is seen as missing it.

The services start once per test process and stay up, because SDK clients may
cache their endpoint. Every object_store() call allocates a fresh
bucket, so tests never share objects.

Azure Blob Storage is not served: the product reaches it only through the
public *.blob.core.windows.net hosts, which an offline judge cannot provide.
"""
import base64
import hashlib
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

_lock = threading.Lock()
_started = {}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _body(self):
        length = int(self.headers.get("content-length") or 0)
        return self.rfile.read(length) if length else b""

    def _reply(self, status, body=b"", content_type="application/json", headers=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


# ------------------------------------------------------------------ S3


class _S3Handler(_Handler):
    """Serve the S3 REST protocol with moto's S3 model (path-style requests)."""

    model_lock = threading.Lock()

    def _route(self):
        from botocore.awsrequest import HTTPHeaders
        from moto.core.exceptions import HTTPException
        from moto.s3.responses import S3ResponseInstance

        body = self._body()
        url = "https://s3.amazonaws.com" + self.path
        headers = HTTPHeaders()
        for name, value in self.headers.items():
            headers[name] = value
        headers["host"] = "s3.amazonaws.com"

        class Request:
            pass

        request = Request()
        request.method, request.url, request.headers, request.body = (
            self.command, url, headers, body)
        parts = urlsplit(url).path.lstrip("/").split("/", 1)
        try:
            with self.model_lock:
                if len(parts) == 1 or parts[1] == "":
                    status, out_headers, out = S3ResponseInstance.bucket_response(
                        request, url, headers)
                else:
                    status, out_headers, out = S3ResponseInstance.key_response(
                        request, url, headers)
        except HTTPException as error:
            status, out_headers, out = error.code, error.get_headers(), error.get_body()
        if isinstance(out, str):
            out = out.encode("utf-8")
        out = out or b""
        out_headers = dict(out_headers)
        lowered = {key.lower(): value for key, value in out_headers.items()}
        self.send_response(int(status))
        for name, value in out_headers.items():
            if name.lower() not in ("content-length", "status"):
                self.send_header(name, str(value))
        if self.command == "HEAD":
            self.send_header("Content-Length", str(lowered.get("content-length", len(out))))
            self.end_headers()
            return
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = do_PUT = do_POST = do_HEAD = do_DELETE = _route


# ------------------------------------------------------------------ GCS


class _GCSStore:
    def __init__(self):
        self.objects = {}
        self.sessions = {}
        self.generation = 0
        self.lock = threading.Lock()

    def put(self, bucket, key, data):
        self.generation += 1
        self.objects[(bucket, key)] = (data, self.generation)
        return self.generation


def _gcs_meta(bucket, key, data, generation):
    return {"kind": "storage#object", "name": key, "bucket": bucket,
            "size": str(len(data)), "generation": str(generation),
            "metageneration": "1",
            "md5Hash": base64.b64encode(hashlib.md5(data).digest()).decode(),
            "etag": base64.b64encode(str(generation).encode()).decode(),
            "contentType": "application/octet-stream",
            "updated": "2026-01-01T00:00:00.000Z",
            "timeCreated": "2026-01-01T00:00:00.000Z",
            "id": "{}/{}/{}".format(bucket, key, generation)}


class _GCSHandler(_Handler):
    """Serve the subset of the Cloud Storage JSON API used by its SDKs."""

    store = _GCSStore()

    def _missing(self):
        self._reply(404, {"error": {"code": 404, "message": "No such object"}})

    def _route(self):
        store = self.store
        parts = urlsplit(self.path)
        query = {key: values[-1] for key, values in
                 parse_qs(parts.query, keep_blank_values=True).items()}
        path, data = parts.path, self._body()
        if path.startswith("/token"):
            return self._reply(200, {"access_token": "loopback", "expires_in": 3600,
                                     "token_type": "Bearer"})
        match = re.fullmatch(r"/download/storage/v1/b/([^/]+)/o/(.+)", path)
        if match is None and query.get("alt") == "media":
            match = re.fullmatch(r"/storage/v1/b/([^/]+)/o/(.+)", path)
        if match and self.command in ("GET", "HEAD"):
            with store.lock:
                found = store.objects.get((match.group(1), unquote(match.group(2))))
            if found is None:
                return self._missing()
            content = found[0]
            requested = self.headers.get("Range")
            if requested:
                start, _, end = requested.split("=", 1)[1].partition("-")
                start = int(start)
                end = int(end) if end else len(content) - 1
                piece = content[start:end + 1]
                return self._reply(206, piece, "application/octet-stream", [
                    ("Content-Range", "bytes {}-{}/{}".format(
                        start, start + len(piece) - 1, len(content)))])
            return self._reply(200, content, "application/octet-stream")
        match = re.fullmatch(r"/upload/storage/v1/b/([^/]+)/o", path)
        if match and self.command == "POST":
            bucket, kind = match.group(1), query.get("uploadType")
            if kind == "multipart":
                boundary = self.headers.get("Content-Type", "").split("boundary=")[1]
                boundary = boundary.strip('"').encode()
                pieces = [piece for piece in data.split(b"--" + boundary)
                          if piece.strip() not in (b"", b"--")]
                meta = json.loads(pieces[0].split(b"\r\n\r\n", 1)[1].strip() or b"{}")
                payload = pieces[1].split(b"\r\n\r\n", 1)[1]
                if payload.endswith(b"\r\n"):
                    payload = payload[:-2]
                key = meta.get("name") or query.get("name")
            elif kind == "media":
                key, payload = query["name"], data
            elif kind == "resumable":
                meta = json.loads(data or b"{}")
                with store.lock:
                    session = uuid.uuid4().hex
                    store.sessions[session] = [bucket, meta.get("name") or query.get("name"), b""]
                location = "http://{}/upload/session/{}".format(self.headers.get("Host"), session)
                return self._reply(200, {}, headers=[("Location", location)])
            else:
                return self._reply(400, {"error": {"code": 400, "message": "upload type"}})
            with store.lock:
                generation = store.put(bucket, key, payload)
            return self._reply(200, _gcs_meta(bucket, key, payload, generation))
        match = re.fullmatch(r"/upload/session/([^/]+)", path)
        if match and self.command in ("POST", "PUT"):
            with store.lock:
                session = store.sessions.get(match.group(1))
                if session is None:
                    return self._missing()
                session[2] += data
                total = (self.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
                if total in ("", None) or (total != "*" and len(session[2]) >= int(total)):
                    bucket, key, payload = session
                    del store.sessions[match.group(1)]
                    generation = store.put(bucket, key, payload)
                    return self._reply(200, _gcs_meta(bucket, key, payload, generation))
                received = len(session[2])
            return self._reply(308, b"", headers=[("Range", "bytes=0-{}".format(received - 1))])
        match = re.fullmatch(
            r"/storage/v1/b/([^/]+)/o/(.+)/(rewriteTo|copyTo)/b/([^/]+)/o/(.+)", path)
        if match and self.command == "POST":
            with store.lock:
                found = store.objects.get((match.group(1), unquote(match.group(2))))
                if found is None:
                    return self._missing()
                bucket, key = match.group(4), unquote(match.group(5))
                generation = store.put(bucket, key, found[0])
                meta = _gcs_meta(bucket, key, found[0], generation)
            if match.group(3) == "copyTo":
                return self._reply(200, meta)
            return self._reply(200, {"kind": "storage#rewriteResponse", "done": True,
                                     "resource": meta, "objectSize": meta["size"],
                                     "totalBytesRewritten": meta["size"]})
        match = re.fullmatch(r"/storage/v1/b/([^/]+)/o/(.+)", path)
        if match:
            bucket, key = match.group(1), unquote(match.group(2))
            with store.lock:
                found = store.objects.get((bucket, key))
                if found is not None and self.command == "DELETE":
                    del store.objects[(bucket, key)]
                    return self._reply(204, b"")
            if found is None:
                return self._missing()
            return self._reply(200, _gcs_meta(bucket, key, *found))
        match = re.fullmatch(r"/storage/v1/b/([^/]+)/o/?", path)
        if match and self.command == "GET":
            bucket = match.group(1)
            prefix, delimiter = query.get("prefix", ""), query.get("delimiter", "")
            items, prefixes = [], set()
            with store.lock:
                listing = sorted((key, value) for (name, key), value in store.objects.items()
                                 if name == bucket and key.startswith(prefix))
            for key, (content, generation) in listing:
                rest = key[len(prefix):]
                if delimiter and delimiter in rest:
                    prefixes.add(prefix + rest.split(delimiter, 1)[0] + delimiter)
                else:
                    items.append(_gcs_meta(bucket, key, content, generation))
            return self._reply(200, {"kind": "storage#objects", "items": items,
                                     "prefixes": sorted(prefixes)})
        match = re.fullmatch(r"/storage/v1/b/([^/]+)/?", path)
        if match and self.command == "GET":
            return self._reply(200, {"kind": "storage#bucket", "name": match.group(1),
                                     "id": match.group(1)})
        return self._reply(400, {"error": {"code": 400, "message": "unsupported request"}})

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_PATCH = _route


# ------------------------------------------------------------------ lifecycle


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "http://127.0.0.1:{}".format(server.server_port)


def _google_credentials(directory, token_endpoint):
    """Write a service-account credential whose token endpoint is the loopback service."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    path = Path(directory) / "google-credentials.json"
    path.write_text(json.dumps({
        "type": "service_account", "project_id": "loopback", "private_key_id": "loopback",
        "private_key": key, "client_email": "acceptance@loopback.iam.gserviceaccount.com",
        "client_id": "1", "token_uri": token_endpoint + "/token"}), encoding="utf-8")
    return str(path)


def service_environment():
    """Start the services once; return the provider SDK environment that reaches them."""
    import tempfile

    with _lock:
        if not _started:
            s3 = _serve(_S3Handler)
            gcs = _serve(_GCSHandler)
            directory = tempfile.mkdtemp(prefix="loopback-credentials-")
            _started.update({
                "AWS_ENDPOINT_URL_S3": s3,
                "AWS_ACCESS_KEY_ID": "loopback",
                "AWS_SECRET_ACCESS_KEY": "loopback",
                "AWS_DEFAULT_REGION": "us-east-1",
                "AWS_EC2_METADATA_DISABLED": "true",
                "STORAGE_EMULATOR_HOST": gcs,
                "GOOGLE_APPLICATION_CREDENTIALS": _google_credentials(directory, gcs),
                "GOOGLE_CLOUD_PROJECT": "loopback",
            })
        return dict(_started)


class ObjectStore:
    """Independent provider-SDK view of one bucket: read, write, exists, remove, keys."""

    def __init__(self, scheme, bucket, read, write, exists, remove, keys):
        self.scheme, self.bucket = scheme, bucket
        self.root = "{}://{}".format(scheme, bucket)
        self.read, self.write, self.exists, self.remove, self.keys = (
            read, write, exists, remove, keys)

    def url(self, key):
        return self.root + "/" + key


def _s3_store(environment):
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3", endpoint_url=environment["AWS_ENDPOINT_URL_S3"], region_name="us-east-1",
        aws_access_key_id="loopback", aws_secret_access_key="loopback")
    bucket = "acceptance-" + uuid.uuid4().hex[:12]
    client.create_bucket(Bucket=bucket)

    def exists(key):
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise
        return True

    def read(key):
        return client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def write(key, data):
        client.put_object(Bucket=bucket, Key=key, Body=data)

    def remove(key):
        client.delete_object(Bucket=bucket, Key=key)

    def keys(prefix=""):
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        return sorted(entry["Key"] for page in pages for entry in page.get("Contents", []))

    return ObjectStore("s3", bucket, read, write, exists, remove, keys)


def _gcs_store(environment):
    from google.api_core.client_options import ClientOptions
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import storage

    client = storage.Client(
        project="loopback", credentials=AnonymousCredentials(),
        client_options=ClientOptions(api_endpoint=environment["STORAGE_EMULATOR_HOST"]))
    name = "acceptance-" + uuid.uuid4().hex[:12]
    bucket = client.bucket(name)

    def keys(prefix=""):
        return sorted(blob.name for blob in client.list_blobs(name, prefix=prefix))

    return ObjectStore(
        "gs", name,
        read=lambda key: bucket.blob(key).download_as_bytes(),
        write=lambda key, data: bucket.blob(key).upload_from_string(data),
        exists=lambda key: bucket.blob(key).exists(),
        remove=lambda key: bucket.blob(key).delete(),
        keys=keys)


@contextmanager
def object_store(scheme):
    """Yield an ObjectStore over a fresh bucket of the 's3' or 'gs' stand-in service.

    The provider SDK environment that reaches the services is applied to this
    process (and so to threads and subprocesses it starts) inside the block and
    restored afterwards, so later tests see the environment they started with.
    """
    environment = service_environment()
    previous = {name: os.environ.get(name) for name in environment}
    os.environ.update(environment)
    try:
        if scheme == "s3":
            yield _s3_store(environment)
        elif scheme == "gs":
            yield _gcs_store(environment)
        else:
            raise ValueError("Unsupported loopback storage service: " + scheme)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
