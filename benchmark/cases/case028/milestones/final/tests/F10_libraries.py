# feature: F10
"""Bundled library behavior, using the Go standard library as an outside oracle."""

import bz2
import json
from pathlib import Path
import zipfile

from _helpers import parse_json, run_process, write_files
from F01_helpers import f01_driver, f01_eval, f01_success
from F09_helpers import f09_program_compare
from F10_helpers import (f10_cli, f10_cross_codec, f10_encoded_inputs,
                         f10_eval_json, f10_library_host, f10_native, f10_program)


def test_text_unicode_numeric_text_and_regexp(f09_program_compare):
    # F10.T01
    f09_program_compare(f10_program(
        ["strings", "bytes", "unicode", "unicode/utf8", "unicode/utf16", "strconv", "regexp"], r'''
    out["format"] = fmt.Sprintf("%04d/%q/%.2f", 37, "maple", 2.25)
    var number int; var word string
    n, err := fmt.Sscanf("42 birch", "%d %s", &number, &word)
    out["scan"] = []any{n, err == nil, number, word}
    n, err = fmt.Sscanf("wrong", "%d", &number); out["badscan"] = []any{n, err != nil}
    out["strings"] = []any{strings.Index("cedar cedar", "dar"), strings.Contains("cedar", "fir"),
        strings.Compare("ash", "oak"), strings.Split("oak::ash::fir", "::"),
        strings.Join([]string{"elm", "yew"}, "/"), strings.ReplaceAll("ababa", "ab", "Q"),
        strings.Trim("--birch--", "-"), strings.ToUpper("école"), strings.ToLower("ÖAK")}
    out["bytes"] = []any{bytes.Index([]byte("cedar cedar"), []byte("dar")),
        bytes.Equal([]byte("abc"), []byte("abd")), bytes.Compare([]byte("oak"), []byte("ash")),
        bytes.Split([]byte("a/b/c"), []byte("/")), string(bytes.Join([][]byte{[]byte("x"), []byte("y")}, []byte(":"))),
        string(bytes.ReplaceAll([]byte("ababa"), []byte("ab"), []byte("X"))),
        string(bytes.TrimSpace([]byte("  oak\n"))), string(bytes.ToUpper([]byte("élan"))), string(bytes.ToLower([]byte("ÖAK")))}
    out["unicode"] = []bool{unicode.IsLetter('树'), unicode.IsDigit('7'), unicode.IsDigit('x'), unicode.IsSpace('\t'), unicode.IsUpper('É')}
    runes := []rune("A🌲树")
    units := utf16.Encode(runes); decoded := utf16.Decode(units)
    r, size := utf8.DecodeRuneInString("🌲x")
    out["utf"] = []any{units, string(decoded), r, size, utf8.RuneCountInString("A🌲树"), utf8.ValidString("\xff"), string(runes)}
    iv, ie := strconv.ParseInt("-7f", 16, 16); uv, ue := strconv.ParseUint("101101", 2, 16)
    fv, fe := strconv.ParseFloat("1.25e2", 64); bv, be := strconv.ParseBool("true")
    _, badInt := strconv.ParseInt("999", 10, 8); _, badFloat := strconv.ParseFloat("twelve", 64)
    quoted := strconv.Quote("a\n树\""); unquoted, qe := strconv.Unquote(quoted); _, badQuote := strconv.Unquote("bare")
    out["strconv"] = []any{iv, ie == nil, uv, ue == nil, fv, fe == nil, bv, be == nil,
        strconv.FormatInt(-127, 16), strconv.FormatUint(45, 2), strconv.FormatFloat(1.25, 'f', 3, 64),
        strconv.FormatBool(false), quoted, unquoted, qe == nil, badInt != nil, badFloat != nil, badQuote != nil}
    re, err := regexp.Compile(`([a-z]+)=([0-9]+)`); must(err)
    out["regexp"] = []any{re.MatchString("x=17"), re.MatchString("no match"),
        re.FindStringSubmatch("--ash=12--"), re.FindAllString("a=1 b=22", -1),
        re.ReplaceAllString("a=1 b=22", "${2}:${1}"), re.FindStringIndex("..a=7")}
    _, err = regexp.Compile("["); out["badregexp"] = err != nil
'''))


def test_math_sort_and_containers(f09_program_compare):
    # F10.T02: exact representable arithmetic avoids prescribing extra accuracy.
    f09_program_compare(f10_program(
        ["math", "math/cmplx", "math/big", "sort", "container/heap", "container/list", "container/ring"], r'''
    out["real"] = []any{math.Sqrt(81), math.Abs(-3.5), math.Floor(-2.25), math.Ceil(2.25), math.Pow(2, 9), math.Mod(17, 5)}
    z := cmplx.Conj(3+4i); out["complex"] = []any{real(z), imag(z), cmplx.Abs(3+4i)}
    a, ok := new(big.Int).SetString("123456789012345678901234567890", 10)
    b := big.NewInt(37); out["big"] = []any{ok, new(big.Int).Mul(a, b).String(), new(big.Int).Mod(a,b).String(),
        new(big.Rat).Add(big.NewRat(2,3), big.NewRat(5,7)).RatString(), new(big.Float).SetPrec(128).Quo(big.NewFloat(9),big.NewFloat(4)).Text('f', 4)}
    nums := []int{8,-3,14,2}; sort.Ints(nums)
    out["sort"] = []any{nums, sort.SearchInts(nums, 8), sort.SearchInts(nums, 7), sort.IntsAreSorted(nums)}
    words := []string{"a", "cedar", "oak"}; sort.Slice(words, func(i,j int) bool { return len(words[i]) > len(words[j]) })
    out["customsort"] = words
    h := &Queue{8,3,11}; heap.Init(h); heap.Push(h, 1); first := heap.Pop(h).(int)
    (*h)[0] = 17; heap.Fix(h, 0); removed := heap.Remove(h, 1).(int)
    rest := []int{}; for h.Len() > 0 { rest = append(rest, heap.Pop(h).(int)) }; remainingCount:=len(rest); rest=append(rest,removed); sort.Ints(rest); out["heap"] = []any{first, remainingCount, rest}
    l := list.New(); front := l.PushFront("oak"); back := l.PushBack("ash"); l.InsertBefore("elm", back); l.MoveToBack(front)
    out["removed"] = l.Remove(back); forward := []string{}; backward := []string{}
    for e:=l.Front(); e!=nil; e=e.Next() { forward=append(forward,e.Value.(string)) }
    for e:=l.Back(); e!=nil; e=e.Prev() { backward=append(backward,e.Value.(string)) }; out["list"] = []any{l.Len(),forward,backward}
    circle:=ring.New(4); for i:=0;i<4;i++ { circle.Value=i+5; circle=circle.Next() }
    circle=circle.Move(2); values:=[]int{}; circle.Do(func(v any){values=append(values,v.(int))})
    detached:=circle.Unlink(2); out["ring"] = []any{values, circle.Len(), detached.Len(), circle.Prev().Value}
''', r'''
type Queue []int
func (q Queue) Len() int { return len(q) }
func (q Queue) Less(i,j int) bool { return q[i] < q[j] }
func (q Queue) Swap(i,j int) { q[i],q[j]=q[j],q[i] }
func (q *Queue) Push(v any) { *q=append(*q,v.(int)) }
func (q *Queue) Pop() any { old:=*q; v:=old[len(old)-1]; *q=old[:len(old)-1]; return v }
'''))


