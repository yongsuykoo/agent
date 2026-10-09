# Bundled PDF reader

The agent includes the unchanged pure Python pypdf 6.20.0 wheel under `app_agent/vendor/pypdf.whl`, published at https://pypi.org/project/pypdf/6.20.0/ under BSD-3-Clause. The complete license is shipped beside it as `PYPDF_LICENSE.txt` and inside the original wheel. The parser is imported only in a bounded isolated child process. No pypdf extras are installed or external decoding command permitted.

Original wheel SHA-256: `f003fc2014814d264fe7dd3f9d435c158e23e1a85a2233f87a0a2d6d21c914ad`.

Vendoring preserves the existing host dependency metadata so compatible signed workers do not require the user to repeat Windows setup. The bundled artifact's checksum is checked before use; it is also covered by the signed worker artifact checksum. Updates require a reviewed new pinned artifact and repeat acceptance tests.
