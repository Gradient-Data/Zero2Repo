# feature: F03
"""FP-03 acceptance through Eval, checked against native Go 1.26."""

from F01_helpers import f01_driver
from F02_helpers import f02_compare
from F03_helpers import f03_package_compare, f03_reads


def test_container_construction_and_operations(f02_compare):
    # F03.T01: observe contents separately from shape, before and after changes.
    f02_compare([
        [("var zero [4]int; a := [...]int{3: 19, 1: 7}; p := new([2]int)", False)] +
        f03_reads("zero", "a", "len(a)", "cap(a)", "*p") +
        [("a[0] = 31; p[1] = 43; view := a[1:3:4]", False)] +
        f03_reads("a", "*p", "len(view)", "cap(view)", "view[0]", "view[1]") +
        [("view[1] = 53", False)] + f03_reads("a", "a[:2][1]", "a[2:][0]"),
        [("s := make([]int, 2, 5); keyed := []int{2: 17, 29}; plain := []int{6, 9}", False)] +
        f03_reads("s[0]", "s[1]", "len(s)", "cap(s)", "len(keyed)",
                  "keyed[0]", "keyed[1]", "keyed[2]", "keyed[3]", "plain[0]", "plain[1]") +
        [("s[0] = 11; s = append(s, 23); s = append(s, plain...)", False)] +
        f03_reads("len(s)", "cap(s)", "s[0]", "s[1]", "s[2]", "s[3]", "s[4]") +
        [("s = append(s, 41, 47)", False)] +
        # Growth capacity is an implementation choice; only the required bound is read.
        f03_reads("len(s)", "cap(s) >= len(s)", "s[0]", "s[4]", "s[5]", "s[6]") +
        [("dst := make([]int, 3); count := copy(dst, s)", False)] +
        f03_reads("count", "dst[0]", "dst[1]", "dst[2]") +
        [("count = copy(dst[1:], dst[:2])", False)] +
        f03_reads("count", "dst[0]", "dst[1]", "dst[2]") +
        [("clear(s[1:3])", False)] +
        f03_reads("len(s)", "s[0]", "s[1]", "s[2]", "s[3]"),
        [('m := map[string]int{"oak": 13, "elm": 27}; allocated := make(map[int]string, 3)', False)] +
        f03_reads("len(m)", 'm["oak"]', 'm["elm"]', "len(allocated)") +
        [('m["elm"] = 39; m["ash"] = 51; allocated[4] = "four"; delete(m, "oak")', False)] +
        f03_reads("len(m)", 'm["oak"]', 'm["elm"]', 'm["ash"]', "allocated[4]") +
        [('delete(m, "absent"); clear(m)', False)] +
        f03_reads("len(m)", 'm["elm"]', 'm["ash"]', "m == nil"),
        [('type Record struct { Count int; Name string; Flags [2]bool }; '
          'var zero Record; keyed := Record{Name: "cedar", Count: 21}; '
          'positional := Record{34, "pine", [2]bool{true, false}}; p := new(Record)', False)] +
        f03_reads("zero.Count", "zero.Name", "zero.Flags[0]", "zero.Flags[1]",
                  "keyed.Count", "keyed.Name", "keyed.Flags[0]", "positional.Count",
                  "positional.Name", "positional.Flags[0]", "positional.Flags[1]", "p.Count", "p.Name") +
        [('keyed.Flags[1] = true; p.Count = 55; positional.Name = "fir"', False)] +
        f03_reads("keyed.Flags[1]", "p.Count", "positional.Name"),
    ])


