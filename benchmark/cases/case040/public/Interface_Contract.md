# Interface Contract

Import the Python package as `velnora`. Its public submodules are importable by their dotted paths. Calls exchange Python objects; terminal display output uses the configured terminal stream, and CGI response output uses `stdout`.

In signatures, `...` marks an optional argument without supplying its value. Key names are strings: `up`, `down`, `left`, `right`, `page up`, `page down`, `home`, `end`, `insert`, `delete`, `backspace`, `tab`, `enter`, and `esc`; function keys use `f{number}`. Modifier prefixes are space-separated `shift`, `ctrl`, `meta`, `super`, and `hyper`. Resize uses `window resize`; paste-boundary keys are `begin paste` and `end paste`.

## `velnora.set_encoding`

`velnora.set_encoding(encoding)` accepts an encoding-name string and configures the output encoding.

## `velnora.util.get_encoding`

`velnora.util.get_encoding()` returns the selected encoding-name string.

## `velnora.set_ascii_fallbacks`

`velnora.set_ascii_fallbacks(fallbacks)` accepts a mapping from character strings to replacement character strings. Registration failures use `ValueError` for invalid character entries or `TypeError` for invalid entry types.

## `velnora.get_ascii_fallbacks`

`velnora.get_ascii_fallbacks()` returns a mapping from character strings to replacement character strings.

## `velnora.apply_target_encoding`

`velnora.apply_target_encoding(s)` and `velnora.util.apply_target_encoding(s)` accept `str` or `bytes`. The result is `(encoded_bytes, charset_runs)`: bytes followed by a list of `(charset, byte_length)` pairs. A charset is `None` for ordinary text or `"0"` for DEC graphics.

Bytes labeled with charset `"0"` use the DEC Special Graphics character-set encoding.

The DEC graphic byte-to-character mapping is: `_` ▮, grave accent ◆, `a` ▒, `b` ␉, `c` ␌, `d` ␍, `e` ␊, `f` °, `g` ±, `h` ␤, `i` ␋, `j` ┘, `k` ┐, `l` ┌, `m` └, `n` ┼, `o` ⎺, `p` ⎻, `q` ─, `r` ⎼, `s` ⎽, `t` ├, `u` ┤, `v` ┴, `w` ┬, `x` │, `y` ≤, `z` ≥, `{` π, `|` ≠, `}` £, `~` ·.

## `velnora.trim_text_attr_cs`

`velnora.util.trim_text_attr_cs(text, attr, cs, start_col, end_col)` accepts bytes, attribute runs, charset runs, and integer column boundaries. Runs are sequences of `(tag, byte_length)` pairs. Its tuple result starts with the trimmed bytes.

## `velnora.calc_width`

`velnora.calc_width(text, start_offs, end_offs)` accepts `str` or `bytes` and integer offsets. It returns an integer screen-column width. Text offsets index code points for `str` and bytes for `bytes`.

## `velnora.calc_text_pos`

`velnora.calc_text_pos(text, start_offs, end_offs, pref_col)` accepts `str` or `bytes` and integer offsets and a requested column. It returns a pair `(text_offset, actual_column)` of integers. Text offsets index code points for `str` and bytes for `bytes`.

## `velnora.move_next_char`

`velnora.move_next_char(text, start_offs, end_offs)` accepts `str` or `bytes` and integer offsets. It returns an integer text offset. Text offsets index code points for `str` and bytes for `bytes`.

## `velnora.move_prev_char`

`velnora.move_prev_char(text, start_offs, end_offs)` accepts `str` or `bytes` and integer offsets. It returns an integer text offset. Text offsets index code points for `str` and bytes for `bytes`.

## `velnora.Sizing`

`velnora.Sizing` exposes the sizing members `BOX`, `FLOW`, and `FIXED`. Widget `sizing()` returns a set or frozenset of these members.

## `velnora.Sizing.BOX`

`velnora.Sizing.BOX` is the `BOX` sizing member.

## `velnora.Sizing.FLOW`

`velnora.Sizing.FLOW` is the `FLOW` sizing member.

## `velnora.Sizing.FIXED`

`velnora.Sizing.FIXED` is the `FIXED` sizing member.

## `velnora.BOX`

`velnora.BOX` is the box-sizing member exposed by the package.

## `velnora.Widget`

`velnora.Widget()` is subclassable. Subclasses declare `_sizing` as a frozenset of sizing members and `_selectable` as a boolean; `_invalidate()` is the subclass notification entry. `sizing()` returns a set of sizing members and `selectable()` returns a boolean.

The widget call protocol is `render(size, focus=...) -> Canvas`, `rows(size, focus=...) -> int`, and `pack(size, focus=...) -> (columns, rows)`. Sizes are tuples: `()` for fixed sizing, `(columns,)` for flow sizing, and `(columns, rows)` for box sizing. Dimensions are integer screen columns and rows. `focus` is an optional boolean.

Interaction entries are `keypress(size, key)`, `mouse_event(size, event, button, col, row, focus)`, and `get_cursor_coords(size)`. A key is a string; keypress returns `None` for a consumed key or a key string for an unhandled key. Mouse arguments contain an event-name string, integer button, zero-based column and row, and boolean focus; the result is boolean handling status. Cursor results are zero-based `(column, row)` integer pairs or `None`. These signatures are also the overrides supplied by application subclasses.

The sizing, rendering, packing, and row-count signatures above also apply to built-in widgets and widget wrappers.

## `velnora.Canvas`

A rendered canvas exposes `text`, an iterable of byte strings, one per row; `content()`, an iterable of rows of `(attribute, charset, data)` segments; integer `cols()` and `rows()`; and `cursor`, either a zero-based `(column, row)` pair or `None`. Segment `data` is bytes. Each segment attribute and charset applies to its bytes. Attributes are hashable tags or attribute objects, or `None`; charset is `None` or `"0"` for ordinary and DEC graphic text. Attribute objects can be supplied to `resolve_attr`.

## `velnora.TextCanvas`

`velnora.TextCanvas(text, attr=..., cursor=..., maxcol=...)` accepts a list of byte rows, optional per-row lists of `(attribute, byte_length)` pairs, an optional cursor pair, and an integer column count. It returns a canvas exposing `text`, `content()`, `cols()`, `rows()`, and `cursor`.

## `velnora.CompositeCanvas`

`velnora.CompositeCanvas(canv)` accepts a canvas and returns a canvas exposing `text`, `content()`, `cols()`, `rows()`, and `cursor`.

Mutation entries are `pad_trim_left_right(left, right)`, `pad_trim_top_bottom(top, bottom)`, `trim(top, count)`, and `trim_end(end)`, with integer dimensions. The resulting canvas is read through the same public canvas members.

## `velnora.CanvasJoin`

`velnora.CanvasJoin(canvas_info)` accepts an iterable of `(canvas, position, focus, columns)` tuples, with an application position, boolean focus, and integer column count. It returns a canvas.

## `velnora.CanvasCombine`

`velnora.CanvasCombine(canvas_info)` accepts an iterable of `(canvas, position, focus)` tuples, with an application position and boolean focus. It returns a canvas.

## `velnora.CanvasOverlay`

`velnora.CanvasOverlay(top_c, bottom_c, left, top)` accepts two canvases and integer offsets. It returns a canvas.

## `velnora.AttrSpec`

