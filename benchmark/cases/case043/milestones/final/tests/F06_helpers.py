# feature: F06
"""Execution-selection observer using only the public C embedding surface.

Earlier features own guest assembly, scalar encoding, callbacks, entity creation,
and export invocation. This adapter adds selected-mode and shared-state reads.
The JSON keys are observer transport, not product output requirements.
"""
import json
import os

import pytest
from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG, f02_arg, f02_values
from F03_helpers import F03_C, F03_ZIG
from _helpers import build_outputs, run_json_adapter

F06_C = r'''
static void f6_mode(wasm_instance_t *inst) {
    int32_t selected=-99;
    bool ok=navor_instance_engine(inst,&selected);
    printf("{\"ok\":%s,\"selected\":%d}",ok?"true":"false",selected);
}
static void f6_state(F3Entities *h,const char *action) {
    if(!strcmp(action,"memory")) {
        NEED(wasm_memory_data_size(h->mem)>7);
        printf("%u",(unsigned char)wasm_memory_data(h->mem)[7]);
    } else if(!strcmp(action,"global")) {
        wasm_val_t v; wasm_global_get(h->global,&v); value(&v); wasm_val_delete(&v);
    } else {
        NEED(!strcmp(action,"table"));
        wasm_ref_t *r=wasm_table_get(h->table,0);
        printf("{\"first\":%s,\"second\":%s}",
            r && wasm_ref_same(r,wasm_foreign_as_ref(h->first))?"true":"false",
            r && wasm_ref_same(r,wasm_foreign_as_ref(h->second))?"true":"false");
        if(r) wasm_ref_delete(r);
    }
}
int f06_main(int argc,char **argv) {
    NEED(argc>=4); int mode=(int)number(argv[1]); const char *action=argv[2];
    int state=!strcmp(action,"memory") || !strcmp(action,"table") || !strcmp(action,"global");
    wasm_byte_vec_t bytes=f3_bytes(argv[3]);
    wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s);
    wasm_module_t *m=wasm_module_new(s,&bytes); wasm_byte_vec_delete(&bytes);
    printf("{\"loaded\":%s",m?"true":"false");
    if(m) {
        F3Entities h=f3_entities(s);
        wasm_importtype_vec_t types; wasm_module_imports(m,&types);
        wasm_extern_t **import_storage=calloc(types.size ? types.size : 1,sizeof(*import_storage)); NEED(import_storage);
    wasm_extern_vec_t imports={types.size,import_storage};
        wasm_func_t *callback=NULL;
        for(size_t i=0;i<types.size;i++) {
            const wasm_externtype_t *t=wasm_importtype_type(types.data[i]);
            switch(wasm_externtype_kind(t)) {
                case WASM_EXTERN_MEMORY: imports.data[i]=wasm_memory_as_extern(h.mem); break;
                case WASM_EXTERN_GLOBAL: imports.data[i]=wasm_global_as_extern(h.global); break;
                case WASM_EXTERN_TABLE: imports.data[i]=wasm_table_as_extern(h.table); break;
                case WASM_EXTERN_FUNC:
                    NEED(!callback);
                    callback=wasm_func_new(s,wasm_externtype_as_functype_const(t),observe); NEED(callback);
                    imports.data[i]=wasm_func_as_extern(callback); break;
                default: NEED(0);
            }
            NEED(imports.data[i]);
        }
        wasm_trap_t *trap=NULL; F3Instance p=f3_instance(s,m,&imports,mode,&trap);
        printf(",\"created\":%s,\"trap\":%d",p.instance?"true":"false",navor_trap_kind(trap));
        if(trap) wasm_trap_delete(trap);
        if(p.instance) {
            if(!strcmp(action,"coexisting")) {
                wasm_trap_t *other_trap=NULL;
                F3Instance other=f3_instance(s,m,&imports,mode==1?2:0,&other_trap);
                NEED(other.instance && !other_trap);
                printf(",\"other\":"); f6_mode(other.instance);
                printf(",\"retained\":"); f6_mode(p.instance);
                f3_drop(&other);
            }
            printf(",\"before\":"); f6_mode(p.instance);
            if(state) {
                printf(",\"initial_host\":"); f6_state(&h,action);
                printf(",\"initial_guest\":"); f3_call(&p,"read",NULL,0,1);
                if(!strcmp(action,"memory")) wasm_memory_data(h.mem)[7]=37;
                else if(!strcmp(action,"global")) { wasm_val_t v={.kind=WASM_I32,.of.i32=-19}; wasm_global_set(h.global,&v); }
                else NEED(wasm_table_set(h.table,0,wasm_foreign_as_ref(h.first)));
                printf(",\"host_write\":"); f3_call(&p,"read",NULL,0,1);
            }
            printf(",\"calls\":"); f3_calls(&p,argc-4,argv+4);
            if(state) { printf(",\"final_guest\":"); f3_call(&p,"read",NULL,0,1);
                printf(",\"final_host\":"); f6_state(&h,action); }
            printf(",\"after\":"); f6_mode(p.instance);
        }
        printf(",\"events\":["); for(size_t i=0;i<nevents;i++) { if(i) putchar(','); printf("%d",events[i]); } putchar(']');
        f3_drop(&p); free(import_storage); wasm_importtype_vec_delete(&types);
        if(callback) wasm_func_delete(callback);
        f3_entities_drop(&h); wasm_foreign_delete(h.first); wasm_foreign_delete(h.second);
        wasm_module_delete(m);
    }
    puts("}"); wasm_store_delete(s); wasm_engine_delete(e); return 0;
}
'''


