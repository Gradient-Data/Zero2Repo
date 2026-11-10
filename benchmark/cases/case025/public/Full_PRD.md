# Velnora Full PRD

Velnora is a semi-static type checker for Python. It helps developers find type errors and suspicious code, including in programs that create types and callable behavior dynamically.

### FP-01: Source checking and diagnostic reporting

- Accept Python source supplied as a file, a directory tree, multiple file or directory targets, or an inline source fragment. Analyze Python files within directory targets and attribute source findings to the affected file and source location.

- For importable source, make runtime-defined classes, functions and module members available to checking. Module-level code executes as part of this use; a function body need not be called for errors in that body to be reported. Check against the Python version and import environment in which the checker runs.

- Report enabled, unsuppressed findings with an explanation that distinguishes their causes and identifies the affected source name or incompatible type. An ordinary checking run with findings has an unsuccessful outcome; a run without findings has a successful outcome. By default collect findings beyond the first error; an explicitly requested first-error mode stops after the first distinct finding, without reporting later findings.

- Provide detailed and concise diagnostic presentations. Detailed presentation is the default and includes source context for located findings; concise presentation retains the location, diagnostic category and explanation. On request, export findings for programmatic consumption or as a document grouped by source file, retaining the diagnostic distinctions and locations. A successful file check with no findings creates no programmatic report.

- Refuse unreadable source and source that is syntactically invalid for the running Python version as input failures. An exception caused by importing or executing submitted source is reported as an import or execution failure, with its cause identifiable.

### FP-02: Configuration and diagnostic suppression

- Allow callers to choose checking targets, import roots, additional type-stub locations and an alternative source of standard-library type stubs through configuration. Resolve configured relative filesystem locations against the configuration file that contains them. Explicit checking targets replace configured default targets.

- Allow diagnostic categories to be enabled or disabled individually or collectively. The diagnostic checks specified here are enabled by default unless described as optional or requiring an explicit search request. Explicit category choices override the collective command-line choice; when a category is both explicitly enabled and disabled on the command line, disabling wins.

- Allow configuration to extend another configuration and to override settings for a module and its descendant modules. For scalar settings and checking, import-root and stub-location lists, command-line values take precedence over configuration values; the including configuration takes precedence over included configurations; within the same configuration priority, the most specific matching module override takes precedence over a broader setting. Lists of disallowed imports, diagnostic exemptions and application extension providers accumulate applicable entries in that priority order, retaining the order within each supplied list. Calls to configured exempt callables are not rejected for argument incompatibility. When multiple constructor extension providers supply a contract for the same class, the first applicable provider in that order governs construction.

- Refuse missing configuration files, recursive configuration inclusion, unknown settings, values of the wrong declared setting type, and module overrides without a module selection as configuration failures. Allow callers to inspect effective settings and their configured overrides without checking source.

- Honor checker-specific suppression comments on the affected line or the immediately preceding standalone line. A category-specific comment suppresses only that category; a blanket comment suppresses all findings on the affected line. A blanket file suppression suppresses findings throughout that file.

- Honor Python type-checking ignore comments on the affected line as blanket suppression. A standalone blanket type-checking ignore before the first source statement suppresses the whole file; the same comment after a source statement does not suppress the file.

- Provide optional checks for unused checker-specific suppression comments and for blanket line suppressions lacking a diagnostic category; both checks are off by default. A whole-file blanket suppression is exempt from the category requirement. An unused-comment finding identifies a comment that suppressed no finding.

### FP-03: Type interpretation, compatibility and generic specialization

- Interpret class annotations, unions, optional types, unrestricted types, literal types, homogeneous lists, sets and mappings, fixed-length and repeated-element tuples, class-object types and callable types. Reject an annotated assignment when the assigned expression's type is incompatible with the declared type; accept compatible assignments. A union destination accepts a source matching a member, whereas a union source must have every possible member accepted by the destination. Unrestricted types allow compatibility without proving a concrete type.

- Preserve subtype relationships for class instances and class objects. Accept integers where floating-point or complex numbers are expected and floating-point numbers where complex numbers are expected. Distinct nominal wrapper types remain distinct from each other and from their underlying type when used as destinations, while their values remain usable as the underlying type.

- Resolve quoted annotations, forward references and type aliases to their declared meanings. Support recursive aliases through container structure and preserve specialization of recursive generic aliases. Reject explicit alias cycles that refer back to themselves without introducing a containing type, and reject expressions that do not denote types in annotation positions.