`velnora.AttrSpec(fg=..., bg=..., colors=..., hyperlink=...)` accepts foreground and background description strings, an optional integer color mode, and an optional hyperlink object, target string, or `None`. The color-mode carriers are `1` for monochrome, `16`, `88`, `256`, and `16777216` for true color. Invalid attribute descriptions raise `AttrSpecError`.

Properties `foreground_number` and `background_number` are integer color codes. `foreground_basic` and `background_basic` are booleans. `foreground` and `background` are color-description strings; a foreground description can contain comma-separated effect names. Effect flags `bold`, `faint`, `italics`, `underline`, `blink`, `standout`, and `strikethrough` are booleans. `hyperlink` is a hyperlink object or `None`.

`get_rgb_values()` returns `(foreground_red, foreground_green, foreground_blue, background_red, background_green, background_blue)`. Each component is an integer or `None` for a terminal-default component.

Color-description syntax includes color-name strings, `default`, `inherit`, `h<index>`, `#<rgb>`, `#<rrggbb>`, `g<percent>`. Numeric placeholders are decimal for indices and percentages and hexadecimal for RGB. Foreground effects are comma-separated names; `no-<effect>` denotes an explicitly removed effect.

Integer-intensity grayscale uses `g#<hh>` with hexadecimal digits.

## `velnora.Hyperlink`

`velnora.Hyperlink(uri, id=...)` accepts strings. The resulting `uri` and `id` fields carry the target and link identity. Validation failures raise `ValueError`.

## `velnora.register_signal`

`velnora.register_signal(sig_cls, signals)` accepts an application class and a collection of notification names.

## `velnora.connect_signal`

`velnora.connect_signal(obj, name, callback, user_arg=..., *, weak_args=..., user_args=...)` accepts a source, notification name, callable, optional legacy context, and optional iterables of weak and ordinary context. It returns an opaque connection key. A delivered callback receives positional arguments `(*weak_args, *user_args, *event_data, user_arg)`, with the legacy context slot omitted when no legacy context is supplied. Unsupported notification registration raises `NameError`.

## `velnora.disconnect_signal`

`velnora.disconnect_signal(obj, name, callback, user_arg=..., *, weak_args=..., user_args=...)` accepts the source, notification name, callable, and registration context to disconnect.

## `velnora.disconnect_signal_by_key`

`velnora.disconnect_signal_by_key(obj, name, key)` accepts a source, notification name, and connection key.

## `velnora.emit_signal`

`velnora.emit_signal(obj, name, *args)` accepts a source, notification name, and positional event data. It returns a boolean: `True` means handled and `False` means unhandled. Application listener failures propagate as their original exception objects.

## `velnora.CommandMap`

`velnora.CommandMap()` returns a command mapping. `mapping[key]` accepts a string and returns an action string or string-compatible value, or `None` for an unmapped key. `dict(mapping)` exposes key/action pairs.

The mapping supports `mapping[key] = command`, `del mapping[key]`, `clear_command(command)`, `restore_defaults()`, and `copy()`. `command` is a string or `None`; `copy()` returns a command mapping with the same operations.

`bind(command, *keys)` accepts an action and key strings. A binding conflict is signaled by `ValueError`.

Standard action-name strings are `cursor up`, `cursor down`, `cursor left`, `cursor right`, `cursor page up`, `cursor page down`, `cursor max left`, `cursor max right`, `activate`, `next selectable`, `prev selectable`, `menu`, and `redraw screen`.

Assigning `None` is the single-key removal form.

## `velnora.command_map`

`velnora.command_map` is the package command-mapping instance. It supports `dict(command_map)`, string-key lookup, assignment, deletion, and `restore_defaults()`, using the `CommandMap` interface.

## `velnora.Text`

`velnora.Text(markup, align=..., wrap=..., layout=...)` accepts plain `str` or `bytes` and nested markup: lists of fragments and `(attribute, content)` pairs. Attribute values are hashable palette names, direct attributes, or `None`. `align` uses `left`, `center`, or `right`; `wrap` uses `space` for word wrapping, `any` for character wrapping, `clip` for clipping, and `ellipsis` for omission-marked clipping; `layout` is a text-layout object. Malformed markup raises `TagMarkupException`; invalid layout choices raise `TextError`.

`get_text()` returns `(text, attribute_runs)`. Each run is `(attribute, text_length)`; lengths count code points for Unicode text and bytes for byte text. `set_text(markup)`, `set_align_mode(mode)`, and `set_wrap_mode(mode)` accept replacement markup or a mode string. Invalid mode setters raise `TextError`.

`render(size, focus=...)` returns a canvas. `rows((columns,), focus=...)` returns an integer; `pack(())` and `pack((columns,))` return `(columns, rows)` integer pairs. `sizing()` returns sizing members. An incompatible render size raises `ValueError`.

## `velnora.TextLayout`

`velnora.TextLayout` is subclassable with `layout(text, width, align, wrap)`. Its result is a list of line layouts, each a list of segments. A source-text segment is `(column_width, start_offset, end_offset)`; a space segment is `(space_count, offset_or_None)`. Offsets address the supplied text; a space segment's offset selects its attribute, and `None` means no attribute. A zero-width `(0, text_offset)` segment marks a text position.

## `velnora.StandardTextLayout`

`velnora.StandardTextLayout(tab_stops=..., tab_stop_every=...)` accepts an iterable of integer tab columns and an integer repeating interval, both optional. It is usable as the `layout` argument to `Text` and `Edit`. Invalid tab configuration raises `ValueError`.

## `velnora.ansi_parser.ParsedLine`

Parsing results expose `text` as a string and `attrib` as a list of `(attribute, text_length)` pairs. Attributes are `AttrSpec` objects or `None`; lengths count text characters. Unlisted trailing text has no attribute. `bel` is an integer bell count; `title` is a string or `None`; `leds` is `None` or a state string: `clear`, `scroll_lock`, `num_lock`, or `caps_lock`. `skipped` is a list of operation reports.

## `velnora.ansi_parser.SkippedOp`

Each entry of `skipped` exposes string fields `kind` and `raw`. The `kind` carrier uses `vertical-move` for an unsupported vertical move, `terminal-setting` for an unsupported terminal operation, and `unknown` for an unrecognized or curtailed operation. `raw` carries the reported control-sequence text, including its escape introducer. OSC report text excludes its terminator; length-limited report text can be truncated. `reason` is a human-readable explanation string.

## `velnora.ansi_parser.AnsiParser`

`velnora.ansi_parser.AnsiParser(one_line=...)` accepts an optional boolean mode. `feed(text)` accepts a string chunk; `finalize()` returns a tuple of parsing-result objects.

## `velnora.ansi_parser.parse_ansi_line`

`velnora.ansi_parser.parse_ansi_line(text)` accepts a string and returns a tuple of parsing-result objects.

## `velnora.ansi_parser.parse_ansi_text`

`velnora.ansi_parser.parse_ansi_text(text)` accepts a string and returns one parsing-result object.

## `velnora.ANSIText`

`velnora.ANSIText(ansi_text, one_line=...)` accepts a string and an optional boolean mode. `text` exposes the resolved string and `attrib` its attribute runs `(attribute, text_length)`. `render(size, focus=...)` returns a canvas.

## `velnora.ANSIText.from_lines`

`velnora.ANSIText.from_lines(chunks, one_line=...)` accepts an iterable of string chunks and an optional boolean mode. It returns an iterator of `ANSIText` widgets exposing `text`, `attrib`, and `render`.

