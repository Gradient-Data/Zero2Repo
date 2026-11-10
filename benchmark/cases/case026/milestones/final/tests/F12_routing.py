# feature: F12
"""The seven planned ownership and routing acceptance checks."""

import math

from _helpers import start_java
from F12_helpers import (
    compile_cluster_caller, run_cluster_caller, run_cluster_scenario, cluster_nodes,
)


def test_topology_configuration_and_even_ownership(tmp_path):
    run_cluster_scenario(tmp_path, r'''
        var nodes=configNodes();
        for(int count:new int[]{1,2,8,19}) balanced(ClusterTopology.evenly(count,nodes),nodes,count);
        var owners=List.of("third","third","Az.0_-","second","third");
        var assigned=ClusterTopology.assigned(nodes,owners);
        eq(owners,assigned.owners()); eq(owners.size(),assigned.partitions());
        for(int p=0;p<owners.size();p++) eq(owners.get(p),assigned.owner(p).name());
        for(int count:new int[]{0,-3})
            rejects(IllegalArgumentException.class,()->ClusterTopology.evenly(count,nodes));
        rejects(IllegalArgumentException.class,()->ClusterTopology.evenly(5,List.of()));
        rejects(IllegalArgumentException.class,()->ClusterTopology.assigned(List.of(),List.of("third")));
        rejects(IllegalArgumentException.class,()->ClusterTopology.assigned(nodes,List.of()));
        rejects(IllegalArgumentException.class,()->ClusterTopology.assigned(nodes,List.of("third","unknown")));
        var duplicates=List.of(nodes.get(0),new ClusterNode(nodes.get(0).name(),nodes.get(1).address()));
        rejects(IllegalArgumentException.class,()->ClusterTopology.evenly(5,duplicates));
        rejects(IllegalArgumentException.class,()->ClusterTopology.assigned(duplicates,List.of(nodes.get(0).name())));
        for(String name:List.of("","two words","slash/name","name:port","水","name\n","a@b","a,b","a+b",
                "a*b","a#b","a=b","a~b","a!b","a%b","a'b","a;b","tab\tname","(a)","a$b","é"))
            rejects(IllegalArgumentException.class,()->new ClusterNode(name,nodes.get(0).address()));
        for(String name:List.of("a","Z","7",".","_","-","node-01.zone_A","ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"))
            eq(name,new ClusterNode(name,nodes.get(0).address()).name());
    ''')


def test_encoded_key_partition_stability_across_clients_and_restarts(tmp_path):
    classpath = compile_cluster_caller(tmp_path, r'''
        var nodes=configNodes(); Random random=new Random(1202);
        List<Integer> observations=new ArrayList<>();
        for(int count:new int[]{1,7,32,257}) {
            List<String> owners=new ArrayList<>();
            for(int p=0;p<count;p++) owners.add(nodes.get((p+1)%nodes.size()).name());
            var topology=ClusterTopology.assigned(nodes,owners);
            var partitioner=new KeyPartitioner<>(RAW_KEY,count);
            var rawMap=new ClusterMap<byte[],String>("records",RAW_KEY,topology,
                new HttpClusterTransport<>(RAW_KEY,TEXT));
            var textMap=routed(topology,httpTransport());
            for(int length:new int[]{0,1,3,8,16,65}) for(int i=0;i<30;i++) {
                byte[] key=new byte[length]; random.nextBytes(key);
                int partition=partitioner.partition(key);
                if(partition<0 || partition>=count) throw new AssertionError("Partition outside configured range");
                eq(partition,partitioner.partition(key.clone()));
                eq(partition,new KeyPartitioner<>(RAW_KEY,count).partition(key.clone()));
                eq(partition,rawMap.partition(key.clone()));
                String encoded=Base64.getEncoder().encodeToString(key);
                eq(partition,textMap.partition(new String(encoded)));
                eq(owners.get(partition),rawMap.owner(key.clone()).name());
                eq(owners.get(partition),textMap.owner(encoded).name());
                observations.add(partition);
            }
        }
        System.out.println(observations);
    ''')
    first = run_cluster_caller(classpath, tmp_path).json(channel='stdout')
    second = run_cluster_caller(classpath, tmp_path).json(channel='stdout')
    assert first == second, 'Identical encoded keys changed partitions after a JVM restart'


# Partition counts at which every logical partition is counted individually
# (4096 exceeds every 8-byte byte sum), and counts so large (beyond 16-bit hash
# values) that partitions are aggregated into 64 contiguous ranges and 64
# residue classes, whose exact probabilities follow from 1/P per partition.
FULL_COUNTS = (2, 7, 32, 127, 4096)
LARGE_COUNTS = (131072, 1000003, 2147483647)
GROUPS = 64


