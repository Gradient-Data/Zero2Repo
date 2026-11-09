"""Reserve the public installation paths for the product handed off at /app.

runtime-layout.json contains only public package and command names exported from
the packaging metadata. These links deliberately remain dangling until a real
candidate has been built; installation never supplies a product implementation.
"""
import json
from pathlib import Path
import sysconfig

layout = json.loads(Path('/env-assets/runtime-layout.json').read_text())
product = Path('/app/.product')
for kind, destination, target in (
    ('packages', Path(sysconfig.get_path('purelib')), product),
    ('console_scripts', Path(sysconfig.get_path('scripts')), product / 'bin'),
):
    for name in layout[kind]:
        if not name or Path(name).name != name or name in ('.', '..'):
            raise ValueError(f'Invalid installation name: {name!r}')
        # Refuse collisions with trusted dependencies or tools in the image.
        (destination / name).symlink_to(target / name)
