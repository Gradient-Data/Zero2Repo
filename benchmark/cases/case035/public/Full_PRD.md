# Velnora Full Product Requirements

Velnora manages Python projects from dependency declaration through reproducible installation, development, distribution building, and publication.

### FP-01: Project definition and validation

- Velnora reads project metadata and dependency declarations from the project document, accepting standard Python project metadata under PEP 621 with PEP 639 license metadata, and legacy product declarations. Metadata includes name, version, description, authors, maintainers, license, license-file selections, README content, keywords, classifiers, project links, Python compatibility, runtime dependencies, optional runtime dependencies, console and graphical application commands, and plugin registrations. Standard static metadata takes precedence over the corresponding legacy metadata; metadata declared dynamic can be supplied through legacy declarations. Legacy dependency information can enrich locking requirements without replacing the standard published dependency declaration.

- Package mode is the default and requires a project name and version. Non-package mode permits a Velnora-only project definition without these two values and supports dependency management without installing the project itself; building or publishing that project is refused as unavailable in non-package mode.

- Project names and declared dependency names must satisfy the name grammar in PEP 508, and project versions must satisfy PEP 440. Malformed project documents, missing mandatory metadata, and invalid metadata types are refused as invalid project definitions. Diagnostics identify the offending declaration for missing metadata and invalid non-identity fields; invalid project-name types may produce a generic diagnostic.

- A project may declare a Python compatibility range for distribution metadata and a narrower range for locking. The locking range must be contained within the published range; a declaration allowing additional Python versions for locking is refused as inconsistent. A declared requirement on the Velnora version is enforced against the running Velnora version, with an incompatibility failure when it is not met.

- Project validation identifies a missing referenced README, an empty README path, and a legacy dependency declaration on the project itself as errors, including declarations in legacy dependency groups. Inline README content does not require a file. Legacy name, description, license, authorship, maintainership, keywords, project links, plugin registrations and extras declarations produce warnings, as do legacy console-command declarations. Legacy version, README and classifier declarations warn when the same standard static metadata is present or when the metadata has not been declared dynamic. Warnings alone permit validation to succeed by default, while strict validation treats them as a failure.

- Project operations discover the project from the working directory or its ancestors and refuse a missing project. A caller can select a different working directory or a different project root. Selecting only a project root leaves the working directory of invoked programs unchanged; selecting a working directory changes it.

### FP-02: Plugin extensions

- Installed project-behavior plugins can change the effective project metadata and dependencies used by ordinary operations. Installed application plugins can contribute executable commands and register command-event behavior whose changes to command inputs affect that command's result. Plugins are enabled by default; disabling plugins for an invocation suppresses their contributed commands and behavior. A registration that supplies neither supported plugin kind is refused as an invalid plugin.

### FP-03: Configuration and repository access

- Users can read, list, set, and remove ordinary persistent settings globally or for one project. Repository credentials and certificate settings are stored globally, including when project-local storage is requested. The functional settings cover storage locations for repository data, managed interpreters and project environments; environment creation, in-project placement, interpreter preference, system-package visibility and inclusion of the package installer; binary distribution policies; per-package build settings; minimum release age and package or source exemptions; publishing destinations; repository credentials and certificates; and keyring use. Effective settings use environment overrides before project settings, project settings before global settings, and global settings before product defaults.

- An unrecognized setting, more than one value for a single-valued setting, or an invalid Boolean or release-age value is refused as invalid configuration. Boolean settings accept true or false and their numeric equivalents one or zero. Storage locations and publishing destinations accept a single location. A username and password can be supplied together, or a username alone prompts for a password; a publishing token accepts one value. Per-package build settings associate named settings with text values or lists of text values; other value types are refused. Updating these settings replaces supplied members and preserves existing members omitted from the update. Removing a setting while supplying a replacement value is refused as conflicting configuration. Refused configuration changes preserve existing persistent settings and credentials.

