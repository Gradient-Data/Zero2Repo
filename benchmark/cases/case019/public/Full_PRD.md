# Document Publishing Product Requirements

The product is a batch document processor and a programmatic PDF library. It turns structured content into typeset PDF documents whose appearance is controlled by style sheets and document templates.

### FP-01: Physical dimensions and colors

- Accept physical lengths in points, picas, inches, millimeters and centimeters, and compare or combine equivalent lengths independently of their chosen unit. An inch is 72 points or 25.4 millimeters, a pica is 12 points, and a centimeter is ten millimeters. Lengths can be added, subtracted, negated, multiplied by a scalar and divided by a nonzero scalar. A numeric length with no explicitly selected unit is measured in points.

- Callers can increase or decrease a length after composing a length expression; obtaining the expression's value again reflects that change. A numeric increment uses the changed length's unit. Relative lengths expressed as percentages, halves or quarters produce the corresponding fraction of a caller-supplied reference length. Relative content widths use the available containing width as their reference.

- Read signed decimal physical lengths and relative lengths expressed as percentages, halves or quarters. Textual lengths with an unknown unit, or a nonzero magnitude with no unit, are refused as malformed lengths. A textual zero can omit its unit.

- Accept and expose red, green and blue color components and optional opacity, each ranging from zero to one inclusive. Omitted opacity is one. A component outside that range is refused as an invalid color. A gray shade supplies the same caller-selected brightness to all three color components. Read hexadecimal colors with optional opacity. Each component uses either one hexadecimal digit throughout or two digits throughout; hexadecimal letter case does not affect the value. One-digit components represent their digit value divided by 15, and two-digit components represent their byte value divided by 255. Malformed descriptions are refused as invalid colors.

### FP-02: PDF document production

- Given caller-supplied plain-text paragraphs and a page arrangement, produce a readable PDF containing those paragraphs in their supplied order. Callers can supply content programmatically without first writing a markup document.

- Deliver the PDF to a caller-selected file destination. A request supplying no output destination is refused as incomplete.

- Preserve a supplied document title and author in the PDF's document properties, using their textual content when they contain styled text.

### FP-03: Resource discovery and selection

- List the available input formats, installed document templates, installed style sheets and installed typefaces. The listings identify the resources available in the current installation, including resources supplied by additional installed distributions.

- Installed input readers, templates, style sheets and typefaces can be selected by their registered names. Installing another compatible resource makes it discoverable and selectable without changing document content.

- Typeface listings distinguish the available weights, slants and widths within each installed family.

- For a selected installed input format, list its configurable reader options with their accepted value types and defaults. A format with no configurable options is distinguishable from one that has options.

### FP-04: Fonts and typographic features

- Render text with caller-supplied OpenType, TrueType and Type1 fonts, and allow selection of an available face by its typeface, weight, slant and width. Characters represented by the selected font retain their corresponding glyphs, including non-Latin characters.

- Provide the built-in typefaces Courier, Helvetica, Times, Symbol and ITC ZapfDingbats. Callers can assemble a named typeface from supplied font faces.

- For uniformly styled text in fonts containing kerning pairs or ligatures, enabling the corresponding typographic feature applies the font's pair spacing or combined glyphs to eligible text; disabling it preserves ordinary spacing or separate glyphs. Kerning and ligatures are enabled by default. Small capitals and old style figures use the corresponding font variants when those variants exist.

- A direct request for a character absent from the requested font's ordinary glyph repertoire fails as a missing glyph.

- A Google Fonts family providing downloadable static TrueType or OpenType faces can be selected by its family name. When the service is reachable and those faces are available, obtain them and use them to render the document. Previously obtained families remain usable without another download.

- Text can use additional character spacing of a caller-selected physical length, including negative lengths that tighten spacing. The default adds no extra spacing.

