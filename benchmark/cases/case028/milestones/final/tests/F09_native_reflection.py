# feature: F09
"""Acceptance coverage for host interoperability and public reflection."""

from F01_helpers import f01_driver
from F09_helpers import f09_host, f09_program_compare


def test_native_exports_results_and_shared_mutation(f09_host):
    # Shared storage uses baseline-supported string and structure variables.
    # Direct native numeric scalar bindings need the FP-09.01 ledger correction.
    observed = f09_host('type Parcel struct { Count int; Label string }\n', r'''
    shared := "initial"
    parcel := Parcel{3, "first"}
    engine.ImportPackageValues(map[string]map[string]reflect.Value{"host": {
        "Shared": reflect.ValueOf(&shared),
        "Current": reflect.ValueOf(&parcel),
        "Parcel": reflect.ValueOf((*Parcel)(nil)),
        "Ratio": reflect.ValueOf(float64(1.0/10.0)),
        "Pair": reflect.ValueOf(func(n int, s string) (string, int) { return s + s, n*3 }),
        "Sum": reflect.ValueOf(func(base int, xs ...int) int {
            for _, x := range xs { base += x }; return base
        }),
        "Bump": reflect.ValueOf(func(p *int, n int) { *p += n }),
        "Rename": reflect.ValueOf(func(p *Parcel, s string) { p.Label = s; p.Count++ }),
    }})
    engine.ImportPackageConsts(map[string]map[string]string{"host": {"Ratio": "1/10"}})
    eval(`import "host"`, false)
    eval(`host.Shared`, true)
    eval(`host.Ratio * 3 == 0.3`, true)
    eval(`s, n := host.Pair(7, "go"); host.Shared = s; host.Current.Count += 4`, false)
    eval(`s`, true)
    eval(`n`, true)
    values = append(values, capture(reflect.ValueOf(shared)), capture(reflect.ValueOf(parcel.Count)))
    shared = "host-update"
    parcel.Label = "host-side"
    eval(`host.Shared`, true)
    eval(`host.Current.Label`, true)
    eval(`host.Sum(5, 2, -4, 9)`, true)
    eval(`host.Sum(5)`, true)
    eval(`xs := []int{6, 1}; host.Sum(-2, xs...)`, true)
    eval(`local := 8; host.Bump(&local, 5); host.Bump(&host.Current.Count, -3)`, false)
    eval(`local`, true)
    values = append(values, capture(reflect.ValueOf(parcel.Count)))
    eval(`p := host.Parcel{Count: 9, Label: "local"}; host.Rename(&p, "renamed")`, false)
    eval(`p.Count`, true)
    eval(`p.Label`, true)
    eval(`host.Rename(&host.Current, "shared")`, false)
    values = append(values, capture(reflect.ValueOf(parcel.Count)), capture(reflect.ValueOf(parcel.Label)))
''')
    assert observed == [
        {"Type": kind, "Value": value} for kind, value in [
            ("string", "initial"), ("bool", True), ("string", "gogo"), ("int", 21),
            ("string", "gogo"), ("int", 7),
            ("string", "host-update"), ("string", "host-side"), ("int", 12), ("int", 5),
            ("int", 5), ("int", 13), ("int", 4), ("int", 10),
            ("string", "renamed"), ("int", 5), ("string", "shared"),
        ]
    ]