- Infer type arguments for generic functions and constructors from supplied arguments, propagate them to result types, and honor explicit specialization. Support ordinary type parameters, captured callable parameter lists and variadic tuple type parameters. Reject incompatible bounds and constraints during generic call inference and explicit generic alias specialization. Reject incompatible specialization arity and type-argument kinds. In declarations with multiple parameters, reject an ordinary type where a captured callable parameter list is required. Validation of bounds and constraints in ordinary runtime generic class specialization, and of individual items in the flat specialization of a sole captured callable parameter list, is outside this requirement.

- Apply declared generic defaults to omitted specialization arguments, substituting earlier arguments into dependent defaults. Reject defaults incompatible with their bounds or constraints, defaults referring to later type parameters, and required ordinary parameters following defaulted ordinary parameters.

- Respect covariant, contravariant and invariant generic relationships: covariance preserves the argument's subtype direction, contravariance reverses it, and invariance requires compatibility in both directions. Runtime-declared ordinary type parameters are invariant unless variance is explicitly declared or inference is requested; inline class type parameters use inferred variance. For declarations requesting inferred variance, output-only use permits covariance, input-only use permits contravariance, and use in both directions or in a writable member requires invariance. A callable input reverses the surrounding direction; a callable result preserves it. Generic parameters belonging to different declarations remain distinct even when their names match.

- Support inline generic declarations on Python versions that accept them, and runtime-declared generics on versions that provide those declarations. Reject use of an unbound type parameter in a variable annotation and capture of an enclosing class's runtime-declared type parameter by a nested independent class. Reject capture of an enclosing class's type parameter by an independent alias. Nested class member annotations referring to an enclosing inline type parameter are outside the capture-rejection guarantee.

- Allow callers to reveal inferred expression types and local variable types, and to assert an expected inferred type. A mismatching type assertion produces an inference diagnostic. For literal expressions and bindings retaining their literal assignments, expose the literal identity; for union and specialized generic annotations, expose the alternatives and type arguments.

- Distinguish values that represent type expressions from ordinary instances. For a parameter restricted to type expressions describing a particular type, accept compatible class or type-expression values, reject ordinary instances and incompatible represented types, and propagate a represented generic argument into the result type.

- A literal destination requires the same literal value and runtime kind, except that callable literals use signature compatibility. An optional annotation accepts either its non-null type or the null singleton. Fixed tuples require compatible elements at every declared position and the declared length; repeated-element tuples require each element to satisfy their element type. Mutable homogeneous lists, sets and mappings are invariant in their type arguments; read-only sequences and iterables permit narrower element types.

- A bounded type parameter retains the inferred subtype when it satisfies the bound. A constrained type parameter uses one of its declared constraints and rejects arguments that cannot share an allowed constraint. With no explicit specialization and no inferred argument or declared default, an omitted ordinary generic argument is unrestricted. Explicit specialization with a nonempty but incomplete argument list is invalid unless defaults or variadic parameters account for the omitted positions.

- An explicit type cast gives its expression the requested annotation for subsequent checking without requiring the original expression to be assignable to it. Reject a cast target that is not a valid type annotation.

- Interpret the empty type as admitting no values. A call declared to return the empty type cannot contribute a normally completing path. An exhaustiveness assertion accepts a value narrowed to the empty type and reports an argument incompatibility if a possible value remains.

- Allow callers to retrieve inferred expression types programmatically from submitted source or a source file, associated with their corresponding source expressions. Known literal expressions expose their values, and name and member reads expose the types established by their bindings.

- Support declared singleton sentinel values as annotation alternatives. Distinct sentinels remain distinct types.

### FP-04: Refined types and user-defined value restrictions

- Support intersection types requiring all constituent restrictions, negation types excluding values belonging to the negated type, and overlap requirements accepting types with a nonempty intersection. Enforce these restrictions during assignment and argument checking, including basic combinations of unions, intersections and negations.

- Accept literal annotations over runtime Python objects. An optional strict-literal check, off by default, limits literal arguments to integers, strings, bytes, booleans, enumeration members and the null singleton.

- Honor user-defined annotation checks that accept or reject assignment into or out of the annotated type. A rejected assignment reports the custom incompatibility reason. Where the check declares generic dependencies, specialize its restrictions with the enclosing generic arguments. Metadata with no recognized restriction does not change compatibility with the underlying type.

- Provide a literal-only restriction that rejects values whose exact value is not known, and an unrestricted-type prohibition that rejects unknown types, overriding ordinary gradual acceptance. The latter checks the outer value by default; an explicitly requested deep check also rejects unknown types nested inside a composite type.