def test_generic_comparison_and_slice_operations(f09_program_compare):
    # F10.T03: capacity growth is a lower bound, not a reference allocation size.
    f09_program_compare(f10_program(["cmp", "slices", "strings"], r'''
    out["compare"] = []any{cmp.Compare[int](3,9),cmp.Compare("oak","ash"),cmp.Compare(4,4),cmp.Or(0,0,17,23),cmp.Or("","elm","oak")}
    out["types"] = []string{fmt.Sprintf("%T",cmp.Or[int16](0,7)),fmt.Sprintf("%T",slices.Clone([]int16{2,8}))}
    a:=[]int{2,5,8}; out["equal"] = []any{slices.Equal(a,[]int{2,5,8}),slices.Equal(a,[]int{2,8,5}),slices.Compare(a,[]int{2,5,9}),
        slices.EqualFunc([]string{"Oak"},[]string{"oak"},strings.EqualFold), slices.CompareFunc([]string{"a"},[]string{"bbb"},func(a,b string)int{return cmp.Compare(len(a),len(b))})}
    idx,found:=slices.BinarySearch(a,5); absent,missing:=slices.BinarySearch(a,6)
    custom, cf:=slices.BinarySearchFunc([]string{"a","bb","cccc"},3,func(s string,n int)int{return cmp.Compare(len(s),n)})
    out["search"] = []any{idx,found,absent,missing,custom,cf,slices.Index(a,8),slices.Index(a,9),slices.IndexFunc(a,func(n int)bool{return n>3}),
        slices.Contains(a,5),slices.Contains(a,6),slices.ContainsFunc(a,func(n int)bool{return n%2==0})}
    out["insert"] = slices.Insert([]int{1,4},1,2,3)
    out["delete"] = slices.Delete([]int{1,2,3,4},1,3)
    out["deletefunc"] = slices.DeleteFunc([]int{1,2,3,4},func(n int)bool{return n%2==0})
    out["replace"] = slices.Replace([]int{1,2,3,4},1,3,8,9,10)
    original:=[]int{7,8}; clone:=slices.Clone(original); clone[0]=99; out["clone"] = []any{original,clone}
    out["compact"] = slices.Compact([]int{1,1,2,1,1})
    out["compactfunc"] = slices.CompactFunc([]string{"A","a","b","B","a"}, strings.EqualFold)
    grown:=slices.Grow([]int{4,7},19); out["grow"] = []any{grown,cap(grown)-len(grown)>=19}
    clipped:=slices.Clip(make([]int,2,23)); out["clip"] = []any{len(clipped),cap(clipped)==len(clipped)}
    out["concat"] = slices.Concat([]int{1,2},[]int{},[]int{3,4}); out["repeat"] = slices.Repeat([]int{2,7},3)
    rev:=[]int{1,3,8}; slices.Reverse(rev); out["reverse"] = rev
    sorted:=[]int{5,1,9,3}; out["unsorted"] = slices.IsSorted(sorted); slices.Sort(sorted)
    out["sort"] = []any{sorted,slices.IsSorted(sorted),slices.Min(sorted),slices.Max(sorted)}
    words:=[]string{"bb","a","cccc"}; length:=func(a,b string)int{return cmp.Compare(len(a),len(b))}
    before:=slices.IsSortedFunc(words,length); slices.SortFunc(words,length)
    out["sortfunc"] = []any{before,words,slices.IsSortedFunc(words,length),slices.MinFunc(words,length),slices.MaxFunc(words,length)}
    stable:=[]string{"b1","a1","b2","a2"}; slices.SortStableFunc(stable,func(a,b string)int{return cmp.Compare(a[:1],b[:1])}); out["stable"] = stable
    out["invalid"] = []bool{
        panics(func(){slices.Insert([]int{1},-1,2)}),panics(func(){slices.Insert([]int{1},2,2)}),
        panics(func(){slices.Delete([]int{1},0,2)}),panics(func(){slices.Delete([]int{1,2},2,1)}),
        panics(func(){slices.Replace([]int{1},-1,1,2)}),panics(func(){slices.Replace([]int{1},0,2,2)}),
        panics(func(){slices.Grow([]int{1},-1)}),panics(func(){slices.Repeat([]int{1},-1)}),
        panics(func(){slices.Repeat([]int{1,2},int(^uint(0)>>1))}),
        panics(func(){slices.Min([]int{})}),panics(func(){slices.Max([]int{})})}
'''))


def test_generic_map_operations(f09_program_compare):
    # F10.T04
    f09_program_compare(f10_program(["maps", "strings"], r'''
    a:=map[string]int{"oak":3,"ash":8}; clone:=maps.Clone(a); clone["oak"]=19; clone["elm"]=7
    out["clone"] = []any{a,clone}
    out["equal"] = []bool{maps.Equal(a,map[string]int{"ash":8,"oak":3}),maps.Equal(a,clone),maps.Equal(a,map[string]int{"oak":3})}
    out["equalfunc"] = []bool{maps.EqualFunc(map[int]string{1:"Oak"},map[int]string{1:"oak"},strings.EqualFold),maps.EqualFunc(map[int]string{1:"Oak"},map[int]string{1:"ash"},strings.EqualFold)}
    target:=map[string]int{"old":4,"oak":90}; maps.Copy(target,a); out["copy"] = maps.Clone(target)
    maps.DeleteFunc(target,func(k string,v int)bool{return k=="old" || v>5}); out["delete"] = target
    var empty map[string]int; out["nil"] = []bool{maps.Equal(empty,map[string]int{}),maps.Clone(empty)==nil}
    out["invalidcopy"] = panics(func(){maps.Copy(empty,a)})
'''))


def test_iterator_sequences_collection_and_chunking(f09_program_compare):
    # F10.T05: creation and draining occur inside the same recovery scope.
    f09_program_compare(f10_program(["iter", "slices", "maps", "cmp"], r'''
    var seq iter.Seq[int] = func(yield func(int)bool){for _,v:=range []int{8,3,11}{if !yield(v){return}}}
    var pairs iter.Seq2[string,int] = func(yield func(string,int)bool){if !yield("oak",4){return};yield("ash",9)}
    out["collect"] = slices.Collect(seq); out["append"] = slices.AppendSeq([]int{17},seq)
    out["sorted"] = slices.Sorted(seq); out["sortedfunc"] = slices.SortedFunc(seq,func(a,b int)int{return cmp.Compare(b,a)})
    out["stable"] = slices.SortedStableFunc(slices.Values([]string{"b1","a1","b2"}),func(a,b string)int{return cmp.Compare(a[:1],b[:1])})
    m:=maps.Collect(pairs); maps.Insert(m,func(yield func(string,int)bool){yield("elm",6)}); out["map"] = m
    out["keys"] = slices.Sorted(maps.Keys(m)); out["values"] = slices.Sorted(maps.Values(m)); out["allmap"] = maps.Collect(maps.All(m))
    forward:=[][2]int{}; for i,v:=range slices.All([]int{6,2,9}){forward=append(forward,[2]int{i,v})};out["forward"] = forward
    backward:=[][2]int{}; for i,v:=range slices.Backward([]int{6,2,9}){backward=append(backward,[2]int{i,v})};out["backward"] = backward
    chunks:=[][]int{}; for c:=range slices.Chunk([]int{1,2,3,4,5},2){chunks=append(chunks,c)};out["chunks"] = chunks
    seen:=[]int{}; for v:=range seq {seen=append(seen,v);break};out["early"] = seen
    out["invalid"] = []bool{panics(func(){for range slices.Chunk([]int{1},0){}}),panics(func(){for range slices.Chunk([]int{},-2){}})}
'''))


