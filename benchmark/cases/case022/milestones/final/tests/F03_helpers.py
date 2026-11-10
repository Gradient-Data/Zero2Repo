# feature: F03
"""Assertions for public ranked search results, allowing arbitrary tie order."""
from contextlib import contextmanager

import numpy as np


def assert_ranked_hits(scores, keys, expected_scores, count, *, largest=False):
    keys = list(keys)
    scores = list(scores)
    assert len(keys) == len(scores) == count
    assert len(set(keys)) == count
    assert set(keys) <= set(expected_scores)
    # The oracle is supplied independently of any product search result.
    np.testing.assert_allclose(scores, [expected_scores[key] for key in keys], rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(
        scores, sorted(expected_scores.values(), reverse=largest)[:count], rtol=1e-6, atol=1e-6)


def assert_ranked_examples(result, rows, expected_scores, count, *, largest=False):
    assert_ranked_hits(result.scores, result.examples['id'], expected_scores, count, largest=largest)
    originals = {row['id']: row for row in rows}
    assert result.examples == {
        column: [originals[key][column] for key in result.examples['id']]
        for column in rows[0]
    }


@contextmanager
def local_elasticsearch():
    """Start the bundled real server offline, in a writable temporary directory.

    Each caller owns its process and files. Startup failures expose the server log;
    no missing dependency is converted into a skip or an empty search result.
    """
    import json
    import os
    from pathlib import Path
    import signal
    import socket
    import subprocess
    import tarfile
    import tempfile
    import time
    import urllib.error
    import urllib.request

    assets = Path(__file__).parent / 'resources' / 'F03'
    with tempfile.TemporaryDirectory(prefix='F03-elasticsearch-') as directory:
        root = Path(directory)
        with tarfile.open(assets / 'F03_elasticsearch.tar.gz') as archive:
            archive.extractall(root, filter='data')
        home = root / 'elasticsearch-7.17.29'
        # Ports are selected by the OS, rather than requiring a shared fixed port.
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        endpoint = f'http://127.0.0.1:{port}'
        config = home / 'config' / 'elasticsearch.yml'
        config.write_text(
            'cluster.name: acceptance-search\n'
            'node.name: acceptance-node\n'
            'node.processors: 2\n'
            'network.host: 127.0.0.1\n'
            f'http.port: {port}\n'
            'transport.port: 0\n'
            'discovery.type: single-node\n'
            'node.store.allow_mmap: false\n'
            'xpack.security.enabled: false\n'
            'xpack.ml.enabled: false\n'
            'ingest.geoip.downloader.enabled: false\n', encoding='utf-8')
        # The bundled OsProbe supports this hierarchy override. Container cgroup
        # mounts expose their root at /sys/fs/cgroup, while /proc/self/cgroup may
        # name an inaccessible ancestor in the host's hierarchy.
        environment = dict(
            os.environ,
            ES_JAVA_OPTS='-Xms128m -Xmx128m -Des.cgroups.hierarchy.override=/',
        )
        with (root / 'server.log').open('w+') as log:
            process = subprocess.Popen([str(home / 'bin' / 'elasticsearch')],
                                       cwd=home, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                expires = time.monotonic() + 180
                # Readiness is a service probe, never the test's search oracle.
                while True:
                    if process.poll() is not None or time.monotonic() >= expires:
                        log.flush()
                        log.seek(0)
                        raise AssertionError('Elasticsearch startup failed:\n' + log.read())
                    try:
                        with urllib.request.urlopen(
                            endpoint + '/_cluster/health?wait_for_status=yellow&timeout=1s',
                            timeout=2,
                        ) as response:
                            health = json.load(response)
                            if health['status'] in ('yellow', 'green') and not health['timed_out']:
                                break
                    except urllib.error.URLError:
                        time.sleep(0.2)
                client_environment = dict(os.environ)
                client_environment['PYTHONPATH'] = os.pathsep.join([
                    str(assets / 'F03_elasticsearch_client.whl'),
                    str(assets / 'F03_urllib3.whl'),
                    *([os.environ['PYTHONPATH']] if 'PYTHONPATH' in os.environ else []),
                ])
                try:
                    yield endpoint, client_environment
                except BaseException as error:
                    log.flush()
                    log.seek(0)
                    error.add_note('Elasticsearch server log:\n' + log.read())
                    raise
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
