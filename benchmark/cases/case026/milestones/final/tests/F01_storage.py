# feature: F01
"""Acceptance checks for the nine planned concurrent-map storage obligations."""

from F01_helpers import run_map_scenario


def test_creation_reads_and_membership(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> empty = VelqoraMap.memory();
             VelqoraMap<String,Integer> map = new VelqoraMap<>(Map.of("oak", 17, "elm", -4))) {
            contents(Map.of(), empty);
            eq(null, empty.get("oak"));
            eq(91, empty.getOrDefault("oak", 91));
            eq(false, empty.containsKey("oak"));
            eq(false, empty.containsValue(17));
            contents(Map.of("oak", 17, "elm", -4), map);
            eq(true, map.containsKey("elm"));
            eq(false, map.containsKey("missing"));
            eq(true, map.containsValue(-4));
            eq(false, map.containsValue(91));
            eq(17, map.getOrDefault("oak", 91));
            eq(null, map.get("missing"));
            eq(91, map.getOrDefault("missing", 91));
            eq(null, map.put("pine", 23));
            contents(Map.of("oak", 17, "elm", -4, "pine", 23), map);
            eq(17, map.put("oak", 8));
            contents(Map.of("oak", 8, "elm", -4, "pine", 23), map);
            eq(false, map.containsValue(17));
            eq(true, map.containsValue(8));
            eq(null, empty.put("new", 6));
            contents(Map.of("new", 6), empty);
            // Membership compares equal, separately constructed keys and values.
            eq(true, map.containsKey(new String("elm")));
            eq(-4, map.get(new String("elm")));
            eq(null, map.put("wide", 70000));
            eq(true, map.containsValue(Integer.valueOf("70000")));
            eq(false, map.containsValue(Integer.valueOf("70001")));
            eq(70000, map.put(new String("wide"), 80000));
            eq(false, map.containsValue(Integer.valueOf("70000")));
            eq(true, map.containsValue(Integer.valueOf("80000")));
            contents(Map.of("oak", 8, "elm", -4, "pine", 23, "wide", 80000), map);
            // Membership reflects removed entries, not earlier insertions.
            eq(23, map.remove("pine"));
            eq(false, map.containsKey("pine"));
            eq(false, map.containsValue(23));
            eq(80000, map.remove(new String("wide")));
            eq(false, map.containsKey("wide"));
            contents(Map.of("oak", 8, "elm", -4), map);
            map.clear();
            eq(false, map.containsKey("oak"));
            eq(false, map.containsKey(new String("elm")));
            eq(false, map.containsValue(8));
            contents(Map.of(), map);
            eq(null, map.put("elm", 5));
            eq(true, map.containsKey("elm"));
            contents(Map.of("elm", 5), map);
        }
    ''')


def test_conditional_changes(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> map = new VelqoraMap<>()) {
            eq(null, map.putIfAbsent("a", 501));
            contents(Map.of("a", 501), map);
            eq(501, map.putIfAbsent("a", 702));
            contents(Map.of("a", 501), map);
            eq(null, map.replace("missing", 88));
            contents(Map.of("a", 501), map);
            eq(501, map.replace("a", 702));
            contents(Map.of("a", 702), map);
            eq(false, map.replace("a", 501, 900));
            eq(false, map.replace("missing", 702, 900));
            contents(Map.of("a", 702), map);
            // Equal separately constructed values must compare by value, not identity.
            eq(true, map.replace("a", Integer.valueOf("702"), 900));
            contents(Map.of("a", 900), map);
            eq(false, map.remove("a", 702));
            eq(false, map.remove("missing", 900));
            contents(Map.of("a", 900), map);
            eq(true, map.remove("a", Integer.valueOf("900")));
            contents(Map.of(), map);
            eq(false, map.remove("a", 900));
        }
    ''')


