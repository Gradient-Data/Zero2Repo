# feature: F11

The terminal observer uses unmodified upstream pure Python wheels directly on
Python's import path. No network or installation is required when tests run.
Upstream distribution metadata and licenses remain in the archives.

| Asset | Upstream PyPI distribution | SHA-256 |
| --- | --- | --- |
| F11_pyte.whl | pyte 0.8.2 | 85db42a35798a5aafa96ac4d8da78b090b2c933248819157fc0e6f78876a0135 |
| F11_wcwidth.whl | wcwidth 0.2.13 | 3da69048e4540d84af32131829ff948f1e022c1c6bdb8d6102117aac784f6859 |

The observer reads terminal display cells and cursor position rather than
requiring any particular choice of equivalent VT output sequences. Geometry
changes use unwrapped pending input and do not depend on terminal reflow of old
wrapped rows.
