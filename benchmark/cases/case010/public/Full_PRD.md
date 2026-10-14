# Lingora Language Toolkit (LINGORA) — Full Product Requirements Document

## Product overview

**LINGORA** — the **Lingora Language Toolkit** — is a suite of open source Python modules, data sets, and tutorials for research and development in Natural Language Processing. It is a **library**. An integrator imports it and calls its published processing entries; it is not a single end-user application. A command-line convenience can tokenize a text stream with the same recommended word tokenizer the library exposes; that convenience is the same capability, not a second product.

The product advertises easy-to-use access to many packaged corpora and lexical resources such as WordNet, together with a suite of text processing libraries for **classification**, **tokenization**, **stemming**, **tagging**, **parsing**, and **semantic reasoning**. This document specifies the **core processing path a first-time integrator actually runs**: split text into tokens, reduce words to stems, assign part-of-speech tags, group tagged tokens into shallow chunks, parse a sentence against a caller-supplied grammar and work with constituent trees, train a text classifier, and score outputs with the built-in evaluation metrics.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, call signatures and output forms belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished LINGORA library. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

Packaged corpora, WordNet, graphical corpus browsers, chat demos, Twitter helpers, wrappers for external industrial taggers and parsers, and first-order semantic inference against external theorem provers are part of the wider suite. They are **not** feature points of this specification. When a specified path needs a packaged model (the Punkt sentence models, the averaged perceptron tagger), that prerequisite is stated on that path; a missing model makes that path fail.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **Token** | A contiguous substring the tokenizer treats as one unit: a word, a number, a punctuation mark, or a similar piece. |
| **Token list** | An ordered sequence of tokens produced from one string. |
| **Span** | A pair of character offsets into the original string. Slicing the original string at a span must recover the corresponding token. |
| **Sentence token** | A substring the sentence tokenizer treats as one sentence. |
| **Stem** | The residual form a stemmer returns after stripping morphological affixes. A stem is not required to be a dictionary word. |
| **Tag** | A case-sensitive label on a token, typically a part-of-speech category such as a common noun or a proper noun. |
| **Tagged token** | A pairing of a token with a tag. |
| **Backoff** | A fallback tagger consulted only when the primary tagger does not assign a tag. |
| **Chunk** | A non-overlapping group of consecutive tagged tokens (for example a base noun phrase). |
| **Chunk structure** | A shallow tree whose root is the sentence, whose leaves are tagged tokens, and whose only internal nodes are chunks. |
| **Chunk grammar** | A small text grammar whose clauses name a chunk label and list tag patterns. A pattern in braces chunks matching tag sequences; later clauses may cascade. |
| **Tag pattern** | A pattern over tags, written with each tag inside angle brackets. Whitespace in a tag pattern is ignored. |
| **Context-free grammar** | A set of productions the caller supplies as text. A production has a left-hand nonterminal, an arrow, and a right-hand sequence of nonterminals or quoted terminals. |
| **Parse tree** | A constituent tree whose root is the grammar’s start symbol and whose leaves, in order, are the input tokens. |
| **Bracketed tree text** | The parenthesized encoding used by the Penn Treebank and by LINGORA: a node is an opening parenthesis, a label, its children, and a closing parenthesis. |
| **Featureset** | A mapping from feature names to feature values that describes one example for a classifier. Values are typically booleans, numbers, or strings. |
| **Label** | The category a classifier assigns. |
| **Punkt** | LINGORA’s packaged sentence-boundary models. The recommended sentence tokenizer, and the recommended word tokenizer when it first splits the text into sentences, require Punkt for the requested language. |
| **Penn Treebank tokenizer** | The word tokenizer that follows the Penn Treebank tokenization conventions (FP-01). |
| **Word/punctuation tokenizer** | The simpler tokenizer that splits on the boundary between word characters and non-word characters (FP-01). |
| **Porter stemmer** | The English suffix-stripping stemmer after Porter’s published algorithm, with the three modes listed in FP-02. |
| **Snowball stemmer** | The family of language-specific stemmers after Martin Porter’s Snowball algorithms. The supported language names are listed in FP-02. |
| **Lancaster stemmer** | The Paice/Husk English stemmer. |
| **Naive Bayes classifier** | The built-in classifier that learns label and feature-value frequencies from labeled featuresets and returns the most probable label. |
| **Decision tree classifier** | The built-in classifier that learns a tree of feature tests and assigns the label at the leaf reached by an example. |
| **BLEU** | The Bilingual Evaluation Understudy score over token lists: a candidate is scored against one or more reference token lists. |

