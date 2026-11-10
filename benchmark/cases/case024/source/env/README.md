# Locked local runtime

`install.sh` installs the Python requirements and the real AWS Glue 5.0 Python
interface, Glue JVM libraries, and AWS SDK dependencies for local DynamicFrame
execution. Installation needs network access; execution uses installed files.
Downloads are verified against the SHA-256 hashes in `packages.json`,
`requirements.txt`, and `glue-runtime.lock.json`.

Spark 3.5.4 matches the upstream Glue 5.0 POM; Java 17 is retained. The Glue Python source is pinned
to an immutable commit of the upstream `glue-5.0` branch. The Glue JVM libraries
and SDK versions come from the published Glue Maven dependency graph.
The reader dependencies include Jackson CSV/Ion, Ion Java, BSON, and
MessagePack (including its core library), plus Grok's named-regexp library.
The NimbleParquet writer also requires Fastutil 6.5.12, as declared in its POM;
without it, reading works but saving fails with a missing IntIterator class.
Their versions follow the AWSGlueReaders and AWSGlueGrokFork POMs. Glue discovers all reader implementations together through Java
ServiceLoader when initializing a source, so a CSV source also needs the
classes referenced by the other registered readers.

Glue's CSV extension requires Jackson 2.15.2 APIs. The locked Jackson
core, annotations, databind, Scala module, Java time module, and YAML module
use 2.15.2 together, matching Spark 3.5.4, and load before Spark's bundled jars. Downgrading
CSV alone is incompatible with Glue's compiled parser constructor.

Spark supplies its engine and bundled dependencies. Hadoop S3A is installed as
`hadoop-aws` 3.3.4, matching Spark's bundled Hadoop client 3.3.4; the installer
rejects a different bundled client version. Its non-test dependencies are the
provided Hadoop libraries, the AWS SDK v1 bundle, and WildFly OpenSSL 1.0.7.Final.
The bundle uses 1.12.696 to retain the existing Glue SDK core version, rather
than Hadoop's older 1.12.262 default. It replaces the standalone SDK core jar,
providing one consistent SDK v1 implementation and shaded third-party libraries;
the separate SDK v2 libraries used by Glue are retained. All three added jars
are version-pinned and SHA-256 verified through the existing locked installer
and use the ordinary driver/executor classpaths. Reinstallation removes obsolete
jars from the installer's managed directories to prevent duplicate SDK versions.
No dependencies are downloaded at Spark startup.

Optional database connector dependencies remain outside this runtime.
The upstream Glue 5.0 POM targets Spark 3.5.4. Spark 3.4.3 cannot run
Glue's Parquet reader: it lacks the PartitionDirectory.apply overload taking
an InternalRow and a FileStatus array. Importing Glue, initializing a source,
and converting a DynamicFrame do not exercise that binary interface.
A separate offline probe also verifies real local CSV source initialization
through GlueContext.getSource; this initializes the registered reader set.

The pinned Jackson family precedes Spark's bundled jars on both driver and
executor classpaths; Spark's jars precede the remaining Glue dependencies,
following upstream `bin/glue-setup.sh` for that order. The configuration lives in
the installed PySpark distribution so ordinary SparkSession creation loads it
without a separate launcher.

An installed Python startup file sets `PYSPARK_PYTHON` to the driver's own
interpreter unless the caller explicitly configures a worker. PySpark 3.5.4
chooses workers from this environment variable in the Python driver; JVM Spark
configuration alone does not control this path. This keeps local workers on the
installed Python 3.12 runtime even when `python3` on the caller's `PATH` is a
different version, without changing the caller's `PATH`.

Upstream sources:

- https://github.com/awslabs/aws-glue-libs/tree/23918d0038663555dcfc696c44c0efbe497e0705
- https://aws-glue-etl-artifacts.s3.amazonaws.com/release/com/amazonaws/AWSGlueETL/5.0.0/AWSGlueETL-5.0.0.pom
- https://aws-glue-etl-artifacts.s3.amazonaws.com/release/com/amazonaws/AWSGlueReaders/5.0.0/AWSGlueReaders-5.0.0.pom
- https://aws-glue-etl-artifacts.s3.amazonaws.com/release/com/amazonaws/AWSGlueGrokFork/5.0.0/AWSGlueGrokFork-5.0.0.pom
- https://aws-glue-etl-artifacts.s3.amazonaws.com/release/com/amazonaws/NimbleParquet/5.0.0/NimbleParquet-5.0.0.pom
- https://repo.maven.apache.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.pom
- https://repo.maven.apache.org/maven2/org/apache/hadoop/hadoop-project/3.3.4/hadoop-project-3.3.4.pom
- https://repo.maven.apache.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.696/aws-java-sdk-bundle-1.12.696.pom

The local conversion probe requires neither AWS credentials nor an AWS service.
The S3A dependency addition was verified by replaying `install.sh` from the
locked base image, then running offline as a non-root user with read-only
product/tests. Ordinary Spark startup resolves and instantiates S3A with Hadoop
3.3.4; the existing Glue local CSV source initialization and DynamicFrame row
roundtrip checks also pass. Both classpaths are configured, but a separate
executor JVM was not exercised. An offline product probe now verifies real Glue
Parquet loading through Hadoop S3A against the tests' loopback S3 service,
collects the input rows, computes derived rows, saves new Parquet objects, and
reopens them through the product. The three existing Spark acceptance tests
also pass, including Python workers, SQL queries, and JSON dataset read/write.
These checks use a non-root user with read-only original product and tests.
Other dataset formats have not been verified by this repair.

The Maven Central artifacts use the Alibaba Cloud public repository, including
the SDK v1 bundle. The pinned versions and SHA-256 checksums are unchanged.
AWS Glue release artifacts and the pinned GitHub archive use their official
sources because these upstream distributions have no Alibaba Cloud source.

The default `python3` command is installed as a launcher for
`/opt/runtime/bin/python3` at the image's existing PATH entry. This persists
across shells and users, including the judge that starts `python3` directly.
The launcher executes the virtual environment by its own path so Python finds
its environment configuration and all locked dependencies. The underlying
Conda interpreter and Ubuntu system interpreter remain available by their
versioned paths. Build and test commands use this same default `python3`.
The installer checks its prefix and dependency imports before succeeding.

The offline build installs the judged product with `--prefix=/usr/local`.
Pip therefore generates its real console entry points in `/usr/local/bin`,
which is already on the image's PATH for the judge and inherited subprocesses.
Installation prepares a `.pth` file in the locked runtime pointing at the
system prefix's pure/extension package directories; isolated Python startup
also processes this file. No product package or command is supplied by the
source-free dependency installation. Product scripts and packages are created
from the current submitted tree by the supported offline build, before judging.
The build's local PATH setting is retained for the locked build backend's own
executable; product execution does not depend on that temporary setting.
