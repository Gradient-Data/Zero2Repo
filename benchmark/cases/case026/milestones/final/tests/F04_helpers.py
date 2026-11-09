# feature: F04
"""Public eviction observations; no victim selection or internal target is pinned."""

from F03_helpers import COMPACTION_SUPPORT

EVICTION_SUPPORT = COMPACTION_SUPPORT + r'''
    static Map<String,String> evictionInput(int count, int width) {
        Map<String,String> input = new LinkedHashMap<>();
        for (int i=0; i<count; i++)
            input.put("entry-"+i, "value-"+i+"水".repeat(width));
        return input;
    }
    static void awaitEviction(VelqoraMap<?,?> map, int limit) throws Exception {
        // A generous deadlock guard, not a latency or throughput requirement.
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        while (map.size() > limit && System.nanoTime() < deadline)
            Thread.sleep(2);
        if (map.size() > limit)
            throw new AssertionError("Eviction did not converge: " + map.size() + " > " + limit);
        // No retention target below the limit is pinned; let a pass in progress finish.
        awaitQuiescent(map);
    }
    static void awaitQuiescent(VelqoraMap<?,?> map) throws Exception {
        // Background eviction may still be removing entries after the bound is met;
        // wait (bounded) until the population stays unchanged for a short interval.
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        int last = map.size();
        long stableSince = System.nanoTime();
        while (System.nanoTime() < deadline) {
            Thread.sleep(10);
            int now = map.size();
            if (now != last) {
                last = now;
                stableSince = System.nanoTime();
            } else if (System.nanoTime() - stableSince >= TimeUnit.MILLISECONDS.toNanos(300)) {
                return;
            }
        }
        throw new AssertionError("Population did not become stable");
    }
    static Map<String,String> evictionSubset(VelqoraMap<String,String> map,
                                              Map<String,String> input, int limit) {
        Map<String,String> retained = new HashMap<>(map);
        if (retained.size() > limit || (limit >= 2 && retained.isEmpty()))
            throw new AssertionError("Invalid retained population: " + retained.size());
        for (var entry : retained.entrySet()) {
            if (!input.containsKey(entry.getKey()))
                throw new AssertionError("Eviction invented a key");
            eq(input.get(entry.getKey()), entry.getValue());
        }
        contents(retained,map);
        for (var entry : input.entrySet()) {
            eq(retained.get(entry.getKey()),map.get(entry.getKey()));
            eq(retained.containsKey(entry.getKey()),map.containsKey(entry.getKey()));
        }
        return retained;
    }
'''
