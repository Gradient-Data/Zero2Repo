# feature: F01
"""Independent framing vectors from ITU-T X.690 (2015), sections 8.1 and 10.1.

Headers are explicit standard encodings, not computed by the product or by a
second implementation of its framing algorithm. Contents are opaque to this
low-level public API. Constructed examples contain complete child elements.
"""


def framing_vectors():
    """Yield (class, method, tag, header, contents) for definite elements.

Each row adds a tag/length boundary or an otherwise uncovered class/form.
The dimensions are paired rather than multiplied into a Cartesian product.
"""
    yield 0, 0, 0, b'\x00\x00', b''
    yield 1, 0, 30, b'\x5e\x01', b'\xa7'
    yield 2, 0, 31, b'\x9f\x1f\x7f', bytes(range(127))
    yield 3, 0, 127, b'\xdf\x7f\x81\x80', bytes(range(128))
    yield 0, 1, 128, b'\x3f\x81\x00\x81\xff', b'\x04\x01z' + b'\x05\x00' * 126
    yield 1, 1, 201, b'\x7f\x81\x49\x82\x01\x00', b'\x05\x00' * 128
    yield 2, 1, 16383, b'\xbf\xff\x7f\x82\xff\xff', b'\x04\x01z' + b'\x05\x00' * 32766
    yield 3, 1, 16384, b'\xff\x81\x80\x00\x83\x01\x00\x00', b'\x05\x00' * 32768
    yield 2, 0, 34359738368, b'\x9f\x81\x80\x80\x80\x80\x00\x02', b'\xfe\x01'
