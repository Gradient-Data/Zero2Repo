# Interface Contract

The Python package is imported as velnora. The expression namespace is available as velnora.claripy.

The command-line entry is python -m velnora decompile; the local MCP server entry is python -m velnora.mcp.

## `velnora`

The package exposes Project, load_shellcode, KnowledgeBase, SimProcedure, PointerWrapper, SimFile, SimFileStream, SimPackets, and SimPacketsStream, SimHostFilesystem, SimFileDescriptorDuplex, and KnowledgeBaseSnapshot. Its namespaces include claripy, types, calling_conventions, options, errors, engines, exploration_techniques, analyses, and SIM_PROCEDURES.

## `velnora.Project`

### Construction

Project(thing, ...) accepts a binary filename as str or a binary stream. The keyword interface includes auto_load_libs, main_opts, ld_path, except_missing_libs, use_system_libs, load_debug_info, exclude_sim_procedures_list, and engine.

main_opts is a dictionary with named options backend, arch, base_addr, entry_point, entry_point_params, jni_libs, jni_libs_ld_path, android_sdk, and android_api_version. Path collections contain strings; architecture selection accepts an architecture object or identifier; native addresses are integers. backend includes the raw-image selector blob. Java entry selection uses a qualified method string and a tuple of parameter-type strings.

### Object interface

Readable attributes are loader, arch, entry, factory, kb, analyses, and filename. rustc_version is assignable as a compiler-version string. entry is an integer native address or a Java address descriptor.

hook(addr, hook, length=..., replace=...) accepts a procedure object or a callable receiving a state. hook_symbol(symbol_name, simproc) accepts a symbol-name string and a procedure object. is_hooked(addr) returns bool; hooked_by(addr) returns the registered procedure; unhook(addr) removes a registration.

Failure carriers are Exception for unavailable input, velnora.errors.VelnoraValueError for an invalid native address, cle.CLEError for missing architecture information, cle.CLEFileNotFoundError for a missing dependency, and KeyError for an unavailable architecture.

## `velnora.load_shellcode`

load_shellcode(shellcode, arch, load_address=..., start_offset=..., engine=...) accepts machine-code bytes, an architecture identifier or architecture object, integer load_address and start_offset arguments, and an optional execution-engine class. It returns a Project.

## `cle.Loader`

A project's loader exposes main_object, iterable all_objects, and name-indexed shared_objects. find_object_containing(address) returns an image object or None; find_symbol(name) returns a symbol with rebased_addr. memory.load(address, size) returns bytes.

Image objects expose arch, entry, min_addr, max_addr, segments, sections, binary, symbols, imports, and memory. Segment fields vaddr, filesize, and offset are integer virtual address, file-backed byte length, and file offset. Section fields vaddr, memsize, and is_executable are address, mapped byte length, and execution flag. contains_addr(address) returns bool.

get_symbol(name) returns a symbol; imports[name].symbol is the imported symbol. Symbols expose name, rebased_addr, is_export, owner, and resolvedby.

Universal-image metadata exposes available_arches as a sequence of architecture-name strings and child_objects as a sequence of image objects. Java images expose get_soot_method(name, params=...); its result has name, params, ret, and blocks. A method block has idx and statements. Debug metadata exposes iterable compilation_units, whose units have language.

## `archinfo`

The archinfo namespace exposes ArchX86(), ArchAMD64(), ArchPcode(language), and arch_from_id(identifier, endness=...). Constructors and lookup return architecture objects.

An architecture exposes name as text, bits and byte_width as integer bit counts, memory_endness as an endianness token, and registers as a mapping from register names to (offset, size) tuples. Register offsets and sizes are measured in bytes. Endianness tokens exchanged with memory and architecture interfaces are Iend_LE and Iend_BE.

For architecture-name fields, X86 denotes 32-bit x86, AMD64 denotes 64-bit x86, AARCH64 denotes 64-bit Arm, and Soot denotes Java bytecode. Letter case in these names is insignificant.

## `archinfo.ArchX86`

ArchX86() returns an architecture object in the archinfo namespace.

## `archinfo.ArchAMD64`

ArchAMD64() returns an architecture object in the archinfo namespace.

## `archinfo.ArchPcode`

ArchPcode(language) returns an architecture object in the archinfo namespace.

## `archinfo.arch_from_id`

arch_from_id(identifier, endness=...) returns an architecture object in the archinfo namespace.

## `velnora.types`

The types namespace exposes parse_type, parse_file, and register_types, also defined in velnora.sim_type.

## `velnora.sim_type.parse_type`

parse_type(defn) accepts a C declaration string and returns a type object. Parsing failure raises pycparser.c_parser.ParseError.

## `velnora.sim_type.parse_file`

parse_file(defn) accepts C declaration text and returns (declarations, types), two dictionaries indexed by declared names and named-type spellings, respectively. Their values are type objects.

## `velnora.sim_type.register_types`

register_types(types) accepts a dictionary of named type objects or a named structure type object.

## `velnora.sim_type.SimTypeNum`

SimTypeNum(size, signed=...) constructs a type object. Type objects expose with_arch(arch) returning a bound type and size as a bit count. size is a bit count and signed is boolean.

## `velnora.sim_type.SimTypeInt`

SimTypeInt() constructs a type object. Type objects expose with_arch(arch) returning a bound type and size as a bit count. signed is a boolean attribute.

## `velnora.sim_type.SimTypeShort`

SimTypeShort is an inspectable type class. Type objects expose size as a bit count. signed is a boolean attribute.

## `velnora.sim_type.SimTypeLong`

SimTypeLong() constructs a type object. Type objects expose size as a bit count.

## `velnora.sim_type.SimTypeChar`

SimTypeChar() constructs a type object. Type objects expose size as a bit count.

## `velnora.sim_type.SimTypeFloat`

SimTypeFloat is an inspectable type class.

## `velnora.sim_type.SimTypeDouble`

SimTypeDouble is an inspectable type class.

## `velnora.sim_type.SimTypePointer`

SimTypePointer(pts_to) constructs a type object. Type objects expose with_arch(arch) returning a bound type and size as a bit count. pts_to is the pointed-to type.

## `velnora.sim_type.SimTypeArray`

SimTypeArray is an inspectable type class. Type objects expose size as a bit count. elem_type is the element type and length is the integer element count.

## `velnora.sim_type.SimStruct`

SimStruct is an inspectable type class. Type objects expose with_arch(arch) returning a bound type and size as a bit count. fields maps member names to type objects; offsets maps those names to byte offsets. An unavailable-layout failure is signaled by ValueError.

## `velnora.sim_type.SimUnion`

SimUnion is an inspectable type class. members maps member names to type objects.

## `velnora.sim_type.SimTypeEnum`

SimTypeEnum is an inspectable type class. members maps enumerator names to integer values.

## `velnora.sim_type.SimTypeFunction`

SimTypeFunction(args, returnty) constructs a type object. Type objects expose with_arch(arch) returning a bound type and size as a bit count. args is the argument-type sequence, returnty is the return type, and arg_names is the argument-name sequence. c_repr() returns a C declaration string. str() uses (<argument types>) -> <return type>.

## `velnora.sim_type`

The module exposes SimTypeNum, SimTypeInt, SimTypeShort, SimTypeLong, SimTypeChar, SimTypeFloat, SimTypeDouble, SimTypePointer, SimTypeArray, SimStruct, SimUnion, SimTypeEnum, SimTypeFunction, parse_type, parse_file, and register_types.

## `velnora.factory.VelnoraObjectFactory`

A project's factory exposes these call forms:

- blank_state(addr=..., add_options=..., mode=...) returns a state.
- entry_state(args=..., env=..., stdin=...) and full_init_state(args=..., env=...) return states. args is a sequence of byte strings or expressions; env is a mapping with string or byte-string keys and string, byte-string, or expression values. stdin accepts a simulated file.
- call_state(addr, *args, prototype=..., ret_addr=..., cc=..., stack_base=..., alloc_base=..., grow_like_stack=...) returns a state. Arguments may be scalars, expressions, strings, lists, a PointerWrapper, or Java SootArgument objects. prototype accepts a C declaration string or a function-type object.
- successors(state, num_inst=..., extra_stop_points=...) returns a successor result. Stop points are a set of native addresses.
- callable(addr, prototype=..., cc=..., concrete_only=...) returns a callable function object.
- simulation_manager(state_or_states, stashes=..., save_unsat=..., save_unconstrained=..., veritesting=...) returns a simulation manager. The initial argument may be a state or a list of states; stashes is a dictionary from names to state lists.
- block(addr, size=..., num_inst=..., byte_string=..., opt_level=...) returns an instruction block. addr accepts an integer or Java address descriptor. Sizes are byte counts, num_inst is an instruction count, and byte_string is bytes.

successors can raise velnora.errors.SimSegfaultException, velnora.errors.SimIRSBNoDecodeError, or velnora.errors.SimEngineError. Instruction translation can raise velnora.errors.SimTranslationError.

concrete_only selects single-path-only invocation. grow_like_stack=False selects allocation toward higher addresses.

## `velnora.SimState`

State attributes include project, arch, addr, solver, memory, registers, regs, mem, fs, posix, libc, options, inspect, history, callstack, scratch, and dvars. addr is the current address. The regs object exposes readable and assignable expression attributes named by arch.registers. Its ip attribute is the instruction-pointer carrier. For Java invocation, invoke_return_value carries the method result expression.

