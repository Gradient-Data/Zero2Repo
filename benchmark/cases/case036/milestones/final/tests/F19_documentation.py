# feature: F19
"""Acceptance coverage for public keyword documentation generation."""
from _helpers import (write_file, read_json, read_xml, call_public, run_module,
                      index_by_identity)
from F01_helpers import native_case
from F03_helpers import keyword_service
from F10_helpers import rendered_probe
from F19_helpers import (DYNAMIC_LIBRARY, RESOURCE, NATIVE_DOC,
                         doc_library, generate_doc, json_doc, doc_keywords,
                         check_paint, reader_snapshot, markup_tree, check_blocks, animated_document_probe)


def test_documented_sources_and_metadata(tmp_path):
    from velun.velunexdocs import velunexdocs
    library = doc_library(tmp_path)
    target = tmp_path / 'api.json'
    call_public(velunexdocs, str(library), str(target), specdocformat='RAW')
    data = read_json(target)
    check_paint(data)
    assert data['type'] == 'LIBRARY'
    init = data['inits'][0]
    assert init['doc'] == 'Select the documented region.'
    assert init['args'][0]['name'] == 'region'
    assert init['args'][0]['defaultValue'] == 'west'
    assert init['args'][0]['required'] is False
    module = write_file(tmp_path / 'Module.py', '"""Module introduction."""\nfrom velun.api.deco import keyword\n@keyword("Echo")\ndef echo(value):\n    """Return the supplied value."""\n    return value\n')
    module_data = json_doc(module, tmp_path / 'module.json')
    assert isinstance(module_data['name'], str)
    assert module_data['doc'] == 'Module introduction.'
    echo = doc_keywords(module_data)['Echo']
    assert echo['doc'] == 'Return the supplied value.'
    assert echo['args'][0]['name'] == 'value'
    dynamic = write_file(tmp_path / 'Dynamic.py', DYNAMIC_LIBRARY)
    for area in ('Coast', 'Forest'):
        configured = json_doc(str(dynamic) + '::' + area, tmp_path / (area + '.json'))
        keywords = doc_keywords(configured)
        assert set(keywords) == {'Visit ' + area}
        kw = keywords['Visit ' + area]
        assert kw['doc'] == 'Visit documentation for ' + area + '.'
        assert kw['tags'] == ['travel']
        assert [(a['name'], a['required'], a['defaultValue']) for a in kw['args']] == [('place', True, None), ('visits', False, '2')]
    with keyword_service() as (service, url):
        information = service.get_library_information
        service.get_library_information = lambda: {**information(), '__init__': {'doc': 'Connect to the local service.'}, '__intro__': {'doc': 'Local service introduction.'}}
        remote = json_doc('Remote::' + url, tmp_path / 'remote.json')
        # Remote discovery's __intro__ and __init__ entries carry the introduction
        # and initialization documentation.
        assert remote['doc'] == 'Local service introduction.'
        assert [init['doc'] for init in remote['inits']] == ['Connect to the local service.']
        assert set(doc_keywords(remote)) == {'Echo', 'Combine', 'Ordinary', 'Continuable', 'Fatal', 'Delay', 'Malformed', 'Binary', 'Mapping'}
        for kw in remote['keywords']:
            assert kw['doc'] == 'Local service operation.'
            assert [a['kind'] for a in kw['args']] == ['VAR_POSITIONAL', 'VAR_NAMED']
    for filename in ('Routes.resource', 'Routes.velun', '__init__.velun'):
        source_path = tmp_path / 'Compass' / filename if filename == '__init__.velun' else tmp_path / filename
        text = RESOURCE
        if filename != 'Routes.resource':
            text = text.replace('*** Settings ***', '*** Settings ***\nName    ' + ('Compass' if filename == '__init__.velun' else 'Routes'))
        source = write_file(source_path, text + (native_case() if filename == 'Routes.velun' else ''))
        data = json_doc(source, tmp_path / (filename + '.json'))
        if filename.endswith('.resource'):
            assert isinstance(data['name'], str)
        else:
            assert data['name'] == ('Compass' if filename == '__init__.velun' else 'Routes')
        assert data['type'] == ('RESOURCE' if filename.endswith('.resource') else 'SUITE')
        if filename.endswith('.resource'):
            assert data['doc'] == 'Resource introduction.'
        keywords = doc_keywords(data)
        assert set(keywords) == {'Public Route', 'Hidden Route'}
        assert keywords['Hidden Route']['private'] is True
        public = keywords['Public Route']
        assert public['doc'] == 'Route description.'
        assert public['tags'] == ['navigation']
        assert [(a['name'], a['required'], a['defaultValue']) for a in public['args']] == [('origin', True, None), ('target', False, 'harbour')]
        page = tmp_path / (filename + '.html')
        generate_doc(source, page)
        observed = rendered_probe(tmp_path, page, '''
return Array.from(frame.contentDocument.querySelectorAll('.keyword-container .kw-name')).map(e=>e.textContent.trim());''')
        assert observed == ['Public Route']


