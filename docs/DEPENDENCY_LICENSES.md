# Third-party dependency licenses

TopoMarket is released under the **MIT** license. This audit covers every direct
dependency declared in `pyproject.toml` and every distribution pinned in
`requirements.lock` (and, once present, the Cloud `requirements.txt`). It exists to
catch a strong copyleft dependency (GPL/AGPL) early: such a dependency would force the
distributed project onto the same license.

Regenerate with `python scripts/refresh_dependency_licenses.py`; verify offline in CI
with `scripts/audit_dependency_licenses.py` and `tests/test_dependency_licenses.py`.

## Result

- Packages audited: **80**
- Permissive / compatible: **79**
- Weak copyleft or manual review: **1**
- Strong copyleft (GPL/AGPL): **0**

**Verdict: no strong copyleft dependency found. MIT remains the project license; genuine market data stays outside the repository (see `NOTICE.md`).**

## Method

1. A PyPI SPDX `license_expression` wins when present; a strong copyleft alternative only
   fails when the expression offers no permissive alternative.
2. Otherwise OSI license classifiers are used; a dual-licensed package with a permissive
   option (for example `docutils`) is distributed under the permissive option.
3. Otherwise a short `License` metadata field is used. Long license texts are not
   scanned:
   packages such as `matplotlib`/`scipy` embed third-party font/GCC-runtime notices that
   would otherwise create false positives (`matplotlib` is PSF/BSD-compatible,
   `scipy`/`scikit-learn` are BSD-3-Clause, `numpy` is BSD-3-Clause).

Weak copyleft dependencies (for example `certifi`, MPL-2.0) keep their own file-level
terms; TopoMarket uses them unmodified as external dependencies, which does not affect
the MIT distribution of this repository.

## Runtime imports

The package imports `httpx`, `numpy` and `ripser` at runtime; the Streamlit UI extra adds
`streamlit` and the chart renderer (`matplotlib`). All are permissive.

## Packages

