# feature: F03
"""Read the public register and stack location carriers directly."""
from velnora.calling_conventions import SimRegArg, SimStackArg


def location_record(location):
    if isinstance(location, SimRegArg):
        return ("register", location.reg_name, location.size)
    if isinstance(location, SimStackArg):
        return ("stack", location.stack_offset, location.size)
    raise AssertionError(f"Unexpected public argument location: {location!r}")