class F06Driver:
    def __init__(self, compiler, directory):
        self.compiler, self.directory = compiler, directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F06')

    def run(self, source, calls=(), *, mode=0, action='plain', valid=True, features='all'):
        binary = self.compiler.wat(source)
        assert self.compiler.standard_valid(binary, features=features) is valid, source
        self.serial += 1
        path = self.directory / f'guest-{self.serial}.wasm'
        path.write_bytes(binary)
        command = [self.program(),str(mode),action,path]
        for name,args,nresults in calls:
            command.extend([name,str(len(args)),str(nresults)])
            for kind,bits in args:
                command.extend([str(kind),str(bits)])
        result = run_json_adapter(command,timeout=30)
        path.with_suffix('.observation.json').write_bytes(result.process.stdout)
        return result.value


@pytest.fixture(scope='session')
def f06_driver(f01_driver,tmp_path_factory):
    return F06Driver(f01_driver,tmp_path_factory.mktemp('f06-consumer'))

F06_CORE = '''(module
 (func (export "run") (param i32 i32) (result i32)
   local.get 0 local.get 0 i32.mul local.get 1 i32.sub))'''

F06_ENTITIES = {
    'memory': '''(module
      (import "env" "memory" (memory 1 4))
      (func (export "read") (result i32) i32.const 7 i32.load8_u)
      (func (export "write") (param i32) i32.const 7 local.get 0 i32.store8))''',
    'global': '''(module
      (import "env" "global" (global $g (mut i32)))
      (func (export "read") (result i32) global.get $g)
      (func (export "write") (param i32) local.get 0 global.set $g))''',
    'table': '''(module
      (import "env" "table" (table 2 5 externref))
      (func (export "read") (result i32) i32.const 0 table.get ref.is_null)
      (func (export "write") (param i32)
        i32.const 0 i32.const 1 table.get table.set))''',
}


def f06_check_mode(observation, selected):
    """Assert public query success and the mode both before and after calls."""
    assert observation['loaded'] is True, observation
    assert observation['created'] is True, observation
    assert observation['trap'] == -1, observation
    for field in ('before', 'after'):
        assert observation[field] == {'ok': True, 'selected': selected}, observation


def consumer_sources():
    return {'F06': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f06_main(argc, argv);')
                + F03_ZIG + '\nextern fn f06_main(c_int, [*][*:0]u8) c_int;\n', F02_C + F03_C + F06_C, ('v3_0',))}
