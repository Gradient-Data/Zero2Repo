# Interface Contract

The Python package is `talvo`, with source under `src/talvo`. Public modules are importable through their `talvo` paths. The command-line module is invoked with `python -m talvo` from the caller's working directory.

Programmatic content accepts Python strings and styled-text objects. Block content is passed as flowable objects. A `style` argument accepts a style object, a style-label string, or `None`; an `id` is a caller-supplied target identifier. Caller-supplied identifiers and labels are strings.

Styled classes serve as selectors. Selector syntax includes `Class.like(style_name, **attributes)`, keyword `style` for a style-label constraint, `/` between selectors, `...` within a selector expression, and unary `+` and `-`. The selector attributes used by callers are `id`, `has_class`, `level` and `index_level`. Selectors are accepted by `StyledMatcher`.

Python diagnostics are observable through the warnings interface as `TalvoWarning` records. Command-line textual reports use stdout; failure diagnostics use stderr. Text files exchanged with public readers and configuration loaders use UTF-8.

The project root is installable with `python -m pip install PROJECT_DIRECTORY`; the installed distribution exposes the same `talvo` package and public entries.

## `talvo.attribute.ParseError`

`ParseError` is the exception class exposed for textual attribute parsing failures.

## `talvo.attribute.OverrideDefault`

`OverrideDefault(default_value)` is used as a class attribute when defining a document-template subclass. It accepts the replacement value for an inherited template option.

## `talvo.attribute.Var`

`Var(name)` accepts a variable-name string and is accepted as a style-property or template-option value.

## `talvo.attribute.Attribute`

`Attribute(accepted_type, default_value, description)` declares a configurable reader option on a reader subclass. The arguments are the public value-type class, the declared default value, and descriptive text.

## `talvo.attribute.Integer`

`Integer` is the public integer attribute-type class accepted by `Attribute` for reader option declarations.

## `talvo.attribute.Bool`

`Bool` is the public boolean attribute-type class accepted by `Attribute` for reader option declarations.

## `talvo.dimension.Dimension`

`Dimension(value, unit)` accepts a numeric magnitude and an optional physical unit object. `float(length)` returns its numeric point value. Length operands support `+`, `-`, unary `-`, scalar `*`, scalar `/`, and comparisons `==`, `<`, `>`, `<=`, `>=`; comparison results are booleans. Plain numeric operands are accepted by addition and subtraction.

`grow(value)` accepts a number or length. `Dimension.from_string(text)` accepts a string and returns a physical or relative length. Relative length objects expose `to_points(total_dimension)`, returning a number for a numeric or length reference. Textual parsing rejection raises `talvo.attribute.ParseError`.

Textual physical units are `pt`, `pc`, `in`, `mm` and `cm` for points, picas, inches, millimeters and centimeters. The form is a signed decimal magnitude followed by a unit, with an optional separating space. Relative forms append `%`, `/2` or `/4` for percentages, halves or quarters; halves and quarters use integer numerators.

## `talvo.dimension.PT`

`PT` is a unit object. Multiplying a numeric magnitude by `PT` produces a length accepted by public length arguments. The result supports `float(length)` returning a point value.

## `talvo.dimension.PICA`

`PICA` is a unit object. Multiplying a numeric magnitude by `PICA` produces a length accepted by public length arguments. The result supports `float(length)` returning a point value.

## `talvo.dimension.INCH`

`INCH` is a unit object. Multiplying a numeric magnitude by `INCH` produces a length accepted by public length arguments. The result supports `float(length)` returning a point value.

## `talvo.dimension.MM`

`MM` is a unit object. Multiplying a numeric magnitude by `MM` produces a length accepted by public length arguments. The result supports `float(length)` returning a point value.

## `talvo.dimension.CM`

`CM` is a unit object. Multiplying a numeric magnitude by `CM` produces a length accepted by public length arguments. The result supports `float(length)` returning a point value.

## `talvo.dimension.PERCENT`

`PERCENT` is a unit object. Multiplying a numeric magnitude by `PERCENT` produces a length accepted by public length arguments. The result exposes `to_points(total_dimension)` returning a numeric point value.

## `talvo.dimension.HALVES`

`HALVES` is a unit object. Multiplying a numeric magnitude by `HALVES` produces a length accepted by public length arguments. The result exposes `to_points(total_dimension)` returning a numeric point value.

## `talvo.dimension.QUARTERS`

`QUARTERS` is a unit object. Multiplying a numeric magnitude by `QUARTERS` produces a length accepted by public length arguments. The result exposes `to_points(total_dimension)` returning a numeric point value.

## `talvo.color.Color`

`Color(red, green, blue, alpha)` accepts numeric components; `alpha` is optional. Numeric attributes `r`, `g`, `b`, `a` expose red, green, blue and opacity respectively. Constructor rejection raises `ValueError`.

`Color.from_string(string)` returns a color object with the same component attributes. Textual parsing rejection raises `talvo.attribute.ParseError`.

## `talvo.color.Gray`

`Gray(luminance, alpha)` accepts numeric brightness and optional opacity. Its numeric `r`, `g`, `b`, `a` attributes expose color components and opacity. Constructor rejection raises `ValueError`.

## `talvo.color.HexColor`

`HexColor(string)` accepts a hexadecimal color-description string and returns a color exposing numeric `r`, `g`, `b`, `a` component attributes. Constructor rejection raises `ValueError`.

The textual component order is red, green, blue, followed by optional opacity, with an optional leading `#`. The same textual form is accepted by `Color.from_string`.

## `talvo.color.BLACK`

`BLACK` is a color object accepted by `font_color`.

## `talvo.paper.Paper`

`Paper(name, width, height)` accepts a name string and physical lengths and returns a paper object accepted by `page_size`. `Paper.from_string(string)` accepts a paper description and returns a paper object.

A custom textual paper description has the form `<width> * <height>`, with physical lengths on both sides.

## `talvo.document.DocumentTree`

`DocumentTree(flowables)` accepts a list of flowables and returns the document content object passed to a document template. Its `children` attribute exposes the contained flowables.

## `talvo.template.DocumentTemplate`

`DocumentTemplate(document_tree, configuration=configuration)` is the public base for caller-defined document templates. Subclasses expose named document-part and page-template attributes. `parts` is the template option for a list of part-name strings.

`Template.Configuration(name, base=base, language=language, strings=strings, stylesheet=stylesheet, parts=parts)` returns a configuration for a document-template class. The name is a required string. `base` accepts a configuration, `language` a language object, `strings` a string collection, `stylesheet` a style sheet, and `parts` a list of component-name strings. Configuration `variables` is a writable mapping from variable names to option values. `configuration(component, **options)` supplies settings for a named component; `base` names a base component. An invalid programmatic option is signaled with `TypeError`; an unknown component is signaled with `ValueError`.