add_constraints(*constraints) accepts boolean expressions. step(**kwargs) returns a successor result. copy() returns a state. merge(*others) returns (state, conditions, changed): the result state, a condition sequence corresponding to the receiver followed by the supplied states, and a boolean change indicator. get_plugin(name) returns the named state component. State objects support pickle.dumps and pickle.load.

options supports add(option) and discard(option), and writable symbolic_ip_max_targets as an integer target count. libc exposes writable max_packet_size as an integer byte count and errno_location as an integer memory address, plus readable errno as an error-code expression. scratch.sim_procedure accepts the active procedure object.

## `velnora.state_plugins.solver.SimSolver`

The state-bound solver supports:

- BVS(name, size), returning a symbolic bitvector.
- add(*constraints), accepting boolean constraints.
- satisfiable(extra_constraints=...), is_true(expression), and is_false(expression), returning bool.
- eval(expression, cast_to=..., extra_constraints=..., signed=...) and eval_one(expression, cast_to=..., extra_constraints=...), returning a scalar.
- eval_upto(expression, n, extra_constraints=...), eval_atleast(expression, n), and eval_exact(expression, n), returning lists of scalar solutions.
- min(expression, signed=...) and max(expression, signed=...), returning integer bit patterns.

Scalar solutions are int for bitvectors and lengths, bool for booleans, float for floating-point expressions, and str for strings. cast_to=bytes requests a byte-string result. Query-local constraints are sequences of boolean expressions. Failure classes are velnora.errors.SimUnsatError for an unsatisfiable evaluation and velnora.errors.SimValueError for a failed solution-cardinality request.

## `velnora.storage.memory_mixins.DefaultMemory`

State memory and registers expose load(addr, size=..., endness=..., inspect=...) and store(addr, data, size=..., endness=...). Addresses are integers or bitvector expressions; register storage also accepts a register-name string. Sizes are byte counts. Stored data accepts bytes, integers, or bitvector expressions. load returns an expression.

Memory additionally exposes map_region(addr, length, permissions), unmap_region(addr, length), and permissions(addr, permissions=...). A permissions query returns a bit-mask expression: read is bit 1, write is bit 2, and execute is bit 4. read_strategies and write_strategies are assignable lists of address-policy objects. Access failure is signaled by velnora.errors.SimSegfaultException.

Java memory.load accepts a SimSootValue_StaticFieldRef or SimSootValue_ArrayRef and returns the corresponding Java value. Java object values expose get_field(state, field_name, field_type).

## `velnora.state_plugins.view.SimMemView`

state.mem[address].with_type(sim_type) returns a typed memory view. A view exposes resolved as an expression and concrete as a Python value: bytes for a character, int for an integer, and a list for an array. Structure members are accessed and assigned by their declared attribute names. Array elements support integer indexing and assignment. deref returns the target view of a pointer. store(value) writes through a view.

## `velnora.callable.Callable`

The object returned by factory.callable is called as function(*args); its return is an expression. result_state exposes the resulting state, and result_path_group exposes a simulation manager. set_base_state(state) accepts a state.

Call failures raise velnora.errors.VelnoraCallableError or its more specific velnora.errors.VelnoraCallableMultistateError.

## `velnora.calling_conventions`

The calling_conventions namespace exposes SimCCCdecl, SimCCStdcall, SimCCMicrosoftFastcall, SimCCMicrosoftThiscall, SimCCSystemVAMD64, SimCCMicrosoftAMD64, SimCCARM, SimCCARMHF, SimCCAArch64, SimCCO32, SimCCN32, SimCCN64, SimCCPowerPC, SimCCPowerPC64, SimCCS390X, SimCCRISCV64, SimCCUsercall, SimRegArg, and SimStackArg.

## `velnora.calling_conventions.SimCCCdecl`