## `velnora.AttrMap`

`velnora.AttrMap(w, attr_map, focus_map=...)` accepts a widget, a hashable attribute or attribute mapping, and an optional focus attribute or mapping. `set_attr_map(attr_map)` and `set_focus_map(focus_map)` accept mappings. `render(size, focus=...)` returns a canvas.

## `velnora.Padding`

`velnora.Padding(w, align=..., width=..., min_width=..., left=..., right=...)` accepts a widget; a string alignment or `('relative', percentage)` pair; an integer width, size-mode string, or `('relative', percentage)` pair; optional integer minimum; and integer margins. Size-mode strings used here are `pack` and `clip`. It exposes `render`, `rows`, `pack`, `keypress`, `mouse_event`, and `get_cursor_coords` with widget-protocol signatures. Rejected configuration raises `PaddingError`; an incompatible child sizing request raises `WidgetError`.

Alignment strings are `left`, `center`, and `right`.

## `velnora.Filler`

`velnora.Filler(body, valign=..., height=..., min_height=..., top=..., bottom=...)` accepts a widget, string vertical alignment or `('relative', percentage)` pair, integer height or `('relative', percentage)` pair, optional integer minimum, and integer margins. It exposes `render`, `rows`, `pack`, `keypress`, `mouse_event`, and `get_cursor_coords` with widget-protocol signatures. Rejected configuration raises `FillerError` or `ValueError`. `base_widget` exposes the underlying undecorated widget.

Alignment strings are `top`, `middle`, and `bottom`; natural height uses `pack`.

## `velnora.BoxAdapter`

`velnora.BoxAdapter(box_widget, height)` accepts a widget and an integer row count. `rows((columns,))` returns an integer, `pack((columns,))` an integer dimension pair, and `render((columns,))` a canvas.

## `velnora.LineBox`

`velnora.LineBox(original_widget, title=..., title_align=..., tlcorner=..., tline=..., lline=..., trcorner=..., blcorner=..., rline=..., bline=..., brcorner=...)` accepts a widget and optional strings for the title, corners, and sides; `title_align` is one of `left`, `center` and `right`. `set_title(text)` accepts a replacement title string. `render((columns, rows))` returns a canvas. A refused title raises `ValueError`, from the constructor or from `set_title`.

## `velnora.Divider`

`velnora.Divider(div_char=..., top=..., bottom=...)` accepts a character string and optional integer row counts. `rows((columns,))` returns an integer; `pack((columns,))` returns an integer dimension pair; `render((columns,))` returns a canvas.

## `velnora.SolidFill`

`velnora.SolidFill(fill_char=...)` accepts an optional character string. `sizing()` returns sizing members; `pack((columns, rows))` returns an integer dimension pair; `render((columns, rows), focus=...)` returns a canvas. Incompatible render sizing raises `ValueError`.

## `velnora.WidgetDisable`

`velnora.WidgetDisable(original_widget)` accepts a widget. It exposes `selectable() -> bool`, `keypress(size, key) -> str | None`, `mouse_event(size, event, button, col, row, focus) -> bool`, and `render(size, focus=...) -> Canvas`.

## `velnora.WidgetPlaceholder`

`velnora.WidgetPlaceholder(original_widget)` accepts a widget. `original_widget` is a readable and assignable widget property. It exposes `selectable() -> bool` and the widget entries `render`, `keypress`, and `mouse_event`.

## `velnora.WidgetWrap`

`velnora.WidgetWrap(w)` accepts a widget and can be subclassed. A subclass can override `keypress(size, key) -> str | None`; the superclass exposes that entry as well.

## `velnora.Columns`

`velnora.Columns(widget_list, dividechars=..., min_width=..., *, select_navigation=...)` accepts a child iterable, optional integer gap and minimum width, and an optional boolean navigation setting.

Child declarations are a widget, `(amount, widget)`, `('pack', widget)`, `('given', amount, widget)`, or `('weight', amount, widget)`. `amount` is numeric; the two-element form is the given form, so `(amount, widget)` and `('given', amount, widget)` declare the same allocation. `contents` is a mutable sequence of `(widget, options)` pairs supporting indexing, replacement, append, deletion, and `len`.

`options(width_type, width_amount)` also accepts omitted arguments and returns an option tuple suitable for `contents`. Its size-kind strings are `pack`, `given`, and `weight`. Invalid allocation declarations raise `ColumnsError`.

`focus_position` is a readable and assignable integer position; `focus` is the corresponding widget or `None`. `get_focus_path()` returns a list of nested positions. Invalid focus assignments raise `IndexError`.

The widget entries `render`, `keypress`, and `mouse_event` use the widget protocol. `select_navigation` is a readable and assignable boolean.

`rows((columns,), focus=...)` returns an integer.

## `velnora.Pile`

`velnora.Pile(widget_list, focus_item=..., *, select_navigation=...)` accepts a child iterable, an optional initial focus index, and an optional boolean navigation setting.

Child declarations are a widget, `(amount, widget)`, `('pack', widget)`, `('given', amount, widget)`, or `('weight', amount, widget)`. `amount` is numeric; the two-element form is the given form, so `(amount, widget)` and `('given', amount, widget)` declare the same allocation. `contents` is a mutable sequence of `(widget, options)` pairs supporting indexing, replacement, append, deletion, and `len`.

`options(height_type, height_amount)` also accepts omitted arguments and returns an option tuple suitable for `contents`. Its size-kind strings are `pack`, `given`, and `weight`. Invalid allocation declarations raise `PileError`.

`focus_position` is a readable and assignable integer position; `focus` is the corresponding widget or `None`. `get_focus_path()` returns a list of nested positions. `base_widget` exposes the underlying undecorated widget. Invalid focus assignments raise `IndexError`.

The widget entries `render`, `keypress`, `mouse_event`, and `get_cursor_coords` use the widget protocol. `select_navigation` is a readable and assignable boolean.

`rows((columns,), focus=...)` returns an integer; `sizing()` returns sizing members.

## `velnora.GridFlow`

`velnora.GridFlow(cells, cell_width, h_sep, v_sep, align, *, select_navigation=...)` accepts a child iterable, integer cell width and gaps, and a string row alignment or a `("relative", percentage)` pair, with an optional boolean navigation setting.

`contents` is a mutable sequence of `(widget, options)` pairs. `options(width_type, width_amount)` accepts the `given` size-kind string and an integer cell width, returning a tuple suitable for `contents`.

`focus_position` is a readable and assignable integer position. Invalid focus assignments raise `IndexError`.

The widget entries `render`, `keypress`, and `mouse_event` use the widget protocol. `select_navigation` is a readable and assignable boolean.

## `velnora.Frame`

`velnora.Frame(body, header=..., footer=..., focus_part=...)` accepts a body widget, optional header and footer widgets, and a string initial focus region.

`header`, `body`, and `footer` expose the region widgets; `header` and `footer` can also be `None` and can be assigned. `contents` is a mutable mapping keyed by `header`, `body`, and `footer`, containing `(widget, options)` pairs. `options()` returns the options value for these entries. Invalid initial focus configuration raises `ValueError`.

`focus_position` is a readable and assignable position; `focus` is the corresponding widget or `None`. `get_focus_path()` returns a list of nested positions and `set_focus_path(positions)` accepts such a list. Invalid focus assignments raise `IndexError`.