A document's `metadata` mapping supports `update(mapping)`. The exchanged keys are `title`, `subtitle`, `author`, `date`, `abstract` and caller-defined keys. Textual metadata accepts strings or styled text; `abstract` accepts a flowable. `get_metadata(key)` returns a stored metadata value. `insert(document_part_name, flowable, position)` accepts a part name, a flowable and a zero-based insertion position.

`render(filename_root)` accepts a filename-root string and returns a boolean: `True` signals successful rendering and `False` signals rendering with reported errors. The output file is `<filename_root>.pdf`. Incomplete destination requests are signaled with `ValueError`.

## `talvo.templates.Article`

`Article(document_tree, configuration=configuration)` returns a document instance and is importable as `talvo.templates.Article`. The class may be subclassed, with named part and page declarations. `Article.Configuration(name, **options)` returns a configuration; `name` is a required string. The document exposes `metadata`, `render`, `insert` and `get_metadata` with the document-template interfaces.

The additional article option `abstract_location` is a string. Named components include `contents` and `contents_page`. The page-decoration options `title_page_header_text` and `title_page_footer_text` accept styled text or `None`.

`abstract_location` values are `title` and `body`, identifying the title area and body.

## `talvo.templates.Book`

`Book(document_tree, configuration=configuration)` returns a document instance and is importable as `talvo.templates.Book`. The class may be subclassed, with named part and page declarations. `Book.Configuration(name, **options)` returns a configuration; `name` is a required string. The document exposes `metadata`, `render`, `insert` and `get_metadata` with the document-template interfaces.

Named components exposed to configuration include `front_matter_page`, `front_matter_left_page`, `front_matter_right_page`, `contents_page`, `contents_left_page`, `contents_right_page`, `back_matter_page`, `back_matter_left_page`, `back_matter_right_page`.

## `talvo.template.ContentsPartTemplate`

`ContentsPartTemplate(**options)` is a document-part declaration accepted as a named attribute on a template subclass. The `page_number_format` string option is accepted. The corresponding configuration also accepts string `end_at_page` and boolean `drop_if_empty`.

`page_number_format` additionally accepts `continue` for continuation. `end_at_page` accepts `any`, `left` and `right`.

## `talvo.template.FixedDocumentPartTemplate`

`FixedDocumentPartTemplate()` is a document-part declaration accepted as a named attribute on a template subclass. Its configuration accepts `flowables` as a list, `page_number_format` and `end_at_page` as strings, and `drop_if_empty` as a boolean.

`page_number_format` additionally accepts `continue`; `end_at_page` accepts `any`, `left` and `right`.

## `talvo.template.BodyPageTemplate`

`BodyPageTemplate(**options)` is a named page declaration on a template subclass. It accepts `base` as a component-name string. The same options are accepted through `configuration(component, **options)`.

`page_size` accepts a paper object; `page_orientation` is a string; `left_margin`, `right_margin`, `top_margin`, `bottom_margin`, `column_spacing`, `header_footer_distance` and `chapter_title_height` accept lengths; `columns` accepts an integer. `background` accepts a background-image object. `header_text`, `footer_text`, `chapter_header_text` and `chapter_footer_text` accept styled text, a variable reference or `None`. `chapter_title_flowables` accepts a flowable list or `None`.

`page_orientation` values are `portrait` and `landscape`.

## `talvo.template.TemplateConfigurationFile`

`TemplateConfigurationFile(filename)` accepts a configuration-file path and returns a configuration. Its `template` attribute is the selected template class, callable with a document tree and `configuration`.

The exchanged file is UTF-8 INI. `[TEMPLATE_CONFIGURATION]` carries `name`, `template`, `base` and `stylesheet` string settings. `[VARIABLES]` maps variable names to textual values; `paper_size` is a supplied variable name. Named component sections carry option-name/value settings, including `left_margin`, `right_margin`, `header_text` and `title_page_header_text`. Styled-text literals in these files use single quotes. Loading or using an unknown component raises `ValueError`.

## `talvo.style.StyleSheet`

`StyleSheet(name, matcher=matcher, base=base)` returns a style sheet; `matcher` and `base` are optional. `base` accepts another style sheet or a registered-name string. `matcher` accepts a styled matcher.

`sheet(label, **properties)` defines properties of a named style. `sheet[label] = style` assigns a style object. A definition's `base` accepts a named style, `PARENT_STYLE`, `NEXT_STYLE` or the reset selector `default`. `variables` is a writable mapping from names to style values, including variable references supplied through `Var(name)`.

## `talvo.style.StyledMatcher`

`StyledMatcher(mapping)` accepts a mapping from style-label strings to selector expressions and returns a matcher accepted by a style sheet.

## `talvo.style.PARENT_STYLE`

`PARENT_STYLE` is a style-base sentinel accepted by `base` in a style definition.

## `talvo.style.NEXT_STYLE`

`NEXT_STYLE` is a style-base sentinel accepted by `base` in a style definition.

## `talvo.style.StyleSheetFile`

`StyleSheetFile(filename)` accepts a style-file path and returns a style sheet.

The exchanged file is UTF-8 INI. `[STYLESHEET]` carries `name` and `base` strings. `[VARIABLES]` carries named textual style values, including `serif_typeface`. Named style sections such as `[body]` carry property/value settings, including `font_size`, `font_color` and `typeface`.

## `talvo.stylesheets.sphinx`

`sphinx` is a supplied style-sheet object in `talvo.stylesheets` and a registered style-sheet name accepted by `base` and `--stylesheet`.

## `talvo.stylesheets.sphinx_article`

`sphinx_article` is a supplied style-sheet object in `talvo.stylesheets` and a registered style-sheet name accepted by `base` and `--stylesheet`.

## `talvo.stylesheets.sphinx_base14`

`sphinx_base14` is a supplied style-sheet object in `talvo.stylesheets` and a registered style-sheet name accepted by `base` and `--stylesheet`.

## `talvo.stylesheets.sphinx_article_base14`

`sphinx_article_base14` is a supplied style-sheet object in `talvo.stylesheets` and a registered style-sheet name accepted by `base` and `--stylesheet`.

## `talvo.paragraph.Paragraph`

`Paragraph(content, custom_label=custom_label, id=id, style=style)` accepts plain text, styled text or a list of inline items and returns a flowable. The optional `custom_label` is text; `id` is a target identifier. `classes` is a mutable list of class-label strings.

`Paragraph.like(style_name, **attributes)` returns a selector; the style name is optional. Selectors accept `id` and `has_class` constraints.

## `talvo.paragraph.ParagraphBase`

`ParagraphBase` is exposed as a paragraph-type selector.

## `talvo.paragraph.ParagraphStyle`