## Public surface inventory

LINGORA is imported and used from Python. The public surface, grouped by feature point, is:

- Tokenizing a string into words, punctuation, sentences, or spans, including the word/punctuation tokenizer, the Penn Treebank word tokenizer, LINGORA’s recommended word tokenizer, the recommended sentence tokenizer, whitespace and blank-line tokenizers, a caller-supplied regular-expression tokenizer, and a tweet tokenizer. An s-expression tokenizer also exists; it is outside this specification. A command-line tokenize command applies the recommended word tokenizer to each line of a text stream, including the sentence-splitting step, so it requires the Punkt models for the requested language.
- Stemming a word with Porter, Lancaster, Snowball, a caller-supplied suffix pattern, or the language-specific stemmers listed in FP-02.
- Tagging a token list: sequential taggers the caller trains (default, unigram, bigram, trigram, affix, regular-expression) with optional backoff, and LINGORA’s recommended English or Russian tagger when the corresponding averaged perceptron tagger resource is installed.
- Chunking a tagged token list with a chunk grammar. A named-entity chunker exists when its packaged model is installed; it is not the primary way to satisfy chunking.
- Building a context-free grammar from productions, parsing a token list with a recursive-descent, shift-reduce, or chart parser, generating strings from a grammar, and building, comparing, and pretty-printing constituent trees from bracketed tree text.
- Training and applying a Naive Bayes classifier or a decision tree classifier on labeled featuresets, including a probability distribution over labels for Naive Bayes.
- Scoring: Levenshtein edit distance (optional transpositions), Jaccard distance, accuracy, precision, recall, f-measure, and BLEU.

Feature points below group these entries by capability. They do not invent additional product surfaces.

## Non-functional constraints

- **Form factor:** A pure-Python library with no compiled extensions, native code, or GPU/accelerator requirements. Packaging uses a flat package layout. An editable install from this repository’s source tree is sufficient.
- **Language:** Python 3.10 or newer, through the latest 3.14. Runtime dependencies are limited to pure-Python packages. Optional extra groups add scientific-computing libraries for some classifiers and plot helpers; they are not required for the CPU profile.
- **Platforms:** Windows, Mac OS X, and Linux. The product must run on Linux with a supported interpreter.
- **Hardware:** CPU-only. Importing the package from this repository and running a word/punctuation tokenization needs no downloaded corpus or model.
- **Packaged data:** Many advertised resources (Punkt, the averaged perceptron tagger, WordNet, Treebank, and other corpora) live outside the source tree and are located through LINGORA’s data finder. Full-suite corpus download is documented via the package downloader. It is **not** required for the baseline word/punctuation tokenizer, for trainable sequential taggers, for regular-expression chunking, for grammar-based parsing, for in-memory classification, or for the evaluation metrics. When a feature point names a packaged model as a prerequisite, absence of that model makes that path fail observably. The finder searches a list of directories that the caller may set; a path that needs a packaged model finds it only in those directories.
- **Unicode:** Input and output are Unicode text. Accented letters in a tweet-style tokenizer remain intact inside their tokens.
- **Threading and process model:** Not a concern of this specification. The library is used in-process.

## Core capabilities (global)

Every feature point below is a core capability of the real library: the outcomes come from the library implementing the stated rules on the caller’s inputs. When the package cannot be imported, none of its entries can be called.

## Non-goals