The widget entries `render`, `keypress`, and `mouse_event` use the widget protocol. `select_navigation` is a readable and assignable boolean.

## `velnora.Edit`

`velnora.Edit(caption=..., edit_text=..., multiline=..., wrap=..., allow_tab=..., edit_pos=..., layout=..., mask=..., *, expand_tabs=...)` accepts optional caption markup, editable string, boolean editing settings, wrapping string, integer cursor offset, layout object, and string mask or `None`. `caption` and `edit_text` expose strings; `edit_pos` exposes an integer text offset.

`set_edit_text(text)`, `set_edit_pos(pos)`, and `set_mask(mask)` accept a string, integer offset, and string or `None`, respectively. `render(size, focus=...)` returns a canvas and `get_cursor_coords(size)` returns coordinates. `keypress` and `mouse_event` use the widget protocol.

Notification `change` calls `callback(editor, proposed_text)`; `postchange` calls `callback(editor, previous_text)`. Both payload texts are strings.

## `velnora.IntEdit`

`velnora.IntEdit(caption=..., default=...)` accepts optional caption markup and an integer, string, or `None` initial value. It exposes `edit_text`, `edit_pos`, `set_edit_text`, `set_edit_pos`, and `keypress` through the editor interface. `value()` returns an integer; invalid numeric conversion raises `ValueError`.

## `velnora.numedit.IntegerEdit`

`velnora.numedit.IntegerEdit(caption=..., default=..., base=..., *, allow_negative=...)` accepts optional caption markup; integer, string, `decimal.Decimal`, or `None` initial value; integer base; and boolean sign setting. It exposes the editor entries `edit_text`, `edit_pos`, `set_edit_text`, `set_edit_pos`, and `keypress`. `value()` returns a `decimal.Decimal` or `None`. Invalid initialization and conversion raise `ValueError`.

## `velnora.numedit.FloatEdit`

`velnora.numedit.FloatEdit(caption=..., default=..., *, preserve_significance=..., decimal_separator=..., allow_negative=...)` accepts optional caption markup; string, integer, `decimal.Decimal`, or `None` initial value; boolean significance and sign settings; and a string separator. It exposes the editor entries `edit_text`, `edit_pos`, `set_edit_text`, `set_edit_pos`, and `keypress`. `value()` returns a `decimal.Decimal` or `None`. Invalid initialization raises `ValueError`; invalid numeric conversion raises `decimal.InvalidOperation`.

## `velnora.Button`

`velnora.Button(label, on_press=..., user_data=...)` accepts label markup, an optional callback, and optional application context. `get_label()` returns the label string. `click` listeners receive `(button,)`; an `on_press` callback with supplied context receives `(button, user_data)`. `render` and `keypress` use widget signatures; `mouse_event` returns boolean handling status.

## `velnora.CheckBox`

`velnora.CheckBox(label, has_mixed=...)` accepts label markup and an optional boolean cycle setting. `state` is a readable and assignable choice-state value; `get_state()` returns that value and `set_state(state, do_callback=...)` accepts a state plus an optional boolean callback setting.

`change` calls `callback(control, proposed_state)` and `postchange` calls `callback(control, previous_state)`. `keypress`, `render`, and `mouse_event` use widget signatures.

States are represented by booleans and the string `mixed`. `set_label(label)` accepts markup and `get_label()` returns a string. Invalid state assignment raises `CheckBoxError`.

## `velnora.RadioButton`

`velnora.RadioButton(group, label)` accepts a mutable list of group members and label markup. `state` is a readable and assignable choice-state value; `get_state()` returns that value and `set_state(state, do_callback=...)` accepts a state plus an optional boolean callback setting.

`change` calls `callback(control, proposed_state)` and `postchange` calls `callback(control, previous_state)`. `keypress`, `render`, and `mouse_event` use widget signatures.

Radio state is exposed as a boolean.

## `velnora.SelectableIcon`

`velnora.SelectableIcon(text, cursor_position=..., wrap=...)` accepts label markup, an optional integer character position, and optional wrapping string. `selectable()` returns a boolean. `render(size, focus=...)` returns a canvas; `keypress(size, key)` uses the widget key return form.

## `velnora.ListWalker`

`velnora.ListWalker` is subclassable. The application provider implements `get_focus() -> (widget, position)`, `set_focus(position)`, `get_next(position) -> (widget, position)`, and `get_prev(position) -> (widget, position)`. An absent neighbor or focus is `(None, None)`. Positions are application-defined objects. `_modified()` is the provider notification entry. A provider can expose `__length_hint__() -> int` for its estimated length.

## `velnora.SimpleListWalker`

`velnora.SimpleListWalker(contents, wrap_around=...)` accepts an iterable of widgets and an optional boolean wrapping setting. `get_focus()`, `get_next(position)`, and `get_prev(position)` return `(widget, integer_position)` or `(None, None)`. `set_focus(position)` accepts an integer and signals rejected focus with `IndexError`.

## `velnora.SimpleFocusListWalker`

`velnora.SimpleFocusListWalker(contents, wrap_around=...)` accepts an iterable of widgets and an optional boolean wrapping setting. `get_focus()`, `get_next(position)`, and `get_prev(position)` return `(widget, integer_position)` or `(None, None)`. `set_focus(position)` accepts an integer and signals rejected focus with `IndexError`.

The provider supports `insert(index, widget)`, index and slice deletion, and `clear()` as mutable sequence operations.

## `velnora.ListBox`

`velnora.ListBox(body, select_navigation=...)` accepts a list provider or iterable of widgets and an optional boolean navigation setting. `body` exposes its provider. `focus` exposes a widget or `None`; `focus_position` exposes the provider position and accepts assignment to a position. `set_focus(position)` accepts that position. `set_focus_valign(valign)` accepts a vertical alignment string.

`render((columns, rows), focus=...)` and `render((columns,), focus=...)` return canvases. `rows((columns,))` returns full-content row count; `sizing()` returns sizing members. `keypress` and `mouse_event` use widget signatures. `select_navigation` is a readable and assignable boolean.

## `velnora.TreeNode`

`velnora.TreeNode(value, parent=..., key=...)` is subclassable with an application value, optional parent node, and optional hashable key. `get_value()` returns the application value, `get_depth()` an integer depth, and `get_widget()` its widget. `load_widget()` is the application override returning a tree widget.

## `velnora.ParentNode`

`velnora.ParentNode(value, parent=..., key=...)` is subclassable with an application value, optional parent node, and optional hashable key. `get_value()` returns the application value, `get_depth()` an integer depth, and `get_widget()` its widget. `load_widget()` is the application override returning a tree widget.

`load_child_keys()` is the application override returning child keys; `load_child_node(key)` returns a child node. `get_child_node(key)` returns the child node for a key.

## `velnora.TreeWidget`

`velnora.TreeWidget(node)` is subclassable with a tree node. Application overrides include `get_display_text()` returning label text and `is_initially_expanded()` returning boolean expansion state. Application class attributes `indent_cols`, `expanded_icon`, and `unexpanded_icon` carry an integer indentation and indicator widgets. `is_initially_expanded()` is also callable on the superclass. `get_node()` returns the node, `get_indent_cols()` an integer indentation, and `expanded` a boolean. `expand()` and `collapse()` are expansion entries.

## `velnora.TreeWalker`

