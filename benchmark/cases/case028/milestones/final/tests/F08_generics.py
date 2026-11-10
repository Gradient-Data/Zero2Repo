# feature: F08
"""Generic programs observed through Eval and an independent Go 1.26 oracle."""

from F01_helpers import f01_driver, f01_eval, f01_success
from F03_helpers import f03_package_compare, f03_reads


def test_explicit_functions_types_and_receiver_methods(f03_package_compare):
    # F08.T01: observe scalar types and generic type membership, not mangled names.
    declarations = r'''
func choose[T any](first, second T, takeFirst bool) T {
    if takeFirst { return first }; return second
}
type Cell[T any] struct { Value T }
func (c Cell[T]) Get() T { return c.Value }
func (c *Cell[T]) Set(v T) { c.Value = v }
type Pair[K any, V any] struct { Key K; Value V }
func (p Pair[K, V]) GetKey() K { return p.Key }
func (p Pair[K, V]) GetValue() V { return p.Value }
func integerCell(x any) bool { _, ok := x.(Cell[int]); return ok }
func textCell(x any) bool { _, ok := x.(Cell[string]); return ok }
'''
    steps = f03_reads('choose[int16](-12, 27, true)',
                      'choose[string]("cedar", "elm", false)',
                      'choose[float64](2.75, -6.5, false)',
                      'choose[int16](-12, 27, false)')
    steps += [('pick := choose[uint32]', False)] + f03_reads('pick(43, 81, true)')
    steps += [('a := Cell[int]{Value: 17}; b := Cell[string]{Value: "birch"}; var zero Cell[int]', False)]
    steps += f03_reads('a.Value', 'b.Value', 'a.Get()', 'b.Get()', 'zero.Value',
                       'integerCell(a)', 'integerCell(b)', 'textCell(a)', 'textCell(b)')
    steps += [('a.Set(29); b.Set("willow")', False)]
    steps += f03_reads('a.Value', 'b.Value', 'a.Get()', 'b.Get()', 'zero.Get()')
    steps += [('p := Pair[string, int16]{Key: "height", Value: -23}; q := Pair[int16, string]{Key: 31, Value: "depth"}', False)]
    steps += f03_reads('p.Key', 'p.Value', 'p.GetKey()', 'p.GetValue()',
                       'q.Key', 'q.Value', 'q.GetKey()', 'q.GetValue()')
    f03_package_compare(declarations, steps)


def test_inference_argument_forms_constants_and_explicit_prefix(f03_package_compare, f01_driver):
    # F08.T02: each enumerated argument shape binds an otherwise unknown type.
    declarations = r'''
func identity[T any](x T) T { return x }
func dereference[T any](x *T) T { return *x }
func first[T any](x []T) T { return x[0] }
func lookup[K comparable, V any](x map[K]V, key K) V { return x[key] }
func receive[T any](x chan T) T { return <-x }
func invoke[A any, B any](f func(A) B, x A) B { return f(x) }
func project[A any, B any](x A, y B) B { return y }
func fromSlice[S ~[]E, E any](s S) E { return s[0] }
func find[S ~[]E, E comparable](s S, value E) int {
    for i, v := range s { if v == value { return i } }; return -1
}
func same[T comparable](a, b T) bool { return a == b }
func complexType(x any) bool { _, ok := x.(complex128); return ok }
'''
    steps = [('var n int16 = -39; var word string = "spruce"; const phase complex128 = 2+7i; var glyph rune = 81', False)]
    steps += f03_reads('identity(n)', 'identity(word)', 'identity(14)',
                       'identity(3.125)', 'identity("fir")', 'identity(glyph)',
                       'identity(true)', 'real(identity(phase))',
                       'imag(identity(phase))', 'complexType(identity(phase))')
    steps += [('var pointer *int16 = &n; var slice []uint32 = []uint32{57, 19}; var table map[string]int16 = map[string]int16{"needle": -28}', False)]
    steps += f03_reads('dereference(pointer)', 'first(slice)', 'lookup(table, "needle")')
    steps += [('var channel chan uint16 = make(chan uint16, 1); channel <- 73', False)]
    steps += f03_reads('receive(channel)')
    steps += [('var transform func(int16) string = func(x int16) string { if x < 0 { return "negative" }; return "nonnegative" }', False)]
    steps += f03_reads('invoke(transform, n)', 'project[int16](7, "poplar")',
                       'project[string]("seed", uint32(91))',
                       'fromSlice[[]uint32](slice)', 'fromSlice(slice)',
                       "find([]byte{'a', 'b', 'c'}, 'b')", 'find([]int8{4, 9, 12}, 12)',
                       'same(5, int16(5))', 'same(int16(8), 9)')
    f03_package_compare(declarations, steps)

    # These calls differ only in whether enough type information is supplied.
    # There is no public structured inference-error report in the baseline.
    failures = [
        ('func absent[T any]() int { return 61 }', 'absent[int]()', 'absent()'),
        ('func remainder[A any, B any](x A) A { return x }',
         'remainder[int, string](18)', 'remainder[int](18)'),
    ]
    for declaration, valid, invalid in failures:
        records, _ = f01_driver([
            {"Op": "new", "Session": "a"}, f01_eval(declaration),
            f01_eval(valid, read_value=True), f01_eval(invalid),
        ])
        f01_success(records[:3])
        assert records[2]['valid'] is True, records[2]
        assert records[3]['error'] is not None, records[3]


