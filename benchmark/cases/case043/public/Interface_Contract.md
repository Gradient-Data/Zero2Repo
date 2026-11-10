# Interface Contract

The project is a Zig path dependency named `navor`. The dependency exposes `module("navor")`, which supplies both the Zig API and public C ABI symbols, `artifact("navor")` as the CLI executable, and `path("include")` as the public header directory. Zig clients use `@import("navor")`; C clients include `wasm.h`, `navor.h`, and `wasi.h`.

Build configuration uses `-Dwasm=<level>` (`v1_0`, `v2_0`, `v3_0`), `-Dwasi=<level>` (`none`, `p1`, `p3`), `-Dengine=<mode>` (`both`, `interp`, `jit`), `-Dcompiler-rt=<bool>` (`true`, `false`), and `-Doptimize=<mode>` (`ReleaseSafe`, `ReleaseFast`). The installed command is `zig-out/bin/navor`, run with the caller's working directory.

C owning results are released through the corresponding public delete functions. Borrowed descriptors and cast views remain tied to the owning handle. A vector carries `size` and `data`; names and binaries are byte sequences with explicit lengths. Native Zig operations use error unions: failures carry a named Zig error, readable through `@errorName`.

## `wasm_byte_vec_delete`

```c
void wasm_byte_vec_delete( wasm_byte_vec_t*);
```

Releases the owning handle or vector.

## `wasm_byte_vec_new`

```c
void wasm_byte_vec_new( wasm_byte_vec_t* out, size_t, wasm_byte_t const[]);
```

Writes an owning vector with the supplied element count; data is writable element storage.

## `wasm_byte_vec_new_uninitialized`

```c
void wasm_byte_vec_new_uninitialized( wasm_byte_vec_t* out, size_t);
```

Writes an owning vector with the supplied element count; data is writable element storage.

## `wasm_engine_delete`

```c
void wasm_engine_delete( wasm_engine_t*);
```

Releases the owning handle or vector.

## `wasm_engine_new`

```c
wasm_engine_t* wasm_engine_new(void);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_exporttype_name`

```c
const wasm_name_t* wasm_exporttype_name(const wasm_exporttype_t*);
```

Returns a borrowed name byte vector.

## `wasm_exporttype_type`

```c
const wasm_externtype_t* wasm_exporttype_type(const wasm_exporttype_t*);
```

## `wasm_exporttype_vec_delete`

```c
void wasm_exporttype_vec_delete( wasm_exporttype_vec_t*);
```

Releases the owning handle or vector.

## `wasm_extern_as_func`

```c
wasm_func_t* wasm_extern_as_func(wasm_extern_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_extern_as_global`

```c
wasm_global_t* wasm_extern_as_global(wasm_extern_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_extern_as_memory`

```c
wasm_memory_t* wasm_extern_as_memory(wasm_extern_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_extern_as_table`

```c
wasm_table_t* wasm_extern_as_table(wasm_extern_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_extern_copy`

```c
wasm_extern_t* wasm_extern_copy(const wasm_extern_t*);
```

Accepts an instance-export external handle and returns a separate owning reference to that external.

## `wasm_extern_vec_delete`

```c
void wasm_extern_vec_delete( wasm_extern_vec_t*);
```

Releases the owning handle or vector.

## `wasm_extern_vec_new_uninitialized`

```c
void wasm_extern_vec_new_uninitialized( wasm_extern_vec_t* out, size_t);
```

Writes an owning vector with the supplied element count; data is writable element storage.

## `wasm_externtype_as_functype_const`

```c
const wasm_functype_t* wasm_externtype_as_functype_const(const wasm_externtype_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_externtype_as_globaltype_const`

```c
const wasm_globaltype_t* wasm_externtype_as_globaltype_const(const wasm_externtype_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_externtype_as_memorytype_const`

```c
const wasm_memorytype_t* wasm_externtype_as_memorytype_const(const wasm_externtype_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_externtype_as_tabletype_const`

```c
const wasm_tabletype_t* wasm_externtype_as_tabletype_const(const wasm_externtype_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_externtype_as_tagtype_const`

```c
const wasm_tagtype_t* wasm_externtype_as_tagtype_const(const wasm_externtype_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_externtype_kind`

```c
wasm_externkind_t wasm_externtype_kind(const wasm_externtype_t*);
```

Returns a `wasm_externkind_t` tag: `WASM_EXTERN_FUNC`, `WASM_EXTERN_GLOBAL`, `WASM_EXTERN_TABLE`, `WASM_EXTERN_MEMORY`, or `WASM_EXTERN_TAG`.

## `wasm_foreign_as_ref`

```c
wasm_ref_t* wasm_foreign_as_ref(wasm_foreign_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_foreign_delete`

```c
void wasm_foreign_delete( wasm_foreign_t*);
```

Releases the owning handle or vector.

## `wasm_foreign_new`

```c
wasm_foreign_t* wasm_foreign_new(wasm_store_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_frame_delete`

```c
void wasm_frame_delete( wasm_frame_t*);
```

Releases the owning handle or vector.

## `wasm_frame_func_index`

```c
uint32_t wasm_frame_func_index(const wasm_frame_t*);
```

Returns the frame function index.

## `wasm_frame_func_offset`

```c
size_t wasm_frame_func_offset(const wasm_frame_t*);
```

Returns the byte offset from the beginning of the encoded function body, including its local-declaration vector.

## `wasm_frame_module_offset`

```c
size_t wasm_frame_module_offset(const wasm_frame_t*);
```

Returns the byte offset within the module.

## `wasm_frame_vec_delete`

```c
void wasm_frame_vec_delete( wasm_frame_vec_t*);
```

Releases the owning handle or vector.

## `wasm_func_as_extern`

```c
wasm_extern_t* wasm_func_as_extern(wasm_func_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_func_call`

```c
wasm_trap_t* wasm_func_call( const wasm_func_t*, const wasm_val_vec_t* args, wasm_val_vec_t* results);
```

args and results are value vectors. The caller supplies writable result storage. Returns NULL on success and an owning trap pointer on failure. Successful results are written into results.

## `wasm_func_delete`

```c
void wasm_func_delete( wasm_func_t*);
```

Releases the owning handle or vector.

## `wasm_func_new`

```c
wasm_func_t* wasm_func_new( wasm_store_t*, const wasm_functype_t*, wasm_func_callback_t);
```

Returns an owning function handle. The callback receives arguments and writable results and returns NULL for success or an owning trap pointer for failure.

## `wasm_functype_delete`

```c
void wasm_functype_delete( wasm_functype_t*);
```

Releases the owning handle or vector.

## `wasm_functype_new`

```c
wasm_functype_t* wasm_functype_new( wasm_valtype_vec_t* params, wasm_valtype_vec_t* results);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_functype_params`

```c
const wasm_valtype_vec_t* wasm_functype_params(const wasm_functype_t*);
```

Returns a borrowed vector of function-signature value types.

## `wasm_functype_results`

```c
const wasm_valtype_vec_t* wasm_functype_results(const wasm_functype_t*);
```

Returns a borrowed vector of function-signature value types.

## `wasm_global_as_extern`

```c
wasm_extern_t* wasm_global_as_extern(wasm_global_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_global_delete`

```c
void wasm_global_delete( wasm_global_t*);
```

Releases the owning handle or vector.

## `wasm_global_get`

```c
void wasm_global_get(const wasm_global_t*, wasm_val_t* out);
```

Writes the current value into the supplied wasm_val_t.

## `wasm_global_new`

```c
wasm_global_t* wasm_global_new( wasm_store_t*, const wasm_globaltype_t*, const wasm_val_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_global_set`

```c
void wasm_global_set(wasm_global_t*, const wasm_val_t*);
```

## `wasm_globaltype_content`

```c
const wasm_valtype_t* wasm_globaltype_content(const wasm_globaltype_t*);
```

## `wasm_globaltype_delete`

```c
void wasm_globaltype_delete( wasm_globaltype_t*);
```

Releases the owning handle or vector.

## `wasm_globaltype_mutability`

```c
wasm_mutability_t wasm_globaltype_mutability(const wasm_globaltype_t*);
```

Returns a `wasm_mutability_t` tag: `WASM_CONST` or `WASM_VAR`.

## `wasm_globaltype_new`

```c
wasm_globaltype_t* wasm_globaltype_new( wasm_valtype_t*, wasm_mutability_t);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_importtype_module`

```c
const wasm_name_t* wasm_importtype_module(const wasm_importtype_t*);
```

Returns a borrowed name byte vector.

## `wasm_importtype_name`

```c
const wasm_name_t* wasm_importtype_name(const wasm_importtype_t*);
```

Returns a borrowed name byte vector.

## `wasm_importtype_type`

```c
const wasm_externtype_t* wasm_importtype_type(const wasm_importtype_t*);
```

## `wasm_importtype_vec_delete`

```c
void wasm_importtype_vec_delete( wasm_importtype_vec_t*);
```

Releases the owning handle or vector.

## `wasm_instance_delete`

```c
void wasm_instance_delete( wasm_instance_t*);
```

Releases the owning handle or vector.

## `wasm_instance_exports`

```c
void wasm_instance_exports(const wasm_instance_t*, wasm_extern_vec_t* out);
```

Writes an owning vector of external handles. Entries correspond by index to the non-tag declarations returned by `wasm_module_exports`; tag declarations have no external handle in this vector.

## `wasm_instance_new`

```c
wasm_instance_t* wasm_instance_new( wasm_store_t*, const wasm_module_t*, const wasm_extern_vec_t* imports, wasm_trap_t** );
```

Returns an owning instance pointer and a NULL trap on success. Failure returns NULL; the optional trap out-parameter carries an owning trap pointer or NULL for a failure without a trap.

## `wasm_memory_as_extern`

```c
wasm_extern_t* wasm_memory_as_extern(wasm_memory_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_memory_data`

```c
byte_t* wasm_memory_data(wasm_memory_t*);
```

Returns a borrowed pointer to memory bytes.

## `wasm_memory_data_size`

```c
size_t wasm_memory_data_size(const wasm_memory_t*);
```

Returns memory length in bytes.

## `wasm_memory_delete`

```c
void wasm_memory_delete( wasm_memory_t*);
```

Releases the owning handle or vector.

## `wasm_memory_grow`

```c
bool wasm_memory_grow(wasm_memory_t*, wasm_memory_pages_t delta);
```

Returns a boolean success indicator.

## `wasm_memory_new`

```c
wasm_memory_t* wasm_memory_new(wasm_store_t*, const wasm_memorytype_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_memory_size`

```c
wasm_memory_pages_t wasm_memory_size(const wasm_memory_t*);
```

Returns memory size in pages.

## `wasm_memorytype_delete`

```c
void wasm_memorytype_delete( wasm_memorytype_t*);
```

Releases the owning handle or vector.

## `wasm_memorytype_limits`

```c
const wasm_limits_t* wasm_memorytype_limits(const wasm_memorytype_t*);
```

Returns a borrowed limits descriptor.

## `wasm_memorytype_new`

```c
wasm_memorytype_t* wasm_memorytype_new(const wasm_limits_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_module_delete`

```c
void wasm_module_delete( wasm_module_t*);
```

Releases the owning handle or vector.

## `wasm_module_deserialize`

```c
wasm_module_t* wasm_module_deserialize(wasm_store_t*, const wasm_byte_vec_t*);
```

Accepts an opaque serialized byte vector and returns an owning module pointer, or NULL for failure.

## `wasm_module_exports`

```c
void wasm_module_exports(const wasm_module_t*, wasm_exporttype_vec_t* out);
```

Writes an owning vector of export declarations or handles.

## `wasm_module_imports`

```c
void wasm_module_imports(const wasm_module_t*, wasm_importtype_vec_t* out);
```

## `wasm_module_new`

```c
wasm_module_t* wasm_module_new( wasm_store_t*, const wasm_byte_vec_t* binary);
```

Returns an owning module pointer, or NULL for refusal.

