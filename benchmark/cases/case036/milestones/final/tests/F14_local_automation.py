# feature: F14
"""Local automation observed through Velun keywords and the real operating system."""
from concurrent.futures import ThreadPoolExecutor
import os

from _helpers import temporary_workspace, write_file, require_python
from F14_helpers import os_run


def test_file_content_encodings_binary_append_and_line_search():
    require_python((3, 13))
    with temporary_workspace() as d:
        write_file(d / 'input', chr(10).join(['préface ab7 end','AB8','ab9 middle','other','xxab1yy','']))
        write_file(d / 'latin', b'caf\xe9')
        write_file(d / 'raw', bytes([0, 255, 13, 10, 65]))
        os_run(d, r'''Working
    ${v}=    Get File    @ROOT@/input
    Check    ${v}    chr(10).join(['préface ab7 end','AB8','ab9 middle','other','xxab1yy',''])
    ${v}=    Grep File    @ROOT@/input    ab?
    Check    ${v}    chr(10).join(['préface ab7 end','ab9 middle','xxab1yy'])
    ${v}=    Grep File    @ROOT@/input    ab[79]    regexp=True
    Check    ${v}    chr(10).join(['préface ab7 end','ab9 middle'])
    ${v}=    Grep File    @ROOT@/input    ^ab[0-9]    regexp=True
    Check    ${v}    'ab9 middle'
    ${v}=    Grep File    @ROOT@/input    9*e
    Check    ${v}    'ab9 middle'
    ${v}=    Grep File    @ROOT@/input    absent
    Check    ${v}    ''
    ${v}=    Get File    @ROOT@/latin    encoding=latin-1
    Check    ${v}    'café'
    ${v}=    Get Binary File    @ROOT@/raw
    Check    ${v}    bytes([0,255,13,10,65])
    Create File    @ROOT@/written    naïve
    Append To File    @ROOT@/written    café
    ${v}=    Disk Bytes    @ROOT@/written
    Check    ${v}    'naïvecafé'.encode('utf-8')
    Create File    @ROOT@/selected    café    encoding=latin-1
    Append To File    @ROOT@/selected    été    encoding=latin-1
    ${v}=    Disk Bytes    @ROOT@/selected
    Check    ${v}    bytes([99,97,102,233,233,116,233])
    ${data}=    Evaluate    bytes([0,255,13,10,65])
    Create Binary File    @ROOT@/binary    ${data}
    ${v}=    Disk Bytes    @ROOT@/binary
    Check    ${v}    bytes([0,255,13,10,65])
''')


def test_create_copy_move_remove_and_empty_real_trees():
    with temporary_workspace() as d:
        os_run(d, r'''Working
    Create Directory    @ROOT@/tree/branch
    Create Directory    @ROOT@/tree/branch
    Create File    @ROOT@/tree/branch/leaf    old
    Create File    @ROOT@/tree/branch/leaf    replacement
    ${v}=    Disk Bytes    @ROOT@/tree/branch/leaf
    Check    ${v}    b'replacement'
    Create File    @ROOT@/new/parents/file    payload
    Copy File    @ROOT@/new/parents/file    @ROOT@/tree/branch/leaf
    ${v}=    Disk Bytes    @ROOT@/tree/branch/leaf
    Check    ${v}    b'payload'
    ${v}=    Disk Bytes    @ROOT@/new/parents/file
    Check    ${v}    b'payload'
    Move File    @ROOT@/new/parents/file    @ROOT@/moved
    ${v}=    Disk Exists    @ROOT@/new/parents/file
    Check    ${v}    False
    ${v}=    Disk Bytes    @ROOT@/moved
    Check    ${v}    b'payload'
    Copy Directory    @ROOT@/tree    @ROOT@/copy
    ${v}=    Disk Tree    @ROOT@/copy
    Check    ${v}    {'branch':None,'branch/leaf':b'payload'}
    Move Directory    @ROOT@/copy    @ROOT@/relocated
    ${v}=    Disk Exists    @ROOT@/copy
    Check    ${v}    False
    ${v}=    Disk Tree    @ROOT@/relocated
    Check    ${v}    {'branch':None,'branch/leaf':b'payload'}
Refuse Nonempty
    Remove Directory    @ROOT@/tree
Cleanup
    ${v}=    Disk Tree    @ROOT@/tree
    Check    ${v}    {'branch':None,'branch/leaf':b'payload'}
    Empty Directory    @ROOT@/tree
    ${v}=    Disk Tree    @ROOT@/tree
    Check    ${v}    {}
    ${v}=    Disk Exists    @ROOT@/tree
    Check    ${v}    True
    Remove Directory    @ROOT@/relocated    recursive=True
    ${v}=    Disk Exists    @ROOT@/relocated
    Check    ${v}    False
    Remove Directory    @ROOT@/absent
    Create Directory    @ROOT@/hollow
    Remove Directory    @ROOT@/hollow
    ${v}=    Disk Exists    @ROOT@/hollow
    Check    ${v}    False
    Remove File    @ROOT@/moved
    Remove File    @ROOT@/moved
    ${v}=    Disk Exists    @ROOT@/moved
    Check    ${v}    False
''', failures=('Refuse Nonempty',))