- Enforce numeric upper and lower bounds, with either inclusive or exclusive endpoints; divisibility; minimum and maximum lengths; timezone restrictions; and user-supplied value predicates attached as annotation metadata. Known values must satisfy the requested restrictions. A concretely typed value lacking evidence for a restriction is rejected as unproven; an unrestricted value remains accepted unless its annotation also prohibits unrestricted types. Divisibility uses the remainder operation in the Python Language Reference for the running interpreter's major and minor version: the supplied value divided by the supplied divisor must have zero remainder. A predicate returning false or raising an ordinary exception produces an incompatibility finding; an exception's cause remains identifiable.

- For timezone restrictions, distinguish a datetime without timezone information, a datetime with timezone information, and a datetime matching a supplied fixed-offset timezone. A value that is not a datetime fails the restriction. Accept a supplied numeric bound when its endpoint and inclusiveness imply the requested bound of the same direction without assuming an integer-only domain. Accept stronger length bounds and divisibility metadata whose divisor is a multiple of the required divisor.

- Resolve an explicitly qualified external type reference even when the referring source has no direct import of that type. A reference that cannot be resolved produces an annotation failure rather than being treated as a successfully resolved concrete type.

### FP-05: Name binding and control-flow correctness

- Resolve names according to Python's local, enclosing, global, built-in, class-body and comprehension scopes. Report a reference to a name with no binding as undefined, and a local read reachable without a preceding assignment as possibly undefined. Comprehension-local iteration variables do not become bindings in the surrounding scope.

- Combine possible types and binding availability across conditional branches, loops, loop completion clauses, exception handlers and cleanup clauses. A branch that returns, raises or calls a function declared never to return does not contribute values to the following reachable statements. Include the possibility of an empty iterable when determining whether a loop body definitely assigned a local variable. After a loop completion clause, inferred types may conservatively retain loop-body alternatives; assignments in the body and completion clause alone need not establish definite binding.

- Reject declarations of nonlocal variables without a binding in an enclosing function and conflicting uses of global or nonlocal declarations. Respect reassignment through valid enclosing or global bindings.

- Reject raising a non-exception object, using a non-exception handler target, and using an exception-group class as a subgroup handler target. Bind ordinary handler variables to the caught exception type and subgroup-handler variables to the corresponding exception-group type on Python versions supporting subgroup handlers.

- For comparisons of the running Python version, platform or interpreter implementation with literal version components or names, apply the branch selected by that environment. Treat a direct type-checking-only condition as true for checking even though it is false during ordinary execution. This guarantee does not extend to its negated form inside a function. Code excluded by these conditions does not produce errors solely from names or operations in the excluded branch.

- Offer unreachable-code reporting, off by default, for statements following unconditional termination and branches excluded by a provable condition. Distinguish those locations from reachable code; do not report each successive statement of the same unreachable block as a separate unreachable-code finding.

### FP-06: Callable contracts and return checking

- Check calls to functions, bound methods, callable instances and class constructors against their signatures. Support positional, keyword, positional-only, keyword-only and variadic arguments, including unpacked positional sequences and keyword mappings. Report missing required arguments, repeated bindings, unexpected arguments and incompatible argument types; reject calling a value known to be non-callable.

- Treat a callable as compatible with an expected callable when it accepts the expected calls and returns an accepted result. Preserve captured parameter lists through higher-order functions and decorators, including signatures with added leading parameters; reject calls to the resulting callable that violate the preserved signature.

- For a call with concrete arguments, use the first declared overload accepting the call's shape and types. For union arguments accepted by different overloads, infer the union of the corresponding result types; reject a call with an uncovered alternative. When unknown argument types cause ambiguity between overloads with different results, infer an unrestricted result. Reject calls accepted by no overload and inconsistent overload declarations whose implementation cannot accept their declared calls or return their declared results.

- Check parameter defaults and returned values against their annotations. Report a function that can finish without returning a value when its return annotation excludes the null singleton. Report normal return from a function declared never to return. An explicit empty implementation in a stub or abstract declaration does not by itself require a return statement.

- For unannotated functions with available source whose completing paths return known expression types, infer those types, combining different returned types as a union and including the null singleton for an explicit bare return. Infer the null singleton for a normally completing function with no value returns. Inclusion of implicit fallthrough alongside value returns is outside this inference guarantee. Preserve the result of an annotated call through subsequent assignments and calls. A callable whose signature is unknown remains callable without asserting a concrete result type.

- On request, report missing annotations on ordinary function parameters and return values, and missing generic arguments in annotations. These checks are off by default. The implicit instance or class receiver of a method does not require an explicit parameter annotation.