- Repository-specific username and password credentials and publishing tokens can be saved, replaced, and removed. Subsequent repository operations use the credentials associated with their repository; environment-supplied credentials take precedence over stored credentials. General configuration listings do not disclose passwords or tokens.

- Repository access verifies server certificates by default. Users can provide a custom certificate authority and a client certificate for a repository, or explicitly disable server-certificate verification for that repository. With verification enabled, a server certificate not trusted by the selected authority causes a certificate-validation failure; authentication rejected by a repository remains an access failure.

- Keyring use is enabled by default. Users can store credentials in an available system keyring and retrieve them for later repository access. They can explicitly disable keyring use and persist credentials in configuration instead; removing saved credentials removes the corresponding stored secret.

### FP-04: Dependency constraints and groups

- Dependencies can identify an indexed package, a Git repository, a local project directory, a local distribution file, or a remote distribution archive. Git requirements can select a branch, tag, or commit and a package subdirectory; an unspecified Git revision selects the repository's default revision. A directory requirement can request editable installation, so subsequent changes to its source are visible to programs using the installed dependency.

- Standard dependency declarations follow PEP 508. Version comparisons, exact requirements, exclusions, compatible-release requirements, and wildcard version matching use PEP 440 with the declared version requirement and candidate package version as inputs. Multiple simultaneous constraints intersect; alternative Velnora constraints admit versions allowed by any alternative. Malformed requirements are refused as invalid dependency declarations.

- Velnora caret requirements admit the stated minimum and later releases below the next increment of the first nonzero specified release component; when all specified components are zero, the last specified component determines that upper boundary. Velnora tilde requirements admit the stated minimum through releases below the next minor release when a minor component is specified, or below the next major release otherwise. These forms are accepted in Velnora declarations and dependency addition, and are converted to equivalent standard constraints when recorded as standard dependencies.

- Dependency applicability can be restricted by Python version, operating platform, and environment markers. Marker truth follows PEP 508 using the dependency's marker expression, the target Python and platform environment, and the selected extras. Requests for a dependency's extras activate the additional requirements declared by that dependency. An extra may include other extras of the same package through an unconditional self-reference; conditional self-references between a package's own extras are outside the supported dependency model.

- Runtime dependencies belong to the main group. Named dependency groups accept both PEP 735 declarations and Velnora group declarations, including inclusion of other groups; the including group acquires the included groups' requirements. Groups can be optional, and package extras separately select optional runtime requirements. Group dependencies are not published as runtime dependencies merely because they belong to a group.

- Group selection for installation and dependency inspection includes the main group and all non-optional groups by default. Users can add optional groups, exclude groups, or select only named groups. Exclusion wins over inclusion; an only-groups selection replaces the default selection and takes precedence over inclusion and exclusion. Unknown groups named by any selection control are refused as missing groups even when an only-groups selection would otherwise ignore that control. Installation also permits selecting all groups; combining that selection with selective group controls is refused as conflicting selection.

- Package identity follows the normalized-name rule of PEP 503, using the supplied package name; extra identity follows PEP 685, using the supplied extra name. Dependency-group identity follows PEP 735; declarations of distinct groups with the same normalized name are refused as duplicate groups. Missing included groups and cycles of group inclusion are refused as invalid group definitions.

### FP-05: Package sources

- Users can add, replace, inspect, and remove named package sources in a project. Source inspection shows configured locations and priorities and distinguishes a missing named source from a configured one. A custom source requires a location; the built-in PyPI source has a fixed location that callers cannot replace. Invalid source configuration is refused without saving the proposed source change.

- Package sources have primary, supplemental, or explicit priority; an omitted priority means primary. When PyPI is not explicitly configured and no primary source exists, PyPI is available implicitly. Configuring a primary source disables implicit PyPI, although PyPI can still be configured explicitly. A configuration leaving only explicit sources and no general package source is refused.

- For a dependency without a named source, candidates from all primary sources are considered together. Supplemental sources are consulted in configured order only while preceding sources supply no candidates satisfying the current version and release-selection restrictions. These restrictions can narrow as requirements are combined, allowing another version from a supplemental source. For the same package release, transitive conflicts do not change its configured source precedence. When the same package release exists in multiple eligible sources, their configured precedence determines its source. Explicit sources supply candidates only to dependencies that name them.