def test_path_assertions_listings_counts_and_filters():
    with temporary_workspace() as d:
        write_file(d / 'entries/z.txt', 'z')
        write_file(d / 'entries/a.txt', '')
        write_file(d / 'entries/m.bin', 'm')
        (d / 'entries/b-dir').mkdir()
        (d / 'entries/y-dir').mkdir()
        cases = r'''Working
    Should Exist    @ROOT@/entries/*
    File Should Exist    @ROOT@/entries/*.txt
    Directory Should Exist    @ROOT@/entries/*-dir
    Should Not Exist    @ROOT@/entries/missing*
    File Should Not Exist    @ROOT@/entries/*-dir
    Directory Should Not Exist    @ROOT@/entries/*.txt
    File Should Be Empty    @ROOT@/entries/a.txt
    File Should Not Be Empty    @ROOT@/entries/z.txt
    Directory Should Be Empty    @ROOT@/entries/b-dir
    Directory Should Not Be Empty    @ROOT@/entries
'''
        for keyword, expected, filtered in (
            ('List Directory', "['a.txt','b-dir','m.bin','y-dir','z.txt']", "['a.txt','z.txt']"),
            ('List Files In Directory', "['a.txt','m.bin','z.txt']", "['a.txt','z.txt']"),
            ('List Directories In Directory', "['b-dir','y-dir']", '[]')):
            cases += f'    ${{v}}=    {keyword}    @ROOT@/entries\n    Check    ${{v}}    {expected}\n'
            cases += f'    ${{v}}=    {keyword}    @ROOT@/entries    *.txt\n    Check    ${{v}}    {filtered}\n'
            full = repr([str(d / 'entries' / p) for p in eval(expected)])
            cases += f'    ${{v}}=    {keyword}    @ROOT@/entries    absolute=True\n    Check    ${{v}}    {full}\n'
        for keyword, count, filtered in (('Items', 5, 2), ('Files', 3, 2), ('Directories', 2, 0)):
            cases += f'    ${{v}}=    Count {keyword} In Directory    @ROOT@/entries\n    Check    ${{v}}    {count}\n'
            cases += f'    ${{v}}=    Count {keyword} In Directory    @ROOT@/entries    *.txt\n    Check    ${{v}}    {filtered}\n'
        rejected = {
            'Missing': 'Should Exist    @ROOT@/entries/missing*',
            'Unexpected': 'Should Not Exist    @ROOT@/entries/*.txt',
            'Unexpected File': 'File Should Not Exist    @ROOT@/entries/*.txt',
            'Unexpected Directory': 'Directory Should Not Exist    @ROOT@/entries/*-dir',
            'Wrong File Kind': 'File Should Exist    @ROOT@/entries/b-dir',
            'Wrong Directory Kind': 'Directory Should Exist    @ROOT@/entries/a.txt',
            'Nonempty File': 'File Should Be Empty    @ROOT@/entries/z.txt',
            'Empty File': 'File Should Not Be Empty    @ROOT@/entries/a.txt',
            'Nonempty Directory': 'Directory Should Be Empty    @ROOT@/entries',
            'Empty Directory': 'Directory Should Not Be Empty    @ROOT@/entries/b-dir'}
        cases += ''.join(f'{name}\n    {statement}\n' for name, statement in rejected.items())
        os_run(d, cases, failures=tuple(rejected))


