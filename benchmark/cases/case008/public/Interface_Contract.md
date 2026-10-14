# Interface Contract

### Product overview

**Hrefparse** is an embeddable C++20 library (with a matching C interface) that parses, normalizes, inspects and mutates URLs, handles URL Search Params, converts domains with IDNA, and compiles and matches URLPatterns. Behaviour is specified in the Full PRD; this document is the shell: where the entries are, how they are called, and the form of every value they hand back.

The finished product is a **library**, not a network service and not an importable Python package. There is no wire protocol, no product configuration file, and no product-owned process exit code: outcomes are reported only through the return values described below. The optional command-line tool `hrefparsec` is not part of this required surface.

### Repository layout and artifacts

- **Headers.** The public C++ umbrella header is `hrefparse.h`; the public C header is `hrefparse_c.h`. Both sit at the root of the include directory `include/` at the repository root, so a translation unit compiles with `#include "hrefparse.h"` or `#include "hrefparse_c.h"` given `-Iinclude`. Nested headers are reached through `hrefparse.h`. A documented single-header amalgamation is an alternative distribution of the same C++ API.
- **Library.** The CMake project, the library target and the link stem are `hrefparse`. Configuring from the repository root with the build directory `build` (`cmake -B build`, then `cmake --build build`) produces the library file `libhrefparse.a` or `libhrefparse.so` in `build/src/`, `build/`, or `build/lib/`. The headers declare the entries; their definitions live in that library file, so a program must link it (with a C++ driver, since the implementation needs the C++ standard library). C callers link the same library.
- **Compile definition.** C++ programs that use the library are compiled with `HREFPARSE_USE_UNSAFE_STD_REGEX_PROVIDER` always defined (`-DHREFPARSE_USE_UNSAFE_STD_REGEX_PROVIDER`); C programs are compiled without it. The headers must compile in both cases. Whether the define exposes a `std::regex`-backed engine is the implementer's choice; callers supply their own engine.
- **CLI.** The optional tool's basename is `hrefparsec`; it is absent unless tools are enabled at configure time.

### Value forms

- **Strings.** All string inputs are byte strings (ASCII or UTF-8) given as `std::string_view` in C++ or as a `const char*` buffer plus a `size_t` byte length in C (the buffer need not be NUL-terminated; a `char*` is accepted).
- **C++ parse result.** `hrefparse::result<T>` is `tl::expected<T, hrefparse::errors>` and is reachable through `hrefparse.h` without another include. A success converts to `true`, exposes `T` through `operator->`, and through unary `*` (so `&*r` is a `T*`). A failure converts to `false` and yields no usable object. The members of `hrefparse::errors` are the implementer's choice.
- **C views.** `hrefparse_string` is `struct { const char* data; size_t length; }`. A view returned from a URL handle stays valid only until that handle is mutated or freed; a view returned from a search-params handle or a string list stays valid until that object is mutated or freed.
- **C owned strings.** `hrefparse_owned_string` is `struct { const char* data; size_t length; }` and is released with `hrefparse_free_owned_string`. For the standalone IDNA entries, a usable domain is one with non-null `data` and non-zero `length`; null `data` or zero `length` means "no usable domain".
- **Booleans.** Every yes/no and accepted/refused report is `bool` (C: a boolean-convertible value).
- **Host kind.** C++ public data member `host_type` of the URL object, C `hrefparse_get_host_type` (`uint8_t`); both convert to `unsigned`. The three numeric values for domain, IPv4 and IPv6 are the implementer's choice, provided they are distinct.
- **Length cap.** `uint32_t` byte count; the default is the maximum 32-bit unsigned integer.
- **Search and hash writers** return nothing (C++ return type free, callers ignore it; C `void`).

### C++ entries (`#include "hrefparse.h"`, namespace `hrefparse`)

```
hrefparse::result<hrefparse::url_aggregator> hrefparse::parse(std::string_view input);
hrefparse::result<hrefparse::url_aggregator> hrefparse::parse(std::string_view input,
                                                   const hrefparse::url_aggregator* base_url);
bool hrefparse::can_parse(std::string_view input);
bool hrefparse::can_parse(std::string_view input, const std::string_view* base_input);
std::string hrefparse::href_from_file(std::string_view path);
void hrefparse::set_max_input_length(uint32_t length);
uint32_t hrefparse::get_max_input_length();
```