`ParagraphStyle(base=base, **attributes)` returns a style object. The optional `base` accepts a named style or style-base sentinel.

The supplied text properties are `typeface` (typeface object or variable reference), `font_weight` and `font_width` (integers), `font_slant` and `font_variant` (strings), `font_size` and `character_spacing` (lengths), `font_color` (color), `kerning`, `ligatures` and `hyphenate` (booleans), `hyphen_lang` (string), `hyphen_chars` (integer), and `no_break_after` (word list object).

Paragraph properties are `indent_first` (length), `line_spacing` (spacing object), `text_align` (string), `tab_stops` (tab-stop list), `split_minimum_lines` (integer), `number_format` (string or `None`), `number_separator`, `label_prefix` and `label_suffix` (styled text or `None`), `numbering_level` (integer), `custom_label` and `keep_with_next` (booleans), and `before` and `after` (styled text or `None`).

Block properties accept `space_above`, `space_below`, `margin_left`, `margin_right`, `padding`, `padding_left`, `padding_right`, `padding_top`, `padding_bottom` as lengths or numeric zero; `border`, `border_left`, `border_right`, `border_top`, `border_bottom` as strokes; `background_color` as a color; and `hide` as a boolean. These property names are also accepted in paragraph definitions made through a style sheet.

`text_align` values are `left`, `right`, `center` and `justify`. `number_format` values are `number`, `lowercase character`, `uppercase character`, `lowercase roman`, `uppercase roman`, `symbol` and `None`, denoting decimal, alphabetic, Roman, footnote-symbol and unnumbered labels respectively. These numbering spellings also apply to heading, caption, equation-label, note-marker and part numbering. `font_variant` values are `normal`, `small capital` and `oldstyle figures`.

## `talvo.paragraph.ProportionalSpacing`

`ProportionalSpacing(factor)` accepts a numeric factor and returns a `line_spacing` value.

## `talvo.paragraph.FixedSpacing`

`FixedSpacing(pitch, minimum=minimum)` accepts a physical pitch length and an optional spacing object or `None` minimum. It returns a `line_spacing` value.

## `talvo.paragraph.SINGLE`

`SINGLE` is a spacing object accepted by `line_spacing`.

## `talvo.paragraph.STANDARD`

`STANDARD` is a spacing object accepted by `line_spacing`.

## `talvo.paragraph.DOUBLE`

`DOUBLE` is a spacing object accepted by `line_spacing`.

## `talvo.paragraph.TabStop`

`TabStop(position, align)` accepts a length position and an optional alignment string and returns a tab-stop object.

`align` values are `left`, `right` and `center`.

## `talvo.paragraph.TabStopList`

`TabStopList(iterable)` accepts a list of tab-stop objects and returns a value accepted by `tab_stops`.

## `talvo.text.StyledText`

`StyledText` is the public inline-text selector type. `StyledText.like(style_name, **attributes)` returns a selector. Styled text supports `+` with strings or other styled text, including a string on the left; the result is composable inline content.

## `talvo.text.SingleStyledText`

`SingleStyledText(text, style=style)` accepts a string and an optional style object or style-label string. It returns inline content. Its writable `annotation` accepts a hyperlink object.

## `talvo.text.MixedStyledText`

`MixedStyledText(text_or_items, style=style)` accepts text or a list of strings and inline objects, with optional style object or label. It returns inline content and supports concatenation with text or styled text.

## `talvo.text.TextStyle`

`TextStyle(**attributes)` returns an inline style. Supplied properties include `font_size` (length), `font_color` (color), `before` and `after` (styled text or `None`), `font_slant` (string), `font_weight` (integer) and `typeface` (typeface object). These names can also be used in style-sheet definitions targeting `StyledText`.

## `talvo.text.Superscript`

`Superscript` is an exposed inline-content type that can be imported from `talvo.text`.

## `talvo.text.Subscript`

`Subscript` is an exposed inline-content type that can be imported from `talvo.text`.

## `talvo.text.NoBreakAfter`

`NoBreakAfter(words)` accepts a list of strings and returns a value accepted by `no_break_after`.

## `talvo.flowable.FlowableStyle`

`FlowableStyle(**attributes)` returns a block style. `space_below` accepts a length.

## `talvo.flowable.Flowable`

`Flowable()` is the public base for caller-defined block content. A subclass may implement `render(container, last_descender, state, **kwargs)` and return a three-item tuple `(width, top_to_baseline, descender)` of numeric or length values. The received container can be passed to public drawing objects' `render(container)` calls and exposes `advance(height)` for a length.

Drawing coordinates exchanged through this interface are in points, relative to the content container, with positive vertical direction upward.

## `talvo.flowable.DummyFlowable`

`DummyFlowable()` returns a flowable accepted as content or an admonition label.

## `talvo.flowable.GroupedFlowables`

`GroupedFlowables` is an exposed block-group selector. `GroupedFlowables.like(style_name)` accepts a style-label string and returns a selector.

## `talvo.flowable.StaticGroupedFlowables`

`StaticGroupedFlowables(flowables, style=style)` accepts a flowable list and optional style object or label. The class is also a selector and exposes `like(style_name)`.

## `talvo.flowable.PageBreak`

`PageBreak(page_break)` returns a flowable; the optional `page_break` argument is a page-side string.

`page_break` values are `any`, `left` and `right`, for an unrestricted new page or the selected page side.

## `talvo.font.Typeface`

`Typeface(name, *fonts)` accepts a family name and supplied font objects, and returns a typeface. `Typeface(name)` and `Typeface.from_string(name)` also accept a family-name string.

`get_font(weight=weight, slant=slant, width=width)` returns a font object. The arguments are optional integer weight, slant string and integer width. `fonts()` returns an iterable of available font objects. `name` is the family-name string.

A returned font exposes `get_glyph_metrics(char, variant)` accepting a single-character string and variant string, returning an object with `name` (glyph-name string) and `width` (numeric advance in font units). Missing-glyph failure raises `MissingGlyphException`.

Face-substitution diagnostics use Python `TalvoWarning`. The message carries `<family>` and `<requested-width> <requested-weight> <requested-slant>` before the label `Falling back to`, and `<selected-width> <selected-weight> <selected-slant>` after that label.

## `talvo.font.MissingGlyphException`

`MissingGlyphException` is the public exception class signaling a missing glyph on a direct font request.

## `talvo.font.opentype.OpenTypeFont`

`OpenTypeFont(filename)` accepts a font-file path string and returns a font object accepted by `Typeface`.

## `talvo.font.type1.Type1Font`

`Type1Font(filename, weight=weight, core=core, unicode_mapping=unicode_mapping)` accepts a Type1 filename root, optional integer weight, optional boolean core-font selection, and an optional mapping from Unicode integer code points to lists of PostScript glyph-name strings. It returns a font object accepted by `Typeface`. The root names the associated `.afm` metrics file and, for a supplied font program, the `.pfa` file.