- Font-face choices distinguish upright, oblique and italic slants, and nine widths: ultra-condensed, extra-condensed, condensed, semi-condensed, normal, semi-expanded, expanded, extra-expanded and ultra-expanded. The widths have integer classes one through nine in that order. Numeric font weights are integers from zero to 1000 inclusive. Textual face choices outside these supported slants, widths or weight range are refused as invalid font choices.

- If a requested face is unavailable within a nonempty selected family, use another available face from that family and warn that the requested face has been substituted. The warning distinguishes the requested face from the selected face.

### FP-05: Style selection and inheritance

- Apply caller-defined style rules to document elements selected by element type, style label, attributes, direct parent or more distant ancestor context. Rules can target inline text separately from surrounding block content.

- Higher selector priority takes precedence over specificity; ordinary selectors have priority zero. At equal priority, more matching style-label constraints take precedence; if those counts are equal, more matching ordinary attribute constraints take precedence over element-type constraints. With otherwise identical constraints, an exact element type outranks a broader type, and additional matching ancestor constraints increase specificity.

- A style sheet can extend another style sheet. A derived definition overrides the properties it supplies and retains the remaining properties of the corresponding base definition. A caller can instead reset that definition to the element's default style.

- Styles can inherit properties from a named base style. Inline text inherits unspecified properties from its containing text or paragraph; block elements do not inherit their parent's properties unless parent inheritance is explicitly selected for compatible element types. An explicitly selected lower-priority matching style supplies properties left unspecified by the higher-priority rule.

- Style variables supply reusable property values. Redefining a variable in a derived style sheet changes every inherited definition that refers to that variable, while literal property values retain their specified values.

- Load style sheets from caller-supplied files or select the included book and article styles, each available with either TeX Gyre text faces or PDF core text faces. The TeX Gyre versions use Pagella for serif text, Heros for sans-serif text and Cursor for monospaced text; the PDF core versions use Times, Helvetica and Courier for those respective roles. Relative references to a base style sheet are resolved relative to the style sheet containing the reference.

- Styling can set text size and color, block margins and padding, border width and color, and background color. Per-side borders and nonzero per-side padding override the corresponding general border or padding setting. An omitted per-side padding or a directly supplied numeric zero retains the general padding. Zero-valued physical-length objects are outside this zero-padding guarantee. Marking an element hidden removes its rendered content; an explicitly hidden list label leaves the item body visible.

- A style report identifies the document elements, the styles that matched them and which matching styles were selected, so competing matches and inherited styles can be distinguished for a particular element.

### FP-06: Document language and reusable text

- Select English, French, Italian, Dutch, German, Polish, Czech, Spanish or Hungarian as the document language. Generated chapter labels and admonition titles use the selected language. Descriptive section references are localized in English and Dutch. English is the default document language.

- Caller-defined replacements for standard document strings take precedence over the selected language's strings. Callers can also define reusable custom strings and insert their text into document content and page decorations.

### FP-07: Text, sections and structured blocks

- Lay out paragraphs as lines within the available text width, retaining the input's text and inline emphasis, strong emphasis, literal text, superscripts and subscripts. Nested inline styles combine their independently specified properties.

- Support left, right, centered and justified paragraph alignment, first-line indentation and caller-selected line spacing. Explicit tab stops position subsequent text with left, right or centered alignment at the selected stop.

- Preserve explicit line breaks and indentation in literal blocks and line blocks. Ordinary paragraph source line breaks act as spaces. In text supplied directly to paragraphs or styled text through the Python interface, a newline character starts a new line and a tab character moves the following text to the next tab stop. A nonbreaking space keeps the words on either side together when the combined text fits an otherwise empty line.

- When hyphenation is enabled and a dictionary exists for the selected hyphenation language, uniformly styled words can break at that language's permitted hyphenation positions. Hyphenation is enabled by default and uses American English unless a different hyphenation language is selected. The configured minimum number of characters on each side of a hyphen is respected; its default is two characters. Disabling hyphenation prevents these discretionary word breaks.