`velnora.TreeWalker(start_from)` accepts a tree node. `get_next(node)` and `get_prev(node)` return `(tree_widget, node)` pairs or `(None, None)`. `positions(reverse=...)` returns an iterable of nodes and accepts an optional boolean direction.

## `velnora.TreeListBox`

`velnora.TreeListBox(body)` accepts a tree walker. It exposes `focus_position` as a node and `focus` as a tree widget. `set_focus(node)`, `focus_first_child()`, `focus_home(size)`, and `focus_end(size)` are focus entries. `sizing`, `rows`, `render`, `keypress`, and `mouse_event` use the list-box signatures.

## `velnora.Scrollable`

`velnora.Scrollable(widget)` accepts a widget. It exposes `render`, `keypress`, and `mouse_event` with widget signatures. `get_scrollpos()` returns an integer row offset and `set_scrollpos(position)` accepts an integer. Incompatible child sizing raises `ValueError`.

## `velnora.ScrollBar`

`velnora.ScrollBar(widget, thumb_char=..., trough_char=..., side=..., width=..., *, visible=..., scroll_by_focus=..., end_markers=..., attr=..., focus_attr=..., thumb_attr=..., thumb_focus_attr=..., marker_dim_attr=...)` accepts a scrollable widget or list box; optional character strings, side string, integer width, boolean visibility or `None`, boolean focus permission, pair of marker strings, and hashable style values. `render`, `keypress`, and `mouse_event` use widget signatures. Invalid side configuration raises `ValueError`.

`visible=None`, `True`, and `False` denote automatic, forced, and hidden visibility. `side` uses `left` or `right`.

## `velnora.Overlay`

`velnora.Overlay(top_w, bottom_w, align, width, valign, height, left=..., right=..., top=..., bottom=...)` accepts foreground and background widgets; string alignments; integer sizes or `('relative', percentage)` pairs; and optional integer margins. `render(size, focus=...)` returns a canvas and `keypress(size, key)` uses the widget key return form.

## `velnora.PopUpLauncher`

`velnora.PopUpLauncher(original_widget)` is subclassable with a widget. Override `create_pop_up()` to return a widget and `get_pop_up_parameters()` to return a dictionary with integer fields `left`, `top`, `overlay_width`, `overlay_height`, and optional integer `anchor_height`. Public entries are `open_pop_up()`, `close_pop_up()`, `render(size, focus=...)`, and `keypress(size, key)`.

## `velnora.PopUpTarget`

`velnora.PopUpTarget(original_widget)` accepts a widget. It exposes `render`, `keypress`, and `mouse_event` with widget signatures. `enter_selectable(reverse=...)` accepts an optional boolean direction.

## `velnora.DropDown`

`velnora.DropDown(options, selected=..., max_visible_items=...)` accepts an iterable of label markup, an optional integer selection index, and optional integer visible-item count. `options` exposes the option collection; `selected` is a readable and assignable integer index. `drop_down_indicator` exposes an indicator widget supporting `render(())`. `pack()` returns an integer dimension pair. `render`, `keypress`, and `mouse_event` use widget signatures. The `change` notification calls `callback(control, new_index)`. Rejected indices raise `IndexError`; rejected collection or visible-count configuration raises `ValueError`.

## `velnora.ProgressBar`

`velnora.ProgressBar(normal, complete, current=..., done=..., satt=...)` accepts hashable styles, optional numeric progress and completion amount, and an optional smoothing style. `current` and `done` are readable and assignable numeric properties. `set_completion(current)` accepts a number. `get_text()` returns a string in the form `<integer> %`. `render((columns,))` returns a canvas.

## `velnora.BarGraph`

`velnora.BarGraph(attlist, hatt=..., satt=...)` accepts segment styles as a sequence of attributes or `(attribute, character)` pairs, optional horizontal-line styles, and an optional mapping from `(foreground_segment, background_segment)` integer pairs to smoothing attributes. `set_data(bardata, top, hlines=...)` accepts a sequence of numeric bar sequences, a numeric scale maximum, and an optional sequence of numeric reference lines. `set_bar_width(width)` accepts an integer or `None`. `render((columns, rows))` returns a canvas. Rejected attribute configuration raises `BarGraphError`; rejected bar width raises `ValueError`.

## `velnora.GraphVScale`

`velnora.GraphVScale(labels, top)` accepts a sequence of `(numeric_value, label_markup)` pairs and a numeric scale maximum. `render((columns, rows))` returns a canvas.

## `velnora.BigText`

`velnora.BigText(markup, font)` accepts text markup and a font object. `set_text(markup)` accepts replacement markup. `pack(())` returns an integer dimension pair; `render(())` returns a canvas.

## `velnora.Font`

`velnora.Font` is subclassable with integer class attribute `height` and a sequence of strings in class attribute `data`. Each glyph-data block is newline-delimited: an initial empty line, a character header, then artwork rows. Each character's repeated contiguous header columns identify its artwork span.

Font instances are constructed without arguments. `characters()` returns a string of supported characters, `char_width(character)` returns an integer column width, `char_data(character)` returns a list of artwork row strings, and `height` is the integer row count.

## `velnora.get_all_fonts`

`velnora.get_all_fonts()` returns a list of `(name, font_class)` pairs. The name is a string; the class is callable without arguments and returns a font. The named entries are `Thin 3x3`, `Thin 4x3`, `Thin 6x6`, `Sextant 3x3`, `Sextant 2x2`, `Half Block 5x4`, `Half Block 6x5`, `Half Block Heavy 6x5`, and `Half Block 7x7`.

## `velnora.display.raw.Screen`

`velnora.display.raw.Screen(input=..., output=..., bracketed_paste_mode=..., focus_reporting=..., extended_keys=...)` accepts optional terminal input and text-output streams and boolean mode settings. `extended_keys` exposes a boolean.

`start()` returns a context manager and starts the display; `stop()` is the stop entry. `started` exposes a boolean lifecycle state. `get_cols_rows()` returns `(columns, rows)` as integers. `draw_screen(size, canvas)` accepts an integer dimension pair and a canvas. `flush()` flushes the terminal output stream.

`set_input_timeouts(max_wait=..., complete_wait=...)` accepts optional numeric seconds. `set_mouse_tracking(enable)` accepts a boolean. `get_input()` returns a list of events: key strings, the `window resize` label, or `(event, button, column, row)` mouse tuples. Mouse labels are `mouse press`, `mouse release`, and `mouse drag`; button and coordinates are integers, with zero-based coordinates.

`set_terminal_properties(colors=..., hyperlinks=...)` accepts an optional integer color mode and boolean hyperlink setting. Terminal drawing goes to the supplied `output` stream as VT text and control sequences. Hyperlink scope uses OSC 8 framing `ESC ] 8 ; <parameters> ; <uri> ST`; an empty target is the link-closing carrier. OSC termination is BEL or `ESC` followed by backslash. Mouse mode changes use `ESC [ ? <mode parameters> h` and `ESC [ ? <mode parameters> l`, where parameters are semicolon-separated decimal mode numbers.

`register_palette(palette)` accepts entries `(name, source_name)`, `(name, foreground, background)`, `(name, foreground, background, mono)`, or `(name, foreground, background, mono, foreground_high, background_high)`. Names are hashable and may include `None`. Color descriptions are strings; `mono` accepts a string or tuple of strings. `register_palette_entry(name, foreground, background, mono=..., foreground_high=..., background_high=...)` accepts the same field types. Invalid palette data raises `velnora.ScreenError`. `resolve_attr(attr, index)` returns an `AttrSpec`; representation indices are `0` for basic colors, `1` for monochrome, `2` for 88 colors, `3` for 256 colors, and `4` for true color.