## `talvo.font.style.FontSlant`

`FontSlant.from_string(string)` accepts a string and returns a slant string. A refused choice raises `ValueError` or `talvo.attribute.ParseError`.

## `talvo.font.style.FontWidth`

`FontWidth.from_string(string)` accepts a string and returns a integer width class. A refused choice raises `ValueError` or `talvo.attribute.ParseError`.

## `talvo.font.style.FontWeight`

`FontWeight.from_string(string)` accepts a string and returns a integer weight. A refused choice raises `ValueError` or `talvo.attribute.ParseError`.

Named weight forms used in face descriptions and textual weight input are `thin`, `extra-light`, `light`, `regular`, `medium`, `semi-bold`, `bold`, `extra-bold` and `heavy`, for classes 100 through 900 in steps of 100. Class 100 also has the form `hairline`, class 200 `ultra-light`, and class 900 `black`.

## `talvo.language.Language`

`Language.from_string(string)` returns a language object accepted by template configuration.

Language codes are `en`, `fr`, `it`, `nl`, `de`, `pl`, `cs`, `es` and `hu`, denoting English, French, Italian, Dutch, German, Polish, Czech, Spanish and Hungarian respectively.

## `talvo.strings.Strings`

`Strings()` returns a string collection supporting assignment by string key: `strings[identifier] = value`. Prefix `@` denotes a standard-string key; prefix `$` denotes a caller-defined key. Values are strings. Keys supplied to the collection include `@chapter`, `@warning`, `@index_see` and `@index_seealso`.

## `talvo.strings.StringField`

`StringField(key, user=user)` accepts a string key and optional boolean `user` selection and returns inline content. It supports concatenation with strings and other inline content.

## `talvo.annotation.HyperLink`

`HyperLink(target)` accepts a destination URI string. The returned annotation object can be assigned to the `annotation` attribute of text or image content.

## `talvo.structure.Section`

`Section(flowables, id=id, style=style)` returns block content. `flowables` is a list; `id` and `style` are optional. The class is also a selector; `Section.like(style=style)` returns one. Style-sheet properties include `show_in_toc` and `hide` (booleans) and `page_break` (string or `None`).

## `talvo.structure.Heading`

`Heading(content, custom_label=custom_label, style=style)` returns block content. `content` is text or styled text; `custom_label` and `style` are optional. `Heading.style_class(**attributes)` constructs a heading style. Its properties include `custom_label` (boolean) `number_format` (string or `None`), and `number_separator` (styled text or `None`). `Heading.like(level=level)` returns a selector for an integer section level.

## `talvo.structure.List`

`List(list_items, style=style)` returns block content. `list_items` is a list of list-item objects; `style` is optional. The class is accepted as a selector and exposes `like(style_name)`.

Its style-sheet property `bullet` accepts styled text for the unordered-list label.

## `talvo.structure.ListItem`

`ListItem(flowable)` returns block content. `flowable` is the item body. The class is accepted as a selector.

## `talvo.structure.Admonition`

`Admonition(label, flowable, type=type)` returns block content. `label` and `flowable` are flowables; `type` is an optional string. Style-sheet property `inline_title` is boolean.

Admonition category strings are `attention`, `caution`, `danger`, `error`, `hint`, `important`, `note`, `tip`, `warning` and `seealso`.

## `talvo.structure.AdmonitionFlowables`

`AdmonitionFlowables(flowables)` returns block content. `flowables` is a list of block content.

## `talvo.structure.ListItemLabel`

`ListItemLabel` is the selector for list labels. Its style-sheet property `hide` is boolean.

## `talvo.structure.TableOfContents`

`TableOfContents(local=local, style=style)` returns a flowable. The optional `local` is boolean, and `style` accepts a contents style or label.

## `talvo.structure.TableOfContentsStyle`

`TableOfContentsStyle(depth=depth)` returns a contents style. The optional `depth` is an integer.

## `talvo.structure.TableOfContentsSection`

`TableOfContentsSection` is an exposed selector for the contents section. Its style-sheet property `hide` is boolean.

## `talvo.structure.TableOfContentsEntry`

`TableOfContentsEntry` is an exposed selector for navigation entries. Style-sheet property `text` accepts styled text containing `ReferenceField` objects.

## `talvo.structure.ListOfEntry`

`ListOfEntry` is an exposed selector for navigation entries. Style-sheet property `text` accepts styled text containing `ReferenceField` objects.

## `talvo.reference.Reference`

`Reference(target_id, type=type, custom_title=custom_title, style=style)` returns inline content. `target_id` is a string; optional `type` is a string, `custom_title` is styled text or `None`, and `style` accepts a reference style or label.

A descriptive section reference carries `<section-category> <number>` as readable PDF text.

The unresolved-reference indication is `??` in rendered text. Reference diagnostics are Python `TalvoWarning` records carrying single-quoted `'<target-id>'` and `'<reference-kind>'` fields.

`type` values are `reference`, `number`, `title`, `page` and `custom`, identifying descriptive reference text, number, title, page number and caller-supplied text respectively.

## `talvo.reference.ReferenceStyle`

`ReferenceStyle(link=link, quiet=quiet)` returns a reference style; both optional properties are boolean.

## `talvo.reference.ReferenceField`

`ReferenceField(type)` accepts a reference-kind string and returns inline content used in a navigation-entry `text` property.

`type` uses `number`, `title` and `page` for the corresponding navigation fields.

## `talvo.reference.Field`

`Field(type)` returns inline content. `type` is a page, section or metadata field object.

## `talvo.reference.PAGE_NUMBER`

`PAGE_NUMBER` is a field-type object accepted by `Field`.

## `talvo.reference.NUMBER_OF_PAGES`

`NUMBER_OF_PAGES` is a field-type object accepted by `Field`.

## `talvo.reference.DOCUMENT_TITLE`

`DOCUMENT_TITLE` is a field-type object accepted by `Field`.

## `talvo.reference.DOCUMENT_SUBTITLE`

`DOCUMENT_SUBTITLE` is a field-type object accepted by `Field`.

## `talvo.reference.DOCUMENT_AUTHOR`

`DOCUMENT_AUTHOR` is a field-type object accepted by `Field`.

## `talvo.reference.SECTION_NUMBER`

`SECTION_NUMBER(level)` accepts an integer section level and returns a field-type object accepted by `Field`.

## `talvo.reference.SECTION_TITLE`

`SECTION_TITLE(level)` accepts an integer section level and returns a field-type object accepted by `Field`.

## `talvo.reference.Note`

`Note(flowable, id=id, style=style)` returns a note flowable. `id` and `style` are optional. The class is an exposed selector with `like(style=style)`. Its style-sheet property `location` is a string.

