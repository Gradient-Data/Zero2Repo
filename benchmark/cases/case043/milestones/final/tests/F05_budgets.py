# feature: F05
"""Five planned acceptance tests for bounded and cancellable execution.

Expected arithmetic and growth results follow the guest's Core semantics.
Fuel costs are measured anew for each engine, never copied from reference
instruction accounting. See the author verification record for run status.
"""
from F05_helpers import (f01_driver, f05_driver, f02_arg, f02_values,
                         f04_call, f05_completed_work, F05_WORK)


def test_fuel_bounds_loops_and_is_repeatable_and_monotone(f05_driver):
    for engine in ('interp','jit'):
        costs = []
        budget = max(f05_completed_work(f05_driver,engine,n)[0] for n in (37,61))
        for n, answer in ((37,703),(61,1891)):
            run = f05_driver.run(F05_WORK,[('remaining',),f04_call('work',[f02_arg(0,n)],1),
                ('remaining',),('global','runs'),('bytes',0,4,'-')],engine=engine,fuel=budget)
            assert run['created'] is True, run
            first = run['observations']
            expected = f02_values((0,answer))
            assert first[1] == expected, first
            assert first[3:] == [{'kind':0,'bits':1},{'bytes':answer.to_bytes(4,'little').hex()}], first
            assert 0 <= first[2]['remaining'] < budget, first
            costs.append(budget - first[2]['remaining'])
            unmetered = f05_driver.run(F05_WORK,[f04_call('work',[f02_arg(0,n)],1),
                ('remaining',),('global','runs'),('bytes',0,4,'-')],engine=engine)
            assert unmetered == {'created':True,'observations':[expected,{'remaining':None},
                {'kind':0,'bits':1},{'bytes':answer.to_bytes(4,'little').hex()}]}, unmetered
            # Rebuild each arm, so only allowance changes, never prior state.
            again = f05_driver.run(F05_WORK,[('remaining',),f04_call('work',[f02_arg(0,n)],1),
                ('remaining',),('global','runs'),('bytes',0,4,'-')],engine=engine,fuel=budget)
            assert again == {'created':True,'observations':first}, again
            larger_budget = min(budget*2,(1<<63)-1)
            larger = f05_driver.run(F05_WORK,[('remaining',),f04_call('work',[f02_arg(0,n)],1),
                ('remaining',),('global','runs'),('bytes',0,4,'-')],engine=engine,fuel=larger_budget)
            assert larger['created'] is True, larger
            obs = larger['observations']
            assert obs[0] == {'remaining':larger_budget}, obs
            assert obs[1] == expected and obs[3:] == first[3:], obs
            assert 0 <= obs[2]['remaining'] <= larger_budget, obs
        assert costs[1] > costs[0] > 0, (engine,costs)
        for budget in (17,257):
            for _ in range(2):
                got = f05_driver.run(F05_WORK,[f04_call('spin'),('remaining',)],engine=engine,fuel=budget)
                assert got == {'created':True,'observations':[{'error':'OutOfFuel'},{'remaining':0}]}, got
        faults = f05_driver.run(F05_WORK,[f04_call('divide',results=1),f04_call('fault',results=1)],engine=engine)
        assert faults == {'created':True,'observations':[{'error':'DivByZero'},{'error':'OutOfBoundsLoad'}]}, faults