- Being a general-purpose regular-expression engine, machine-learning framework, or theorem prover.
- Shipping WordNet, Treebank, or other corpora inside the source tree. Those are packaged data. The data finder and downloader exist so callers can install them; they are not feature points here.
- Graphical applications (chart parser, chunk parser, WordNet browser, concordance, and similar desktop demos) and drawing helpers.
- Chat bots, Twitter clients, Hugging Face dataset helpers, and Toolbox readers.
- Wrappers that require an external binary or service (Stanford, Senna, Hunpos, Malt, Bllip, CoreNLP, Weka, MEGAM, TADM).
- Combinatory categorial grammar, discourse representation, first-order inference against Prover9 or Mace, and other semantic-reasoning tools that are not on the first-time processing path.
- N-gram language-model training as a separate product. Counting and scoring that classifiers and metrics already perform are specified where they are observable.
- Guaranteeing a particular tokens-per-second throughput.

---

## Feature points

### FP-01: Word, punctuation, and sentence tokenization

**Public entry:** LINGORA’s tokenizer entries: the word/punctuation tokenizer; the Penn Treebank word tokenizer; LINGORA’s recommended word tokenizer (an improved Penn Treebank word tokenizer); the recommended sentence tokenizer; the whitespace tokenizer; the blank-line tokenizer; a regular-expression tokenizer the caller configures; the tweet tokenizer; and span extraction on a tokenizer that supports spans. An s-expression tokenizer also exists; it is outside this specification.

The command-line tokenize command applies the recommended word tokenizer to each line of a text stream, including the sentence-splitting step, and writes the tokens joined by a delimiter (one space by default). Because that path splits sentences first, it requires the **Punkt** models for the requested language.

The recommended sentence tokenizer, and the recommended word tokenizer when it is asked to split the input into sentences first, require the **Punkt** models for the requested language; the default language is English. The word/punctuation tokenizer, the Penn Treebank word tokenizer, the recommended word tokenizer applied to one already-delimited line (no sentence splitting), the whitespace and blank-line tokenizers, a caller-configured regular-expression tokenizer, and the tweet tokenizer do **not** require a downloaded model.

**Normal behavior:**

- **Word/punctuation tokenizer.** The tokens are, left to right, the maximal runs of word characters (Unicode letters, digits and the underscore) and the maximal runs of characters that are neither word characters nor whitespace. Whitespace is never part of a token.
- **Penn Treebank word tokenizer.** It follows the Penn Treebank tokenization conventions:
  - The text is split at whitespace, and punctuation is then split off as follows.
  - A straight double quote at the start of the text, or after a space or an opening bracket, becomes the opening-quote token made of two backticks. Every other straight double quote becomes the closing-quote token made of two apostrophes. A straight double quote is never a token of its own.
  - Each of the characters `;`, `@`, `#`, `$`, `%`, `&`, `?`, `!` and each bracket is a token of its own. So is an ellipsis of three points.
  - A comma or colon is split off unless a digit follows it.
  - A point is split off only when it ends the text, optionally followed by closing quotes or brackets.
  - The clitics `'s`, `'m`, `'d`, `'ll`, `'re`, `'ve` and `n't` (in either letter case), and a bare apostrophe ending a word, are split from the word they follow and become tokens of their own.
  - The fused forms *cannot*, *d'ye*, *gimme*, *gonna*, *gotta*, *lemme*, *more'n*, *wanna*, *'tis* and *'twas* are split into their two parts (*can* + *not*, *gon* + *na*, and so on).
  - An apostrophe that does not begin one of those clitics stays inside its word.
- **Recommended word tokenizer.** It applies the same Penn Treebank conventions, with these improvements:
  - Typographic quotation marks are split off as tokens of their own.
  - Dashes in the range U+2012–U+2015 and asterisks are split off.
  - Any run of two or more points is a token.
  - A double hyphen is a token.

  Unless the caller says the input is one already-delimited line, it first splits the text into sentences with the recommended sentence tokenizer, then tokenizes each sentence and concatenates the tokens in order.