- `parse`: the second argument is an already-parsed base obtained as `&*r` of a successful result. `hrefparse::url_aggregator` is the default result type; `hrefparse::url` is an alternative layout with the same members.
- `can_parse`: the second argument points to the base URL **string**, not a parsed URL.
- `href_from_file`: returns the `file:` href, or `""` when the conversion fails.

**URL object** (`hrefparse::url_aggregator`, reached through `operator->` of a successful result):

```
std::string_view get_href() const;      std::string get_origin() const;
std::string_view get_protocol() const;  std::string_view get_username() const;
std::string_view get_password() const;  std::string_view get_host() const;
std::string_view get_hostname() const;  std::string_view get_port() const;
std::string_view get_pathname() const;  std::string_view get_search() const;
std::string_view get_hash() const;
bool has_credentials() const;  bool has_hostname() const;  bool has_port() const;
bool has_search() const;       bool has_hash() const;
void clear_port();  void clear_search();  void clear_hash();
bool set_href(std::string_view);      bool set_protocol(std::string_view);
bool set_username(std::string_view);  bool set_password(std::string_view);
bool set_host(std::string_view);      bool set_hostname(std::string_view);
bool set_port(std::string_view);      bool set_pathname(std::string_view);
void set_search(std::string_view);    void set_hash(std::string_view);
/* public data member */ host_type;   // converts to unsigned
```

Reader values: `get_origin` is the serialized origin; `get_protocol` includes the trailing `:`; `get_port` is the decimal port without a colon or the empty string; `get_search` / `get_hash` carry their leading `?` / `#` or are empty. Writers' `bool` is `true` for accepted, `false` for refused.

**URL Search Params** (`hrefparse::url_search_params`):

```
explicit url_search_params(const std::string_view input);
size_t size() const noexcept;
void append(std::string_view key, std::string_view value);
std::optional<std::string_view> get(std::string_view key);
std::vector<std::string> get_all(std::string_view key);
bool has(std::string_view key) noexcept;
bool has(std::string_view key, std::string_view value) noexcept;
void set(std::string_view key, std::string_view value);
void remove(std::string_view key);
void remove(std::string_view key, std::string_view value);
void sort();
std::string to_string() const;
void reset(std::string_view input);
url_search_params_keys_iter get_keys();
url_search_params_values_iter get_values();
url_search_params_entries_iter get_entries();
```

`get` returns an empty optional for a missing key. `to_string` returns the serialization without a leading `?`. The iterator types `hrefparse::url_search_params_keys_iter`, `hrefparse::url_search_params_values_iter`, `hrefparse::url_search_params_entries_iter` each have `bool has_next() const` and `next()`; `next()` returns `std::optional<std::string_view>` for keys and values and `std::optional<std::pair<std::string_view, std::string_view>>` (key, value) for entries.

**URLPattern** (C++ only):

```
template <class regex_provider>
tl::expected<hrefparse::url_pattern<regex_provider>, hrefparse::errors>
hrefparse::parse_url_pattern(std::string_view input, const std::string_view* base_url,
                             const hrefparse::url_pattern_options* options);
template <class regex_provider>
tl::expected<hrefparse::url_pattern<regex_provider>, hrefparse::errors>
hrefparse::parse_url_pattern(hrefparse::url_pattern_init input, const std::string_view* base_url,
                             const hrefparse::url_pattern_options* options);
```