## `wasm_module_obtain`

```c
wasm_module_t* wasm_module_obtain(wasm_store_t*, const wasm_shared_module_t*);
```

Returns an owning module handle in the supplied store.

## `wasm_module_serialize`

```c
void wasm_module_serialize(const wasm_module_t*, wasm_byte_vec_t* out);
```

Writes an owning byte vector containing opaque serialized module bytes.

## `wasm_module_share`

```c
wasm_shared_module_t* wasm_module_share(const wasm_module_t*);
```

Returns an owning shared-module handle.

## `wasm_module_validate`

```c
bool wasm_module_validate(wasm_store_t*, const wasm_byte_vec_t* binary);
```

Returns true for acceptance and false for refusal.

## `wasm_ref_as_func`

```c
wasm_func_t* wasm_ref_as_func(wasm_ref_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_ref_delete`

```c
void wasm_ref_delete( wasm_ref_t*);
```

Releases the owning handle or vector.

## `wasm_ref_same`

```c
bool wasm_ref_same(const wasm_ref_t*, const wasm_ref_t*);
```

Returns a boolean identity comparison.

## `wasm_shared_module_delete`

```c
void wasm_shared_module_delete( wasm_shared_module_t*);
```

Releases the owning handle or vector.

## `wasm_store_delete`

```c
void wasm_store_delete( wasm_store_t*);
```

Releases the owning handle or vector.

## `wasm_store_new`

```c
wasm_store_t* wasm_store_new(wasm_engine_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_table_as_extern`

```c
wasm_extern_t* wasm_table_as_extern(wasm_table_t*);
```

Returns a borrowed typed view, or NULL when unavailable.

## `wasm_table_delete`

```c
void wasm_table_delete( wasm_table_t*);
```

Releases the owning handle or vector.

## `wasm_table_get`

```c
wasm_ref_t* wasm_table_get(const wasm_table_t*, wasm_table_size_t index);
```

Returns an owning reference pointer or NULL.

## `wasm_table_grow`

```c
bool wasm_table_grow(wasm_table_t*, wasm_table_size_t delta, wasm_ref_t* init);
```

Returns a boolean success indicator.

## `wasm_table_new`

```c
wasm_table_t* wasm_table_new( wasm_store_t*, const wasm_tabletype_t*, wasm_ref_t* init);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_table_set`

```c
bool wasm_table_set(wasm_table_t*, wasm_table_size_t index, wasm_ref_t*);
```

Returns a boolean success indicator.

## `wasm_table_size`

```c
wasm_table_size_t wasm_table_size(const wasm_table_t*);
```

Returns the element count.

## `wasm_tabletype_delete`

```c
void wasm_tabletype_delete( wasm_tabletype_t*);
```

Releases the owning handle or vector.

## `wasm_tabletype_element`

```c
const wasm_valtype_t* wasm_tabletype_element(const wasm_tabletype_t*);
```

## `wasm_tabletype_limits`

```c
const wasm_limits_t* wasm_tabletype_limits(const wasm_tabletype_t*);
```

Returns a borrowed limits descriptor.

## `wasm_tabletype_new`

```c
wasm_tabletype_t* wasm_tabletype_new( wasm_valtype_t*, const wasm_limits_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_tagtype_functype`

```c
const wasm_functype_t* wasm_tagtype_functype(const wasm_tagtype_t*);
```

## `wasm_trap_delete`

```c
void wasm_trap_delete( wasm_trap_t*);
```

Releases the owning handle or vector.

## `wasm_trap_message`

```c
void wasm_trap_message(const wasm_trap_t*, wasm_message_t* out);
```

Writes an owning message byte vector with a trailing NUL. It contains human-readable diagnostic text.

## `wasm_trap_new`

```c
wasm_trap_t* wasm_trap_new(wasm_store_t* store, const wasm_message_t*);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_trap_origin`

```c
wasm_frame_t* wasm_trap_origin(const wasm_trap_t*);
```

Returns an owning frame pointer or NULL when no origin is available.

## `wasm_trap_trace`

```c
void wasm_trap_trace(const wasm_trap_t*, wasm_frame_vec_t* out);
```

Writes an owning vector of frame pointers.

## `wasm_val_delete`

```c
void wasm_val_delete( wasm_val_t* v);
```

Releases the owning handle or vector.

## `wasm_valtype_kind`

```c
wasm_valkind_t wasm_valtype_kind(const wasm_valtype_t*);
```

## `wasm_valtype_new`

```c
wasm_valtype_t* wasm_valtype_new(wasm_valkind_t);
```

Returns an owning handle of the declared type, or NULL for failure.

## `wasm_valtype_vec_new`

```c
void wasm_valtype_vec_new( wasm_valtype_vec_t* out, size_t, wasm_valtype_t * const[]);
```

Writes an owning vector with the supplied element count; data is writable element storage.

## `navor_engine_set_compile_hook`

```c
void navor_engine_set_compile_hook( wasm_engine_t*, navor_compile_hook_t, void* user_data);
```

The callback is nullable. user_data is an opaque pointer passed to the callback.

```c
typedef void (*navor_compile_hook_t)(void* user_data, size_t wasm_len, bool accepted);
```

## `navor_engine_set_fuel_exhausted_hook`

```c
void navor_engine_set_fuel_exhausted_hook( wasm_engine_t*, navor_fuel_exhausted_hook_t, void* user_data);
```

The callback is nullable. user_data is an opaque pointer passed to the callback.

```c
typedef void (*navor_fuel_exhausted_hook_t)(void* user_data, uint64_t instance_id);
```

## `navor_engine_set_instantiate_hook`

```c
void navor_engine_set_instantiate_hook( wasm_engine_t*, navor_instantiate_hook_t, void* user_data);
```

The callback is nullable. user_data is an opaque pointer passed to the callback.

```c
typedef void (*navor_instantiate_hook_t)(void* user_data, uint64_t instance_id);
```

## `navor_engine_set_memory_growth_hook`

```c
void navor_engine_set_memory_growth_hook( wasm_engine_t*, navor_memory_growth_hook_t, void* user_data);
```

The callback is nullable. user_data is an opaque pointer passed to the callback.

```c
typedef void (*navor_memory_growth_hook_t)(void* user_data, uint64_t instance_id, uint32_t memory_index, uint64_t old_pages, uint64_t new_pages);
```

## `navor_engine_set_trap_hook`

```c
void navor_engine_set_trap_hook( wasm_engine_t*, navor_trap_hook_t, void* user_data);
```

The callback is nullable. user_data is an opaque pointer passed to the callback.

```c
typedef void (*navor_trap_hook_t)(void* user_data, uint64_t instance_id, int32_t trap_kind, const char* message, size_t message_len);
```

## `navor_instance_disable_fuel`

```c
void navor_instance_disable_fuel(wasm_instance_t*);
```

## `navor_instance_engine`

```c
bool navor_instance_engine(const wasm_instance_t*, int32_t* out);
```

Returns a boolean availability indicator; on true, the int32_t out-parameter is jit=1 or interp=2.

## `navor_instance_new_ex`

```c
wasm_instance_t* navor_instance_new_ex( wasm_store_t*, const wasm_module_t*, const wasm_extern_vec_t*, wasm_trap_t**, uint8_t engine_kind);
```

engine_kind is a uint8_t selector: auto=0, jit=1, interp=2. Returns an owning instance pointer or NULL. The optional trap out-parameter receives an owning trap pointer or NULL.

The import vector is positional in the order returned by `wasm_module_imports`. A NULL slot denotes an unsupplied binding; an empty vector supplies no explicit bindings.

## `navor_instance_set_fuel`

```c
void navor_instance_set_fuel(wasm_instance_t*, uint64_t fuel);
```

## `navor_module_imports_ex`

```c
bool navor_module_imports_ex( const wasm_module_t*, wasm_importtype_vec_t* out);
```

Returns a success boolean and writes an owning import-type vector on success.

## `navor_store_set_wasi`

```c
void navor_store_set_wasi(wasm_store_t*, navor_wasi_config_t*);
```

Transfers configuration ownership to the store.

## `navor_store_wasi_exit_code`

```c
bool navor_store_wasi_exit_code(const wasm_store_t*, uint32_t* out);
```

Returns a boolean availability indicator and, on true, writes the uint32_t guest exit status.

## `navor_trap_kind`

```c
int32_t navor_trap_kind(const wasm_trap_t*);
```

Returns int32_t: -1 no trap; 0 binding_error; 1 unreachable; 2 div_by_zero; 3 int_overflow; 4 invalid_conversion; 5 oob_memory; 6 oob_table; 7 uninitialized_elem; 8 indirect_call_mismatch; 11 null_reference; 12 cast_failure; 13 uncaught_exception; 17 out_of_fuel; 18 wasi_exit; 19 invalid_module.

Numeric range-error failure is represented by `int_overflow` or `invalid_conversion`.

## `navor_version`

```c
const char* navor_version(void);
```

Returns a non-NULL, NUL-terminated release string.

## `navor_wasi_config_inherit_stdio`

```c
void navor_wasi_config_inherit_stdio(navor_wasi_config_t*);
```

## `navor_wasi_config_new`

```c
navor_wasi_config_t* navor_wasi_config_new(void);
```

Returns an owning handle of the declared type, or NULL for failure.

## `navor_wasi_config_preopen_dir`

```c
bool navor_wasi_config_preopen_dir( navor_wasi_config_t*, const char* host_path, const char* guest_path);
```

Both paths are NUL-terminated C strings. Returns a boolean success indicator.

## `navor_wasi_config_set_args`

```c
void navor_wasi_config_set_args( navor_wasi_config_t*, size_t argc, const char* const* argv);
```

argv is an argc-element array of NUL-terminated C strings.

## `navor_wasi_config_set_envs`

```c
void navor_wasi_config_set_envs( navor_wasi_config_t*, size_t count, const char* const* keys, const char* const* vals);
```

keys and vals are count-element arrays of NUL-terminated C strings.

## `wasm_byte_vec_t`

```c
typedef struct wasm_byte_vec_t { size_t size; char* data; } wasm_byte_vec_t;
```

size is the element count; data points to contiguous elements.

## `wasm_engine_t`

`wasm_engine_t` is an opaque C handle type, exchanged through pointers.

## `wasm_exporttype_vec_t`

```c
typedef struct wasm_exporttype_vec_t { size_t size; wasm_exporttype_t** data; } wasm_exporttype_vec_t;
```

size is the element count; data points to contiguous elements.

## `wasm_extern_t`

`wasm_extern_t` is an opaque C handle type, exchanged through pointers.

## `wasm_extern_vec_t`

```c
typedef struct wasm_extern_vec_t { size_t size; wasm_extern_t** data; } wasm_extern_vec_t;
```

size is the element count; data points to contiguous elements.

## `wasm_externtype_t`

`wasm_externtype_t` is an opaque C handle type, exchanged through pointers.

## `wasm_foreign_t`

`wasm_foreign_t` is an opaque C handle type, exchanged through pointers.

## `wasm_frame_t`

`wasm_frame_t` is an opaque C handle type, exchanged through pointers.

## `wasm_frame_vec_t`

```c
typedef struct wasm_frame_vec_t { size_t size; wasm_frame_t** data; } wasm_frame_vec_t;
```

size is the element count; data points to contiguous elements.

## `wasm_func_callback_t`

```c
typedef wasm_trap_t* (*wasm_func_callback_t)(const wasm_val_vec_t* args, wasm_val_vec_t* results);
```

The callback returns NULL on success or an owning trap pointer on failure.

## `wasm_func_t`

`wasm_func_t` is an opaque C handle type, exchanged through pointers.

## `wasm_functype_t`

`wasm_functype_t` is an opaque C handle type, exchanged through pointers.

## `wasm_global_t`

`wasm_global_t` is an opaque C handle type, exchanged through pointers.

## `wasm_globaltype_t`

`wasm_globaltype_t` is an opaque C handle type, exchanged through pointers.

