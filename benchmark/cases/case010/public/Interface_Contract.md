# Interface Contract

### Product overview

`lingora` is a Python natural-language processing library with a command-line group. This document is the library's shell: the package and its submodules, every public entry with its signature, what each entry takes, what it returns, the packaged-resource locations it reads, and how a failure shows from outside. What each entry computes is stated in the product requirements (PRD); this document does not restate it.

### Shape of the public surface

The product is an **importable Python library** with a flat package layout: one importable package directory `lingora` at the repository root. The installable distribution and the import package are both named `lingora`. Python 3.10 or newer. It is not a network service and not a wire protocol, and it has no product-owned configuration file. Importing the package downloads nothing.

**Calls and failures.** Every entry is a Python callable. A call that succeeds returns the value described for that entry. A call that does not succeed raises an exception. A refusal never shows as a returned empty list, empty string, `0` or `None`, unless an entry below says otherwise. Exception classes and message wording are the implementer's choice, except where an entry below states what a message contains.

**Parameters.** In the signatures below, a parameter written `name=…` has a default. The PRD states the default's behaviour wherever it matters. Parameters not shown are the implementer's choice, as long as callers that pass only the shown arguments get the stated behaviour. Positional parameters are shown first, and every shown parameter may also be passed by keyword.

**Numbers.** A score or distance is a real number: an `int` or a `float`, never a `bool`.

### Packaged resources — `lingora.data`

`from lingora import data`

- `data.path` — a mutable `list` of directory strings searched for packaged resources. A caller may replace its contents in place after importing the package and before calling any entry that needs a resource. Such calls then find resources only in the listed directories. An empty list means no packaged resource is visible. The list's initial contents are the implementer's choice.

Resource names, relative to a directory on `data.path`:

| Resource | Name |
| --- | --- |
| Punkt sentence model for `<language>` | `tokenizers/punkt_tab/<language>/` (English: `tokenizers/punkt_tab/english/`) |
| English averaged perceptron tagger | `taggers/averaged_perceptron_tagger_eng/` |
| Russian averaged perceptron tagger | `taggers/averaged_perceptron_tagger_rus/` |
| Universal tagset tables | `taggers/universal_tagset/` |
| Named-entity chunker model | `chunkers/maxent_ne_chunker_tab/english_ace_multiclass/` |
| English wordlist | `corpora/words` |
| Stopwords list for `<language>` | `corpora/stopwords/<language>`: a UTF-8 text file holding one word per line, with the Snowball language name as file name |
| WordNet | `corpora/wordnet` |

Each model directory holds the files of the packaged resource of that name, in their published layout.

The model files the library reads, all UTF-8 text, are read as shipped. In a text file, each line without its line terminator is one entry.

| Resource | Files in the directory |
| --- | --- |
| Punkt sentence model | `abbrev_types.txt`: one `<type>` per line. `sent_starters.txt`: one `<type>` per line. `collocations.tab`: one `<type>` TAB `<type>` per line. `ortho_context.tab`: one `<type>` TAB `<integer>` per line. |
| Averaged perceptron tagger (`<lang>` is `eng` or `rus`) | `averaged_perceptron_tagger_<lang>.weights.json`: a JSON object `{"<feature>": {"<tag>": <number>, …}, …}`. `averaged_perceptron_tagger_<lang>.tagdict.json`: a JSON object `{"<word>": "<tag>", …}`. `averaged_perceptron_tagger_<lang>.classes.json`: a JSON array `["<tag>", …]`, the tags the model can assign. |
| Universal tagset tables | `en-ptb.map`: one `<Penn Treebank tag>` TAB `<universal tag>` per line. Other files in the directory are not read for English. |

- In the Punkt files, `<type>` is a lowercased word form, written without its final period for an abbreviation, or the literal `##number##`, which stands for any number.
- The `ortho_context.tab` `<integer>` is a bit set of orthographic observations of that type: `2` upper-case at a sentence start, `4` upper-case inside a sentence, `8` upper-case in an unknown position, `16` lower-case at a sentence start, `32` lower-case inside a sentence, `64` lower-case in an unknown position. A type absent from the file has no observation.