- For overload calls with an unpacked positional sequence of unknown length, prefer matching alternatives with variadic positional parameters. For an unpacked keyword mapping of unknown keys, prefer matching alternatives with variadic keyword parameters. This preference takes precedence over declaration order among otherwise matching alternatives.

- Use available type-stub declarations to check imported callables whose runtime definitions lack annotations. Enforce the stub's argument types, defaults and overload alternatives and propagate its declared return type to subsequent expressions.

- For a callable described by an intersection of callable contracts and arguments with concrete types, a call is accepted when every possible argument alternative is accepted by at least one constituent. Where multiple constituents accept the same alternative, its result satisfies the intersection of their result types; different argument alternatives contribute a union of those results. Report an argument alternative accepted by no constituent.

- For an ordinary class whose allocation and initialization contracts accept the same arguments, construction checks those arguments and produces the specialized instance type. A class using only default construction accepts no arguments. When an explicitly annotated allocation operation returns an unrelated type, an unrestricted type or the empty type, use its argument contract and declared result without imposing the instance initializer's contract. A custom metaclass call with an explicit non-instance result instead governs the class call's arguments and result.

### FP-07: Objects, inheritance and structural interfaces

- Infer reads of annotated and runtime-known attributes on modules, classes and instances, including inherited members, bound methods, properties and descriptors. Report missing members on modules and built-in types, and writes incompatible with a declared attribute type. Check descriptor writes when the descriptor declares matching read and write types. Reject writes to read-only properties. Apply the specialization of inherited generic bases to the types of their members.

- Preserve the concrete receiver type for self-referential return annotations on inherited instance methods and class methods. Reject self-referential annotations outside a valid class context and on static methods.

- Enforce structural interfaces by checking the required members and their types without requiring nominal inheritance. Missing members and incompatible member signatures cause compatibility failures. Writable members require compatibility in both directions; read-only members permit a narrower returned type. Apply generic arguments to structural members.

- Reject reassignment of final variables and inheritance from a final class. With optional override-compatibility checking enabled, reject overriding final members and report method signatures and attributes incompatible with their base declarations. Override checking, including final-member overrides, is off by default.

- Validate explicit override declarations: a marked method must replace a base member, and the marker must occur on a class member. For class declarations analyzed from source without executing the declaration, diagnose instantiation when abstract members remain unimplemented. Reject repeated parameters in a generic base declaration and inheritance paths that give the same generic ancestor incompatible specializations. Reject a specialized generic metaclass or a metaclass value that is not a class derived from the class-of-classes type.

- Preserve enumeration-member identity and the types of declared member values through access and iteration. Diagnose a repeated member value in an enumeration declaration. A declared annotation for enumeration values constrains those values, and incompatible member values are reported.

- For a class with a known closed set of instance slots and no instance dictionary in its inheritance chain, reject writes to undeclared instance attributes. Accept writes to declared inherited slots. For ordinary user-defined classes, report an attribute read that has no declaration or assignment in the examined class and its examined bases when whole-program attribute checking is enabled.

- For declared read-only attributes, reject writes outside initialization contexts and reject deletion. A concrete class permits writes to its own instance receiver in its initializer, to an instance of that class or a subclass in its directly declared allocation method or class methods, and to its class-variable receiver in its subclass-initialization hook. These permissions do not extend to nested functions. Structural-interface declarations cannot initialize their read-only attributes; concrete implementations can. In an intersection of object types, a writable declaration of a member permits a type-compatible write even if another constituent exposes that member as read-only.

- Class-variable qualifiers are valid on class-body attribute declarations, and required or optional field-presence qualifiers are valid only on typed mapping fields. Read-only qualifiers are valid on class-body attributes, instance-attribute declarations in initializers and typed mapping fields. Reject these qualifiers in ordinary parameter, return and local-variable annotations. Reject repeated final qualifiers and combinations of final with read-only. A data-class class-variable qualifier may enclose a final qualifier; reject the reverse nesting and reject either nesting for an ordinary class. Qualifiers that enclose a type accept exactly one enclosed type.

- For generated integer enumerations declared by paired member-name and integer-value mappings, accept their listed integer literals and values annotated as that enumeration, and reject known integer literals absent from the mappings. An integer of unknown value remains assignable. Enumeration-annotated values retain integer compatibility, including integer-indexing structural requirements.

### FP-08: Typed mapping records