- A dependency constrained to one source is resolved only from that source, regardless of its priority. This source constraint does not automatically constrain that dependency's own dependencies. An unknown source named by a dependency is reported as an invalid source reference.

- Package retrieval supports PyPI, public or private simple repositories with HTML or JSON package listings, and single-page collections of distribution links. Published versions, Python compatibility, dependencies, extras, and distribution availability from these sources determine which packages can satisfy a request. A missing requested package or release is reported as unavailable.

### FP-06: Dependency resolution

- Given project requirements and available package metadata, Velnora selects direct and transitive dependencies whose versions, Python compatibility, environment conditions, extras, and origins jointly satisfy the requirements. Resolution covers the project's declared Python range and all dependency groups, including optional groups, rather than only the interpreter and groups used for the current installation.

- Mutually exclusive environment conditions may select different releases of the same package. Requirements that apply together must admit a consistent solution. When no solution exists, resolution fails with an explanation identifying conflicting requirements or the missing compatible package.

- Fresh resolution prefers newer compatible releases while retaining a complete consistent dependency set. By default, a dependency prefers stable candidates and admits prereleases when no stable candidate satisfies its constraint. Explicit prerelease permission removes that preference; explicit prerelease prohibition excludes indexed prerelease candidates. Release ordering follows PEP 440 using the candidate versions.

- Releases withdrawn by a repository are excluded from unconstrained version selection. An exactly pinned withdrawn release can be selected, and its withdrawn status is made visible, including the repository's reason when one is supplied.

- A user can require a minimum release age measured in whole days of 24 hours from repository-reported distribution upload times to the time of resolution. A release with any known distribution upload newer than that age is excluded. The default minimum is zero days, which disables this filter; negative values are refused. Explicitly exempted package names or source names or locations bypass only the age filter. Missing upload times do not by themselves exclude a release.

- Direct-origin requirements obtain the package identity, version, and transitive requirements from the referenced project or distribution. A missing local source, an inaccessible Git revision, or a requested package name that conflicts with the referenced package's metadata produces a source-resolution failure. A valid direct origin can satisfy another requirement on the same package when that requirement does not constrain it to a different source.

### FP-07: Locking and reproducibility

- Locking records the resolved dependency set in the lock document without installing packages. The recorded result retains exact versions, dependency relationships, group and environment applicability, extras, and source identities; Git dependencies retain the resolved commit so later installation does not follow a moved branch or tag.

- Ordinary locking preserves existing locked releases when they still satisfy the project, while incorporating changed requirements. Directory dependencies are refreshed from their current declarations even when their version has not changed. Explicit regeneration disregards previous selections and produces a fresh compatible lock.

- A lock becomes stale when project declarations change their Python compatibility, runtime dependencies, optional dependencies or extras, dependency groups or group inclusions, or package sources. Checking a project with a stale lock fails as an inconsistent lock; checking with a mandatory-lock request also fails when no lock exists. Changes confined to descriptive metadata do not invalidate dependency selections.

- Locks retain distribution integrity information identifying the content of the selected artifacts. Installation rejects selected artifact bytes that do not match their recorded content identity. Lock format versions from 1 inclusive to 3 exclusive are supported. An unreadable or unsupported lock is refused as unusable; explicit regeneration can replace it from the project's dependency declarations.

### FP-08: Python installation management

- Users can list discovered Python installations, including their versions, implementations, executable locations, and whether Velnora manages them. Installed-interpreter listing can be restricted by requested version, implementation, managed ownership, or free-threaded capability. A major-only version selection includes that major release series, a major-and-minor selection includes that minor series, and a complete release selects that release. Users can also list downloadable releases available for the current platform, restricted by version.