def test_budget_replacement_exact_fit_disable_and_new_invocation(f05_driver):
    for engine in ('interp','jit'):
        budget, measured = f05_completed_work(f05_driver,engine,37)
        cost = budget - measured[2]['remaining']
        exact = f05_driver.run(F05_WORK,[f04_call('work',[f02_arg(0,37)],1),('remaining',)],engine=engine,fuel=cost)
        assert exact == {'created':True,'observations':[f02_values((0,703)),{'remaining':0}]}, exact
        assert cost > 0, (engine,measured)
        below = f05_driver.run(F05_WORK,[f04_call('work',[f02_arg(0,37)],1),('remaining',)],engine=engine,fuel=cost-1)
        assert below == {'created':True,'observations':[{'error':'OutOfFuel'},{'remaining':0}]}, below
        # One assignment, then decreasing workloads on the same instance. A
        # per-invocation reset would make the later remainder rise.
        large_budget, _ = f05_completed_work(f05_driver,engine,61)
        shared_budget = min(4 * max(budget,large_budget),(1<<63)-1)
        cumulative = f05_driver.run(F05_WORK,[('fuel',shared_budget),
            f04_call('work',[f02_arg(0,61)],1),('remaining',),
            f04_call('work',[f02_arg(0,37)],1),('remaining',),
            f04_call('work',[f02_arg(0,11)],1),('remaining',),
            ('global','runs'),('bytes',0,4,'-')],engine=engine)
        assert cumulative['created'] is True, cumulative
        sequence = cumulative['observations']
        assert sequence[0] == {'remaining':shared_budget}, sequence
        assert sequence[1] == f02_values((0,1891)), sequence
        assert sequence[3] == f02_values((0,703)), sequence
        assert sequence[5] == f02_values((0,66)), sequence
        balances = [sequence[i]['remaining'] for i in (0,2,4,6)]
        assert all(0 <= later <= earlier for earlier,later in zip(balances,balances[1:])), sequence
        assert sequence[7:] == [{'kind':0,'bits':3},{'bytes':'42000000'}], sequence
        replacement = f05_driver.run(F05_WORK,
            [('fuel',shared_budget),('fuel',cost-1),f04_call('work',[f02_arg(0,37)],1),('remaining',)],engine=engine)
        assert replacement == {'created':True,'observations':[
            {'remaining':shared_budget},{'remaining':cost-1},
            {'error':'OutOfFuel'},{'remaining':0}]}, replacement
        # Exhaustion is read before replacement, so a reset cannot hide it.
        ops = [('fuel',17),f04_call('spin'),('remaining',),('global','runs'),
               ('fuel',budget),('remaining',),f04_call('work',[f02_arg(0,37)],1),
               ('remaining',),('global','runs'),('bytes',0,4,'-'),
               ('fuel',0),('fuel','none'),('remaining',),
               f04_call('work',[f02_arg(0,11)],1),('remaining',),('global','runs'),('bytes',0,4,'-')]
        got = f05_driver.run(F05_WORK,ops,engine=engine)
        assert got['created'] is True, got
        obs = got['observations']
        assert obs[:3] == [{'remaining':17},{'error':'OutOfFuel'},{'remaining':0}], obs
        assert obs[4:8] == [{'remaining':budget},{'remaining':budget},f02_values((0,703)),{'remaining':budget-cost}], obs
        assert obs[8] == {'kind':0,'bits':obs[3]['bits']+1}, obs
        assert obs[9:15] == [{'bytes':'bf020000'},{'remaining':0},{'remaining':None},{'remaining':None},
                             f02_values((0,66)),{'remaining':None}], obs
        assert obs[15:] == [{'kind':0,'bits':obs[3]['bits']+2},{'bytes':'42000000'}], obs
        # Same initial state and exhausted budget, with only disabling varied.
        disabled = f05_driver.run(F05_WORK,[('fuel','none'),f04_call('work',[f02_arg(0,37)],1),('remaining',)],
                                  engine=engine,fuel=cost-1)
        assert disabled == {'created':True,'observations':[{'remaining':None},f02_values((0,703)),{'remaining':None}]}, disabled