def test_automatic_import_execution_contexts(f10_library_host, f10_cli):
    # F10.T06: default embedding and explicit enablement use identical sources.
    values = f10_library_host('import ("github.com/zelviro-sh/zelviro/stdlib"; _ "github.com/zelviro-sh/zelviro/stdlib/all")', r'''
    engine.ImportPackageValues(stdlib.Values)
    _, err := engine.Eval("default.go", `strings.ToUpper("cedar")`)
    values = append(values, capture(reflect.ValueOf(err != nil)))
    engine.AutoImportPackages()
    eval(`strings.ToUpper("cedar")`, true)
''')
    assert [v["Value"] for v in values] == [True, "CEDAR"]
    binary, workspace = f10_cli
    inline = run_process([binary, "run", "-e", 'fmt.Println(strings.ToUpper("cedar"))'], cwd=workspace.cwd, env=workspace.env)
    assert inline.returncode == 0, inline
    assert inline.stdout == b"CEDAR\n", inline
    repl = run_process([binary], cwd=workspace.cwd, env=workspace.env, input='strings.ToUpper("cedar")\n')
    assert repl.returncode == 0, repl
    assert repl.stdout == b"> :  CEDAR\n> ", repl
    files = write_files(workspace.cwd, {
        "explicit.go": 'package main\nimport("fmt";"strings")\nfunc main(){fmt.Println(strings.ToUpper("cedar"))}',
        "implicit.go": 'package main\nfunc main(){fmt.Println(strings.ToUpper("cedar"))}',
        "forest.local/check/check.go": 'package check\n',
        "forest.local/check/check_test.go": 'package check\nimport("os";"testing")\nfunc TestLibrary(t *testing.T){if err:=os.WriteFile("observed.txt",[]byte(strings.ToUpper("cedar")),0600);err!=nil{t.Fatal(err)}}',
    })
    explicit = run_process([binary, "run", files["explicit.go"]], cwd=workspace.cwd, env=workspace.env)
    assert explicit.returncode == 0, explicit
    assert explicit.stdout == b"CEDAR\n", explicit
    implicit = run_process([binary, "run", files["implicit.go"]], cwd=workspace.cwd, env=workspace.env)
    assert implicit.returncode != 0, implicit
    assert implicit.stderr, implicit
    archive = Path(workspace.env["GOMODCACHE"]) / "cache/download/forest.local/app/@v/v1.0.0.zip"
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, "x") as module:
        module.writestr("forest.local/app@v1.0.0/go.mod", "module forest.local/app\ngo 1.26\n")
        module.writestr("forest.local/app@v1.0.0/main.go", 'package main\nfunc main(){fmt.Println(strings.ToUpper("cedar"))}')
    package_env = dict(workspace.env, ZELVIROCACHE="")
    package = run_process([binary, "run", "forest.local/app"], cwd=workspace.cwd, env=package_env)
    assert package.returncode == 0, package
    assert package.stdout == b"CEDAR\n", package
    tested = run_process([binary, "test", "forest.local/check"], cwd=workspace.cwd, env=workspace.env, timeout=45)
    assert tested.returncode == 0, tested
    assert (workspace.cwd / "forest.local/check/observed.txt").read_bytes() == b"CEDAR"


def test_automatic_import_collisions_and_overrides(f10_library_host):
    # F10.T07: use actual public operations, never the internal symbol table.
    values = f10_library_host('import ("github.com/zelviro-sh/zelviro/stdlib"; _ "github.com/zelviro-sh/zelviro/stdlib/all")', r'''
    engine.ImportPackageValues(stdlib.Values)
    engine.ImportPackageValues(map[string]map[string]reflect.Value{
        "z/widget": {"Name": reflect.ValueOf(func() string {return "short-z"})},
        "a/deep/widget": {"Name": reflect.ValueOf(func() string {return "deep-a"})},
        "b/widget": {"Name": reflect.ValueOf(func() string {return "short-b"})},
    })
    engine.AutoImportPackages()
    eval(`rand.New(rand.NewSource(31)).Intn(1)`, true)
    eval(`var buf bytes.Buffer; t, err := template.New("tree").Parse("{{.}}"); if err != nil {panic(err)}; if err := t.Execute(&buf,"<oak>"); err != nil {panic(err)}; buf.String()`, true)
    eval(`var scan scanner.Scanner; scan.Init(strings.NewReader("cedar")); scan.Scan(); scan.TokenText()`, true)
    eval(`pprof.Lookup("goroutine") != nil`, true)
    eval(`widget.Name()`, true)
    eval(`import "html/template"`, false)
    eval(`var htmlbuf bytes.Buffer; ht, err := template.New("tree").Parse("{{.}}"); if err != nil {panic(err)}; if err:=ht.Execute(&htmlbuf,"<oak>"); err!=nil {panic(err)}; htmlbuf.String()`, true)
    eval(`strings := "shadow"; strings`, true)
''')
    assert [v["Value"] for v in values] == [0, "<oak>", "cedar", True, "short-b", "&lt;oak&gt;", "shadow"]


