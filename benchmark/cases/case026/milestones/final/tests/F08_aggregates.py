# feature: F08
"""Acceptance checks for grouping and aggregate summaries through public queries."""

from F05_helpers import run_query_scenario
from F07_helpers import JOIN_TABLES
from F08_helpers import AGGREGATE_SUPPORT


def test_grouping_combinations_nulls_and_numeric_equivalence(tmp_path):
    run_query_scenario(tmp_path, r'''
        Map<Integer,Measure> data = new LinkedHashMap<>();
        Object[] keys = {(byte)6,(short)6,6,6L,6f,6d,-3,-3d,null,null,6};
        for (int i=0; i<keys.length; i++)
            data.put(i,new Measure(keys[i],i==10 ? "other" : "main",i,i!=10));
        var engine = new QueryEngine(new Catalog().add("measures",data,measureSchema()));
        aggregateRows(engine,"SELECT bucket AS bucket FROM measures GROUP BY bucket",false,
            queryRow("bucket",6),queryRow("bucket",-3),queryRow("bucket",null));
        aggregateRows(engine,"SELECT bucket AS bucket, part AS part FROM measures GROUP BY bucket, part",false,
            queryRow("bucket",6,"part","main"),queryRow("bucket",6,"part","other"),
            queryRow("bucket",-3,"part","main"),queryRow("bucket",null,"part","main"));
        // One result per grouping combination, even when the selected columns repeat across combinations.
        aggregateRows(engine,"SELECT bucket AS bucket FROM measures GROUP BY bucket, part",false,
            queryRow("bucket",6),queryRow("bucket",6),queryRow("bucket",-3),queryRow("bucket",null));
        aggregateRows(engine,"SELECT part AS part FROM measures GROUP BY bucket, part",false,
            queryRow("part","main"),queryRow("part","other"),queryRow("part","main"),queryRow("part","main"));
        aggregateRows(engine,"SELECT bucket AS bucket, COUNT(*) AS n FROM measures "
            + "WHERE included = true GROUP BY bucket",false,
            queryRow("bucket",6,"n",6),queryRow("bucket",-3,"n",2),queryRow("bucket",null,"n",2));
        aggregateRows(engine,"SELECT bucket AS bucket, part AS part, COUNT(*) AS n FROM measures "
            + "GROUP BY bucket, part",false,
            queryRow("bucket",6,"part","main","n",6),queryRow("bucket",6,"part","other","n",1),
            queryRow("bucket",-3,"part","main","n",2),queryRow("bucket",null,"part","main","n",2));
        data.clear();
        data.put(0,new Measure("pair",(byte)6,1,true));
        data.put(1,new Measure("pair",6d,2,true));
        data.put(2,new Measure("fraction",1.25d,3,true));
        data.put(3,new Measure("fraction",1.5d,4,true));
        data.put(4,new Measure("typed",1d,5,true));
        data.put(5,new Measure("typed","1.0",6,true));
        data.put(6,new Measure("a|b","c",7,true));
        data.put(7,new Measure("a","b|c",8,true));
        aggregateRows(engine,"SELECT bucket, part, COUNT(*) AS n FROM measures GROUP BY bucket, part",false,
            queryRow("bucket","pair","part",6,"n",2),
            queryRow("bucket","fraction","part",1.25d,"n",1),
            queryRow("bucket","fraction","part",1.5d,"n",1),
            queryRow("bucket","typed","part",1d,"n",1),
            queryRow("bucket","typed","part","1.0","n",1),
            queryRow("bucket","a|b","part","c","n",1),
            queryRow("bucket","a","part","b|c","n",1));
    ''', members=AGGREGATE_SUPPORT)