- **Whitespace tokenizer.** The tokens are the maximal runs of non-whitespace characters (whitespace is space, tab, newline and the other Unicode white-space characters).
- **Blank-line tokenizer.** A separator is a newline, then optional whitespace, then another newline, together with any whitespace around them. The segments are the pieces of text between separators, in order, with empty pieces dropped. Single newlines inside a segment are kept.
- **Regular-expression tokenizer.**
  - In token mode (the default), the tokens are the successive non-overlapping matches of the caller's pattern, found left to right.
  - In gap mode, the pattern matches separators, and the tokens are the pieces of text between successive matches and before the first or after the last.
  - Empty pieces are dropped unless the caller turns empty-discarding off (it is on by default).
- **Tweet tokenizer.**
  - Words containing an internal apostrophe (contractions) stay one token.
  - Letters with diacritics are word characters, so accented words stay whole.
  - Emoticons, URLs, hashtags and @-handles are single tokens, and other punctuation marks are tokens of their own.
  - With handle stripping on (off by default), every @-handle is removed before tokenizing, and the text on either side of it is tokenized as if a space stood there. An @-handle is an `@` that does not continue a preceding word, followed by a user name of 1 to 15 ASCII letters, digits or underscores.
  - With length reduction on (off by default), every run of three or more consecutive occurrences of the same character is shortened to exactly three occurrences before tokenizing.
  - With case preservation off (it is on by default), tokens are lowercased, except emoticons.
- **Spans.** A tokenizer that reports spans returns one pair of character offsets per token, in token order. Slicing the input at each pair gives the corresponding token. Each pair starts at or after the end of the previous one.
- **Sentence tokenizer.** It implements the Punkt unsupervised sentence-boundary detection algorithm (Kiss and Strunk, 2006). It uses the packaged Punkt parameters for the requested language: abbreviation types, collocations, sentence starters and orthographic context. It returns the sentences of the text in their original order. Each sentence is the original text of that sentence, without the whitespace that separates it from the next one. A text that is a single sentence yields that one sentence.
- **Command line.** The tokenize command reads standard input line by line. For each input line it writes one output line: that line's recommended-word-tokenizer tokens, with sentence splitting, joined by the delimiter.

**Boundary / error behavior:**

- An empty string, and a string made only of whitespace, yield an empty token list on every tokenizer that does not need a model.
- When sentence splitting is requested and the Punkt models for the requested language are not installed, the recommended sentence tokenizer and the recommended word tokenizer do **not** succeed. The failure is distinguishable from a successful empty token list.
- The command-line tokenize command does **not** succeed when the Punkt models for the requested language are missing: it ends with a failure status and writes no token line.

---

### FP-02: Stemming

**Public entry:** LINGORA’s stemmer entries. The built-in stemmer families are exactly: **Porter** (English), **Lancaster** (English, Paice/Husk), **Snowball** (the languages listed below), a **regular-expression** stemmer that strips a caller-supplied pattern, **ISRI** (Arabic), **ARLSTem** and **ARLSTem2** (Arabic), **Cistem** (German), and **RSLP** (Portuguese). A WordNet lemmatizer also lives in this family; it requires the WordNet resource.

The stemmer families specified here are Porter in its default mode, Lancaster, Snowball for the languages named below, and the regular-expression stemmer. ISRI, ARLSTem, ARLSTem2, Cistem, RSLP, and the WordNet lemmatizer exist; their stemming results are outside this specification. RSLP and the WordNet lemmatizer require packaged data; the specified families do not require WordNet.

The Snowball language names are exactly: arabic, danish, dutch, english, finnish, french, german, hungarian, italian, norwegian, porter, portuguese, romanian, russian, spanish, and swedish. Enabling Snowball stopword skipping requires the packaged stopwords list for that language.

The Porter stemmer has exactly three modes: the original published algorithm, the Martin Porter extensions, and the LINGORA extensions. The default mode is the LINGORA extensions. The other two modes exist; their results are outside this specification.

Every stemmer treats its whole input string as one token. A string containing spaces is not split into words.

**Normal behavior:**