### Tokenizers — `lingora.tokenize`

`from lingora.tokenize import RegexpTokenizer, TreebankWordTokenizer, TweetTokenizer, WhitespaceTokenizer, WordPunctTokenizer, blankline_tokenize, sent_tokenize, word_tokenize, wordpunct_tokenize` (the submodule is also `from lingora import tokenize`).

```
wordpunct_tokenize(text)                      -> list[str]   # word/punctuation tokenizer
WordPunctTokenizer().tokenize(text)           -> list[str]   # same tokenizer
WordPunctTokenizer().span_tokenize(text)      -> iterable of (start, end)
TreebankWordTokenizer().tokenize(text)        -> list[str]   # Penn Treebank tokenizer
word_tokenize(text, language=…, preserve_line=…) -> list[str] # recommended word tokenizer
sent_tokenize(text, language=…)               -> list[str]   # recommended sentence tokenizer
WhitespaceTokenizer().tokenize(text)          -> list[str]
blankline_tokenize(text)                      -> list[str]   # segments
RegexpTokenizer(pattern, gaps=…, discard_empty=…).tokenize(text) -> list[str]
TweetTokenizer(preserve_case=…, reduce_len=…, strip_handles=…).tokenize(text) -> list[str]
```

- `text` and `pattern` are `str`. `pattern` is a Python regular expression. `gaps`, `discard_empty`, `preserve_line`, `preserve_case`, `reduce_len` and `strip_handles` are `bool`.
- `language` is a Punkt language directory name, such as `english`.
- `preserve_line=True` treats `text` as one already-delimited line, with no sentence splitting. `preserve_line=False` splits sentences first.
- Each element of a returned list is one token: a sentence string for `sent_tokenize`, or a segment string for `blankline_tokenize`.
- `span_tokenize` yields one `(start, end)` pair of `int` character offsets per token.
- When the Punkt model is not visible, `sent_tokenize` and `word_tokenize(..., preserve_line=False)` raise.

### Command line — `lingora.cli`

`from lingora.cli import cli` — a command group object. Its program entry is:

```
cli.main(args=<list of str>, standalone_mode=True)
```

- `args=['tokenize']` runs the tokenize command. It reads UTF-8 text from standard input. For every input line it writes one line to standard output: the line's tokens joined by the delimiter (a single space by default), ending with a newline.
- With `standalone_mode=True`, `main` ends the process: exit status 0 on success and a non-zero status on failure. On failure no token line is written for the failed input. The exact non-zero status, any standard-error text, and any progress display on standard error are the implementer's choice.
- Further options of the command (language, delimiter, encoding) are the implementer's choice.

### Stemmers — `lingora.stem`

`from lingora.stem import ARLSTem, ARLSTem2, LancasterStemmer, PorterStemmer, RegexpStemmer, SnowballStemmer, WordNetLemmatizer`

```
PorterStemmer().stem(word, to_lowercase=…)    -> str   # default mode
LancasterStemmer().stem(word)                 -> str
SnowballStemmer(language, ignore_stopwords=…).stem(word) -> str
ARLSTem().stem(word)                          -> str
ARLSTem2().stem(word)                         -> str
RegexpStemmer(regexp).stem(word)              -> str
WordNetLemmatizer().lemmatize(word)           -> str
```

- `word` is a `str` and is treated as one token. `to_lowercase` and `ignore_stopwords` are `bool`. `regexp` is a Python regular-expression string.
- `language` is one of the names `arabic`, `danish`, `dutch`, `english`, `finnish`, `french`, `german`, `hungarian`, `italian`, `norwegian`, `porter`, `portuguese`, `romanian`, `russian`, `spanish`, `swedish`.
- An unsupported `language` makes the `SnowballStemmer` constructor raise, and the exception message contains the requested name.
- When `ignore_stopwords=True` and that language's stopwords list is not visible, the `SnowballStemmer` constructor raises.
- When WordNet is not visible, `WordNetLemmatizer` raises, either at construction or from `lemmatize`.