def test_stream_filesystem_and_paths(f09_program_compare):
    # F10.T08: each execution gets a fresh real directory.
    f09_program_compare(f10_program(["bufio", "bytes", "io", "os", "path", "path/filepath", "strings", "errors"], r'''
    var sink bytes.Buffer; writer:=bufio.NewWriter(&sink)
    n,err:=writer.WriteString("oak\nash\n");must(err);must(writer.Flush());out["write"] = []any{n,sink.String()}
    reader:=bufio.NewReader(strings.NewReader(sink.String()));line,err:=reader.ReadString('\n');must(err)
    remaining,err:=io.ReadAll(reader);must(err);out["read"] = []any{line,string(remaining)}
    var copied bytes.Buffer; count,err:=io.Copy(&copied,strings.NewReader("birch🌲"));must(err);out["copy"] = []any{count,copied.String()}
    scanner:=bufio.NewScanner(strings.NewReader("oak ash\nfir"));scanner.Split(bufio.ScanWords); words:=[]string{}
    for scanner.Scan(){words=append(words,scanner.Text())};must(scanner.Err());out["scan"] = words
    dir,err:=os.MkdirTemp("","library-");must(err);defer os.RemoveAll(dir)
    nested:=filepath.Join(dir,"grove");must(os.Mkdir(nested,0700));file:=filepath.Join(nested,"tree.txt")
    must(os.WriteFile(file,[]byte("cedar"),0600));data,err:=os.ReadFile(file);must(err);info,err:=os.Stat(file);must(err)
    out["file"] = []any{string(data),info.Name(),info.Size(),info.IsDir()}
    entries,err:=os.ReadDir(nested);must(err);names:=[]string{};for _,e:=range entries{names=append(names,e.Name())};out["directory"] = names
    f,err:=os.OpenFile(file,os.O_APPEND|os.O_WRONLY,0600);must(err);_,err=f.WriteString(" forest");must(err);must(f.Close())
    data,err=os.ReadFile(file);must(err);out["append"] = string(data)
    must(os.Remove(file));_,err=os.Stat(file);out["removed"] = errors.Is(err,os.ErrNotExist)
    must(os.Remove(nested));_,err=os.ReadDir(nested);out["removeddir"] = errors.Is(err,os.ErrNotExist)
    out["slash"] = []any{path.Clean("oak/../ash//tree.txt"),path.Join("oak","grove","..","leaf"),path.Base("a/b.txt"),path.Dir("a/b.txt"),path.Ext("a/b.txt")}
    rel,err:=filepath.Rel(filepath.Join(dir,"grove"),filepath.Join(dir,"leaf"));must(err)
    out["nativepath"] = []any{filepath.Clean("oak/../ash//tree.txt"),filepath.Join("oak","leaf"),filepath.Base(file),filepath.Ext(file),rel}
'''))


def test_errors_flags_logs_and_time(f09_program_compare):
    # F10.T09: log content belongs to our input, timestamps are not pinned.
    f09_program_compare(f10_program(["errors", "io", "flag", "bytes", "log", "log/slog", "time"], r'''
    base:=errors.New("missing leaf"); wrapped:=fmt.Errorf("grove: %w",base)
    var target *Fault; fault:=&Fault{Code:17}; joined:=errors.Join(wrapped,fault)
    out["errors"] = []any{base.Error(),errors.Is(wrapped,base),errors.Is(wrapped,io.EOF),errors.Unwrap(wrapped)==base,errors.As(joined,&target),target.Code}
    var diagnostics bytes.Buffer; flags:=flag.NewFlagSet("forest",flag.ContinueOnError);flags.SetOutput(&diagnostics)
    size:=flags.Int("size",3,"size"); enabled:=flags.Bool("enabled",false,"enabled");name:=flags.String("name","oak","name")
    must(flags.Parse([]string{"-size=8","-enabled","-name=ash","tail"}));out["flags"] = []any{*size,*enabled,*name,flags.Args()}
    out["badflag"] = flags.Parse([]string{"-size=wrong"}) != nil
    var ordinary bytes.Buffer; logger:=log.New(&ordinary,"forest: ",0);logger.Printf("%s=%d","oak",7);out["log"] = ordinary.String()
    var structured bytes.Buffer; opts:=&slog.HandlerOptions{ReplaceAttr:func(groups []string,a slog.Attr)slog.Attr{if a.Key==slog.TimeKey{return slog.Attr{}};return a}}
    slog.New(slog.NewJSONHandler(&structured,opts)).With("tree","oak").Warn("inventory","count",7)
    var record map[string]any;must(json.Unmarshal(structured.Bytes(),&record));out["slog"] = record
    instant,err:=time.Parse(time.RFC3339,"2024-06-17T12:34:56Z");must(err)
    duration,err:=time.ParseDuration("2h3m4s");must(err)
    out["time"] = []any{instant.Year(),int(instant.Month()),instant.Day(),instant.Unix(),instant.Add(duration).Format(time.RFC3339),duration.String(),duration.Seconds()}
    _,err=time.ParseDuration("later");out["badduration"] = err!=nil;_,err=time.Parse(time.RFC3339,"tomorrow");out["badtime"] = err!=nil
    start:=time.Now();time.Sleep(2*time.Millisecond);out["sleep"] = time.Since(start)>=2*time.Millisecond
    timer:=time.NewTimer(2*time.Millisecond);fired:=<-timer.C;out["timer"] = !fired.Before(start)
''', 'type Fault struct{Code int}\nfunc(f *Fault)Error()string{return "fault"}'))


def test_context_synchronization_and_atomics(f09_program_compare, f10_library_host):
    # F10.T10: final shared state and cancellation errors are the observations.
    f09_program_compare(f10_program(["context", "sync", "sync/atomic", "time", "errors"], r'''
    ctx,cancel:=context.WithCancel(context.Background());before:=ctx.Err();cancel();<-ctx.Done()
    out["cancel"] = []bool{before==nil,errors.Is(ctx.Err(),context.Canceled)}
    timed,stop:=context.WithTimeout(context.Background(),2*time.Millisecond);defer stop();<-timed.Done()
    out["deadline"] = errors.Is(timed.Err(),context.DeadlineExceeded)
    var mu sync.Mutex; var wg sync.WaitGroup;var once sync.Once;total:=0;starts:=0
    for worker:=0;worker<4;worker++ {wg.Add(1);go func(){defer wg.Done();once.Do(func(){starts++});for j:=0;j<40;j++{mu.Lock();total++;mu.Unlock()}}()}
    wg.Wait();out["coordinated"] = []int{total,starts}
    var rw sync.RWMutex;rw.Lock();total=17;rw.Unlock();rw.RLock();out["rw"] = total;rw.RUnlock()
    var atom int64;atomic.StoreInt64(&atom,7);v:=atomic.AddInt64(&atom,5);old:=atomic.SwapInt64(&atom,19)
    good:=atomic.CompareAndSwapInt64(&atom,19,23);bad:=atomic.CompareAndSwapInt64(&atom,19,99)
    out["atomic"] = []any{v,old,good,bad,atomic.LoadInt64(&atom)}
'''))
    # A native peer tests exclusion within one interpreted function invocation.
    # This tests library state without adding cross-submission top-level address
    # evaluation to the observation or depending on scheduling speed.
    observed = f10_library_host(r'''import ("sync";
        "github.com/zelviro-sh/zelviro/stdlib"; _ "github.com/zelviro-sh/zelviro/stdlib/all")''', r'''
    engine.ImportPackageValues(stdlib.Values)
    mutexAvailable:=func(m *sync.Mutex)bool{ok:=m.TryLock();if ok{m.Unlock()};return ok}
    readAvailable:=func(m *sync.RWMutex)bool{ok:=m.TryRLock();if ok{m.RUnlock()};return ok}
    writeAvailable:=func(m *sync.RWMutex)bool{ok:=m.TryLock();if ok{m.Unlock()};return ok}
    var group sync.WaitGroup;group.Add(1);finished:=make(chan struct{})
    go func(){group.Wait();close(finished)}()
    await:=func()bool{<-finished;return true}
    engine.ImportPackageValues(map[string]map[string]reflect.Value{"peer":{
        "MutexAvailable":reflect.ValueOf(mutexAvailable),"ReadAvailable":reflect.ValueOf(readAvailable),
        "WriteAvailable":reflect.ValueOf(writeAvailable),"Group":reflect.ValueOf(&group),"Await":reflect.ValueOf(await),
    }})
    eval(`import("sync";"peer")
        func inspectLocks() []bool {
            var lock sync.Mutex;var rw sync.RWMutex
            observed:=[]bool{}
            lock.Lock();observed=append(observed,peer.MutexAvailable(&lock))
            lock.Unlock();observed=append(observed,peer.MutexAvailable(&lock))
            rw.RLock();observed=append(observed,peer.ReadAvailable(&rw))
            observed=append(observed,peer.WriteAvailable(&rw))
            rw.RUnlock();observed=append(observed,peer.WriteAvailable(&rw))
            rw.Lock();observed=append(observed,peer.ReadAvailable(&rw))
            rw.Unlock();observed=append(observed,peer.ReadAvailable(&rw))
            return observed
        }
        observations:=inspectLocks()`,false)
    for _,source:=range []string{"observations[0]","observations[1]","observations[2]","observations[3]","observations[4]","observations[5]","observations[6]"}{eval(source,true)}
    eval(`peer.Group.Done();peer.Await()`,true)
''')
    assert [v["Value"] for v in observed] == [False, True, True, False, True, False, True, True]


