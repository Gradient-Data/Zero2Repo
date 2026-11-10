# feature: F16
"""Fresh-process imports using the public import-time compilation hook."""
from F15_helpers import read_built_values


def import_time_values(project, source):
    """Enable the hook with project-owned output, then execute the observation."""
    prelude = ('import veximport\n'
               f'hooks = veximport.install(build_dir={str(project.path("build"))!r}, '
               'language_level=3)\n')
    return read_built_values(project, prelude + source)