Callers write `hrefparse::parse_url_pattern<Engine>(…)`. The base pointer is null when absent (with an initializer, the base is the initializer's `base_url` and the pointer is null); the options pointer may point to a default-constructed object. A compile failure is a falsy result with no usable pattern.

```
struct url_pattern_init {           // default-constructible; members assigned from std::string
  std::optional<std::string> protocol, username, password, hostname, port,
                             pathname, search, hash, base_url;
};
struct url_pattern_options {        // default-constructible
  bool ignore_case;                 // defaults to false
};
using url_pattern_input = std::variant<std::string_view, hrefparse::url_pattern_init>;

// hrefparse::url_pattern<regex_provider>, reached through operator-> of a successful compile
bool has_regexp_groups() const;
std::string_view get_protocol() const;  std::string_view get_username() const;
std::string_view get_password() const;  std::string_view get_hostname() const;
std::string_view get_port() const;      std::string_view get_pathname() const;
std::string_view get_search() const;    std::string_view get_hash() const;
hrefparse::result<bool> test(const url_pattern_input& input, const std::string_view* base_url);
hrefparse::result<std::optional<hrefparse::url_pattern_result>>
    exec(const url_pattern_input& input, const std::string_view* base_url);

struct url_pattern_result {
  url_pattern_component_result protocol, username, password, hostname,
                               port, pathname, search, hash;
};
struct url_pattern_component_result {
  std::string input;
  /* map-like, sized, range-for over pairs */ groups;   // first: std::string name;
                                                         // second: std::optional<std::string>
};
```

`test` / `exec` are called with a URL string or an initializer and a null base pointer. `*test(...)` is the yes/no. `exec`'s optional is empty for no-match and filled for a match. In `groups`, a group without a captured value is either missing from the map or present with an empty optional (the implementer's choice). `get_<component>` returns that component's compiled pattern string.

**Engine shape** required of `regex_provider`:

```
using regex_type = /* engine regex object */;
static std::optional<regex_type> create_instance(std::string_view pattern, bool ignore_case);
static std::optional<std::vector<std::optional<std::string>>>
    regex_search(std::string_view input, const regex_type& pattern);
static bool regex_match(std::string_view input, const regex_type& pattern);
```

`pattern` is one component's regular expression in ECMAScript syntax; `ignore_case` is the options flag. `std::nullopt` from `create_instance` means the engine cannot create that expression. `regex_search` returns an empty outer optional for no match, otherwise one entry per capturing group in group order (`std::nullopt` for a group that did not participate). `regex_match` returns whether the whole input matches.

### C entries (`#include "hrefparse_c.h"`)

Handles: `hrefparse_url` (URL), `hrefparse_url_search_params`, `hrefparse_strings` (string list), `hrefparse_url_search_params_keys_iter`, `hrefparse_url_search_params_values_iter`, `hrefparse_url_search_params_entries_iter`; all opaque. `hrefparse_string_pair` is `struct { hrefparse_string key; hrefparse_string value; }`.