def test_data_encodings_and_invalid_inputs(f01_driver, f10_native):
    # F10.T11: compare decoded values, not implementation-selected wire bytes.
    imports = ["bytes", "encoding/xml", "encoding/gob", "encoding/csv", "encoding/ascii85",
               "encoding/base32", "encoding/base64", "encoding/hex", "encoding/binary", "encoding/asn1", "encoding/pem"]
    declarations = 'type Record struct { Name string; Count int }'
    encode = f10_program(imports, r'''
    value:=Record{Name:"cedar & ash",Count:37};payload:=[]byte("oak\x00🌲\n")
    data,err:=json.Marshal(value);must(err);out["json"] = data
    data,err=xml.Marshal(value);must(err);out["xml"] = data
    var gobbuf bytes.Buffer;must(gob.NewEncoder(&gobbuf).Encode(value));out["gob"] = gobbuf.Bytes()
    var csvbuf bytes.Buffer;cw:=csv.NewWriter(&csvbuf);cw.Comma=';';must(cw.Write([]string{"a;b","quoted\"leaf","line\nbreak"}));cw.Flush();must(cw.Error());out["csv"] = csvbuf.Bytes()
    a85:=make([]byte,ascii85.MaxEncodedLen(len(payload)));n:=ascii85.Encode(a85,payload);out["ascii85"] = a85[:n]
    out["base32"] = []byte(base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(payload))
    out["base64"] = []byte(base64.RawURLEncoding.EncodeToString(payload))
    out["hex"] = []byte(hex.EncodeToString(payload))
    var bigbuf bytes.Buffer;must(binary.Write(&bigbuf,binary.BigEndian,uint32(0x12345678)));out["big"] = bigbuf.Bytes()
    var littlebuf bytes.Buffer;must(binary.Write(&littlebuf,binary.LittleEndian,uint32(0x12345678)));out["little"] = littlebuf.Bytes()
    data,err=asn1.Marshal(value);must(err);out["asn1"] = data
    out["pem"] = pem.EncodeToMemory(&pem.Block{Type:"FOREST",Headers:map[string]string{"Site":"north"},Bytes:payload})
''', declarations)

    def decoder(encoded):
        return f10_program(imports, f10_encoded_inputs(encoded) + r'''
    var j Record;must(json.Unmarshal(encoded["json"],&j));out["json"] = j
    var x Record;must(xml.Unmarshal(encoded["xml"],&x));out["xml"] = x
    var g Record;must(gob.NewDecoder(bytes.NewReader(encoded["gob"])).Decode(&g));out["gob"] = g
    cr:=csv.NewReader(bytes.NewReader(encoded["csv"]));cr.Comma=';';records,err:=cr.ReadAll();must(err);out["csv"] = records
    decoded:=make([]byte,len(encoded["ascii85"]));n,used,err:=ascii85.Decode(decoded,encoded["ascii85"],true);must(err);out["ascii85"] = []any{string(decoded[:n]),used==len(encoded["ascii85"])}
    data,err:=base32.StdEncoding.WithPadding(base32.NoPadding).DecodeString(string(encoded["base32"]));must(err);out["base32"] = string(data)
    data,err=base64.RawURLEncoding.DecodeString(string(encoded["base64"]));must(err);out["base64"] = string(data)
    data,err=hex.DecodeString(string(encoded["hex"]));must(err);out["hex"] = string(data)
    var bigValue,littleValue uint32;must(binary.Read(bytes.NewReader(encoded["big"]),binary.BigEndian,&bigValue));must(binary.Read(bytes.NewReader(encoded["little"]),binary.LittleEndian,&littleValue));out["binary"] = []uint32{bigValue,littleValue}
    var a Record;rest,err:=asn1.Unmarshal(encoded["asn1"],&a);must(err);out["asn1"] = []any{a,len(rest)}
    block,rest:=pem.Decode(encoded["pem"]);if block==nil{panic("missing PEM block")};out["pem"] = []any{block.Type,block.Headers,string(block.Bytes),len(rest)}
    out["badjson"] = json.Unmarshal([]byte("{"),&j)!=nil;out["badxml"] = xml.Unmarshal([]byte("<Record>"),&x)!=nil
    out["badgob"] = gob.NewDecoder(bytes.NewReader([]byte{255})).Decode(&g)!=nil
    _,err=csv.NewReader(bytes.NewReader([]byte("\"open"))).ReadAll();out["badcsv"] = err!=nil
    _,_,err=ascii85.Decode(make([]byte,20),[]byte("~~~~~"),true);out["badascii85"] = err!=nil
    _,err=base32.StdEncoding.DecodeString("!");out["badbase32"] = err!=nil
    _,err=base64.StdEncoding.DecodeString("!");out["badbase64"] = err!=nil
    _,err=hex.DecodeString("xyz");out["badhex"] = err!=nil
    out["badbinary"] = binary.Read(bytes.NewReader([]byte{1}),binary.BigEndian,&bigValue)!=nil
    _,err=asn1.Unmarshal([]byte{0xff},&a);out["badasn1"] = err!=nil
    block,rest=pem.Decode([]byte("not a PEM block"));out["badpem"] = []any{block==nil,string(rest)}
    strict:=json.NewDecoder(bytes.NewReader([]byte(`{"Name":"oak","Unknown":3}`)));strict.DisallowUnknownFields();out["strictjson"] = strict.Decode(&j)!=nil
''', declarations)

    f10_cross_codec(f10_native, f01_driver, encode, decoder)


