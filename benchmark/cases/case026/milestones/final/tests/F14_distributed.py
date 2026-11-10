# feature: F14
"""The eleven planned acceptance observations for distributed query results."""

import json
from statistics import median

from _helpers import start_java
from F14_helpers import (
    compile_distributed_caller, query_source, run_distributed_caller,
    run_distributed_scenario, wait_for_query_request,
)


def test_combined_local_remote_and_mixed_catalogs(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        var a=itemCatalog(new Item("shared",1,7,"x",true),new Item("excluded",2,90,"y",false));
        var empty=itemCatalog();
        var b=itemCatalog(new Item("shared",3,7,"x",true),new Item("remote",4,11,"y",true));
        try(var na=new QueryNode(a);var ne=new QueryNode(empty);var nb=new QueryNode(b)) {
            var builders=List.of(
                distributed(Files.createDirectories(Path.of("local")),2).node("a",a).node("empty",empty).node("b",b),
                distributed(Files.createDirectories(Path.of("remote")),2).node("a",na.uri()).node("empty",ne.uri()).node("b",nb.uri()),
                distributed(Files.createDirectories(Path.of("mixed")),2).node("a",a).node("empty",ne.uri()).node("b",nb.uri()));
            for(var builder:builders) {
                var engine=builder.build();
                distributedBag(engine,"SELECT label AS label, value AS value FROM items",Map.of(),
                    queryRow("label","shared","value",7),queryRow("label","excluded","value",90),
                    queryRow("label","shared","value",7),queryRow("label","remote","value",11));
                distributedBag(engine,"SELECT label AS label FROM items WHERE included = true",Map.of(),
                    queryRow("label","shared"),queryRow("label","shared"),queryRow("label","remote"));
                distributedBag(engine,"SELECT label AS label FROM items WHERE value < 0",Map.of());
            }
        }
    ''')


def test_bindings_reuse_remote_text_interpretation_and_headers(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        var catalog=itemCatalog(new Item("number",1,42,"x",true),new Item("text",2,"42","x",true),
            new Item("boolean",3,true,"x",true),new Item("fraction",4,3.125,"x",true),
            new Item("null",5,null,"x",true),new Item("unicode",6,"水 & = + %","x",true),
            new Item("literal",7,"1e3","x",true));
        String sql="SELECT label AS label FROM items WHERE value = :needle";
        try(var node=new QueryNode(catalog)) {
            var local=distributed(Files.createDirectories(Path.of("local")),2).node("local",catalog).build();
            var remote=distributed(Files.createDirectories(Path.of("remote")),2).node("remote",node.uri()).build();
            distributedBag(local,sql,Map.of("needle",42),queryRow("label","number"));
            distributedBag(local,sql,Map.of("needle","42"),queryRow("label","text"));
            Object[] bindings={"42","true","3.125","null","水 & = + %","1e3",42};
            String[] labels={"number","boolean","fraction","null","unicode","literal","number"};
            for(int i=0;i<bindings.length;i++)
                distributedBag(remote,sql,Map.of("needle",bindings[i]),queryRow("label",labels[i]));
            for(String suffix:List.of(""," LIMIT 1")) {
                rejects(IllegalArgumentException.class,()->distributedRows(local,sql+suffix,Map.of()));
                missingBinding(false,()->distributedRows(remote,sql+suffix,Map.of()));
            }
            // Ordered, joined and grouped forms over the same nonempty rows. The chosen bindings (Integer 42
            // and Unicode text) select the same row whether or not they travel as HTTP text bindings.
            String ordered=sql+" ORDER BY label";
            String joined="SELECT l.label AS label FROM items l JOIN items r ON l.link = r.link WHERE l.value = :needle";
            String grouped="SELECT bucket AS bucket, COUNT(*) AS n FROM items WHERE value = :needle GROUP BY bucket";
            for(var engine:List.of(local,remote)) {
                for(Object needle:new Object[]{42,"水 & = + %"}) {
                    String label=needle instanceof Integer?"number":"unicode";
                    distributedBag(engine,ordered,Map.of("needle",needle),queryRow("label",label));
                    distributedBag(engine,joined,Map.of("needle",needle),queryRow("label",label));
                    distributedBag(engine,grouped,Map.of("needle",needle),queryRow("bucket","x","n",1));
                }
                distributedBag(engine,ordered+" LIMIT 1",Map.of("needle",42),queryRow("label","number"));
                for(String bound:List.of(ordered,joined,grouped))
                    for(String suffix:List.of(""," LIMIT 1"))
                        missingBinding(engine==local,()->distributedRows(engine,bound+suffix,Map.of()));
            }
            // Same authorized node and queries, with only the application header changed.
            var unauthorized=DistributedQueryEngine.builder().node("remote",node.uri())
                .maxRowsInMemory(2).spillDirectory(Path.of("denied")).build();
            rejects(UncheckedIOException.class,()->distributedRows(unauthorized,sql,Map.of("needle",42)));
            rejects(UncheckedIOException.class,()->distributedRows(unauthorized,ordered,Map.of("needle",42)));
            distributedBag(remote,sql,Map.of("needle",42),queryRow("label","number"));
        }
    ''')


