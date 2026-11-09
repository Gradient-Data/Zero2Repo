# feature: F01
"""Feature-local setup and an independent IEEE 754 reference."""
import struct
import z3
from _helpers import import_product


def expression_api():
    velnora = import_product()
    return velnora, velnora.claripy


def fresh_state():
    velnora, _ = expression_api()
    return velnora.load_shellcode(b"\x90", arch="AMD64").factory.blank_state()


def ieee_bits(value, width):
    return int.from_bytes(struct.pack(">f" if width == 32 else ">d", value), "big")


def ieee_operation(name, left, right, width):
    sort = z3.Float32() if width == 32 else z3.Float64()
    a, b = z3.FPVal(left, sort), z3.FPVal(right, sort)
    operations = {"add": z3.fpAdd, "sub": z3.fpSub,
                  "mul": z3.fpMul, "div": z3.fpDiv}
    result = operations[name](z3.RNE(), a, b)
    return z3.simplify(z3.fpToIEEEBV(result)).as_long()