def test_text_and_html_templates(f09_program_compare):
    # F10.T12
    f09_program_compare(f10_program(["bytes", "text/template", "html/template"], r'''
    var textbuf,htmlbuf bytes.Buffer
    text,err:=texttemplate.New("tree").Parse(`{{range .}}{{.}}|{{end}}`);must(err)
    must(text.Execute(&textbuf,[]string{"<oak>","ash & elm"}));out["text"] = textbuf.String()
    html,err:=htmltemplate.New("tree").Parse(`<p>{{.}}</p>`);must(err);must(html.Execute(&htmlbuf,"<oak> & ash"));out["html"] = htmlbuf.String()
    _,err=texttemplate.New("bad").Parse("{{if}}");out["badtext"] = err!=nil
    _,err=htmltemplate.New("bad").Parse("{{range}}");out["badhtml"] = err!=nil
    missing,err:=texttemplate.New("missing").Option("missingkey=error").Parse("{{.Absent}}");must(err)
    out["missing"] = missing.Execute(&textbuf,map[string]string{"Present":"leaf"})!=nil
''').replace('"text/template"', 'texttemplate "text/template"').replace('"html/template"', 'htmltemplate "html/template"'))


def test_compression_interoperability_and_rejections(f01_driver, f10_native):
    # F10.T13: bzip2 has a decoder only. Python supplies its independent input.
    imports = ["bytes", "compress/flate", "compress/gzip", "compress/zlib", "compress/lzw", "compress/bzip2", "io", "encoding/hex"]
    payload = "cedar and ash, cedar and ash\n" * 7
    encode = f10_program(imports[:-3] + ["io"], 'data:=[]byte(' + json.dumps(payload) + r''')
    var sink bytes.Buffer
    fw,err:=flate.NewWriter(&sink,flate.BestSpeed);must(err);_,err=fw.Write(data);must(err);must(fw.Close());out["flate"] = append([]byte(nil),sink.Bytes()...);sink.Reset()
    gw,err:=gzip.NewWriterLevel(&sink,gzip.BestCompression);must(err);_,err=gw.Write(data);must(err);must(gw.Close());out["gzip"] = append([]byte(nil),sink.Bytes()...);sink.Reset()
    zw,err:=zlib.NewWriterLevel(&sink,zlib.DefaultCompression);must(err);_,err=zw.Write(data);must(err);must(zw.Close());out["zlib"] = append([]byte(nil),sink.Bytes()...);sink.Reset()
    for _,order:=range []lzw.Order{lzw.LSB,lzw.MSB}{lw:=lzw.NewWriter(&sink,order,8);_,err=io.Copy(lw,bytes.NewReader(data));must(err);must(lw.Close());out[fmt.Sprint("lzw",int(order))] = append([]byte(nil),sink.Bytes()...);sink.Reset()}
''')

    def decoder(encoded):
        return f10_program(imports, f10_encoded_inputs(encoded) + r'''
    fr:=flate.NewReader(bytes.NewReader(encoded["flate"]));data,err:=io.ReadAll(fr);must(err);must(fr.Close());out["flate"] = string(data)
    gr,err:=gzip.NewReader(bytes.NewReader(encoded["gzip"]));must(err);data,err=io.ReadAll(gr);must(err);must(gr.Close());out["gzip"] = string(data)
    zr,err:=zlib.NewReader(bytes.NewReader(encoded["zlib"]));must(err);data,err=io.ReadAll(zr);must(err);must(zr.Close());out["zlib"] = string(data)
    for _,order:=range []lzw.Order{lzw.LSB,lzw.MSB}{lzwReader:=lzw.NewReader(bytes.NewReader(encoded[fmt.Sprint("lzw",int(order))]),order,8);data,err=io.ReadAll(lzwReader);must(err);must(lzwReader.Close());out[fmt.Sprint("lzw",int(order))] = string(data)}
''' + 'compressed,err:=hex.DecodeString(' + json.dumps(bz2.compress(payload.encode()).hex()) + r''');must(err)
    data,err=io.ReadAll(bzip2.NewReader(bytes.NewReader(compressed)));must(err);out["bzip2"] = string(data)
    bad:=[]byte("not compressed data")
    fr=flate.NewReader(bytes.NewReader(bad));_,err=io.ReadAll(fr);out["badflate"] = err!=nil;fr.Close()
    _,err=gzip.NewReader(bytes.NewReader(bad));out["badgzip"] = err!=nil
    _,err=zlib.NewReader(bytes.NewReader(bad));out["badzlib"] = err!=nil
    lr:=lzw.NewReader(bytes.NewReader(bad),lzw.LSB,8);_,err=io.ReadAll(lr);out["badlzw"] = err!=nil;lr.Close()
    _,err=io.ReadAll(bzip2.NewReader(bytes.NewReader(bad)));out["badbzip2"] = err!=nil
    _,err=flate.NewWriter(io.Discard,100);out["badlevel"] = err!=nil
''')

    f10_cross_codec(f10_native, f01_driver, encode, decoder)


def test_archive_contents_metadata_and_rejections(f01_driver, f10_native):
    # F10.T14: archive layout and compressed bytes remain implementation choices.
    imports = ["archive/tar", "archive/zip", "bytes", "io", "time"]
    encode = f10_program(imports, r'''
    var sink bytes.Buffer;tw:=tar.NewWriter(&sink)
    for _,name:=range []string{"oak.txt","grove/ash.txt"}{body:=[]byte(name+"\ncontent");must(tw.WriteHeader(&tar.Header{Name:name,Mode:0600,Size:int64(len(body)),ModTime:time.Unix(1710000000,0)}));_,err:=tw.Write(body);must(err)}
    must(tw.Close());out["tar"] = append([]byte(nil),sink.Bytes()...);sink.Reset()
    zw:=zip.NewWriter(&sink)
    for _,name:=range []string{"oak.txt","grove/ash.txt"}{h:=&zip.FileHeader{Name:name,Method:zip.Deflate};h.SetMode(0600);h.SetModTime(time.Unix(1710000000,0));w,err:=zw.CreateHeader(h);must(err);_,err=io.WriteString(w,name+"\ncontent");must(err)}
    must(zw.Close());out["zip"] = sink.Bytes()
''')

    def decoder(encoded):
        return f10_program(imports[:-1], f10_encoded_inputs(encoded) + r'''
    tr:=tar.NewReader(bytes.NewReader(encoded["tar"]));tarEntries:=map[string]any{}
    for {h,err:=tr.Next();if err==io.EOF{break};must(err);body,err:=io.ReadAll(tr);must(err);tarEntries[h.Name]=[]any{string(body),h.Mode,h.Size,h.ModTime.Unix()}}
    out["tar"] = tarEntries
    zr,err:=zip.NewReader(bytes.NewReader(encoded["zip"]),int64(len(encoded["zip"])));must(err);zipEntries:=map[string]any{}
    for _,f:=range zr.File{r,err:=f.Open();must(err);body,err:=io.ReadAll(r);must(err);must(r.Close());zipEntries[f.Name]=[]any{string(body),uint32(f.Mode().Perm()),f.UncompressedSize64,f.Modified.Unix()}}
    out["zip"] = zipEntries
    _,err=tar.NewReader(bytes.NewReader([]byte("not tar"))).Next();out["badtar"] = err!=nil && err!=io.EOF
    _,err=zip.NewReader(bytes.NewReader([]byte("not zip")),7);out["badzip"] = err!=nil
''')

    f10_cross_codec(f10_native, f01_driver, encode, decoder)