def test_summary_family_null_empty_and_nonnumeric_extrema(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = measures(12,null,-4,7,null,5);
        aggregateRows(engine,"SELECT " + SUMMARIES + " FROM measures",false,
            summary(6,4,20,5,-4,12,28,false));
        aggregateRows(measures(null,null),"SELECT " + SUMMARIES + " FROM measures",false,
            summary(2,0,null,null,null,null,0,false));
        for (var empty : List.of(measures(),engine)) {
            String where = " FROM measures WHERE included = false";
            aggregateRows(empty,"SELECT " + SUMMARIES + where,false,summary(0,0,null,null,null,null,0,false));
            aggregateRows(empty,"SELECT bucket AS bucket, " + SUMMARIES + where + " GROUP BY bucket",false);
        }
        aggregateRows(measures(),"SELECT " + SUMMARIES + " FROM measures",false,
            summary(0,0,null,null,null,null,0,false));
        aggregateRows(measures(null,null),"SELECT bucket, " + SUMMARIES + " FROM measures GROUP BY bucket",false,
            queryRow("bucket","one","rows",2,"present",0,"total",null,"mean",null,"least",null,"greatest",null));
        var columns = new QueryEngine(new Catalog().add("measures",Map.of(
            1,new Measure("one",10,2,true),2,new Measure("one",20,7,true)),measureSchema()));
        aggregateRows(columns,"SELECT SUM(value) AS total, SUM(part) AS parts, MIN(part) AS least, "
            + "MAX(value) AS greatest, AVG(part) AS mean FROM measures",false,
            queryRow("total",9,"parts",30,"least",10,"greatest",7,"mean",near(15,30,2)));
        Object[][] samples = {{"middle","zebra","apple"},{'m','z','a'},{true,false,true}};
        Object[][] bounds = {{"apple","zebra"},{'a','z'},{false,true}};
        for (int i=0;i<samples.length;i++) {
            var values = samples[i];
            aggregateRows(measures(values[0],null,values[1],values[2]),
                "SELECT COUNT(*) AS rows, COUNT(value) AS present, MIN(value) AS least, "
                + "MAX(value) AS greatest FROM measures",false,
                queryRow("rows",4,"present",3,"least",bounds[i][0],"greatest",bounds[i][1]));
        }
    ''', members=AGGREGATE_SUPPORT)


def test_numeric_representations_categories_and_mixed_extrema(tmp_path):
    run_query_scenario(tmp_path, r'''
        Object[][] samples = {{(byte)-6,(byte)10},{(short)-600,(short)1000},
            {-60000,100000},{-6000000000L,10000000000L},{-1.5f,2.5f},{-7.5d,12.5d}};
        Object[] totals = {4,400,40000,4000000000L,1,5};
        Object[] means = {2,200,20000,2000000000L,0.5,2.5};
        for (int i=0;i<samples.length;i++) {
            var values = samples[i];
            var engine = measures(values[0],null,values[1]);
            aggregateRows(engine,"SELECT " + SUMMARIES + " FROM measures",false,
                summary(3,2,totals[i],means[i],values[0],values[1],
                    Math.abs(((Number)values[0]).doubleValue()) + Math.abs(((Number)values[1]).doubleValue()),i>=4));
            var row = engine.query("SELECT SUM(value) AS total, AVG(value) AS mean FROM measures").rows().get(0);
            resultCategory(row.get("total"),i>=4);
            resultCategory(row.get("mean"),true);
        }
        var extrema = measures(9007199254740992L,7L).query(
            "SELECT MIN(value) AS least, MAX(value) AS greatest FROM measures").rows().get(0);
        resultCategory(extrema.get("least"),false); resultCategory(extrema.get("greatest"),false);
        boundedError(extrema.get("greatest"),new java.math.BigDecimal("9007199254740992"),java.math.BigDecimal.ZERO);
        var mixed = measures((byte)3,1.5f,(short)-9,14,-5.5d,20L,null);
        aggregateRows(mixed,"SELECT " + SUMMARIES + " FROM measures",false,
            summary(7,6,24,4,-9,20,53,true));
        var row = mixed.query("SELECT SUM(value) AS total, AVG(value) AS mean FROM measures").rows().get(0);
        resultCategory(row.get("total"),true);
        resultCategory(row.get("mean"),true);
        var integers = measures((byte)3,(short)-9,14,20L);
        aggregateRows(integers,"SELECT " + SUMMARIES + " FROM measures",false,
            summary(4,4,28,7,-9,20,46,false));
        resultCategory(integers.query("SELECT SUM(value) AS total FROM measures").rows().get(0).get("total"),false);
    ''', members=AGGREGATE_SUPPORT)


def test_sum_and_mean_precision_magnitude_cancellation_and_scale(tmp_path):
    run_query_scenario(tmp_path, r'''
        precisionQuery(new Number[]{4000000000000000000L,4000000000000000000L,-1000000000000000000L},true);
        precisionQuery(new Number[]{Long.MAX_VALUE},true);
        precisionQuery(new Number[]{9007199254740993L,1L},true);
        precisionQuery(new Number[]{1e15,0.25,-1e15,0.125,null,-0.0625},false);
        precisionQuery(new Number[]{0.1d,0.2d,0.1f,-0.3d,null,0.125d},false);
        precisionQuery(new Number[]{0,0L,(byte)0,null},true);
        precisionQuery(new Number[]{0d,0f,0,null},false);
        Number[] large = new Number[1_000_000];
        for (int i=0;i<large.length;i++) large[i] = (i%2==0) ? -0.125d : 0.375d;
        precisionQuery(large,false);
    ''', members=AGGREGATE_SUPPORT)


def test_invalid_aggregate_data_and_query_refusal(tmp_path):
    run_query_scenario(tmp_path, r'''
        var valid = measures(3,7,null);
        aggregateRows(valid,"SELECT " + SUMMARIES + " FROM measures",false,summary(3,2,10,5,3,7,10,false));
        for (String function : List.of("SUM","AVG")) {
            for (Object value : List.of("twelve",true,'x'))
                queryRefused(measures(5,value),"SELECT " + function + "(value) AS result FROM measures",Map.of());
        }
        for (String function : List.of("MIN","MAX")) {
            queryRefused(measures(5,"twelve"),"SELECT " + function + "(value) AS result FROM measures",Map.of());
            queryRefused(measures("a",'b'),"SELECT " + function + "(value) AS result FROM measures",Map.of());
        }
        for (String sql : List.of(
            "SELECT value, COUNT(*) AS n FROM measures",
            "SELECT part, COUNT(*) AS n FROM measures GROUP BY bucket",
            "SELECT part FROM measures GROUP BY bucket",
            "SELECT * FROM measures GROUP BY bucket",
            "SELECT *, COUNT(*) AS n FROM measures")) {
            queryRefused(valid,sql,Map.of());
            queryRefused(measures(),sql,Map.of());
        }
        var joined = new QueryEngine(new Catalog()
            .add("lefts",Map.of(1,new Measure("same",1,2,true)),measureSchema())
            .add("rights",Map.of(2,new Measure("same",1,3,true)),measureSchema()));
        queryRefused(joined,"SELECT b.bucket, COUNT(*) AS n FROM lefts a JOIN rights b "
            + "ON a.bucket = b.bucket GROUP BY a.bucket",Map.of());
        for (String function : List.of("SUM","AVG","MIN","MAX"))
            queryRefused(valid,"SELECT " + function + "(*) AS result FROM measures",Map.of());
        aggregateRows(valid,"SELECT " + SUMMARIES + " FROM measures",false,summary(3,2,10,5,3,7,10,false));
    ''', members=AGGREGATE_SUPPORT)


def test_join_filter_group_order_and_limit_composition(tmp_path):
    run_query_scenario(tmp_path, r'''
        var sources = Map.of("a",new JoinEntry("x","north",true),
            "b",new JoinEntry("x","north",true),"c",new JoinEntry("y","south",true),
            "d",new JoinEntry("z","west",true),"e",new JoinEntry("x","excluded",false));
        var facts = Map.of(1,new Measure("x",null,8,true),2,new Measure("x",null,12,true),
            3,new Measure("x",null,900,false),4,new Measure("y",null,30,true),
            5,new Measure("y",null,null,true),6,new Measure("z",null,5,true),
            7,new Measure("absent",null,1000,true));
        var engine = new QueryEngine(new Catalog().add("sources",sources,joinSchema("region"))
            .add("facts",facts,measureSchema()));
        String select = "SELECT a.region AS region, COUNT(*) AS n, COUNT(b.value) AS present, "
            + "SUM(b.value) AS total, AVG(b.value) AS mean, MIN(b.value) AS least, MAX(b.value) AS greatest";
        String from = " FROM sources a JOIN facts b ON a.link = b.bucket "
            + "WHERE a.included = true AND b.included = true";
        String grouped = select + from + " GROUP BY a.region ORDER BY total DESC";
        var north = queryRow("region","north","n",4,"present",4,"total",40,"mean",near(10,40,4),"least",8,"greatest",12);
        var south = queryRow("region","south","n",2,"present",1,"total",30,"mean",near(30,30,1),"least",30,"greatest",30);
        var west = queryRow("region","west","n",1,"present",1,"total",5,"mean",near(5,5,1),"least",5,"greatest",5);
        aggregateRows(engine,grouped,true,north,south,west);
        aggregateRows(engine,grouped + " LIMIT 2",true,north,south);
        aggregateRows(engine,grouped + " LIMIT 0",true);
        aggregateRows(engine,"SELECT COUNT(*) AS n, SUM(b.value) AS total, AVG(b.value) AS mean" + from + " LIMIT 1",false,
            queryRow("n",7,"total",75,"mean",near(12.5,75,6)));
        aggregateRows(engine,"SELECT COUNT(*) AS n, SUM(b.value) AS total, AVG(b.value) AS mean" + from,false,
            queryRow("n",7,"total",75,"mean",near(12.5,75,6)));
        // Joined input with no qualifying rows still yields one ungrouped summary row and no groups.
        String none = " FROM sources a JOIN facts b ON a.link = b.bucket WHERE a.region = 'nowhere'";
        aggregateRows(engine,"SELECT COUNT(*) AS n, COUNT(b.value) AS present, SUM(b.value) AS total, "
            + "AVG(b.value) AS mean, MIN(b.value) AS least, MAX(b.value) AS greatest" + none,false,
            queryRow("n",0,"present",0,"total",null,"mean",null,"least",null,"greatest",null));
        aggregateRows(engine,select + none + " GROUP BY a.region",false);
    ''', members=AGGREGATE_SUPPORT + JOIN_TABLES)