def test_computed_and_combined_changes(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> map = VelqoraMap.memory()) {
            eq(6, map.compute("spruce", (k,v) -> { eq(null,v); return k.length(); }));
            contents(Map.of("spruce", 6), map);
            eq(18, map.compute("spruce", (k,v) -> k.length() + v * 2));
            contents(Map.of("spruce", 18), map);
            eq(null, map.compute("spruce", (k,v) -> null));
            contents(Map.of(), map);
            eq(false, map.containsKey("spruce"));
            eq(null, map.compute("absent", (k,v) -> null));
            contents(Map.of(), map);
            eq(4, map.computeIfAbsent("birch", k -> k.length() - 1));
            eq(4, map.computeIfAbsent("birch", k -> 999));
            contents(Map.of("birch", 4), map);
            eq(null, map.computeIfAbsent("absent", k -> null));
            contents(Map.of("birch", 4), map);
            eq(null, map.computeIfPresent("absent", (k,v) -> 123));
            contents(Map.of("birch", 4), map);
            eq(21, map.computeIfPresent("birch", (k,v) -> k.length() + v * 4));
            contents(Map.of("birch", 21), map);
            eq(null, map.computeIfPresent("birch", (k,v) -> null));
            contents(Map.of(), map);
            eq(false, map.containsKey("birch"));
            eq(7, map.merge("fir", 7, (old,supplied) -> old - supplied));
            contents(Map.of("fir", 7), map);
            eq(23, map.merge("fir", 2, (old,supplied) -> old * 3 + supplied));
            contents(Map.of("fir", 23), map);
            eq(null, map.merge("fir", 8, (old,supplied) -> null));
            contents(Map.of(), map);
            eq(false, map.containsKey("fir"));
        }
    ''')


def test_updates_under_contention(tmp_path):
    run_map_scenario(tmp_path, r'''
        final int workers = 8;
        final int rounds = 600;
        try (VelqoraMap<String,Integer> map = VelqoraMap.memory()) {
            List<Integer> insertions = contend(workers, i -> map.putIfAbsent("winner", i));
            eq(1L, insertions.stream().filter(Objects::isNull).count());
            int winner = map.get("winner");
            if (winner < 0 || winner >= workers) throw new AssertionError("Unknown winner");
            eq(null, insertions.get(winner));
            for (Integer prior : insertions) if (prior != null) eq(winner, prior);
            map.put("cas", 0);
            List<Boolean> replacements = contend(workers, i -> map.replace("cas", 0, i + 1));
            eq(1L, replacements.stream().filter(Boolean::booleanValue).count());
            eq(replacements.indexOf(true) + 1, map.get("cas"));
            List<Boolean> removals = contend(workers, i -> map.remove("winner", winner));
            eq(1L, removals.stream().filter(Boolean::booleanValue).count());
            eq(null, map.get("winner"));
            for (String operation : List.of("compute", "present", "merge", "replace")) {
                map.put("total", 0);
                List<List<Integer>> results = contend(workers, worker -> {
                    List<Integer> completed = new ArrayList<>();
                    for (int j = 0; j < rounds; j++) {
                        if (operation.equals("compute")) {
                            completed.add(map.compute("total", (k,v) -> { Thread.yield(); return v + 1; }));
                        } else if (operation.equals("present")) {
                            completed.add(map.computeIfPresent("total", (k,v) -> { Thread.yield(); return v + 1; }));
                        } else if (operation.equals("merge")) {
                            completed.add(map.merge("total", 1, (a,b) -> { Thread.yield(); return a + b; }));
                        } else {
                            boolean done = false;
                            for (int retry = 0; retry < 100000 && !done; retry++) {
                                int old = map.get("total");
                                Thread.yield();
                                if (map.replace("total", old, old + 1)) {
                                    completed.add(old + 1);
                                    done = true;
                                }
                            }
                            if (!done) throw new AssertionError("Conditional update made no progress");
                        }
                    }
                    return completed;
                });
                List<Integer> observed = new ArrayList<>();
                results.forEach(observed::addAll);
                Collections.sort(observed);
                eq(workers * rounds, observed.size());
                for (int n = 0; n < observed.size(); n++) eq(n + 1, observed.get(n));
                eq(workers * rounds, map.get("total"));
            }
            // Contended first insertions: all workers target the same initially absent keys.
            // A barrier aligns the workers on every key; the callback pauses briefly
            // while it sees absence, so competing first insertions really overlap.
            final int fresh = 150;
            for (String operation : List.of("compute", "merge")) {
                CyclicBarrier align = new CyclicBarrier(workers);
                List<List<Integer>> results = contend(workers, worker -> {
                    List<Integer> completed = new ArrayList<>();
                    for (int j = 0; j < fresh; j++) {
                        String key = operation + "-fresh-" + j;
                        align(align);
                        if (operation.equals("compute")) {
                            completed.add(map.compute(key, (k,v) -> {
                                if (v != null) return v + 1;
                                try { Thread.sleep(1); } catch (InterruptedException stop) { throw new IllegalStateException(stop); }
                                return 1;
                            }));
                        } else {
                            completed.add(map.merge(key, 1, (a,b) -> { Thread.yield(); return a + b; }));
                        }
                    }
                    return completed;
                });
                for (int j = 0; j < fresh; j++) {
                    List<Integer> observed = new ArrayList<>();
                    for (List<Integer> completed : results) observed.add(completed.get(j));
                    Collections.sort(observed);
                    for (int n = 0; n < workers; n++) eq(n + 1, observed.get(n));
                    eq(workers, map.get(operation + "-fresh-" + j));
                }
            }
            CyclicBarrier claimAlign = new CyclicBarrier(workers);
            List<List<Integer>> claims = contend(workers, worker -> {
                List<Integer> seen = new ArrayList<>();
                for (int j = 0; j < fresh; j++) {
                    align(claimAlign);
                    seen.add(map.computeIfAbsent("claim-" + j, k -> { Thread.yield(); return worker; }));
                }
                return seen;
            });
            for (int j = 0; j < fresh; j++) {
                Integer stored = map.get("claim-" + j);
                if (stored == null || stored < 0 || stored >= workers) throw new AssertionError("Unknown claim");
                for (List<Integer> seen : claims) eq(stored, seen.get(j));
            }
        }
    ''')


def test_bulk_changes_and_removal(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> map = new VelqoraMap<>(Map.of("a", 2, "untouched", 9))) {
            map.putAll(Map.of("a", 7, "bb", -3, "ccc", 11));
            contents(Map.of("a", 7, "bb", -3, "ccc", 11, "untouched", 9), map);
            map.putAll(Map.of());
            contents(Map.of("a", 7, "bb", -3, "ccc", 11, "untouched", 9), map);
            map.replaceAll((k,v) -> v * 2 + k.length());
            contents(Map.of("a", 15, "bb", -4, "ccc", 25, "untouched", 27), map);
            eq(25, map.remove("ccc"));
            eq(null, map.remove("missing"));
            contents(Map.of("a", 15, "bb", -4, "untouched", 27), map);
            eq(false, map.removeAll(List.of()));
            eq(false, map.removeAll(List.of("missing", "ccc")));
            contents(Map.of("a", 15, "bb", -4, "untouched", 27), map);
            eq(true, map.removeAll(List.of("missing", "a", "bb")));
            contents(Map.of("untouched", 27), map);
            eq(false, map.containsKey("a"));
            // A large batch stores every supplied entry; bulk removal removes every requested key.
            Map<String,Integer> batch = new HashMap<>();
            for (int i = 0; i < 3000; i++) batch.put("bulk-" + i, i * 7 - 1000);
            map.putAll(batch);
            Map<String,Integer> expected = new HashMap<>(batch);
            expected.put("untouched", 27);
            contents(expected, map);
            List<String> doomed = new ArrayList<>();
            for (int i = 0; i < 3000; i += 2) doomed.add("bulk-" + i);
            eq(true, map.removeAll(doomed));
            expected.keySet().removeAll(doomed);
            contents(expected, map);
            for (String key : doomed) eq(false, map.containsKey(key));
            map.putAll(Map.of("d", 5, "e", 8));
            map.clear();
            contents(Map.of(), map);
            eq(false, map.containsKey("untouched"));
            map.clear();
            map.replaceAll((k,v) -> 77);
            contents(Map.of(), map);
        }
    ''')