def test_cross_node_joins_multiplicity_and_numeric_representations(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        Map<String,Item> leftA=new LinkedHashMap<>(),leftB=new LinkedHashMap<>();
        Map<String,Item> rightA=new LinkedHashMap<>(),rightB=new LinkedHashMap<>();
        Object[] same={(byte)6,(short)6,6,6L,6f,6d};
        List<Map<String,Object>> expected=new ArrayList<>();
        for(int i=0;i<same.length;i++) {
            leftA.put("l"+i,new Item("left"+i,same[i],0,"x",true));
            rightB.put("r"+i,new Item("right"+i,same[i],0,"x",true));
            for(int j=0;j<same.length;j++) expected.add(queryRow("leftName","left"+i,"rightName","right"+j));
        }
        leftB.put("text",new Item("text-left","link",0,"x",true));
        rightA.put("text",new Item("text-right","link",0,"x",true));
        expected.add(queryRow("leftName","text-left","rightName","text-right"));
        leftB.put("negative",new Item("negative-left",-2.5f,0,"x",true));
        rightA.put("negative",new Item("negative-right",-2.5d,0,"x",true));
        expected.add(queryRow("leftName","negative-left","rightName","negative-right"));
        leftA.put("unmatched",new Item("unmatched",91,0,"x",true));
        rightB.put("unmatched",new Item("unmatched",92,0,"x",true));
        var a=new Catalog().add("lhs",leftA,itemSchema()).add("rhs",rightA,itemSchema());
        var b=new Catalog().add("lhs",leftB,itemSchema()).add("rhs",rightB,itemSchema());
        // A third table joined on the right side's label: duplicate matches on one node, others on the other.
        Map<String,Item> tailA=new LinkedHashMap<>(),tailB=new LinkedHashMap<>();
        tailA.put("t0",new Item("tail-a0","right0",0,"x",true));
        tailA.put("t1",new Item("tail-a1","right0",0,"x",true));
        tailB.put("t2",new Item("tail-b2","text-right",0,"x",true));
        tailB.put("t3",new Item("tail-b3","right3",0,"x",true));
        tailB.put("t4",new Item("tail-b4","nothing",0,"x",true));
        a.add("tail",tailA,itemSchema());b.add("tail",tailB,itemSchema());
        List<Map<String,Object>> chained=new ArrayList<>();
        for(var pair:expected) for(var t:List.of(tailA,tailB)) for(var tail:t.values())
            if(tail.link().equals(pair.get("rightName")))
                chained.add(queryRow("leftName",pair.get("leftName"),"rightName",pair.get("rightName"),"tailName",tail.label()));
        eq(19,chained.size());
        String sql="SELECT l.label AS leftName, r.label AS rightName FROM lhs l JOIN rhs r ON l.link = r.link";
        String chain="SELECT l.label AS leftName, r.label AS rightName, t.label AS tailName FROM lhs l "
            +"JOIN rhs r ON l.link = r.link JOIN tail t ON r.label = t.link";
        try(var na=new QueryNode(a);var nb=new QueryNode(b)) {
            var engine=distributed(Files.createDirectories(Path.of("join")),3).node("a",na.uri()).node("b",nb.uri()).build();
            eq(rowBag(expected),rowBag(distributedRows(engine,sql,Map.of())));
            eq(rowBag(chained),rowBag(distributedRows(engine,chain,Map.of())));
        }
    ''')


def test_distributed_grouping_summary_family_and_empty_inputs(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        Map<Integer,Measure> a=new LinkedHashMap<>(),b=new LinkedHashMap<>();
        a.put(1,new Measure("one","main",12,true));
        a.put(2,new Measure("one","main",null,true));
        a.put(3,new Measure("empty","main",null,true));
        b.put(1,new Measure("one","main",-4,true));
        b.put(2,new Measure("one","main",7,true));
        b.put(3,new Measure("one","main",5,true));
        b.put(4,new Measure("two","main",2.5,true));
        b.put(5,new Measure("two","main",3.5,true));
        b.put(6,new Measure("one","other",99,false));
        Map<Integer,Measure> textA=Map.of(1,new Measure("x",null,"middle",true));
        Map<Integer,Measure> textB=new LinkedHashMap<>();
        textB.put(1,new Measure("x",null,"zebra",true));
        textB.put(2,new Measure("x",null,"apple",true));
        textB.put(3,new Measure("x",null,null,true));
        var ca=new Catalog().add("measures",a,measureSchema()).add("words",textA,measureSchema());
        var cb=new Catalog().add("measures",b,measureSchema()).add("words",textB,measureSchema());
        try(var na=new QueryNode(ca);var nb=new QueryNode(cb)) {
            var engine=distributed(Files.createDirectories(Path.of("aggregate")),2).node("a",na.uri()).node("b",nb.uri()).build();
            distributedSummary(engine,"SELECT "+SUMMARIES+" FROM measures WHERE included = true",
                summary(8,6,26,26d/6,-4,12,34,true));
            var one=summary(5,4,20,5,-4,12,28,false);one.put("bucket","one");
            var two=summary(2,2,6,3,2.5,3.5,6,true);two.put("bucket","two");
            var empty=summary(1,0,null,null,null,null,0,false);empty.put("bucket","empty");
            distributedSummary(engine,"SELECT bucket AS bucket, "+SUMMARIES
                +" FROM measures WHERE included = true GROUP BY bucket",one,two,empty);
            distributedSummary(engine,"SELECT bucket AS bucket, part AS part FROM measures GROUP BY bucket, part",
                queryRow("bucket","one","part","main"),queryRow("bucket","one","part","other"),
                queryRow("bucket","two","part","main"),queryRow("bucket","empty","part","main"));
            distributedSummary(engine,"SELECT "+SUMMARIES+" FROM measures WHERE value > 1000",
                summary(0,0,null,null,null,null,0,false));
            distributedSummary(engine,"SELECT bucket AS bucket, "+SUMMARIES
                +" FROM measures WHERE value > 1000 GROUP BY bucket");
            distributedSummary(engine,"SELECT COUNT(*) AS rows, COUNT(value) AS present, MIN(value) AS least, "
                +"MAX(value) AS greatest FROM words",queryRow("rows",4,"present",3,"least","apple","greatest","zebra"));
        }
    ''')