- Users can explicitly download and install a requested Python release from Python Standalone Builds. Supported implementation choices are CPython and PyPy, with CPython as the default. Successful installation supplies an executable interpreter with its standard library, matching the requested release and implementation; an unavailable platform or release combination is refused as unavailable.

- Free-threaded Python can be requested when a corresponding distribution is available. Requests for free-threaded Python earlier than 3.13 are refused as unsupported. Malformed version requests are refused as invalid versions. These unsupported or malformed requests do not download a distribution or change managed installations.

- A request to install an existing valid, discoverable managed installation without explicit replacement is refused as already installed and preserves its distribution files. Explicit replacement restores the distribution's supplied files. A failed download is reported as an installation failure.

- Users can remove one or more Velnora-managed Python installations by exact release, implementation, and threading variant. Removal defaults to CPython and the standard threaded variant. It requires a complete major, minor, and patch version and refuses an incomplete version. It does not remove system-managed interpreters; a missing managed installation is reported as absent.

### FP-09: Project environments

- By default, project operations use a virtual environment whose Python satisfies the project's compatibility requirement. With no explicit project environment selection, an already active external virtual environment is reused, except for the base Conda environment; otherwise Velnora reuses a project environment or creates one. An incompatible environment already selected for reuse causes an incompatibility failure. Environments for distinct projects remain separately selectable.

- Users can select a locally available interpreter for a project, causing a suitable project environment to be selected or created, and can clear that selection to restore automatic selection. A missing interpreter is refused as unavailable. An explicitly chosen incompatible interpreter is refused as incompatible; when creating a new environment, automatic selection can choose another installed compatible interpreter and fails when none can be found. Project installation does not implicitly download Python.

- New environments normally use the active Python interpreter when compatible; users can instead request the interpreter used by Velnora. For new environments, users can choose storage within the project or in configured shared environment storage. With no location override, an existing in-project environment is recognized; explicitly disabling in-project environments excludes it from selection.

- When environment creation is disabled, an active external virtual environment is reused unless a project environment selection overrides it; otherwise an existing enabled in-project environment is used, or the system environment is used. An incompatible interpreter in the resulting environment is refused. Newly created environments exclude system-installed packages by default; users can explicitly expose system packages or omit the bundled package installer from the new environment.

- Users can inspect the selected environment's interpreter, version, implementation, location, and validity, and list the environments associated with the project while distinguishing the selected one. Removing selected or all project environments removes only the requested project's managed environments and clears a removed selection; a named environment belonging to another project is refused.

- Environment activation supplies a command that a caller can execute in the current shell to activate the selected environment. Shell-specific activation is available for POSIX-compatible shells, Bash, Zsh, mksh, Csh, Tcsh, Fish, Nushell, PowerShell, and the Windows command shell when the corresponding environment activation file exists. A missing applicable activation file is reported as unavailable activation.

### FP-10: Distribution building

- Building a package project creates both a source distribution and a wheel by default; users can request either format alone. An unsupported distribution format is refused as an invalid format selection. The resulting artifacts carry the project's identity, version, declared runtime requirements, extras, descriptive metadata, and declared executable and plugin entry points. A failed build is reported as a failure without claiming the requested artifacts were produced.

- Without explicit package selection, Velnora packages the module or package whose import name corresponds to the normalized project name with separators replaced by underscores. A matching module or package at the project root takes precedence over one in the source layout. If both a module file and a package directory match in the chosen layout, automatic selection is refused as ambiguous. Explicit selection replaces automatic selection and can include multiple packages, nested packages, alternative source locations, and relocated installation destinations. A selection restricted to one distribution format affects only that format. Missing selected package sources prevent a successful build.

- Package-file exclusions and Git ignore rules omit matching files; explicit inclusions override those exclusions for their applicable formats. An inclusion with no format restriction applies only to the source distribution, while an exclusion with no format restriction applies to both formats. Explicit license-file selection controls the included license material, and an explicitly empty selection includes none.

- README contents become the distribution's long description; multiple declared README files contribute in declaration order.