- **Porter, default mode.** The stemmer implements M. F. Porter's algorithm (“An algorithm for suffix stripping”, 1980) with these LINGORA extensions:
  - The word is lowercased first, unless the caller turns lowercasing off.
  - The lowercased word is first looked up in a small built-in table of irregular forms, and a hit returns the table's stem. The table's entries are outside this specification.
  - A word of one or two characters is returned as it stands after the lowercasing step. It is never stemmed and never refused.
  - In Step 1a, a four-letter word ending in *-ies* becomes *-ie* rather than *-i*.
  - At the start of Step 1b, a word ending in *-ied* becomes *-ie* if it has four letters and *-i* otherwise. In that case the rest of Step 1b is skipped.
  - The *\*o* condition (the stem ends consonant–vowel–consonant and the final consonant is not *w*, *x* or *y*) also holds for a two-letter stem made of a vowel followed by a consonant.
  - In Step 1c, a final *y* becomes *i* only when it follows a consonant that is not the first letter of the stem. This replaces the original "stem contains a vowel" condition.
  - In Step 2:
    - *-alli* → *-al* is tried first, when the remaining stem has positive measure. If it applies, the result goes through Step 2 again.
    - *-bli* → *-ble* replaces the original *-abli* → *-able*.
    - The rules *-fulli* → *-ful* and *-logi* → *-log* are added. The *-logi* rule applies when the part of the word before *-ogi* has positive measure.
  - Every other step and condition is the published algorithm's. Every word is stemmed without refusal, including a word whose stem reduces to a single letter.
- **Lancaster.** The stemmer implements the Paice/Husk algorithm (C. D. Paice, “Another Stemmer”, 1990) with the standard rule table published with it. The word is lowercased first, and no prefix is stripped.
- **Snowball.** The stemmer for a language implements the Snowball stemming algorithm for that language, as published by the Snowball project in its 2.2 release:
  - For Dutch, this is the original Dutch algorithm, which later Snowball releases keep as the Porter-style Dutch stemmer.
  - The language named *english* is the Porter2 (English) algorithm. The language named *porter* is Snowball's rendering of the original Porter algorithm, so the two can give different stems.
  - The word is lowercased first.
  - With stopword skipping on (off by default), a lowercased word that appears in that language's packaged stopwords list is returned unchanged (lowercased).
- **Regular-expression stemmer.** It removes every match of the caller's pattern from the word and changes nothing else; no suffix rewriting is applied. A word the pattern does not match is returned unchanged.

**Boundary / error behavior:**

- Asking Snowball for a language that is not in the list above does not produce a usable stemmer. The failure names the requested language.
- When Snowball stopword skipping is requested and the packaged stopwords list for that language is not installed, constructing the stemmer does **not** succeed. A list installed only for another language does not satisfy it.
- The WordNet lemmatizer does not succeed when WordNet is not installed. Porter, Lancaster and Snowball do not require WordNet.

---

### FP-03: Part-of-speech tagging

**Public entry:** LINGORA’s tagger entries. The sequential taggers a caller can train without a downloaded model are exactly: a **default** tagger that assigns one tag to every token; a **unigram** tagger; a **bigram** tagger; a **trigram** tagger; an **affix** tagger; and a **regular-expression** tagger. Any of these may name another sequential tagger as backoff.

The trainable taggers specified here are the default tagger, the unigram tagger (with and without backoff), and the regular-expression tagger. Bigram, trigram, and affix taggers exist and follow the same train-then-tag protocol; their results are outside this specification.

LINGORA’s **recommended** tagger for English and for Russian is a separately packaged averaged perceptron tagger. The recommended English tagger uses the Penn Treebank tagset; the recommended Russian tagger uses the Russian National Corpus tagset. The caller may ask the recommended tagger to map tags into the **universal** tagset. Mapping English tags into that tagset also requires the packaged universal tagset tables; mapping Russian tags does not. The English mapping's results when those tables are present are outside this specification.

**Normal behavior:**

