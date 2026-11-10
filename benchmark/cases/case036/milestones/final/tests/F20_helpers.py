# feature: F20
"""Real suite sources and rendered suite-document observations."""
from _helpers import run_module, write_file
from F10_helpers import rendered_probe


def documentation_sources(directory):
    library = write_file(directory / 'Recorder.py', '''from pathlib import Path

def record_body(path, text):
    Path(path).write_text(text, encoding='utf-8')
''')
    root = directory / 'fleet'
    write_file(root / '__init__.velun', '''*** Settings ***
Name    Fleet
Documentation    Fleet overview.
Metadata    Owner    Marine team
Metadata    Region    Coast
''')
    markers = {}
    for filename, name, tag in [('alpha', 'Harbour Check', 'smoke'),
                                 ('beta', 'Ocean Check', 'slow'),
                                 ('extra', 'Island Check', 'smoke')]:
        marker = directory / (filename + '-body.txt')
        markers[name] = (marker, filename)
        path = directory / 'extra.velun' if filename == 'extra' else root / (filename + '.velun')
        write_file(path, f'''*** Settings ***
Name    {filename.title()}
Documentation    {filename} suite notes.
Metadata    Area    {filename}
Library    {library}
*** Test Cases ***
{name}
    [Documentation]    {filename} test notes.
    [Tags]    {tag}    voyage
    Record Body    {marker}    {filename}
    No Operation
''')
    return root, directory / 'extra.velun', markers


def generate_overview(sources, target, *options):
    process = run_module('velun.velunexplan', [*options, *map(str, sources), str(target)])
    assert process.returncode == 0, (process.stdout, process.stderr)
    assert target.is_file()
    return process


def overview_page(directory, target):
    return rendered_probe(directory, target, '''
const doc = frame.contentDocument;
const expand = doc.querySelector('.suite > .element-header a.expand');
if (!expand) throw Error('Missing suite expansion control');
expand.click();
await pause();
function direct(node, selector) {
    const result = node.querySelector(':scope > ' + selector);
    if (!result) throw Error('Missing document field: ' + selector);
    if (!result.getClientRects().length) throw Error('Document field is hidden: ' + selector);
    return result;
}
function entry(node) {
    const name = direct(node, '.element-header .name').textContent.trim();
    const fields = {};
    for (const row of direct(node, '.children > table.metadata').rows) {
        const label = row.querySelector('th').textContent.trim();
        if (Object.hasOwn(fields, label)) throw Error('Duplicate metadata label');
        fields[label] = row.querySelector('td').textContent.trim();
    }
    const children = direct(node, '.children');
    const calls = Array.from(children.querySelectorAll(':scope > .keyword')).map(kw => ({
        name: direct(kw, '.element-header .name').textContent.trim(),
        args: direct(kw, '.element-header .arg').textContent.trim()
    }));
    return {name, fields, calls,
        suites:Array.from(children.querySelectorAll(':scope > .suite')).map(entry),
        tests:Array.from(children.querySelectorAll(':scope > .test')).map(entry)};
}
return {title:doc.title, heading:doc.querySelector('#header h1').textContent,
        suite:entry(doc.querySelector('body > .suite'))};
''')