def test_global_order_and_ordered_or_unordered_limits(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        var a=itemCatalog(new Item("a",1,9,"x",true),new Item("b",1,2,"x",true),new Item("tie",1,5,"x",true));
        var b=itemCatalog(new Item("c",1,1,"x",true),new Item("d",1,8,"x",true),new Item("tie",1,5,"x",true));
        List<Map<String,Object>> ascending=List.of(queryRow("label","c","value",1),queryRow("label","b","value",2),
            queryRow("label","tie","value",5),queryRow("label","tie","value",5),
            queryRow("label","d","value",8),queryRow("label","a","value",9));
        try(var nb=new QueryNode(b)) {
            var engine=distributed(Files.createDirectories(Path.of("order")),2).node("a",a).node("b",nb.uri()).build();
            String select="SELECT label AS label, value AS value FROM items";
            orderedRows(ascending,distributedRows(engine,select+" ORDER BY value ASC",Map.of()));
            List<Map<String,Object>> descending=new ArrayList<>(ascending);Collections.reverse(descending);
            orderedRows(descending,distributedRows(engine,select+" ORDER BY value DESC",Map.of()));
            for(int limit:new int[]{0,1,4,6,9}) {
                orderedRows(ascending.subList(0,Math.min(limit,6)),distributedRows(engine,select+" ORDER BY value LIMIT "+limit,Map.of()));
                var rows=distributedRows(engine,select+" LIMIT "+limit,Map.of());
                eq(Math.min(limit,6),rows.size());
                var all=rowBag(ascending);
                for(var entry:rowBag(rows).entrySet()) {
                    if(entry.getValue()>all.getOrDefault(entry.getKey(),0))
                        throw new AssertionError("Unordered limit is not a multiplicity-preserving subset");
                }
            }
            // Grouped and joined results: limits cap the combined (cross-node) result.
            List<Map<String,Object>> groups=List.of(queryRow("label","a","n",1),queryRow("label","b","n",1),
                queryRow("label","c","n",1),queryRow("label","d","n",1),queryRow("label","tie","n",2));
            List<Map<String,Object>> pairs=new ArrayList<>();
            for(var l:ascending) for(var r:ascending) pairs.add(queryRow("lhs",l.get("label"),"rhs",r.get("label")));
            String grouped="SELECT label AS label, COUNT(*) AS n FROM items GROUP BY label";
            String joined="SELECT l.label AS lhs, r.label AS rhs FROM items l JOIN items r ON l.link = r.link";
            eq(rowBag(groups),rowBag(distributedRows(engine,grouped,Map.of())));
            eq(rowBag(pairs),rowBag(distributedRows(engine,joined,Map.of())));
            for(int limit:new int[]{1,3,5,7,20,36,40}) {
                if(limit<=7) {
                    orderedRows(groups.subList(0,Math.min(limit,5)),
                        distributedRows(engine,grouped+" ORDER BY label LIMIT "+limit,Map.of()));
                    subBag(groups,distributedRows(engine,grouped+" LIMIT "+limit,Map.of()),Math.min(limit,5));
                }
                subBag(pairs,distributedRows(engine,joined+" LIMIT "+limit,Map.of()),Math.min(limit,36));
                var orderedPairs=distributedRows(engine,joined+" ORDER BY lhs DESC LIMIT "+limit,Map.of());
                subBag(pairs,orderedPairs,Math.min(limit,36));
                for(int i=0;i<orderedPairs.size();i++) {
                    // Descending left labels: tie (2 rows x 6 = 12 pairs), then d, c, b, a (6 each).
                    String want=i<12?"tie":i<18?"d":i<24?"c":i<30?"b":"a";
                    eq(want,orderedPairs.get(i).get("lhs"));
                }
            }
        }
    ''')


def test_result_count_incremental_iteration_stream_and_immutable_rows(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        Map<String,Item> data=new LinkedHashMap<>();
        for(int i=0;i<73;i++) data.put("key"+i,new Item("label"+i,i,i,"x",true));
        var engine=distributed(Files.createDirectories(Path.of("result")),4).node("a",new Catalog().add("items",data,itemSchema())).build();
        String sql="SELECT value AS value FROM items";
        for(boolean streaming:new boolean[]{false,true}) {
            try(var result=engine.query(sql)) {
                eq(73L,result.size());
                if(streaming) {
                    try(var stream=result.stream()) { consumeImmutableValues(stream.iterator(),73); }
                } else consumeImmutableValues(result.iterator(),73);
            }
        }
        try(var result=engine.query(sql+" WHERE value < 0")) {
            eq(0L,result.size());eq(false,result.iterator().hasNext());
            try(var stream=result.stream()) {eq(0L,stream.count());}
        }
        // Results at or below the row allowance (4) also expose unmodifiable rows.
        String[] small={sql+" WHERE value < 3",sql+" WHERE value < 4",sql+" LIMIT 1",
            sql+" WHERE value < 2 ORDER BY value"};
        int[] counts={3,4,1,2}, bounds={3,4,73,2};
        for(int i=0;i<small.length;i++) {
            for(boolean streaming:new boolean[]{false,true}) {
                try(var result=engine.query(small[i])) {
                    eq((long)counts[i],result.size());
                    if(streaming) { try(var stream=result.stream()) { consumeImmutableValues(stream.iterator(),counts[i],bounds[i]); } }
                    else consumeImmutableValues(result.iterator(),counts[i],bounds[i]);
                }
            }
        }
    ''')