def test_aggregate_copies_and_reference_sharing(f02_compare):
    # F03.T02: callee results prove calls ran; caller observations prove copying.
    f02_compare([
        [("a := [3]int{5, 12, 24}; b := a; b[1] = 37; "
          "change := func(v [3]int) [3]int { v[0] = 48; return v }; c := change(a)", False)] +
        f03_reads("a", "b", "c") +
        [("a[2] = 59", False)] + f03_reads("a", "b", "c"),
        [("type Record struct { N int; A [2]int; S []int; M map[string]int }; "
          'a := Record{8, [2]int{16, 32}, []int{64, 96}, map[string]int{"k": 128}}; '
          "b := a; b.N = 9; b.A[0] = 17; b.S[0] = 65; b.M[\"k\"] = 129", False)] +
        f03_reads("a.N", "b.N", "a.A", "b.A", "a.S[0]", 'a.M["k"]') +
        [("change := func(v Record) Record { v.N = 10; v.A[1] = 33; "
          'v.S[1] = 97; v.M["k"] = 130; return v }; c := change(a)', False)] +
        f03_reads("a.N", "a.A", "c.N", "c.A", "a.S[1]", "b.S[1]", 'a.M["k"]', 'b.M["k"]'),
        [("a := make([]int, 3, 6); a[0] = 11; a[1] = 22; a[2] = 33; b := a; "
          "b = b[1:]; b[0] = 44", False)] +
        f03_reads("len(a)", "cap(a)", "len(b)", "cap(b)", "a[0]", "a[1]", "b[0]") +
        [("change := func(s []int) []int { s[0] = 55; s = s[:1]; return s }; c := change(a)", False)] +
        f03_reads("len(a)", "len(c)", "a[0]", "c[0]") +
        [("b = append(b, 66)", False)] +
        f03_reads("len(a)", "len(b)", "a[:4][3]") +
        [("bounded := a[:2:2]; grown := append(bounded, 77); grown[0] = 88", False)] +
        f03_reads("len(grown)", "grown[0]", "grown[2]", "a[0]", "a[2]") +
        [("holder := struct{ S []int }{a}; "
          "detach := func(s []int, h *struct{ S []int }) int { h.S = nil; return len(s) }; "
          "saved := detach(holder.S, &holder)", False)] +
        f03_reads("saved", "holder.S == nil", "len(a)"),
        [('a := map[string]int{"x": 7, "y": 14}; b := a; b["x"] = 21; '
          'edit := func(m map[string]int) int { m["z"] = 28; delete(m, "y"); return len(m) }; '
          'count := edit(b)', False)] +
        f03_reads("count", "len(a)", 'a["x"]', 'a["y"]', 'a["z"]') +
        [('b = make(map[string]int); b["x"] = 35', False)] +
        f03_reads("len(a)", "len(b)", 'a["x"]', 'b["x"]'),
    ])


def test_pointer_storage_allocation_and_recursive_types(f03_package_compare):
    # F03.T03: no closure captures the variables whose addresses are tested.
    declarations = """
type Node struct { Value int; Next *Node }
type Left struct { Value int; Peer *Right }
type Right struct { Value int; Peer *Left }
func localStorage() [3]int {
    value := 9
    pointer := &value
    alias := pointer
    *pointer = 18
    first := value
    value = 27
    return [3]int{first, *alias, value}
}
"""
    steps = [("var x int = 13; var y int = 26; p := &x; q := p; pp := &p; var absent *int", False)]
    steps += f03_reads("localStorage()", "*p", "p == q", "p == &x", "p == &y", "absent == nil", "p == nil")
    steps += [("**pp = 39", False)] + f03_reads("x", "*q", "y")
    steps += [("x = 52; allocated := new(int); separate := new(int)", False)]
    steps += f03_reads("*q", "*allocated", "allocated == nil", "allocated == separate")
    steps += [("*allocated = 65; a := [3]int{4, 8, 12}; s := []int{7, 14, 21}; "
               "ap := &a[1]; sp := &s[2]; *ap = 80; *sp = 210", False)]
    steps += f03_reads("*allocated", "*separate", "a", "s[0]", "s[1]", "s[2]", "ap == &a[1]", "sp == &s[2]")
    steps += [("root := &Node{Value: 17, Next: &Node{Value: 34}}; field := &root.Next.Value; *field = 51", False)]
    steps += f03_reads("root.Value", "root.Next.Value", "root.Next.Next == nil", "field == &root.Next.Value")
    steps += [("root.Next.Next = root; root.Next.Next.Value = 68; "
               "left := new(Left); right := &Right{Value: 23, Peer: left}; left.Peer = right; "
               "left.Peer.Peer.Value = 46", False)]
    steps += f03_reads("root.Value", "root.Next.Next == root", "left.Value", "left.Peer.Value", "right.Peer == left")
    f03_package_compare(declarations, steps)


