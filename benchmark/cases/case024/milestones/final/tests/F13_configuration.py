# feature: F13
"""Remote executor configuration checks that require no running service.

The service-dependent remainder of F13.T04 is recorded in the ledger.
Configuration acceptance here does not claim that a remote task executed.
"""
from _helpers import capture_call, memory_scheduler
from F13_helpers import remote_failure


def test_f13_t04(tmp_path):
    def use_remote(settings):
        scheduler = memory_scheduler({"executors.remote": settings})
        return scheduler.run(remote_failure.options(executor="remote")("configuration"))

    configurations = [
        ({"type": "docker", "image": "velnora-worker:acceptance",
          "scratch": str(tmp_path / "scratch")}, ("image", "scratch")),
        ({"type": "aws_batch", "image": "velnora-worker:acceptance",
          "queue": "acceptance-queue", "s3_scratch": "s3://acceptance-work/scratch",
          "aws_region": "us-east-1"}, ("image", "queue", "s3_scratch")),
        ({"type": "aws_glue", "s3_scratch": "s3://acceptance-work/scratch",
          "aws_region": "us-east-1", "role": "acceptance-glue-role"},
         ("s3_scratch",)),
    ]
    for complete, required in configurations:
        # Complete construction is allowed; positive remote execution is covered
        # by the service tests. Refusal may occur on construction, load, or use.
        baseline = capture_call(
            memory_scheduler, ({"executors.remote": complete},))
        assert baseline.exception is None, baseline.exception
        for setting in required:
            incomplete = dict(complete)
            del incomplete[setting]
            rejected = capture_call(
                use_remote, (incomplete,))
            # Missing configuration has a public failure carrier, not silent success.
            # Do not pin the human-readable message or which key is named.
            assert isinstance(rejected.exception, KeyError), (
                complete["type"], setting, rejected.exception)