- Represent nested sections with their headings and preserve the order and nesting of their body content. Bulleted lists, enumerated lists and definition lists preserve item order and nesting, and visually separate labels or terms from their bodies.

- Render block quotations, field lists, option lists, horizontal rules and admonitions as distinct structured blocks. Admonitions retain their body and supplied title, with either an inline title or a separate title according to the selected style.

- For code blocks with a recognized source language and syntax-highlighting support available, apply the chosen highlighting style to language tokens while preserving the code's text, indentation and line breaks.

- Inline glossary terms can display a supplied definition at their first occurrence, at every occurrence or never; the default is the first occurrence. A later conflicting definition of the same term produces a warning and retains the first definition. A term requiring a definition that has not been supplied produces a warning identifying the term and still displays the term itself.

- Line spacing can follow the font's recommended spacing, a caller-selected multiple of the largest text size on each line, a fixed distance between baselines, or a fixed gap between successive lines' text bounds. The supplied proportional presets use one, 1.2 or two times the largest text size. Fixed baseline spacing can enforce a selected minimum to avoid overlap, and by default its minimum is the largest text size on the line. For OpenType and TrueType text, recommended spacing and text bounds use the font's typographic ascent, descent and line gap defined by OpenType Specification 1.9, scaled from font units to the selected text size. A line's top is its baseline minus the greatest ascender among its spans; its bottom is its baseline minus the lowest descender among its spans. Recommended spacing places the next line's top one next-line maximum font line gap below the preceding line's bottom. A fixed text-bound gap places those same bounds the caller's distance apart, independently of the characters' ink shapes.

- Styles can insert caller-supplied styled text before and after a paragraph's content or an inline text element. The inserted text appears in that order and retains its own styling.

- A caller-selected list of words can prevent line breaks immediately after matching words, keeping each with its following word when the combined text fits an empty line. An explicitly empty list disables this word-based protection.

### FP-08: Page geometry and content flow

- Set page width, height, portrait or landscape orientation, margins, body-column count and spacing between columns. Page dimensions and content positions in the PDF reflect these choices. A landscape page exchanges the configured paper width and height.

- Offer A0, A1, A2, A3, A4, A5, A6, A7, A8, A9 and A10 paper sizes using the trimmed dimensions for the selected A-series size in ISO 216:2007. Also offer letter at 8.5 by 11 inches, legal at 8.5 by 14 inches, junior legal at 8 by 5 inches, ledger at 17 by 11 inches and tabloid at 11 by 17 inches, as well as caller-specified dimensions. The default paper is A4 in portrait orientation.

- Content exceeding a column's available height continues in the next column and then on subsequent pages in reading order. For text that fits individual lines and pages, continuation preserves the content without duplication or omission.

- An explicit page break starts following content on a new page. A left-page or right-page break starts it on the requested side, inserting an empty page when necessary. A keep-with-next setting keeps a block with its following block when their combined content fits a fresh page or column.

- A paragraph can require a minimum number of its lines to remain in the current page or column when it must continue elsewhere. If fewer than that minimum fit the remaining space, move that portion to the next area, provided the minimum fits a fresh area. By default no minimum is imposed.

- Repeated page headers and footers display caller-supplied content outside the body. Distinct left, right and chapter-opening page settings change the corresponding pages' decorations and chapter-title placement.

- Callers can select and reorder document parts and omit parts. Empty parts configured for omission contribute no pages. Callers can place additional content at a selected position in an existing named part.

- Each document part can restart page numbering with a selected numbering format or continue the preceding part's numbering. A required ending page side introduces the blank page needed to make the next part start on the opposite side.

### FP-09: Numbering, references and links

- Automatically number section headings and numbered paragraphs in document order, with configurable enclosing-section prefixes and restarting at a selected section level. Suppressed numbering leaves the heading or paragraph content visible. Caller-supplied custom labels replace automatic labels when custom-label use is enabled in the style; otherwise automatic numbering remains in effect.

