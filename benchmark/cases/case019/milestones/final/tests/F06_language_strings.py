# feature: F06
"""Acceptance checks for document localization and reusable caller text."""

from _helpers import call_public, observe_pdf
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F06_helpers import render_language_book


# Frozen supplied translations from the public language resources documented
# by doc/api/language.rst, with definitions in the original repository at
# src/talvo/language/{en,fr,it,nl,de,pl,cs,es,hu}.py.
# These are independent expectations, never queried from the running product.
# Labels are text results; typography, capitalization and pagination are not fixed.
TRANSLATIONS = {
    'en': ('Chapter', 'Warning', 'Note'),
    'fr': ('Chapitre', 'Avertissement', 'Note'),
    'it': ('Capitolo', 'Avvertimento', 'Nota'),
    'nl': ('Hoofdstuk', 'Waarschuwing', 'Noot'),
    'de': ('Kapitel', 'Warnung', 'Notiz'),
    'pl': ('Rozdział', 'Ostrzeżenie', 'Notatka'),
    'cs': ('Kapitola', 'Varování', 'Poznámka'),
    'es': ('Capítulo', 'Precaución', 'Nota'),
    'hu': ('Fejezet', 'Figyelmeztetés', 'Megjegyzés'),
}


def test_document_languages_and_default_english(tmp_path):
    observer = pdf_observer_environment(tmp_path / 'observer')
    # The finite language enumeration is covered inside one planned test.
    for code in (None, *TRANSLATIONS):
        destination = tmp_path / ('language-' + str(code))
        result = call_public(render_language_book, destination, code)
        assert result.exception is None, result.traceback
        assert result.value is True, (result.stdout, result.stderr)
        text = pdf_plain_text(observe_pdf(destination.with_suffix('.pdf'),
                                          env=observer)).casefold()
        chapter, warning, note = TRANSLATIONS['en' if code is None else code]
        # Observe automatic labels on their real section/admonition paths,
        # rather than inserting language fields manually into paragraphs.
        assert chapter.casefold() in text.split(), (code, text)
        assert 'orchard survey' in text, (code, text)
        assert warning.casefold() + ' advice for warning' in text, (code, text)
        assert note.casefold() + ' advice for note' in text, (code, text)
        assert 'bodystart' in text and 'bodyend' in text, (code, text)


def test_standard_overrides_and_custom_text_in_body_and_footer(tmp_path):
    observer = pdf_observer_environment(tmp_path / 'observer')
    scenarios = [
        ('fr', ('Division', 'Watchfulness'),
         (('motto', 'Cedar and river'), ('signoff', 'A quiet horizon'))),
        ('nl', ('Volume', 'Take heed'),
         (('motto', 'Amber over water'), ('signoff', 'Return at sunrise'))),
    ]
    for code, (chapter, warning), custom in scenarios:
        destination = tmp_path / ('replacements-' + code)
        result = call_public(render_language_book, destination, code,
                             (('chapter', chapter), ('warning', warning)), custom)
        assert result.exception is None, result.traceback
        assert result.value is True, (result.stdout, result.stderr)
        text = pdf_plain_text(observe_pdf(destination.with_suffix('.pdf'),
                                          env=observer))
        folded = text.casefold()
        assert chapter.casefold() in folded.split(), text
        assert warning.casefold() + ' advice for warning' in folded, text
        # Replacing selected strings must leave other selected-language labels live.
        assert TRANSLATIONS[code][2].casefold() + ' advice for note' in folded, text
        for _, value in custom:
            assert 'FirstUse ' + value + ' EndFirst' in text, text
            assert 'SecondUse ' + value + ' EndSecond' in text, text
        assert ('FooterStart ' + ' / '.join(value for _, value in custom)
                + ' / FooterEnd') in text, text


MORE_TRANSLATIONS = {'en': {'attention': 'Attention!', 'caution': 'Caution!', 'danger': '!DANGER!', 'error': 'Error', 'hint': 'Hint', 'important': 'Important', 'tip': 'Tip', 'seealso': 'See also'}, 'fr': {'attention': 'Attention !', 'caution': 'Prudence !', 'danger': '! DANGER !', 'error': 'Erreur', 'hint': 'Conseil', 'important': 'Important', 'tip': 'Astuce', 'seealso': 'Voir aussi'}, 'it': {'attention': 'Attenzione!', 'caution': 'Prudenza!', 'danger': '!PERICOLO!', 'error': 'Errore', 'hint': 'Consiglio', 'important': 'Importante', 'tip': 'Suggerimento', 'seealso': 'Vedi anche'}, 'nl': {'attention': 'Opgelet!', 'caution': 'Pas op!', 'danger': '!GEVAAR!', 'error': 'Fout', 'hint': 'Hint', 'important': 'Belangrijk', 'tip': 'Tip', 'seealso': 'Zie ook'}, 'de': {'attention': 'Aufgepasst!', 'caution': 'Vorsicht!', 'danger': '!GEFAHR!', 'error': 'Fehler', 'hint': 'Hinweis', 'important': 'Wichtig', 'tip': 'Tipp', 'seealso': 'Siehe auch'}, 'pl': {'attention': 'Uwaga!', 'caution': 'Ostrożnie!', 'danger': '!NIEBEZPIECZEŃSTWO!', 'error': 'Błąd', 'hint': 'Wskazówka', 'important': 'Ważne', 'tip': 'Porada', 'seealso': 'Zobacz również'}, 'cs': {'attention': 'Opatrnost!', 'caution': 'Pozornost!', 'danger': '!NEBEZPEČÍ!', 'error': 'Chyba', 'hint': 'Poznámka', 'important': 'Důležité', 'tip': 'Tip', 'seealso': 'Viz také'}, 'es': {'attention': '¡Atención!', 'caution': '¡Cuidado!', 'danger': '¡PELIGRO!', 'error': 'Error', 'hint': 'Pista', 'important': 'Importante', 'tip': 'Consejo', 'seealso': 'Véase también'}, 'hu': {'attention': 'Figyelem!', 'caution': 'Vigyázat!!', 'danger': '!VESZÉLY!', 'error': 'Hiba', 'hint': 'Tanács', 'important': 'Fontos', 'tip': 'Tipp', 'seealso': 'Lásd még'}}


def test_additional_admonition_and_section_labels(tmp_path):
    observer = pdf_observer_environment(tmp_path / 'observer')
    for code, labels in MORE_TRANSLATIONS.items():
        destination = tmp_path / ('additional-' + code)
        result = call_public(render_language_book, destination, code,
            kwargs=dict(kinds=tuple(labels), section_reference=code in ('en', 'nl')))
        assert result.exception is None, result.traceback
        assert result.value is True, (result.stdout, result.stderr)
        snapshot = observe_pdf(destination.with_suffix('.pdf'), env=observer)
        text = pdf_plain_text(snapshot).casefold()
        # Observe each generated title at its own supplied body carrier. Case
        # and punctuation of the localized short label have no semantic effect.
        import re
        words = lambda value: re.findall(r'[^\W\d_]+', value.casefold())
        tokens = words(text)
        for kind, label in labels.items():
            expected = words(label) + ['advice', 'for', kind]
            assert any(tokens[i:i+len(expected)] == expected
                       for i in range(len(tokens))), (code, kind, text)
        if code in ('en', 'nl'):
            from F09_helpers import compact_line
            expected = 'Section' if code == 'en' else 'Sectie'
            assert compact_line(snapshot, 'SectionStart').casefold() == (
                'SectionStart' + expected + '1.1SectionEnd').casefold()