- For a project declaring a build backend and build requirements, building produces the distributions defined by that backend with the declared requirements available, including additional requirements declared by the backend. Caller-supplied build settings affect the backend's requested output. Projects supplying a native-extension build and the necessary build tools can produce distributions containing the generated extension. A missing build requirement or a failing custom build produces a build failure identifying the affected build.

- Users can choose the artifact destination and request that existing destination contents be cleaned before building. Without a cleanup request, unrelated destination contents are retained. When using Velnora's build backend, a requested local version label is reflected in the built distribution's version without changing the project's declared base version.

### FP-11: Dependency installation and synchronization

- For projects whose required plugins are already available, installation makes the dependencies selected by the lock, group selection, extras, and target environment available in the project environment. Packages become importable and their installed commands become executable. A changed required version replaces the installed version, while an already satisfied dependency is retained.

- Ordinary installation preserves unrelated installed packages and installed locked packages belonging only to unselected optional groups or extras. Synchronization additionally removes packages outside the selected locked dependency set. Synchronization preserves the root project and the environment's pre-existing package installer when it is not a project dependency, and does not delete packages supplied by the system environment outside the project environment.

- In package mode, the project itself is installed editably by default, making source changes available without reinstalling the project. Users can omit the root project, install only the root project, or omit directory dependencies including transitive directory dependencies. Installing only the root conflicts with excluding the root or selecting dependency groups and is refused as contradictory. Missing project source needed for root installation is reported as a project-installation failure.

- Project extras select their optional requirements, and users can select all declared extras. An unknown extra is refused as missing; combining all-extras selection with individually selected extras is refused as conflicting selection.

- Installation accepts compatible wheel and source distributions. A wheel incompatible with the target Python, operating system, or architecture is not installed. Installing a source distribution or source project supplies its built package contents, using its declared build requirements. Build settings supplied for that dependency affect the build, and additional project-declared build constraints restrict the versions of build requirements without becoming runtime dependencies. An unsatisfiable build requirement or failed build is reported as a build failure for that package.

- Users can disallow binary distributions or require binary distributions for all packages or named packages; by default both source and binary distributions are allowed. A restriction naming a package takes precedence over an opposing all-packages restriction. Naming the same package in both restrictions leaves no permitted distribution. If no distribution satisfies compatibility, policy, and locked integrity requirements, installation fails for the affected package.

- A dry run reports the proposed package installations, updates, and removals without applying them or writing project or lock changes. Users can request bytecode compilation of installed Python sources; compilation is off by default.

- Installation without a lock resolves the project and records a lock. Installation with a stale lock is refused with a requirement to refresh it, rather than silently replacing the selected releases.

### FP-12: Project plugin provisioning

- For a project declaring required plugins, project installation with plugins enabled ensures those requirements are satisfied. Compatible plugins already available in Velnora's environment are reused; missing plugins or required different versions become available to subsequent invocations for that project. Disabling plugins also suppresses automatic installation of project-required plugins.

- Project plugin requirements honor their version constraints and environment markers. A requirement whose marker does not apply to Velnora's environment is not provisioned. Project-specific plugin provisioning does not change globally installed plugins. When none of the applicable required plugins is already installed in Velnora's runtime, required plugin dependencies must be compatible with the versions of other runtime packages already installed; an incompatible request is reported as an unsatisfiable plugin installation.

### FP-13: Dependency maintenance

- Adding dependencies records their requirements in the project document, updates the lock document, and installs the resulting dependencies by default. A caller can choose the main group or a named group; a missing named group is created. With standard dependency declarations, a caller can add the dependency to an optional runtime extra. With only legacy runtime declarations, optional addition marks the dependency optional without creating an extra. Requested extras, markers, source restrictions, and editable source status remain part of the recorded requirement.

- Adding an indexed package without a version selects a suitable current release and records a caret-compatible range based on it. Adding an existing dependency without a replacement constraint leaves it unchanged and identifies that no addition occurred. Supplying a new constraint replaces the existing requirement; explicitly requesting the latest release refreshes its constraint. Adding the project as its own dependency is refused.