def _range_probabilities(count):
    # Range b holds partitions p with floor(p*64/count) == b.
    edges = [-(-b * count // GROUPS) for b in range(GROUPS + 1)]
    return [(edges[b + 1] - edges[b]) / count for b in range(GROUPS)]


def _residue_probabilities(count):
    return [(count // GROUPS + (1 if r < count % GROUPS else 0)) / count for r in range(GROUPS)]


def test_uniform_encoded_key_partition_distribution(tmp_path):
    result = run_cluster_scenario(tmp_path, r'''
        List<String> observations=new ArrayList<>();
        for(int length:new int[]{8,24}) {
            for(int count:new int[]{FULL}) {
                Random random=new Random(0x12D157L+length*1009L+count);
                var partitioner=new KeyPartitioner<>(RAW_KEY,count);
                int samples=Math.max(262144,256*count);
                int[] frequencies=new int[count];
                for(int i=0;i<samples;i++) {
                    byte[] key=new byte[length]; random.nextBytes(key);
                    int p=partitioner.partition(key);
                    if(p<0 || p>=count) throw new AssertionError("Partition outside configured range");
                    frequencies[p]++;
                }
                observations.add("{\"length\":"+length+",\"partitions\":"+count+",\"samples\":"+samples
                    +",\"frequencies\":"+Arrays.toString(frequencies)+"}");
            }
            for(int count:new int[]{LARGE}) {
                Random random=new Random(0x12D158L+length*1013L+count);
                var partitioner=new KeyPartitioner<>(RAW_KEY,count);
                int samples=1<<20;
                long[] ranges=new long[64], residues=new long[64];
                for(int i=0;i<samples;i++) {
                    byte[] key=new byte[length]; random.nextBytes(key);
                    int p=partitioner.partition(key);
                    if(p<0 || p>=count) throw new AssertionError("Partition outside configured range");
                    ranges[(int)((long)p*64/count)]++; residues[p%64]++;
                }
                observations.add("{\"length\":"+length+",\"partitions\":"+count+",\"samples\":"+samples
                    +",\"ranges\":"+Arrays.toString(ranges)+",\"residues\":"+Arrays.toString(residues)+"}");
            }
        }
        System.out.println("["+String.join(",",observations)+"]");
    '''.replace('FULL', ','.join(map(str, FULL_COUNTS))).replace('LARGE', ','.join(map(str, LARGE_COUNTS))))
    observations = result.json(channel='stdout')
    # Each table is one multinomial sample whose exact cell probabilities follow
    # from FP-12.02 (1/P per logical partition; a group sums its partitions).
    # (1) Per cell, Bernstein gives P(|X-mu| >= t) <= 2 exp(-L) for
    #     t = sqrt(2*mu*L) + 2*L/3 (variance <= mu). L is chosen so the union over
    #     every compared cell is <= 1e-12: a rigorous false-rejection bound.
    # (2) Per table, Pearson's chi-square statistic must stay below the
    #     Laurent-Massart chi-square tail point df + 2*sqrt(df*x) + 2*x at x = 50
    #     (nominal tail e^-50 ~ 2e-22 per table). Every expected cell count is
    #     >= 256, where the chi-square approximation is accurate; the remaining
    #     slack to the 1e-9 whole-test budget is over ten orders of magnitude.
    # No hash algorithm, partition vector or particular partition is pinned.
    tables = []
    for observation in observations:
        count, samples = observation['partitions'], observation['samples']
        if 'frequencies' in observation:
            assert count in FULL_COUNTS and len(observation['frequencies']) == count
            tables.append((observation, observation['frequencies'], [1 / count] * count, samples))
        else:
            assert count in LARGE_COUNTS
            tables.append((observation, observation['ranges'], _range_probabilities(count), samples))
            tables.append((observation, observation['residues'], _residue_probabilities(count), samples))
    assert len(tables) == 2 * (len(FULL_COUNTS) + 2 * len(LARGE_COUNTS))
    cells = sum(len(probabilities) for _, _, probabilities, _ in tables)
    tail_log = math.log(2 * cells / 1e-12)
    for observation, counts, probabilities, samples in tables:
        context = (observation['length'], observation['partitions'])
        assert len(counts) == len(probabilities) and sum(counts) == samples, context
        chi_square = 0.0
        for value, probability in zip(counts, probabilities):
            mean = samples * probability
            margin = math.sqrt(2 * mean * tail_log) + 2 * tail_log / 3
            assert abs(value - mean) <= margin, (context, value, mean)
            chi_square += (value - mean) ** 2 / mean
        freedom = len(counts) - 1
        threshold = freedom + 2 * math.sqrt(freedom * 50) + 2 * 50
        assert chi_square <= threshold, (context, chi_square, threshold)


def test_real_application_and_independent_http_owner_operations(tmp_path):
    classpath = compile_cluster_caller(tmp_path, r'''
        var local=configNodes();
        try(var stores=new ApplicationStores(local)) {
            exerciseRouting(ClusterTopology.evenly(23,local),stores,
                (node,map,key,value)->eq(value,stores.store(node,map).get(key)));
        }
        var remote=nodes(args);
        exerciseRouting(ClusterTopology.evenly(23,remote),httpTransport(),F12ClusterCheck::remoteValue);
    ''')
    with cluster_nodes(classpath, tmp_path) as (_, addresses):
        run_cluster_caller(classpath, tmp_path, *addresses)


def test_membership_reassignment_and_fixed_partition_count(tmp_path):
    run_cluster_scenario(tmp_path, r'''
        var nodes=configNodes(); var initialNodes=nodes.subList(0,2);
        var original=ClusterTopology.evenly(17,initialNodes);
        var before=new ArrayList<>(original.owners());
        var expanded=original.withNodes(nodes);
        eq(before,expanded.owners()); eq(new HashSet<>(nodes),new HashSet<>(expanded.nodes()));
        eq(before,original.owners());
        var assignments=Map.of(0,nodes.get(2).name(),7,nodes.get(2).name(),16,nodes.get(1).name());
        var changed=expanded.reassign(assignments);
        for(int p=0;p<17;p++) eq(assignments.getOrDefault(p,before.get(p)),changed.owner(p).name());
        var rebalanced=changed.rebalance(List.of(nodes.get(2),nodes.get(0)));
        balanced(rebalanced,List.of(nodes.get(2),nodes.get(0)),17);
        for(int p:new int[]{-1,17}) {
            rejects(IllegalArgumentException.class,()->expanded.reassign(Map.of(p,nodes.get(0).name())));
            rejects(IllegalArgumentException.class,()->expanded.owner(p));
        }
        rejects(IllegalArgumentException.class,()->expanded.reassign(Map.of(0,"unknown")));
        rejects(IllegalArgumentException.class,()->changed.withNodes(initialNodes));
        var duplicateMembers=List.of(nodes.get(0),nodes.get(1),nodes.get(2),
            new ClusterNode(nodes.get(2).name(),URI.create("http://127.0.0.1:4")));
        rejects(IllegalArgumentException.class,()->changed.rebalance(List.of()));
        rejects(IllegalArgumentException.class,()->changed.rebalance(duplicateMembers));
        rejects(IllegalArgumentException.class,()->changed.withNodes(List.of()));
        rejects(IllegalArgumentException.class,()->changed.withNodes(duplicateMembers));
        var unassignedMember=ClusterTopology.assigned(nodes,before);
        eq(before,unassignedMember.withNodes(initialNodes).owners()); // Removing an unassigned member is legal.
        try(var stores=new ApplicationStores(nodes)) {
            var client=routed(original,stores);
            client.topology(changed);
            Random random=new Random(1205);
            List<String> keys=new ArrayList<>();
            for(int i=0;i<100;i++) {
                String key=randomKey(random); keys.add(key);
                eq(changed.owner(client.partition(key)),client.owner(key));
            }
            rejects(IllegalArgumentException.class,()->client.topology(ClusterTopology.evenly(18,nodes)));
            for(String key:keys) eq(changed.owner(client.partition(key)),client.owner(key));
            client.topology(rebalanced);
            for(String key:keys) eq(rebalanced.owner(client.partition(key)),client.owner(key));
        }
    ''')


def test_reassignment_changes_routing_without_moving_records(tmp_path):
    classpath = compile_cluster_caller(tmp_path, r'''
        var nodes=nodes(args); var old=nodes.get(0); var fresh=nodes.get(1);
        var topology=ClusterTopology.assigned(nodes,Collections.nCopies(11,old.name()));
        var client=routed(topology,httpTransport());
        String key=randomKey(new Random(1206));
        client.put(key,"original 水"); eq("original 水",client.get(key));
        remoteValue(old,"records",key,"original 水"); remoteValue(fresh,"records",key,null);
        var changed=topology.reassign(Map.of(client.partition(key),fresh.name()));
        client.topology(changed); eq(fresh,client.owner(key));
        eq(null,client.get(key)); eq(false,client.remove(key));
        remoteValue(old,"records",key,"original 水"); remoteValue(fresh,"records",key,null);
        client.put(key,"new-owner Ω"); eq("new-owner Ω",client.get(key));
        remoteValue(old,"records",key,"original 水"); remoteValue(fresh,"records",key,"new-owner Ω");
        eq(true,client.remove(key)); eq(false,client.remove(key)); eq(null,client.get(key));
        remoteValue(old,"records",key,"original 水"); remoteValue(fresh,"records",key,null);
        client.putAll(Map.of(key,"batch-new")); eq("batch-new",client.get(key));
        remoteValue(old,"records",key,"original 水"); remoteValue(fresh,"records",key,"batch-new");
        client.removeAll(List.of(key));
        remoteValue(old,"records",key,"original 水"); remoteValue(fresh,"records",key,null);
        client.topology(ClusterTopology.assigned(nodes,Collections.nCopies(11,old.name())));
        eq("original 水",client.get(key));
    ''')
    with cluster_nodes(classpath, tmp_path, count=2) as (_, addresses):
        run_cluster_caller(classpath, tmp_path, *addresses)


def test_owner_loss_reports_identity_and_preserves_other_owners(tmp_path):
    classpath = compile_cluster_caller(tmp_path, r"""
        int lostIndex=Integer.parseInt(args[0]);
        var nodes=nodes(Arrays.copyOfRange(args,1,args.length));
        var topology=ClusterTopology.evenly(23,nodes);
        var client=routed(topology,httpTransport());
        var selected=ownerKeys(client,nodes);
        var unavailable=nodes.get(lostIndex); var holder=nodes.get((lostIndex+1)%nodes.size());
        String key=selected.get(unavailable.name()).get(0);
        // A stale copy of the lost owner's key is left at another member by an earlier
        // reassignment; FP-12.05 keeps it there. It must never answer for the lost owner.
        client.topology(topology.reassign(Map.of(client.partition(key),holder.name())));
        client.put(key,"stale-copy"); eq(holder,client.owner(key));
        client.topology(topology); eq(unavailable,client.owner(key));
        Map<String,String> initial=new LinkedHashMap<>();
        for(var owner:selected.entrySet()) for(String k:owner.getValue()) initial.put(k,"before-"+k);
        client.putAll(initial);
        for(var node:nodes) for(String k:selected.get(node.name())) {
            remoteValue(node,"records",k,initial.get(k));
            remoteValue(holder,"records",k,k.equals(key)?"stale-copy":node.equals(holder)?initial.get(k):null);
        }
        // Warm this same client by reading and writing the lost owner's keys before the loss.
        client.put(key,"latest"); eq("latest",client.get(key));
        for(String k:selected.get(unavailable.name())) eq(k.equals(key)?"latest":initial.get(k),client.get(k));
        System.out.println("{\"ready\":true}"); System.out.flush();
        awaitGo();
        for(String k:selected.get(unavailable.name())) ownerFailure(unavailable.name(),nodes,()->client.get(k));
        ownerFailure(unavailable.name(),nodes,()->client.put(key,"must-not-write"));
        ownerFailure(unavailable.name(),nodes,()->client.remove(key));
        ownerFailure(unavailable.name(),nodes,()->client.putAll(Map.of(key,"must-not-batch")));
        ownerFailure(unavailable.name(),nodes,()->client.removeAll(List.of(key)));
        ownerFailure(unavailable.name(),nodes,()->client.get(key));
        for(var node:nodes) if(!node.equals(unavailable))
            remoteValue(node,"records",key,node.equals(holder)?"stale-copy":null);
        for(var node:nodes) if(!node.equals(unavailable)) {
            var keys=selected.get(node.name());
            for(String healthy:keys) eq(initial.get(healthy),client.get(healthy));
            client.put(keys.get(0),"still-writable"); eq("still-writable",client.get(keys.get(0)));
            eq(true,client.remove(keys.get(0))); eq(false,client.remove(keys.get(0)));
            client.putAll(Map.of(keys.get(0),"restored",keys.get(1),"updated"));
            eq("restored",client.get(keys.get(0))); eq("updated",client.get(keys.get(1)));
            client.removeAll(List.of(keys.get(0),keys.get(1)));
            remoteValue(node,"records",keys.get(0),null); remoteValue(node,"records",keys.get(1),null);
            remoteValue(node,"records",keys.get(2),initial.get(keys.get(2)));
        }
        ownerFailure(unavailable.name(),nodes,()->client.get(key));
        remoteValue(holder,"records",key,"stale-copy");
    """)
    # Two different lost owners distinguish owner identification from a fixed
    # diagnostic. Each arm starts with fresh stores and one long-lived client that
    # has already read and written the lost owner's keys before the owner stops.
    for lost_index in (0, 1):
        with cluster_nodes(classpath, tmp_path) as (processes, addresses):
            with start_java('F12ClusterCheck', java='java', classpath=classpath, cwd=tmp_path,
                            args=[str(lost_index), *addresses], jvm_args=['-Xmx512m']) as client:
                assert client.read_json_line(channel='stdout', timeout=90) == {'ready': True}
                processes[lost_index].close()
                assert processes[lost_index].poll() is not None, 'Owned server JVM is still running'
                client.send(b'go\n', timeout=10)
                client.wait(timeout=120, check=True)