def test_live_read_only_views(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> map = new VelqoraMap<>(Map.of("a", 3, "b", 3))) {
            Set<String> keys = map.keySet();
            Collection<Integer> values = map.values();
            Set<Map.Entry<String,Integer>> entries = map.entrySet();
            eq(Set.of("a", "b"), new HashSet<>(keys));
            List<Integer> sorted = new ArrayList<>(values);
            Collections.sort(sorted);
            eq(List.of(3,3), sorted);
            eq(Map.of("a",3,"b",3).entrySet(), new HashSet<>(entries));
            map.put("c", 8);
            map.put("a", 5);
            map.remove("b");
            eq(Set.of("a", "c"), new HashSet<>(keys));
            sorted = new ArrayList<>(values);
            Collections.sort(sorted);
            eq(List.of(5,8), sorted);
            eq(Map.of("a",5,"c",8).entrySet(), new HashSet<>(entries));
            List<Action> attempts = List.of(
                () -> keys.remove("a"), () -> keys.clear(),
                () -> values.remove(5), () -> values.clear(),
                () -> entries.remove(Map.entry("a",5)), () -> entries.clear(),
                () -> { var it = keys.iterator(); it.next(); it.remove(); },
                () -> { var it = values.iterator(); it.next(); it.remove(); },
                () -> { var it = entries.iterator(); it.next(); it.remove(); },
                () -> entries.iterator().next().setValue(99));
            for (Action attempt : attempts) {
                rejects(UnsupportedOperationException.class, attempt);
                contents(Map.of("a",5,"c",8), map);
            }
            // Entries reached through streams, splitting, forEach or arrays stay read-only.
            List<Action> entryPaths = List.of(
                () -> entries.stream().findFirst().get().setValue(99),
                () -> entries.stream().forEach(e -> e.setValue(99)),
                () -> entries.spliterator().tryAdvance(e -> e.setValue(99)),
                () -> entries.forEach(e -> e.setValue(99)),
                () -> ((Map.Entry<String,Integer>) entries.toArray()[0]).setValue(99));
            for (Action attempt : entryPaths) {
                rejects(UnsupportedOperationException.class, attempt);
                contents(Map.of("a",5,"c",8), map);
            }
            // Bulk removal through a view is refused too: storage stays unchanged.
            List<Action> bulkRemovals = List.of(
                () -> keys.removeAll(List.of("a", "c")), () -> keys.retainAll(List.of()),
                () -> keys.removeIf(k -> true),
                () -> values.removeAll(List.of(5, 8)), () -> values.retainAll(List.of()),
                () -> values.removeIf(v -> true),
                () -> entries.removeAll(Set.of(Map.entry("a",5), Map.entry("c",8))),
                () -> entries.retainAll(List.of()), () -> entries.removeIf(e -> true));
            for (Action attempt : bulkRemovals) {
                rejects(UnsupportedOperationException.class, attempt);
                contents(Map.of("a",5,"c",8), map);
            }
            map.clear();
            eq(Set.of(), new HashSet<>(keys));
            eq(List.of(), new ArrayList<>(values));
            eq(Set.of(), new HashSet<>(entries));
        }
    ''')


def test_null_inputs_and_bulk_null_results(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> map = new VelqoraMap<>(Map.of("a", 7))) {
            Map<String,Integer> nullKey = new HashMap<>(); nullKey.put(null, 3);
            Map<String,Integer> nullValue = new HashMap<>(); nullValue.put("bad", null);
            List<Action> attempts = List.of(
                () -> map.put(null, 1), () -> map.put("bad", null),
                () -> map.get(null), () -> map.getOrDefault(null, 1),
                () -> map.containsKey(null), () -> map.remove(null),
                () -> map.remove(null, 7),
                () -> map.putIfAbsent(null, 1), () -> map.putIfAbsent("bad", null),
                () -> map.replace(null, 1), () -> map.replace("a", null),
                () -> map.replace(null, 7, 8), () -> map.replace("a", 7, null),
                () -> map.compute(null, (k,v) -> 1),
                () -> map.computeIfAbsent(null, k -> 1),
                () -> map.computeIfPresent(null, (k,v) -> 1),
                () -> map.merge(null, 1, Integer::sum),
                () -> map.merge("a", null, Integer::sum),
                () -> map.putAll(nullKey), () -> map.putAll(nullValue),
                () -> new VelqoraMap<String,Integer>(nullKey),
                () -> new VelqoraMap<String,Integer>(nullValue),
                () -> map.replaceAll((k,v) -> null));
            for (Action attempt : attempts) {
                rejects(NullPointerException.class, attempt);
                contents(Map.of("a",7), map);
            }
            eq(7, map.put("a", 12));
            contents(Map.of("a",12), map);
        }
    ''')