def test_explicit_waits_observe_external_events_and_expiration():
    with temporary_workspace() as d:
        write_file(d / 'remove', 'existing')
        write_file(d / 'stays', 'existing')
        os_run(d, r'''Working
    ${event}=    Begin Event    @ROOT@/created    create    0.6
    Wait Until Created    @ROOT@/created    5 seconds
    Event Completed    ${event}    @ROOT@/created    create
    ${event}=    Begin Event    @ROOT@/remove    remove    0.6
    Wait Until Removed    @ROOT@/remove    5 seconds
    Event Completed    ${event}    @ROOT@/remove    remove
    Wait Until Created    @ROOT@/created    0.2 seconds
    Wait Until Removed    @ROOT@/missing    0.2 seconds
Create Expires
    ${start}=    Clock Now
    Set Suite Variable    ${start}
    Wait Until Created    @ROOT@/never    0.4 seconds
Check Create Expiration
    Elapsed At Least    ${start}    0.4
    Elapsed At Most    ${start}    5
Remove Expires
    ${start}=    Clock Now
    Set Suite Variable    ${start}
    Wait Until Removed    @ROOT@/stays    0.4 seconds
Check Remove Expiration
    Elapsed At Least    ${start}    0.4
    Elapsed At Most    ${start}    5
''', failures=('Create Expires', 'Remove Expires'))


def test_paths_sizes_modification_time_and_touch():
    with temporary_workspace() as d:
        write_file(d / 'file.tar.gz', b'\x00\xc3\xa9abc')
        os.utime(d / 'file.tar.gz', (946684800, 946684800))
        os_run(d, r'''Working
    ${v}=    Join Path    @ROOT@    missing    child
    Check    ${v}    '@ROOT@/missing/child'
    ${v}=    Join Paths    @ROOT@    one    two
    Check    ${v}    ['@ROOT@/one','@ROOT@/two']
    ${v}=    Normalize Path    @ROOT@//missing/./branch/../leaf
    Check    ${v}    '@ROOT@/missing/leaf'
    ${v}=    Normalize Path    ~/never-created/../leaf
    ${home}=    Evaluate    os.path.expanduser('~')    modules=os
    ${expected}=    Evaluate    $home + '/leaf'
    Should Be Equal    ${v}    ${expected}
    ${v}=    Split Path    @ROOT@/file.tar.gz
    Check    ${v}    ('@ROOT@','file.tar.gz')
    ${v}=    Split Extension    @ROOT@/file.tar.gz
    Check    ${v}    ('@ROOT@/file.tar','gz')
    ${v}=    Get File Size    @ROOT@/file.tar.gz
    Check    ${v}    6
    ${v}=    Get Modified Time    @ROOT@/file.tar.gz    epoch
    Check    ${v}    946684800
    Set Modified Time    @ROOT@/file.tar.gz    1262304000
    Mtime Is    @ROOT@/file.tar.gz    1262304000
    ${v}=    Get Modified Time    @ROOT@/file.tar.gz    epoch
    Check    ${v}    1262304000
    ${before}=    Begin Touch
    Touch    @ROOT@/file.tar.gz
    Touched Since    @ROOT@/file.tar.gz    ${before}
    ${v}=    Disk Bytes    @ROOT@/file.tar.gz
    Check    ${v}    bytes([0,195,169,97,98,99])
    ${before}=    Begin Touch
    Touch    @ROOT@/new-touch
    Touched Since    @ROOT@/new-touch    ${before}
    ${v}=    Disk Bytes    @ROOT@/new-touch
    Check    ${v}    b''
Missing Size
    Get File Size    @ROOT@/absent
Directory Size
    Get File Size    @ROOT@
Missing Time
    Get Modified Time    @ROOT@/absent
Missing Set
    Set Modified Time    @ROOT@/absent    1262304000
Bad Touch
    Touch    @ROOT@/absent-parent/leaf
''', failures=('Missing Size', 'Directory Size', 'Missing Time', 'Missing Set', 'Bad Touch'))