def test_output_forms_and_detached_spec_conversion(tmp_path):
    library = doc_library(tmp_path)
    specifications = []
    for extension in ('json', 'xml'):
        path = tmp_path / ('original.' + extension)
        generate_doc(library, path, '--specdocformat', 'RAW')
        specifications.append(path)
    library.unlink()
    for spec in specifications:
        for extension in ('json', 'xml', 'md', 'html'):
            target = tmp_path / (spec.suffix[1:] + '-converted.' + extension)
            options = ('--specdocformat', 'RAW') if extension in ('json', 'xml') else ()
            generate_doc(spec, target, *options)
            if extension == 'json':
                check_paint(read_json(target))
            elif extension == 'xml':
                root = read_xml(target).getroot()
                assert root.attrib['name'] == 'Atlas'
                assert root.findtext('version') == '3.7-doc'
                assert 'Atlas introduction' in root.findtext('doc')
                kw = index_by_identity(root.findall('./keywords/kw'), lambda e: e.attrib['name'])['Paint Item']
                assert kw.findtext('doc') == 'Apply pigment to the requested items.'
                assert {e.text for e in kw.findall('./tags/tag')} == {'palette', 'public'}
                args = kw.findall('./arguments/arg')
                assert [e.findtext('name') for e in args] == ['shade', 'count']
                assert [e.attrib['required'] for e in args] == ['true', 'false']
                assert args[0].find('type').attrib['name'] == 'Shade'
                assert args[1].find('type').attrib['name'] == 'int'
                assert args[1].findtext('default') == '4'
                assert kw.find('returntype').attrib['name'] == 'str'
            elif extension == 'md':
                text = target.read_text()
                assert '# Atlas\n' in text
                assert '### Paint Item\n' in text
                assert '#### Arguments\n' in text
                assert '`shade` (type: `Shade`)' in text
                assert '`count` (type: `int`, default: `4`)' in text
                assert 'Apply pigment to the requested items.' in text
                assert '`palette`' in text and '`public`' in text
                assert '#### Returns\n\n* `str`' in text
            else:
                observed = reader_snapshot(tmp_path, target)
                assert set(observed['names']) == {'Paint Item', 'Inspect Item', 'Repaint Items', 'Pin', 'Pan'}
                assert 'Atlas introduction' in observed['intro']
                assert 'Apply pigment to the requested items.' in observed['paint']
                assert 'palette' in observed['paint'] and 'public' in observed['paint']
                assert {'shade', 'count'} <= set(observed['args'])
                assert {'Shade', 'int', 'str'} <= set(observed['types'])
                assert '4' in observed['paint']


def test_source_formats_and_structured_rendering(tmp_path):
    documents = {
        'VELUN': '= Format heading =\n\nFirst paragraph.\n\nSecond paragraph.\n\n- list member\n\n[https://example.org/guide|format link]\n\n| code content',
        'MARKDOWN': '# Format heading\n\nFirst paragraph.\n\nSecond paragraph.\n\n- list member\n\n[format link](https://example.org/guide)\n\n```\ncode content\n```',
        'REST': 'Format heading\n==============\n\nFirst paragraph.\n\nSecond paragraph.\n\n- list member\n\n`format link <https://example.org/guide>`_\n\n::\n\n    code content',
        'HTML': '<h1>Format heading</h1><p>First paragraph.</p><p>Second paragraph.</p><ul><li>list member</li></ul><a href="https://example.org/guide">format link</a><pre>code content</pre>',
        'TEXT': '= Literal heading =\n\n*literal emphasis*\n<a>literal tag</a>',
    }
    for format_name, original in documents.items():
        source = write_file(tmp_path / (format_name + '.py'), '__doc__ = ' + repr(original) + '\ndef witness():\n    """Documented operation."""\n')
        raw = json_doc(source, tmp_path / (format_name + '-raw.json'), '--docformat', format_name)
        assert raw['doc'] == original
        assert raw['docFormat'] == format_name
        rendered_path = tmp_path / (format_name + '-rendered.json')
        generate_doc(source, rendered_path, '--docformat', format_name, '--specdocformat', 'HTML')
        rendered = read_json(rendered_path)
        assert rendered['docFormat'] == 'HTML'
        root = markup_tree(rendered['doc'])
        if format_name == 'TEXT':
            assert '*literal emphasis*' in root.text_content()
            assert '<a>literal tag</a>' in root.text_content()
            assert not root.xpath('.//h1|.//h2|.//b|.//strong|.//a')
        else:
            assert any('Format heading' == e.text_content().strip() for e in root.xpath('.//h1|.//h2|.//h3|.//h4'))
            assert any(e.text_content().strip() == 'First paragraph.' for e in root.xpath('.//p'))
            assert any(e.text_content().strip() == 'Second paragraph.' for e in root.xpath('.//p'))
            assert any(e.text_content().strip() == 'list member' for e in root.xpath('.//li'))
            assert any(e.text_content().strip() == "format link"
                       for e in root.xpath('.//a[@href="https://example.org/guide"]'))
            assert any('code content' in e.text_content() for e in root.xpath('.//pre'))