def test_map_presence_and_nil_container_distinctions(f02_compare):
    # F03.T04: successful values and explicit presence bits, not failed probes.
    f02_compare([
        [('var nilMap map[string]int; empty := make(map[string]int); literal := map[string]int{}; '
          'm := map[string]int{"zero": 0, "value": 42}; '
          'missing, missingOK := m["missing"]; zero, zeroOK := m["zero"]; '
          'value, valueOK := m["value"]; nilValue, nilOK := nilMap["missing"]', False)] +
        f03_reads("nilMap == nil", "empty == nil", "literal == nil", "len(nilMap)", "len(empty)",
                  "len(literal)", "missing", "missingOK", "zero", "zeroOK", "value", "valueOK", "nilValue", "nilOK") +
        [('delete(m, "value"); deleted, deletedOK := m["value"]; delete(nilMap, "x"); clear(nilMap)', False)] +
        f03_reads("deleted", "deletedOK", "nilMap == nil") +
        [('texts := map[int]string{}; text, textOK := texts[1]; '
          'ptrs := map[int]*int{}; ptr, ptrOK := ptrs[1]; '
          'records := map[int]struct{ N int; S string }{}; record, recordOK := records[1]', False)] +
        f03_reads("text", "textOK", "ptr == nil", "ptrOK", "record.N", "record.S", "recordOK"),
        [("var nilSlice []int; allocated := make([]int, 0); literal := []int{}; "
          "backing := []int{19}; resliced := backing[:0]", False)] +
        f03_reads("nilSlice == nil", "allocated == nil", "literal == nil", "resliced == nil",
                  "len(nilSlice)", "cap(nilSlice)", "len(allocated)", "len(literal)", "len(resliced)") +
        [("nilSlice = append(nilSlice, 31); allocated = append(allocated, 47)", False)] +
        f03_reads("nilSlice == nil", "nilSlice[0]", "allocated[0]", "len(nilSlice)", "len(allocated)"),
    ])


def test_string_byte_and_rune_operations(f02_compare):
    # F03.T05: multibyte text separates byte indexing from rune conversion.
    f02_compare([
        [('text := "Aé界\\U0001F642Z"; bytes := []byte(text); runes := []rune(text)', False)] +
        f03_reads("len(text)", "text[0]", "text[1]", "text[2]", "text[6]", "text[10]",
                  "text[1:6]", "text[:3]", "text[6:]", "text[3:3]", "len(bytes)", "len(runes)",
                  "string(bytes)", "string(runes)", "runes[0]", "runes[1]", "runes[2]", "runes[3]", "runes[4]") +
        [("bytes[0] = 'B'; runes[2] = '水'; saved := string(bytes); bytes[0] = 'C'", False)] +
        f03_reads("text", "string(bytes)", "string(runes)", "saved") +
        [('raw := []byte{0, 65, 127}; letters := []rune{\'λ\', \'海\', \'Q\'}', False)] +
        f03_reads("string(raw)", "string(letters)", 'len([]byte(""))', 'len([]rune(""))',
                  "string([]byte(nil))", "string([]rune(nil))"),
    ])


def test_storage_layout_and_live_pointer_views(f03_package_compare):
    # F03.T06: live, in-bounds storage only; strings are never mutated.
    declarations = """
type Inner struct { Small byte; Wide int64 }
type Layout struct { Prefix byte; Middle Inner; Tail uint16 }
"""
    steps = [("var layout Layout; words := [4]int32{15, 30, 45, 60}", False)]
    steps += f03_reads("unsafe.Sizeof(layout)", "unsafe.Alignof(layout)",
                       "unsafe.Offsetof(layout.Prefix)", "unsafe.Offsetof(layout.Middle)",
                       "unsafe.Offsetof(layout.Tail)", "unsafe.Offsetof(layout.Middle.Wide)",
                       "unsafe.Sizeof(words)", "unsafe.Alignof(words)",
                       "unsafe.Sizeof(&layout)", "unsafe.Alignof(&layout)")
    steps += [("base := unsafe.Pointer(&words[0]); "
               "next := (*int32)(unsafe.Add(base, unsafe.Sizeof(words[0]))); "
               "view := unsafe.Slice(next, 2)", False)]
    steps += f03_reads("*next", "len(view)", "cap(view)", "view[0]", "view[1]", "unsafe.SliceData(view) == &words[1]")
    steps += [("view[1] = 99; words[1] = 77", False)]
    steps += f03_reads("words", "view[0]", "view[1]")
    steps += [("*unsafe.SliceData(view) = 88; "
               "last := (*int32)(unsafe.Pointer(uintptr(base) + 3*unsafe.Sizeof(words[0]))); *last = 111", False)]
    steps += f03_reads("words", "*last")
    steps += [("storage := [6]byte{'c', 'e', 'd', 'a', 'r', '!'}; "
               "text := unsafe.String(&storage[0], 5); "
               "textView := unsafe.Slice(unsafe.StringData(text), len(text))", False)]
    steps += f03_reads("text", "len(text)", "unsafe.StringData(text) == &storage[0]", "string(textView)",
                       "unsafe.String(unsafe.StringData(text), 3)")
    f03_package_compare(declarations, steps, imports=("unsafe",))
