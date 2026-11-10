# feature: F09
"""Real biological and time-series inputs and isolated source invocations."""
import functools
import os
import shutil
import subprocess
import sys
import tempfile
import hashlib
from pathlib import Path

from velnora import load_dataset
from _helpers import run_python


@functools.lru_cache(maxsize=1)
def time_series_dependencies():
    """Install the pinned real native dependency in a writable offline target."""
    asset = Path(__file__).parent / 'resources' / 'F09' / 'F09_tsfile.whl'
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == '7bab89d68915c12c09f25f4189136126d3430e55469e262beef93892ead2b05f'
    target = Path(tempfile.mkdtemp(prefix='F09-dependencies-'))
    wheel = target / 'tsfile-2.5.0-cp313-cp313-manylinux_2_28_x86_64.whl'
    shutil.copyfile(asset, wheel)
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                             '--target', str(target / 'site'), str(wheel)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return str(target / 'site')


def biological_source_test(function):
    @functools.wraps(function)
    def execute(tmp_path):
        source = '''
import sys
import os
import time
os.environ['TZ'] = 'UTC0'
time.tzset()
from pathlib import Path
source = Path('/app/src')
if not (source / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(source))
sys.path.insert(0, sys.argv[1])
from F09_biological_timeseries import FUNCTION
FUNCTION.__wrapped__(Path(sys.argv[2]))
'''.replace('FUNCTION', function.__name__)
        result = run_python(source, timeout=180,
                            args=(str(Path(__file__).parent), str(tmp_path)),
                            env=dict(os.environ, PYTHONPATH=time_series_dependencies() +
                                     os.pathsep + os.environ.get('PYTHONPATH', '')))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def sequence_sources(root):
    contents = {
        'fasta': b'>cedar first sample\nACGT\nTGCA\n>elm second sample\nTT\nGA\n',
        'fastq': b'@cedar first sample\nACGT\nTGCA\n+\n!"#$\n%&\'(\n@elm second sample\nTT\nGA\n+\nAB\nCD\n',
        'genbank': b'''LOCUS       CEDAR                      8 bp    DNA     linear   BCT 01-JAN-2024
DEFINITION  A small annotated sequence.
ACCESSION   CD0001
VERSION     CD0001.2
KEYWORDS    .
SOURCE      Bacillus subtilis
  ORGANISM  Bacillus subtilis
            Bacteria; Bacillota.
FEATURES             Location/Qualifiers
     source          1..8
                     /organism="Bacillus subtilis"
     gene            2..6
                     /gene="cedA"
ORIGIN
        1 acgttgca
//
LOCUS       ELMWOOD                    6 bp    DNA     linear   PLN 02-FEB-2024
DEFINITION  A second annotated sequence.
ACCESSION   EW0002
VERSION     EW0002.1
KEYWORDS    .
SOURCE      Ulmus americana
  ORGANISM  Ulmus americana
            Eukaryota; Viridiplantae.
FEATURES             Location/Qualifiers
     source          1..6
                     /organism="Ulmus americana"
     CDS             complement(2..5)
                     /gene="elmB"
ORIGIN
        1 ggatcc
//
''',
    }
    paths = {}
    for format, content in contents.items():
        path = root / ('records.' + format)
        path.write_bytes(content)
        paths[format] = path
    return paths


def structure_sources(root):
    pdb = root / 'geometry.pdb'
    pdb.write_text(
        'MODEL        1\n'
        'ATOM      1  N   GLY A   1       1.000   2.000   3.000  1.00 20.00           N\n'
        'ATOM      2  CA  GLY A   1       2.000   4.000   6.000  1.00 20.00           C\n'
        'TER\nENDMDL\nMODEL        2\n'
        'ATOM      1  N   ALA B   2       7.000   8.000   9.000  1.00 20.00           N\n'
        'TER\nENDMDL\nEND\n', encoding='ascii')
    cif = root / 'geometry.cif'
    cif.write_text('''data_geometry
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.auth_seq_id
_atom_site.auth_asym_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N . GLY A 1 1 ? 1.0 2.0 3.0 1.0 20.0 1 A 1
ATOM 2 C CA . GLY A 1 1 ? 2.0 4.0 6.0 1.0 20.0 1 A 1
ATOM 3 N N . ALA B 1 2 ? 7.0 8.0 9.0 1.0 20.0 2 B 2
#
''', encoding='ascii')
    return {'pdb': pdb, 'mmcif': cif}


def write_time_tables(path, tables):
    """Write native TsFiles, with table rows grouped into independent tablets."""
    from tsfile import ColumnCategory, ColumnSchema, TableSchema, Tablet, TsFileWriter
    from tsfile.constants import TSDataType
    with TsFileWriter(str(path)) as writer:
        for name, fields, groups in tables:
            columns = [('time', TSDataType.TIMESTAMP, ColumnCategory.TIME),
                       ('site', TSDataType.STRING, ColumnCategory.TAG),
                       ('device', TSDataType.STRING, ColumnCategory.TAG)]
            columns += [(field, TSDataType.DOUBLE, ColumnCategory.FIELD) for field in fields]
            writer.register_table(TableSchema(name, [ColumnSchema(*column) for column in columns]))
        for name, fields, groups in tables:
            names = ['site', 'device', *fields]
            types = [TSDataType.STRING, TSDataType.STRING] + [TSDataType.DOUBLE] * len(fields)
            for rows in groups:
                tablet = Tablet(names, types, len(rows))
                tablet.set_table_name(name)
                for i, row in enumerate(rows):
                    tablet.add_timestamp(i, row['time'])
                    for column in names:
                        tablet.add_value_by_name(column, i, row[column])
                writer.write_table(tablet)
    return path


def time_rows(paths, **kwargs):
    data = load_dataset('tsfile', data_files=[str(path) for path in paths], split='train', **kwargs)
    return list(data)