def test_console_query_matching_and_metadata(tmp_path):
    library = doc_library(tmp_path)
    all_names = {'Paint Item', 'Inspect Item', 'Repaint Items', 'Pin', 'Pan'}
    selections = [
        ((), all_names),
        (('ITEM',), {'Paint Item', 'Inspect Item', 'Repaint Items'}),
        (('p a i n t',), {'Paint Item', 'Repaint Items'}),
        (('p*item',), {'Paint Item', 'Inspect Item', 'Repaint Items'}),
        (('p?n',), {'Pin', 'Pan'}),
        (('p[ai]n',), {'Pin', 'Pan'}),
        (('inspect', 'p?n'), {'Inspect Item', 'Pin', 'Pan'}),
    ]
    for filters, expected in selections:
        result = run_module('velun.velunexdocs', [str(library), 'list', *filters])
        assert result.returncode == 0, result.stderr
        assert set(result.stdout.decode().splitlines()) == expected
    for filters, expected in [((), all_names), (('item',), set()), (('p a i n t i t e m',), {'Paint Item'}), (('*item*',), {'Paint Item', 'Inspect Item', 'Repaint Items'}), (('p[ai]n',), {'Pin', 'Pan'}), (('p?n', 'inspect*'), {'Pin', 'Pan', 'Inspect Item'})]:
        result = run_module('velun.velunexdocs', [str(library), 'show', *filters])
        assert result.returncode == 0, result.stderr
        text = result.stdout.decode()
        headings = {line[4:] for line in text.splitlines() if line.startswith('### ')}
        assert headings == expected
        if 'Paint Item' in expected:
            assert '#### Arguments\n' in text
            assert '`shade` (type: `Shade`)' in text
            assert '`count` (type: `int`, default: `4`)' in text
            assert 'Apply pigment to the requested items.' in text
    result = run_module('velun.velunexdocs', [str(library), 'version'])
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == ['3.7-doc']


def test_interactive_search_links_and_languages(tmp_path):
    library = doc_library(tmp_path)
    observations = []
    for language in ('en', 'fi'):
        target = tmp_path / (language + '.html')
        generate_doc(library, target, '--language', language)
        observed = animated_document_probe(tmp_path, target, '''
const doc=frame.contentDocument;
const names=()=>Array.from(doc.querySelectorAll('#keyword-shortcuts-container a.match')).map(e=>e.textContent.trim());
const all=names();
const headings=['Introduction','Keywords','Importing'].map(id=>doc.getElementById(id).textContent);
const argInfo=Array.from(doc.querySelectorAll('#keywords-container .arg-row')).map(e=>e.textContent.trim());
const typeInfo=Array.from(doc.querySelectorAll('#keywords-container .type')).map(e=>e.textContent.trim());
const reference=doc.querySelector('#introduction-container .doc a[href="#Paint%20Item"]');
reference.click(); await pause();
const keywordTarget=decodeURIComponent(frame.contentWindow.location.hash.slice(1));
const typeLink=doc.getElementById('Paint Item').querySelector('a.type[data-typedoc="Shade"]');
typeLink.click(); await pause();
const modal=doc.querySelector('#modal-content #type-modal-Shade');
const typeVisible=Number(frame.contentWindow.getComputedStyle(doc.getElementById('modal-background')).opacity)>0;
const members=Array.from(modal.querySelectorAll('.enum-member')).map(e=>e.textContent.trim());
const typeDescription=modal.querySelector('.dtdoc').textContent;
doc.querySelector('.modal-close-button').click();
frame.contentWindow.focus();
doc.querySelector('.search-input').focus();
const search=doc.querySelector('.search-input');
search.dispatchEvent(new frame.contentWindow.KeyboardEvent('keydown',{bubbles:true,key:'t'}));
search.value='inspect';
search.dispatchEvent(new frame.contentWindow.InputEvent('input',{bubbles:true,inputType:'insertText',data:'t'}));
search.dispatchEvent(new frame.contentWindow.KeyboardEvent('keyup',{bubbles:true,key:'t'}));
for(let attempts=0; attempts<40 && names().length===all.length; attempts++) await pause();
const filtered=names();
doc.querySelector('.clear-search').click(); await pause();
return {all,headings,argInfo,typeInfo,keywordTarget,typeVisible,members,typeDescription,filtered,restored:names()};
''')
        assert set(observed['all']) == {'Paint Item', 'Inspect Item', 'Repaint Items', 'Pin', 'Pan'}
        assert observed['filtered'] == ['Inspect Item']
        assert set(observed['restored']) == set(observed['all'])
        assert observed['keywordTarget'] == 'Paint Item'
        assert observed['typeVisible'] is True
        assert set(observed['members']) == {'AMBER', 'TEAL'}
        assert 'Available pigment choices.' in observed['typeDescription']
        assert observed['headings'] == (['Introduction', 'Keywords', 'Importing'] if language == 'en' else ['Johdanto', 'Avainsanat', 'Käyttöönotto'])
        observations.append(observed)
    assert sorted(observations[0]['argInfo']) == sorted(observations[1]['argInfo'])
    assert sorted(observations[0]['typeInfo']) == sorted(observations[1]['typeInfo'])


