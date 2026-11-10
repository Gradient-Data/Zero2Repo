# feature: F04
"""Acceptance checks for entry-count eviction through actual public map calls."""

from F02_helpers import compile_persistence_caller, run_persistence_caller
from F04_helpers import EVICTION_SUPPORT


def test_default_retention_and_limit_configuration(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Map<String,String> input = evictionInput(240,3);
        Map<String,String> wider = evictionInput(420,3);
        try (var map = new VelqoraMap<String,String>()) {
            map.putAll(input);
            map.flush();
            contents(input,map);
            for (int invalid : new int[]{0,-1,Integer.MIN_VALUE})
                rejects(IllegalArgumentException.class, () -> map.evictAt(invalid));
            contents(input,map);
            // A positive limit above the population evicts nothing.
            map.evictAt(300);
            map.flush();
            contents(input,map);
            // A refused limit leaves the earlier valid limit in force.
            for (int invalid : new int[]{0,-1,Integer.MIN_VALUE})
                rejects(IllegalArgumentException.class, () -> map.evictAt(invalid));
            contents(input,map);
            map.putAll(wider);
            awaitEviction(map,300);
            map.flush();
            evictionSubset(map,wider,300);
            map.evictAt(400);
            map.evictAt(7);
            awaitEviction(map,7);
            map.flush();
            evictionSubset(map,wider,7);
        }
        // An increased replacement must stop using the previous smaller limit.
        try (var map = new VelqoraMap<String,String>()) {
            map.evictAt(2);
            map.evictAt(300);
            map.putAll(input);
            map.flush();
            contents(input,map);
        }
        // Default retention and large positive limits hold for large populations.
        Map<String,String> large = evictionInput(120000,0);
        try (var map = new VelqoraMap<String,String>()) {
            map.putAll(large);
            map.flush();
            awaitQuiescent(map);
            contents(large,map);
            map.evictAt(150000);
            map.flush();
            awaitQuiescent(map);
            contents(large,map);
            map.evictAt(100000);
            awaitEviction(map,100000);
            map.flush();
            evictionSubset(map,large,100000);
        }
    ''', members=EVICTION_SUPPORT)
    run_persistence_caller(caller, tmp_path)


def test_bulk_and_concurrent_writes_settle_to_entry_bound(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        // Large values below the entry limit must not be mistaken for overflow.
        Map<String,String> small = evictionInput(9,8192);
        try (var map = new VelqoraMap<String,String>()) {
            map.evictAt(17);
            map.putAll(small);
            map.flush();
            contents(small,map);
            Map<String,String> input = evictionInput(360,8192);
            map.putAll(input);
            awaitEviction(map,17);
            map.flush();
            evictionSubset(map,input,17);
            // Clearing removes entries, not the configured limit.
            map.clear();
            contents(Map.of(),map);
            map.putAll(input);
            awaitEviction(map,17);
            map.flush();
            evictionSubset(map,input,17);
        }
        // New entries created by conditional insertion, computation or combination count too.
        Map<String,String> created = evictionInput(96,2);
        for (String operation : List.of("putIfAbsent","computeIfAbsent","compute","merge")) {
            try (var map = new VelqoraMap<String,String>()) {
                map.evictAt(11);
                for (var entry : created.entrySet()) {
                    String key = entry.getKey(), value = entry.getValue();
                    if (operation.equals("putIfAbsent")) map.putIfAbsent(key,value);
                    else if (operation.equals("computeIfAbsent")) map.computeIfAbsent(key,k -> value);
                    else if (operation.equals("compute")) map.compute(key,(k,v) -> value);
                    else map.merge(key,value,(a,b) -> b);
                }
                awaitEviction(map,11);
                map.flush();
                evictionSubset(map,created,11);
            }
        }
        Map<String,String> input = evictionInput(1600,5);
        try (var map = new VelqoraMap<String,String>()) {
            map.evictAt(31);
            contend(4, worker -> {
                for (int i=worker; i<1600; i+=4)
                    map.put("entry-"+i,input.get("entry-"+i));
                return true;
            });
            awaitEviction(map,31);
            map.flush();
            evictionSubset(map,input,31);
        }
        for (int limit : new int[]{2,1}) {
            try (var map = new VelqoraMap<String,String>()) {
                map.evictAt(limit);
                map.putAll(input);
                awaitEviction(map,limit);
                map.flush();
                evictionSubset(map,input,limit);
            }
        }
    ''', members=EVICTION_SUPPORT)
    run_persistence_caller(caller, tmp_path)


def test_checkpoint_settles_eviction_and_preserves_deleted_keys(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        Map<String,String> input = evictionInput(12000,7);
        if (args[1].equals("write")) {
            for (String name : List.of("existing", "incoming")) {
                var map = new VelqoraMap<String,String>(root.resolve(name),TEXT,TEXT);
                if (name.equals("existing")) {
                    map.putAll(input);
                    map.flush();
                    contents(input,map);
                    map.evictAt(23);
                } else {
                    map.evictAt(23);
                    map.putAll(input);
                }
                // No waiting or close can finish eviction on behalf of flush.
                map.flush();
                Map<String,String> retained = evictionSubset(map,input,23);
                Properties expected = new Properties();
                expected.putAll(retained);
                try (var out = Files.newOutputStream(root.resolve(name+".properties"))) {
                    expected.store(out,"Application-observed checkpoint contents");
                }
            }
            compactionExit();
        } else {
            for (String name : List.of("existing", "incoming")) {
                Properties saved = new Properties();
                try (var in = Files.newInputStream(root.resolve(name+".properties"))) {
                    saved.load(in);
                }
                Map<String,String> expected = new HashMap<>();
                for (String key : saved.stringPropertyNames())
                    expected.put(key,saved.getProperty(key));
                try (var restored = new VelqoraMap<String,String>(root.resolve(name),TEXT,TEXT)) {
                    contents(expected,restored);
                    evictionSubset(restored,input,23);
                    for (String key : input.keySet())
                        eq(expected.get(key),restored.get(key));
                }
            }
        }
    ''', members=EVICTION_SUPPORT)
    run_persistence_caller(caller, tmp_path, tmp_path, 'write')
    run_persistence_caller(caller, tmp_path, tmp_path, 'read')