### Taggers — `lingora.tag`

`from lingora.tag import DefaultTagger, RegexpTagger, UnigramTagger, pos_tag` (the submodule is also `from lingora import tag`).

```
DefaultTagger(tag)
UnigramTagger(train=<tagged sentences>, backoff=…)
RegexpTagger(regexps, backoff=…)
<tagger>.tag(tokens)                          -> list[tuple[str, str | None]]
pos_tag(tokens, tagset=…, lang=…)             -> list[tuple[str, str | None]]
```

- `tokens` is a `list` of `str`.
- `train` is a `list` of sentences. Each sentence is a `list` of `(token, tag)` pairs.
- `regexps` is a `list` of `(<pattern>, <tag>)` pairs, each a regular-expression string and a tag string.
- `backoff` is another tagger, or `None`.
- `pos_tag` arguments:
  - `lang` is `'eng'` (the default) or `'rus'`.
  - `tagset` is `None` (the default: native tags) or `'universal'`.
  - A `str` passed as `tokens` is refused by raising.
  - Any other `lang`, and a missing model for the requested `lang`, also make the call raise.
- The result holds one `(token, tag)` tuple per input token, in order. `token` is the input token. `tag` is a `str`, or `None` when no tag is assigned.

### Chunking — `lingora.chunk`

`from lingora.chunk import RegexpParser, ne_chunk` (the submodule is also `from lingora import chunk`).

```
RegexpParser(grammar)
<parser>.parse(tagged)                        -> Tree
ne_chunk(tagged_tokens)                       -> Tree
```