def test_documentation_input_errors(tmp_path):
    library = doc_library(tmp_path)
    check_paint(json_doc(library, tmp_path / 'valid.json'))
    broken_spec = write_file(tmp_path / 'broken.xml', '<keywordspec><kw>')
    scenarios = [
        (str(tmp_path / 'Unavailable.py'), ()),
        (str(tmp_path / 'Absent.resource'), ()),
        (str(library) + '::one::two', ()),
        (str(broken_spec), ()),
        (str(library), ('--format', 'UNSUPPORTED')),
    ]
    for number, (source, options) in enumerate(scenarios):
        result = run_module('velun.velunexdocs', [*options, source, str(tmp_path / ('bad-' + str(number) + '.json'))])
        assert result.returncode == 252, (result.stdout, result.stderr)
        assert result.stdout.strip(), (result.stdout, result.stderr)


def test_invalid_keywords_remain_identified(tmp_path):
    source = write_file(tmp_path / 'Mixed.resource', '''*** Keywords ***
Good Route
    [Documentation]    Complete valid route documentation.
    [Arguments]    ${start}    ${end}=home
    [Tags]    usable
    No Operation
Broken Route
    [Arguments]    invalidparameter
    No Operation
''')
    target = tmp_path / 'mixed.json'
    process = generate_doc(source, target, '--specdocformat', 'RAW')
    keywords = doc_keywords(read_json(target))
    assert set(keywords) == {'Good Route', 'Broken Route'}
    good = keywords['Good Route']
    assert good['doc'] == 'Complete valid route documentation.'
    assert good['tags'] == ['usable']
    assert [(a['name'], a['required'], a['defaultValue']) for a in good['args']] == [('start', True, None), ('end', False, 'home')]
    assert 'invalidparameter' in keywords['Broken Route']['doc']
    assert keywords['Broken Route']['source'] == str(source)
    assert keywords['Broken Route']['lineno'] == 7
    error = process.stderr.decode()
    assert '[ ERROR ]' in error
    assert str(source) in error
    assert 'Broken Route' in error
    assert 'line 8:' in error


def test_native_formatting_in_documentation_and_reports(tmp_path):
    source = write_file(tmp_path / 'Native.py', '__doc__ = ' + repr(NATIVE_DOC) + '\nfrom velun.api.deco import keyword\n@keyword("Paint Item")\ndef paint_item():\n    """Paint a surface."""\n')
    target = tmp_path / 'native.html'
    generate_doc(source, target)
    fragment = rendered_probe(tmp_path, target, '''
const doc=frame.contentDocument;
const intro=doc.querySelector('#introduction-container .doc');
const link=intro.querySelector('a[href="#Paint%20Item"]');
link.click(); await pause();
return {markup:intro.innerHTML,target:decodeURIComponent(frame.contentWindow.location.hash.slice(1)),name:doc.getElementById('Paint Item').querySelector('.kw-name').textContent.trim()};''')
    check_blocks(markup_tree(fragment['markup']))
    assert fragment['target'] == fragment['name'] == 'Paint Item'
    documentation = '\n'.join('...    ' + line if line else '...    ${EMPTY}' for line in NATIVE_DOC.splitlines())
    suite = write_file(tmp_path / 'Formatted.velun', '*** Settings ***\nDocumentation\n' + documentation + '\n' + native_case())
    process = run_module('velun', ['--outputdir', str(tmp_path), str(suite)])
    assert process.returncode == 0, (process.stdout, process.stderr)
    markup = rendered_probe(tmp_path, tmp_path / 'report.html', '''
const row=Array.from(frame.contentDocument.querySelectorAll('tr')).find(e=>e.querySelector('th')?.textContent==='Documentation:');
return row.querySelector('td.doc').innerHTML;''')
    check_blocks(markup_tree(markup))