`hook_event_loop(event_loop, callback)` registers a callback with signature `callback(keys, raw_codes)`, receiving the public event list and a list of integer input byte codes. `unhook_event_loop(event_loop)` removes the registration. Both entries return `None`.

With `extended_keys=True`, terminal replies on the input stream are consumed, not returned as events: a keyboard flag-query reply `ESC [ ? <flags> u` and a primary device-attributes reply `ESC [ ? <parameters> c`. A kitty key report on input has the form `ESC [ <key-code> [ ; <modifiers> ] u` with decimal fields, where `<modifiers>` is one plus the sum of 1 for Shift, 2 for Alt, 4 for Control, 8 for Super and 16 for Hyper; it is returned under the key names of the package surface.

Changes to keyboard reporting appear on the output stream as kitty flag pushes `ESC [ > <flags> u`, pops `ESC [ < [<count>] u`, flag updates `ESC [ = <flags> [ ; <operation> ] u` (operation 1 replaces, 2 adds, 3 removes bits), and xterm modifyOtherKeys settings `ESC [ > 4 ; <value> m` (`ESC [ > 4 m` resets the resource). Flag values are the kitty progressive-enhancement bits: 1 disambiguate, 2 report event types, 4 report alternate keys, 8 report all keys, 16 report associated text. A terminal's modifyOtherKeys reply on input, `ESC [ > 4 ; <value> m`, is consumed like the other replies. Under modifyOtherKeys a modified key arrives as `ESC [ 27 ; <modifiers> ; <key-code> ~`; with event types requested, a kitty report carries `<modifiers>:<event-type>`, where 1 is press, 2 repeat and 3 release.

Legacy key input spellings include `CSI A/B/C/D` for the arrows, `CSI 5~/6~` for Page Up/Down, `CSI H/F` for Home/End, `CSI 2~/3~` and `CSI P` for Insert/Delete, DEL for Backspace, HT for Tab and CR for Enter. Function keys F1–F20 use `CSI number ~`, with numbers 11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34 in function-key order. Modified arrows use `CSI 1 ; modifiers final`, with the modifier field above. An ESC prefix denotes Meta; ASCII control codes denote Control-letter input.

Mouse input uses `CSI < code ; column ; row M` or the release form ending in `m`. Wire coordinates are one-based. Button codes 0, 1 and 2 identify the first three buttons; the motion bit is 32 and wheel codes are 64 and 65. xterm modifyOtherKeys level 2 is the reporting form for disambiguated modified input.

## `velnora.display.curses.Screen`

`velnora.display.curses.Screen()` constructs a screen using the process terminal streams and the terminal description named by `TERM`. `start()` returns a context manager and starts the display; `stop()` is the stop entry. `get_cols_rows()` returns `(columns, rows)` as integers. `draw_screen(size, canvas)` accepts an integer dimension pair and a canvas; terminal text and controls go to the terminal output stream. An unsupported external event-loop integration raises `NotImplementedError`.

`get_input()` returns a list of public key strings and mouse tuples `(event, button, column, row)`; `set_mouse_tracking(enable)` accepts a boolean. Coordinates and key labels use the package input forms.

`set_input_timeouts(max_wait=..., complete_wait=...)` accepts numeric seconds. `set_mouse_tracking(False)` can raise `NotImplementedError` for unsupported tracking changes. Legacy key input and SGR mouse reports use the input spellings given for the direct screen.

## `velnora.SelectEventLoop`

`velnora.SelectEventLoop()` constructs an event-loop adapter. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects.

## `velnora.AsyncioEventLoop`

`velnora.AsyncioEventLoop(loop=...)` constructs an event-loop adapter. The optional `loop` is an application-supplied asyncio event loop. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects. Callback arguments can be ordinary callables or async callables.

## `velnora.TornadoEventLoop`

`velnora.TornadoEventLoop(loop)` constructs an event-loop adapter. The argument is an application-supplied Tornado IOLoop. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects. Callback arguments can be ordinary callables or async callables.

## `velnora.TwistedEventLoop`

`velnora.TwistedEventLoop(reactor)` constructs an event-loop adapter. The argument is an application-supplied Twisted reactor. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects.

## `velnora.GLibEventLoop`

`velnora.GLibEventLoop()` constructs an event-loop adapter. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects.

## `velnora.TrioEventLoop`

`velnora.TrioEventLoop()` constructs an event-loop adapter. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects. Callback arguments can be ordinary callables or async callables.

## `velnora.ZMQEventLoop`

`velnora.ZMQEventLoop()` constructs an event-loop adapter. `alarm(seconds, callback)`, `watch_file(fd, callback)`, and `enter_idle(callback)` return opaque handles. Delays are numeric seconds and file descriptors are integers. Callbacks are called without arguments. `remove_alarm(handle)`, `remove_watch_file(handle)`, and `remove_enter_idle(handle)` accept the corresponding handles. `run()` is the execution entry; the explicit-exit carrier is `ExitMainLoop`, and propagated callback failures retain their original exception objects. Callback arguments can be ordinary callables or async callables.

`watch_queue(queue, callback)` accepts a ZeroMQ socket and a no-argument callable, including an async callable. It returns an opaque handle accepted by `remove_watch_queue(handle)`.

## `velnora.ExitMainLoop`

`velnora.ExitMainLoop` is the exception class used for an explicit application-loop exit request.

## `velnora.MainLoop`

`velnora.MainLoop(widget, screen=..., input_filter=..., unhandled_input=..., event_loop=...)` accepts a root widget and optional screen, input-filter callback, unhandled-input callback, and event-loop adapter. `widget` is readable and assignable; `screen` and `event_loop` expose their objects. `screen_size` is an integer `(columns, rows)` pair.

`process_input(keys)` accepts an iterable of events; `draw_screen()` is the drawing entry. An input-filter callback receives `(keys, raw)`, with a list of events and a list of raw integer input codes, and returns a list of events. The unhandled-input callback receives one event.

`set_alarm_in(sec, callback, user_data=...)` and `set_alarm_at(tm, callback, user_data=...)` accept numeric relative seconds or an absolute Unix timestamp, a callable, and optional application context. They return opaque handles accepted by `remove_alarm(handle)`. Alarm callbacks receive `(main_loop, user_data)`.

`watch_file(fd, callback)` accepts an integer descriptor and no-argument callback and returns a handle accepted by `remove_watch_file(handle)`. `watch_pipe(callback)` returns a writable OS file descriptor; its callback receives bytes. `remove_watch_pipe(write_fd)` accepts that descriptor. A write after removal can return a byte count or raise `BrokenPipeError`.

`run()` is the application execution entry; it returns normally for `ExitMainLoop`; propagated input and readable-file failures retain their original exception objects. `paused()` returns a context manager, through which exceptions from the body retain their original exception objects. An unsupported display/event-loop combination raises `NotImplementedError`.

## `velnora.Terminal`

`velnora.Terminal(command, env=...)` accepts an argument sequence, no-argument application callable, or `None`, and an optional environment mapping. `SHELL` names the shell executable and `TERM` is the terminal-type environment field exchanged with executed child commands. The child exchanges terminal bytes through its stdin and stdout. `render((columns, rows), focus=...)` returns a canvas; `get_cursor_coords(size)` returns a zero-based integer coordinate pair or `None`.

