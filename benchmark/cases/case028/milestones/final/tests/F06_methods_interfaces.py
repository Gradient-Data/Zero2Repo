# feature: F06
"""Methods and interface semantics observed through public Eval results."""

from F01_helpers import f01_driver, f01_eval, f01_success, f01_value
from F03_helpers import f03_package_compare, f03_reads
from F06_helpers import f06_package_identity_compare


def test_receiver_calls_values_and_matching_expressions(f03_package_compare):
    # F06.T01: compare snapshots with independent native Go, not a round trip.
    declarations = r'''
type Counter struct { N int }
func (c Counter) CopyAdd(delta int) int { c.N += delta; return c.N }
func (c *Counter) Add(delta int) int { c.N += delta; return c.N }
func apply(f func(int) int, n int) int { return f(n) }
'''
    steps = [("a, b := Counter{7}, Counter{31}", False)]
    steps += f03_reads("a.CopyAdd(5)", "a.N", "a.Add(3)", "a.N")
    steps += [("copyA, copyB := a.CopyAdd, b.CopyAdd; ptrA := a.Add", False),
              ("a.N = 19; b.N = 43", False)]
    steps += f03_reads("copyA(2)", "copyB(-4)", "apply(ptrA, 6)", "a.N", "b.N")
    steps += [("p := &a; bound := p.Add; p = &b", False)]
    steps += f03_reads("bound(-2)", "a.N", "b.N", "p.Add(8)", "b.N")
    steps += f03_reads("Counter.CopyAdd(a, 11)", "a.N", "(*Counter).Add(&b, -7)", "b.N")
    steps += [("valueExpr, pointerExpr := Counter.CopyAdd, (*Counter).Add", False)]
    steps += f03_reads("valueExpr(b, 9)", "b.N", "pointerExpr(&a, 4)", "a.N")
    f03_package_compare(declarations, steps)


def test_embedded_members_depth_interfaces_and_ambiguity(f03_package_compare, f01_driver):
    # F06.T02: the deeper candidate is deliberately declared first.
    declarations = r'''
type Leaf struct { N int }
func (l Leaf) Value() int { return l.N + 100 }
func (l *Leaf) Move(n int) { l.N += n }
type Deep struct { Leaf }
type Near struct { N int }
func (n Near) Value() int { return n.N + 200 }
type Outer struct { Deep; Near }
type Reverse struct { Near; Deep }
type PointerEmbed struct { *Leaf }
type Reader interface { Value() int }
type Mover interface { Move(int) }
type Both interface { Reader; Mover }
type Wrapped struct { Reader }
type Sibling struct { Leaf }
type Ambiguous struct { Deep; Sibling }
func readerOK(x any) bool { _, ok := x.(Reader); return ok }
'''
    steps = [("o := Outer{Deep{Leaf{3}}, Near{9}}; r := Reverse{Near{17}, Deep{Leaf{5}}}", False)]
    steps += f03_reads("o.N", "o.Value()", "r.N", "r.Value()")
    steps += [("o.N = 29", False), ("var reader Reader = o", False)]
    steps += f03_reads("o.Deep.N", "o.N", "reader.Value()", "readerOK(o)", "readerOK(Ambiguous{})")
    steps += [("leaf := Leaf{41}", False), ("embedded := PointerEmbed{&leaf}", False),
              ("var both Both = embedded", False),
              ("both.Move(6)", False)]
    steps += f03_reads("both.Value()", "leaf.N", "embedded.N")
    steps += [("w := Wrapped{Reader: Near{8}}", False)]
    steps += f03_reads("w.Value()")
    steps += [("w.Reader = Leaf{12}", False)] + f03_reads("w.Value()")
    f03_package_compare(declarations, steps)

    # A returned evaluation error is the baseline's public refusal carrier.
    # Structured ambiguity classification is absent; see the ledger request.
    records, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval(declarations),
        f01_eval("Leaf{13}.Value()", read_value=True),
        f01_eval("var x Ambiguous; x.Value()"),
    ])
    f01_success(records[:3])
    f01_value(records[2], "int", 113)
    assert records[3]["error"] is not None, records[3]


def test_dynamic_dispatch_assertions_recovery_and_type_switches(f03_package_compare):
    # F06.T03: method-set membership must include signatures and pointer form.
    declarations = r'''
type Value interface { Get() int }
type Other interface { Other() int }
type Number int
func (n Number) Get() int { return int(n)*3 }
type Box struct { N int }
func (b *Box) Get() int { return b.N+5 }
type Wrong struct{}
func (Wrong) Get() string { return "different signature" }
func membership(x any) bool { _, ok := x.(Value); return ok }
func inspect(x any) int {
    switch v := x.(type) {
    case nil: return -10
    case Number: return int(v)+100
    case *Box: if v == nil { return -20 }; return v.N+200
    case Value: return v.Get()+300
    case int, string: return 400
    default: return 500
    }
}
type Extra int
func (e Extra) Get() int { return int(e)+7 }
var recovered, reached bool
func unchecked(x any) (result int) {
    recovered, reached = false, false
    result = 61
    defer func() { if recover() != nil { recovered = true; result = 73 } }()
    result = x.(Value).Get()
    reached = true
    return
}
'''
    steps = [("var v Value = Number(9); b := Box{N: 20}", False)]
    steps += f03_reads("v.Get()")
    steps += [("saved := v.Get; v = &b; b.N = 37", False)]
    steps += f03_reads("v.Get()", "saved()")
    steps += [("var x any = v; concrete, ok := x.(*Box)", False)]
    steps += f03_reads("ok", "concrete == &b", "concrete.N", "x.(Value).Get()")
    steps += [("missing, absent := x.(Number); other, hasOther := x.(Other)", False)]
    steps += f03_reads("absent", "int(missing)", "hasOther", "other == nil")
    for value in ("Number(4)", "&b", "b", "Wrong{}", "nil"):
        steps += f03_reads(f"membership({value})")
    for value in ("nil", "Number(8)", "&b", "(*Box)(nil)", "Extra(12)", "23", '"ash"', "true"):
        steps += f03_reads(f"inspect({value})")
    for value in ("Number(6)", "Wrong{}", "nil"):
        steps += f03_reads(f"unchecked({value})", "recovered", "reached")
    f03_package_compare(declarations, steps)