## `wasm_importtype_vec_t`

```c
typedef struct wasm_importtype_vec_t { size_t size; wasm_importtype_t** data; } wasm_importtype_vec_t;
```

size is the element count; data points to contiguous elements.

## `wasm_instance_t`

`wasm_instance_t` is an opaque C handle type, exchanged through pointers.

## `wasm_limits_t`

```c
typedef struct wasm_limits_t { uint32_t min; uint32_t max; } wasm_limits_t;
```

min and max are declared bounds; max = 0xffffffff denotes an absent maximum.

## `wasm_memory_t`

`wasm_memory_t` is an opaque C handle type, exchanged through pointers.

## `wasm_memorytype_t`

`wasm_memorytype_t` is an opaque C handle type, exchanged through pointers.

## `wasm_message_t`

`wasm_message_t` is a wasm_byte_vec_t with byte count `size` and byte pointer `data`. Diagnostic bytes include a trailing NUL.

## `wasm_module_t`

`wasm_module_t` is an opaque C handle type, exchanged through pointers.

## `wasm_name_t`

`wasm_name_t` is a wasm_byte_vec_t with byte count `size` and byte pointer `data`.

## `wasm_ref_t`

`wasm_ref_t` is an opaque C handle type, exchanged through pointers.

## `wasm_shared_module_t`

`wasm_shared_module_t` is an opaque C handle type, exchanged through pointers.

## `wasm_store_t`

`wasm_store_t` is an opaque C handle type, exchanged through pointers.

## `wasm_table_t`

`wasm_table_t` is an opaque C handle type, exchanged through pointers.

## `wasm_tabletype_t`

`wasm_tabletype_t` is an opaque C handle type, exchanged through pointers.

## `wasm_trap_t`

`wasm_trap_t` is an opaque C handle type, exchanged through pointers.

## `wasm_val_t`

```c
typedef struct wasm_val_t { wasm_valkind_t kind; union { int32_t i32; int64_t i64; float f32; double f64; wasm_ref_t* ref; } of; } wasm_val_t;
```

kind identifies the active scalar or reference payload.

## `wasm_val_vec_t`

```c
typedef struct wasm_val_vec_t { size_t size; wasm_val_t* data; } wasm_val_vec_t;
```

size is the element count; data points to contiguous elements.

## `wasm_valkind_t`

`wasm_valkind_t` is `uint8_t`. Its named tags are `WASM_I32`, `WASM_I64`, `WASM_F32`, `WASM_F64`, `WASM_EXTERNREF`, and `WASM_FUNCREF`. The v128 boundary tag is `4`.

## `wasm_valtype_t`

`wasm_valtype_t` is an opaque C handle type, exchanged through pointers.

## `wasm_valtype_vec_t`

```c
typedef struct wasm_valtype_vec_t { size_t size; wasm_valtype_t** data; } wasm_valtype_vec_t;
```

size is the element count; data points to contiguous elements.

## `navor_wasi_config_t`

`navor_wasi_config_t` is an opaque C handle type, exchanged through pointers.

## `WASM_EXTERNREF`

`WASM_EXTERNREF` is the C wasm_valkind_t tag `128` for a external reference.

## `navor.Engine`

Public type `navor.Engine`:
```zig
init(alloc: std.mem.Allocator, opts: InitOpts) InitError!Engine
deinit(self: *Engine) void
compile(self: *Engine, bytes: []const u8) CompileError!Module
setCompileHook(self: *Engine, hook: ?CompileFn, user_data: ?*anyopaque) void
setInstantiateHook(self: *Engine, hook: ?InstantiateFn, user_data: ?*anyopaque) void
setTrapHook(self: *Engine, hook: ?TrapFn, user_data: ?*anyopaque) void
setFuelExhaustedHook(self: *Engine, hook: ?FuelExhaustedFn, user_data: ?*anyopaque) void
setMemoryGrowthHook(self: *Engine, hook: ?MemoryGrowthFn, user_data: ?*anyopaque) void
```
`InitOpts` accepts `.{}`. `CompileError` includes `ParseFailed`, `ValidateFailed`.

Callbacks use `callconv(.c)` and return void. Their arguments after the optional opaque user pointer are: compile `(usize, bool)` for input byte count and acceptance; instantiate `(u64)` for instance identity; trap `(u64, i32, ?[*]const u8, usize)` for instance identity, category, message pointer and message byte length; fuel-exhausted `(u64)` for instance identity; memory-growth `(u64, u32, u64, u64)` for instance identity, memory index, old page count and new page count. Message bytes are human-readable diagnostic text.

## `navor.Value`

`navor.Value` is a tagged union:
```zig
union(enum) {
    i32: i32, i64: i64, f32: u32, f64: u64, v128: u128,
    funcref: ?u64, externref: ?u64,
}
```
The floating-point payloads carry IEEE-754 bits. Reference payloads are optional opaque reference values.

## `navor.Module`

Public type `navor.Module`:
```zig
deinit(self: *Module) void
instantiate(self: *Module, opts: InstantiateOpts) InstantiateError!Instance
imports(self: *const Module, alloc: std.mem.Allocator) IntrospectError!ModuleImports
exports(self: *const Module, alloc: std.mem.Allocator) IntrospectError!ModuleExports
```
`InstantiateError` includes `InstantiateFailed`, `StartTrapped`, `MemoryLimitExceeded`, `TableLimitExceeded`.

## `navor.Module.Budget`

`navor.Module.Budget` is `union(enum) { unmetered, limited: u64 }`. The limited payload is the caller-supplied allowance.

## `navor.Module.InstantiateOpts`

`navor.Module.InstantiateOpts` accepts `.{}` and named fields:
```zig
fuel: Budget,
max_memory_pages: Budget,
max_table_elements: Budget,
engine: enum { auto, jit, interp },
```
The budget payloads use fuel units, memory pages, and table elements respectively.

## `navor.ExternKind`

`navor.ExternKind` is `enum { func, table, memory, global, tag }`.

## `navor.ImportItem`

`navor.ImportItem` has fields `module: []const u8`, `name: []const u8`, `kind: ExternKind`. The byte slices carry the import namespace and member name.

## `navor.ExportItem`

`navor.ExportItem` has fields `name: []const u8`, `kind: ExternKind`.

## `navor.ModuleImports`

`navor.ModuleImports` has `items: []const ImportItem` and `deinit(self: *ModuleImports) void`.

## `navor.ModuleExports`

`navor.ModuleExports` has `items: []const ExportItem` and `deinit(self: *ModuleExports) void`.

## `navor.Instance`

Public type `navor.Instance`:
```zig
deinit(self: *Instance) void
invoke(self: *Instance, name: []const u8, args: []const Value, results: []Value) InvokeError!void
memory(self: *Instance) ?Memory
global(self: *Instance, name: []const u8) ?Global
table(self: *Instance, name: []const u8) ?Table
setFuel(self: *Instance, fuel: ?u64) void
fuelRemaining(self: *Instance) ?u64
setMemoryPagesLimit(self: *Instance, limit: ?u64) void
setTableElementsLimit(self: *Instance, limit: ?u64) void
interrupt(self: *Instance) void
clearInterrupt(self: *Instance) void
wasiExitCode(self: *const Instance) ?u32
```
The caller supplies result storage. Optional accessors carry an available value or null. `wasiExitCode` carries a recorded guest status. `InvokeError` carries named errors including `ExportNotFound`, `NotAFunc`, `ArgArityMismatch`, `ResultArityMismatch`, `ProcExit`, `HostTrap`, `UnsupportedEngineSignature`, and runtime trap categories `Unreachable`, `DivByZero`, `OutOfBoundsLoad`, `Interrupted`, `OutOfFuel`.
`ExportNotFound` and `NotAFunc` are the two accepted export-binding failure forms.

## `navor.Memory`

Public type `navor.Memory`:
```zig
size(self: Memory) u32
read(self: Memory, comptime T: type, addr: u32) Error!T
write(self: Memory, addr: u32, val: anytype) Error!void
sliceAt(self: Memory, offset: u32, len: u32) Error![]u8
grow(self: Memory, delta: u32) ?u32
```
size and delta use pages; grow returns an optional previous page count. Addresses, offsets, and lengths use bytes. sliceAt returns a writable byte slice. The errors are `OutOfBoundsLoad` and `OutOfBoundsStore`.

## `navor.Global`

Public type `navor.Global`:
```zig
get(self: Global) Value
set(self: Global, val: Value) error{Immutable}!void
```

## `navor.Table`

Public type `navor.Table`:
```zig
size(self: Table) u32
get(self: Table, idx: u32) Error!Value
set(self: Table, idx: u32, val: Value) Error!void
grow(self: Table, delta: u32, init: Value) Error!void
```
size and delta use elements. Error categories are `OutOfBounds` and `GrowFailed`.

## `navor.Linker`

Public type `navor.Linker`:
```zig
init(engine: *Engine) Linker
deinit(self: *Linker) void
defineFunc(self: *Linker, module: []const u8, name: []const u8, comptime Sig: type, user_fn: *const Sig) !void
defineInstance(self: *Linker, namespace: []const u8, source: *Instance) !void
defineWasi(self: *Linker, config: WasiConfig) !void
instantiate(self: *Linker, mod: *Module, opts: Module.InstantiateOpts) LinkError!Instance
```
Typed callbacks take `*Caller` first and then typed scalar arguments. Their return form is void, a scalar, an ordered result struct, or an error union of those forms.

`LinkError` includes `UnknownImport`, `ImportKindMismatch`, `SignatureMismatch`, `InstantiateFailed`.

The error names denote an unresolved binding (`UnknownImport`), external-kind disagreement (`ImportKindMismatch`), function or global type disagreement (`SignatureMismatch`), or an instance-construction refusal including memory/table compatibility (`InstantiateFailed`).

## `navor.Linker.WasiConfig`

`WasiConfig` accepts `args: []const []const u8`, `envs: []const Env`, `preopens: []const Preopen`, `io: ?std.Io`. `Env` has `name: []const u8` and `value: []const u8`; `Preopen` has `host_path: []const u8` and `guest_path: []const u8`.

## `navor.Caller`

`navor.Caller` exposes `memory(self: Caller) ?Memory`, returning an optional guest-memory view.

## `navor.diagnostic`

The module `navor.diagnostic` exposes `clearDiag() void` and `lastDiagnostic() ?*const Info`. An available diagnostic provides `message(self: *const Info) []const u8`, a human-readable byte string.

## `navor.wasi.host.Host`

Public type `navor.wasi.host.Host`:
```zig
init(alloc: std.mem.Allocator) !Host
deinit(self: *Host) void
setArgs(self: *Host, args: []const []const u8) !void
setEnvs(self: *Host, keys: []const []const u8, vals: []const []const u8) !void
addPendingPreopen(self: *Host, host_path: []const u8, guest_path: []const u8) !void
materializePendingPreopens(self: *Host) !void
```
Assignable fields are `io: ?std.Io`, `stdin_bytes: ?[]const u8`, `stdout_buffer: ?*std.ArrayList(u8)`, and `stderr_buffer: ?*std.ArrayList(u8)`. The output buffers contain raw guest bytes on their respective channels. `exit_code: ?u32` carries an optional guest termination status.

For completed component commands, `null` and `0` are successful status forms; `1` represents an unsuccessful command outcome.

## `navor.feature.component.host.runWasiP2Main`

```zig
runWasiP2Main(engine: *Engine, alloc: std.mem.Allocator, bytes: []const u8, host: *Host, opts: Module.InstantiateOpts) anyerror!void
```

Available through `navor.feature.component.host`. Completion returns void; failure carries a named Zig error. Guest output and termination status are exposed through the supplied Host.

The operation-failure names read at this entry are `OutOfBoundsLoad`, `Unreachable`, and `TypeMismatch`. `Unreachable` and `TypeMismatch` are accepted runtime-trap and resource-type failure forms respectively.

## `navor.feature.component.host.runWasiP3Main`