| Package | Version | Declared | License | Class | Risk |
| --- | --- | --- | --- | --- | --- |
| `altair` | 6.3.0 | cloud | OSI Approved :: BSD License | permissive | PASS |
| `anyio` | 4.16.0 | cloud | MIT | permissive | PASS |
| `attrs` | 26.1.0 | cloud | MIT | permissive | PASS |
| `build` | 1.6.1 | pyproject | MIT | permissive | PASS |
| `certifi` | 2026.11.20 | cloud | OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | weak-copyleft | REVIEW |
| `cffi` | 2.1.1 | lock | MIT-0 | permissive | PASS |
| `charset-normalizer` | 3.5.3 | cloud | MIT | permissive | PASS |
| `click` | 8.5.1 | cloud | BSD-3-Clause | permissive | PASS |
| `cloudpickle` | 3.1.3 | cloud | BSD-3-Clause | permissive | PASS |
| `contourpy` | 1.4.0 | cloud | BSD-3-Clause | permissive | PASS |
| `cryptography` | 50.0.2 | lock | Apache-2.0 OR BSD-3-Clause | permissive | PASS |
| `cycler` | 0.12.1 | cloud | OSI Approved :: BSD License | permissive | PASS |
| `cython` | 3.3.2 | cloud | Apache-2.0 | permissive | PASS |
| `deprecated` | 3.0.1 | cloud | MIT | permissive | PASS |
| `docutils` | 0.23 | lock | OSI Approved :: BSD License; OSI Approved :: GNU Gene... | permissive | PASS |
| `fonttools` | 4.68.0 | cloud | MIT | permissive | PASS |
| `h11` | 0.16.0 | cloud | OSI Approved :: MIT License | permissive | PASS |
| `httpcore` | 1.0.9 | cloud | BSD-3-Clause | permissive | PASS |
| `httpx` | 0.28.1 | pyproject | OSI Approved :: BSD License | permissive | PASS |
| `id` | 1.6.1 | lock | OSI Approved :: Apache Software License | permissive | PASS |
| `idna` | 3.20 | cloud | BSD-3-Clause | permissive | PASS |
| `iniconfig` | 2.3.1 | lock | MIT | permissive | PASS |
| `itsdangerous` | 2.2.0 | cloud | OSI Approved :: BSD License | permissive | PASS |
| `jaraco.classes` | 3.4.0 | lock | OSI Approved :: MIT License | permissive | PASS |
| `jaraco.context` | 6.1.2 | lock | MIT | permissive | PASS |
| `jaraco.functools` | 4.6.0 | lock | MIT | permissive | PASS |
| `jeepney` | 0.9.0 | lock | MIT | permissive | PASS |
| `jinja2` | 3.1.6 | cloud | OSI Approved :: BSD License | permissive | PASS |
| `joblib` | 1.6.0 | cloud | BSD-3-Clause | permissive | PASS |
| `jsonschema` | 4.26.0 | cloud | MIT | permissive | PASS |
| `jsonschema-specifications` | 2025.9.1 | cloud | MIT | permissive | PASS |
| `keyring` | 25.7.0 | lock | MIT | permissive | PASS |
| `kiwisolver` | 1.5.1 | cloud | OSI Approved :: BSD License | permissive | PASS |
| `markdown-it-py` | 4.3.0 | lock | OSI Approved :: MIT License | permissive | PASS |
| `markupsafe` | 3.0.4 | cloud | BSD-3-Clause | permissive | PASS |
| `matplotlib` | 3.11.2 | pyproject | OSI Approved :: Python Software Foundation License | permissive | PASS |
| `mdurl` | 0.1.2 | lock | OSI Approved :: MIT License | permissive | PASS |
| `more-itertools` | 11.2.1 | lock | MIT | permissive | PASS |
| `narwhals` | 2.29.0 | cloud | MIT | permissive | PASS |
| `nh3` | 0.3.8 | lock | MIT | permissive | PASS |
| `numpy` | 2.5.5 | pyproject | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | permissive | PASS |
| `packaging` | 26.4 | cloud | Apache-2.0 OR BSD-2-Clause | permissive | PASS |
| `pandas` | 3.1.1 | cloud | BSD-3-Clause | permissive | PASS |
| `persim` | 0.4.1 | cloud | OSI Approved :: MIT License | permissive | PASS |
| `pillow` | 13.0.0 | cloud | MIT-CMU | permissive | PASS |
| `plotly` | 6.5.0 | pyproject | OSI Approved :: MIT License | permissive | PASS |
| `pluggy` | 1.7.0 | lock | OSI Approved :: MIT License | permissive | PASS |
| `protobuf` | 7.36.2 | cloud | 3-Clause BSD License | permissive | PASS |
| `pyarrow` | 26.0.1 | cloud | Apache-2.0 | permissive | PASS |
| `pycparser` | 3.12 | lock | BSD-3-Clause | permissive | PASS |
| `pydeck` | 0.9.3 | cloud | Apache License 2.0 | permissive | PASS |
| `pygments` | 2.21.0 | lock | BSD-2-Clause | permissive | PASS |
| `pyparsing` | 3.3.3 | cloud | MIT | permissive | PASS |
| `pyproject-hooks` | 1.3.3 | lock | MIT | permissive | PASS |
| `pytest` | 9.2.0 | pyproject | MIT | permissive | PASS |
| `python-dateutil` | 4.0.0 | cloud | BSD-3-Clause | permissive | PASS |
| `python-multipart` | 0.0.34 | cloud | Apache-2.0 | permissive | PASS |
| `readme-renderer` | 46.0 | lock | Apache-2.0 | permissive | PASS |
| `referencing` | 0.37.0 | cloud | MIT | permissive | PASS |
| `requests` | 2.34.2 | cloud | OSI Approved :: Apache Software License | permissive | PASS |
| `requests-toolbelt` | 1.0.0 | lock | OSI Approved :: Apache Software License | permissive | PASS |
| `rfc3986` | 2.0.0 | lock | OSI Approved :: Apache Software License | permissive | PASS |
| `rich` | 15.0.0 | lock | OSI Approved :: MIT License | permissive | PASS |
| `ripser` | 0.6.15 | pyproject | OSI Approved :: MIT License | permissive | PASS |
| `rpds-py` | 2026.9.1 | cloud | MIT | permissive | PASS |
| `ruff` | 0.17.6 | pyproject | MIT | permissive | PASS |
| `scikit-learn` | 1.9.1 | cloud | BSD-3-Clause | permissive | PASS |
| `scipy` | 1.18.1 | cloud | OSI Approved :: BSD License | permissive | PASS |
| `secretstorage` | 3.5.0 | lock | BSD-3-Clause | permissive | PASS |
| `starlette` | 1.10.0 | cloud | BSD-3-Clause | permissive | PASS |
| `streamlit` | 1.67.0 | pyproject | Apache-2.0 | permissive | PASS |
| `threadpoolctl` | 3.8.0 | cloud | BSD-3-Clause | permissive | PASS |
| `twine` | 7.0.0 | pyproject | Apache-2.0 | permissive | PASS |
| `typing-extensions` | 4.16.0 | cloud | PSF-2.0 | permissive | PASS |
| `tzdata` | 2026.6 | cloud | Apache-2.0 | permissive | PASS |
| `urllib3` | 2.8.0 | cloud | MIT | permissive | PASS |
| `uvicorn` | 0.54.0 | cloud | BSD-3-Clause | permissive | PASS |
| `watchdog` | 7.1.1 | cloud | Apache-2.0 | permissive | PASS |
| `websockets` | 17.4 | cloud | BSD-3-Clause | permissive | PASS |
| `wrapt` | 2.5.2 | cloud | BSD-2-Clause | permissive | PASS |

## Cloud dependency definition

`requirements.txt` is the effective Streamlit Community Cloud definition. It is
pinned and audited by `scripts/audit_dependency_licenses.py`; regenerate it when
dependencies change (see `docs/DEPLOYMENT.md`).
