# feature: F03
"""Public embedding consumers for import binding and host services.

Reuse the preceding consumer's scalar transport and prerequisite checks. The
adapter only transports public returns; Python owns the acceptance assertions.
All guest inputs are assembled and independently validated by wasm-tools.
"""
import json
import os
import pytest
from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG, f02_arg, f02_values
from _helpers import build_outputs, run_json_adapter

F03_C = r'''
extern int f03_zig(const unsigned char*, size_t, const unsigned char*, size_t, int, const char*, int, char**);
static wasm_store_t *f3_store;
static wasm_memory_t *f3_memory;
static int f3_variant;
static wasm_val_t f3_seen[32][5];
static size_t f3_seen_n;
static size_t f3_seen_sizes[32];
void f3_record(int32_t a,int32_t b,int64_t c,float d,double e) {
    NEED(f3_seen_n<32); f3_seen_sizes[f3_seen_n]=5; wasm_val_t *v=f3_seen[f3_seen_n++];
    v[0]=(wasm_val_t){.kind=WASM_I32,.of.i32=a}; v[1]=(wasm_val_t){.kind=WASM_I32,.of.i32=b};
    v[2]=(wasm_val_t){.kind=WASM_I64,.of.i64=c}; v[3]=(wasm_val_t){.kind=WASM_F32,.of.f32=d};
    v[4]=(wasm_val_t){.kind=WASM_F64,.of.f64=e};
}
static void f3_records(void) {
    printf(",\"received\":["); for(size_t i=0;i<f3_seen_n;i++) { if(i) putchar(','); putchar('[');
        for(size_t j=0;j<f3_seen_sizes[i];j++) { if(j) putchar(','); value(&f3_seen[i][j]); } putchar(']'); } putchar(']');
}
static wasm_trap_t *f3_mix(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==5 && r->size==1 && f3_memory && wasm_memory_data_size(f3_memory)>9);
    f3_record(a->data[0].of.i32,a->data[1].of.i32,a->data[2].of.i64,a->data[3].of.f32,a->data[4].of.f64);
    unsigned char *p=(unsigned char*)wasm_memory_data(f3_memory);
    p[9]=(unsigned char)(p[9]+a->data[1].of.i32);
    r->data[0]=(wasm_val_t){.kind=WASM_F64,.of.f64=f3_variant ? a->data[4].of.f64-a->data[3].of.f32 : a->data[4].of.f64+a->data[3].of.f32};
    return NULL;
}
void f3_record_pair(int32_t a,int32_t b) {
    NEED(f3_seen_n<32); f3_seen_sizes[f3_seen_n]=2; wasm_val_t *v=f3_seen[f3_seen_n++];
    v[0]=(wasm_val_t){.kind=WASM_I32,.of.i32=a}; v[1]=(wasm_val_t){.kind=WASM_I32,.of.i32=b};
}
static wasm_trap_t *f3_pair_callback(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==2 && r->size==1 && f3_memory && wasm_memory_data_size(f3_memory)>9);
    int32_t x=a->data[0].of.i32,y=a->data[1].of.i32; f3_record_pair(x,y);
    unsigned char *p=(unsigned char*)wasm_memory_data(f3_memory); p[9]=(unsigned char)(p[9]+y);
    r->data[0]=(wasm_val_t){.kind=WASM_I32,.of.i32=f3_variant?y*3-x:x*3-y}; return NULL;
}
static wasm_trap_t *f3_float(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==2 && r->size==1 && f3_seen_n<32); f3_seen_sizes[f3_seen_n]=2;
    memcpy(f3_seen[f3_seen_n++],a->data,2*sizeof(wasm_val_t));
    r->data[0]=(wasm_val_t){.kind=WASM_F64,.of.f64=a->data[1].of.f64-a->data[0].of.f32}; return NULL;
}
static wasm_trap_t *f3_single(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==1 && r->size==1); r->data[0]=(wasm_val_t){.kind=WASM_F32,.of.f32=a->data[0].of.f32*-2}; return NULL;
}
static wasm_trap_t *f3_multi(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==2 && r->size==2); int32_t x=a->data[0].of.i32,y=a->data[1].of.i32; f3_record_pair(x,y);
    r->data[0]=(wasm_val_t){.kind=WASM_I64,.of.i64=(int64_t)x*8589934592LL+y};
    r->data[1]=(wasm_val_t){.kind=WASM_I32,.of.i32=x-y}; return NULL;
}
static wasm_trap_t *f3_wide(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==2 && r->size==1); r->data[0]=(wasm_val_t){.kind=WASM_I64,.of.i64=a->data[0].of.i64-a->data[1].of.i64}; return NULL;
}
static wasm_trap_t *f3_fail(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==0 && r->size==0);
    if(!f3_variant) return NULL;
    wasm_message_t msg; wasm_byte_vec_new(&msg,18,"host request abort");
    wasm_trap_t *t=wasm_trap_new(f3_store,&msg); wasm_byte_vec_delete(&msg); NEED(t); return t;
}
static wasm_trap_t *f3_linear(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==1 && r->size==1); r->data[0]=(wasm_val_t){.kind=WASM_I32,.of.i32=a->data[0].of.i32*3+1}; return NULL;
}
static void f3_direct_errors(wasm_store_t *store) {
    wasm_functype_t *type=wasm_functype_new_1_1(wasm_valtype_new(WASM_I32),wasm_valtype_new(WASM_I32));
    wasm_func_t *fn=wasm_func_new(store,type,f3_linear); NEED(fn); wasm_functype_delete(type);
    wasm_val_t av[2]={{.kind=WASM_I32,.of.i32=8},{.kind=WASM_I32,.of.i32=3}},rv[2]={{0},{0}};
    wasm_val_vec_t args={1,av},results={1,rv}; wasm_trap_t *trap=wasm_func_call(fn,&args,&results); NEED(!trap);
    printf("{\"baseline\":%d,\"refusals\":[",rv[0].of.i32);
    const size_t counts[4][2]={{0,1},{2,1},{1,0},{1,2}};
    for(size_t i=0;i<4;i++) {
        args.size=counts[i][0];results.size=counts[i][1];trap=wasm_func_call(fn,&args,&results);
        if(i) putchar(','); printf("%d",navor_trap_kind(trap)); if(trap) wasm_trap_delete(trap);
    }
    wasm_func_delete(fn);
    wasm_valtype_vec_t params={0,NULL},returns={0,NULL};
    type=wasm_functype_new(&params,&returns);fn=wasm_func_new(store,type,f3_fail);NEED(fn);wasm_functype_delete(type);
    args.size=0;results.size=0;f3_variant=1;trap=wasm_func_call(fn,&args,&results);NEED(trap);
    wasm_message_t msg;wasm_trap_message(trap,&msg);
    printf("],\"failure\":%d,\"message\":[",navor_trap_kind(trap));
    for(size_t i=0;i<msg.size;i++){if(i) putchar(',');printf("%u",(unsigned char)msg.data[i]);}
    printf("]}");wasm_byte_vec_delete(&msg);wasm_trap_delete(trap);wasm_func_delete(fn);
}
static wasm_byte_vec_t f3_bytes(const char *path) {
    FILE *f=fopen(path,"rb"); NEED(f); NEED(!fseek(f,0,SEEK_END)); long n=ftell(f); NEED(n>=0); rewind(f);
    wasm_byte_vec_t b; wasm_byte_vec_new_uninitialized(&b,(size_t)n); NEED(b.data || !n);
    NEED(fread(b.data,1,b.size,f)==b.size); NEED(!fclose(f)); return b;
}
typedef struct { wasm_module_t *module; wasm_instance_t *instance; wasm_extern_vec_t exports; wasm_exporttype_vec_t names; } F3Instance;
static F3Instance f3_instance(wasm_store_t *s,wasm_module_t *m,wasm_extern_vec_t *im,int mode,wasm_trap_t **trap) {
    F3Instance p={.module=m}; p.instance=navor_instance_new_ex(s,m,im,trap,mode);
    if(p.instance) { NEED(!*trap); wasm_instance_exports(p.instance,&p.exports); wasm_module_exports(m,&p.names); NEED(p.exports.size==p.names.size); }
    return p;
}
static wasm_extern_t *f3_export(F3Instance *p,const char *name) {
    for(size_t i=0;i<p->names.size;i++) if(named(wasm_exporttype_name(p->names.data[i]),name)) return p->exports.data[i];
    fprintf(stderr,"Missing adapter export: %s\n",name); exit(70);
}
static void f3_drop(F3Instance *p) {
    wasm_extern_vec_delete(&p->exports); wasm_exporttype_vec_delete(&p->names);
    if(p->instance) wasm_instance_delete(p->instance); p->instance=NULL;
}
static void f3_call(F3Instance *p,const char *name,wasm_val_t *a,size_t na,size_t nr) {
    wasm_func_t *f=wasm_extern_as_func(f3_export(p,name)); NEED(f && nr<=16);
    wasm_val_t rv[16]={0}; wasm_val_vec_t av={na,a},res={nr,rv}; wasm_trap_t *t=wasm_func_call(f,&av,&res);
    if(t) { printf("{\"trap\":%d}",navor_trap_kind(t)); wasm_trap_delete(t); }
    else { printf("{\"values\":["); for(size_t i=0;i<nr;i++) { if(i) putchar(','); value(rv+i); wasm_val_delete(rv+i); } printf("]}"); }
}
static void f3_calls(F3Instance *p,int argc,char **argv) {
    putchar('['); int pos=0,first=1;
    while(pos<argc) {
        NEED(pos+3<=argc); const char *name=argv[pos++]; size_t na=number(argv[pos++]),nr=number(argv[pos++]);
        NEED(na<=16 && pos+(int)(na*2)<=argc); wasm_val_t args[16]={0};
        for(size_t i=0;i<na;i++) { args[i].kind=number(argv[pos++]); uint64_t bits=number(argv[pos++]); uint32_t small=(uint32_t)bits;
            switch(args[i].kind) { case WASM_I32: memcpy(&args[i].of.i32,&small,4); break; case WASM_I64: memcpy(&args[i].of.i64,&bits,8); break;
              case WASM_F32: memcpy(&args[i].of.f32,&small,4); break; case WASM_F64: memcpy(&args[i].of.f64,&bits,8); break; default: NEED(0); }
        }
        if(!first) putchar(','); first=0; f3_call(p,name,args,na,nr);
    } putchar(']');
}
static wasm_extern_vec_t f3_bind(F3Instance *provider,wasm_module_t *consumer,int missing) {
    wasm_importtype_vec_t names; wasm_module_imports(consumer,&names);
    wasm_extern_vec_t bindings; wasm_extern_vec_new_uninitialized(&bindings,missing?0:names.size);
    for(size_t i=0;i<bindings.size;i++) {
        const wasm_name_t *name=wasm_importtype_name(names.data[i]); wasm_extern_t *found=NULL;
        for(size_t j=0;j<provider->names.size;j++) { const wasm_name_t *n=wasm_exporttype_name(provider->names.data[j]);
            if(n->size==name->size && !memcmp(n->data,name->data,n->size)) found=provider->exports.data[j]; }
        NEED(found); bindings.data[i]=wasm_extern_copy(found); NEED(bindings.data[i]);
    } wasm_importtype_vec_delete(&names); return bindings;
}
static void f3_pair(wasm_store_t *s,wasm_engine_t *e,wasm_module_t *m,wasm_byte_vec_t *provider,int mode,const char *action,int argc,char **argv) {
    int cross=!strcmp(action,"cross"),module_cross=!strcmp(action,"module-cross"),share=!strcmp(action,"share");
    wasm_store_t *other=(cross || module_cross || share)?wasm_store_new(e):NULL; if(cross || module_cross || share) NEED(other);
    wasm_store_t *ps=other?other:s;
    wasm_module_t *pm=wasm_module_new(ps,provider); NEED(pm);
    wasm_extern_vec_t empty={0,NULL}; wasm_trap_t *trap=NULL;
    F3Instance p=f3_instance(ps,pm,&empty,mode,&trap); NEED(p.instance && !trap);
    wasm_module_t *target=m;
    if(module_cross || share) { target=pm; if(share) { wasm_shared_module_t *sh=wasm_module_share(pm); NEED(sh); target=wasm_module_obtain(s,sh); NEED(target); wasm_shared_module_delete(sh); } }
    wasm_extern_vec_t bindings=(module_cross || share)?empty:f3_bind(&p,m,!strcmp(action,"missing"));
    F3Instance c=f3_instance(s,target,&bindings,mode,&trap);
    printf("{\"created\":%s,\"trap\":%d",c.instance?"true":"false",navor_trap_kind(trap));
    if(trap) { wasm_trap_delete(trap); trap=NULL; }
    if(!strcmp(action,"release")) { wasm_extern_vec_delete(&bindings); f3_drop(&p); wasm_module_delete(pm); pm=NULL; }
    if(c.instance) { printf(",\"calls\":"); f3_calls(&c,argc,argv);
        if(!strcmp(action,"compose")) { printf(",\"provider\":"); f3_call(&p,"state",NULL,0,1); }
    }
    printf("}"); f3_drop(&c); if(strcmp(action,"release")) { wasm_extern_vec_delete(&bindings); f3_drop(&p); }
    if(share) wasm_module_delete(target); if(pm) wasm_module_delete(pm); if(other) wasm_store_delete(other);
}
static void f3_host(wasm_store_t *s,wasm_module_t *m,int mode,int argc,char **argv,int direct_mode) {
    wasm_importtype_vec_t types; wasm_module_imports(m,&types); wasm_extern_t **import_storage=calloc(types.size ? types.size : 1,sizeof(*import_storage)); NEED(import_storage);
    wasm_extern_vec_t imports={types.size,import_storage};
    for(size_t i=0;i<types.size;i++) { const wasm_functype_t *ft=wasm_externtype_as_functype_const(wasm_importtype_type(types.data[i])); NEED(ft);
        const wasm_name_t *n=wasm_importtype_name(types.data[i]); wasm_func_callback_t cb;
        if(named(n,"mix")) cb=f3_mix; else if(named(n,"pair")) cb=f3_pair_callback; else if(named(n,"linear")) cb=f3_linear; else if(named(n,"float")) cb=f3_float; else if(named(n,"single")) cb=f3_single; else if(named(n,"wide")) cb=f3_wide; else if(named(n,"multi")) cb=f3_multi; else { NEED(named(n,"fail")); cb=f3_fail; }
        wasm_func_t *f=wasm_func_new(s,ft,cb); NEED(f); imports.data[i]=wasm_func_as_extern(f);
    }
    if(direct_mode) {
        wasm_func_t *direct=wasm_extern_as_func(imports.data[0]); NEED(direct);
        wasm_val_t av[1]={{.kind=WASM_I32,.of.i32=41}},rv[1]={{0}};
        wasm_val_vec_t aa={1,av},rr={1,rv}; wasm_trap_t *dt=wasm_func_call(direct,&aa,&rr);
        printf("{\"created\":%s,\"trap\":%d",dt?"false":"true",navor_trap_kind(dt));
        if(dt) wasm_trap_delete(dt); else { printf(",\"direct\":"); value(&rv[0]); }
        printf("}");
        for(size_t i=0;i<imports.size;i++) wasm_func_delete(wasm_extern_as_func(imports.data[i]));
        free(import_storage); wasm_importtype_vec_delete(&types); return;
    }
    wasm_trap_t *trap=NULL; F3Instance p=f3_instance(s,m,&imports,mode,&trap);
    printf("{\"created\":%s,\"trap\":%d",p.instance?"true":"false",navor_trap_kind(trap));
    if(p.instance) { f3_memory=wasm_extern_as_memory(f3_export(&p,"memory")); NEED(f3_memory); printf(",\"calls\":"); f3_calls(&p,argc,argv); }
    if(trap) wasm_trap_delete(trap); f3_records(); putchar('}'); f3_drop(&p);
    for(size_t i=0;i<imports.size;i++) wasm_func_delete(wasm_extern_as_func(imports.data[i]));
    free(import_storage);
    wasm_importtype_vec_delete(&types);
}
typedef struct { wasm_func_t *fn; wasm_foreign_t *first,*second; wasm_memory_t *mem; wasm_global_t *global; wasm_table_t *table; } F3Entities;
static F3Entities f3_entities(wasm_store_t *s) {
    wasm_valtype_t *in=wasm_valtype_new(WASM_I32),*out=wasm_valtype_new(WASM_I32); NEED(in && out);
    wasm_valtype_vec_t av,rv; wasm_valtype_vec_new(&av,1,&in); wasm_valtype_vec_new(&rv,1,&out);
    wasm_functype_t *ft=wasm_functype_new(&av,&rv); NEED(ft);
    F3Entities h={0}; h.fn=wasm_func_new(s,ft,f3_linear); wasm_functype_delete(ft); NEED(h.fn);
    h.first=wasm_foreign_new(s); h.second=wasm_foreign_new(s); NEED(h.first && h.second);
    wasm_limits_t ml={1,3},tl={2,4}; wasm_memorytype_t *mt=wasm_memorytype_new(&ml); NEED(mt); h.mem=wasm_memory_new(s,mt); wasm_memorytype_delete(mt); NEED(h.mem);
    wasm_globaltype_t *gt=wasm_globaltype_new(wasm_valtype_new(WASM_I32),WASM_VAR); NEED(gt); wasm_val_t initial={.kind=WASM_I32,.of.i32=7};
    h.global=wasm_global_new(s,gt,&initial); wasm_globaltype_delete(gt); NEED(h.global);
    wasm_tabletype_t *tt=wasm_tabletype_new(wasm_valtype_new(WASM_EXTERNREF),&tl); NEED(tt); h.table=wasm_table_new(s,tt,NULL); wasm_tabletype_delete(tt); NEED(h.table); NEED(wasm_table_set(h.table,1,wasm_foreign_as_ref(h.second)));
    NEED(wasm_memory_data_size(h.mem)>7); wasm_memory_data(h.mem)[7]=11; return h;
}
static void f3_entities_drop(F3Entities *h) { wasm_func_delete(h->fn);  wasm_memory_delete(h->mem); wasm_global_delete(h->global); wasm_table_delete(h->table); }
static F3Instance f3_entity_instance(wasm_store_t *s,wasm_module_t *m,F3Entities *h,wasm_trap_t **t) {
    wasm_extern_t *v[]={wasm_func_as_extern(h->fn),wasm_memory_as_extern(h->mem),wasm_global_as_extern(h->global),wasm_table_as_extern(h->table)};
    wasm_extern_vec_t im={4,v}; return f3_instance(s,m,&im,2,t);
}
static void f3_states(F3Instance *a,F3Instance *b,F3Instance *c) { putchar('['); f3_call(a,"read",NULL,0,4); putchar(','); f3_call(b,"read",NULL,0,4); putchar(','); f3_call(c,"read",NULL,0,4); putchar(']'); }
static void f3_shared(wasm_store_t *s,wasm_module_t *m,int release) {
    F3Entities h=f3_entities(s),independent=f3_entities(s); wasm_trap_t *t=NULL;
    F3Instance a=f3_entity_instance(s,m,&h,&t); NEED(a.instance && !t);
    F3Instance b=f3_entity_instance(s,m,&h,&t); NEED(b.instance && !t);
    F3Instance c=f3_entity_instance(s,m,&independent,&t); NEED(c.instance && !t);
    printf("{\"initial\":"); f3_states(&a,&b,&c);
    wasm_memory_data(h.mem)[7]=37; wasm_val_t next={.kind=WASM_I32,.of.i32=-19}; wasm_global_set(h.global,&next);
    NEED(wasm_table_set(h.table,0,wasm_foreign_as_ref(h.first)));
    if(release) f3_entities_drop(&h);
    printf(",\"host_write\":"); f3_states(&a,&b,&c);
    wasm_val_t args[]={{.kind=WASM_I32,.of.i32=91},{.kind=WASM_I32,.of.i32=53}};
    printf(",\"write\":"); f3_call(&a,"write",args,2,0);
    printf(",\"guest_write\":"); f3_states(&a,&b,&c);
    if(!release) { wasm_val_t v; wasm_global_get(h.global,&v); printf(",\"host_global\":"); value(&v);
        printf(",\"host_byte\":%u",(unsigned char)wasm_memory_data(h.mem)[7]);
        wasm_ref_t *ref=wasm_table_get(h.table,0); NEED(ref);
        printf(",\"host_table_same\":%s",wasm_ref_same(ref,wasm_foreign_as_ref(h.second))?"true":"false"); wasm_ref_delete(ref); }
    wasm_table_t *bt=wasm_extern_as_table(f3_export(&b,"table")); NEED(bt); wasm_ref_t *br=wasm_table_get(bt,0); NEED(br);
    printf(",\"peer_table_same\":%s",wasm_ref_same(br,wasm_foreign_as_ref(h.second))?"true":"false"); wasm_ref_delete(br);
    putchar('}'); f3_drop(&c); f3_drop(&b); f3_drop(&a); if(!release) f3_entities_drop(&h); f3_entities_drop(&independent); wasm_foreign_delete(h.first); wasm_foreign_delete(h.second); wasm_foreign_delete(independent.first); wasm_foreign_delete(independent.second);
}
static void f3_host_owner(wasm_store_t *s,wasm_engine_t *e,wasm_module_t *m,int mode,const char *action,int argc,char **argv) {
    int cross=!strcmp(action,"host-cross"),release=!strcmp(action,"host-release");
    wasm_store_t *other=cross?wasm_store_new(e):NULL; if(cross) NEED(other);
    F3Entities h=f3_entities(cross?other:s); wasm_importtype_vec_t types; wasm_module_imports(m,&types); NEED(types.size==1);
    wasm_extern_t *ext=NULL;
    switch(wasm_externtype_kind(wasm_importtype_type(types.data[0]))) {
      case WASM_EXTERN_FUNC: ext=wasm_func_as_extern(h.fn); break;
      case WASM_EXTERN_GLOBAL: ext=wasm_global_as_extern(h.global); break;
      case WASM_EXTERN_MEMORY: ext=wasm_memory_as_extern(h.mem); break;
      case WASM_EXTERN_TABLE: ext=wasm_table_as_extern(h.table); break;
      default: NEED(0);
    }
    NEED(ext); wasm_extern_vec_t im={1,&ext}; wasm_trap_t *trap=NULL; F3Instance p=f3_instance(s,m,&im,mode,&trap);
    printf("{\"created\":%s,\"trap\":%d",p.instance?"true":"false",navor_trap_kind(trap));
    if(trap) wasm_trap_delete(trap);
    if(release) f3_entities_drop(&h);
    if(p.instance) { printf(",\"calls\":"); f3_calls(&p,argc,argv); }
    putchar('}'); f3_drop(&p); if(!release) f3_entities_drop(&h);
    wasm_foreign_delete(h.first); wasm_foreign_delete(h.second); wasm_importtype_vec_delete(&types); if(other) wasm_store_delete(other);
}

static int f3_cleanups, f3_wrong_env; static int32_t f3_context=47;
static wasm_trap_t *f3_context_call(void *env,const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    r->data[0].kind=WASM_I32; r->data[0].of.i32=a->data[0].of.i32+*(int32_t*)env; return NULL;
}
static void f3_cleanup(void *env) { f3_cleanups++; if(env!=&f3_context) f3_wrong_env++; }
static void f3_lifetime(wasm_engine_t *e,const wasm_byte_vec_t *bytes,int mode) {
    printf("{\"lifetime\":[");
    for(int release=0;release<2;release++) {
        if(release) putchar(','); f3_cleanups=0; f3_wrong_env=0;
        wasm_store_t *store=wasm_store_new(e); NEED(store);
        wasm_module_t *m=wasm_module_new(store,bytes); NEED(m);
        wasm_functype_t *ty=wasm_functype_new_1_1(wasm_valtype_new(WASM_I32),wasm_valtype_new(WASM_I32)); NEED(ty);
        wasm_func_t *f=wasm_func_new_with_env(store,ty,f3_context_call,&f3_context,f3_cleanup); NEED(f); wasm_functype_delete(ty);
        wasm_extern_t *ex=wasm_func_as_extern(f); wasm_extern_vec_t imports={1,&ex}; wasm_trap_t *trap=NULL;
        F3Instance inst=f3_instance(store,m,&imports,mode,&trap); NEED(inst.instance && !trap);
        if(release) wasm_func_delete(f);
        wasm_val_t av[1]={{.kind=WASM_I32,.of.i32=19}},rv[1]={{0}}; wasm_val_vec_t a={1,av},r={1,rv};
        trap=wasm_func_call(wasm_extern_as_func(f3_export(&inst,"run")),&a,&r); NEED(!trap);
        printf("{\"result\":%d,\"before\":%d",rv[0].of.i32,f3_cleanups);
        f3_drop(&inst); wasm_module_delete(m); wasm_store_delete(store);
        printf(",\"after\":%d,\"wrong_env\":%d}",f3_cleanups,f3_wrong_env);
    }
    printf("]}");
}
int f03_main(int argc,char **argv) {
    NEED(argc>=7); const char *api=argv[1],*action=argv[2]; int mode=(int)number(argv[3]); f3_variant=(int)number(argv[4]);
    wasm_byte_vec_t b=f3_bytes(argv[5]),p=f3_bytes(argv[6]);
    if(!strcmp(api,"zig")) { int rc=f03_zig((unsigned char*)b.data,b.size,(unsigned char*)p.data,p.size,mode,action,argc-7,argv+7); f3_records(); putchar('}'); wasm_byte_vec_delete(&p); wasm_byte_vec_delete(&b); return rc; }
    NEED(!strcmp(api,"c")); wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s); f3_store=s;
    wasm_module_t *m=wasm_module_new(s,&b); NEED(m);
    if(!strcmp(action,"direct-errors")) f3_direct_errors(s);
    else if(!strcmp(action,"lifetime")) f3_lifetime(e,&b,mode);
    else if(!strcmp(action,"host")) f3_host(s,m,mode,argc-7,argv+7,0);
    else if(!strcmp(action,"host-direct")) f3_host(s,m,mode,argc-7,argv+7,1);
    else if(!strcmp(action,"entities") || !strcmp(action,"entities-release")) f3_shared(s,m,!strcmp(action,"entities-release"));
    else if(!strcmp(action,"host-cross") || !strcmp(action,"host-bind") || !strcmp(action,"host-release")) f3_host_owner(s,e,m,mode,action,argc-7,argv+7);
    else f3_pair(s,e,m,&p,mode,action,argc-7,argv+7);
    wasm_module_delete(m); wasm_store_delete(s); wasm_engine_delete(e); wasm_byte_vec_delete(&b); wasm_byte_vec_delete(&p); return 0;
}
int f3_get_variant(void) { return f3_variant; }
'''