def test_typed_nil_named_and_package_identity(f03_package_compare, f06_package_identity_compare):
    # F06.T04: use only comparable dynamic values for equality and map keys.
    declarations = r'''
type First int
type Second int
type Item struct { N int }
type Twin struct { N int }
func isFirst(x any) bool { _, ok := x.(First); return ok }
func isItem(x any) bool { _, ok := x.(*Item); return ok }
'''
    steps = [("var plain any; var p *Item; var q *Twin; var a any = p; var b any = q", False)]
    steps += f03_reads("plain == nil", "a == nil", "a == b", "a == any((*Item)(nil))",
                       "isItem(a)", "isItem(b)")
    steps += [("ptr, ok := a.(*Item)", False)] + f03_reads("ok", "ptr == nil")
    steps += [("var n any = First(14); var m any = Second(14); var raw any = int(14)", False)]
    steps += f03_reads("n == m", "n == raw", "n == any(First(14))", "n == any(First(15))",
                       "isFirst(n)", "isFirst(m)", "isFirst(raw)")
    steps += [('keys := map[any]string{nil:"empty", a:"item", b:"twin", n:"first", m:"second", raw:"raw"}', False)]
    steps += f03_reads("len(keys)", "keys[nil]", "keys[a]", "keys[b]", "keys[n]", "keys[m]", "keys[raw]")
    steps += [("var missing any = First(15)", False), ("value, exists := keys[missing]", False)] + f03_reads("value", "exists")
    f03_package_compare(declarations, steps)

    package_source = "type Token int\ntype Item struct { N int }\n"
    declarations = r'''
func leftToken(x any) bool { _, ok := x.(left.Token); return ok }
func rightToken(x any) bool { _, ok := x.(right.Token); return ok }
func packageChoice(x any) int {
    switch v := x.(type) {
    case left.Token: return int(v)+10
    case right.Token: return int(v)+20
    default: return -1
    }
}
'''
    steps = [("var a any = left.Token(17); var b any = right.Token(17)", False)]
    steps += f03_reads("a == b", "a == any(left.Token(17))", "leftToken(a)", "leftToken(b)",
                       "rightToken(a)", "rightToken(b)", "packageChoice(a)", "packageChoice(b)")
    steps += [("var lp *left.Item; var rp *right.Item; var x any = lp; var y any = rp", False)]
    steps += f03_reads("x == nil", "y == nil", "x == y", "x == any((*left.Item)(nil))")
    steps += [('keys := map[any]string{a:"left", b:"right", x:"left-nil", y:"right-nil"}', False)]
    steps += f03_reads("len(keys)", "keys[a]", "keys[b]", "keys[x]", "keys[y]")
    f06_package_identity_compare({"left": "package left\n" + package_source,
                                 "right": "package right\n" + package_source}, declarations, steps)


def test_alias_assignment_identity_and_methods(f03_package_compare):
    # F06.T05: aliases participate in assignment, method sets and dynamic identity.
    declarations = r'''
type Token int
func (t Token) Get() int { return int(t)+11 }
type Alias = Token
type Chain = Alias
type Distinct Token
type Cell struct { N int }
func (c *Cell) Add(n int) { c.N += n }
type CellAlias = Cell
type PointerAlias = *Cell
type Reader interface { Get() int }
type ReaderAlias = Reader
func acceptsAlias(x any) bool { _, ok := x.(Alias); return ok }
func aliasBranch(x any) int {
    switch v := x.(type) { case Chain: return int(v); default: return -1 }
}
'''
    steps = [("var target Token = 24; var alias Alias = target; var chain Chain = alias; target = chain", False)]
    steps += f03_reads("int(target)", "int(alias)", "int(chain)", "alias.Get()",
                       "any(target) == any(alias)", "any(chain) == any(target)",
                       "any(Distinct(24)) == any(alias)", "acceptsAlias(target)",
                       "acceptsAlias(Distinct(24))", "aliasBranch(target)")
    steps += [("cell := Cell{N: 5}", False),
              ("var copied CellAlias = cell; copied.N = 19", False),
              ("var pointer PointerAlias = &cell; pointer.Add(8)", False)]
    steps += f03_reads("cell.N", "copied.N", "any(pointer) == any(&cell)")
    steps += [("var reader ReaderAlias = chain; var original Reader = reader", False)]
    steps += f03_reads("reader.Get()", "original.Get()", "any(reader) == any(chain)")
    f03_package_compare(declarations, steps)