- `tagged` and `tagged_tokens` are `list`s of `(token, tag)` pairs.
- `grammar` is a `str`, or a list of chunk-parser stages (the stage objects are the implementer's choice). Any other value makes the constructor raise.
- `ne_chunk` raises when the named-entity model or the English wordlist is not visible.
- **Grammar text.**
  - A grammar is one or more clauses. A clause begins with a line `<LABEL>: <pattern>`. Further patterns of the same clause follow on indented lines.
  - A pattern is `{<tag pattern>}` (a chunk rule) or `}<tag pattern>{` (a chink rule).
  - A tag pattern is a sequence of elements `<…>`, each optionally followed by a quantifier `?`, `*`, `+` or `{m,n}` / `{m,}`. An element's content is a regular expression over a tag, which may use `.`, `*` and `|`.
- **Result.** The result is a `Tree` (see Trees below):
  - The root's label is the default sentence label. Its spelling is the implementer's choice.
  - Its children are, in order, the input `(token, tag)` pairs that are in no chunk, and one `Tree` per chunk.
  - A chunk's label is its clause's `<LABEL>`, and its children are its `(token, tag)` pairs.

### Grammars and parsers — `lingora.grammar`, `lingora.parse`

`from lingora.grammar import CFG`; `from lingora.parse import ChartParser, ShiftReduceParser`; `from lingora.parse.generate import generate`.

```
CFG.fromstring(input)                         -> CFG
<cfg>.start()                                 -> symbol
<cfg>.productions()                           -> list of Production
<production>.rhs()                            -> sequence of (symbol | str)
ChartParser(grammar).parse(tokens)            -> iterator of Tree
ShiftReduceParser(grammar).parse(tokens)      -> iterator of Tree
generate(grammar, start=…, depth=…, n=…)      -> iterator of list[str]
```

- **Grammar text.**
  - The text has one production per line, written `<LHS> -> <RHS>`. Blank lines are ignored.
  - `<RHS>` is a space-separated sequence of nonterminals (unquoted identifiers) and terminals (single- or double-quoted text). `|` separates alternatives.
  - A production with nothing after `->` is an empty production.
- **Grammar objects.**
  - A nonterminal is returned as a symbol: a `str`, or an object whose `str()` is the nonterminal's name. Which of the two is the implementer's choice.
  - In `rhs()`, a terminal appears as a `str` equal to the quoted text, without the quotes. A nonterminal appears as a symbol that is not a `str`.
  - `productions()` holds one `Production` per alternative.
- **Parsing.**
  - `tokens` is a `list` of `str`.
  - `parse` returns zero or more trees. A token list the grammar does not derive gives an empty iterator.
  - A token that no production produces makes `parse` raise. The exception is raised by the call or by the first iteration of its result.
- **Generation.**
  - `n` is an `int` or `None`: the maximum number of sentences, or no limit.
  - `depth` is an `int` or `None`: the derivation depth bound.
  - `start` is a symbol, or `None` for the grammar's start symbol.
  - Each sentence is a `list` of `str` tokens.

### Trees — `lingora.tree`

`from lingora.tree import Tree` (the submodule is also `from lingora import tree`).

```
Tree(label, children)                         -> Tree
Tree.fromstring(s)                            -> Tree
<tree>.label()                                -> str
<tree>.leaves()                               -> list[str]
<tree>.pformat()                              -> str
```

- Iterating a tree, `len(tree)` and `tree[i]` give its immediate children, which are `str` leaves or trees. `==` compares two trees.
- `children` must be a list of children. A `str` given as `children`, or omitting `children`, makes `Tree` raise. `Tree(label, [])` is a tree with no children.
- `s` is bracketed tree text: `(<label> <child> …)`, where a child is a nested bracketed node or a leaf token, separated by whitespace.
- `pformat()` returns the pretty-printed text as a `str`. Its layout is the implementer's choice.

### Classifiers — `lingora.classify`

`from lingora.classify import NaiveBayesClassifier, DecisionTreeClassifier, accuracy` (the submodule is also `from lingora import classify`).

```
NaiveBayesClassifier.train(labeled_featuresets)   -> NaiveBayesClassifier
DecisionTreeClassifier.train(labeled_featuresets) -> DecisionTreeClassifier
<classifier>.classify(featureset)             -> label
<naive bayes>.prob_classify(featureset)       -> ProbDist
<naive bayes>.labels()                        -> list of labels
accuracy(classifier, gold)                    -> number
```

- `labeled_featuresets` and `gold` are `list`s of `(featureset, label)` pairs. A featureset is a `dict` from feature names to values. A label is any hashable value.
- A `ProbDist` has `prob(<label>)`, which returns that label's probability as a `float`, and `samples()`, which returns the labels.

### Metrics — `lingora.metrics`, `lingora.translate`

`from lingora.metrics import accuracy, edit_distance, jaccard_distance, precision, recall, f_measure` (the submodule is also `from lingora import metrics`); `from lingora.translate import bleu`.

```
accuracy(reference, test)                     -> number
edit_distance(s1, s2, substitution_cost=…, transpositions=…) -> number
jaccard_distance(label1, label2)              -> number
precision(reference, test)                    -> number | None
recall(reference, test)                       -> number | None
f_measure(reference, test)                    -> number | None
bleu(references, hypothesis, weights=…)       -> number
```

- `lingora.metrics.accuracy`:
  - `reference` and `test` are `list`s.
  - Lists of different lengths make it raise.
- `edit_distance`:
  - `s1` and `s2` are `str`.
  - `substitution_cost` is a number.
  - `transpositions` is a `bool`.
- `jaccard_distance`: `label1` and `label2` are `set`s.
- `precision`, `recall` and `f_measure`:
  - `reference` and `test` are `set`s (or `frozenset`s). A non-set argument makes the call raise.
  - When the PRD says no number results, the call returns `None`.
- `bleu`:
  - `references` is a `list` of reference token lists, and `hypothesis` is a token list. A token list is a `list` of `str`.
  - `weights` is a sequence of numbers, one per n-gram order starting from unigrams.
  - The call is unsmoothed unless a smoothing function is passed. The name and form of that argument are the implementer's choice.