F03_ZIG = r'''
extern fn f03_main(c_int, [*][*:0]u8) c_int;
extern fn f3_get_variant() c_int;
extern fn f3_record(i32,i32,i64,f32,f64) void;
extern fn f3_record_pair(i32,i32) void;
fn f3Pair(c: *zw.Caller,a: i32,b: i32) !i32 {
    f3_record_pair(a,b); const mem=c.memory() orelse return error.MissingMemory;
    const old=try mem.read(u8,9); try mem.write(9,@as(u8,@truncate(@as(u32,old)+@as(u32,@bitCast(b)))));
    return if(f3_get_variant()!=0) b*3-a else a*3-b;
}
fn f3Mix(c: *zw.Caller,a: i32,b: i32,d: i64,e: f32,f: f64) !i32 {
    f3_record(a,b,d,e,f); const mem=c.memory() orelse return error.MissingMemory;
    const old=try mem.read(u8,9); try mem.write(9,@as(u8,@truncate(@as(u32,old)+@as(u32,@bitCast(b)))));
    return if(f3_get_variant()!=0) b*3-a else a*3-b;
}
const F3Multi = struct { wide: i64, small: i32 };
fn f3Multi(_: *zw.Caller,a: i32,b: i32) F3Multi { f3_record_pair(a,b); return .{.wide=@as(i64,a)*8589934592+b,.small=a-b}; }
fn f3Wide(_: *zw.Caller,a: i64,b: i64) i64 { return a-b; }
fn f3Fail(_: *zw.Caller) !void { if(f3_get_variant()!=0) return error.RequestAborted; }
fn f3Emit(inst: *zw.Instance,name: []const u8,args: []const zw.Value,nr: usize) void {
    var result: [16]zw.Value=undefined;
    inst.invoke(name,args,result[0..nr]) catch |err| { _=printf("{\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))); return; };
    _=printf("{\"values\":[");
    for(result[0..nr],0..) |v,i| {
        if(i!=0) _=printf(",");
        const k:c_uint=switch(v) { .i32=>0,.i64=>1,.f32=>2,.f64=>3,else=>@panic("Non scalar result") };
        const bits:u64=switch(v) { .i32=>|x| @as(u32,@bitCast(x)),.i64=>|x| @bitCast(x),.f32=>|x| x,.f64=>|x| x,else=>unreachable };
        _=printf("{\"kind\":%u,\"bits\":%llu}",k,@as(c_ulonglong,bits));
    } _=printf("]}");
}
fn f3Calls(inst: *zw.Instance,argc: usize,argv: [*][*:0]u8) void {
    _=printf("["); var pos:usize=0; var first=true;
    while(pos<argc) {
        const name=std.mem.span(argv[pos]); const na:usize=@intCast(number(argv[pos+1])); const nr:usize=@intCast(number(argv[pos+2])); pos+=3;
        if(na>16 or nr>16 or pos+2*na>argc) @panic("Invalid adapter call"); var args:[16]zw.Value=undefined;
        for(0..na) |i| { const k=number(argv[pos]); const bits=number(argv[pos+1]); pos+=2;
            args[i]=switch(k) { 0=>.{.i32=@bitCast(@as(u32,@truncate(bits)))},1=>.{.i64=@bitCast(bits)},2=>.{.f32=@truncate(bits)},3=>.{.f64=bits},else=>@panic("Invalid input kind") }; }
        if(!first) _=printf(","); first=false; f3Emit(inst,name,args[0..na],nr);
    } _=printf("]");
}
pub export fn f03_zig(data:[*]const u8,len:usize,provider:[*]const u8,plen:usize,mode:c_int,act:[*:0]const u8,argc:c_int,argv:[*][*:0]u8) c_int {
    f3Zig(data[0..len],provider[0..plen],mode,std.mem.span(act),@intCast(argc),argv) catch |err| { _=printf("adapter error: %s",@as([*:0]const u8,@errorName(err))); return 70; }; return 0;
}
fn f3Zig(data:[]const u8,provider:[]const u8,mode:c_int,action:[]const u8,argc:usize,argv:[*][*:0]u8) !void {
    var eng=try zw.Engine.init(std.heap.c_allocator,.{}); defer eng.deinit();
    var m=try eng.compile(data); defer m.deinit();
    var pm=try eng.compile(provider); defer pm.deinit();
    var p=try pm.instantiate(.{.engine=.interp}); defer p.deinit();
    var linker=zw.Linker.init(&eng); defer linker.deinit();
    if(std.mem.eql(u8,action,"host")) {
        try linker.defineFunc("env","mix",@TypeOf(f3Mix),f3Mix);
        try linker.defineFunc("env","pair",@TypeOf(f3Pair),f3Pair);
        try linker.defineFunc("env","wide",@TypeOf(f3Wide),f3Wide);
        try linker.defineFunc("env","multi",@TypeOf(f3Multi),f3Multi);
        try linker.defineFunc("env","fail",@TypeOf(f3Fail),f3Fail);
    } else if(!std.mem.eql(u8,action,"missing")) try linker.defineInstance("env",&p);
    var inst=linker.instantiate(&m,.{.engine=if(mode==1) .jit else .interp}) catch |err| {
        _=printf("{\"created\":false,\"error\":\"%s\"",@as([*:0]const u8,@errorName(err))); return;
    }; defer inst.deinit();
    _=printf("{\"created\":true,\"calls\":"); f3Calls(&inst,argc,argv);
    if(std.mem.eql(u8,action,"state")) {
        _=printf(",\"provider_before\":"); f3Emit(&p,"read",&.{},3);
        _=printf(",\"provider_write\":"); f3Emit(&p,"write",&.{.{.i32=46},.{.i32 = -17}},0);
        _=printf(",\"consumer_after\":"); f3Emit(&inst,"read",&.{},3);
        var independent=try pm.instantiate(.{.engine=.interp}); defer independent.deinit();
        _=printf(",\"independent\":"); f3Emit(&independent,"read",&.{},3);
    }
}
'''