def test_environment_changes_reads_assertions_and_children():
    with temporary_workspace() as d:
        os_run(d, r'''Working
    Remove Environment Variable    F14_AUTOMATION_ENTRY    f14_automation_entry
    Environment Variable Should Not Be Set    F14_AUTOMATION_ENTRY
    ${v}=    Get Environment Variable    F14_AUTOMATION_ENTRY    replacement
    Check    ${v}    'replacement'
    Set Environment Variable    F14_AUTOMATION_ENTRY    first
    Set Environment Variable    f14_automation_entry    lower
    Environment Variable Should Be Set    F14_AUTOMATION_ENTRY
    ${v}=    Get Environment Variable    f14_automation_entry
    Check    ${v}    'lower'
    ${v}=    Get Environment Variables
    ${selected}=    Evaluate    $v['F14_AUTOMATION_ENTRY']
    Check    ${selected}    'first'
    Append To Environment Variable    F14_AUTOMATION_ENTRY    second    third
    ${v}=    Get Environment Variable    F14_AUTOMATION_ENTRY
    Check    ${v}    'first:second:third'
    ${v}=    Child Environment    F14_AUTOMATION_ENTRY
    Check    ${v}    'first:second:third'
    Append To Environment Variable    F14_AUTOMATION_ENTRY    last    separator=|
    ${v}=    Get Environment Variable    F14_AUTOMATION_ENTRY
    Check    ${v}    'first:second:third|last'
    Remove Environment Variable    F14_AUTOMATION_ENTRY
    Append To Environment Variable    F14_AUTOMATION_ENTRY    fresh    next    separator=;
    ${v}=    Get Environment Variable    F14_AUTOMATION_ENTRY
    Check    ${v}    'fresh;next'
    Remove Environment Variable    F14_AUTOMATION_ENTRY
    Remove Environment Variable    F14_AUTOMATION_ENTRY
    Environment Variable Should Not Be Set    F14_AUTOMATION_ENTRY
    ${v}=    Child Environment    F14_AUTOMATION_ENTRY
    Check    ${v}    None
    ${v}=    Get Environment Variable    f14_automation_entry
    Check    ${v}    'lower'
Missing Lookup
    Get Environment Variable    F14_AUTOMATION_ENTRY
Missing Assertion
    Environment Variable Should Be Set    F14_AUTOMATION_ENTRY
Present Assertion
    Environment Variable Should Not Be Set    f14_automation_entry
''', failures=('Missing Lookup', 'Missing Assertion', 'Present Assertion'))


def test_wildcards_multiple_files_and_directory_copy_boundaries():
    with temporary_workspace() as d:
        write_file(d / 'not-directory', b'occupied')
        write_file(d / 'source/a.txt', b'alpha')
        write_file(d / 'source/b.txt', b'beta')
        write_file(d / 'source/keep.bin', b'keep')
        write_file(d / 'source/nested/leaf', b'leaf')
        os_run(d, r'''Working
    Create Directory    @ROOT@/destination
    Copy File    @ROOT@/source/a.txt    @ROOT@/destination
    ${v}=    Disk Bytes    @ROOT@/destination/a.txt
    Check    ${v}    b'alpha'
    Copy Files    @ROOT@/source/*.txt    @ROOT@/destination
    ${v}=    Disk Tree    @ROOT@/destination
    Check    ${v}    {'a.txt':b'alpha','b.txt':b'beta'}
    Create Directory    @ROOT@/moved
    Move Files    @ROOT@/destination/a.txt    @ROOT@/destination/b.txt    @ROOT@/moved
    ${v}=    Disk Tree    @ROOT@/destination
    Check    ${v}    {}
    ${v}=    Disk Tree    @ROOT@/moved
    Check    ${v}    {'a.txt':b'alpha','b.txt':b'beta'}
    Move File    @ROOT@/moved/a.txt    @ROOT@/destination
    ${v}=    Disk Bytes    @ROOT@/destination/a.txt
    Check    ${v}    b'alpha'
    ${v}=    Disk Exists    @ROOT@/moved/a.txt
    Check    ${v}    False
    Copy Directory    @ROOT@/source    @ROOT@/destination
    ${v}=    Disk Tree    @ROOT@/destination/source
    Check    ${v}    {'a.txt':b'alpha','b.txt':b'beta','keep.bin':b'keep','nested':None,'nested/leaf':b'leaf'}
    Remove Files    @ROOT@/source/*.txt
    ${v}=    Disk Tree    @ROOT@/source
    Check    ${v}    {'keep.bin':b'keep','nested':None,'nested/leaf':b'leaf'}
Copy Needs Directory
    Copy Files    @ROOT@/destination/source/a.txt    @ROOT@/destination/source/b.txt    @ROOT@/not-directory
Move Needs Directory
    Move Files    @ROOT@/destination/source/a.txt    @ROOT@/destination/source/b.txt    @ROOT@/not-directory
Existing Subtree
    Copy Directory    @ROOT@/source    @ROOT@/destination
''', failures=('Copy Needs Directory', 'Move Needs Directory', 'Existing Subtree'))