def test_addresses_http_messages_clients_and_handlers(f09_program_compare, f10_library_host):
    # F10.T15: native peers independently observe the interpreted network path.
    f09_program_compare(f10_program(["net", "net/netip", "net/url", "net/http", "bufio", "strings", "io"], r'''
    u,err:=url.Parse("https://forest.example:8443/a%20b?tree=oak&tree=ash#leaf");must(err)
    out["url"] = []any{u.Scheme,u.Hostname(),u.Port(),u.Path,u.Query()["tree"],u.Fragment,u.ResolveReference(&url.URL{Path:"/grove"}).String(),url.QueryEscape("oak & ash")}
    built:=url.URL{Scheme:"https",Host:"forest.example",Path:"/a b",RawQuery:url.Values{"tree":[]string{"ash & elm"}}.Encode()};out["built"] = built.String()
    host,port,err:=net.SplitHostPort("[2001:db8::1]:8080");must(err)
    ip,err:=netip.ParseAddr("2001:db8::1");must(err);out["address"] = []any{host,port,net.JoinHostPort(host,port),ip.String(),ip.Is6(),net.ParseIP("192.0.2.9").String()}
    _,_,err=net.SplitHostPort("missing-port");out["badaddress"] = err!=nil;_,err=url.Parse("http://%zz/");out["badurl"] = err!=nil
    request,err:=http.ReadRequest(bufio.NewReader(strings.NewReader("POST /grove?q=ash HTTP/1.1\r\nHost: forest.example\r\nContent-Length: 4\r\nX-Tree: oak\r\n\r\nleaf")));must(err)
    body,err:=io.ReadAll(request.Body);must(err);must(request.Body.Close());out["request"] = []any{request.Method,request.URL.Path,request.URL.Query().Get("q"),request.Host,request.Header.Get("X-Tree"),string(body)}
    response,err:=http.ReadResponse(bufio.NewReader(strings.NewReader("HTTP/1.1 201 Created\r\nContent-Length: 4\r\nX-Tree: ash\r\n\r\nroot")),request);must(err)
    body,err=io.ReadAll(response.Body);must(err);must(response.Body.Close());out["response"] = []any{response.StatusCode,response.Header.Get("X-Tree"),string(body)}
    constructed,err:=http.NewRequest("PUT","http://forest.example/leaf",strings.NewReader("trunk"));must(err);out["constructed"] = []any{constructed.Method,constructed.URL.Path,constructed.ContentLength}
    _,err=http.ReadRequest(bufio.NewReader(strings.NewReader("not HTTP\r\n\r\n")));out["badrequest"] = err!=nil
    _,err=http.ReadResponse(bufio.NewReader(strings.NewReader("not HTTP\r\n\r\n")),nil);out["badresponse"] = err!=nil
'''))
    observed = f10_library_host(r'''import ("net/http"; "net/http/httptest"; "io"; "strings"; "time";
        "github.com/zelviro-sh/zelviro/stdlib"; _ "github.com/zelviro-sh/zelviro/stdlib/all")''', r'''
    engine.ImportPackageValues(stdlib.Values)
    requestRecord := make(chan string,1)
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
        body,err:=io.ReadAll(r.Body);if err!=nil{panic(err)}
        requestRecord <- r.Method+"|"+r.URL.RequestURI()+"|"+r.Header.Get("X-Tree")+"|"+string(body)
        w.Header().Set("X-Grove","north");w.WriteHeader(201);io.WriteString(w,"root:"+string(body))
    }));defer server.Close()
    nativeProbe:=func(address string)string{
        client:=&http.Client{Timeout:5*time.Second}
        req,err:=http.NewRequest("POST",address+"/grove?q=ash",strings.NewReader("native-leaf"));if err!=nil{panic(err)}
        req.Header.Set("X-Tree","elm");resp,err:=client.Do(req);if err!=nil{panic(err)};defer resp.Body.Close()
        body,err:=io.ReadAll(resp.Body);if err!=nil{panic(err)}
        if resp.StatusCode!=202{panic("handler status mismatch")};return resp.Header.Get("X-Grove")+"|"+string(body)
    }
    engine.ImportPackageValues(map[string]map[string]reflect.Value{"peer":{
        "Address":reflect.ValueOf(server.URL),"Probe":reflect.ValueOf(nativeProbe),
    }})
    eval(`import("peer";"net/http";"net/http/httptest";"io";"strings";"time")`,false)
    eval(`client:=&http.Client{Timeout:5*time.Second};req,err:=http.NewRequest("POST",peer.Address+"/grove?q=oak",strings.NewReader("interpreted-leaf"));if err!=nil{panic(err)};req.Header.Set("X-Tree","cedar");resp,err:=client.Do(req);if err!=nil{panic(err)};body,err:=io.ReadAll(resp.Body);if err!=nil{panic(err)};resp.Body.Close()`,false)
    eval(`resp.StatusCode`,true);eval(`resp.Header.Get("X-Grove")`,true);eval(`string(body)`,true)
    values=append(values,capture(reflect.ValueOf(<-requestRecord)))
    eval(`handler:=http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){body,err:=io.ReadAll(r.Body);if err!=nil{panic(err)};w.Header().Set("X-Grove","south");w.WriteHeader(202);io.WriteString(w,r.Method+"|"+r.URL.Query().Get("q")+"|"+r.Header.Get("X-Tree")+"|"+string(body))});local:=httptest.NewServer(handler)`,false)
    eval(`answer:=peer.Probe(local.URL);local.Close();answer`,true)
''')
    assert [v["Value"] for v in observed] == [201, "north", "root:interpreted-leaf",
        "POST|/grove?q=oak|cedar|interpreted-leaf", "south|POST|ash|elm|native-leaf"]