`location` values are `footer` and `in-place`.

## `talvo.reference.NoteMarkerBase`

`NoteMarkerBase` is a note-marker selector exposing `like(style=style)`. Its style-sheet properties include `number_format` (string), `link` and `custom_label` (booleans), and `label_prefix` and `label_suffix` (styled text or `None`).

## `talvo.reference.NoteMarkerByID`

`NoteMarkerByID(target_id, custom_label=custom_label, style=style)` accepts a target-id string and optional styled custom label and style. It returns inline note-marker content.

## `talvo.reference.NoteMarkerWithNote`

`NoteMarkerWithNote(note, custom_label=custom_label, style=style)` accepts a note object and optional styled custom label and style. It returns inline note-marker content.

## `talvo.image.Image`

`Image(filename_or_file, width=width, height=height, scale=scale, dpi=dpi, rotate=rotate, alt=alt)` returns an image object. The first argument accepts a path string. Optional `width` and `height` are lengths; `scale` is a number or sizing-mode string; `dpi` and `rotate` are numbers; `alt` is text or `None`.

The writable `annotation` attribute accepts a hyperlink. Conflicting sizing requests are signaled with `TypeError`. Rendering failures are signaled by the document rendering result and `TalvoWarning` carrying the image identity.

The sizing-mode strings for `scale` are `fit` and `fill`.

## `talvo.image.InlineImage`

`InlineImage(filename_or_file, width=width, height=height, scale=scale, dpi=dpi, rotate=rotate, alt=alt)` returns inline content. The first argument accepts a path string. Optional `width` and `height` are lengths; `scale` is a number or sizing-mode string; `dpi` and `rotate` are numbers; `alt` is text or `None`.

## `talvo.image.BackgroundImage`

`BackgroundImage(filename_or_file, width=width, height=height, scale=scale, dpi=dpi, rotate=rotate, alt=alt)` returns an image object. The first argument accepts a path string. Optional `width` and `height` are lengths; `scale` is a number or sizing-mode string; `dpi` and `rotate` are numbers; `alt` is text or `None`. The object is accepted by the page option `background`.

## `talvo.image.Figure`

`Figure(flowables, id=id, style=style)` accepts a list of block content and optional identifier and style, returning a flowable.

## `talvo.image.FigureStyle`

`FigureStyle(float=placement)` returns a figure style; `float` accepts a placement string or `None`.

Placement forms are `None` for body placement, `here` for placement above the body and `sideways` for a sideways page.

## `talvo.image.Caption`

`Caption(content, style=style)` accepts text or styled text and optional style, returning a caption flowable. It is also an exposed selector with `like(style=style)`. Its style-sheet properties include `number_format` (string or `None`) and `numbering_level` (integer).

English numbered caption text carries the label `Figure` for a figure and `Table` for a table, followed by `<number> <caption-text>`.

## `talvo.image.ListOfFigures`

`ListOfFigures()` returns a flowable and is also an exposed selector.

## `talvo.draw.Stroke`

`Stroke(width, color)` accepts a physical width and color object and returns a stroke value.

## `talvo.draw.Line`

`Line(start, end, style=style)` accepts two coordinate pairs and an optional line style. `render(container)` draws the object into the supplied document container.

## `talvo.draw.Polygon`

`Polygon(points, style=style)` accepts a list of coordinate pairs and an optional shape style. `render(container)` draws the object into the supplied document container.

## `talvo.draw.Rectangle`

`Rectangle(bottom_left, width, height, style=style)` accepts a coordinate pair, numeric width and height, and an optional shape style. `render(container)` draws the object into the supplied document container.

## `talvo.draw.LineStyle`

`LineStyle(stroke=stroke)` returns a line style. The `stroke` property accepts a stroke object or `None`.

## `talvo.draw.ShapeStyle`

`ShapeStyle(stroke=stroke, fill_color=fill_color)` returns a shape style. `stroke` accepts a stroke object or `None`; `fill_color` accepts a color object or `None`.

## `talvo.table.Table`

`Table(body, head=head, column_widths=column_widths, width=width, style=style)` returns a flowable. `body` is a table-body object or `None`, `head` an optional table-head object, `column_widths` an optional list of lengths, integer proportions or `None` entries, and `width` an optional length. `style` accepts a table style or label. Inconsistent sizing is signaled with `ValueError` when the table is rendered.

## `talvo.table.TableBody`

`TableBody(rows)` accepts a list of table-row objects and returns a table section.

## `talvo.table.TableHead`

`TableHead(rows)` accepts a list of table-row objects and returns a table section.

## `talvo.table.TableRow`

`TableRow(cells)` accepts a list of table-cell objects and returns a table row.

## `talvo.table.TableCell`

`TableCell(flowables, rowspan=rowspan, colspan=colspan, style=style)` accepts a list of flowables, optional integer spans and an optional cell style or label. It returns a cell object. It is an exposed selector with `like(style=style)`.

## `talvo.table.TableStyle`

`TableStyle(**attributes)` returns a table style. `column_widths` accepts a list of lengths, integer proportions or `None` entries; `repeat_head` is boolean; `split_minimum_rows` is an integer; `border` accepts a stroke and `background_color` a color.

## `talvo.table.TableCellStyle`

`TableCellStyle(**attributes)` returns a cell style. `vertical_align` is a string, `padding` is a length and `background_color` is a color.

`vertical_align` values are `top`, `middle` and `bottom`.

## `talvo.table.TableCellBackground`

`TableCellBackground` is a selector for cell background artwork. Its style-sheet property `fill_color` accepts a color.

## `talvo.table.TableCellBorder`

`TableCellBorder` is a selector for cell border artwork. Its style-sheet property `stroke` accepts a stroke.

## `talvo.table.TableWithCaption`

`TableWithCaption(flowables, id=id, style=style)` accepts a list of flowables, optional target identifier and optional style, returning a captioned-table flowable.

## `talvo.table.TableWithCaptionStyle`

`TableWithCaptionStyle(float=placement)` returns a captioned-table style. `float` accepts a placement string or `None`.

`sideways` selects sideways placement; `None` denotes body placement.

## `talvo.table.ListOfTables`

`ListOfTables()` returns a flowable and is also an exposed selector.

## `talvo.index.Index`

`Index(style=style)` returns an index flowable. `style` is optional and accepts an index style or label.

## `talvo.index.IndexStyle`

`IndexStyle(initials=initials)` returns an index style; `initials` is an optional boolean.

## `talvo.index.IndexTerm`

`IndexTerm(*terms)` accepts positional term strings and returns an index-term value.

## `talvo.index.IndexSee`

`IndexSee(term, reference)` accepts a term string and reference-text string, and returns an index cross-reference value.

## `talvo.index.IndexSeeAlso`