- For dependencies declared directly in the runtime dependency list or named groups, removal deletes the dependency from the specified group, or from all such groups when none is specified, updates the lock, and uninstalls dependencies no longer needed by the resulting project. A requested name absent from the selected runtime dependency list and groups is refused as missing; removing an empty group also removes references that would otherwise include that deleted group.

- Updating refreshes all dependencies or explicitly named direct or transitive dependencies to compatible releases and updates the lock and installation. The declared version constraints in the project document remain unchanged. Unselected locked dependencies are retained when compatible with the requested update. Group controls limit installation, not the all-groups lock solution. An explicitly requested package not declared or locked is refused as unknown, and supplying a version constraint in place of an update package name is refused.

- Adding, removing, and updating can be restricted to declarations and locking without changing installed packages, or previewed without changing declarations, lock selections, or installed packages. A failed addition or removal does not commit its proposed project declaration or lock changes; a dependency-resolution failure identifies the incompatible request.

### FP-14: Project creation and initialization

- Creating a project produces a usable package source, test starting point, README, and a project document with build-system metadata. Users can supply the project name independently of the destination and can create a namespace package. The default source layout separates package sources from the project root; a flat layout can be selected. Creation refuses a nonempty destination rather than replacing its contents.

- Initializing an existing directory creates its project metadata without generating package or test source trees. Existing unrelated project-document content is preserved. An existing build-system declaration is refused as already initialized; an existing README can be referenced without creating one.

- Creation and initialization accept the project's description, authorship, license, Python compatibility, and runtime and development dependencies, either interactively or from supplied inputs. Accepted values are reflected in the resulting project declaration. The initial version defaults to 0.1.0 and can be changed interactively. Without an explicit Python requirement, the project accepts the preferred interpreter's major-and-minor release and newer versions, without an upper bound. Malformed dependency requirements are rejected without modifying the destination's existing contents.

### FP-15: Dependency inspection

- Dependency inspection lists locked package identities, versions, and descriptions for the selected groups and current environment. It distinguishes installed packages from locked packages absent from that environment. Users can request all locked packages, including those outside the selected groups or inapplicable to the current system, or restrict the result to direct dependencies. Inspection requiring a lock reports a missing lock as a prerequisite failure. Dependency inspection leaves project declarations and the lock unchanged.

- Inspecting a named dependency exposes its own requirements and the packages requiring it. A dependency tree starts at the project's direct dependencies or a requested package and displays each dependency path, repeating a shared dependency and its descendants under each parent. A cycle-closing dependency is marked and that path ends there. A list reason view identifies immediate requiring packages; a named package's reason tree starts at each immediate requiring package and includes the named package and its dependency paths. A requested package absent from the lock is reported as missing.

- Users can inspect available newer releases alongside locked releases or restrict the report to packages with a newer release. The report distinguishes a currently selected release from an available upgrade and obtains indexed candidates from the locked package's source. This inspection can show releases beyond the project's declared dependency version constraint; it does not change that constraint or the lock.

- Diagnostic resolution reports the selected package versions without installing them or replacing the lock. Users can request a target Python version and inspect the dependencies applicable to that target; an unsatisfiable request reports the resolution conflict. Environment diagnostics expose the selected interpreter's release, implementation, executable and environment locations, platform, and accepted wheel compatibility tags. These diagnostics leave project declarations, the lock and installed packages unchanged.

- Searching configured primary and supplemental simple repositories that publish a package-name listing returns packages whose names contain any supplied search term, with their available versions and source identity. Repeated matches for the same package version from the same source are not duplicated; matches from different sources remain distinguishable. A search with no matches reports an empty result.

### FP-16: Command execution

- Users can execute a command or Python script in the selected project environment. The invoked program receives the user's arguments, including option-like arguments, and observes the selected environment's interpreter and installed dependencies. Its completion status is returned to the caller.

- Installed console scripts declared by the project are executable in that environment and invoke their declared application entry. Reinstalling the project after changing its script declarations makes the changed commands available. A requested executable that cannot be found is reported as an unavailable command.