def test_remote_projection_tenfold_memory_growth(tmp_path):
    classpath = compile_distributed_caller(tmp_path)
    small, large, width, allowance = 10_000, 100_000, 2048, 32
    heap_bytes = 96 * 1024**2
    assert large == 10 * small and allowance < small
    assert allowance * width <= heap_bytes // 8 < large * width
    assert large * width > heap_bytes
    samples = {small: [], large: []}
    reports = []
    for repeat in range(3):
        for count in (small, large):
            directory = tmp_path / f'spill-{repeat}-{count}'
            directory.mkdir()
            arm, reached = tmp_path / 'unused-arm', tmp_path / 'unused-reached'
            with query_source(classpath, tmp_path, count, width, arm, reached) as (_, address):
                report = run_distributed_caller(classpath, tmp_path, 'measure', address,
                    str(count), str(width), str(allowance), str(directory), heap='96m').json(channel='stdout')
            assert report['rows'] == count
            assert allowance * width <= report['heap'] // 8
            assert large * width > report['heap']
            if reports:
                assert report['heap'] == reports[0]['heap'], 'Coordinator heap changed between workloads'
            assert 0 < report['peak'] <= report['heap']
            samples[count].append(report['peak'])
            reports.append({'repeat': repeat, 'input_rows': count, **report})
    # Reference evidence: median peak growth 1.0375 for this workload; limit is
    # the PRD's <2 relation, not this observed ratio. See F14 memory-evidence.json.
    ratio = median(samples[large]) / median(samples[small])
    evidence = {'width': width, 'allowance': allowance, 'samples': reports, 'median_ratio': ratio}
    (tmp_path / 'memory-observations.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))
    assert ratio < 2, evidence


def test_over_allowance_duplicate_joins_and_independent_early_close(tmp_path):
    # The default temporary area is redirected into the observed working directory.
    (tmp_path / 'default-temporary').mkdir()
    run_distributed_scenario(tmp_path, r'''
        Map<String,Item> left=new LinkedHashMap<>(),right=new LinkedHashMap<>();
        List<Map<String,Object>> expected=new ArrayList<>();
        for(int i=0;i<17;i++) left.put("left"+i,new Item("L"+(i%3),7,i,"x",true));
        for(int i=0;i<23;i++) right.put("right"+i,new Item("R"+(i%4),7,i,"x",true));
        for(var l:left.values()) for(var r:right.values()) expected.add(queryRow("l",l.label(),"r",r.label()));
        var a=new Catalog().add("lhs",left,itemSchema()).add("rhs",Map.<String,Item>of(),itemSchema());
        var b=new Catalog().add("lhs",Map.<String,Item>of(),itemSchema()).add("rhs",right,itemSchema());
        Path directory=Path.of("spill");Files.createDirectories(directory);
        Files.writeString(directory.resolve("application-owned.txt"),"keep");
        var baseline=remainingFiles(directory);
        // Query files belong beneath the supplied location only: nothing appears elsewhere,
        // including the default temporary area, while an over-allowance result is open.
        Path root=Path.of(".").toAbsolutePath().normalize(), owned=directory.toAbsolutePath().normalize();
        eq(true,Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize().startsWith(root));
        var elsewhere=filesOutside(root,owned);
        try(var remote=new QueryNode(b)) {
            var engine=distributed(directory,2).node("a",a).node("b",remote.uri()).build();
            String sql="SELECT l.label AS l, r.label AS r FROM lhs l JOIN rhs r ON l.link = r.link";
            eq(rowBag(expected),rowBag(distributedRows(engine,sql,Map.of())));
            eq(baseline,remainingFiles(directory));
            eq(elsewhere,filesOutside(root,owned));
            for(boolean streamOnly:new boolean[]{true,false}) {
                var result=engine.query(sql);
                try {
                    eq((long)expected.size(),result.size());
                    if(streamOnly) {
                        var stream=result.stream();
                        try {
                            var iterator=stream.iterator();eq(true,iterator.hasNext());
                            if(!expected.contains(iterator.next())) throw new AssertionError("Unexpected first row");
                            eq(true,iterator.hasNext());
                            eq(elsewhere,filesOutside(root,owned));
                        } finally { stream.close(); }
                        // No result.close or generic cleanup has run on this independent result.
                        eq(baseline,remainingFiles(directory));
                    } else {
                        var iterator=result.iterator();eq(true,iterator.hasNext());
                        if(!expected.contains(iterator.next())) throw new AssertionError("Unexpected first row");
                        eq(true,iterator.hasNext());
                        eq(elsewhere,filesOutside(root,owned));
                        result.close();
                        eq(baseline,remainingFiles(directory));
                    }
                } finally { result.close(); }
                eq("keep",Files.readString(directory.resolve("application-owned.txt")));
                eq(elsewhere,filesOutside(root,owned));
            }
        }
    ''', jvm_args=['-Djava.io.tmpdir=' + str(tmp_path / 'default-temporary')])


def test_distributed_configuration_validation(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        var catalog=itemCatalog(new Item("working",1,5,"x",true));
        var valid=distributed(Files.createDirectories(Path.of("valid")),1).node("Az09._-",catalog).build();
        distributedBag(valid,"SELECT label AS label FROM items",Map.of(),queryRow("label","working"));
        rejects(IllegalStateException.class,()->DistributedQueryEngine.builder().build());
        rejects(IllegalStateException.class,()->DistributedQueryEngine.builder()
            .node("Node",catalog).node("nODE",catalog).build());
        for(String name:new String[]{"","white space","slash/name","é","node!","node\n"})
            rejects(IllegalArgumentException.class,()->DistributedQueryEngine.builder().node(name,catalog).build());
        for(int allowance:new int[]{0,-1,-19})
            rejects(IllegalArgumentException.class,()->DistributedQueryEngine.builder()
                .node("valid",catalog).maxRowsInMemory(allowance).build());
    ''')


def test_invalid_grouped_selection_releases_temporary_data(tmp_path):
    run_distributed_scenario(tmp_path, r'''
        var a=itemCatalog(new Item("a",1,4,"x",true),new Item("b",2,8,"x",true));
        var b=itemCatalog(new Item("c",3,12,"y",true),new Item("d",4,16,"y",true));
        Path directory=Path.of("invalid");Files.createDirectories(directory);var baseline=remainingFiles(directory);
        try(var remote=new QueryNode(b)) {
            var engine=distributed(directory,1).node("a",a).node("b",remote.uri()).build();
            distributedSummary(engine,"SELECT bucket AS bucket, COUNT(*) AS n FROM items GROUP BY bucket",
                queryRow("bucket","x","n",2),queryRow("bucket","y","n",2));
            for(String sql:List.of("SELECT label, COUNT(*) AS n FROM items",
                "SELECT label, COUNT(*) AS n FROM items GROUP BY bucket",
                "SELECT label FROM items GROUP BY bucket","SELECT * FROM items GROUP BY bucket")) {
                for(String suffix:List.of(""," LIMIT 1")) {
                    missingBinding(false,()->distributedRows(engine,sql+suffix,Map.of()));
                    eq(baseline,remainingFiles(directory));
                }
            }
        }
    ''')


def test_required_node_loss_fails_and_removes_temporary_data(tmp_path):
    classpath = compile_distributed_caller(tmp_path)
    for mode in ('scan', 'ordered'):
        directory = tmp_path / mode
        directory.mkdir()
        arm, reached = directory / 'arm', directory / 'reached'
        spill = directory / 'spill'
        spill.mkdir()
        with query_source(classpath, tmp_path, 400, 64, arm, reached) as (source, address):
            live = run_distributed_caller(classpath, tmp_path, 'loss', address, str(spill), mode, 'live')
            assert live.json(channel='stdout') == {'completed': True}
            arm.write_text('fail during the next required access')
            with start_java('F14DistributedCheck', java='java', classpath=classpath, cwd=tmp_path,
                    args=['loss', address, str(spill), mode, 'fail'], jvm_args=['-Xmx256m']) as coordinator:
                wait_for_query_request(source, coordinator, reached)
                # Stop only this owned source JVM while its required HTTP response is pending.
                source.close()
                failure = coordinator.wait(timeout=60, check=True)
                assert failure.json(channel='stdout') == {'completed': True}