`IndexSeeAlso(term, reference)` accepts a term string and reference-text string, and returns an index cross-reference value.

## `talvo.index.IndexTarget`

`IndexTarget(index_terms)` accepts a list of index terms or cross-reference values and returns a flowable.

## `talvo.index.InlineIndexTarget`

`InlineIndexTarget(index_terms)` accepts a list of index terms or cross-reference values and returns inline content.

## `talvo.index.IndexLabel`

`IndexLabel` is an exposed index-heading selector. Its style-sheet property `keep_with_next` is boolean.

## `talvo.styleds.IndexEntry`

`IndexEntry` is importable from `talvo.styleds` as an index-entry selector. `IndexEntry.like(index_level=level)` accepts an integer level. Its style-sheet property `margin_left` accepts a length.

## `talvo.math.Equation`

`Equation(latex_equation, inline=inline)` accepts a LaTeX-expression string and optional boolean inline selection, returning inline equation content. It is an exposed selector; its `style_class` accepts `font_size` (length) and `font_color` (color) properties.

A missing-mathematics-support diagnostic is a Python `TalvoWarning` whose message begins with the label `Math rendering`, followed by explanatory text.

## `talvo.math.DisplayEquation`

`DisplayEquation(latex_equation, id=id)` accepts a LaTeX-expression string and optional target identifier, returning a flowable.

## `talvo.math.EquationLabel`

`EquationLabel` is an exposed equation-label selector. Its style-sheet properties are `number_format` (string), `label_prefix` and `label_suffix` (styled text or `None`).

## `talvo.highlight.CodeBlock`

`CodeBlock(text, language=language)` accepts a source-code string and optional language-name string, returning a flowable and exposed selector.

## `talvo.highlight.pygments_style_to_stylesheet`

`pygments_style_to_stylesheet(style, base=base)` accepts a Pygments Style class declaring token-category style strings, and an optional base style sheet. It returns a style sheet.

## `talvo.glossary.GlossaryTerm`

`GlossaryTerm(term, definition=definition, style=style)` accepts styled term text, an optional styled definition, and an optional style. It returns inline content. Glossary diagnostics use `TalvoWarning` and carry the affected term.

## `talvo.glossary.GlossaryTermStyle`

`GlossaryTermStyle(show_definition=policy)` accepts an optional policy string and returns a glossary-term style.

`show_definition` values are `first`, `always` and `never`.

## `talvo.frontend.Reader`

`Reader` is importable from `talvo.frontend` and is the public base for installed readers. A subclass declares `extensions` as an iterable of filename-extension strings and configurable options as `Attribute` declarations. `reader[name]` returns a configured option value.

The reader callable accepts option keyword values. `parse(filename)` returns a `DocumentTree` accepted by document templates.

## `talvo.frontend.rst.ReStructuredTextReader`

`ReStructuredTextReader()` returns a reader. `parse(filename_or_file)` accepts a source filename string or an open text stream and returns a `DocumentTree` accepted by document templates. Unavailable source input is signaled with `docutils.io.InputError`.

Parsed inline style labels include `emphasis`, `strong` and `monospaced`. Parsed block quotations use the group label `block quote`; warning admonitions have type `warning`. These labels are exposed to stylesheet selectors.

## `talvo.frontend.commonmark.CommonMarkReader`

`CommonMarkReader()` returns a reader. `parse(filename_or_file)` accepts a source filename string or an open text stream and returns a `DocumentTree` accepted by document templates. Unavailable source input is signaled with `docutils.io.InputError`.

Parsed inline style labels include `emphasis`, `strong` and `monospaced`; block quotations use the group label `block quote`. These labels are exposed to stylesheet selectors.

## `talvo.warnings.TalvoWarning`

`TalvoWarning` is the public warning category, a subclass of `UserWarning`. Messages carry diagnostic information and can be read through Python warning records.

Source-associated table diagnostics carry the envelope `[<source>:<location> <table>] <explanation>`. `<source>` is the source filename, `<location>` is a source-location field, and the tag `table` identifies the source element.

## `hyph_*.dic`

Caller-supplied hyphenation dictionaries are read from `hyph_<hyphen_lang>.dic` in the working directory. The exchanged file is a hyphenation dictionary in the `.dic` format, with its text-encoding declaration on the first line.

## `google_fonts`

Previously obtained static font files are read under `<XDG_DATA_HOME>/talvotype/google_fonts/<family>/<face>.ttf`. `XDG_DATA_HOME` names the caller-selected data directory; `<family>` is the selected family name and `<face>.ttf` is a font filename.

Font acquisition accepts `HTTPS_PROXY` as the caller-selected HTTPS proxy and `SSL_CERT_FILE` as the trusted certificate-authority file.

The font-service endpoint is `https://fonts.google.com/download/list?family=<family>`, with the family URL-encoded. Its JSON response has the five-byte prefix `)]}'\n` and a `manifest` object. `manifest.files` contains records with string `filename` and `contents` fields; `manifest.fileRefs` contains records with string `filename` and `url` fields. Referenced HTTPS URLs carry the font-file bytes. Filenames are relative paths within the family directory.

## `PDF`

Rendering writes a PDF binary file named `<filename_root>.pdf`. Its page sequence carries the published content. Publicly readable content includes Unicode text, character and line locations, baselines, text sizes, fonts and their bold, italic and monospaced properties, colors, page rectangles and rotation, graphic bounds, stroke widths and colors, fills, image artwork, transparency and embedded color profiles.

Physical geometry and text size are expressed in PDF points. The readable page text carries generated labels together with supplied content: numbered paragraph and heading labels surround their text with caller-supplied prefix and suffix; captions carry a category label, number and caption text. Note labels are beside note bodies, and inline note markers occur in paragraph text. Equation numbers occur as standalone label lines. Navigation-entry text uses the caller's `text` property and reference fields.

Index entry lines begin with the term and carry page labels and cross-references. Cross-references carry a category label and the supplied reference text. Initial headings occupy standalone lines.

PDF document properties `Title` and `Author` carry Unicode title and author strings. PDF links expose their source rectangles and either a destination URI or a resolvable internal page and point. The outline exposes hierarchy levels, title strings, and resolvable page destinations. Outline titles carry the available label and heading text as whitespace-separated text.

## `.stylelog`

A rendering's style report is the UTF-8 text file `<filename_root>.stylelog`. It contains indented element records followed by their indented match rows. A paragraph element record begins with `Paragraph('` and includes its text.

A match row has the form `<indent><mark> (<specificity>) <style-label> [<sheet-name>]`, with optional ` > <base-label>`. `<mark>` is `>` for the selected match or a space for another matching style. The style label identifies the matched definition; the bracketed name identifies its source sheet, and the base label identifies the named base style. Parenthesized specificity is text. Page separator lines begin with `---` and container headings with `####`.