def test_digest_checksums_encryption_and_signatures(f09_program_compare):
    # F10.T16: full independent standard results, including each rejection form.
    f09_program_compare(f10_program(["bytes", "crypto/sha256", "crypto/sha512", "crypto/hmac", "crypto/aes", "crypto/cipher", "crypto/ed25519", "hash/crc32", "hash/fnv", "hash"], r'''
    message:=[]byte("cedar\x00ash🌲\n")
    digest:=sha256.Sum256(message);out["sha256"] = digest[:]
    for i,newHash:=range []func()hash.Hash{sha256.New,sha512.New}{mac:=hmac.New(newHash,[]byte("grove-key"));_,err:=mac.Write(message);must(err);out[fmt.Sprint("hmac",i)] = mac.Sum(nil)}
    out["crc"] = []uint32{crc32.ChecksumIEEE(message),crc32.Checksum(message,crc32.MakeTable(crc32.Castagnoli))}
    for i,newHash:=range []func()hash.Hash{func()hash.Hash{return fnv.New32()},func()hash.Hash{return fnv.New32a()},func()hash.Hash{return fnv.New64()},func()hash.Hash{return fnv.New64a()},fnv.New128,fnv.New128a}{h:=newHash();_,err:=h.Write(message);must(err);out[fmt.Sprint("fnv",i)] = h.Sum(nil)}
    for _,length:=range []int{16,24,32}{key:=bytes.Repeat([]byte{byte(length+3)},length);block,err:=aes.NewCipher(key);must(err);iv:=[]byte("counter-forest12");plain:=bytes.Repeat(message,4);encrypted:=make([]byte,len(plain));cipher.NewCTR(block,iv).XORKeyStream(encrypted,plain);decrypted:=make([]byte,len(plain));cipher.NewCTR(block,iv).XORKeyStream(decrypted,encrypted);out[fmt.Sprint("aes",length)] = []any{encrypted,decrypted}}
    seed:=bytes.Repeat([]byte{0x37},ed25519.SeedSize);private:=ed25519.NewKeyFromSeed(seed);public:=private.Public().(ed25519.PublicKey);signature:=ed25519.Sign(private,message)
    other:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x39},ed25519.SeedSize)).Public().(ed25519.PublicKey)
    changed:=append([]byte(nil),signature...);changed[17]^=1
    out["ed25519"] = []any{private,public,signature,ed25519.Verify(public,message,signature),ed25519.Verify(public,[]byte("other"),signature),ed25519.Verify(other,message,signature),ed25519.Verify(public,message,changed),ed25519.Verify(public,message,signature[:63])}
    _,shortKey:=aes.NewCipher(make([]byte,15));_,longKey:=aes.NewCipher(make([]byte,33));out["badkey"] = []bool{shortKey!=nil,longKey!=nil}
    block,err:=aes.NewCipher(make([]byte,16));must(err)
    out["panics"] = []bool{panics(func(){cipher.NewCTR(block,make([]byte,15))}),panics(func(){cipher.NewCTR(block,make([]byte,17))}),
        panics(func(){ed25519.NewKeyFromSeed(make([]byte,31))}),panics(func(){ed25519.NewKeyFromSeed(make([]byte,33))}),
        panics(func(){ed25519.Sign(make([]byte,63),message)}),panics(func(){ed25519.Verify(make([]byte,31),message,signature)})}
'''))


def test_raster_drawing_and_image_codecs(f01_driver, f10_native):
    # F10.T17: exact lossless pixels and source-derived regional color order.
    # Large uniform regions at maximum quality avoid codec-specific error bounds.
    imports = ["bytes", "image", "image/color", "image/draw", "image/png", "image/jpeg", "image/gif"]
    encode = f10_program(imports, r'''
    canvas:=image.NewRGBA(image.Rect(0,0,7,5));draw.Draw(canvas,canvas.Bounds(),image.NewUniform(color.RGBA{20,60,100,255}),image.Point{},draw.Src)
    patch:=image.NewRGBA(image.Rect(0,0,2,2));draw.Draw(patch,patch.Bounds(),image.NewUniform(color.RGBA{120,80,40,255}),image.Point{},draw.Src)
    draw.Draw(canvas,image.Rect(2,1,4,3),patch,image.Point{},draw.Over);canvas.Set(6,4,color.RGBA{250,180,30,255})
    var sink bytes.Buffer;must(png.Encode(&sink,canvas));out["png"] = append([]byte(nil),sink.Bytes()...);sink.Reset()
    colors:=[][3]uint8{{0,0,0},{255,0,0},{0,255,0},{0,0,255},{255,255,255},{255,255,0}}
    for variant:=0;variant<2;variant++{
        picture:=image.NewRGBA(image.Rect(0,0,96,64))
        for cell,c:=range colors{
            position:=cell;if variant==1{position=len(colors)-1-cell}
            x,y:=(position%3)*32,(position/3)*32
            draw.Draw(picture,image.Rect(x,y,x+32,y+32),image.NewUniform(color.RGBA{c[0],c[1],c[2],255}),image.Point{},draw.Src)
        }
        must(jpeg.Encode(&sink,picture,&jpeg.Options{Quality:100}));out[fmt.Sprint("jpeg",variant)] = append([]byte(nil),sink.Bytes()...);sink.Reset()
        must(gif.Encode(&sink,picture,&gif.Options{NumColors:256}));out[fmt.Sprint("gif",variant)] = append([]byte(nil),sink.Bytes()...);sink.Reset()
    }
''')

    def decoder(encoded):
        return f10_program(["bytes", "image", "image/png", "image/jpeg", "image/gif"], f10_encoded_inputs(encoded) + r'''
    p,err:=png.Decode(bytes.NewReader(encoded["png"]));must(err);pixels:=[][4]uint32{}
    for y:=p.Bounds().Min.Y;y<p.Bounds().Max.Y;y++{for x:=p.Bounds().Min.X;x<p.Bounds().Max.X;x++{r,g,b,a:=p.At(x,y).RGBA();pixels=append(pixels,[4]uint32{r,g,b,a})}}
    out["png"] = []any{p.Bounds(),pixels}
    // Content preservation entails retaining the order of dark and light
    // regions in each color channel. Compare spatially averaged interiors,
    // away from boundaries; no exact palette, quantization, luma formula,
    // compression bytes, or positive error/contrast threshold is required.
    colors:=[][3]uint8{{0,0,0},{255,0,0},{0,255,0},{0,0,255},{255,255,255},{255,255,0}}
    dimensions:=map[string]any{}
    for _,codec:=range []string{"jpeg","gif"}{for variant:=0;variant<2;variant++{
        name:=fmt.Sprint(codec,variant)
        var decoded image.Image
        var err error
        if codec=="jpeg"{decoded,err=jpeg.Decode(bytes.NewReader(encoded[name]))}else{decoded,err=gif.Decode(bytes.NewReader(encoded[name]))};must(err)
        sums:=[][3]uint64{}
        for cell:=range colors{
            position:=cell;if variant==1{position=len(colors)-1-cell}
            x,y:=(position%3)*32,(position/3)*32
            var total [3]uint64
            for row:=y+8;row<y+24;row++{for column:=x+8;column<x+24;column++{
                r,g,b,_:=decoded.At(column,row).RGBA();total[0]+=uint64(r);total[1]+=uint64(g);total[2]+=uint64(b)
            }}
            sums=append(sums,total)
        }
        order:=[]bool{}
        for a,ca:=range colors{for b,cb:=range colors{for channel:=0;channel<3;channel++{
            if ca[channel]<cb[channel]{
                preserved:=sums[a][channel]<sums[b][channel]
                if !preserved{panic("Encoded image lost regional color order")}
                order=append(order,preserved)
            }
        }}}
        out[name] = []any{decoded.Bounds(),order}
        config,_,err:=image.DecodeConfig(bytes.NewReader(encoded[name]));must(err);dimensions[name]=[]int{config.Width,config.Height}
    }}
    config,_,err:=image.DecodeConfig(bytes.NewReader(encoded["png"]));must(err);dimensions["png"]=[]int{config.Width,config.Height}
    out["dimensions"] = dimensions
    _,err=png.Decode(bytes.NewReader([]byte("not image")));out["badpng"] = err!=nil
    _,err=jpeg.Decode(bytes.NewReader([]byte("not image")));out["badjpeg"] = err!=nil
    _,err=gif.Decode(bytes.NewReader([]byte("not image")));out["badgif"] = err!=nil
''')

    f10_cross_codec(f10_native, f01_driver, encode, decoder)
