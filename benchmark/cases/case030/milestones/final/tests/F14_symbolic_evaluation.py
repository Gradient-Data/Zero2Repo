# feature: F14
"""Symbolic expressions observed through their compiled numerical callables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from F05_helpers import interactive_session, require_exception
from F11_helpers import require_array_result


def test_ordered_typed_expression_results(tmp_path):
    for language in ('c', 'fortran'):
        def exercise(ezelvori):
            from F00_oracle import host_numpy as np
            from F00_oracle import host_sympy
            sp = host_sympy()
            from zelvori import lambdify

            x, y = sp.symbols('x y')
            # Reverse lexical order deliberately; subtraction is asymmetric.
            scalar = lambdify(x - y, {y: 'float', x: 'float'},
                              result_type='float', language=language, folder='scalar')
            for a, b in ((1.25, -2.5), (-3.0, 0.5), (4.0, 4.0)):
                expected = float((x - y).subs({y: a, x: b}))
                actual = scalar(a, b)
                assert np.asarray(actual).dtype == np.dtype("float64")
                require_array_result(actual, expected)

            array = lambdify(x - y, {y: 'float[:,:]', x: 'float[:,:]'},
                             result_type='float[:,:]', language=language, folder='array')
            for shape in ((2, 3), (3, 1)):
                a = np.arange(np.prod(shape), dtype=float).reshape(shape) / 4
                b = np.full(shape, -1.5)
                expected = sp.lambdify((y, x), x - y, 'numpy')(a, b)
                require_array_result(array(a, b), expected)

            sine = lambdify(sp.sin(x), {x: 'float[:]'}, result_type='float[:]',
                            language=language, folder='sine')
            for values in ([-0.75, 0.0, 0.5, 1.25], [2.0, -1.0]):
                a = np.array(values)
                require_array_result(sine(a), np.sin(a))

            single = lambdify(x - y,
                              {x: 'float32[:]', y: 'float32[:]'},
                              result_type='float32[:]',
                              language=language, folder='single')
            a = np.array([0.25, -2.0, 4.5], dtype=np.float32)
            b = np.array([1.5, 0.5, -1.25], dtype=np.float32)
            require_array_result(single(a, b), a - b)

        interactive_session(tmp_path / language, exercise)


def test_return_and_caller_owned_output(tmp_path):
    for language in ('c', 'fortran'):
        def exercise(ezelvori):
            from F00_oracle import host_numpy as np
            from F00_oracle import host_sympy
            sp = host_sympy()
            from zelvori import lambdify

            x, y = sp.symbols('x y')
            expression = x / y
            arguments = {x: 'float[:,:]', y: 'float[:,:]'}
            returned = lambdify(expression, arguments, language=language, folder='returned')
            output = lambdify(expression, arguments, result_type='float[:,:]',
                              use_out=True, language=language, folder='output')
            reference = sp.lambdify((x, y), expression, 'numpy')
            for shape in ((2, 3), (1, 4)):
                a = np.arange(1, np.prod(shape) + 1, dtype=float).reshape(shape)
                b = np.full(shape, 2.0)
                expected = reference(a, b)
                require_array_result(returned(a, b), expected)
                out = np.full(shape, np.nan)
                alias = out.view()
                output(a, b, out)
                require_array_result(alias, expected)
                # Reuse the same storage with new values, through keyword binding.
                a = -a
                output(a, b, out=out)
                require_array_result(alias, reference(a, b))

        interactive_session(tmp_path / language, exercise)


def test_invalid_expression_compilation_requests(tmp_path):
    def exercise(ezelvori):
        from F00_oracle import host_numpy as np
        from F00_oracle import host_sympy
        sp = host_sympy()
        from zelvori import lambdify

        x = sp.Symbol('x')
        valid = lambdify(x + 1, {x: 'float'}, language='c', folder='valid')
        require_array_result(valid(2.5), 3.5)
        invalid = [
            ({x: 'float[:]'}, {'use_out': True}),
            ([(x, 'float')], {}),
            ({'x': 'float'}, {}),
            ({x: float}, {}),
            ({x: 'float'}, {'result_type': np.dtype('float64')}),
        ]
        for index, (arguments, options) in enumerate(invalid):
            with require_exception(TypeError):
                lambdify(x + 1, arguments, language='c', folder=f'invalid_{index}', **options)
        require_array_result(valid(-1.5), -0.5)

    interactive_session(tmp_path / 'requests', exercise)