def test_file_errors_real_permissions_missing_and_invalid_encoding():
    assert os.geteuid() != 0, 'Permission observations require the judge non-root user.'
    with temporary_workspace() as d:
        write_file(d / 'valid', 'visible')
        write_file(d / 'invalid', b'\xff\xfe')
        denied = write_file(d / 'denied', 'private')
        locked = d / 'locked'
        locked.mkdir()
        denied.chmod(0)
        locked.chmod(0o500)
        try:
            os_run(d, r'''Working
    ${v}=    Get File    @ROOT@/valid
    Check    ${v}    'visible'
    Create File    @ROOT@/valid    updated
    ${v}=    Disk Bytes    @ROOT@/valid
    Check    ${v}    b'updated'
Missing Read
    Get File    @ROOT@/missing
Strict Decode
    Get File    @ROOT@/invalid
Unknown Encoding
    Get File    @ROOT@/valid    encoding=not-a-real-codec
Denied Read
    Get File    @ROOT@/denied
Denied Write
    Create File    @ROOT@/locked/new    forbidden
''', failures=('Missing Read', 'Strict Decode', 'Unknown Encoding', 'Denied Read', 'Denied Write'))
        finally:
            denied.chmod(0o600)
            locked.chmod(0o700)


def test_default_and_unlimited_waits_use_real_elapsed_time():
    # Independent subprocesses keep the real one-minute observations concurrent.
    def observe(action, timeout):
        with temporary_workspace() as d:
            if action == 'remove':
                write_file(d / 'target', 'existing')
            keyword = 'Created' if action == 'create' else 'Removed'
            if timeout == 'default':
                cases = f'''Expires
    ${{start}}=    Clock Now
    Set Suite Variable    ${{start}}
    Wait Until {keyword}    @ROOT@/target
Check Expiration
    Elapsed At Least    ${{start}}    60
    Elapsed At Most    ${{start}}    75
'''
                root = os_run(d, cases, failures=('Expires',))
            else:
                cases = f'''Working
    ${{event}}=    Begin Event    @ROOT@/target    {action}    62
    Wait Until {keyword}    @ROOT@/target    {timeout}
    Event Completed    ${{event}}    @ROOT@/target    {action}
    ${{v}}=    Disk Exists    @ROOT@/target
    Check    ${{v}}    {action == 'create'}
'''
                root = os_run(d, cases)
            return {t.attrib['name']: t.find('status').attrib['status'] for t in root.findall('.//test')}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(observe, action, timeout)
                   for action in ('create', 'remove')
                   for timeout in ('default', '${None}', '-1 second')]
        outcomes = [future.result(timeout=115) for future in futures]
    expected = {'Expires': 'FAIL', 'Check Expiration': 'PASS'}
    assert outcomes == [expected if timeout == 'default' else {'Working': 'PASS'}
                        for action in ('create', 'remove')
                        for timeout in ('default', '${None}', '-1 second')]