```
hrefparse_url hrefparse_parse(const char* input, size_t length);
hrefparse_url hrefparse_parse_with_base(const char* input, size_t input_length,
                                        const char* base, size_t base_length);
bool hrefparse_can_parse(const char* input, size_t length);
bool hrefparse_can_parse_with_base(const char* input, size_t input_length,
                                   const char* base, size_t base_length);
bool hrefparse_is_valid(hrefparse_url result);
void hrefparse_free(hrefparse_url result);

hrefparse_string hrefparse_get_href(hrefparse_url result);
hrefparse_owned_string hrefparse_get_origin(hrefparse_url result);
hrefparse_string hrefparse_get_protocol(hrefparse_url result);
hrefparse_string hrefparse_get_username(hrefparse_url result);
hrefparse_string hrefparse_get_password(hrefparse_url result);
hrefparse_string hrefparse_get_host(hrefparse_url result);
hrefparse_string hrefparse_get_hostname(hrefparse_url result);
hrefparse_string hrefparse_get_port(hrefparse_url result);
hrefparse_string hrefparse_get_pathname(hrefparse_url result);
hrefparse_string hrefparse_get_search(hrefparse_url result);
hrefparse_string hrefparse_get_hash(hrefparse_url result);
uint8_t hrefparse_get_host_type(hrefparse_url result);

bool hrefparse_set_href(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_protocol(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_username(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_password(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_host(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_hostname(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_port(hrefparse_url result, const char* input, size_t length);
bool hrefparse_set_pathname(hrefparse_url result, const char* input, size_t length);
void hrefparse_set_search(hrefparse_url result, const char* input, size_t length);
void hrefparse_set_hash(hrefparse_url result, const char* input, size_t length);
void hrefparse_clear_port(hrefparse_url result);
void hrefparse_clear_search(hrefparse_url result);
void hrefparse_clear_hash(hrefparse_url result);
bool hrefparse_has_credentials(hrefparse_url result);
bool hrefparse_has_hostname(hrefparse_url result);
bool hrefparse_has_port(hrefparse_url result);
bool hrefparse_has_search(hrefparse_url result);
bool hrefparse_has_hash(hrefparse_url result);

void hrefparse_set_max_input_length(uint32_t length);
uint32_t hrefparse_get_max_input_length(void);
hrefparse_owned_string hrefparse_idna_to_ascii(const char* input, size_t length);
hrefparse_owned_string hrefparse_idna_to_unicode(const char* input, size_t length);
void hrefparse_free_owned_string(hrefparse_owned_string owned);

hrefparse_url_search_params hrefparse_parse_search_params(const char* input, size_t length);
void hrefparse_free_search_params(hrefparse_url_search_params result);
size_t hrefparse_search_params_size(hrefparse_url_search_params result);
hrefparse_owned_string hrefparse_search_params_to_string(hrefparse_url_search_params result);
hrefparse_string hrefparse_search_params_get(hrefparse_url_search_params result,
                                             const char* key, size_t key_length);
hrefparse_strings hrefparse_search_params_get_all(hrefparse_url_search_params result,
                                                  const char* key, size_t key_length);
bool hrefparse_search_params_has(hrefparse_url_search_params result,
                                 const char* key, size_t key_length);
bool hrefparse_search_params_has_value(hrefparse_url_search_params result,
                                       const char* key, size_t key_length,
                                       const char* value, size_t value_length);
void hrefparse_search_params_append(hrefparse_url_search_params result,
                                    const char* key, size_t key_length,
                                    const char* value, size_t value_length);
void hrefparse_search_params_set(hrefparse_url_search_params result,
                                 const char* key, size_t key_length,
                                 const char* value, size_t value_length);
void hrefparse_search_params_remove(hrefparse_url_search_params result,
                                    const char* key, size_t key_length);
void hrefparse_search_params_remove_value(hrefparse_url_search_params result,
                                          const char* key, size_t key_length,
                                          const char* value, size_t value_length);
void hrefparse_search_params_sort(hrefparse_url_search_params result);
void hrefparse_search_params_reset(hrefparse_url_search_params result,
                                   const char* input, size_t length);
size_t hrefparse_strings_size(hrefparse_strings result);
hrefparse_string hrefparse_strings_get(hrefparse_strings result, size_t index);
void hrefparse_free_strings(hrefparse_strings result);

hrefparse_url_search_params_keys_iter hrefparse_search_params_get_keys(hrefparse_url_search_params);
bool hrefparse_search_params_keys_iter_has_next(hrefparse_url_search_params_keys_iter);
hrefparse_string hrefparse_search_params_keys_iter_next(hrefparse_url_search_params_keys_iter);
void hrefparse_free_search_params_keys_iter(hrefparse_url_search_params_keys_iter);
hrefparse_url_search_params_values_iter hrefparse_search_params_get_values(hrefparse_url_search_params);
bool hrefparse_search_params_values_iter_has_next(hrefparse_url_search_params_values_iter);
hrefparse_string hrefparse_search_params_values_iter_next(hrefparse_url_search_params_values_iter);
void hrefparse_free_search_params_values_iter(hrefparse_url_search_params_values_iter);
hrefparse_url_search_params_entries_iter hrefparse_search_params_get_entries(hrefparse_url_search_params);
bool hrefparse_search_params_entries_iter_has_next(hrefparse_url_search_params_entries_iter);
hrefparse_string_pair hrefparse_search_params_entries_iter_next(hrefparse_url_search_params_entries_iter);
void hrefparse_free_search_params_entries_iter(hrefparse_url_search_params_entries_iter);
```

- Every handle from `hrefparse_parse` / `hrefparse_parse_with_base` (valid or not) is released with `hrefparse_free`; success is read with `hrefparse_is_valid` before any component is read. The C entries take the base as a string, unlike the C++ two-argument `parse`.
- `hrefparse_get_origin`, `hrefparse_idna_to_ascii`, `hrefparse_idna_to_unicode` and `hrefparse_search_params_to_string` return owned strings released with `hrefparse_free_owned_string`; every other C reader returns a view.
- Search-params handles are released with `hrefparse_free_search_params`, string lists with `hrefparse_free_strings`, iterators with their matching `hrefparse_free_search_params_*_iter`. `hrefparse_search_params_get` of a missing key returns a view whose content is the implementer's choice; presence is read with `hrefparse_search_params_has`. Lists are indexed from 0 to `hrefparse_strings_size` − 1.
- Iterators are walked with `*_has_next` before each `*_next`.
- URLPattern has no C entry.