def test_in_memory_maintenance(tmp_path):
    run_map_scenario(tmp_path, r'''
        VelqoraMap<String,Integer> map = VelqoraMap.memory();
        try {
            eq(null, map.put("saved", 31));
            contents(Map.of("saved",31), map);
            map.flush();
            contents(Map.of("saved",31), map);
            map.compact();
            contents(Map.of("saved",31), map);
        } finally {
            map.close();
        }
    ''')


def test_mutation_observer_keys(tmp_path):
    run_map_scenario(tmp_path, r'''
        try (VelqoraMap<String,Integer> map = VelqoraMap.memory()) {
            List<String> first = new ArrayList<>();
            List<String> second = new ArrayList<>();
            map.onMutation(first::add);
            map.onMutation(second::add);
            notified(map,first,second,Set.of("a"),Map.of("a",2), () -> eq(null,map.put("a",2)));
            notified(map,first,second,Set.of("a"),Map.of("a",3), () -> eq(2,map.put("a",3)));
            // Replacing with an equal value is still a successful replacement.
            notified(map,first,second,Set.of("a"),Map.of("a",3), () -> eq(3,map.put("a",Integer.valueOf("3"))));
            notified(map,first,second,Set.of("a"),Map.of("a",3), () -> eq(3,map.replace("a",Integer.valueOf("3"))));
            notified(map,first,second,Set.of("a"),Map.of("a",3), () -> eq(true,map.replace("a",3,Integer.valueOf("3"))));
            // Computations restricted to absent or present keys are unmet conditions otherwise.
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(3,map.computeIfAbsent("a",k->99)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(null,map.computeIfPresent("absent",(k,v)->99)));
            // A null computation result for an absent key removes nothing.
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(null,map.compute("absent",(k,v)->null)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(3,map.putIfAbsent("a",8)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(null,map.replace("absent",8)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(false,map.replace("a",9,8)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(false,map.replace("absent",3,8)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(false,map.remove("a",8)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(false,map.remove("absent",3)));
            notified(map,first,second,Set.of(),Map.of("a",3), () -> eq(null,map.remove("absent")));
            notified(map,first,second,Set.of("b"),Map.of("a",3,"b",4), () -> eq(null,map.putIfAbsent("b",4)));
            notified(map,first,second,Set.of("a"),Map.of("a",5,"b",4), () -> eq(3,map.replace("a",5)));
            notified(map,first,second,Set.of("a"),Map.of("a",6,"b",4), () -> eq(true,map.replace("a",5,6)));
            notified(map,first,second,Set.of("b"),Map.of("a",6), () -> eq(true,map.remove("b",4)));
            notified(map,first,second,Set.of("a"),Map.of(), () -> eq(6,map.remove("a")));
            notified(map,first,second,Set.of("x"),Map.of("x",4), () -> eq(4,map.compute("x",(k,v)->4)));
            notified(map,first,second,Set.of("x"),Map.of("x",12), () -> eq(12,map.compute("x",(k,v)->v*3)));
            notified(map,first,second,Set.of("x"),Map.of(), () -> eq(null,map.compute("x",(k,v)->null)));
            notified(map,first,second,Set.of("c"),Map.of("c",7), () -> eq(7,map.computeIfAbsent("c",k->7)));
            notified(map,first,second,Set.of("c"),Map.of("c",8), () -> eq(8,map.computeIfPresent("c",(k,v)->v+1)));
            notified(map,first,second,Set.of("c"),Map.of(), () -> eq(null,map.computeIfPresent("c",(k,v)->null)));
            notified(map,first,second,Set.of("d"),Map.of("d",9), () -> eq(9,map.merge("d",9,Integer::sum)));
            notified(map,first,second,Set.of("d"),Map.of("d",11), () -> eq(11,map.merge("d",2,Integer::sum)));
            notified(map,first,second,Set.of("d"),Map.of(), () -> eq(null,map.merge("d",2,(a,b)->null)));
            notified(map,first,second,Set.of("e"),Map.of("e",1), () -> eq(null,map.put("e",1)));
            notified(map,first,second,Set.of("e","f"),Map.of("e",2,"f",3), () -> map.putAll(Map.of("e",2,"f",3)));
            notified(map,first,second,Set.of("e","f"),Map.of("e",4,"f",6), () -> map.replaceAll((k,v)->v*2));
            notified(map,first,second,Set.of(),Map.of("e",4,"f",6), () -> map.putAll(Map.of()));
            notified(map,first,second,Set.of(),Map.of("e",4,"f",6), () -> eq(false,map.removeAll(List.of("absent"))));
            notified(map,first,second,Set.of("h"),Map.of("e",4,"f",6,"h",10), () -> eq(null,map.put("h",10)));
            notified(map,first,second,Set.of("e","h"),Map.of("f",6), () -> eq(true,map.removeAll(List.of("e","absent","h"))));
            map.put("g",7);
            notified(map,first,second,Set.of("f","g"),Map.of(), () -> map.clear());
            // Clearing an already empty map removes nothing and notifies nobody.
            notified(map,first,second,Set.of(),Map.of(), () -> map.clear());
        }
    ''')