- Interpret typed mapping declarations with named fields, per-field value types, required or optional presence, inheritance and generic arguments. Generic field substitution and the resulting construction, assignment and field-operation checks are guaranteed for local declarations analyzed without executing the declaration; executed module-level generic mapping declarations are outside that guarantee. Fields are required and writable by default. A declaration can make its own fields optional by default without changing inherited requiredness; an explicit per-field presence qualifier overrides the declaring class's default. Construction and assignment must provide required fields with compatible values. Reject non-type field annotations, contradictory or repeated presence qualifiers, repeated read-only qualifiers and class-variable qualifiers on fields.

- Infer the declared value type when reading a known field. Reject keys outside the declared field set unless the mapping permits typed extra entries; extra entries use their declared value type. Reject non-string keys. For a mapping without typed extra entries, a string key whose value is unknown is reported as an invalid typed-mapping key.

- Check field writes, updates, removal and deletion against field value types, required presence and mutability. For insertion with a default into a declared named field, check the default against that field's type. Reject mutation of read-only named fields and deletion of required fields. Operations returning stored values retain the field or extra-entry type and include the supplied default's type when absence can select that default.

- Distinguish open mappings, closed mappings and mappings with explicitly typed extra entries; mappings are open by default. Without typed extra entries, construction and assignment from a mapping display reject undeclared fields. Open destinations nevertheless accept structural assignment from another typed mapping containing additional fields; closed destinations reject those additional fields. Construction and indexed writes of extra entries must satisfy their declared value type; reads retain that type. Inheritance cannot explicitly reopen a closed base or a base with typed extra entries, or incompatibly change a writable extra-entry type. Omission of an extra-entry declaration retains the inherited constraint. A subclass may narrow a read-only extra-entry type or close that mapping, but may not close a base with writable extra entries.

- For structural assignment between typed mappings, a required destination field requires a required source field. Writable destination fields require compatible types in both directions, identical requiredness and a writable source field. Read-only destination fields accept narrower source value types and may accept a required source field when the destination field is optional. Inherited fields obey these same compatibility and requiredness rules when redeclared. Use an unpacked typed mapping in a callable's keyword contract to enforce its required fields and value types at call sites.

### FP-09: Expressions, collections and protocol operations

- Infer element, key and value types for list, tuple, set and mapping expressions, comprehensions and their unpacked contents. For collection displays with individually known entries, preserve their positions or keys for indexed access and fixed-shape unpacking. Report a non-iterable unpacking source and a known length that cannot fit the assignment targets, including starred targets.

- Check arithmetic, bitwise, comparison, unary, augmented-assignment, containment, indexing and slicing operations against the operand types and their declared operations. Infer the operation's result type, including reflected operations supplied by the other operand. Report unsupported operations and incompatible operand or index types. Validation of non-literal slice-boundary types on built-in sequences is outside this guarantee; slicing result types and custom declared indexing contracts remain covered.

- Check collection construction and mutation using the container's element, key and value types. Appending, extending and mapping insertion with incompatible values are type errors. Infer iteration values and the results of indexing, slicing, copying and collection conversions from their source collection types, except that preservation of key types through the ordinary mapping constructor is outside this guarantee.

- Report duplicate known keys in mapping displays and unhashable keys or set elements. Report a known out-of-range index into a fixed tuple and removal without a default of a known absent key from a mapping whose keys are known.

- Check synchronous context-manager use against its entry and exit operations. Infer the bound value from the entry result, including unions of valid managers. A union with a member that cannot serve as a synchronous context manager is rejected.

- Diagnose equality comparisons between disjoint ordinary built-in types, including incompatible element types in containers, when the comparison has no custom equality behavior permitting the other operand. Permit comparison between overlapping union alternatives and comparisons to the null singleton.

### FP-10: Named tuples and data-class records

- Check named-tuple construction using its ordered fields, declared types and trailing defaults. Infer field access, positional indexing and unpacking from the declared field types. Reject incompatible constructor arguments, missing required fields, field names that are not Python identifiers or begin with an underscore, non-type field annotations and required fields following fields with defaults. Reject assignment to or deletion of tuple fields.

- For named tuples declared in type stubs, recognize replacement, construction from an iterable and conversion to a mapping as record operations. These operations returning the record preserve the concrete subclass type. Conversion to a mapping produces string keys and unrestricted value types. A subclass's additional ordinary attributes do not become tuple elements or extra constructor fields.

- Check data-class constructor calls against inherited and locally declared fields, defaults, default factories, keyword-only fields and fields excluded from initialization. Initialization-only values participate in constructor argument checking without becoming ordinary stored fields. With optional override checking enabled, reject a post-initialization method signature incompatible with the initialization-only fields. Reject incompatible field defaults and required positional fields following defaulted positional fields.

