# feature: F18
"""Caller-supplied extensions driven through installed configuration and CLI."""
from pathlib import Path

from F01_helpers import install_bundle
from F02_helpers import recipe_file


def install_extensions(client, files):
    install_bundle(client, Path(client.cwd) / 'extensions-input', files)


def extension_failure(client, *args, identity=None, reason=None):
    from F01_helpers import cli_rejection
    result = cli_rejection(client, *args)
    diagnostic = result.text('stderr')
    if identity is not None:
        assert identity in diagnostic, result
    if reason is not None:
        assert reason in diagnostic, result
    return result


POLICY_PACKAGE = '''    settings = "build_type"
    description = "inspected material"
    def step(self, label):
        import os
        if os.environ.get("F18_STEPS"):
            with open(os.environ["F18_STEPS"], "a") as stream:
                stream.write(label + "\\n")
    def source(self):
        from velmora.tools.files import save
        self.step("source")
        save(self, "source.txt", self.description)
    def build(self):
        import os
        from velmora.tools.files import load, save
        self.step("build")
        save(self, "built.txt", load(self, os.path.join(self.source_folder, "source.txt")))
    def package(self):
        import os, json
        from velmora.tools.files import load, save
        self.step("package")
        save(self, os.path.join(self.package_folder, "payload.json"),
             json.dumps({"material": load(self, os.path.join(self.build_folder, "built.txt")),
                         "build_type": str(self.settings.build_type)}))
'''


PROFILE_POLICY = '''from velmora.errors import VelmoraException

def profile_plugin(profile):
    mode = profile.settings.get("build_type")
    if mode == "MinSizeRel":
        raise VelmoraException("profile-policy-denied-size")
    profile.settings["build_type"] = {"Release": "Debug", "Debug": "RelWithDebInfo"}[mode]
'''


COMMAND_EXTENSION = '''import json
from velmora.cli.command import velmora_command, velmora_subcommand
from velmora.api.output import cli_out_write

def emit(info):
    cli_out_write(json.dumps(info))

@velmora_command(formatters={"json": emit})
def render(velmora_api, parser, *args):
    """Transform caller text and write a requested file."""
    parser.add_argument("text")
    parser.add_argument("destination")
    parsed = parser.parse_args(*args)
    result = parsed.text.upper() + "\\n"
    with open(parsed.destination, "w") as stream:
        stream.write(result)
    return {"result": result}
'''

SUBCOMMAND_EXTENSION = '''import json
from velmora.cli.command import velmora_command, velmora_subcommand
from velmora.api.output import cli_out_write

def emit(info):
    cli_out_write(json.dumps(info))

@velmora_command()
def toolkit(velmora_api, parser, *args):
    """Caller text tools."""

@velmora_subcommand(formatters={"json": emit})
def toolkit_repeat(velmora_api, parser, subparser, *args):
    """Repeat caller text into a requested file."""
    subparser.add_argument("text")
    subparser.add_argument("count", type=int)
    subparser.add_argument("destination")
    parsed = parser.parse_args(*args)
    result = parsed.text * parsed.count
    with open(parsed.destination, "w") as stream:
        stream.write(result)
    return {"result": result}
'''


DEPENDENCY_GENERATOR = '''import json, os
from velmora.tools.files import save, load
class DependencyReceipt:
    def __init__(self, velmorafile):
        self.velmorafile = velmorafile
    def generate(self):
        entries = {}
        for dep in self.velmorafile.dependencies.direct_host.values():
            entries[dep.ref.name] = {"version": str(dep.ref.version),
                "content": load(self.velmorafile, os.path.join(dep.package_folder, "source.txt"))}
        save(self.velmorafile, os.path.join(self.velmorafile.generators_folder, "dependencies.json"),
             json.dumps(entries))
'''


SIGNING_KEY = b'acceptance-extension-integrity-key'
SIGNING_EXTENSION = '''import os, json, hmac, hashlib
from velmora.errors import VelmoraException
KEY = b"acceptance-extension-integrity-key"

def digest(path):
    with open(path, "rb") as stream:
        return hmac.new(KEY, stream.read(), hashlib.sha256).hexdigest()

def sign(ref, artifacts_folder, signature_folder, **kwargs):
    signatures = {name: digest(os.path.join(artifacts_folder, name))
                  for name in os.listdir(artifacts_folder)
                  if os.path.isfile(os.path.join(artifacts_folder, name))}
    with open(os.path.join(signature_folder, "digests.json"), "w") as stream:
        json.dump(signatures, stream)
    return [{"method": "caller-hmac-sha256", "provider": "acceptance",
             "sign_artifacts": {"signature": "digests.json"}}]

def verify(ref, artifacts_folder, signature_folder, files, **kwargs):
    if os.environ.get("F18_REJECT_VERIFY") == ("binary" if ":" in str(ref) else "recipe"):
        raise VelmoraException("verification-policy-denied " + str(ref))
    with open(os.path.join(signature_folder, "digests.json")) as stream:
        signatures = json.load(stream)
    checked = []
    for name in files:
        path = os.path.join(artifacts_folder, name)
        if os.path.isfile(path):
            if not hmac.compare_digest(signatures[name], digest(path)):
                raise VelmoraException("verification-integrity-failed " + str(ref))
            checked.append(name)
    with open(os.environ["F18_VERIFICATION_RECEIPT"], "a") as stream:
        stream.write(json.dumps({"ref": str(ref), "checked": checked}) + "\\n")
'''


def signing_consumer(client, root, reference):
    root = Path(root)
    output = root / 'received.txt'
    recipe_file(root, '''    requires = %r
    def generate(self):
        import os
        from velmora.tools.files import save, load
        dep = self.dependencies["freight"]
        save(self, %r, load(self, os.path.join(dep.package_folder, "source.txt")))
''' % (reference, str(output)))
    return root, output


def signing_receipts(path):
    import json
    return [json.loads(line) for line in Path(path).read_text().splitlines()]