class F03Driver:
    def __init__(self, compiler, directory):
        self.compiler = compiler
        self.directory = directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F03')

    def run(self, guest, calls=(), *, provider='(module)', action='host', api='c', engine='interp', variant=0):
        self.serial += 1
        paths = []
        for name, source in [('guest',guest),('provider',provider)]:
            binary = self.compiler.wat(source)
            assert self.compiler.standard_valid(binary), source
            path = self.directory / f'{self.serial}-{name}.wasm'
            path.write_bytes(binary)
            paths.append(path)
        command = [self.program(),api,action,'1' if engine=='jit' else '2',str(variant),*paths]
        for name,args,nresults in calls:
            command.extend([name,str(len(args)),str(nresults)])
            for kind,bits in args:
                command.extend([str(kind),str(bits)])
        result = run_json_adapter(command,timeout=30)
        (self.directory / f'{self.serial}-observation.json').write_bytes(result.process.stdout)
        return result.value


@pytest.fixture(scope='session')
def f03_driver(f01_driver,tmp_path_factory):
    return F03Driver(f01_driver,tmp_path_factory.mktemp('f03-consumer'))


def consumer_sources():
    return {'F03': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f03_main(argc, argv);') + F03_ZIG, F02_C + F03_C, ('v3_0',))}