- A tagger returns one tagged token per input token, in input order, each pairing the input token with its tag or with no tag. Tagging an empty token list yields an empty list.
- **Default tagger.** It assigns its one configured tag to every token.
- **Unigram tagger.** Each word seen in training receives the tag it was seen with most often in training. Ties are broken in the implementer's choice of way. A word never seen in training receives no tag.
- **Regular-expression tagger.** Rules are tried in the caller's order. A token receives the tag of the first rule whose pattern matches the token starting at its first character. A token no rule matches receives no tag.
- **Backoff.** A backoff tagger is consulted only for tokens the primary tagger leaves without a tag. Tokens the primary tagger tagged keep their tags.
- **Recommended English tagger.** It is the greedy averaged perceptron part-of-speech tagger published as *textblob-aptagger* (M. Honnibal, 2013), with that tagger's feature templates, word normalisation and sentence-boundary context. It reads its weights, tag dictionary and classes from the packaged English resource and returns the Penn Treebank tags that the packaged model assigns. The whole token list is tagged as one sentence, from left to right, and the tags already assigned to earlier tokens are context for later ones.
- **Recommended Russian tagger.** It is the same algorithm reading the packaged Russian resource, and returns the model's Russian National Corpus tags.
- **Universal tagset mapping.**
  - English tags are mapped with the packaged English Penn Treebank → universal table (the universal tagset of Petrov, Das and McDonald, 2012).
  - Russian tags are mapped by the part before any `=`: each Russian National Corpus part-of-speech category is mapped to the universal category of the same part of speech, so nouns and verbs map to the universal noun and verb categories. The exact table is the implementer's choice.

**Boundary / error behavior:**

- The recommended tagger accepts a **list of tokens**, not a raw string. Passing an untokenized string does not succeed, and the failure is distinguishable from a successful tagging.
- The recommended tagger supports only English and Russian. Asking it to tag with any other language does not succeed.
- When the averaged perceptron tagger resource for the requested language is not installed, the recommended tagger does not succeed. The resource of the other language does not satisfy it.
- When the caller asks the recommended English tagger for the universal tagset and the packaged universal tagset tables are not installed, that mapping does **not** take place: the call either fails or returns tags that are not mapped. Russian mapping does not need those tables.

---

### FP-04: Chunking

**Public entry:** LINGORA’s chunk parser that reads a **chunk grammar** and is applied to a list of tagged tokens. The grammar is a text with one or more clauses. Each clause names a chunk label and then lists tag patterns. A pattern enclosed in braces is a chunk rule. A pattern written with a closing brace, then a tag pattern, then an opening brace, is a chink rule. The root label of the resulting chunk structure defaults to a sentence label that is the same for every parser and differs from clause labels.

A separately packaged named-entity chunker exists. It requires its trained model and tagged input. It is a resource-gated path, not the primary way to satisfy this feature point. Its results when the resource is present are outside this specification.

**Normal behavior:**

- A tag pattern is matched against the sequence of tags of the tokens. Each angle-bracketed element matches one token whose whole tag matches the element read as a regular expression over the tag string (`.` matches any character of a tag, `|` is alternation). Quantifiers after an element (`?`, `*`, `+`, and a brace count such as at least *n*) apply to that element. Whitespace in a pattern is ignored.
- **Chunk rule.** Every match of the pattern among tokens not yet in a chunk becomes one chunk carrying the clause's label. Matches are found left to right, each as long as possible, without overlap. Two matches that touch are two separate chunks. Tokens no rule chunks stay direct children of the root.
- **Chink rule.** It removes the matching tokens from the chunks built earlier in the same clause. A chunk whose interior is removed is split into the parts on either side, and chinked tokens become direct children of the root.
- The rules of a clause apply in their written order. Clauses apply in their written order. A later clause sees every chunk built by an earlier clause as a single unit whose tag is that chunk's label, so it can chunk the remaining tokens but cannot chink inside an earlier clause's chunks.
- The chunk structure's leaves, in order, are exactly the input tagged tokens. Chunking groups tokens; it never drops, reorders, or retags them.

**Boundary / error behavior:**