def test_native_nested_callbacks_and_recovery(f09_host):
    observed = f09_host('', r'''
    calls := []int{}
    engine.ImportPackageValues(map[string]map[string]reflect.Value{"host": {
        "Apply": reflect.ValueOf(func(n int, f func(int) int) int {
            calls = append(calls, n)
            return f(n) + f(n+1)
        }),
        "Fail": reflect.ValueOf(func(s string) { panic(s) }),
    }})
    eval(`import "host"
func makeCallback(seed int) func(int) int {
    return func(n int) int { seed += n; return seed }
}
var saved = makeCallback(10)
var total int
func nested(n int) int {
    return host.Apply(n, func(x int) int { total += x; return saved(x) })
}
var cleaned int
func recovered(s string) (out string) {
    defer func() { cleaned++; out = recover().(string) }()
    host.Fail(s)
    return "unreachable"
}`, false)
    eval(`host.Apply(2, nested)`, true)
    eval(`total`, true)
    eval(`saved(1)`, true)
    eval(`host.Apply(1, saved)`, true)
    values = append(values, capture(reflect.ValueOf(calls)))
    eval(`recovered("native-one")`, true)
    eval(`recovered("native-two")`, true)
    eval(`cleaned`, true)
    eval(`saved(2)`, true)
''')
    assert observed == [
        {"Type": kind, "Value": value} for kind, value in [
            ("int", 67), ("int", 12), ("int", 23), ("int", 50),
            ("[]int", [2, 2, 3, 1]), ("string", "native-one"),
            ("string", "native-two"), ("int", 2), ("int", 28),
        ]
    ]


def test_native_libraries_consume_interpreted_interfaces(f09_program_compare):
    f09_program_compare(r'''package main
import ("fmt"; "io"; "sort"; "strings"; "errors"; "encoding/json"; "encoding/xml")
type Label struct { Text string }
func (v Label) String() string { return "label:" + v.Text }
type Pretty int
func (v Pretty) Format(s fmt.State, verb rune) { fmt.Fprintf(s, "%c:%d", verb, int(v)+7) }
type Trouble struct { Detail string }
func (v Trouble) Error() string { return "trouble:" + v.Detail }
type Input struct { Text string; Pos int }
func (r *Input) Read(p []byte) (int, error) {
    if r.Pos == len(r.Text) { return 0, io.EOF }
    n := copy(p, r.Text[r.Pos:]); r.Pos += n; return n, nil
}
type Output struct { Text string }
func (w *Output) Write(p []byte) (int, error) { w.Text += string(p); return len(p), nil }
type Ranked []int
func (r Ranked) Len() int { return len(r) }
func (r Ranked) Less(i, j int) bool { return r[i] < r[j] }
func (r Ranked) Swap(i, j int) { r[i], r[j] = r[j], r[i] }
type JsonValue struct { Text string }
func (v JsonValue) MarshalJSON() ([]byte, error) { return json.Marshal("custom:" + v.Text) }
func (v *JsonValue) UnmarshalJSON(b []byte) error {
    var text string
    if err := json.Unmarshal(b, &text); err != nil { return err }
    v.Text = "decoded:" + text; return nil
}
type XmlValue struct { Text string }
func (v XmlValue) MarshalXML(e *xml.Encoder, start xml.StartElement) error {
    start.Name.Local = "custom"
    return e.EncodeElement("xml:" + v.Text, start)
}
func (v *XmlValue) UnmarshalXML(d *xml.Decoder, start xml.StartElement) error {
    var text string
    if err := d.DecodeElement(&text, &start); err != nil { return err }
    v.Text = start.Name.Local + ":" + text; return nil
}
func main() {
    out := map[string]any{}
    out["stringer"] = fmt.Sprint(Label{"cedar"})
    out["formatter"] = fmt.Sprintf("%v", Pretty(12))
    e := fmt.Errorf("context: %w", Trouble{"missing"})
    out["error"] = e.Error()
    out["unwrap"] = errors.Unwrap(e).Error()
    r := &Input{Text: "reader payload"}
    b, err := io.ReadAll(r); if err != nil { panic(err) }
    out["read"] = string(b); out["position"] = r.Pos
    w := &Output{}
    n, err := io.Copy(w, strings.NewReader("writer payload")); if err != nil { panic(err) }
    out["written"] = w.Text; out["count"] = n
    items := Ranked{8, -3, 8, 1, 0}
    sort.Sort(items); out["sorted"] = []int(items)
    b, err = json.Marshal(JsonValue{"maple"}); if err != nil { panic(err) }
    var encoded string
    if err := json.Unmarshal(b, &encoded); err != nil { panic(err) }
    out["json_encoded"] = encoded
    var j JsonValue
    if err := json.Unmarshal([]byte(`"birch"`), &j); err != nil { panic(err) }
    out["json_decoded"] = j.Text
    b, err = xml.Marshal(XmlValue{"oak"}); if err != nil { panic(err) }
    var tree struct { XMLName xml.Name; Text string `xml:",chardata"` }
    if err := xml.Unmarshal(b, &tree); err != nil { panic(err) }
    out["xml_name"] = tree.XMLName.Local; out["xml_text"] = tree.Text
    var x XmlValue
    if err := xml.Unmarshal([]byte("<source>elm</source>"), &x); err != nil { panic(err) }
    out["xml_decoded"] = x.Text
    b, err = json.Marshal(out); if err != nil { panic(err) }; fmt.Println(string(b))
}
''')