- Automatic numbering sequences begin at one. Number labels support decimal numbers, lowercase or uppercase alphabetic numbering, lowercase or uppercase Roman numerals, repeating footnote symbols, and no numbering. Alphabetic labels use nonempty Latin-letter strings ordered first by length and then alphabetically. Footnote symbols follow the order asterisk, dagger, double dagger, section sign, double vertical line, pilcrow and number sign; each subsequent cycle adds one repetition of the selected symbol. Prefix and suffix text surround the resulting label when supplied.

- References to identified document elements can display their descriptive reference, number, title, page number or caller-supplied reference text. Forward and backward references resolve to the referenced content and its final page location. Internal reference links navigate to the target when linking is enabled.

- A reference to an unknown target or requesting information absent from its target, without custom replacement text or quiet handling, emits a warning identifying the target and the unavailable information, and displays an unresolved-reference indication. Quiet handling suppresses both the warning and unresolved text. Supplied replacement text suppresses the warning and takes precedence over quiet handling. By default, quiet handling is disabled and internal reference linking is enabled.

- External hyperlinks retain their supplied destination and clickable text or image region in the PDF.

- Dynamic text can display the current page number, the total page count of the current numbering sequence, the document title, subtitle and author, and the current section's title or number at a requested level. The displayed page and section information follows the page on which the text appears. Missing document metadata contributes no text.

### FP-10: Images, figures and drawing

- Embed PNG and JPEG images, and PDF pages with a single content stream, in document content, preserving the source image's appearance, transparency and embedded color profile where present. Images can appear as standalone blocks, inline with text or as page backgrounds. A page background image is placed at the top of the page, aligned with the page's left edge.

- Honor explicit image width and height; specifying only one preserves the original aspect ratio. A scale factor multiplies the intrinsic dimensions, and caller-specified resolution overrides embedded resolution. Raster images without resolution information use 72 pixels per inch to determine their intrinsic size.

- An image can be rotated by the caller's angle in degrees; a positive angle turns it counter-clockwise as seen on the page. Proportional fitting keeps it within the available width and height; proportional filling covers that area. Combining explicit dimensions with a non-unit scale factor or an explicit resolution is refused as conflicting sizing instructions.

- Figures display their image content, caption and legend in order. Numbered captions give figures referenceable labels. Without an enclosing section, default caption numbering is decimal. Figures can stay in the body, float above body content or occupy sideways pages, according to the selected placement.

- An image file that cannot be opened makes rendering unsuccessful and identifies the unavailable image. Any resulting document displays the supplied alternative text, or a visible image-error indication when no alternative text was supplied.

- Caller-supplied lines, polygons and rectangles appear with the requested geometry, stroke width, stroke color and fill color. Omitting a stroke or fill suppresses that part of the drawing while retaining the other requested part.

### FP-11: Tables and tabular pagination

- Render tables with optional header rows, body rows and cells spanning multiple rows or columns. Preserve the cells' content and spans, including empty cells and block content within cells. Tables consisting only of header rows remain renderable.

- Accept fixed and automatic column widths, including combinations of both when automatic columns precede the other columns. Proportional sizing supports tables with at least two proportionally sized columns, optionally alongside fixed columns or leading automatic columns. Fixed widths retain their supplied physical sizes, proportional columns share their allocated width in the supplied ratios, and automatic columns accommodate their content within the available width when that content can fit. An explicit list of widths with a different length from the table's column count is refused as inconsistent table sizing.

- Apply table and cell borders, backgrounds, padding and top, middle or bottom vertical cell alignment. Column widths and text wrapping determine cell heights so content within a row fits its allocated cells when the requested widths permit it.