## `python -m talvo`

Invoke `python -m talvo INPUT`, where `INPUT` is a source-file path. The conversion options are `--format FORMAT`, `--template NAME_OR_FILE`, `--stylesheet NAME_OR_FILE`, `--paper PAPER`, `--output DESTINATION`, repeatable `--option NAME=VALUE`, and the argument-free `--install-resources`. Format, resource, paper and option names are strings. Template and style-sheet selections accept a registered name or file path.

A destination can be a filename root or an existing directory. A filename-root destination produces `<root>.pdf`; an existing directory produces `<directory>/<input-stem>.pdf`. With no destination argument, the file is `<working-directory>/<input-stem>.pdf`. The result channel is the PDF file.

Conversion success exits `0`. Conversion refusal or reported rendering errors exit `1`. Failure diagnostics are on stderr and carry the offending input, resource, paper, option or image identity. A reader-value parsing failure can instead carry a nonempty stderr diagnostic without an option name. A format-assumption report appears on stdout and carries the assumed format name.

Discovery commands use `--list-formats`, `--list-templates`, `--list-stylesheets`, `--list-fonts` and `--list-options FRONTEND`. Successful discovery exits `0` and places records on stdout.

Format records are `- <registered-name> (.<extension>[, .<extension>...]) [<distribution>]`. Template and style-sheet records are `- <registered-name>`. Typeface family records are `- <family-name> [<distribution>]`, followed by face rows `   <width>: <style>[, <style>...]` with three leading spaces. A style field is `<weight>` or `<slant>-<weight>`.

Reader option records are `- <name> (<accepted-type>): <description>. Default: <default>`. The type field is the declared public type-class name, including `Integer` and `Bool`; the default field uses Python's string representation of the declared default (decimal integers and boolean `True` or `False`). A reader with no options has a nonempty stdout status report carrying the reader name, with no `- ` option record.

`--list-fonts FILENAME` writes a font-specimen PDF at `<FILENAME>.pdf` and exits `0` on success. Each specimen text row has the form `<typeface> <width> <slant> <weight>`.

Resource acquisition takes the requested typeface family name as its lookup input and `--install-resources` as explicit installation permission. Compatible typeface distributions from the selected package index declare their family registrations in the same form as the typeface distributions installed in the environment. Resource-installation inputs use `PIP_INDEX_URL` for the package index, `PIP_TARGET` for the installation destination, the other `PIP_*` settings for pip options, `HTTPS_PROXY` for the HTTPS proxy and `SSL_CERT_FILE` for trusted certificate authorities.

## `talvo.frontend.sphinx`

The Sphinx extension is `talvo.frontend.sphinx` and the builder name is `talvo`. Invoke `python -m sphinx -b talvo SOURCE OUTPUT`; `SOURCE` is the Sphinx project directory containing `conf.py`, and `OUTPUT` is the publication directory. The invocation also accepts `-E`, `-a` and `--no-color`. Published files are `OUTPUT/<target>.pdf`.

The `conf.py` setting `extensions` accepts `talvo.frontend.sphinx` and `sphinx.ext.graphviz`. The document settings used by the publishing interface are `master_doc`, `project`, `author`, `release`, `exclude_patterns`, `today` and `today_fmt`. Values are strings except the list-valued `exclude_patterns` and `extensions`.

`talvo_documents` is a list of target dictionaries. The exchanged keys are `doc` (root document name), `target` (output target name), `toctree_only` (boolean), `title`, `subtitle`, `author`, `date` and `logo` (strings), `template` (registered name or template configuration), `domain_indices` (boolean), and caller-defined metadata keys. `talvo_targets` is a list of target-name strings. The compatibility setting `latex_documents` is a list of tuples `(root, filename, title, author, documentclass)`. `graphviz_dot` is a string executable path.

Completed publishing exits `0`. An incomplete target configuration is signaled by exit `2`, with stderr carrying `talvo_documents` and the missing key. Nonfatal publishing reports use stderr and carry the relevant unknown document name, unknown target name, or `talvo_documents` configuration key.

The PDF contains navigation and domain-index text; the Python domain-index heading label is `Python Module Index`.

## `talvo.annotation`

The module `talvo.annotation` exposes `HyperLink`.

## `talvo.attribute`

The module `talvo.attribute` exposes `OverrideDefault`, `ParseError`, `Var`.

## `talvo.color`

The module `talvo.color` exposes `BLACK`, `Color`, `Gray`, `HexColor`.

## `talvo.dimension`

The module `talvo.dimension` exposes `CM`, `Dimension`, `HALVES`, `INCH`, `MM`, `PERCENT`, `PICA`, `PT`, `QUARTERS`.

## `talvo.document`

The module `talvo.document` exposes `DocumentTree`.

## `talvo.draw`

The module `talvo.draw` exposes `Line`, `LineStyle`, `Polygon`, `Rectangle`, `ShapeStyle`, `Stroke`.

## `talvo.flowable`

The module `talvo.flowable` exposes `DummyFlowable`, `Flowable`, `FlowableStyle`, `GroupedFlowables`, `PageBreak`, `StaticGroupedFlowables`.

## `talvo.font`

The module `talvo.font` exposes `MissingGlyphException`, `Typeface`.

## `talvo.font.opentype`

The module `talvo.font.opentype` exposes `OpenTypeFont`.

## `talvo.font.style`

The module `talvo.font.style` exposes `FontSlant`, `FontWeight`, `FontWidth`.

## `talvo.font.type1`

The module `talvo.font.type1` exposes `Type1Font`.

## `talvo.frontend.commonmark`

The module `talvo.frontend.commonmark` exposes `CommonMarkReader`.

## `talvo.frontend.rst`

The module `talvo.frontend.rst` exposes `ReStructuredTextReader`.

## `talvo.glossary`

The module `talvo.glossary` exposes `GlossaryTerm`, `GlossaryTermStyle`.

## `talvo.highlight`

The module `talvo.highlight` exposes `CodeBlock`, `pygments_style_to_stylesheet`.

## `talvo.image`

The module `talvo.image` exposes `BackgroundImage`, `Caption`, `Figure`, `FigureStyle`, `Image`, `InlineImage`, `ListOfFigures`.

## `talvo.index`

The module `talvo.index` exposes `Index`, `IndexLabel`, `IndexSee`, `IndexSeeAlso`, `IndexStyle`, `IndexTarget`, `IndexTerm`, `InlineIndexTarget`.

## `talvo.language`

The module `talvo.language` exposes `Language`.

The generated chapter, warning and note labels have these textual forms:

| Language | Chapter | Warning | Note |
| --- | --- | --- | --- |
| English | Chapter | Warning | Note |
| French | Chapitre | Avertissement | Note |
| Italian | Capitolo | Avvertimento | Nota |
| Dutch | Hoofdstuk | Waarschuwing | Noot |
| German | Kapitel | Warnung | Notiz |
| Polish | Rozdział | Ostrzeżenie | Notatka |
| Czech | Kapitola | Varování | Poznámka |
| Spanish | Capítulo | Precaución | Nota |
| Hungarian | Fejezet | Figyelmeztetés | Megjegyzés |

Additional generated admonition labels are:

| Language | Attention | Caution | Danger | Error | Hint | Important | Tip | See also |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| English | Attention! | Caution! | !DANGER! | Error | Hint | Important | Tip | See also |
| French | Attention ! | Prudence ! | ! DANGER ! | Erreur | Conseil | Important | Astuce | Voir aussi |
| Italian | Attenzione! | Prudenza! | !PERICOLO! | Errore | Consiglio | Importante | Suggerimento | Vedi anche |
| Dutch | Opgelet! | Pas op! | !GEVAAR! | Fout | Hint | Belangrijk | Tip | Zie ook |
| German | Aufgepasst! | Vorsicht! | !GEFAHR! | Fehler | Hinweis | Wichtig | Tipp | Siehe auch |
| Polish | Uwaga! | Ostrożnie! | !NIEBEZPIECZEŃSTWO! | Błąd | Wskazówka | Ważne | Porada | Zobacz również |
| Czech | Opatrnost! | Pozornost! | !NEBEZPEČÍ! | Chyba | Poznámka | Důležité | Tip | Viz také |
| Spanish | ¡Atención! | ¡Cuidado! | ¡PELIGRO! | Error | Pista | Importante | Consejo | Véase también |
| Hungarian | Figyelem! | Vigyázat!! | !VESZÉLY! | Hiba | Tanács | Fontos | Tipp | Lásd még |

Descriptive section-reference labels are `Section` in English and `Sectie` in Dutch.

## `talvo.math`

The module `talvo.math` exposes `DisplayEquation`, `Equation`, `EquationLabel`.

## `talvo.paper`

The module `talvo.paper` exposes `Paper`.

## `talvo.paragraph`

The module `talvo.paragraph` exposes `DOUBLE`, `FixedSpacing`, `Paragraph`, `ParagraphBase`, `ParagraphStyle`, `ProportionalSpacing`, `SINGLE`, `STANDARD`, `TabStop`, `TabStopList`.

`DefaultSpacing` is also importable from this module.

## `talvo.reference`

The module `talvo.reference` exposes `DOCUMENT_AUTHOR`, `DOCUMENT_SUBTITLE`, `DOCUMENT_TITLE`, `Field`, `NUMBER_OF_PAGES`, `Note`, `NoteMarkerBase`, `NoteMarkerByID`, `NoteMarkerWithNote`, `PAGE_NUMBER`, `Reference`, `ReferenceField`, `ReferenceStyle`, `SECTION_NUMBER`, `SECTION_TITLE`.

## `talvo.strings`

The module `talvo.strings` exposes `StringField`, `Strings`.

## `talvo.structure`

The module `talvo.structure` exposes `Admonition`, `AdmonitionFlowables`, `Heading`, `List`, `ListItem`, `ListItemLabel`, `ListOfEntry`, `Section`, `TableOfContents`, `TableOfContentsEntry`, `TableOfContentsSection`, `TableOfContentsStyle`.

## `talvo.style`

The module `talvo.style` exposes `NEXT_STYLE`, `PARENT_STYLE`, `StyleSheet`, `StyleSheetFile`, `StyledMatcher`.

## `talvo.styleds`

The module `talvo.styleds` exposes `IndexEntry`.

## `talvo.stylesheets`

The module `talvo.stylesheets` exposes `sphinx_article`.

## `talvo.table`

The module `talvo.table` exposes `ListOfTables`, `Table`, `TableBody`, `TableCell`, `TableCellBackground`, `TableCellBorder`, `TableCellStyle`, `TableHead`, `TableRow`, `TableStyle`, `TableWithCaption`, `TableWithCaptionStyle`.

## `talvo.template`

The module `talvo.template` exposes `BodyPageTemplate`, `ContentsPartTemplate`, `DocumentTemplate`, `FixedDocumentPartTemplate`, `TemplateConfigurationFile`.

## `talvo.templates`

The module `talvo.templates` exposes `Article`, `Book`.

## `talvo.text`

The module `talvo.text` exposes `MixedStyledText`, `NoBreakAfter`, `SingleStyledText`, `StyledText`, `Subscript`, `Superscript`, `TextStyle`.

## `talvo.warnings`

The module `talvo.warnings` exposes `TalvoWarning`.

## `talvo.templates.article.ArticleBodyPageTemplate`

`ArticleBodyPageTemplate(**options)` is importable from `talvo.templates.article` as a page declaration for article subclasses. It accepts `page_size` as a paper object and `left_margin`, `right_margin`, `top_margin` and `bottom_margin` as lengths.

## `talvo.fonts.adobe14.courier`

`courier` is the supplied typeface object in `talvo.fonts.adobe14`. Its `fonts()` method returns an iterable of font objects accepted by `Typeface`.

## `talvo.frontends`

Resource distributions written for this product declare entry points in the groups `talvo.frontends`, `talvo.templates`, `talvo.stylesheets` and `talvo.typefaces`. Each declaration exchanges a registered resource name and an import reference `<module>:<object>`.

A frontend resource is a reader class exposing `extensions` and `parse`; a template resource is a document-template class; a style-sheet resource is a style-sheet object; a typeface resource is a typeface object. These resources are selectable by their registered names through the respective command-line options and public typeface parsing interface.

## `talvo.frontend`

The module `talvo.frontend` exposes `Reader`.

## `talvo.templates.article`

The module `talvo.templates.article` exposes `ArticleBodyPageTemplate`.

## `talvo.fonts.adobe14`

The module `talvo.fonts.adobe14` exposes `courier`.

## `docutils.io.InputError`

`docutils.io.InputError` is the exception class exposed by the structured-input reader interface for unavailable source input.

## `pygments.style.Style`

The style argument of `pygments_style_to_stylesheet` accepts a subclass of `pygments.style.Style` declaring a `styles` mapping. Its keys are token-category objects and its values are style-description strings, including hexadecimal color strings. The exchanged categories are `Comment`, `Keyword`, `Name`, `Number` and `String`, imported from `pygments.token`.

## `talvo.paragraph.DefaultSpacing`

`DefaultSpacing()` returns a line-spacing object accepted by `ParagraphStyle(line_spacing=...)`.

## `talvo.paragraph.Leading`

`Leading(leading)` accepts a physical length and returns a line-spacing object accepted by `ParagraphStyle(line_spacing=...)`.
