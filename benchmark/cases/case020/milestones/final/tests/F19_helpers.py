# feature: F19
"""Public recipe-driven SBOM and comparison observations."""
import contextlib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from _helpers import read_json, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_file


def sbom_consumer(root, declarations, variants, *, extra_info=None):
    """Generate each requested document on the same resolved install graph."""
    body = declarations + '''    def generate(self):
        import json, os
        from velmora.tools.sbom import cyclonedx_1_4, cyclonedx_1_6
        from velmora.tools.files import save
'''
    for filename, version, options in variants:
        body += ('        save(self, os.path.join(self.generators_folder, %r), '
                 'json.dumps(cyclonedx_%s(self, extra_info=%r, **%r)))\n'
                 % (filename, version.replace('.', '_'), extra_info, options))
    return recipe_file(root, body, name='bill', version='3.0').parent


def sbom_documents(client, root, variants):
    report = cli_success(client, 'install', root, '-nr', '--format=json').json('stdout')
    return report, {filename: read_json(Path(root) / filename)
                    for filename, _, _ in variants}


def sbom_components(document):
    """Read the standard component carrier, rejecting duplicate identities."""
    rows = document.get('components', [])
    result = {row['name']: row for row in rows}
    assert len(result) == len(rows), rows
    return result


def sbom_revision(component):
    """Read the revision qualifier from the component's published package URI."""
    return parse_qs(urlsplit(component['bom-ref']).query)['rrev'][0]


def sbom_edges(document):
    identities = {row['bom-ref']: row['name'] for row in document.get('components', [])}
    identities[document['metadata']['component']['bom-ref']] = '$root'
    result = {}
    for row in document['dependencies']:
        name = identities[row['ref']]
        assert name not in result, row
        result[name] = {identities[target] for target in row.get('dependsOn', [])}
    return result


def comparison_inputs(root, version, marker, *, removed=False):
    """Caller-owned exported files, patches and acquired sources."""
    declarations = '''    exports = "*.txt"
    exports_sources = "*.h", "patches/*"
    description = %r
    def source(self):
        from velmora.tools.files import save, patch
        save(self, "acquired.txt", %r)
        save(self, %r, %r)
        patch(self, patch_file="patches/change.patch")
''' % (marker, marker + ' source\n', 'retired.c' if removed else 'introduced.c',
       marker + ' unique source\n')
    recipe_file(root, declarations, name='compare', version=version)
    write_file(Path(root) / 'material.txt', marker + ' exported\n')
    write_file(Path(root) / ('retired.txt' if removed else 'introduced.txt'),
               marker + ' unique export\n')
    write_file(Path(root) / 'header.h', marker + ' header\n')
    write_file(Path(root) / ('retired.h' if removed else 'introduced.h'),
               marker + ' unique header\n')
    write_file(Path(root) / 'patches/change.patch',
               '--- /dev/null\n+++ patched.txt\n@@ -0,0 +1 @@\n+' + marker + ' patched\n')
    return Path(root)


def comparison_report(client, old, new, *, paths=None, rejected=False):
    from F01_helpers import cli_rejection
    args = ['report', 'diff', '--old-reference', old, '--new-reference', new, '--format=json']
    if paths is not None:
        args += ['--old-path', str(paths[0]), '--new-path', str(paths[1])]
    invoke = cli_rejection if rejected else cli_success
    result = invoke(client, *args)
    return result if rejected else result.json('stdout')


def difference_lines(report, relative_path):
    """The report maps absolute file paths to unified-diff line arrays."""
    matches = [lines for path, lines in report.items()
               if path.endswith('/' + relative_path)]
    assert len(matches) == 1, (relative_path, report)
    return matches[0]


@contextlib.contextmanager
def comparison_client(root):
    """Supply the comparison entry with a real, isolated available repository."""
    from F02_helpers import recipe_client
    from F03_helpers import recipe_repository, attach_repositories
    client = recipe_client(root)
    with recipe_repository(Path(root) / 'repository', client.env) as url:
        attach_repositories(client, [('provenance', url)])
        yield client