- Reject writes to frozen data-class instance fields. Honor declared slots and generated ordering support. An ordering comparison unsupported by the record declaration produces an operation failure.

- Recognize data-class transformation declarations on decorators, base classes and metaclasses. Apply their constructor, field and frozen-record declarations to resulting classes, including field defaults, keyword-only choices and field aliases. Reject multiple applicable transformation sources on the same class.

- A data-class field without a default or default factory is required in construction unless excluded from initialization. Fields are positional-or-keyword, mutable and included in initialization by default; an explicit field choice overrides the class-wide keyword-only choice. Constructor field order follows inherited fields before newly declared fields, retaining an inherited field's position when overridden. Class variables do not become constructor fields. Generated ordering is off by default; when enabled, comparisons between instances of the same record type are accepted, while ordering different record types is rejected.

### FP-11: Conditional narrowing and pattern matching

- Narrow possible values using instance and subclass checks, identity and equality tests against known values, including declared singleton sentinels, and truth tests. Apply the positive or negative information to the corresponding branch and assertions; combine information through conjunction, disjunction and negation. A successful callable check permits calling the value. For a value annotated as the universal object type, the successful branch exposes a callable with arbitrary arguments and an unrestricted result; the unsuccessful branch retains the universal object type. A successful attribute-presence check permits access to that member, without guaranteeing its concrete type or exclusion of union alternatives. Reassignment invalidates a previous restriction on the reassigned value.

- Honor a declared positive type guard on its guarded argument only in the successful branch. Honor a declared two-sided type guard in both branches, excluding the guarded type in the unsuccessful branch; reject a two-sided guarded type that is not a subtype of the input type. Support extended guards that name a parameter other than the first, including bound-method calls.

- Use comparisons against literal numeric bounds and length bounds to refine annotated restrictions. Exact tuple-length information refines a repeated-element tuple into the corresponding fixed shape; lower-bound information preserves the guaranteed elements together with the remaining variable-length portion. Eliminate typed-mapping alternatives whose required or permitted sizes cannot meet the established length condition.

- Support literal, singleton, capture, wildcard, sequence, mapping, class, alternative and guarded patterns. Infer captures and narrow the subject within a matching case; exclude covered literal alternatives from later cases. Report patterns impossible for the subject type and class patterns with invalid positional or keyword attribute selections.

- Preserve literal-string safety for literal text and interpolated strings whose embedded values all have literal-string types. Reject a general runtime string where a literal-string annotation is required.

- For data-class patterns, use the record's declared positional matching fields and honor exclusion of keyword-only fields or disabling of positional matching. A positional pattern requiring a field outside that declaration produces a pattern failure.

### FP-12: Generators and native asynchronous code

- Check generators against declared yielded, sent and returned types. Infer the value received by a yield expression from the declared sent type, and infer a delegated generator's result from its return type. Report incompatible yielded or returned values and incompatible delegated yields.

- Reject generator declarations whose return annotation does not describe an iterable or generator. For an iterable-only annotation, check yielded elements against the iterable element type, infer the null singleton for the received value, and reject a non-null generator return value.

- Infer an asynchronous function call as an awaitable carrying its declared result, and infer awaiting it as that result. Reject awaiting a non-awaitable. Report a discarded coroutine call in asynchronous code as a missing-await error, while allowing a coroutine to be returned or passed where an awaitable is expected.

- Check asynchronous generators and asynchronous iteration using their yielded element and sent-value types. Reject asynchronous iteration over a type lacking asynchronous iteration support, and reject yielded elements incompatible with the asynchronous generator annotation.

- Check asynchronous context-manager use against its asynchronous entry and exit operations. Infer the bound value from the awaited entry result, including unions of valid managers. Reject a union containing a member that cannot serve as an asynchronous context manager.

### FP-13: Generator-based task framework checking

- For the supported generator-based task framework, distinguish direct result-producing calls from task-producing calls, and infer the yielded result of a task from the wrapped callable's result type. Accept task-aware callable annotations only for callables satisfying the requested ordinary and task-call signatures.

- In a framework task function, accept yields of futures, tasks, the explicit null singleton, and nested lists, tuples or mappings of these values. Infer the same collection shape with task results in place of tasks. Reject other yielded values and a yield with no supplied expression.

- Report a task or future returned or discarded by a framework task function without yielding it. Report direct result-producing calls to framework asynchronous callables inside framework task functions. Also apply this call-discipline check to ordinary instance methods of configured classes and their subclasses, except configured exempt methods; ordinary class methods are not included by that configuration. Method exemptions do not disable the check inside a declared framework task function.