```zig
runWasiP3Main(engine: *Engine, alloc: std.mem.Allocator, bytes: []const u8, host: *Host, opts: Module.InstantiateOpts) anyerror!void
```

Available through `navor.feature.component.host`. Completion returns void; failure carries a named Zig error. Guest output and termination status are exposed through the supplied Host.

Failure names include `Unreachable` for a guest trap and `NoAsyncCallback` for an unsupported async entry form.

## `navor.feature.component.host.open`

```zig
open(engine: *Engine, alloc: std.mem.Allocator, bytes: []const u8, host: *Host, opts: Module.InstantiateOpts) anyerror!Opened
```

Available through `navor.feature.component.host`. The component input is a byte slice. Success returns an owning Opened handle; failure carries a named Zig error, including `NotAComponent`, `InvalidTypeIndex`, or `InvalidName`.

## `navor.feature.component.host.Opened`

Public component handle `Opened`:
```zig
deinit(self: *Opened) void
exportedFuncs(self: *const Opened, alloc: std.mem.Allocator) std.mem.Allocator.Error![]TypeInfo.ExportedFunc
resolveFuncSig(self: *const Opened, arena: std.mem.Allocator, name: []const u8) !?FuncSig
invokeTyped(self: *Opened, name: []const u8, args: []const ComponentValue, out_alloc: std.mem.Allocator) !?ComponentValue
dropResource(self: *Opened, handle: u32) !void
```
Export names are byte strings: a top-level name or `<interface>#<function>`. Signature lookup and typed invocation return optional values. Returned value trees are owned by the caller and use the supplied output allocator; textual type labels remain tied to the opened component. Invocation failures carry named errors including `ExportNotResolved`, `ArgArityMismatch`, `ValueShapeMismatch`, `UnsupportedEncoding`, `UnsupportedType`, `ValueTypeMismatch`, and runtime trap errors. Resource-drop failure carries `InvalidHandle` or `NoResourceTable`.

Typed resource-argument refusal carries `ValueTypeMismatch` or `Unreachable`.

## `navor.feature.component.host.ComponentValue`

`ComponentValue` is a tagged union with these payloads:
```zig
bool: bool, s8: i8, u8: u8, s16: i16, u16: u16,
s32: i32, u32: u32, s64: i64, u64: u64,
f32: f32, f64: f64, char: u21, string: []const u8,
list: []ComponentValue, tuple: []ComponentValue,
record: []Field, variant: Variant, @"enum": Enum,
option: ?*ComponentValue, result: Result, flags: Flags,
own: u32, borrow: u32,
```
`Field` has `name: []const u8`, `value: ComponentValue`. `Variant` has `case: u32`, `case_name: []const u8`, `payload: ?*ComponentValue`. `Enum` has `index: u32`, `label: []const u8`. `Result` has `is_ok: bool`, `payload: ?*ComponentValue`. `Flags` has `bits: u32`, `labels: []const []const u8`. Strings carry UTF-8 bytes; resource values carry opaque handles. `deinit(self: ComponentValue, alloc: std.mem.Allocator) void` releases a returned value tree.
Host input values initialize the listed fields, including the labels of variants, enums, and flags.

## `navor.feature.component.host.WitType`

`WitType` is a tagged union:
```zig
prim: PrimValType, list: *const WitType, record: []const Field,
tuple: []const WitType, variant: []const Case,
enum_: []const []const u8, flags: []const []const u8,
option: *const WitType,
result: struct { ok: ?*const WitType, err: ?*const WitType },
own: u32, borrow: u32,
```
`Field` has `name: []const u8`, `ty: WitType`. `Case` has `name: []const u8`, `payload: ?*const WitType`. Primitive tags are `bool`, `s8`, `u8`, `s16`, `u16`, `s32`, `u32`, `s64`, `u64`, `f32`, `f64`, `char`, `string`. Text slices carry type-member labels; own and borrow carry resource type indices.

## `navor.feature.component.host.FuncSig`

`FuncSig` has `params: []const Param` and `result: ?WitType`. Each `Param` has `name: []const u8` and `ty: WitType`.

## `navor.feature.component.types.TypeInfo`

`TypeInfo.ExportedFunc` exposes `name: []const u8`. `TypeInfo.freeExportedFuncs(alloc: std.mem.Allocator, funcs: []ExportedFunc) void` releases an exported-function list.

## `navor.feature.component.host.instantiateGraph`

```zig
instantiateGraph(engine: *Engine, alloc: std.mem.Allocator, bytes: []const u8, opts: Module.InstantiateOpts) !ComponentGraph
```

Available through `navor.feature.component.host`; the input is a component byte slice. Returns an owning graph handle or a named Zig error. Graph construction or invocation can report `ImportUnsatisfied`, `UnsupportedBoundaryType`, or `OutOfBoundsLoad`.

The guest core allocation export is `cabi_realloc: (param i32 i32 i32 i32) (result i32)`. Its arguments are the previous pointer, previous byte length, alignment, and requested new byte length; its result is a guest-memory pointer.

## `navor.feature.component.host.ComponentGraph`

`ComponentGraph` exposes:
```zig
deinit(self: *ComponentGraph) void
invokeFlat(self: *ComponentGraph, name: []const u8, args: []const Value, results: []Value) !void
driveAsyncMain(self: *ComponentGraph, name: []const u8) !void
```
The caller supplies writable results. Failures are named Zig errors. Async driving exposes `AsyncDeadlock`, `NoAsyncCallback`, `Unreachable`, `ImportUnsatisfied`, `UnsupportedBoundaryType`, and `OutOfBoundsLoad`.

## `navor`

Command forms:
```text
navor
navor --version
```
`--version` writes this single LF-terminated line to stdout:
```text
navor v<release> (wasm: <wasm-level>, wasi: <wasi-level>, engine: <engine-mode>, mode: <build-mode>)
```
With no arguments stdout contains:
```text
navor v<release>
  wasm-level: <wasm-level>, wasi-level: <wasi-level>, engine: <engine-mode>
```
The placeholders carry the release string and the selected build identifiers. Both forms exit 0 with empty stderr. Usage failure exits 2 with a diagnostic on stderr.

## `navor.run`

```text
navor run [--engine <mode>] [--invoke <name>[=<arguments>]]
          [--env <KEY=VALUE>] [--dir <host>:<guest>]
          [--fuel <unsigned>] [--timeout <milliseconds>]
          [--max-memory <bytes>] [--max-table-elements <unsigned>]
          <file> [guest-arguments...]
```
`--engine` uses `auto`, `interp`, or `jit`. `--invoke` takes an export name, optionally followed in the same argument by `=` and comma-separated scalar values. `--env` and `--dir` take one mapping per occurrence. Numeric limit arguments use unsigned decimal text. The file argument names the input binary or compiled artifact; guest arguments follow it. The automatic-entry names are `_start` and `main`. Scalar argument tokens use signed or unsigned decimal integer text, or decimal/scientific floating-point text.

Scalar results go to stdout, one bare value per LF-terminated line: signed decimal integers or decimal/scientific floating-point numbers. Guest stdout and stderr remain separate raw byte channels, and stdin supplies guest input bytes. Diagnostics go to stderr. A trap diagnostic has the line form `navor: trap kind=<category>` with optional ` msg=<human-readable text>`. Categories read through this form include `unreachable_`, `out_of_fuel`, and `interrupted`.

Exit statuses: 0 successful completion; 1 load, I/O, or execution failure; 2 usage or unsupported-configuration failure. A guest-requested process status is returned as the process exit status. A refusal before producing results has empty stdout and a diagnostic on stderr.

## `navor.compile`

```text
navor compile <source> -o <destination>
```
The source and destination are caller-supplied paths. Success exits 0. Failure exits 1 and writes a diagnostic to stderr. Usage failure exits 2. The artifact can be supplied as the file argument to `navor run`.

## `navor.cli.run.runWasmCapturedFull`

Available as `navor.cli.run.runWasmCapturedFull`:
```zig
runWasmCapturedFull(alloc: std.mem.Allocator, io: std.Io,
    bytes: []const u8, argv: []const []const u8,
    stdout_capture: ?*std.ArrayList(u8), stderr_capture: ?*std.ArrayList(u8),
    stdin: StdinSource, invoke_name: ?[]const u8,
    preopens: []const PreopenDir, env_keys: []const []const u8,
    env_vals: []const []const u8, invoke_args: ?[]const u8,
    limits: Limits) !u8
```
Returns a guest status byte or a named Zig error. Supplied output arrays receive raw stdout and stderr bytes. `PreopenDir` contains `host_path: []const u8` and `guest_path: []const u8`. `StdinSource` accepts `.bytes: []const u8` and `.none`. `Limits` accepts `.{}` and fields `fuel: ?u64`, `max_memory_bytes: ?u64`, `max_table_elements: ?u64`, `timeout_ms: ?u64`, `max_output_bytes: ?u64`, `engine` with tags `auto`, `interp`, `jit`. The limit fields carry fuel units, bytes, elements, milliseconds, and captured bytes respectively.

## `cwasm`

A compiled artifact has a 136-byte header: four ASCII bytes `CWAS`, followed by 33 little-endian unsigned 32-bit words in this order:
```text
version, arch, flags, n_funcs, n_types, n_imports, code_offset, code_size, metadata_offset, metadata_size, types_offset, types_size, relocs_offset, relocs_size, exports_offset, exports_size, globals_offset, globals_size, memory_min_pages, memory_max_pages, memory_init_offset, memory_init_size, table0_size, elem_offset, elem_size, imports_offset, imports_size, wasm_bytes_offset, wasm_bytes_size, func_extras_offset, func_extras_size, eh_offset, eh_size
```
`version` is `0x00050000`; `arch` is `1` for arm64 or `2` for x86_64. Each `*_offset` and corresponding `*_size` pair describes a file-relative byte range. The payload bytes are opaque.

## `wasi_snapshot_preview1.fd_prestat_get`

Imported from `wasi_snapshot_preview1`:
```text
fd_prestat_get(fd: i32, prestat_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_prestat_dir_name`

Imported from `wasi_snapshot_preview1`:
```text
fd_prestat_dir_name(fd: i32, name_out: i32, name_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_open`

Imported from `wasi_snapshot_preview1`:
```text
path_open(fd: i32, lookup_flags: i32, path_ptr: i32, path_len: i32, open_flags: i32, rights_base: i64, rights_inheriting: i64, fd_flags: i32, fd_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_read`

Imported from `wasi_snapshot_preview1`:
```text
fd_read(fd: i32, iovecs_ptr: i32, iovecs_len: i32, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_write`

Imported from `wasi_snapshot_preview1`:
```text
fd_write(fd: i32, iovecs_ptr: i32, iovecs_len: i32, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_pread`

Imported from `wasi_snapshot_preview1`:
```text
fd_pread(fd: i32, iovecs_ptr: i32, iovecs_len: i32, offset: i64, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_pwrite`

Imported from `wasi_snapshot_preview1`:
```text
fd_pwrite(fd: i32, iovecs_ptr: i32, iovecs_len: i32, offset: i64, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_seek`

Imported from `wasi_snapshot_preview1`:
```text
fd_seek(fd: i32, offset: i64, whence: i32, offset_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_tell`

Imported from `wasi_snapshot_preview1`:
```text
fd_tell(fd: i32, offset_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_close`

Imported from `wasi_snapshot_preview1`:
```text
fd_close(fd: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_sync`

Imported from `wasi_snapshot_preview1`:
```text
fd_sync(fd: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_datasync`

Imported from `wasi_snapshot_preview1`:
```text
fd_datasync(fd: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_filestat_get`

Imported from `wasi_snapshot_preview1`:
```text
fd_filestat_get(fd: i32, stat_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_filestat_set_size`

Imported from `wasi_snapshot_preview1`:
```text
fd_filestat_set_size(fd: i32, size: i64) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_fdstat_get`