- With no row minimum imposed, tables whose body extends beyond a page continue across pages without dropping or duplicating body rows, provided each inseparable row span and any repeated header fit the available table area on a fresh page. Repeating headers, when enabled, reproduce the header on continuation pages. For a table of unspanned body rows that fits on one fresh page, a positive split minimum prevents an initial split leaving either portion with fewer body rows than that minimum; the table moves intact to the next page instead. By default, no row minimum is imposed and headers are not repeated.

- A captioned table can be numbered and referenced, and can occupy a sideways page while retaining its caption and cell content.

- Fixed column widths whose sum exceeds the available table width produce an over-width warning. Automatic sizing that cannot fit the cell contents within the available width produces a warning identifying the table as too wide.

### FP-12: Footnotes and citations

- A note marker identifies its note and links to the note text. Automatically numbered notes receive labels in reference order, while explicitly supplied note labels are retained.

- Notes configured for footer placement appear at the bottom of the page containing their first reference, with space reserved so body text does not overlap them, provided the note fits that page's note area. Repeated references to the same note on that page do not duplicate its text.

- Notes configured for in-place placement display their labeled text at their location in the document body. Citation references resolve to their supplied citation labels and corresponding citation bodies; citation style can select body or footer placement.

### FP-13: Contents and document navigation

- Generate a table of contents from the document's section hierarchy in document order, including heading text, available numbering and final page references. A requested maximum depth limits included levels; the default depth is three section levels. Sections explicitly excluded from the table of contents or hidden from rendering, and their descendant sections, are omitted.

- A local table of contents inside a section lists that section's descendants within the selected depth rather than unrelated sections elsewhere in the document. The containing section counts as the first depth level.

- Generate lists of figures and tables from their numbered captions, retaining document order and references to their final locations.

- The PDF outline reflects the hierarchy of section headings eligible for the table of contents and navigates to their locations. Outline entries retain heading titles and available numbering.

### FP-14: Alphabetical indexes

- Collect supplied index terms into an alphabetical index with references to the pages of their marked occurrences. Repeated occurrences of a term share an index entry, and nested terms appear beneath their parent terms.

- Sort index terms alphabetically without giving letter case precedence over the letters themselves. When initial grouping is enabled, alphabetic entries are grouped by their initial letter and entries beginning with nonletters are grouped separately. Initial grouping is enabled by default.

- Index entries can carry see and see-also references to supplied term text, including entries that have no page occurrence of their own. Preserve multiple supplied cross-references and distinguish see references from see-also references.

### FP-15: Mathematical notation

- With mathematical rendering support installed, render LaTeX mathematical expressions both inline and as display equations. Fractions, roots, summations, Greek letters, superscripts and subscripts retain their mathematical arrangement, and inline expressions align with the surrounding text's baseline.

- Equation styling controls the displayed text size and color. Display equations can receive automatic number labels and serve as internal reference targets.

- When mathematical rendering support is absent, requesting equation content produces a warning identifying the missing capability and omits the equation artwork.

### FP-16: Document templates and configuration

- Provide article and book templates. The article uses the included article style with TeX Gyre text faces by default, places supplied title, subtitle and author above the body on its opening page, uses a continuous decimal page sequence, and allows the abstract either in the title area or in the body. The title area is the default abstract location and spans the body columns.

- The book template uses the included book style with TeX Gyre text faces by default and provides title pages, front matter, body and back matter. Front matter contains the table of contents and nonempty lists of figures and tables, with lowercase Roman page numbers. The body restarts with decimal page numbers, and back matter continues the body's numbering and contains the index when index terms exist.

- Template configuration can override page geometry, page decorations, language, standard strings and the style sheet. A configuration can extend another, retaining inherited settings except where overridden. Shared configuration variables affect every setting that refers to them. Relative references to base configurations and style sheets are resolved relative to the referring configuration.

- Specific left-page or right-page settings take precedence over the corresponding general page settings. Callers can define custom templates with their own document parts, content and page arrangements, and render documents using those templates.

- Unsupported programmatic template options are refused as invalid configuration. A configuration referring to a nonexistent part or page template is refused as an unknown template component.