`keypress(size, key)` and `mouse_event(size, event, button, col, row, focus)` use widget signatures and handling results. `wait_and_feed(timeout)` accepts numeric seconds and processes pending child output. `terminate()` is the close entry. `master` exposes the OS terminal descriptor and `terminated` is a boolean.

Notifications have positional payloads: `title` calls `callback(terminal, title_string)`, `beep` calls `callback(terminal)`, `leds` calls `callback(terminal, state)`, and `closed` calls `callback(terminal)`. LED state carriers are `clear`, `scroll_lock`, `num_lock`, and `caps_lock`.

Child input uses terminal byte protocols: text is UTF-8, Enter is carriage return, SGR mouse reports have the form `ESC [ < <button-code> ; <column> ; <row> M` for press or drag and the same form ending in `m` for release, with one-based coordinate fields. Paste delimiters are `ESC [ 200 ~` and `ESC [ 201 ~`.

The kitty keyboard response carrier is `ESC [ <key-code> [ : <shifted-key-code> ] [ ; <modifiers> [ ; <text-codepoint> ] ] u`. Fields are decimal integers, with empty optional fields retained where needed to reach a later field. A keyboard flag-query response is `ESC [ ? <flags> u`.

The child-output stream uses the terminal-control spellings listed for `velnora.ansi_parser`, including the erase, edit, mode, scrolling-region, tab and save/restore spellings. Mode selection without `?` uses `CSI mode h` and `CSI mode l`: mode 4 is insertion and mode 20 is newline. Private modes are 6 for region-relative cursor positioning, 7 for wrapping, 25 for cursor visibility, 47 for basic alternate-screen switching, 1047 for clear-on-return switching, and 1049 for save-and-clear switching. Erasure parameters 0, 1 and 2 mean through the end, through the beginning and the entire extent, respectively. `ESC M` is reverse line feed and `ESC c` is terminal reset. `CSI 0 g` clears the current tab stop; `CSI 3 g` clears all stops. `CSI s`/`CSI u` are position-only cursor save/restore; `ESC 7`/`ESC 8` include attributes and character-set selection.

Mouse modes use private-mode controls 1000 for press/release, 1002 for button-held motion, and 1006 for SGR report syntax. Bracketed paste is private mode 2004. Kitty keyboard controls are `CSI = flags u` for assignment, `CSI > flags u` for push, `CSI < u` for pop, and `CSI ? u` for query. Flag bits and modifier fields use the keyboard encodings of `velnora.display.raw.Screen`. ASCII uppercase alternate-key codes pair the lowercase code with its uppercase code; named special-key codes include 13 for Enter and 57441 for left Shift.

## `velnora.display.web.set_preferences`

`velnora.display.web.set_preferences(app_name, pipe_dir=...)` accepts an application-name string and an optional directory path string.

## `velnora.display.web.Screen`

`velnora.display.web.Screen()` constructs a screen. `start()` and `stop()` are its lifecycle entries. `get_input()` returns a list of decoded event-name or key strings; the resize event label is `window resize`. `get_cols_rows()` returns `(columns, rows)` as integers.

`pipe_name` is a path stem of the form `<pipe_dir>/velnora_<session_id>`, using the configured directory and a session identifier. The session identifier is supplied as `HTTP_X_VELNORA_ID` on subsequent CGI input requests.

## `velnora.display.web.handle_short_request`

`velnora.display.web.handle_short_request()` handles a CGI request and returns boolean `True` for a handled request and `False` for a request that starts the application. The CGI environment fields are `REQUEST_METHOD` with value `POST`, `HTTP_X_VELNORA_ID` with the screen session identifier, `HTTP_X_VELNORA_METHOD` with value `multipart`, and `CONTENT_TYPE` with form `text/plain; charset=<codec>`. The encoded request body is supplied on `stdin`.

The CGI response goes to `stdout` as ASCII header lines terminated by CRLF and a blank line. Header names are case-insensitive. Successful input submission carries `Content-Type: text/plain`. A malformed-input rejection carries `Status: 400 <reason phrase>`.

A web application is one CGI program served at one URL under a standard CGI gateway (request variables as in RFC 3875, the request body on `stdin`, the response streamed from `stdout` as it is written). The program calls `set_preferences(...)` and then `handle_short_request()`; when that returns `True` the program exits, and when it returns `False` it runs its application with `velnora.MainLoop(widget, screen=velnora.display.web.Screen(), ...)`. A `GET` request returns `Content-type: text/html` with the browser client page. Loaded in a browser, that page itself drives the session by further requests to the same URL: it displays the screen updates the application draws, and sends the browser's key presses, using the key names of the package surface, and its window size as `window resize` requests.

## `window resize`

The web input stream consists of newline-delimited key strings. Its dimension-request line is `window resize <columns> <rows>` followed by newline; both fields are decimal integers separated by single spaces. Startup receives its initial dimension line on `stdin` with `HTTP_X_VELNORA_METHOD=multipart`.

## `velnora.AttrSpecError`

`velnora.AttrSpecError` is an exception class for the corresponding public validation failure.

## `velnora.PaddingError`

`velnora.PaddingError` is an exception class for the corresponding public validation failure.

## `velnora.FillerError`

`velnora.FillerError` is an exception class for the corresponding public validation failure.

## `velnora.WidgetError`

`velnora.WidgetError` is an exception class for the corresponding public validation failure.

## `velnora.ColumnsError`

`velnora.ColumnsError` is an exception class for the corresponding public validation failure.

## `velnora.PileError`

`velnora.PileError` is an exception class for the corresponding public validation failure.

## `velnora.CheckBoxError`

`velnora.CheckBoxError` is an exception class for the corresponding public validation failure.

## `velnora.command_map.restore_defaults`

`velnora.command_map` is the package command-mapping instance. It supports `dict(command_map)`, string-key lookup, assignment, deletion, and `restore_defaults()`, using the `CommandMap` interface.

## `velnora`

The `velnora` package exposes `ANSIText`, `AsyncioEventLoop`, `AttrMap`, `AttrSpec`, `FLOW`, `FIXED`, `BOX`, `BarGraph`, `BigText`, `BoxAdapter`, `Button`, `CanvasCombine`, `CanvasJoin`, `CanvasOverlay`, `CheckBox`, `CheckBoxError`, `Columns`, `ColumnsError`, `CommandMap`, `CompositeCanvas`, `Divider`, `DropDown`, `Edit`, `ExitMainLoop`, `Filler`, `FillerError`, `Font`, `Frame`, `GLibEventLoop`, `GraphVScale`, `GridFlow`, `Hyperlink`, `IntEdit`, `LineBox`, `ListBox`, `ListWalker`, `MainLoop`, `Overlay`, `Padding`, `PaddingError`, `ParentNode`, `Pile`, `PileError`, `PopUpLauncher`, `PopUpTarget`, `ProgressBar`, `RadioButton`, `ScrollBar`, `Scrollable`, `SelectEventLoop`, `SelectableIcon`, `SimpleFocusListWalker`, `SimpleListWalker`, `Sizing`, `SolidFill`, `StandardTextLayout`, `Terminal`, `Text`, `TextCanvas`, `TextLayout`, `TornadoEventLoop`, `TreeListBox`, `TreeNode`, `TreeWalker`, `TreeWidget`, `TrioEventLoop`, `TwistedEventLoop`, `Widget`, `WidgetDisable`, `WidgetError`, `WidgetPlaceholder`, `WidgetWrap`, `ZMQEventLoop`, `command_map`, `connect_signal`, `disconnect_signal`, `disconnect_signal_by_key`, `emit_signal`, `get_all_fonts`, `get_ascii_fallbacks`, `register_signal`, `set_ascii_fallbacks`, `set_encoding`, `widget`, `apply_target_encoding`, `calc_width`, `calc_text_pos`, `move_next_char`, `move_prev_char`. It also exposes the `util` module.