SimCCCdecl(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCStdcall`

SimCCStdcall(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCMicrosoftFastcall`

SimCCMicrosoftFastcall(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCMicrosoftThiscall`

SimCCMicrosoftThiscall(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCSystemVAMD64`

SimCCSystemVAMD64(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object. get_args(state, prototype) returns argument expressions. str() renders <SimCCSystemVAMD64>.

## `velnora.calling_conventions.SimCCMicrosoftAMD64`

SimCCMicrosoftAMD64(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCARM`

SimCCARM(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCARMHF`

SimCCARMHF(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCAArch64`

SimCCAArch64(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCO32`

SimCCO32(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCN32`

SimCCN32(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCN64`

SimCCN64(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCPowerPC`

SimCCPowerPC(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCPowerPC64`

SimCCPowerPC64(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCS390X`

SimCCS390X(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCRISCV64`

SimCCRISCV64(arch) constructs a calling-convention object. arg_locs(prototype) returns a sequence of argument-location objects; return_val(type) returns a return-location object.

## `velnora.calling_conventions.SimCCUsercall`

SimCCUsercall(arch, args, ret_loc) accepts an architecture, a sequence of argument-location objects, and a return-location object. arg_locs(prototype) returns the location sequence; return_val(type) returns a location. setup_callsite(state, ret_addr, args, prototype, stack_base=...) accepts call values. get_args(state, prototype) returns argument expressions; set_return_val(state, value, type) writes a return value.

## `velnora.calling_conventions.SimRegArg`

SimRegArg(reg_name, size) constructs a location object. reg_name is the register-name string; size is a byte count. get_value(state) returns the value expression at the location. Readable attributes are reg_name and size.

## `velnora.calling_conventions.SimStackArg`

SimStackArg(stack_offset, size) constructs a location object. stack_offset is a byte offset relative to the call-state stack base; size is a byte count. Readable attributes are stack_offset and size.

## `velnora.PointerWrapper`

PointerWrapper(value) accepts a tuple representing a structured argument and supplies an argument object to call_state.

## `velnora.concretization_strategies.SimConcretizationStrategyAny`

SimConcretizationStrategyAny() returns an address-policy object accepted in memory read_strategies and write_strategies.

This is the single-address policy selector.

## `velnora.concretization_strategies.SimConcretizationStrategyRange`

SimConcretizationStrategyRange(limit) accepts an integer byte-span limit and returns an address-policy object accepted in memory read_strategies and write_strategies.

This is the all-address policy selector.

## `velnora.concretization_strategies`

The module exposes SimConcretizationStrategyAny and SimConcretizationStrategyRange.

## `velnora.engines.successors.SimSuccessors`

A successor result exposes flat_successors, unsat_successors, and unconstrained_successors as lists of states.

## `velnora.SimProcedure`

SimProcedure(prototype=..., cc=...) is subclassable. A subclass supplies run(self, *arguments), receives state as self.state, and may return a value expression. NO_RET is a class flag. local_vars names instance attributes retained for a continuation.

execute(state, arguments=...) returns an executed procedure with ret_expr. state.scratch.sim_procedure accepts a procedure object for direct invocation. ret(expression), jump(address), exit(exit_code), and call(address, args, continue_at=..., prototype=...) are callable from run; continue_at names a continuation method on the subclass.

## `velnora.claripy.BVS`

BVS(name, size) returns a bitvector expression; name is str and size is a bit count.

## `velnora.claripy.BVV`

BVV(value, size=...) returns a bitvector expression; value is an integer or bytes and size is a bit count.

## `velnora.claripy.BoolS`

BoolS(name) returns a boolean expression; name is str.

## `velnora.claripy.BoolV`

BoolV(value) returns a boolean expression; value is bool.

## `velnora.claripy.And`

And(*args) returns a boolean expression from boolean-expression arguments.

## `velnora.claripy.Or`

Or(*args) returns a boolean expression from boolean-expression arguments.

## `velnora.claripy.Not`

Not(expression) returns a boolean expression.

## `velnora.claripy.If`

If(condition, then_expression, else_expression) returns an expression; condition is boolean and the two result expressions share a type.

## `velnora.claripy.LShR`

LShR(expression, amount) returns a bitvector expression; amount is an integer or bitvector.

## `velnora.claripy.RotateLeft`

RotateLeft(expression, amount) returns a bitvector expression; amount is a bitvector.

## `velnora.claripy.RotateRight`

RotateRight(expression, amount) returns a bitvector expression; amount is a bitvector.

## `velnora.claripy.Concat`

Concat(*args) returns a bitvector expression from bitvector arguments.

## `velnora.claripy.Extract`

Extract(high, low, expression) returns a bitvector expression; high and low are integer bit positions.

Bit positions count from the least significant bit at zero; high and low are inclusive endpoints.

## `velnora.claripy.Reverse`

Reverse(expression) returns a bitvector expression.

## `velnora.claripy.ZeroExt`

ZeroExt(amount, expression) returns a bitvector expression; amount is an integer bit count.

## `velnora.claripy.SignExt`

SignExt(amount, expression) returns a bitvector expression; amount is an integer bit count.

## `velnora.claripy.StringS`

StringS(name) returns a string expression; name is str.

## `velnora.claripy.StringV`

StringV(value) returns a string expression; value is str.

## `velnora.claripy.StrLen`

StrLen(expression) returns a bitvector expression representing a length.

## `velnora.claripy.StrConcat`

StrConcat(left, right) returns a string expression.

## `velnora.claripy.StrSubstr`

StrSubstr(start, count, expression) returns a string expression; start and count are bitvector expressions.

## `velnora.claripy.StrContains`

StrContains(expression, substring) returns a boolean expression from string expressions.

## `velnora.claripy.StrPrefixOf`

StrPrefixOf(prefix, expression) returns a boolean expression from string expressions.

## `velnora.claripy.StrSuffixOf`

StrSuffixOf(suffix, expression) returns a boolean expression from string expressions.

## `velnora.claripy.FPS`

FPS(name, sort) returns a floating-point expression; name is str and sort is a floating-point sort.

## `velnora.claripy.FPV`

FPV(value, sort) returns a floating-point expression; value is numeric and sort is a floating-point sort.

## `velnora.claripy.SI`

SI(bits=..., lower_bound=..., upper_bound=..., stride=...) returns a bitvector expression representing an abstract integer set; arguments are integers.

## `velnora.claripy`

The claripy namespace exposes BVS, BVV, BoolS, BoolV, And, Or, Not, If, LShR, RotateLeft, RotateRight, Concat, Extract, Reverse, ZeroExt, SignExt, StringS, StringV, StrLen, StrConcat, StrSubstr, StrContains, StrPrefixOf, StrSuffixOf, FPS, FPV, SI, Solver, SolverVSA, vsa, FSORT_FLOAT, FSORT_DOUBLE, and ClaripyError.

## `velnora.claripy.ast.BV`

Bitvector expressions support Python +, -, *, /, //, %, unary -, &, |, ^, ~, <<, >>, ==, !=, <, <=, >, and >=. Arithmetic and bitwise operators return bitvectors; comparisons return boolean expressions. An integer may be supplied as an operand.

Methods SDiv(other), SMod(other), SLT(other), SLE(other), SGT(other), and SGE(other) accept bitvector operands. size() returns the integer bit width; symbolic is bool; concrete_value is a concrete scalar; variables is a collection of symbolic names. zero_extend(amount), get_byte(index), and get_bytes(index, count) return bitvectors. union(other) and intersection(other) return abstract bitvectors.

raw_to_fp() and val_to_fp(sort, signed=...) return floating-point expressions. Invalid expression construction raises claripy.ClaripyError.

get_byte(index) and get_bytes(index, count) index byte portions from the most significant byte at zero.

## `velnora.claripy.ast.FP`

Floating-point expressions support Python +, -, *, /, ==, !=, <, <=, >, and >=. Arithmetic returns floating-point expressions and comparisons return boolean expressions. raw_to_bv() returns a bitvector. to_fp(sort) returns a floating-point expression. val_to_bv(size, signed=...) returns a bitvector; size is a bit count.

## `velnora.claripy.FSORT_FLOAT`

FSORT_FLOAT is the binary32 floating-point sort object accepted by FPS, FPV, to_fp, and val_to_fp.

## `velnora.claripy.FSORT_DOUBLE`

FSORT_DOUBLE is the binary64 floating-point sort object accepted by FPS, FPV, to_fp, and val_to_fp.

## `velnora.claripy.ClaripyError`

ClaripyError is an exception class exposed by claripy.

## `velnora.claripy.Solver`

Solver() constructs an expression solver. add(expressions) accepts a sequence of boolean expressions. eval(expression, n, extra_constraints=...) returns a sequence of Python scalar solutions. batch_eval(expressions, n) returns a list of tuples, with tuple positions corresponding to the supplied expressions. satisfiable(extra_constraints=...) returns bool. branch() returns a solver object. extra_constraints is a sequence of boolean expressions.

## `velnora.claripy.SolverVSA`

SolverVSA() constructs an abstract-value solver. solution(expression, value) returns bool.

## `velnora.claripy.vsa`

vsa.min(expression) and vsa.max(expression) return integer extrema. vsa.eval(expression, n) returns a sequence of integer members of an abstract value.

## `velnora.claripy.ast.Bool`

Boolean expressions support ==, !=, and unary ~, returning boolean expressions.

## `velnora.SimFile`

SimFile(name, content=..., size=..., has_end=...) constructs simulated storage. name is str; content accepts bytes or a bitvector. set_state(state) binds a state. read(pos, size) returns (data, length, position): a bitvector, a length expression, and the next-position expression. write(pos, data) returns the next-position expression. size is the storage-size expression. concretize() returns bytes.

## `velnora.SimFileStream`

SimFileStream(name=..., content=..., has_end=...) constructs a simulated stream accepted as entry_state stdin. name is str, content is bytes, and has_end is bool.

## `velnora.SimPackets`

SimPackets(name) constructs packet storage; name is str. set_state(state) binds a state. read(pos, size, short_reads=...) returns (data, length, position), comprising a bitvector, a length expression, and an integer packet position. write(pos, data) accepts bytes and returns an integer packet position. concretize() returns a list of bytes packets.

## `velnora.SimPacketsStream`

SimPacketsStream(name, content=...) constructs packet-stream storage. name is str; content is a list of bytes packets. set_state(state) binds a state. read(pos, size, short_reads=...) returns (data, length, position), comprising a bitvector, a length expression, and an integer packet position. write(pos, data) accepts bytes and returns an integer packet position. concretize() returns a list of bytes packets.

## `velnora.storage.file.SimFileDescriptor`

A file descriptor exposes read_data(size), returning (data, length) expressions; write_data(data), returning the written-length expression; tell(), returning a position expression; and seek(offset, whence=...), returning a boolean expression. whence uses start, current, or end as position-selector strings. write_storage exposes the outgoing storage.

## `velnora.SimFileDescriptorDuplex`

SimFileDescriptorDuplex(read_file, write_file) constructs a descriptor from incoming and outgoing packet streams. set_state(state) binds a state. read_data(size) returns (data, length) expressions, write_data(data) returns a length expression, and write_storage exposes the outgoing stream.

## `velnora.state_plugins.filesystem.SimFilesystem`

The state fs interface exposes chdir(path), chroot(path), get(path), insert(path, simfile), delete(path), and mount(path, mount). Paths accept bytes or strings. cwd and root are byte-string paths. get returns a simulated file or None; insert and delete return bool.

## `velnora.SimHostFilesystem`

SimHostFilesystem(host_path) accepts a host-directory string and returns a filesystem mount object. set_state(state) binds it to a state.

## `velnora.state_plugins.posix.SimSystemPosix`

The state posix interface exposes open(name, flags), returning a nonnegative file-descriptor expression; get_fd(fd), returning a descriptor object or None; open_socket(ident), returning a descriptor number; and dumps(fd), returning bytes. fd is an assignable descriptor-number-to-object mapping. sockets is an assignable identifier-to-(incoming, outgoing) mapping. ENOENT and ENOTDIR are integer error-code tokens for missing input and a non-directory target, respectively. Standard stream descriptor numbers are 0 for stdin, 1 for stdout, and 2 for stderr.

## `velnora.state_plugins.posix.Flags`

Flags exposes the open-mode token O_RDWR.

## `velnora.state_plugins.posix`

The module exposes Flags, with its O_RDWR open-mode token.

## `velnora.SIM_PROCEDURES`

SIM_PROCEDURES is indexed first by library name and then by procedure name. The selected object is constructed with () and supports execute(state, arguments=[...]). The executed object's ret_expr is the return expression.

The accessed libc entries are memcpy, memmove, memset, memcmp, strlen, strcpy, strcmp, strncmp, malloc, free, and exit. The accessed posix entries are open, read, write, close, chroot, and getenv. The accessed linux_kernel entry is lseek. Arguments use the corresponding native procedure signature and may be integers or expressions; byte buffers are passed by state-memory address. Return values are integer expressions in the native return carrier. The read, write, close, lseek, and chroot failure carrier is -1. close and chroot use 0 as their success status.

The arguments sequence uses these positional forms:

- libc memcpy and memmove: (destination address, source address, byte count).
- libc memset: (destination address, byte value, byte count).
- libc memcmp and strncmp: (left address, right address, byte count).
- libc strcmp: (left address, right address).
- libc strlen: (string address).
- libc strcpy: (destination address, source address).
- libc malloc: (byte count); libc free: (allocation address).
- libc exit: (exit status).
- posix open: (path address, flags, mode).
- posix read: (descriptor, destination address, byte count).
- posix write: (descriptor, source address, byte count).
- posix close: (descriptor).
- posix chroot: (path address); posix getenv: (name address).
- linux_kernel lseek: (descriptor, offset, origin selector).

## `velnora.options`

The options namespace exposes ZERO_FILL_UNCONSTRAINED_MEMORY, ZERO_FILL_UNCONSTRAINED_REGISTERS, STRICT_PAGE_ACCESS, ENABLE_NX, TRACK_MEMORY_ACTIONS, TRACK_REGISTER_ACTIONS, and OPTIMIZE_IR as option tokens, plus refs as an option collection. Tokens are accepted by state option sets and add_options or state_add_options.

## `velnora.options.ZERO_FILL_UNCONSTRAINED_MEMORY`

ZERO_FILL_UNCONSTRAINED_MEMORY is a state-option token.

## `velnora.options.ZERO_FILL_UNCONSTRAINED_REGISTERS`

ZERO_FILL_UNCONSTRAINED_REGISTERS is a state-option token.

## `velnora.options.STRICT_PAGE_ACCESS`

STRICT_PAGE_ACCESS is a state-option token.

## `velnora.options.ENABLE_NX`

ENABLE_NX is a state-option token.

## `velnora.options.TRACK_MEMORY_ACTIONS`

TRACK_MEMORY_ACTIONS is a state-option token.

## `velnora.options.TRACK_REGISTER_ACTIONS`

TRACK_REGISTER_ACTIONS is a state-option token.

## `velnora.options.OPTIMIZE_IR`

OPTIMIZE_IR is a state-option token.

## `velnora.options.refs`

refs is an option collection.

## `velnora.state_plugins.inspect.SimInspector`

The state inspect interface exposes b(event_type, when=..., action=..., condition=..., mem_write_address=...), returning a breakpoint object. action and condition are callables receiving the current state. remove_breakpoint(event_type, bp=...) accepts that object.

Event names are mem_read, mem_write, reg_read, reg_write, instruction, call, return, syscall, exit, constraints, and symbolic_variable. Timing tokens are velnora.BP_BEFORE and velnora.BP_AFTER.

Callbacks read and can assign fields on inspect.attrs. Fields are mem_read_address, mem_read_expr, mem_write_address, mem_write_expr, reg_read_offset, reg_read_expr, reg_write_offset, reg_write_expr, instruction, function_address, syscall_name, exit_target, exit_guard, exit_jumpkind, added_constraints, symbolic_name, symbolic_size, and symbolic_expr. Addresses and values may be concrete scalars or expressions; offsets and sizes are integers; names and transfer kinds are strings; added_constraints is a sequence of boolean expressions.

BP_BEFORE selects observation before the event and BP_AFTER selects observation after it. The call-frame interface is requested with state.get_plugin("callstack").

## `velnora.state_plugins.history.SimStateHistory`

State history exposes bbl_addrs, jump_guards, and jumpkinds as ordered iterables of executed-block addresses, boolean transfer expressions, and string transfer kinds. block_count is an integer executed-block count.

actions is an iterable of records with type, action, addr.ast, and data.ast. type identifies mem or reg, action identifies read or write, and ast holds the address or value expression.

events is an iterable of records with type and objects. A terminate event carries its exit_code expression in objects.

## `velnora.state_plugins.callstack.CallStack`

The state callstack is iterable over frames and exposes the current frame's func_addr, call_site_addr, ret_addr, and stack_ptr. These are the function address, call-site address, return address, and entry stack pointer.

## `velnora.sim_manager.SimulationManager`

The simulation manager exposes stashes, a dictionary from group names to lists of states. Groups are also readable as attributes bearing the group name. Named outcome groups are active, deadended, unsat, unconstrained, found, avoid, deferred, cut, spinning, and traced. Callers may supply their own group names. errored is a list of records exposing state and error.

Methods are step(stash=..., n=..., selector_func=..., filter_func=...), run(n=...), explore(find=..., avoid=..., num_find=..., n=..., avoid_priority=...), move(from_stash=..., to_stash=..., filter_func=...), drop(stash=...), merge(stash=...), populate(stash, states), and use_technique(technique). A selector or filter receives a state; a filter returns a group name. find and avoid accept addresses or state predicates. use_technique accepts an exploration object.

## `velnora.exploration_techniques.DFS`

DFS() constructs an exploration object accepted by use_technique.

## `velnora.exploration_techniques.LengthLimiter`

LengthLimiter(max_length=..., drop=...) constructs an exploration object accepted by use_technique.

## `velnora.exploration_techniques.LoopSeer`

LoopSeer(cfg=..., functions=..., bound=..., use_header=...) constructs an exploration object accepted by use_technique.

use_header selects entry-visit counting when true and loop-continuation counting when false.

## `velnora.exploration_techniques.Tracer`

Tracer(trace=..., fast_forward_to_entry=..., aslr=...) constructs an exploration object accepted by use_technique. trace is an address sequence. A trace mismatch raises TracerDesyncError.

## `velnora.exploration_techniques`

The namespace exposes DFS, LengthLimiter, LoopSeer, and Tracer.

## `velnora.exploration_techniques.tracer.TracerDesyncError`

TracerDesyncError is the Python exception class for trace mismatch.

## `velnora.exploration_techniques.tracer`

The module exposes TracerDesyncError.

## `velnora.block.Block`

An instruction block exposes addr, size, bytes, instruction_addrs, capstone, disassembly, and vex. addr and instruction_addrs are native integer addresses, size is a byte count, and bytes is the decoded byte string. capstone.insns and disassembly.insns are instruction sequences.

Instruction wrappers expose address, size, mnemonic, op_str, and insn. insn exposes mnemonic, operands, and reg_name(register_id). Each operand has type plus reg for a register operand or imm for an immediate operand. The operand tags are capstone.CS_OP_REG and capstone.CS_OP_IMM.

## `velnora.block.SootBlock`

A Java block exposes addr as a SootAddressDescriptor, size as a statement count, and soot.statements as the addressed block's statement sequence.

Statement class names include IdentityStmt, AssignStmt, and ReturnStmt. IdentityStmt and AssignStmt expose left_op and right_op. ReturnStmt exposes value. SootBinopExpr exposes op, value1, and value2; op is an operation-name string, including add. SootParamRef exposes index. Integer constants expose value. Local-value objects support equality comparison.

## `velnora.block.Block.vex`

The vex result exposes statements, tyenv, jumpkind, next, and exit_statements. jumpkind is a transfer-kind string with tokens Ijk_Boring, Ijk_Call, Ijk_Ret, and Ijk_Sys_syscall. Constant continuations expose next.con.value.

VEX statement objects have tag. Tag-specific fields are: Ist_WrTmp has tmp and data; Ist_Put has offset and data; Ist_Store has addr, data, and end; Ist_Exit has guard and dst.value. Instruction and annotation statement tags include Ist_IMark, Ist_NoOp, and Ist_AbiHint.

Expressions have tag and result_size(tyenv), returning a bit count. Fields are con.value for Iex_Const, tmp for Iex_RdTmp, offset for Iex_Get, cond/iftrue/iffalse for Iex_ITE, addr/end for Iex_Load, and op/args for Iex_Unop and Iex_Binop. end is Iend_LE or Iend_BE. op is a string beginning Iop_, followed by the operation and width notation. Integer operation spellings include Add, Sub, CmpEQ, CmpNE, And, Xor, Or, Shr, and conversions in the form <source width><U or S when present>to<destination width>.

## `velnora.engines.pcode.lifter.IRSB`

The P-Code block representation is obtained through Block.vex. It exposes jumpkind, next.con.value, and exit_statements. str() contains numbered operation lines in the form <decimal index> | <operation>. Instruction-marker operations begin with ------.

Operand forms are register names, hexadecimal constants with 0x, and temporaries unique[<hexadecimal identifier>:<byte width>]. Assignments use <operand> = <expression>. Memory operands use *[ram]<address operand>. Expression forms include zext(<operand>), <operand> + <operand>, <operand> == <operand>, and <operand> != <operand>. Control forms include if (<operand>) goto ram[<hexadecimal address>:<byte width>], call ram[<hexadecimal address>:<byte width>], return <operand>, and syscall().

## `velnora.engines.UberEnginePcode`

UberEnginePcode is accepted as the engine argument to load_shellcode.

## `archinfo.arch_soot`

The module exposes SootMethodDescriptor, SootAddressDescriptor, SootAddressTerminator, and SootArgument.

## `archinfo.arch_soot.SootMethodDescriptor`

SootMethodDescriptor.from_string(signature) accepts a qualified method signature string. from_soot_method(method) accepts a loaded Java method object. Both return method descriptors supporting equality. address() returns a SootAddressDescriptor.

## `archinfo.arch_soot.SootAddressDescriptor`

SootAddressDescriptor(method, block_idx, stmt_idx) accepts a method descriptor and integer block and statement positions. Attributes method, block_idx, and stmt_idx expose those components. Descriptors support equality.

## `archinfo.arch_soot.SootAddressTerminator`

SootAddressTerminator() constructs a Java return-address object accepted as call_state ret_addr.

## `archinfo.arch_soot.SootArgument`

SootArgument(value, type) accepts an expression and Java type-name string as a typed argument to call_state.

## `velnora.engines.soot.values.SimSootValue_StaticFieldRef`

SimSootValue_StaticFieldRef(class_name, field_name, type_) constructs a Java memory reference accepted by state.memory.load.

## `velnora.engines.soot.values.SimSootValue_ArrayRef`

SimSootValue_ArrayRef(base, index) constructs a Java memory reference accepted by state.memory.load.

## `velnora.engines.soot.values`

The module exposes SimSootValue_StaticFieldRef and SimSootValue_ArrayRef.

## `velnora.analyses`

The project analyses namespace exposes CFGFast, CFGEmulated, CFGFastSoot, LanguageDetector, Flirt, Identifier, VariableRecoveryFast, CallingConvention, CompleteCallingConventions, Typehoon, ReachingDefinitions, Propagator, DDG, CDG, BackwardSlice, VFG, Decompiler, BinDiff, Reassembler, RustSymbolRecovery, and TypeDBLoader.

Each named analysis is callable on project.analyses. Analysis construction accepts kb=... to select a KnowledgeBase. Indexed access project.analyses[velnora.analyses.Decompiler].prep(fail_fast=...)(...) is also available.

## `velnora.analyses.CFGFast`

CFGFast(regions=..., function_starts=..., symbols=..., start_at_entry=..., function_prologues=..., force_smart_scan=..., force_complete_scan=..., retedges=..., normalize=..., detect_tail_calls=..., data_references=..., cross_references=..., kb=...) is called through project.analyses. regions is a sequence of (start, end) integer-address pairs; function_starts is an address collection. Selection flags are bool.

The result exposes model, kb, functions, regions, jump_tables, and indirect_jumps. functions is a function manager. jump_tables and indirect_jumps are address-indexed mappings of transfer records with jumptable_addr, jumptable_entries, and resolved_targets. These carry a table address and address collections.

## `velnora.analyses.CFGEmulated`

CFGEmulated(initial_state=..., starts=..., call_depth=..., context_sensitivity_level=..., keep_state=..., state_add_options=..., max_iterations=...) is called through project.analyses. starts is an address list; state_add_options is an option collection; depth and count parameters are integers. The result exposes model and kb.

## `velnora.analyses.CFGFastSoot`

CFGFastSoot() is called through project.analyses and returns a result with model and kb.

## `velnora.knowledge_plugins.cfg.CFGModel`

A control-flow model exposes graph and memory_data. graph is a directed graph supporting iteration, nodes, edges(data=True), out_edges(node, data=True), successors(node), and predecessors(node). An edge's jumpkind is a string transfer kind. Node objects expose addr, size, function_address, input_state, and final_states; these are block address, byte extent, owning-function address, saved input state, and saved result-state sequence. Java addresses use method descriptors.

get_any_node(addr, anyaddr=...) returns a node or None. get_all_nodes(addr) returns a node collection. get_predecessors(node) and get_successors(node) return node collections. memory_data is address-indexed; its content is bytes.

serialize() returns bytes; CFGModel.parse(serialized) returns a model.

## `velnora.knowledge_plugins.cfg`

The module exposes CFGModel with its parse(serialized) class method.

## `velnora.KnowledgeBase`

KnowledgeBase(project) constructs an analysis-knowledge object. A project's kb exposes functions, callgraph, cfgs, unresolved_indirect_jumps, xrefs, labels, comments, bookmarks, patches, variables, dvars, and decompilations. cfgs supports indexing by CFGFast and get_most_accurate(), returning a control-flow model. callgraph is a directed graph over function addresses. unresolved_indirect_jumps is a collection of addresses. decompilations is indexed by (function address, flavor), yielding an object with codegen.

## `velnora.knowledge_plugins.functions.FunctionManager`

The functions manager supports indexing by integer address or function-name string, length, and values(). function(name=...) returns a function or None; floor_func(address) returns a function object. callgraph is a directed graph with successors(address), predecessors(address), and edges.

## `velnora.knowledge_plugins.functions.Function`

Function fields are addr, name, size, returning, is_syscall, is_plt, prototype, calling_convention, transition_graph, ret_sites, and block_addrs_set. name, prototype, and calling_convention are assignable. Address-set attributes contain block addresses; ret_sites contains objects with addr.

get_call_sites() returns call-site addresses; get_call_target(callsite_addr) and get_call_return(callsite_addr) return the corresponding destination and continuation addresses. transition_graph is directed, with endpoint objects exposing addr and edge dictionaries exposing type. Transition-kind tokens include call, fake_return, and transition.

## `velnora.knowledge_plugins.patches.PatchManager`

kb.patches exposes add_patch(addr, new_bytes), get_patch(addr), remove_patch(addr), apply_patches_to_state(state), and apply_patches_to_binary(). new_bytes is bytes; get_patch returns a patch with new_bytes or None; apply_patches_to_binary returns the complete binary as bytes.

## `velnora.knowledge_plugins.xrefs.XRefManager`

kb.xrefs.get_xrefs_by_dst(address) and get_xrefs_by_ins_addr(address) return reference collections. Each reference exposes ins_addr and dst as instruction and destination integer addresses.

## `velnora.knowledge_plugins.labels.Labels`

kb.labels supports address indexing, assignment of string labels, and lookup(name), returning an address or None.

## `velnora.knowledge_plugins.comments.Comments`

kb.comments supports address indexing, string assignment, deletion, and membership queries. set_kind(addr, kind) and kind_of(addr) exchange CommentKind values.

## `velnora.knowledge_plugins.bookmarks.Bookmarks`

kb.bookmarks.add_bookmark(addr, label) accepts an address and string label and returns a tuple whose first item is a bookmark. get_bookmark(addr) returns a bookmark or None. remove_bookmark(bookmark) accepts a bookmark. Bookmarks expose addr and a writable label.

## `velnora.knowledge_plugins.CommentKind`

CommentKind exposes the comment-kind member REPEATABLE.

## `velnora.knowledge_plugins`

The module exposes CommentKind.

## `velnora.analyses.LanguageDetector`

LanguageDetector() is called through project.analyses. The result exposes language as one of the strings c, rust, go, swift, or unknown and evidence as a string collection. Compilation-unit evidence carries the label dwarf_language: followed by the unit's language identifier.

## `velnora.analyses.Flirt`

Flirt(sig) accepts a local signature-file path string through project.analyses. The result's matched_suggestions is a mapping whose values are pairs containing signature metadata and an address-to-name dictionary. Assigned names are readable through the function manager.

## `velnora.analyses.Identifier`

Identifier(cfg=..., require_predecessors=..., only_find=...) is called through project.analyses. only_find is a set of operation-name strings: memcmp, strcmp, strncmp, and strcasecmp. run() returns an iterable of (function address, operation name) pairs.

require_predecessors selects the restriction to functions with known callers.

## `velnora.analyses.VariableRecoveryFast`

VariableRecoveryFast(function) is called through project.analyses. The result exposes type_constraints, func_typevar, and var_to_typevars as type-inference inputs. Recovered variable information is available through kb.variables[function.addr].

## `velnora.knowledge_plugins.variables.VariableManagerInternal`

The function-address-indexed variable manager exposes find_variables_by_insn(ins_addr, sort), returning (variable, offset) pairs. sort uses memory or register. get_variable_accesses(variable) returns records with location.ins_addr and access_type. get_variables() returns a variable collection.

Variables expose name, size in bytes, and their location: offset for stack variables or reg for register variables. name is assignable. get_variable_type(variable) returns a type object. set_variable_type(variable, type, mark_manual=...) accepts a type object and boolean manual-type flag.

## `velnora.sim_variable.SimStackVariable`

SimStackVariable identifies stack-variable objects exposing offset as a stack-relative byte offset, size in bytes, and name.

## `velnora.sim_variable`

The module exposes SimStackVariable.

## `velnora.knowledge_plugins.variables.variable_access.VariableAccessSort`

VariableAccessSort exposes READ, WRITE, and REFERENCE as variable-access-kind tokens.

## `velnora.knowledge_plugins.variables.variable_access`

The module exposes VariableAccessSort, including READ, WRITE, and REFERENCE.

## `velnora.analyses.CallingConvention`

CallingConvention(function, cfg=...) is called through project.analyses. The result exposes cc as a convention object and prototype as a function-type object.

## `velnora.analyses.CompleteCallingConventions`

CompleteCallingConventions(recover_variables=..., analyze_callsites=..., prioritize_func_addrs=..., skip_other_funcs=...) is called through project.analyses. Function-address priorities accept an address collection; the remaining named arguments are boolean. Results are inspected through function prototype and calling_convention attributes.

## `velnora.analyses.Typehoon`

Typehoon(constraints, func_var, var_mapping=...) is called through project.analyses. constraints is a dictionary from type variables to sets of constraints; var_mapping maps variables to type-variable sets. simtypes_solution maps type variables to type objects. update_variable_types(func_addr, var_to_typevars) accepts a function address and variable-to-type-variable mapping.

## `velnora.analyses.typehoon.typevars.TypeVariable`

TypeVariable() constructs a hashable type-constraint value.

## `velnora.analyses.typehoon.typevars.DerivedTypeVariable`

DerivedTypeVariable(type_var, label, labels=...) constructs a hashable type-constraint value. labels is a sequence of label values.

## `velnora.analyses.typehoon.typevars.Subtype`

Subtype(sub_type, super_type) constructs a hashable type-constraint value.

## `velnora.analyses.typehoon.typevars.Load`

Load() constructs a hashable type-constraint value.

## `velnora.analyses.typehoon.typevars.Store`

Store() constructs a hashable type-constraint value.

## `velnora.analyses.typehoon.typevars.HasField`

HasField(bits, offset) constructs a hashable field-access constraint value. bits is the field width in bits; offset is its byte displacement within the pointed-to object.

## `velnora.analyses.typehoon.typevars`

The module exposes TypeVariable, DerivedTypeVariable, Subtype, Load, Store, HasField.

## `velnora.analyses.typehoon.typeconsts.Int8`

Int8() constructs a scalar type-constraint value.

## `velnora.analyses.typehoon.typeconsts.Int32`

Int32() constructs a scalar type-constraint value.

## `velnora.analyses.typehoon.typeconsts.Int64`

Int64() constructs a scalar type-constraint value.

## `velnora.analyses.typehoon.typeconsts`

The module exposes Int8, Int32, and Int64.

## `velnora.state_plugins.debug_variables.SimDebugVariablePlugin`

kb.dvars.load_from_dwarf() loads debug-variable information. State dvars[name] returns a variable view exposing addr and mem. addr is an address expression; mem is a typed memory view. deref returns a pointed-to variable view, member(name) returns a member view, and array(index) returns an array-element view.

## `velnora.analyses.ReachingDefinitions`

ReachingDefinitions(subject=..., observe_all=..., dep_graph=...) is called through project.analyses with a function subject and boolean flags. observed_results is indexed by ('insn', instruction address, OP_BEFORE) and yields a live-definition view. all_uses exposes get_uses_by_insaddr(address), returning a definition set, and get_uses(definition), returning code locations with ins_addr. dep_graph exposes graph and find_all_predecessors(definition), returning definitions.

Definitions expose codeloc.ins_addr and atom. Register atoms have reg_offset. Dependency graph nodes are definition objects.

## `velnora.knowledge_plugins.key_definitions.live_definitions.LiveDefinitions`

Live-definition views expose get_register_definitions(reg_offset, size), get_stack_definitions(stack_offset, size), and get_memory_definitions(addr, size). Each returns a set of definition objects. Sizes and location offsets are measured in bytes.
 The method-name form combines get_, a kind of register, stack, or memory, and _definitions.

## `velnora.knowledge_plugins.key_definitions.atoms.Register`

Register identifies register-definition atom objects exposing reg_offset as a register byte offset.

## `velnora.knowledge_plugins.key_definitions.atoms`

The module exposes Register.

## `velnora.knowledge_plugins.key_definitions.constants.OP_BEFORE`

OP_BEFORE is the observation-position token used in reaching-definition observation keys.

## `velnora.knowledge_plugins.key_definitions.constants`

The module exposes OP_BEFORE.

## `velnora.analyses.Propagator`

Propagator(func=..., only_consts=...) is called through project.analyses. replacements is a mapping from code locations to dictionaries mapping operand objects to value expressions. Code locations expose ins_addr; value expressions expose concrete_value.

## `velnora.analyses.propagator.vex_vars.VEXReg`

VEXReg(offset, size) constructs an operand key supporting equality. Location and size arguments are byte offsets or addresses and byte counts.

## `velnora.analyses.propagator.vex_vars.VEXMemVar`

VEXMemVar(addr, size) constructs an operand key supporting equality. Location and size arguments are byte offsets or addresses and byte counts.

## `velnora.analyses.propagator.vex_vars`

The module exposes VEXReg and VEXMemVar.

## `velnora.analyses.DDG`

DDG(cfg, start=...) is called through project.analyses. graph is a directed graph whose nodes expose ins_addr. Edge dictionaries have type and may have subtype, a collection of dependency-kind tokens. Memory dependency tokens are mem, mem_addr, and mem_data.

## `velnora.analyses.CDG`

CDG(cfg, start=...) is called through project.analyses. graph is a directed graph whose endpoint nodes expose addr.

## `velnora.analyses.BackwardSlice`

BackwardSlice(cfg, cdg, ddg, targets=..., control_flow_slice=...) is called through project.analyses. targets is a sequence of (control-flow node, statement selector) pairs. runs_in_slice is a directed graph of integer block addresses. annotated_cfg() returns an object exposing get_whitelisted_statements(address), returning None for all statements or a list of included statement indices; an empty list denotes no included statements.

## `velnora.analyses.VFG`

VFG(cfg, start=..., function_start=..., initial_state=..., interfunction_level=..., context_sensitivity_level=..., record_function_final_states=..., max_iterations_before_widening=..., max_iterations=...) is called through project.analyses. graph has nodes exposing addr; get_any_node(address) returns a node or None. Nodes expose final_states as a state sequence. function_final_states maps a function address to a mapping whose values are result states.

max_iterations and max_iterations_before_widening are the caller-supplied iteration and precision budgets, respectively; both are integer counts.

## `velnora.analyses.Decompiler`

Decompiler(func, cfg=..., flavor=..., regen_clinic=..., use_cache=..., options=...) is called through project.analyses. func accepts a recovered function object, name, or address; cfg accepts a control-flow model. options is a sequence of (option name, value) pairs; the accessed option name is max_function_blocks with an integer value. Flavor tokens are pseudocode, rust, and go.

The result exposes codegen, errors, and complexity_error. codegen is a code-generation object or None. complexity_error is None or an error carrying limit_name as a string, limit as the selected integer bound, and actual as the measured count. The block-count limit label is max_function_blocks.

## `velnora.analyses.decompiler.edits`

The module exposes rename_function, rename_variable, rename_global, set_variable_type, set_function_prototype, set_comment, require_cache, resolve_variable, and list_variable_names. Exception exports are InvalidNameError, NameCollisionError, NotDecompiledError, TypeParseError, UnsupportedEditError, and VariableNotFoundError.

## `velnora.analyses.decompiler.edits.rename_function`

rename_function(project, func, new_name, allow_overwrite=..., strict_names=...). func is a recovered function object; new_name is str; allow_overwrite and strict_names are bool. Returns an edit result with changed: bool. changed reports whether the edit changed the target.

strict_names selects strict name validation when true and relaxed validation when false. allow_overwrite permits name collisions when true.

## `velnora.analyses.decompiler.edits.rename_variable`

rename_variable(project, func, variable_name, new_name, allow_overwrite=..., strict_names=...). func is a recovered function object; new_name is str; variable_name is the displayed variable-name string; allow_overwrite and strict_names are bool. Returns an edit result with changed: bool. changed reports whether the edit changed the target.

strict_names selects strict name validation when true and relaxed validation when false. allow_overwrite permits name collisions when true.

## `velnora.analyses.decompiler.edits.rename_global`

rename_global(project, addr, new_name). addr is an integer address; new_name is str. Returns an edit result with changed: bool. changed reports whether the edit changed the target.

## `velnora.analyses.decompiler.edits.set_variable_type`

set_variable_type(project, func, variable_name, c_type). func is a recovered function object; variable_name is the displayed variable-name string; c_type is a C type string or type object.

## `velnora.analyses.decompiler.edits.set_function_prototype`

set_function_prototype(project, func, prototype, redecompile=...). func is a recovered function object; prototype is a C prototype string or function-type object; redecompile is bool.

## `velnora.analyses.decompiler.edits.set_comment`

set_comment(project, addr, comment). addr is an integer address; comment is str.

## `velnora.analyses.decompiler.edits.require_cache`

require_cache(kb, func_addr) returns an object with codegen. kb is a KnowledgeBase and func_addr is an integer function address.

## `velnora.analyses.decompiler.edits.list_variable_names`

list_variable_names(codegen, kb, func_addr) returns an iterable of displayed variable-name strings.

## `velnora.analyses.decompiler.edits.resolve_variable`

resolve_variable(kb, func_addr, display_name) returns a resolved variable exposing kind, name, arg_index, and unified. kind is a string such as argument or local; name is the displayed name; arg_index is an integer argument position or None; unified is a variable object or None.

## `velnora.analyses.decompiler.edits.InvalidNameError`

InvalidNameError is the Python exception class identifying an invalid-name failure.

## `velnora.analyses.decompiler.edits.NameCollisionError`

NameCollisionError is the Python exception class identifying a name-collision failure.

## `velnora.analyses.decompiler.edits.NotDecompiledError`

NotDecompiledError is the Python exception class identifying an unavailable-decompilation failure.

## `velnora.analyses.decompiler.edits.TypeParseError`

TypeParseError is the Python exception class identifying an invalid-type-description failure.

## `velnora.analyses.decompiler.edits.UnsupportedEditError`

UnsupportedEditError is the Python exception class identifying an unsupported-edit failure.

## `velnora.analyses.decompiler.edits.VariableNotFoundError`

VariableNotFoundError is the Python exception class identifying an unresolved-variable failure.

## `velnora.decompile`

### Invocation

python -m velnora decompile <binary path> --no-colors --functions <selection> [<selection> ...] [--catch-exceptions]

Selections are function-name strings or hexadecimal address strings. Raw-image invocation adds --blob --arch <architecture> --base-addr <address> --entry-point <address>.

### Output

stdout carries C-like source text containing the selected function definitions. --no-colors requests text without terminal coloring. stderr carries diagnostics. An unknown-function diagnostic carries the requested selection; an uncaught ValueError is identified by the label ValueError:. A complexity diagnostic carries the function selection and the limit label max_function_blocks. An argument-error line contains the label error: and the relevant option names, including --blob and the missing option.

Exit status 0 signals completed command handling, including enabled per-function error handling. Status 1 signals a failed decompilation command. Status 2 signals an invalid command-line request. Output is UTF-8 text.

## `velnora.analyses.BinDiff`

BinDiff(other_project, cfg_a=..., cfg_b=...) is called through project.analyses with another project and two control-flow models. Results expose cfg_a, cfg_b, function_matches, unmatched_functions, identical_functions, and differing_functions. Function-pair collections contain (left address, right address) tuples. unmatched_functions is (left address set, right address set). get_function_diff(left_address, right_address) returns a function-comparison object.

## `velnora.analyses.bindiff.FunctionDiff`

A function-comparison object exposes block_matches, identical_blocks, and differing_blocks as collections of (left block, right block) pairs. Each block has addr.

## `velnora.analyses.Reassembler`

Reassembler(syntax=...) is called through project.analyses. syntax selects at&t or intel assembly notation. symbolize() is callable on the result. assembly(symbolized=...) returns GNU assembler source as str. The source contains named procedure and data definitions and symbolic references.

insert_asm(addr, asm_code), remove_instruction(ins_addr), append_procedure(name, asm_code), and append_data(name, initial_content, size, readonly=...) accept integer instruction addresses, assembly strings, symbol-name strings, initial bytes, integer byte sizes, and a boolean readonly flag.

## `velnora.velnoradb.VelnoraDB`

VelnoraDB(project, nullpool=...) or VelnoraDB(nullpool=...) constructs a persistence interface; nullpool is bool. dump(db_path) writes a project database to the supplied path string. load(db_path) reads that database and returns a Project. The database is exchanged through these methods as a binary file.

## `velnora.velnoradb`

The module exposes VelnoraDB.

## `velnora.KnowledgeBaseSnapshot`

KnowledgeBaseSnapshot(kb, included_plugins=...) accepts a knowledge base and an optional iterable of component-name strings. restore() is a zero-argument method. The named component selectors are comments and variables.

## `velnora.analyses.RustSymbolRecovery`

RustSymbolRecovery() is callable through project.analyses.

## `velnora.analyses.TypeDBLoader`

TypeDBLoader() is callable through project.analyses.

## `velnora.flirt_signatures`

XDG_CACHE_HOME selects the cache root. Local Rust signatures reside beneath velnora/flirt_signatures/x86_64/linux/rust/inline/, named <compiler version>-O<optimization>.sig. The velnora/flirt_signatures directory contains the marker .download_complete. Signature files use the binary FLIRT .sig format.

## `velnora.mcp`

### Server invocation

python -m velnora.mcp starts a local MCP server. --transport <transport>, --host <host>, and --port <integer> select the listener interface. Transport names exchanged by callers are stdio, sse, and http. The SSE endpoint path is /sse; the HTTP endpoint path is /mcp. Standard-input/output transport exchanges MCP messages on stdin and stdout; diagnostics use stderr. Protocol text uses UTF-8.

### Tool envelope

MCP tool calls use a tool-name string and an argument object. A successful result has isError false and structuredContent containing the tool's result object. A refused call has isError true. The content field is a sequence of blocks with type and text; text blocks use type text. Function-selection failures carry the submitted selection in the diagnostic text.

Native addresses in result objects use hexadecimal strings with the prefix 0x. project_id is an opaque session-identifier string.

## `load_binary`

MCP tool load_binary(binary_path, auto_load_libs=..., backend=..., arch=...). binary_path is a local path string, auto_load_libs is bool, and backend and arch are selector strings. The result has project_id: str, entry_point: hexadecimal address string, arch: architecture-name string, and bits: integer bit width.

## `list_projects`

MCP tool list_projects(). The result has count: integer and projects: list of objects. Each object has project_id: str, binary_path: absolute path string, and has_cfg: bool indicating analysis availability.

## `close_project`

MCP tool close_project(project_id). The result has closed: bool indicating session closure.

## `get_cfg`

MCP tool get_cfg(project_id, data_references=...). data_references is bool. The result has status: "success" for a completed request.

## `recover_calling_conventions`

MCP tool recover_calling_conventions(project_id). Success is exposed through the common isError envelope.

## `get_function_info`

MCP tool get_function_info(project_id, name=..., address=..., include_blocks=...). name is str, address is a hexadecimal address string, and include_blocks is bool. The result has address: hexadecimal address string, name: str, is_simprocedure: bool identifying a modeled function, size: byte count, num_blocks: integer block count, block_addresses: list of hexadecimal address strings, calling_convention: an angle-bracketed convention-class name, and prototype: a string of the form (<argument types>) -> <return type>. block_addresses accompanies an include_blocks request.

## `list_functions`

MCP tool list_functions(project_id, limit=..., offset=..., name_pattern=..., filter_plt=..., filter_syscall=...). limit and offset are integers, name_pattern is str, and the category selectors are bool. The result has total: integer match count, offset: integer, limit: integer, and functions: list of objects with address: hexadecimal address string, name: str, is_plt: bool, and is_syscall: bool.

For filter_plt and filter_syscall, true selects members of that category and false selects nonmembers; omission leaves that category unfiltered.

## `find_functions_by_pattern`

MCP tool find_functions_by_pattern(project_id, pattern, search_type=...). pattern is str; search_type uses contains, startswith, endswith, or regex. The result has search_type: search-mode string, count: integer match count, and functions: list of objects with name: str.

## `get_basic_blocks`

MCP tool get_basic_blocks(project_id, function_address). function_address is a hexadecimal address string. The result has block_count: integer and blocks: list of objects. Each block has instructions: list of objects with address: hexadecimal address string, bytes: hexadecimal byte encoding, and mnemonic: instruction-name string.

## `get_imports`

MCP tool get_imports(project_id). The result has imports: list of objects with name: symbol-name string.

## `get_exports`

MCP tool get_exports(project_id). The result has exports: list of objects with name: symbol-name string and address: hexadecimal address string.

## `get_xrefs`

MCP tool get_xrefs(project_id, address, direction). address is a hexadecimal address string; direction uses to or from. The result has xrefs: list of objects with from_address: instruction-address string and to_address: referenced-address string, both hexadecimal.

## `get_callgraph`

MCP tool get_callgraph(project_id). The result has nodes: list of objects with address: hexadecimal function address, and edges: list of objects with from and to as hexadecimal caller and callee addresses.

## `get_strings`

MCP tool get_strings(project_id, limit=..., min_length=...). limit and min_length are integer counts. The result has count: integer and strings: list of objects with address: hexadecimal address string and content: decoded string.

## `get_decompilation_flavor`

MCP tool get_decompilation_flavor(project_id). The result has flavor: output-language identifier string.

## `set_decompilation_flavor`

MCP tool set_decompilation_flavor(project_id, flavor). flavor is an output-language identifier string. Success is exposed through the common isError envelope.

## `decompile_function`

MCP tool decompile_function(project_id, name=..., address=..., flavor=...). name is str and address is a hexadecimal string. flavor is an output-language identifier. The result has flavor: selected language identifier and code: source-text string. Flavor spellings are pseudocode, rust, and go. Source text uses C, Rust, or Go notation respectively.

## `rename`

MCP tool rename(project_id, items, dry_run=..., stop_on_error=..., allow_overwrite=..., auto_decompile=...). project_id is str, items is a list of objects, and option flags are bool. Each item has kind and new_name. A function item has kind function and a name or address. A variable item has kind variable, function identifying its function, and name identifying its displayed variable.
The result has total, succeeded, unchanged, failed, and skipped as integer item counts, and results as an item-result list. Each item result has index, its zero-based input position, and status, one of ok, unchanged, error, or skipped. succeeded counts ok results, unchanged counts unchanged results, failed counts error results, and skipped counts skipped results.
Item results also expose target as the selected target string, function_address as the resolved hexadecimal function address or null, and error_kind as a failure-category string. Failure-category spellings are NameCollisionError, FunctionNotFoundError, InvalidArgumentError, and AmbiguousFunctionError.

## `set_type`

MCP tool set_type(project_id, items, dry_run=..., redecompile=...). project_id is str, items is a list of objects, and option flags are bool. Each item has kind and type, a C declaration string. A function item has kind function and name. A variable item has kind variable, function identifying its function, and name identifying its displayed variable.
The result has total, succeeded, unchanged, failed, and skipped as integer item counts, and results as an item-result list. Each item result has index, its zero-based input position, and status, one of ok, unchanged, error, or skipped. succeeded counts ok results, unchanged counts unchanged results, failed counts error results, and skipped counts skipped results.
Item results expose function_address as the resolved hexadecimal function address or null.

## `set_comments`

MCP tool set_comments(project_id, items, dry_run=...). project_id is str, items is a list of objects, and option flags are bool. Each item has kind function, function identifying the target, and comment containing a string.
The result has total, succeeded, unchanged, failed, and skipped as integer item counts, and results as an item-result list. Each item result has index, its zero-based input position, and status, one of ok, unchanged, error, or skipped. succeeded counts ok results, unchanged counts unchanged results, failed counts error results, and skipped counts skipped results.

## `velnora.analyses.decompiler.structured_codegen.base.BaseStructuredCodeGenerator`

The code-generation object exposes text as source text, flavor as a language token, and writable stmt_comments as a mapping from instruction addresses to comment strings.

The pseudocode text uses C declarations and function definitions, with expressions and statements in C syntax. Rust text uses fn <name>(<name>: <type>, ...) -> <type> { <statements> }, typed let declarations, reference notation &, aggregate fields <field>: <value>, constructors such as Some(...) and Ok(...), and format!(<format string>, <arguments>). Go text uses func <name>(<name> <type>, ...) <result type> { <statements> }, optional parenthesized receivers, var declarations or := assignment, slices []<element type>{<values>}, and parenthesized comma-separated result types for multiple results. Return statements with multiple results use comma-separated expressions. Quoted literals use escaped string or character notation; comments use // or /* ... */.

map_addr_to_pos.items() exposes address-to-position entries; get_nearest_pos(address) returns a character position or None. map_pos_to_addr.items() yields (character position, element) pairs; each element has start as a character position and obj.tags['ins_addr'] as the originating instruction address.

## `velnora.errors.VelnoraValueError`

VelnoraValueError is the Python exception class for an invalid-value failure.

## `velnora.errors.VelnoraCallableError`

VelnoraCallableError is the Python exception class for a function-invocation failure.

## `velnora.errors.VelnoraCallableMultistateError`

VelnoraCallableMultistateError is the Python exception class for a multiple-result-state invocation failure. It is a subclass of VelnoraCallableError.

## `velnora.errors.SimSegfaultException`

SimSegfaultException is the Python exception class for a memory-access failure.

## `velnora.errors.SimValueError`

SimValueError is the Python exception class for a solution-cardinality failure.

## `velnora.errors.SimUnsatError`

SimUnsatError is the Python exception class for an unsatisfiable-evaluation failure.

## `velnora.errors.SimEngineError`

SimEngineError is the Python exception class for an execution-engine failure.

## `velnora.errors.SimIRSBNoDecodeError`

SimIRSBNoDecodeError is the Python exception class for an instruction-decoding execution failure.

## `velnora.errors.SimTranslationError`

SimTranslationError is the Python exception class for an instruction-translation failure.

## `velnora.errors`

The errors module exposes VelnoraValueError, VelnoraCallableError, VelnoraCallableMultistateError, SimSegfaultException, SimValueError, SimUnsatError, SimEngineError, SimIRSBNoDecodeError, and SimTranslationError as Python exception classes.

## `cle`

The cle namespace exposes CLEError and CLEFileNotFoundError as Python exception classes.

## `cle.CLEError`

CLEError is the Python exception class used for a loading failure caused by missing architecture information.

## `cle.CLEFileNotFoundError`

CLEFileNotFoundError is the Python exception class for an unavailable loading dependency.

## `capstone`

The capstone namespace exposes CS_OP_REG and CS_OP_IMM as operand-type tokens.

## `capstone.CS_OP_REG`

CS_OP_REG is the operand-type token for a register operand, whose reg field carries a register identifier.

## `capstone.CS_OP_IMM`

CS_OP_IMM is the operand-type token for an immediate operand, whose imm field carries an integer value.

## `velnora.claripy.ast.String`

String expressions support Python == with another string expression, returning a boolean expression.

## `velnora.engines`

The engines namespace exposes UberEnginePcode as an execution-engine class accepted by the engine argument.

## `pycparser`

Local Python parsing utilities are provided by pycparser. c_parser.CParser().parse(source) accepts C source text and returns a syntax tree with ext. Invalid syntax raises c_parser.ParseError. The c_ast namespace supplies syntax node classes ArrayRef, Assignment, BinaryOp, Break, Cast, Compound, Constant, Continue, Decl, DeclList, DoWhile, EmptyStatement, ExprList, For, FuncCall, FuncDef, Goto, ID, Label, PtrDecl, Return, Switch, TernaryOp, Typename, UnaryOp, and While. Nodes support children() yielding (field_name, node) pairs. Their public syntax fields are name, type, op, value, left, right, cond, iftrue, iffalse, expr, exprs, args, decl, body, block_items, init, next, stmt, decls, params, lvalue, rvalue, subscript, and names, as applicable to the node kind.

## `z3`

Local IEEE floating-point utilities are provided by z3. Float32() and Float64() return floating-point sort objects. FPVal(value, sort) constructs a floating-point value. RNE() supplies a rounding-mode token. fpAdd(rounding, left, right), fpSub(rounding, left, right), fpMul(rounding, left, right), and fpDiv(rounding, left, right) return floating-point expressions. fpToIEEEBV(expression) returns a bitvector expression. simplify(expression) returns an expression whose as_long() method returns an integer for a concrete bitvector.

## `networkx`

Local graph utilities are provided by networkx. ancestors(graph, node) and descendants(graph, node) return sets of nodes. single_source_shortest_path_length(graph, source, cutoff=...) returns a mapping from reachable nodes to integer edge counts. Graph inputs support nodes and directed edges.

## `elftools.elf.elffile.ELFFile`

The local ELF reader elftools.elf.elffile.ELFFile(stream) accepts a seekable binary stream. get_section_by_name(name) returns a section. A symbol-table section exposes iter_symbols(); each symbol exposes name and dictionary-style st_value and st_shndx fields. st_value is an integer address and st_shndx is a section index or section-kind string.

## `mcp`

The local MCP client SDK exposes ClientSession(read_stream, write_stream) as an async context manager with initialize() and call_tool(name, arguments) async methods. Tool calls return CallToolResult objects exposing model_dump(by_alias=True), isError, structuredContent, and content. StdioServerParameters(command, args, env=..., cwd=...) holds a command string, argument list, optional environment mapping and working directory. mcp.client.stdio.stdio_client(parameters) and mcp.client.sse.sse_client(url) are async context managers yielding read and write streams. mcp.client.streamable_http.streamable_http_client(url) is an async context manager yielding read and write streams plus a session-id accessor. URLs are strings.

## `pycparser.c_ast`

Stated under `pycparser`.

## `pycparser.c_parser`

Stated under `pycparser`.

## `z3.FPVal`

Stated under `z3`.

## `z3.Float32`

Stated under `z3`.

## `z3.Float64`

Stated under `z3`.

## `z3.RNE`

Stated under `z3`.

## `z3.fpAdd`

Stated under `z3`.

## `z3.fpDiv`

Stated under `z3`.

## `z3.fpMul`

Stated under `z3`.

## `z3.fpSub`

Stated under `z3`.

## `z3.fpToIEEEBV`

Stated under `z3`.

## `z3.simplify`

Stated under `z3`.

## `networkx.ancestors`

Local graph utilities are provided by networkx. ancestors(graph, node) and descendants(graph, node) return sets of nodes. single_source_shortest_path_length(graph, source, cutoff=...) returns a mapping from reachable nodes to integer edge counts. Graph inputs support nodes and directed edges.

## `networkx.descendants`

Local graph utilities are provided by networkx. ancestors(graph, node) and descendants(graph, node) return sets of nodes. single_source_shortest_path_length(graph, source, cutoff=...) returns a mapping from reachable nodes to integer edge counts. Graph inputs support nodes and directed edges.

## `networkx.single_source_shortest_path_length`

Local graph utilities are provided by networkx. ancestors(graph, node) and descendants(graph, node) return sets of nodes. single_source_shortest_path_length(graph, source, cutoff=...) returns a mapping from reachable nodes to integer edge counts. Graph inputs support nodes and directed edges.

## `mcp.ClientSession`

Stated under `mcp`.

## `mcp.StdioServerParameters`

Stated under `mcp`.

## `archinfo.arch_soot.SootMethodDescriptor.from_string`

SootMethodDescriptor.from_string(signature) accepts a qualified method signature string. from_soot_method(method) accepts a loaded Java method object. Both return method descriptors supporting equality. address() returns a SootAddressDescriptor.

## `archinfo.arch_soot.SootMethodDescriptor.from_soot_method`

SootMethodDescriptor.from_string(signature) accepts a qualified method signature string. from_soot_method(method) accepts a loaded Java method object. Both return method descriptors supporting equality. address() returns a SootAddressDescriptor.

## `velnora.knowledge_plugins.cfg.CFGModel.parse`

Stated under `velnora.knowledge_plugins.cfg.CFGModel`.

## `velnora.state_plugins.posix.Flags.O_RDWR`

Flags exposes the open-mode token O_RDWR.

## `velnora.knowledge_plugins.variables.variable_access.VariableAccessSort.READ`

VariableAccessSort exposes READ, WRITE, and REFERENCE as variable-access-kind tokens.

## `velnora.knowledge_plugins.variables.variable_access.VariableAccessSort.WRITE`

VariableAccessSort exposes READ, WRITE, and REFERENCE as variable-access-kind tokens.

## `velnora.knowledge_plugins.variables.variable_access.VariableAccessSort.REFERENCE`

VariableAccessSort exposes READ, WRITE, and REFERENCE as variable-access-kind tokens.

## `pycparser.c_parser.CParser`

Stated under `pycparser`.

## `pycparser.c_parser.ParseError`

Stated under `pycparser`.

## `pycparser.c_ast.ArrayRef`

Stated under `pycparser`.

## `pycparser.c_ast.Assignment`

Stated under `pycparser`.

## `pycparser.c_ast.BinaryOp`

Stated under `pycparser`.

## `pycparser.c_ast.Break`

Stated under `pycparser`.

## `pycparser.c_ast.Cast`

Stated under `pycparser`.

## `pycparser.c_ast.Compound`

Stated under `pycparser`.

## `pycparser.c_ast.Constant`

Stated under `pycparser`.

## `pycparser.c_ast.Continue`

Stated under `pycparser`.

## `pycparser.c_ast.Decl`

Stated under `pycparser`.

## `pycparser.c_ast.DeclList`

Stated under `pycparser`.

## `pycparser.c_ast.DoWhile`

Stated under `pycparser`.

## `pycparser.c_ast.EmptyStatement`

Stated under `pycparser`.

## `pycparser.c_ast.ExprList`

Stated under `pycparser`.

## `pycparser.c_ast.For`

Stated under `pycparser`.

## `pycparser.c_ast.FuncCall`

Stated under `pycparser`.

## `pycparser.c_ast.FuncDef`

Stated under `pycparser`.

## `pycparser.c_ast.Goto`

Stated under `pycparser`.

## `pycparser.c_ast.ID`

Stated under `pycparser`.

## `pycparser.c_ast.Label`

Stated under `pycparser`.

## `pycparser.c_ast.PtrDecl`

Stated under `pycparser`.

## `pycparser.c_ast.Return`

Stated under `pycparser`.

## `pycparser.c_ast.Switch`

Stated under `pycparser`.

## `pycparser.c_ast.TernaryOp`

Stated under `pycparser`.

## `pycparser.c_ast.Typename`

Stated under `pycparser`.

## `pycparser.c_ast.UnaryOp`

Stated under `pycparser`.

## `pycparser.c_ast.While`

Stated under `pycparser`.

## `mcp.client.stdio.stdio_client`

Stated under `mcp`.

## `mcp.client.sse.sse_client`

Stated under `mcp`.

## `mcp.client.streamable_http.streamable_http_client`

Stated under `mcp`.