Imported from `wasi_snapshot_preview1`:
```text
fd_fdstat_get(fd: i32, fdstat_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_fdstat_set_rights`

Imported from `wasi_snapshot_preview1`:
```text
fd_fdstat_set_rights(fd: i32, rights_base: i64, rights_inheriting: i64) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_filestat_set_times`

Imported from `wasi_snapshot_preview1`:
```text
fd_filestat_set_times(fd: i32, atime: i64, mtime: i64, flags: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_filestat_set_times`

Imported from `wasi_snapshot_preview1`:
```text
path_filestat_set_times(fd: i32, lookup_flags: i32, path_ptr: i32, path_len: i32, atime: i64, mtime: i64, flags: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_filestat_get`

Imported from `wasi_snapshot_preview1`:
```text
path_filestat_get(fd: i32, lookup_flags: i32, path_ptr: i32, path_len: i32, stat_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_create_directory`

Imported from `wasi_snapshot_preview1`:
```text
path_create_directory(fd: i32, path_ptr: i32, path_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_remove_directory`

Imported from `wasi_snapshot_preview1`:
```text
path_remove_directory(fd: i32, path_ptr: i32, path_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_unlink_file`

Imported from `wasi_snapshot_preview1`:
```text
path_unlink_file(fd: i32, path_ptr: i32, path_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_rename`

Imported from `wasi_snapshot_preview1`:
```text
path_rename(old_fd: i32, old_ptr: i32, old_len: i32, new_fd: i32, new_ptr: i32, new_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_link`

Imported from `wasi_snapshot_preview1`:
```text
path_link(old_fd: i32, lookup_flags: i32, old_ptr: i32, old_len: i32, new_fd: i32, new_ptr: i32, new_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_symlink`

Imported from `wasi_snapshot_preview1`:
```text
path_symlink(old_ptr: i32, old_len: i32, fd: i32, new_ptr: i32, new_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.path_readlink`

Imported from `wasi_snapshot_preview1`:
```text
path_readlink(fd: i32, path_ptr: i32, path_len: i32, buffer_ptr: i32, buffer_len: i32, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.fd_readdir`

Imported from `wasi_snapshot_preview1`:
```text
fd_readdir(fd: i32, buffer_ptr: i32, buffer_len: i32, cookie: i64, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.clock_time_get`