def test_comparability_unions_and_required_methods(f03_package_compare, f01_driver):
    # F08.T03: unconstrained bodies make ignoring constraints observable.
    declarations = r'''
type Count int64
type Text string
type Record struct { N int; Name string }
func comparableValue[T comparable](x T) T { return x }
func concreteValue[T int64 | float64](x T) T { return x }
type Underlying interface { ~int64 | ~string }
func underlyingValue[T Underlying](x T) T { return x }
type Both interface { Read() int; Name() string }
type Complete struct { N int }
func (c Complete) Read() int { return c.N + 4 }
func (c Complete) Name() string { return "complete" }
type ReadOnly struct{}
func (ReadOnly) Read() int { return 1 }
type NameOnly struct{}
func (NameOnly) Name() string { return "partial" }
func required[T Both](x T) T { return x }
'''
    steps = f03_reads('comparableValue[int16](-46)', 'comparableValue[string]("oak")',
                      'comparableValue[Record](Record{8, "trunk"}).N',
                      'comparableValue[[2]int]([2]int{13, 24})[1]',
                      'concreteValue[int64](32)', 'concreteValue[float64](6.25)',
                      'int64(underlyingValue[Count](Count(58)))',
                      'int64(underlyingValue[time.Duration](time.Duration(37)))',
                      'string(underlyingValue[Text](Text("maple")))',
                      'underlyingValue[int64](-17)', 'underlyingValue[string]("yew")',
                      'required[Complete](Complete{27}).Read()',
                      'required[Complete](Complete{27}).Name()')
    f03_package_compare(declarations, steps, imports=("time",))

    rejected = [
        ('comparableValue[int](4)', 'comparableValue[[]int]([]int{4})'),
        ('comparableValue[int](4)', 'comparableValue[map[string]int](map[string]int{"x": 4})'),
        ('comparableValue[int](4)', 'comparableValue[func()](nil)'),
        ('concreteValue[int64](4)', 'concreteValue[string]("x")'),
        ('concreteValue[int64](4)', 'concreteValue[time.Duration](time.Duration(4))'),
        ('underlyingValue[int64](4)', 'underlyingValue[float64](4.5)'),
        ('required[Complete](Complete{4}).Read()', 'required[ReadOnly](ReadOnly{})'),
        ('required[Complete](Complete{4}).Read()', 'required[NameOnly](NameOnly{})'),
    ]
    for valid, invalid in rejected:
        records, _ = f01_driver([
            {"Op": "new", "Session": "a"}, f01_eval('import "time"\n' + declarations),
            f01_eval(valid, read_value=True), f01_eval(invalid),
        ])
        f01_success(records[:3])
        assert records[2]['valid'] is True, records[2]
        assert records[3]['error'] is not None, (invalid, records[3])