- An empty tagged-token list yields a chunk structure with a sentence root and no children.
- A chunk grammar that is not text and not a list of chunk-parser stages is refused. The operation does not succeed and does not return a chunk structure.
- When the named-entity chunker resource is not installed, the named-entity path does not succeed, even when a tagger resource is installed.

---

### FP-05: Grammar-based parsing and constituent trees

**Public entry:** LINGORA’s context-free grammar reader; the recursive-descent, shift-reduce, and chart parsers that take such a grammar and a token list; the generator that enumerates strings from a grammar; and the constituent-tree entries that build a tree from a label plus children, build a tree from **bracketed tree text**, compare trees, read a node label, read children by position, list leaves, and pretty-print a tree.

The parsers specified here are the chart parser, which is exhaustive, and the shift-reduce parser. A recursive-descent parser exists; its results are outside this specification.

This feature point depends on tokens (FP-01) only as a list of terminals the caller already has. It does not require Punkt, a tagger, or a corpus.

**Normal behavior:**

- **Grammar reader.**
  - The start symbol is the left-hand side of the first production.
  - Each alternative separated by `|` is a production of its own.
  - A quoted terminal is the text inside its quotes, and an unquoted symbol is a nonterminal.
  - A quoted empty string is a terminal that is the empty string. A production with nothing after its arrow is an empty production.
  - Production lines appended to a grammar text add their productions.
- **Chart parser.** It returns every parse tree the grammar assigns to the token list: none for a token list the grammar does not derive, and several for an ambiguous one. Each tree's root is the start symbol, its leaves in order are the input tokens, and it has one internal node per production used.
- **Shift-reduce parser.** It parses by a single left-to-right shift-reduce pass without backtracking: whenever the top of the stack matches the right-hand side of a production, it reduces; otherwise it shifts the next token. It returns the parse that pass completes, or none. On an unambiguous sentence that the pass completes, the tree is the same as the chart parser's.
- **Generator.** It enumerates the sentences the grammar derives from the start symbol, each as a list of terminal tokens, expanding productions in their written order, up to an optional count and an optional depth bound. A quoted empty string contributes an empty-string token. An empty production contributes no token.
- **Trees.**
  - A tree has a label and an ordered list of immediate children; a child is a token string (a leaf) or a tree. Its length is the number of immediate children, and its children can be read by position.
  - Its leaves are the token strings under it in left-to-right order.
  - Two trees are equal exactly when their labels are equal and their children are equal pairwise, recursively.
  - A tree read from bracketed tree text equals the tree built from the same labels and children.
  - The pretty-printed form shows every label and leaf in left-to-right (pre-order) order.

**Boundary / error behavior:**

- Building a tree from a label and a **string** as the child list (instead of a list of children) is refused. Building a tree from a label with no child list is refused. A tree with an empty child list is a valid tree with no children, distinguishable from both refusals.
- A parser given a token list that contains a token no production of the grammar produces does **not** succeed. That failure is distinguishable from a successful empty set of parses, which is the outcome for a list of covered tokens that the grammar does not derive.

---

### FP-06: Text classification

**Public entry:** LINGORA’s Naive Bayes classifier and decision tree classifier. The caller supplies a training list of labeled featuresets. After training, the caller asks for a label, and (for Naive Bayes) for a probability distribution over labels. An accuracy helper compares a classifier’s labels on a test list to the gold labels.

This feature point does not require a downloaded corpus. The caller builds featuresets in memory, with any feature names and labels.

**Normal behavior:**

- **Naive Bayes.**
  - Training estimates label prior probabilities and, per label, the probability of each feature value from the training frequencies. The estimates are smoothed so that no feature value seen with some label gets probability zero under another label.
  - Classifying uses only the features of the queried featureset that occurred in training. A feature name never seen in training is ignored.
  - The returned label is the label with the highest posterior probability.
  - The probability distribution assigns each trained label its posterior probability. The probabilities are real numbers summing to one.
  - The classifier lists exactly the labels seen in training.