def test_live_memory_and_table_ceilings_preserve_and_release(f05_driver):
    guest = '''(module (memory (export "memory") 1 8) (table (export "table") 2 16 externref)
      (func (export "mgrow") (param i32) (result i32) local.get 0 memory.grow)
      (func (export "tgrow") (param i32 externref) (result i32) local.get 1 local.get 0 table.grow))'''
    original = '123400fe' + '00'*(65536-8) + 'a9ff0017'
    for engine in ('interp','jit'):
        # Guest instructions and host accessors have separate public growth
        # paths; exercising either alone cannot establish the other honors caps.
        for host in (False,True):
            ops = [('put',0,4,'123400fe'),('put',65532,4,'a9ff0017'),
                   ('tset','table',0,41),('tset','table',1,93)]
            expected = [{'bytes':'123400fe'},{'bytes':'a9ff0017'},{'ok':True},{'ok':True}]
            size_m,size_t = 1,2
            refs = [{'ref':41},{'ref':93}]
            for cap_m,cap_t,delta,token,allowed in ((1,2,1,73,False),(2,3,1,73,True),
                                                     (2,3,1,89,False),('none','none',2,89,True)):
                if allowed:
                    # Same history and growth request, but keep the ceiling at
                    # the current size. An implementation sensitive only to the
                    # attempt number must not pass as a live cap adjustment.
                    control_ops = ops + [('mcap',size_m),('tcap',size_t)]
                    control_expected = expected + [{'ok':True},{'ok':True}]
                    if host:
                        control_ops += [('mgrow',delta),('tgrow','table',delta,token)]
                        control_expected += [{'old':None},{'error':'GrowFailed'}]
                    else:
                        control_ops += [f04_call('mgrow',[f02_arg(0,delta)],1),
                                        f04_call('tgrow',[f02_arg(0,delta),(128,token)],1)]
                        control_expected += [f02_values((0,-1)),f02_values((0,-1))]
                    control_ops += [('msize',),('tsize','table'),('bytes',0,size_m*65536,'-'),('tscan','table',0,size_t)]
                    control_expected += [{'size':size_m},{'size':size_t},
                                         {'bytes':original+'00'*((size_m-1)*65536)},{'refs':list(refs)}]
                    control = f05_driver.run(guest,control_ops,engine=engine)
                    assert control == {'created':True,'observations':control_expected}, (engine,host,control)
                ops += [('mcap',cap_m),('tcap',cap_t)]
                expected += [{'ok':True},{'ok':True}]
                if host:
                    ops += [('mgrow',delta),('tgrow','table',delta,token)]
                    expected += [{'old':size_m if allowed else None}, {'ok':True} if allowed else {'error':'GrowFailed'}]
                else:
                    ops += [f04_call('mgrow',[f02_arg(0,delta)],1),f04_call('tgrow',[f02_arg(0,delta),(128,token)],1)]
                    expected += [f02_values((0,size_m if allowed else -1)),f02_values((0,size_t if allowed else -1))]
                if allowed:
                    size_m += delta; size_t += delta; refs += [{'ref':token}]*delta
                ops += [('msize',),('tsize','table'),('bytes',0,size_m*65536,'-'),('tscan','table',0,size_t)]
                expected += [{'size':size_m},{'size':size_t},{'bytes':original+'00'*((size_m-1)*65536)},{'refs':list(refs)}]
            got = f05_driver.run(guest,ops,engine=engine)
            assert got == {'created':True,'observations':expected}, (engine,host,got)

    # Independent resources must each receive the ceiling, not share a total
    # allowance. The public host memory view only addresses the first memory;
    # additional interpreter memories are observed through guest exports.
    for engine in ('interp','jit'):
        memory_count = 2 if engine == 'interp' else 1
        declarations = []
        for index in range(memory_count):
            declarations.append(f'''(memory $m{index} 1 8)
              (data (memory $m{index}) (i32.const 0) "\\21\\43\\65\\07")
              (data (memory $m{index}) (i32.const 65532) "\\76\\54\\32\\10")
              (func (export "grow{index}") (param i32) (result i32)
                local.get 0 memory.grow $m{index})
              (func (export "size{index}") (result i32) memory.size $m{index})
              (func (export "load{index}") (param i32) (result i32)
                local.get 0 i32.load $m{index})''')
        for index in range(2):
            declarations.append(f'''(table $t{index} (export "table{index}") 1 16 externref)
              (func (export "tgrow{index}") (param i32 externref) (result i32)
                local.get 1 local.get 0 table.grow $t{index})''')
        guest = '(module ' + ' '.join(declarations) + ')'
        prefix = [('tset',f'table{index}',0,41+index) for index in range(2)]
        expected = [{'ok':True},{'ok':True}]
        size = 1
        # Rebuild equal histories for each allowance arm. Both memories and
        # both tables grow in one instance, so aggregate accounting fails here.
        for ceiling in (2,3,'none'):
            for limit,allowed in ((size,False),(ceiling,True)):
                operations = prefix + [('mcap',limit),('tcap',limit)]
                results = expected + [{'ok':True},{'ok':True}]
                for index in range(memory_count):
                    operations += [f04_call(f'grow{index}',[f02_arg(0,1)],1)]
                    results += [f02_values((0,size if allowed else -1))]
                for index in range(2):
                    operations += [f04_call(f'tgrow{index}',[f02_arg(0,1),(128,73+index)],1)]
                    results += [f02_values((0,size if allowed else -1))]
                resulting_size = size + int(allowed)
                for index in range(memory_count):
                    operations += [f04_call(f'size{index}',results=1)]
                    results += [f02_values((0,resulting_size))]
                    for address,word in ((0,0x07654321),(65532,0x10325476)):
                        operations += [f04_call(f'load{index}',[f02_arg(0,address)],1)]
                        results += [f02_values((0,word))]
                    for page in range(1,resulting_size):
                        operations += [f04_call(f'load{index}',[f02_arg(0,page*65536)],1)]
                        results += [f02_values((0,0))]
                for index in range(2):
                    operations += [('tsize',f'table{index}'),('tscan',f'table{index}',0,resulting_size)]
                    results += [{'size':resulting_size},
                                {'refs':[{'ref':41+index}]+[{'ref':73+index}]*(resulting_size-1)}]
                got = f05_driver.run(guest,operations,engine=engine)
                assert got == {'created':True,'observations':results}, (engine,limit,got)
                if allowed:
                    next_prefix,next_expected = operations,results
            prefix,expected = next_prefix,next_expected
            size += 1