- Report a tuple yield containing the same task expression more than once. For consecutive assignments from yields in the same straight-line block, report an unnecessary separate yield when none of the previous yield's assigned results is read before or in the next yielded expression. Report an ordinary generator that yields a framework task call without a framework task declaration as missing that declaration.

### FP-14: Formatting and regular-expression validation

- Validate literal percent-formatting patterns for text and bytes against their operands. Support decimal, octal and hexadecimal numeric conversions; fixed, exponential and general floating-point conversions; character, string, representation and ASCII-representation conversions; byte conversions in byte patterns; and escaped percent signs. Numeric conversions accept integers, floating-point values and values supporting integer indexing. Text string conversions and representation conversions accept arbitrary values; byte string conversions require bytes. Character conversion accepts an integer or a single character of the pattern's text or byte kind; known integer character values must be between zero and 255 inclusive. Report unknown conversion forms, a byte conversion in a text pattern, missing mapping keys, incompatible operands, wrong argument counts, and non-integer supplied width or precision. Mapping fields require a mapping; positional fields consume arguments in field order, with supplied width and precision preceding their field value.

- For a single known literal replacement-field template with a known positional argument count and known keyword names, report malformed fields, unavailable argument positions or names, and supplied arguments that the template does not reference. Include argument references in nested format specifications when determining which arguments are required or used. Infer formatted text as a string.

- Offer missing-interpolation-prefix checking, off by default, for an ordinary text literal that would be a valid interpolated string and whose replacement expressions contain names that all resolve in scope. Exempt standalone string expressions, strings explicitly used for replacement-field formatting, and strings passed to a call whose keyword arguments supply all those names. Leave strings with unresolved names in braces unflagged by this check.

- Validate known regular-expression patterns used with default external flags in regular-expression operations or annotations requiring valid patterns. With the supplied pattern and its inline flags, report patterns rejected by the Regular Expression Syntax section of the Python Library Reference for the running interpreter's major and minor version. A pattern whose value is unknown is not reported as malformed solely because it is unknown.

### FP-15: Unused code and API usage diagnostics

- Report local variables assigned but never read and assigned values overwritten without a read. Treat underscore-prefixed locals as exempt. In ordinary tuple or list unpacking assignments and tuple comprehension targets, suppress unused-local findings when another name from that target is used. Reads in nested functions count as uses of captured bindings.

- On request, identify functions, classes and class attributes that are unused within the analyzed source set. Account for inherited member access and structural-interface use as uses of the corresponding members. Exclude objects explicitly marked used and configured object or attribute exemptions. Whole-program unused-object and unused-attribute searches are off by default.

- On request, report unused callable input alternatives among observed direct calls: a union alternative never supplied, a boolean parameter observed with only one truth value, or an optional parameter always omitted. Count an omitted boolean default as an observed value. Identify the affected callable and parameter and distinguish which alternative is unused. Do not infer an unused alternative solely from the absence of any observed call or when an unknown argument could supply it. This analysis is off by default.

- Report use of deprecated functions, classes and members, and calls selecting a deprecated overload. Preserve the supplied deprecation reason; calls selecting only non-deprecated overloads do not receive a deprecation finding.

- Reject imports of a configured disallowed module or any descendant of that module. Offer checking of imports and module-member access to names beginning with exactly one underscore, off by default; enabling it makes such access from a different module reportable. Names beginning with two underscores are exempt.

- Report a function or bound method used as a truth condition without being called, a known value whose truth conversion raises an error, and a framework future used as a truth condition. Distinguish these from ordinary boolean-valued conditions. Report discarded synchronous and asynchronous generator results. Ordinary function results need not be used.

### FP-16: Application-specific checking extensions

- Allow applications to supply callable and constructor contracts. Use the supplied argument and result types when checking source calls, so a violation of the custom contract is reported even if the runtime callable accepts arbitrary arguments.

- Allow a custom call check to inspect supplied argument types and known values, issue an application-specific diagnostic and determine the inferred result type. Preserve that result type in subsequent checking and make the custom reason observable at the call site.

- Allow application extensions to declare attribute read and write types, resolve application-specific attributes and unwrap application-specific class wrappers. Instance member reads and writes, member reads through typed class values, and constructor calls obey those declarations and report incompatible uses. Attribute transformation on direct reads from runtime-known class objects is outside this guarantee.

- Allow extensions to register diagnostic categories with descriptions. A registered category can be enabled or disabled through configuration, and is enabled by default. Category-specific suppression applies to findings emitted under that category.