### FP-17: Structured document input

- Read reStructuredText documents from a file or a text stream and preserve headings, paragraphs, inline markup, lists, quotations, literal blocks, field lists, option lists and admonitions as corresponding document content. A top-level document title, subtitle, author information and abstract become document metadata used by the selected template.

- Translate reStructuredText tables, images, figures, footnotes, citations, hyperlink targets, references, contents directives and inline or display mathematics into their corresponding rendered document features. Relative image and included-document references are interpreted from the source document's location.

- Read CommonMark documents from a file or a text stream, preserving headings, paragraphs, emphasis, strong emphasis, inline code, fenced code blocks, block quotations, ordered and unordered lists, links, images and thematic breaks in the resulting document.

- Callers can obtain the parsed structured content and then select its document template and style sheet independently. File input is read as UTF-8; a source file that cannot be opened fails as unavailable input.

### FP-18: Command-line rendering and resource discovery

- Render a selected input document to PDF using an explicitly selected input format or the format associated with its recognized filename extension. The built-in input formats are reStructuredText and CommonMark. Explicit format selection takes precedence over the filename extension. An unrecognized extension is treated as reStructuredText and the assumed format is reported. An explicitly requested unknown format is refused as unsupported.

- Callers can select the document template, a template configuration, the style sheet, paper size and output destination. The default template is article. Explicit command-line style sheet and paper choices override choices inherited from the template configuration.

- Missing input files, unavailable requested style sheets or templates, malformed paper sizes, unsupported reader options and invalid reader-option values that can be lexically parsed cause unsuccessful conversion identifying the offending choice. For a lexically malformed reader-option value, unsuccessful conversion includes a diagnostic but need not identify the option. A render that reports image errors remains an unsuccessful conversion even if a PDF was produced.

- Produce a PDF font specimen that displays the available installed font faces using those faces when they support the specimen text, so the rendered appearance can be associated with the corresponding typeface and face style.

- When automatic resource installation is explicitly enabled and rendering needs an uninstalled typeface distributed through PyPI, obtain the available typeface and complete rendering with it. Without installation permission, an unavailable required resource causes unsuccessful conversion identifying that resource; an unsuccessful installation does not count as successful conversion. Resource acquisition honors the caller-selected package index, installation destination, HTTPS proxy and trusted certificate authorities.

### FP-19: Sphinx project publishing

- Build PDF documents from a Sphinx project, combining each configured root document with the documents referenced by its table-of-contents trees. Multiple configured targets produce separate PDFs. The default template is book.

- A target can include only the documents referenced by its root, omitting the root's own body content. A selected subset of targets restricts which PDFs are produced; other configured targets are not rendered.

- Per-document configuration can override title, subtitle, author, date, logo and template. Ordinary source document information fields for title and author are not imported into the assembled document; source dates are discarded. For title, subtitle and author absent from the assembled document and the per-document configuration, derive a documentation title from the project name, a release subtitle from the project release, and author from the project settings. The date comes from the per-document configuration or, when absent there, the project build date. When no build date is configured, use the current date. Additional supplied metadata remains available to custom templates.

- Resolve links between source documents into links within the assembled PDF, and retain Sphinx object descriptions, signatures, parameter descriptions, code listings, admonitions and glossary definitions. General index entries and domain-specific indexes can be included; domain-specific indexes are enabled by default and can be disabled per target.

- When the dedicated PDF document list is absent or empty, accept the project's LaTeX document configuration as its PDF target definitions. A nonempty dedicated PDF document list takes precedence.

- A target definition lacking its root document or output target is refused as incomplete configuration. An unknown root document is reported and excluded from publishing. An unknown selected target is reported and creates no document for that target. With no configured documents, report that condition and produce no PDFs.

- With graph rendering support configured and available, publish graph descriptions embedded in a Sphinx document as diagrams retaining their nodes, edges, direction and labels.
