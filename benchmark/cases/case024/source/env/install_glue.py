"""Install the locked AWS Glue Python interface and JVM runtime for local Spark."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import site
import subprocess
import tarfile
from urllib.parse import urlsplit

import pyspark

assets = Path('/env-assets')
lock = json.loads((assets / 'glue-runtime.lock.json').read_text())
root = Path('/opt/glue')
jars = root / 'jars'
jars.mkdir(parents=True, exist_ok=True)
jackson = root / 'jackson'
jackson.mkdir(parents=True, exist_ok=True)


def fetch(artifact, destination):
    target = destination / Path(urlsplit(artifact['url']).path).name
    subprocess.run([
        'curl', '--fail', '--location', '--silent', '--show-error',
        '--retry', '3', '--connect-timeout', '20',
        '--speed-limit', '1024', '--speed-time', '60',
        '--output', str(target), artifact['url'],
    ], check=True)
    with target.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != artifact['sha256']:
        raise ValueError(f'Checksum mismatch: {target.name}')
    print(f'Verified {target.name}', flush=True)
    return target


if pyspark.__version__ != lock['spark_version']:
    raise ValueError('Spark version does not match the locked Glue runtime')
spark_root = Path(pyspark.__file__).parent
hadoop_jars = list((spark_root / 'jars').glob('hadoop-client-api-*.jar'))
if [jar.name for jar in hadoop_jars] != [f"hadoop-client-api-{lock['hadoop_version']}.jar"]:
    raise ValueError('Bundled Hadoop version does not match the locked S3A connector')
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    list(executor.map(lambda artifact: fetch(artifact, jars), lock['jars']))
    list(executor.map(lambda artifact: fetch(artifact, jackson), lock['jackson_overrides']))
# These directories belong to this installer. Remove superseded artifacts on
# reinstall so the classpath has exactly the locked versions (including SDK v1).
for directory, artifacts in ((jars, lock['jars']), (jackson, lock['jackson_overrides'])):
    names = {Path(urlsplit(artifact['url']).path).name for artifact in artifacts}
    for installed in directory.glob('*.jar'):
        if installed.name not in names:
            installed.unlink()
archive = fetch(lock['python'], root)
with tarfile.open(archive) as source:
    source.extractall(root, filter='data')
python_root = root / lock['python']['root']
if not (python_root / 'awsglue/context.py').is_file():
    raise ValueError('AWS Glue Python archive is missing its context module')
(Path(site.getsitepackages()[0]) / 'aws-glue.pth').write_text(str(python_root) + '\n')

# PySpark selects its worker in the Python driver, before JVM configuration can
# influence it. Bind local workers to that interpreter, independent of PATH,
# while preserving an explicitly configured worker for external deployments.
(Path(site.getsitepackages()[0]) / 'pyspark-runtime.pth').write_text(
    "import os, sys; os.environ.setdefault('PYSPARK_PYTHON', sys.executable)\n"
)

# Glue's CSV parser requires Jackson 2.15. Use a consistent Jackson family
# before Spark's bundled Jackson; retain Spark-first order otherwise.
conf = spark_root / 'conf'
conf.mkdir(exist_ok=True)
classpath = f'{jackson}/*:{spark_root}/jars/*:{jars}/*'
(conf / 'spark-defaults.conf').write_text(
    f'spark.driver.extraClassPath {classpath}\n'
    f'spark.executor.extraClassPath {classpath}\n'
)