- For callables explicitly approved by the application for evaluation during checking, infer the concrete returned value when all argument values are known and the call succeeds. If such a call raises an ordinary exception, report the failed call and its cause.

### FP-17: Declarative type evaluation

- Allow a callable's typing declaration to choose return types and produce custom call errors according to its arguments. Calls with arguments incompatible with the declaration's parameter types produce argument errors. When multiple argument alternatives satisfy different branches, the inferred result includes the reachable returned types.

- Support conditional declarations based on whether an argument was explicitly supplied, supplied positionally or supplied by keyword; argument type compatibility; equality or identity with literal values; and the running Python version, platform, interpreter implementation name and implementation version. Version conditions support ordered and equality comparisons; platform and implementation names support equality and membership comparisons, and platform names also support prefix tests. Support conjunction, disjunction, negation and nested conditions. When unpacking prevents determining how an individual argument was supplied, treat its supplied-kind tests as false.

- Support conditional branches, type-returning statements, empty statements, explicit diagnostic requests and argument-type revelation in a type-evaluation declaration. Reject other statements, unsupported condition expressions and references to names that are not valid declaration arguments as invalid type-evaluation declarations.

- For an omitted argument with a concrete declared default, use that default's literal type for type evaluation; for an unspecified default, use the parameter annotation. A branch without a returned type uses the declaration's return annotation, or an unrestricted result if no return annotation exists. An explicit diagnostic request does not prevent a later returned type from governing subsequent checking.

- Attribute a custom diagnostic to its specified offending argument when the declaration names one. Include the user-provided explanation and distinguish failure caused by an argument restriction from failure caused by the running environment.

- By default, a type-evaluation compatibility condition does not treat an unrestricted source type as evidence for a concrete target type, including unrestricted types nested in composites; the universal object target remains compatible. In this strict mode, an unrestricted target accepts an unrestricted source but rejects concrete sources, including concrete composite types containing unrestricted members. The declaration can explicitly request ordinary gradual compatibility instead, in which unrestricted targets accept every source and unrestricted sources are compatible with concrete targets.

### FP-18: Continued source checking after import failure

- When import or module-level execution of submitted source fails, report that failure together with independent undefined names and incompatible annotated assignments found in the available source.

- In source that cannot be imported, use explicit function signatures, class member annotations, generic declarations, type aliases, typed mappings, named tuples and data-class field declarations to check their source-level uses. A call or assignment that contradicts these declarations remains a type error even though runtime objects for the module are unavailable.

### FP-19: Runtime assignability checking

- Accept a runtime value and a type annotation and return whether the value is assignable to that annotation. Check every actual element, key and value of parameterized collections as well as the outer container type.

- Provide an explanatory result for runtime incompatibility and an absence of error for compatibility. Distinguish an incompatible outer type from an incompatible contained value, identifying the failing contained position or mapping component when that is the cause.

- Honor recognized value restrictions in runtime assignability checks. In checked source, a successful runtime assignability guard permits subsequent uses of its tested value that require the supplied annotation restriction; unrelated arguments remain subject to their own checks. Exact preservation of the guarded type and restriction metadata is outside this static guarantee.

### FP-20: Annotation suggestions and source corrections

- Offer inferred annotation suggestions for unannotated return values and for unannotated parameters with observed typed call arguments. Both suggestion checks are off by default. Suggested types must accommodate the observed values; do not suggest an ordinary parameter annotation for an implicit method receiver or suggest a type whose only information is unrestricted.

- Offer source corrections for missing interpolation prefixes and unused checker-specific suppression comments. Applied corrections remove the diagnosed construct while preserving the surrounding source.

- In an interactive terminal with a writable working directory and editing support available, let the caller accept or reject proposed edits; a rejected edit leaves its source unchanged. For a file with one reported finding and an available proposed correction, explicit automatic correction applies that edit without interactive acceptance. An ordinary checking run leaves source unchanged.

- On explicit request in the source-editing workflow, insert category-specific suppression comments for reported findings. The inserted comment suppresses its associated finding on a later check. Findings for which no correction is available remain reportable rather than being silently removed from the source.

- Offer optional conversion suggestions, off by default, to interpolated strings for valid percent-formatted text whose arguments are names or attribute chains and whose fields use plain string conversions of exact built-in string values or decimal conversions of exact built-in integer values. The pattern must have matching argument counts and no literal braces, mapping fields, flags, width, precision or length modifiers. Applied conversion preserves the formatted meaning under those conditions.