Imported from `wasi_snapshot_preview1`:
```text
clock_time_get(clock_id: i32, precision: i64, time_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

A failure indicating an unavailable clock or host service returns either `nosys` or `notsup`.

## `wasi_snapshot_preview1.clock_res_get`

Imported from `wasi_snapshot_preview1`:
```text
clock_res_get(clock_id: i32, resolution_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

A failure indicating an unavailable clock or host service returns either `nosys` or `notsup`.

## `wasi_snapshot_preview1.random_get`

Imported from `wasi_snapshot_preview1`:
```text
random_get(buffer_ptr: i32, buffer_len: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.poll_oneoff`

Imported from `wasi_snapshot_preview1`:
```text
poll_oneoff(subscriptions_ptr: i32, events_out: i32, count: i32, count_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

A descriptor-subscription error can appear as the call return errno, or in a returned event while the call return is zero.

## `wasi_snapshot_preview1.args_sizes_get`

Imported from `wasi_snapshot_preview1`:
```text
args_sizes_get(argc_out: i32, argv_bytes_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.args_get`

Imported from `wasi_snapshot_preview1`:
```text
args_get(argv_out: i32, argv_bytes_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.environ_sizes_get`

Imported from `wasi_snapshot_preview1`:
```text
environ_sizes_get(count_out: i32, bytes_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.environ_get`

Imported from `wasi_snapshot_preview1`:
```text
environ_get(environ_out: i32, environ_bytes_out: i32) -> i32
```

The return i32 carries a WASI errno; output pointers address guest linear memory.

## `wasi_snapshot_preview1.proc_exit`

Imported from `wasi_snapshot_preview1`:
```text
proc_exit(status: i32) -> no result
```

status carries the guest termination status.

## `wasi_snapshot_preview1`

Guest imports use the module name `wasi_snapshot_preview1`. All guest-memory numeric fields are little-endian. Pointers, counts, and descriptors are u32; file offsets, lengths and rights are u64. Errno is returned in i32 with u16 error codes. Standard descriptors are stdin=0, stdout=1, stderr=2.

Before guest code changes descriptor state, preopened directories are addressed by a contiguous range of guest descriptors starting at 3. The first descriptor beyond that range has no preopen record; `fd_prestat_get` reports `badf` for that absence.

The exchanged memory records are:

- Argument and environment size outputs: u32 counts and byte lengths. Pointer arrays contain u32 addresses of NUL-terminated byte strings.
- I/O vectors: 8 bytes each, `buf: u32` at offset 0 and `buf_len: u32` at 4; transferred-byte counts are u32.
- Prestat: 8 bytes, directory tag u8=0 at 0 and name length u32 at 4; directory names are raw bytes.
- File stat: 64 bytes, file type u8 at 16, hard-link count u64 at 24, size u64 at 32, access/modification/change timestamps u64 at 40/48/56.
- Descriptor stat: 24 bytes, file type u8 at 0, flags u16 at 2, base and inheriting rights u64 at 8/16.
- Directory entries: 24-byte header with next cookie u64 at 0, inode u64 at 8, name length u32 at 16 and file type u8 at 20, followed by that many name bytes. The returned buffer-use count is u32.
- Seek/tell output: u64 byte offset. Clock time/resolution output: u64 nanoseconds. Random output: raw bytes.
- Poll subscriptions: 48 bytes each, userdata u64 at 0 and event type u8 at 8; clock payload has clock id u32 at 16, timeout u64 at 24, precision u64 at 32 and flags u16 at 40; descriptor payload has fd u32 at 16.
- Poll events: 32 bytes each, userdata u64 at 0, errno u16 at 8, type u8 at 10 and descriptor byte count u64 at 16. Event count output is u32. Event types: clock=0, fd_read=1, fd_write=2.

Errno codes exposed here are success=0, acces=2, again=6, badf=8, exist=20, fault=21, inval=28, io=29, isdir=31, loop=32, noent=44, nospc=51, nosys=52, notdir=54, notempty=55, notsup=58, perm=63, spipe=70, notcapable=76. File types use directory=3, regular_file=4, symbolic_link=7. Seek origins use set=0, cur=1, end=2. Clock ids use realtime=0, monotonic=1, process CPU=2 and thread CPU=3. The `nosys` errno denotes an unavailable host service. Open flags use create=1, directory=2, exclusive=4, truncate=8; append descriptor flag is 1. Timestamp-setting flags use atime=1, atime-now=2, mtime=4, mtime-now=8. Lookup symlink-follow flag and poll absolute-time flag are both 1 in their respective fields.

Rights are u64 bitsets. Bit positions are fd_datasync=0, fd_read=1, fd_seek=2, fd_sync=4, fd_tell=5, fd_write=6, path_create_directory=9, path_create_file=10, path_link_source=11, path_link_target=12, path_open=13, fd_readdir=14, path_readlink=15, path_rename_source=16, path_rename_target=17, path_filestat_get=18, path_filestat_set_size=19, path_filestat_set_times=20, fd_filestat_get=21, fd_filestat_set_size=22, fd_filestat_set_times=23, path_symlink=24, path_remove_directory=25, path_unlink_file=26, and poll_fd_readwrite=27.

## `wasi:io/poll@0.2.0`

Component import interface `wasi:io/poll@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
pollable = resource
poll: func(in: list<borrow<pollable>>) -> list<u32>
[method]pollable.ready: func(self: borrow<pollable>) -> bool
[method]pollable.block: func(self: borrow<pollable>) -> unit
```

## `wasi:io/error@0.2.0`

Component import interface `wasi:io/error@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
error = resource
```

## `wasi:io/streams@0.2.0`

Component import interface `wasi:io/streams@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
output-stream = resource
input-stream = resource
error = type error from wasi:io/error@0.2.0
stream-error = variant { last-operation-failed(own<error>), closed }
pollable = type pollable from wasi:io/poll@0.2.0
[method]output-stream.blocking-write-and-flush: func(self: borrow<output-stream>, contents: list<u8>) -> result<unit, stream-error>
[method]input-stream.blocking-read: func(self: borrow<input-stream>, len: u64) -> result<list<u8>, stream-error>
[method]input-stream.subscribe: func(self: borrow<input-stream>) -> own<pollable>
[method]output-stream.subscribe: func(self: borrow<output-stream>) -> own<pollable>
```

## `wasi:cli/stdout@0.2.0`

Component import interface `wasi:cli/stdout@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
output-stream = type output-stream from wasi:io/streams@0.2.0
get-stdout: func() -> own<output-stream>
```

## `wasi:cli/stderr@0.2.0`

Component import interface `wasi:cli/stderr@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
output-stream = type output-stream from wasi:io/streams@0.2.0
get-stderr: func() -> own<output-stream>
```

## `wasi:cli/stdin@0.2.0`

Component import interface `wasi:cli/stdin@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
input-stream = type input-stream from wasi:io/streams@0.2.0
get-stdin: func() -> own<input-stream>
```

## `wasi:filesystem/types@0.2.0`

Component import interface `wasi:filesystem/types@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
descriptor = resource
directory-entry-stream = resource
path-flags = flags { symlink-follow }
open-flags = flags { create, directory, exclusive, truncate }
descriptor-flags = flags { read, write, file-integrity-sync, data-integrity-sync, requested-write-sync, mutate-directory }
error-code = enum { access, would-block, already, bad-descriptor, busy, deadlock, quota, exist, file-too-large, illegal-byte-sequence, in-progress, interrupted, invalid, io, is-directory, loop, too-many-links, message-size, name-too-long, no-device, no-entry, no-lock, insufficient-memory, insufficient-space, not-directory, not-empty, not-recoverable, unsupported, no-tty, no-such-device, overflow, not-permitted, pipe, read-only, invalid-seek, text-file-busy, cross-device }
descriptor-type = enum { unknown, block-device, character-device, directory, fifo, symbolic-link, regular-file, socket }
datetime = record { seconds: u64, nanoseconds: u32 }
new-timestamp = variant { no-change, now, timestamp(datetime) }
descriptor-stat = record { type: descriptor-type, link-count: u64, size: u64, data-access-timestamp: option<datetime>, data-modification-timestamp: option<datetime>, status-change-timestamp: option<datetime> }
metadata-hash-value = record { lower: u64, upper: u64 }
directory-entry = record { type: descriptor-type, name: string }
[method]descriptor.open-at: func(self: borrow<descriptor>, path-flags: path-flags, path: string, open-flags: open-flags, flags: descriptor-flags) -> result<own<descriptor>, error-code>
[method]descriptor.read: func(self: borrow<descriptor>, length: u64, offset: u64) -> result<tuple<list<u8>, bool>, error-code>
[method]descriptor.write: func(self: borrow<descriptor>, buffer: list<u8>, offset: u64) -> result<u64, error-code>
[method]descriptor.stat: func(self: borrow<descriptor>) -> result<descriptor-stat, error-code>
[method]descriptor.stat-at: func(self: borrow<descriptor>, path-flags: path-flags, path: string) -> result<descriptor-stat, error-code>
[method]descriptor.metadata-hash: func(self: borrow<descriptor>) -> result<metadata-hash-value, error-code>
[method]descriptor.metadata-hash-at: func(self: borrow<descriptor>, path-flags: path-flags, path: string) -> result<metadata-hash-value, error-code>
[method]descriptor.get-type: func(self: borrow<descriptor>) -> result<descriptor-type, error-code>
[method]descriptor.read-directory: func(self: borrow<descriptor>) -> result<own<directory-entry-stream>, error-code>
[method]directory-entry-stream.read-directory-entry: func(self: borrow<directory-entry-stream>) -> result<option<directory-entry>, error-code>
[method]descriptor.readlink-at: func(self: borrow<descriptor>, path: string) -> result<string, error-code>
[method]descriptor.sync: func(self: borrow<descriptor>) -> result<unit, error-code>
[method]descriptor.sync-data: func(self: borrow<descriptor>) -> result<unit, error-code>
[method]descriptor.create-directory-at: func(self: borrow<descriptor>, path: string) -> result<unit, error-code>
[method]descriptor.remove-directory-at: func(self: borrow<descriptor>, path: string) -> result<unit, error-code>
[method]descriptor.unlink-file-at: func(self: borrow<descriptor>, path: string) -> result<unit, error-code>
[method]descriptor.rename-at: func(self: borrow<descriptor>, old: string, newdesc: borrow<descriptor>, new: string) -> result<unit, error-code>
[method]descriptor.link-at: func(self: borrow<descriptor>, flags: path-flags, old: string, newdesc: borrow<descriptor>, new: string) -> result<unit, error-code>
[method]descriptor.symlink-at: func(self: borrow<descriptor>, old: string, new: string) -> result<unit, error-code>
```

Offsets and lengths are byte quantities. Timestamp fields carry seconds and nanoseconds.

## `wasi:filesystem/preopens@0.2.0`

Component import interface `wasi:filesystem/preopens@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
descriptor = type descriptor from wasi:filesystem/types@0.2.0
get-directories: func() -> list<tuple<own<descriptor>, string>>
```

## `wasi:clocks/monotonic-clock@0.2.0`

Component import interface `wasi:clocks/monotonic-clock@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
pollable = type pollable from wasi:io/poll@0.2.0
now: func() -> u64
subscribe-duration: func(when: u64) -> own<pollable>
subscribe-instant: func(when: u64) -> own<pollable>
```

## `wasi:cli/environment@0.2.0`

Component import interface `wasi:cli/environment@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
get-arguments: func() -> list<string>
get-environment: func() -> list<tuple<string, string>>
```

## `wasi:random/random@0.2.0`

Component import interface `wasi:random/random@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
get-random-bytes: func(len: u64) -> list<u8>
```

## `wasi:random/insecure@0.2.0`

Component import interface `wasi:random/insecure@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
get-insecure-random-bytes: func(len: u64) -> list<u8>
```

## `wasi:random/insecure-seed@0.2.0`

Component import interface `wasi:random/insecure-seed@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
insecure-seed: func() -> tuple<u64, u64>
```

## `wasi:clocks/wall-clock@0.2.0`

Component import interface `wasi:clocks/wall-clock@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
datetime = record { seconds: u64, nanoseconds: u32 }
now: func() -> datetime
```

## `wasi:cli/terminal-stdin@0.2.0`

Component import interface `wasi:cli/terminal-stdin@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
terminal-input = resource
get-terminal-stdin: func() -> option<own<terminal-input>>
```

## `wasi:cli/terminal-stdout@0.2.0`

Component import interface `wasi:cli/terminal-stdout@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
terminal-output = resource
get-terminal-stdout: func() -> option<own<terminal-output>>
```

## `wasi:cli/terminal-stderr@0.2.0`

Component import interface `wasi:cli/terminal-stderr@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
terminal-output = resource
get-terminal-stderr: func() -> option<own<terminal-output>>
```

## `wasi:sockets/network@0.2.0`

Component import interface `wasi:sockets/network@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
network = resource
```

## `wasi:sockets/instance-network@0.2.0`

Component import interface `wasi:sockets/instance-network@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
network = type network from wasi:sockets/network@0.2.0
instance-network: func() -> own<network>
```

## `wasi:sockets/tcp@0.2.0`

Component import interface `wasi:sockets/tcp@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
ip-address-family = enum { ipv4, ipv6 }
ipv4-address = tuple<u8, u8, u8, u8>
ipv6-address = tuple<u16, u16, u16, u16, u16, u16, u16, u16>
ipv4-socket-address = record { port: u16, address: ipv4-address }
ipv6-socket-address = record { port: u16, flow-info: u32, address: ipv6-address, scope-id: u32 }
ip-socket-address = variant { ipv4(ipv4-socket-address), ipv6(ipv6-socket-address) }
ip-address = variant { ipv4(ipv4-address), ipv6(ipv6-address) }
error-code = enum { unknown, access-denied, not-supported, invalid-argument, out-of-memory, timeout, concurrency-conflict, not-in-progress, would-block, invalid-state, new-socket-limit, address-not-bindable, address-in-use, remote-unreachable, connection-refused, connection-reset, connection-aborted, datagram-too-large, name-unresolvable, temporary-resolver-failure, permanent-resolver-failure }
tcp-socket = resource
network = type network from wasi:sockets/network@0.2.0
input-stream = type input-stream from wasi:io/streams@0.2.0
output-stream = type output-stream from wasi:io/streams@0.2.0
pollable = type pollable from wasi:io/poll@0.2.0
[method]tcp-socket.start-bind: func(self: borrow<tcp-socket>, network: borrow<network>, address: ip-socket-address) -> result<unit, error-code>
[method]tcp-socket.start-connect: func(self: borrow<tcp-socket>, network: borrow<network>, address: ip-socket-address) -> result<unit, error-code>
[method]tcp-socket.finish-bind: func(self: borrow<tcp-socket>) -> result<unit, error-code>
[method]tcp-socket.start-listen: func(self: borrow<tcp-socket>) -> result<unit, error-code>
[method]tcp-socket.finish-listen: func(self: borrow<tcp-socket>) -> result<unit, error-code>
[method]tcp-socket.local-address: func(self: borrow<tcp-socket>) -> result<ip-socket-address, error-code>
[method]tcp-socket.remote-address: func(self: borrow<tcp-socket>) -> result<ip-socket-address, error-code>
[method]tcp-socket.is-listening: func(self: borrow<tcp-socket>) -> bool
[method]tcp-socket.subscribe: func(self: borrow<tcp-socket>) -> own<pollable>
[method]tcp-socket.finish-connect: func(self: borrow<tcp-socket>) -> result<tuple<own<input-stream>, own<output-stream>>, error-code>
[method]tcp-socket.accept: func(self: borrow<tcp-socket>) -> result<tuple<own<tcp-socket>, own<input-stream>, own<output-stream>>, error-code>
```

An occupied-listener-endpoint failure is an `error-code` result from `start-bind`, `finish-bind`, `start-listen`, or `finish-listen`; no particular reporting stage is required.

## `wasi:sockets/tcp-create-socket@0.2.0`

Component import interface `wasi:sockets/tcp-create-socket@0.2.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
tcp-socket = type tcp-socket from wasi:sockets/tcp@0.2.0
ip-address-family = enum { ipv4, ipv6 }
error-code = enum { unknown, access-denied, not-supported, invalid-argument, out-of-memory, timeout, concurrency-conflict, not-in-progress, would-block, invalid-state, new-socket-limit, address-not-bindable, address-in-use, remote-unreachable, connection-refused, connection-reset, connection-aborted, datagram-too-large, name-unresolvable, temporary-resolver-failure, permanent-resolver-failure }
create-tcp-socket: func(family: ip-address-family) -> result<own<tcp-socket>, error-code>
```

## `wasi:cli/stdout@0.3.0`

Component import interface `wasi:cli/stdout@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
error-code = enum { io, illegal-byte-sequence, pipe }
write-via-stream: func(data: stream<u8>) -> future<result<unit, error-code>>
```

## `wasi:cli/stderr@0.3.0`

Component import interface `wasi:cli/stderr@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
error-code = enum { io, illegal-byte-sequence, pipe }
write-via-stream: func(data: stream<u8>) -> future<result<unit, error-code>>
```

## `wasi:cli/environment@0.3.0`

Component import interface `wasi:cli/environment@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
get-arguments: func() -> list<string>
get-environment: func() -> list<tuple<string, string>>
```

## `wasi:random/random@0.3.0`

Component import interface `wasi:random/random@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
get-random-bytes: func(len: u64) -> list<u8>
```

## `wasi:random/insecure@0.3.0`

Component import interface `wasi:random/insecure@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
get-insecure-random-bytes: func(len: u64) -> list<u8>
```

## `wasi:random/insecure-seed@0.3.0`

Component import interface `wasi:random/insecure-seed@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
insecure-seed: func() -> tuple<u64, u64>
```

## `wasi:cli/stdin@0.3.0`

Component import interface `wasi:cli/stdin@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
error-code = enum { io, illegal-byte-sequence, pipe }
read-via-stream: func() -> tuple<stream<u8>, future<result<unit, error-code>>>
```

## `wasi:clocks/wall-clock@0.3.0`

Component import interface `wasi:clocks/wall-clock@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
datetime = record { seconds: u64, nanoseconds: u32 }
now: func() -> datetime
```

## `wasi:clocks/system-clock@0.3.0`

Component import interface `wasi:clocks/system-clock@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
datetime = record { seconds: s64, nanoseconds: u32 }
now: func() -> datetime
get-resolution: func() -> u64
```

## `wasi:clocks/monotonic-clock@0.3.0`

Component import interface `wasi:clocks/monotonic-clock@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
now: func() -> u64
get-resolution: func() -> u64
wait-for: async func(when: u64) -> unit
wait-until: async func(when: u64) -> unit
```

## `wasi:filesystem/types@0.3.0`

Component import interface `wasi:filesystem/types@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
descriptor = resource
directory-entry-stream = resource
path-flags = flags { symlink-follow }
open-flags = flags { create, directory, exclusive, truncate }
descriptor-flags = flags { read, write, file-integrity-sync, data-integrity-sync, requested-write-sync, mutate-directory }
error-code = variant { access, already, bad-descriptor, busy, deadlock, quota, exist, file-too-large, illegal-byte-sequence, in-progress, interrupted, invalid, io, is-directory, loop, too-many-links, message-size, name-too-long, no-device, no-entry, no-lock, insufficient-memory, insufficient-space, not-directory, not-empty, not-recoverable, unsupported, no-tty, no-such-device, overflow, not-permitted, pipe, read-only, invalid-seek, text-file-busy, cross-device, other(option<string>) }
descriptor-type = variant { block-device, character-device, directory, fifo, symbolic-link, regular-file, socket, other(option<string>) }
datetime = record { seconds: s64, nanoseconds: u32 }
new-timestamp = variant { no-change, now, timestamp(datetime) }
descriptor-stat = record { type: descriptor-type, link-count: u64, size: u64, data-access-timestamp: option<datetime>, data-modification-timestamp: option<datetime>, status-change-timestamp: option<datetime> }
metadata-hash-value = record { lower: u64, upper: u64 }
directory-entry = record { type: descriptor-type, name: string }
[method]descriptor.open-at: async func(self: borrow<descriptor>, pf: path-flags, path: string, of: open-flags, df: descriptor-flags) -> result<own<descriptor>, error-code>
[method]descriptor.metadata-hash: async func(self: borrow<descriptor>) -> result<metadata-hash-value, error-code>
[method]descriptor.metadata-hash-at: async func(self: borrow<descriptor>, flags: path-flags, path: string) -> result<metadata-hash-value, error-code>
[method]descriptor.is-same-object: async func(self: borrow<descriptor>, other: borrow<descriptor>) -> bool
[method]descriptor.sync: async func(self: borrow<descriptor>) -> result<unit, error-code>
[method]descriptor.sync-data: async func(self: borrow<descriptor>) -> result<unit, error-code>
[method]descriptor.set-size: async func(self: borrow<descriptor>, size: u64) -> result<unit, error-code>
[method]descriptor.get-flags: async func(self: borrow<descriptor>) -> result<descriptor-flags, error-code>
[method]descriptor.get-type: async func(self: borrow<descriptor>) -> result<descriptor-type, error-code>
[method]descriptor.stat: async func(self: borrow<descriptor>) -> result<descriptor-stat, error-code>
[method]descriptor.set-times: async func(self: borrow<descriptor>, atime: new-timestamp, mtime: new-timestamp) -> result<unit, error-code>
[method]descriptor.rename-at: async func(self: borrow<descriptor>, old: string, dest: borrow<descriptor>, new: string) -> result<unit, error-code>
[method]descriptor.link-at: async func(self: borrow<descriptor>, flags: path-flags, old: string, dest: borrow<descriptor>, new: string) -> result<unit, error-code>
[method]descriptor.symlink-at: async func(self: borrow<descriptor>, old: string, new: string) -> result<unit, error-code>
[method]descriptor.readlink-at: async func(self: borrow<descriptor>, path: string) -> result<string, error-code>
[method]descriptor.create-directory-at: async func(self: borrow<descriptor>, path: string) -> result<unit, error-code>
[method]descriptor.remove-directory-at: async func(self: borrow<descriptor>, path: string) -> result<unit, error-code>
[method]descriptor.unlink-file-at: async func(self: borrow<descriptor>, path: string) -> result<unit, error-code>
[method]descriptor.write-via-stream: func(self: borrow<descriptor>, data: stream<u8>, offset: u64) -> future<result<unit, error-code>>
[method]descriptor.append-via-stream: func(self: borrow<descriptor>, data: stream<u8>) -> future<result<unit, error-code>>
[method]descriptor.read-via-stream: func(self: borrow<descriptor>, offset: u64) -> tuple<stream<u8>, future<result<unit, error-code>>>
[method]descriptor.read-directory: func(self: borrow<descriptor>) -> tuple<stream<directory-entry>, future<result<unit, error-code>>>
```

Offsets and lengths are byte quantities. Timestamp fields carry seconds and nanoseconds.

## `wasi:filesystem/preopens@0.3.0`

Component import interface `wasi:filesystem/preopens@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
descriptor = type descriptor from wasi:filesystem/types@0.3.0
get-directories: func() -> list<tuple<own<descriptor>, string>>
```

## `wasi:sockets/types@0.3.0`

Component import interface `wasi:sockets/types@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
ip-address-family = enum { ipv4, ipv6 }
ipv4-address = tuple<u8, u8, u8, u8>
ipv6-address = tuple<u16, u16, u16, u16, u16, u16, u16, u16>
ipv4-socket-address = record { port: u16, address: ipv4-address }
ipv6-socket-address = record { port: u16, flow-info: u32, address: ipv6-address, scope-id: u32 }
ip-socket-address = variant { ipv4(ipv4-socket-address), ipv6(ipv6-socket-address) }
ip-address = variant { ipv4(ipv4-address), ipv6(ipv6-address) }
error-code = variant { access-denied, not-supported, invalid-argument, out-of-memory, timeout, invalid-state, address-not-bindable, address-in-use, remote-unreachable, connection-refused, connection-broken, connection-reset, connection-aborted, datagram-too-large, other(option<string>) }
tcp-socket = resource
udp-socket = resource
[static]tcp-socket.create: func(family: ip-address-family) -> result<own<tcp-socket>, error-code>
[method]tcp-socket.bind: func(self: borrow<tcp-socket>, address: ip-socket-address) -> result<unit, error-code>
[method]tcp-socket.connect: async func(self: borrow<tcp-socket>, address: ip-socket-address) -> result<unit, error-code>
[method]tcp-socket.get-local-address: func(self: borrow<tcp-socket>) -> result<ip-socket-address, error-code>
[method]tcp-socket.get-remote-address: func(self: borrow<tcp-socket>) -> result<ip-socket-address, error-code>
[method]tcp-socket.get-address-family: func(self: borrow<tcp-socket>) -> ip-address-family
[method]tcp-socket.get-is-listening: func(self: borrow<tcp-socket>) -> bool
[method]tcp-socket.listen: func(self: borrow<tcp-socket>) -> result<stream<own<tcp-socket>>, error-code>
[method]tcp-socket.send: func(self: borrow<tcp-socket>, data: stream<u8>) -> future<result<unit, error-code>>
[method]tcp-socket.receive: func(self: borrow<tcp-socket>) -> tuple<stream<u8>, future<result<unit, error-code>>>
[static]udp-socket.create: func(family: ip-address-family) -> result<own<udp-socket>, error-code>
[method]udp-socket.bind: func(self: borrow<udp-socket>, address: ip-socket-address) -> result<unit, error-code>
[method]udp-socket.connect: func(self: borrow<udp-socket>, address: ip-socket-address) -> result<unit, error-code>
[method]udp-socket.get-local-address: func(self: borrow<udp-socket>) -> result<ip-socket-address, error-code>
[method]udp-socket.get-remote-address: func(self: borrow<udp-socket>) -> result<ip-socket-address, error-code>
[method]udp-socket.get-address-family: func(self: borrow<udp-socket>) -> ip-address-family
[method]udp-socket.disconnect: func(self: borrow<udp-socket>) -> result<unit, error-code>
[method]udp-socket.send: async func(self: borrow<udp-socket>, data: list<u8>, remote: option<ip-socket-address>) -> result<unit, error-code>
[method]udp-socket.receive: async func(self: borrow<udp-socket>) -> result<tuple<list<u8>, ip-socket-address>, error-code>
```

## `wasi:sockets/ip-name-lookup@0.3.0`

Component import interface `wasi:sockets/ip-name-lookup@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
ip-address-family = enum { ipv4, ipv6 }
ipv4-address = tuple<u8, u8, u8, u8>
ipv6-address = tuple<u16, u16, u16, u16, u16, u16, u16, u16>
ipv4-socket-address = record { port: u16, address: ipv4-address }
ipv6-socket-address = record { port: u16, flow-info: u32, address: ipv6-address, scope-id: u32 }
ip-socket-address = variant { ipv4(ipv4-socket-address), ipv6(ipv6-socket-address) }
ip-address = variant { ipv4(ipv4-address), ipv6(ipv6-address) }
error-code = variant { access-denied, invalid-name, name-unresolvable, temporary-resolver-failure, permanent-resolver-failure, other(option<string>) }
resolve-addresses: async func(name: string) -> result<list<ip-address>, error-code>
```

## `wasi:http/types@0.3.0`

Component import interface `wasi:http/types@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
DNS-error-payload = record { rcode: option<string>, info-code: option<u16> }
TLS-alert-received-payload = record { alert-id: option<u8>, alert-message: option<string> }
field-size-payload = record { field-name: option<string>, field-size: option<u32> }
error-code = variant { DNS-timeout, DNS-error(DNS-error-payload), destination-not-found, destination-unavailable, destination-IP-prohibited, destination-IP-unroutable, connection-refused, connection-terminated, connection-timeout, connection-read-timeout, connection-write-timeout, connection-limit-reached, TLS-protocol-error, TLS-certificate-error, TLS-alert-received(TLS-alert-received-payload), HTTP-request-denied, HTTP-request-length-required, HTTP-request-body-size(option<u64>), HTTP-request-method-invalid, HTTP-request-URI-invalid, HTTP-request-URI-too-long, HTTP-request-header-section-size(option<u32>), HTTP-request-header-size(option<field-size-payload>), HTTP-request-trailer-section-size(option<u32>), HTTP-request-trailer-size(field-size-payload), HTTP-response-incomplete, HTTP-response-header-section-size(option<u32>), HTTP-response-header-size(field-size-payload), HTTP-response-body-size(option<u64>), HTTP-response-trailer-section-size(option<u32>), HTTP-response-trailer-size(field-size-payload), HTTP-response-transfer-coding(option<string>), HTTP-response-content-coding(option<string>), HTTP-response-timeout, HTTP-upgrade-failed, HTTP-protocol-error, loop-detected, configuration-error, internal-error(option<string>) }
fields = resource
request = resource
response = resource
request-options = resource
header-error = variant { invalid-syntax, forbidden, immutable, size-exceeded, other(option<string>) }
request-options-error = variant { not-supported, immutable, other(option<string>) }
method = variant { get, head, post, put, delete, connect, options, trace, patch, other(string) }
scheme = variant { HTTP, HTTPS, other(string) }
[constructor]fields: func() -> own<fields>
[static]fields.from-list: func(entries: list<tuple<string, list<u8>>>) -> result<own<fields>, header-error>
[method]fields.get: func(self: borrow<fields>, name: string) -> list<list<u8>>
[method]fields.has: func(self: borrow<fields>, name: string) -> bool
[method]fields.set: func(self: borrow<fields>, name: string, values: list<list<u8>>) -> result<unit, header-error>
[method]fields.append: func(self: borrow<fields>, name: string, value: list<u8>) -> result<unit, header-error>
[method]fields.delete: func(self: borrow<fields>, name: string) -> result<unit, header-error>
[method]fields.get-and-delete: func(self: borrow<fields>, name: string) -> result<list<list<u8>>, header-error>
[method]fields.clone: func(self: borrow<fields>) -> own<fields>
[static]request.new: func(headers: own<fields>, contents: option<stream<u8>>, trailers: future<result<option<own<fields>>, error-code>>, options: option<own<request-options>>) -> tuple<own<request>, future<result<unit, error-code>>>
[method]request.get-headers: func(self: borrow<request>) -> own<fields>
[static]request.consume-body: func(this: own<request>, res: future<result<unit, error-code>>) -> tuple<stream<u8>, future<result<option<own<fields>>, error-code>>>
[static]response.new: func(headers: own<fields>, contents: option<stream<u8>>, trailers: future<result<option<own<fields>>, error-code>>) -> tuple<own<response>, future<result<unit, error-code>>>
[method]response.get-headers: func(self: borrow<response>) -> own<fields>
[static]response.consume-body: func(this: own<response>, res: future<result<unit, error-code>>) -> tuple<stream<u8>, future<result<option<own<fields>>, error-code>>>
[method]request.set-method: func(self: borrow<request>, value: method) -> result<unit, unit>
[method]request.get-method: func(self: borrow<request>) -> method
[method]request.set-scheme: func(self: borrow<request>, value: option<scheme>) -> result<unit, unit>
[method]request.get-scheme: func(self: borrow<request>) -> option<scheme>
[method]request.set-authority: func(self: borrow<request>, value: option<string>) -> result<unit, unit>
[method]request.get-authority: func(self: borrow<request>) -> option<string>
[method]request.set-path-with-query: func(self: borrow<request>, value: option<string>) -> result<unit, unit>
[method]request.get-path-with-query: func(self: borrow<request>) -> option<string>
[method]response.get-status-code: func(self: borrow<response>) -> u16
[method]response.set-status-code: func(self: borrow<response>, value: u16) -> result<unit, unit>
[constructor]request-options: func() -> own<request-options>
[method]request-options.clone: func(self: borrow<request-options>) -> own<request-options>
[method]request.get-options: func(self: borrow<request>) -> option<own<request-options>>
[method]request-options.get-connect-timeout: func(self: borrow<request-options>) -> option<u64>
[method]request-options.set-connect-timeout: func(self: borrow<request-options>, duration: option<u64>) -> result<unit, request-options-error>
[method]request-options.get-first-byte-timeout: func(self: borrow<request-options>) -> option<u64>
[method]request-options.set-first-byte-timeout: func(self: borrow<request-options>, duration: option<u64>) -> result<unit, request-options-error>
[method]request-options.get-between-bytes-timeout: func(self: borrow<request-options>) -> option<u64>
[method]request-options.set-between-bytes-timeout: func(self: borrow<request-options>, duration: option<u64>) -> result<unit, request-options-error>
```

Header values and body elements are bytes. Timeout durations are u64 nanoseconds.

## `wasi:http/client@0.3.0`

Component import interface `wasi:http/client@0.3.0` exposes these declarations. `unit` denotes no payload. Resource values are opaque handles; `own` and `borrow` distinguish the ownership form.

```text
request = type request from wasi:http/types@0.3.0
response = type response from wasi:http/types@0.3.0
error-code = type error-code from wasi:http/types@0.3.0
send: async func(request: own<request>) -> result<own<response>, error-code>
```

## `wasi:cli/run@0.2.0`

The command component exports an interface instance named `wasi:cli/run@0.2.0` containing:

```text
run: func() -> result<unit, unit>
```

## `wasi:cli/run@0.3.0`

The command component exports an interface instance named `wasi:cli/run@0.3.0` containing:

```text
run: async func() -> unit or result<unit, unit>
```

## `canon`

The `canon` exchange format is the following.

Component binaries exchange component values with core functions using the memory32 Canonical ABI. The type names `bool`, `s8`, `u8`, `s16`, `u16`, `s32`, `u32`, `s64`, `u64`, `f32`, `f64`, `char`, `string`, `list`, `record`, `tuple`, `variant`, `enum`, `flags`, `option`, `result`, `own`, `borrow`, `stream`, and `future` denote the declared value forms.

The guest-memory format is little-endian. Scalar size and alignment, in bytes, are:

| Type | Size | Alignment |
| --- | --- | --- |
| bool, s8, u8 | 1 | 1 |
| s16, u16 | 2 | 2 |
| s32, u32, f32, char | 4 | 4 |
| s64, u64, f64 | 8 | 8 |
| own, borrow, stream, future | 4 | 4 |
| string, list | 8 | 4 |

Signed integers use two's complement; floating values use IEEE-754; a character occupies a u32 Unicode scalar slot. A boolean uses byte 0 for false and 1 for true. Handles occupy u32 slots. A string descriptor contains a u32 byte pointer at offset 0 and u32 UTF-8 byte length at offset 4. A list descriptor has the same pair with an element count as its length; elements occupy consecutive slots of the declared element's memory size.

Record and tuple fields appear in declaration order, each at an offset aligned for its type. Their aggregate alignment is the largest field alignment, and their memory size includes trailing padding to that alignment. Enum and variant tags are zero-based declaration indices, occupying 1, 2, or 4 bytes for at most 256, at most 65536, or more cases respectively. A variant's payload starts after the tag at an offset aligned for every case payload; its slot accommodates the largest payload and has trailing padding to the aggregate alignment. An option has tags 0 for none and 1 for some. A result has tags 0 for ok and 1 for err. Flags occupy 1 byte for up to 8 labels, 2 for up to 16, and 4 for up to 32; bit positions follow label declaration order.

At core-function boundaries, bool, integers through 32 bits, characters, enum tags, flags, and handles occupy i32 operands; 64-bit integers occupy i64; floats occupy their corresponding f32 or f64 operands. Strings and lists occupy a pointer/count pair of i32 operands. Records and tuples occupy their fields' ordered operands. Tagged values occupy an i32 tag followed by payload operands, with the same payload positions shared across alternatives. A synchronous parameter list with more than 16 operands is passed by one i32 pointer to its guest-memory tuple. A result with more than one operand is exchanged in guest memory: an i32 return-area pointer is the lifted core function's result, or a final i32 return-area parameter is supplied to a lowered core function.
A stream or future copy-status word is an i32: `0xffffffff` denotes blocked. Otherwise its low four bits are 0 completed, 1 peer dropped, or 2 cancelled; its high 28 bits carry the transferred element count for streams and 0 for futures.

A canonical lift can include `(post-return <core-function-reference>)`. The referenced core function accepts the lifted core function's result operands and has no result.

## `canon lift`

A component binary's `canon lift` declaration names a core function and a component function type. Its exchanged options are `memory` (the core linear memory), `realloc` (a core function with `(old-pointer: i32, old-size: i32, alignment: i32, new-size: i32) -> i32`), and `string-encoding=<encoding>`. Encoding identifiers appearing at this boundary are `utf8`, `utf16`, and `latin1+utf16`.

The async declaration carries `async` and a `callback` core-function reference. The core entry returns i32. The callback signature is `(event: i32, handle: i32, payload: i32) -> i32`. The entry and callback return word has a low four-bit status: 0 exit, 1 yield, 2 wait. For wait, the high 28 bits carry the waitable-set handle.

Callback event values are 0 none, 1 subtask, 2 stream-read, 3 stream-write, 4 future-read, and 5 future-write. The second argument carries the associated waitable handle. For read/write events the third argument is the copy-status word; for subtask completion it carries status 2.

## `canon lower`

A component binary's `canon lower` declaration names a component function and exposes a core function. The options `memory`, `realloc`, and `string-encoding=<encoding>` identify its exchange memory, allocation callback, and string encoding.

For an `async` lower, the core call returns an i32 packed status. Status 2 in its low four bits denotes completed; a pending call carries a subtask handle in the high 28 bits. An async call with a declared result receives a guest-memory result-area pointer after its arguments. Up to four parameter operands are passed directly; a parameter list with more than four operands is passed as one i32 pointer to its guest-memory tuple.

## `resource.new`

The component binary declaration `canon resource.new <resource-type>` exposes a core function `(representation: i32) -> i32`. The parameter is the resource's core representation; the result is its owning resource handle. Resource type declarations carry an i32 representation and an optional destructor core function `(representation: i32) -> void`.

## `stream.new`

The component binary declaration `canon stream.new <type>` identifies a `stream` type. Core signature: `() -> i64`. The result packs the readable u32 handle in the low 32 bits and the writable u32 handle in the high 32 bits.

## `stream.read`

The component binary declaration `canon stream.read <type>` identifies a `stream` type. Core signature: `(handle: i32, pointer: i32, count: i32) -> i32`. The pointer identifies the guest-memory destination for the declared elements; count is in elements. The result is an i32 copy-status word in the `canon` exchange format. The declaration carries a `memory` option and, for allocated aggregate payloads, a `realloc` function reference.

## `stream.write`

The component binary declaration `canon stream.write <type>` identifies a `stream` type. Core signature: `(handle: i32, pointer: i32, count: i32) -> i32`. The pointer identifies the guest-memory source for the declared elements; count is in elements. The result is an i32 copy-status word in the `canon` exchange format. The declaration carries a `memory` option and, for allocated aggregate payloads, a `realloc` function reference.

## `stream.drop-readable`

The component binary declaration `canon stream.drop-readable <type>` identifies a `stream` type. Core signature: `(handle: i32) -> void`. The argument identifies the readable endpoint.

## `stream.drop-writable`

The component binary declaration `canon stream.drop-writable <type>` identifies a `stream` type. Core signature: `(handle: i32) -> void`. The argument identifies the writable endpoint.

## `stream.cancel-read`

The component binary declaration `canon stream.cancel-read <type>` identifies a `stream` type. Core signature: `(handle: i32) -> i32`. The argument identifies the readable endpoint; the result is an i32 copy-status word in the `canon` exchange format.

## `future.new`

The component binary declaration `canon future.new <type>` identifies a `future` type. Core signature: `() -> i64`. The result packs the readable u32 handle in the low 32 bits and the writable u32 handle in the high 32 bits.

## `future.read`

The component binary declaration `canon future.read <type>` identifies a `future` type. Core signature: `(handle: i32, pointer: i32) -> i32`. The pointer identifies the guest-memory destination for the declared value. The result is an i32 copy-status word in the `canon` exchange format. The declaration carries a `memory` option and, for allocated aggregate payloads, a `realloc` function reference.

## `future.write`

The component binary declaration `canon future.write <type>` identifies a `future` type. Core signature: `(handle: i32, pointer: i32) -> i32`. The pointer identifies the guest-memory source for the declared value. The result is an i32 copy-status word in the `canon` exchange format. The declaration carries a `memory` option and, for allocated aggregate payloads, a `realloc` function reference.

## `future.drop-readable`

The component binary declaration `canon future.drop-readable <type>` identifies a `future` type. Core signature: `(handle: i32) -> void`. The argument identifies the readable endpoint.

## `future.drop-writable`

The component binary declaration `canon future.drop-writable <type>` identifies a `future` type. Core signature: `(handle: i32) -> void`. The argument identifies the writable endpoint.

## `future.cancel-read`

The component binary declaration `canon future.cancel-read <type>` identifies a `future` type. Core signature: `(handle: i32) -> i32`. The argument identifies the readable endpoint; the result is an i32 copy-status word in the `canon` exchange format.

## `waitable-set.new`

The component binary declaration `canon waitable-set.new` exposes a core function `() -> i32`. Its result is an opaque waitable-set handle.

## `waitable.join`

The component binary declaration `canon waitable.join` exposes a core function `(handle: i32, set: i32) -> void`. The first argument identifies a waitable endpoint or subtask; the second identifies a waitable set.

## `task.return`

The component binary declaration `canon task.return` carries its result type as a `result` declaration. Its core signature has the declared result's Canonical ABI operands as parameters and no core result. The exchanged result forms here are `u32` and `result` with no payload in either alternative.

## `WASM_CONST`

`WASM_CONST` is the C wasm_mutability_t tag `0` for a immutable global.

## `WASM_VAR`

`WASM_VAR` is the C wasm_mutability_t tag `1` for a mutable global.

## `WASM_I32`

`WASM_I32` is the C wasm_valkind_t tag `0` for a i32.

## `WASM_I64`

`WASM_I64` is the C wasm_valkind_t tag `1` for a i64.

## `WASM_F32`

`WASM_F32` is the C wasm_valkind_t tag `2` for a f32.

## `WASM_F64`

`WASM_F64` is the C wasm_valkind_t tag `3` for a f64.

## `WASM_FUNCREF`

`WASM_FUNCREF` is the C wasm_valkind_t tag `129` for a function reference.

## `WASM_EXTERN_FUNC`

`WASM_EXTERN_FUNC` is the C wasm_externkind_t tag `0` for a function.

## `WASM_EXTERN_GLOBAL`

`WASM_EXTERN_GLOBAL` is the C wasm_externkind_t tag `1` for a global.

## `WASM_EXTERN_TABLE`

`WASM_EXTERN_TABLE` is the C wasm_externkind_t tag `2` for a table.

## `WASM_EXTERN_MEMORY`

`WASM_EXTERN_MEMORY` is the C wasm_externkind_t tag `3` for a memory.

## `WASM_EXTERN_TAG`

`WASM_EXTERN_TAG` is the C wasm_externkind_t tag `4` for a tag.

## `wasm_func_new_with_env`

```c
typedef wasm_trap_t* (*wasm_func_callback_with_env_t)(
    void* env, const wasm_val_vec_t* args, wasm_val_vec_t* results);
wasm_func_t* wasm_func_new_with_env(
    wasm_store_t* store, const wasm_functype_t* type,
    wasm_func_callback_with_env_t callback, void* env,
    void (*finalizer)(void*));
```

Returns an owning function handle or NULL. The callback receives the supplied
context pointer, an argument vector and a writable result vector. Its return is
NULL or an owning trap handle. The finalizer receives the context pointer.

## `wasm_functype_new_1_1`

```c
wasm_functype_t* wasm_functype_new_1_1(
    wasm_valtype_t* parameter, wasm_valtype_t* result);
```

Accepts owning parameter and result type handles and returns an owning function
type handle. The parameter and result each occupy one position in the signature.

## `wasi:cli/exit@0.2.0`

Component import interface `wasi:cli/exit@0.2.0` exposes:

```text
exit: func(status: result) -> unit
```

`unit` denotes no result payload.

## `stream.cancel-write`

The component binary declaration `canon stream.cancel-write <type>` identifies a `stream` type. Core signature: `(handle: i32) -> i32`. The argument identifies the writable endpoint; the result is an i32 copy-status word in the `canon` exchange format.

## `future.cancel-write`

The component binary declaration `canon future.cancel-write <type>` identifies a `future` type. Core signature: `(handle: i32) -> i32`. The argument identifies the writable endpoint; the result is an i32 copy-status word in the `canon` exchange format.

## `wasm_extern_kind`

```c
wasm_externkind_t wasm_extern_kind(const wasm_extern_t*);
```

Accepts a live external handle and returns its `wasm_externkind_t` tag: `WASM_EXTERN_FUNC`, `WASM_EXTERN_GLOBAL`, `WASM_EXTERN_TABLE`, `WASM_EXTERN_MEMORY`, or `WASM_EXTERN_TAG`. The handle remains borrowed.