def test_cross_thread_cancellation_and_clear_recover(f05_driver):
    guest = '''(module (import "host" "pulse" (func $pulse))
      (func (export "spin") call $pulse (loop $loop br $loop))
      (func (export "work") (param i32) (result i32) call $pulse local.get 0 i32.const 7 i32.add))'''
    # Observe cancellation without a competing fuel-exhaustion condition.
    # The process watchdog remains a failing harness guard, never a result.
    for engine in ('interp','jit'):
        got = f05_driver.run(guest,[f04_call('work',[f02_arg(0,13)],1),
            ('cancel',),f04_call('spin'),('remaining',),('clear',),f04_call('work',[f02_arg(0,31)],1),
            ('cancel',),f04_call('spin'),('clear',),f04_call('work',[f02_arg(0,-12)],1)],engine=engine,linked=True)
        assert got['created'] is True, got
        assert got == {'created':True,'observations':[
            f02_values((0,20)),{'error':'Interrupted'},{'remaining':None},{'ok':True},f02_values((0,38)),
            {'error':'Interrupted'},{'ok':True},f02_values((0,-5))]}, got


def test_creation_limits_distinguish_memory_table_and_start_failure(f05_driver):
    body = '''(memory (export "memory") 2 8) (table (export "table") 3 16 externref)
      (func (export "ok") (result i32) i32.const 29)'''
    for engine in ('interp','jit'):
        for memory,table in ((2,3),(3,4),('none','none')):
            got = f05_driver.run('(module '+body+')',[f04_call('ok',results=1),('msize',),('tsize','table')],
                                engine=engine,memory=memory,table=table)
            assert got == {'created':True,'observations':[f02_values((0,29)),{'size':2},{'size':3}]}, got
        for memory,table,error in ((1,3,'MemoryLimitExceeded'),(2,2,'TableLimitExceeded')):
            got = f05_driver.run('(module '+body+')',engine=engine,memory=memory,table=table)
            assert got == {'created':False,'error':error}, got
        live = '(module '+body+'''
          (func (export "mgrow") (result i32) i32.const 1 memory.grow)
          (func (export "tgrow") (result i32) ref.null extern i32.const 1 table.grow))'''
        for ops, expected in (([('mgrow',1),('tgrow','table',1,0)],
                               [{'old':None},{'error':'GrowFailed'}]),
                              ([f04_call('mgrow',results=1),f04_call('tgrow',results=1)],
                               [f02_values((0,-1)),f02_values((0,-1))])):
            got = f05_driver.run(live,ops+[('msize',),('tsize','table')],engine=engine,memory=2,table=3)
            assert got == {'created':True,'observations':expected+[{'size':2},{'size':3}]}, got
        later = '(module (table 1 16 externref) (table 4 16 externref))'
        got = f05_driver.run(later,engine=engine,table=3)
        assert got == {'created':False,'error':'TableLimitExceeded'}, got
        trapped = f05_driver.run('(module '+body+' (func $start unreachable) (start $start))',
                                engine=engine,memory=2,table=3)
        assert trapped == {'created':False,'error':'StartTrapped'}, trapped