## `velnora.util`

The module `velnora.util` exposes `get_encoding`, `apply_target_encoding`, and `trim_text_attr_cs`.

## `velnora.ansi_parser`

The module `velnora.ansi_parser` exposes `AnsiParser`, `parse_ansi_line`, `parse_ansi_text`.

Terminal-control input syntax uses `ESC` for U+001B, `BEL` for U+0007, `CSI` for `ESC [`, and `OSC` for `ESC ]`. Decimal parameters are separated by semicolons; omitted fields are empty. The following spellings identify operations:

| Input form | Operation |
| --- | --- |
| LF, CR, BS, HT, BEL | Newline, carriage return, backspace, tab, bell |
| `CSI n A`, `CSI n B`, `CSI n C`, `CSI n D` | Up, down, forward, backward |
| `CSI n E`, `CSI n F` | Next line, previous line |
| `CSI n G`, `CSI n d` | Absolute column, absolute row |
| `CSI row ; column H`, `CSI row ; column f` | Absolute position |
| `CSI parameters m` | Color and effect selection |
| `CSI n q` | LED request: 0 clear, 1 scroll lock, 2 number lock, 3 capitals lock |
| `OSC 0 ; title`, `OSC 2 ; title` | Title request |
| `OSC 8 ; parameters ; uri` | Hyperlink control; `parameters` may contain `id=identity` |
| `ESC ( B`, `ESC ( 0` | Designate ordinary or DEC graphics in the first character set |
| `ESC ) B`, `ESC ) 0` | Designate ordinary or DEC graphics in the second character set |
| SO (U+000E), SI (U+000F) | Select second or first character set |

OSC strings end in BEL or `ESC` followed by backslash. Color/effect parameters are 0 for reset; 1 bold, 2 faint, 3 italics, 4 underline, 5 blink, 7 standout, 9 strikethrough; 22 intensity reset, 23 italics off, 24 underline off, 25 blink off, 27 standout off, 29 strikethrough off; 30–37/40–47 for basic foreground/background, 90–97/100–107 for bright foreground/background, and 39/49 for foreground/background reset. The forms `38;5;index` and `48;5;index` select indexed foreground/background; `38;2;red;green;blue` and `48;2;red;green;blue` select component colors.

Terminal-operation spellings recognized for skip reports are `CSI n J` (screen erase), `CSI n K` (line erase), `CSI top ; bottom r` (scrolling region), `CSI s` and `CSI u` or `ESC 7` and `ESC 8` (cursor save/restore), `CSI ? mode h` and `CSI ? mode l` (private-mode selection), `CSI n @` (character insertion), `CSI n P` (character deletion), `CSI n X` (character erasure), `CSI n L` and `CSI n M` (line insertion/deletion), `CSI c` and `CSI n n` (device queries), `CSI n g` and `ESC H` (tab-stop changes).

## `velnora.display`

The module `velnora.display` exposes `web`, `html_fragment` and `lcd`.

## `velnora.display.raw`

The module `velnora.display.raw` exposes `Screen`.

## `velnora.display.curses`

The module `velnora.display.curses` exposes `Screen`.

## `velnora.display.web`

The module `velnora.display.web` exposes `Screen`, `set_preferences`, `handle_short_request`.

## `velnora.numedit`

The module `velnora.numedit` exposes `IntegerEdit`, `FloatEdit`.

## `velnora.get_encoding`

`velnora.util.get_encoding()` returns the selected encoding-name string.

## `velnora.TagMarkupException`

`velnora.TagMarkupException` is an exception class for the corresponding public validation failure.

## `velnora.TextError`

`velnora.TextError` is an exception class for the corresponding public validation failure.

## `velnora.BarGraphError`

`velnora.BarGraphError` is an exception class for the corresponding public validation failure.

## `velnora.ScreenError`

`velnora.ScreenError` is an exception class for invalid display palette data.

## `velnora.display.html_fragment`

The module `velnora.display.html_fragment` exposes `HtmlGenerator` and `screenshot_collect`.

## `velnora.display.html_fragment.HtmlGenerator`

`velnora.display.html_fragment.HtmlGenerator()` constructs a screen usable as the `screen` of `velnora.MainLoop`. Class attributes `sizes` and `keys` are assignable lists: `sizes` holds `(columns, rows)` integer pairs and `keys` holds lists of event strings. `get_cols_rows()` returns an integer dimension pair; `get_input()` returns an event list.

`draw_screen(size, canvas)` accepts an integer dimension pair and a canvas and records one screen fragment. `set_terminal_properties(colors=...)` accepts an integer color mode and `register_palette_entry(name, foreground, background)` accepts a palette entry, as for `velnora.display.raw.Screen`. A fragment is a string of HTML body content; a followable hyperlink is an `a` element whose `href` is the link target.

## `velnora.display.html_fragment.screenshot_collect`

`velnora.display.html_fragment.screenshot_collect()` returns a list of HTML fragment strings.

## `velnora.display.lcd`

The module `velnora.display.lcd` exposes `CF635Screen`.

## `velnora.display.lcd.CF635Screen`

`velnora.display.lcd.CF635Screen(device_path)` opens the serial device at the path string with the device's packet protocol and constructs a screen for a Crystal Fontz 635 display. `get_cols_rows()` returns an integer `(columns, rows)` pair. `draw_screen(size, canvas)` accepts an integer dimension pair and a canvas; screen contents, cursor position and cursor style reach the device as protocol commands sent over the serial line. `get_input_nonblocking()` processes pending device packets, including acknowledgements and key-activity reports, and returns `(timeout, keys, raw_codes)`, where `keys` is a list of key strings. Button presses are reported as `up`, `down`, `left`, `right`, `enter` and `esc`.

Device packets are `command byte, data length byte, data bytes, CRC-16/X-25 of the preceding bytes in little-endian order`. Commands the display applies: `6` clears the screen; `11` with data `column, row` places the cursor; `12` with one style byte sets the cursor style, where `0` hides the cursor; `31` with data `column, row, character bytes` writes characters from that cell. The device acknowledges a command with a packet whose command byte is `0x40` combined with the acknowledged command. A key-activity report is command `0x80` with one code byte: `1` through `6` press up, down, left, right, enter and exit; `7` through `12` release them in the same order.

## `velnora.display.html_fragment.HtmlGenerator.sizes`

Stated under `velnora.display.html_fragment.HtmlGenerator`.

## `velnora.display.html_fragment.HtmlGenerator.keys`

Stated under `velnora.display.html_fragment.HtmlGenerator`.

## `velnora.FLOW`

`velnora.FLOW` is the flow-sizing member exposed by the package.

## `velnora.FIXED`

`velnora.FIXED` is the fixed-sizing member exposed by the package.