### FP-17: Project version management

- Users can read the current project version or replace it with a valid PEP 440 version. A successful change updates every existing project-version declaration in the project document and exposes the new version; malformed replacement versions are refused without changing the document. A preview exposes the proposed version without modifying the document.

- Version changes can increment the major, minor or patch component, start a prerelease at any of those levels, or advance a prerelease. For a stable major-minor-patch release, a major or minor increment raises that component by one and resets lower components to zero; a patch increment raises the patch by one. The three corresponding pre-release increments use the new release with an initial alpha prerelease numbered zero.

- A prerelease increment on a stable release starts the next patch's alpha prerelease at zero. On an existing prerelease it advances that prerelease's number by one without changing its phase. Requesting the next phase instead changes alpha to beta, beta to release candidate, or release candidate to the final release, starting each new prerelease phase at zero. A patch increment on a prerelease finalizes its current release; major and minor increments finalize the current release when it is already a prerelease of that component's boundary, and otherwise advance the component.

### FP-18: Distribution publishing

- Publishing selects source and wheel distributions bearing the current project's name from the selected artifact directory. It uploads only the highest version present for that name, ordered according to PEP 440 using the artifact versions, even if that differs from the project's declared version. Publication targets PyPI by default or a selected configured publishing repository. Explicit publishing repository configuration takes precedence over a dependency source with the same name. When no explicit publishing destination has that name, the corresponding dependency source location can be used for publication. An unknown publishing destination or an absence of matching distributions is refused as a missing prerequisite.

- Publishing can explicitly build the project before selecting distributions for publication. A failed build prevents publication. A publishing dry run prepares the publication without uploading artifacts.

- Publishing uses a complete explicitly supplied username and password in preference to configured credentials. Otherwise it uses the selected repository's configured token in preference to its configured username and password. Explicitly supplied certificate material takes precedence over repository certificate settings. Authentication rejection, connection failure, and upload rejection produce a publishing failure; they are not reported as completed publication.

- A user can request that artifacts already present in the repository be skipped. With that request, a repository response identifying an already existing artifact does not prevent other artifacts from being uploaded; unrelated upload failures remain failures. Without the request, an already-existing-artifact rejection is a publishing failure.

### FP-19: Velnora runtime management

- Users can add, remove, inspect, lock, install, and synchronize additional packages in Velnora's own runtime environment, including plugins. These operations manage Velnora's runtime declarations and installed packages separately from the current project's dependencies. Added packages must be compatible with Velnora's runtime requirements; unsatisfiable additions fail with their dependency conflict.

- Runtime installation makes declared add-ons available, while runtime synchronization additionally removes untracked add-ons without removing Velnora and its required dependencies. Users can inspect all runtime packages, restrict inspection to add-ons and their dependencies, and list installed plugins with their versions and requirements. An absent runtime lock prevents lock-based inspection and is reported as a missing prerequisite.

- Updating Velnora selects and installs a compatible Velnora release and its dependencies, with a requested version constraint when supplied. Stable releases are preferred by default, and preview selection permits prereleases. Package sources configured for Velnora's runtime govern this operation; sources of the current project do not replace them, and existing runtime source configuration is preserved.

- Runtime package changes and Velnora updates can be previewed without altering installed runtime packages. The preview distinguishes proposed installations, removals, and version changes from an already satisfied request.

### FP-20: Repository cache management

- Users can list the repository caches currently present and distinguish an empty cache collection from one containing named repository caches.

- Users can clear all repository metadata caches, a selected repository's cache, or one package version within a selected repository. Only the selected scope is removed; declining interactive confirmation leaves it intact. A missing entry is reported as absent. Clearing an entire scope requires an explicit all-entries request, while specifying a package without its version is refused as incomplete selection.

- Users can request current repository metadata for a single invocation despite previously stored metadata. That invocation obtains the required package metadata from the repository instead of returning an older stored result. The request does not delete the stored repository caches.