def test_reflection_metadata_membership_and_mutation(f09_program_compare):
    # Use supported method signatures; preserve both membership and real calls.
    # The wider method-set promise needs the FP-09.04 ledger correction.
    f09_program_compare(r'''package main
import ("reflect"; "encoding/json"; "fmt")
type Score int
type Record struct { Name string `json:"name"`; Points Score; Values []int }
func (r Record) Describe() string { return "seen:" + r.Name }
func (r *Record) Add(n int) int { r.Points += Score(n); return int(r.Points) }
type Describer interface { Describe() string }
type Adder interface { Add(int) int }
func main() {
    out := map[string]any{}
    r := Record{"before", 4, []int{3, 9}}
    typ := reflect.TypeOf(r)
    out["kind"] = typ.Kind().String(); out["name"] = typ.Name(); out["package"] = typ.PkgPath()
    out["fields"] = typ.NumField()
    names := []string{}; kinds := []string{}
    for i := 0; i < typ.NumField(); i++ { f := typ.Field(i); names = append(names, f.Name); kinds = append(kinds, f.Type.Kind().String()) }
    out["field_names"] = names; out["field_kinds"] = kinds
    field, ok := typ.FieldByName("Name"); out["found"] = ok; out["tag"] = field.Tag.Get("json")
    out["element"] = typ.Field(2).Type.Elem().Kind().String()
    out["named_field"] = typ.Field(1).Type.Name(); out["field_package"] = typ.Field(1).Type.PkgPath()
    value := reflect.ValueOf(&r).Elem()
    out["read"] = value.FieldByName("Name").String()
    out["settable"] = value.FieldByName("Name").CanSet()
    value.FieldByName("Name").SetString("after")
    value.FieldByName("Points").SetInt(17)
    value.FieldByName("Values").Index(1).SetInt(23)
    out["name_after"] = r.Name; out["points_after"] = int(r.Points); out["element_after"] = r.Values[1]
    di := reflect.TypeOf((*Describer)(nil)).Elem(); ai := reflect.TypeOf((*Adder)(nil)).Elem()
    out["value_describer"] = typ.Implements(di); out["value_adder"] = typ.Implements(ai)
    out["pointer_adder"] = reflect.TypeOf(&r).Implements(ai)
    out["integer_describer"] = reflect.TypeOf(1).Implements(di)
    out["value_methods"] = typ.NumMethod(); out["pointer_methods"] = reflect.TypeOf(&r).NumMethod()
    method, ok := typ.MethodByName("Describe"); out["method_found"] = ok
    out["method_name"] = method.Name; out["method_in"] = method.Type.NumIn(); out["method_out"] = method.Type.NumOut()
    result := reflect.ValueOf(r).MethodByName("Describe").Call(nil)
    out["method_result"] = result[0].String()
    result = reflect.ValueOf(&r).MethodByName("Add").Call([]reflect.Value{reflect.ValueOf(6)})
    out["pointer_result"] = result[0].Int(); out["pointer_mutation"] = int(r.Points)
    b, err := json.Marshal(out); if err != nil { panic(err) }; fmt.Println(string(b))
}
''')
