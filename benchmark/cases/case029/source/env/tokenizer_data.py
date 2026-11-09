"""Populate the tokenizer's cache from its pinned encoding declarations."""
import ast
import hashlib
import inspect
import os
from pathlib import Path
import subprocess

import tiktoken
import tiktoken_ext.openai_public

cache = Path('/opt/tokenizer-data')
cache.mkdir(parents=True, exist_ok=True)
os.environ['TIKTOKEN_CACHE_DIR'] = str(cache)
# The installed third-party wheel declares the data URLs and expected hashes.
# There is no Alibaba Cloud mirror for these upstream data endpoints.
syntax = ast.parse(inspect.getsource(tiktoken_ext.openai_public))
urls = sorted({node.value for node in ast.walk(syntax)
               if isinstance(node, ast.Constant) and isinstance(node.value, str)
               and node.value.startswith('https://')})
for url in urls:
    filename = cache / hashlib.sha1(url.encode()).hexdigest()
    subprocess.run(['curl', '--fail', '--location', '--retry', '5', '--retry-all-errors',
                    '--connect-timeout', '20', '--max-time', '300',
                    '--speed-limit', '1024', '--speed-time', '30',
                    '--silent', '--show-error', '--output', str(filename), url], check=True)
# Loading each encoding verifies its data against the library's expected hashes.
for name in tiktoken.list_encoding_names():
    tiktoken.get_encoding(name)
    print(f'Validated tokenizer data: {name}', flush=True)