- **Decision tree.** It learns tests on feature values from the labeled featuresets; a feature absent from a featureset counts as having no value. It chooses at each node the feature whose test classifies the training examples reaching that node best. A leaf returns the majority training label of the examples that reach it. When a single feature's values separate the training labels, each training featureset is classified with its own training label.
- A featureset that shares no feature with the training data still receives one of the trained labels, from either classifier. It is never refused, and it never receives a label that did not occur in training.
- **Classifier accuracy.** It is the fraction of gold examples, position by position, for which the classifier's label for the example's featureset equals the gold label.

**Boundary / error behavior:**

- Two-list accuracy (FP-07) on lists of different lengths does not succeed.

---

### FP-07: Evaluation metrics

**Public entry:** LINGORA’s scoring entries for **Levenshtein edit distance** (with an optional transposition edit), **Jaccard distance**, **accuracy**, **precision**, **recall**, **f-measure**, and **BLEU** (a candidate token list scored against one or more reference token lists, with caller-chosen n-gram weights and an optional smoothing function).

These metrics are pure functions of the arguments the caller supplies. They do not require a downloaded corpus or a trained model.

**Normal behavior:**

- **Edit distance.**
  - It is the minimum total cost of edits that turn the first string into the second.
  - Insertion and deletion of one character cost 1 each. Substitution of one character by a different one costs the caller's substitution cost, which defaults to 1.
  - With transpositions on (off by default), the distance is the unrestricted Damerau–Levenshtein distance (Lowrance and Wagner, 1975). A transposition of two adjacent characters costs 1, and characters may also be inserted between, or deleted from between, the two transposed characters.
  - The distance of a string to itself is 0, and the distance is symmetric.
- **Jaccard distance.** It is the size of the symmetric difference of the two sets divided by the size of their union.
- **Accuracy.** For two lists of equal length, it is the fraction of positions at which they hold equal values.
- **Precision, recall and f-measure.**
  - Precision is |reference ∩ test| / |test|. Recall is |reference ∩ test| / |reference|.
  - The f-measure is the weighted harmonic mean 1 / (α / precision + (1 − α) / recall), with α = 0.5 by default. It is 0 when precision or recall is 0.
- **BLEU.** It is the standard sentence-level BLEU score (Papineni et al., 2002):
  - Each n-gram order has a modified precision: candidate n-gram counts are clipped by the maximum count of that n-gram in any one reference.
  - The precisions are combined as a geometric mean weighted by the caller's weights, one weight per order starting from unigrams. The default is equal weights on unigrams through 4-grams.
  - The result is multiplied by the brevity penalty, computed from the reference length closest to the candidate length (the shorter one when two are equally close).
  - Tokens are compared exactly as given.
  - Without a smoothing function, the score is 0 when the candidate has no unigram match. When any other weighted order has no match, the score is 0 or negligibly close to 0.

**Boundary / error behavior:**

- Accuracy on two lists of different lengths does not succeed.
- Precision and recall require sets. Lists, tuples and other non-set collections are refused. Precision with an empty test set, recall with an empty reference set, and f-measure when either set is empty return no number. That absence is distinguishable from the number 0.
- Edit distance of two empty strings is 0.

---

## Outside this specification (present in the product, not a feature point)

The following surfaces exist in LINGORA and are not feature points of this PRD. They are outside this specification.

- Packaged corpora, WordNet, the data finder, and the downloader (including the downloader graphical interface), beyond what the feature points state about locating packaged models.
- Graphical applications and tree/table drawing.
- Chat, Twitter, Hugging Face, and Toolbox helpers.
- External-binary wrappers (Stanford, Senna, Hunpos, Malt, Bllip, CoreNLP, Weka, MEGAM, TADM).
- Combinatory categorial grammar, discourse representation, glue semantics, and inference against Prover9 or Mace.
- N-gram language models, collocation finders, concordance over a Text object, and sentiment lexicons (including VADER).
- Optional machine-learning extras (CRF, scikit-learn wrapper) that are not required for Naive Bayes or the decision tree.
