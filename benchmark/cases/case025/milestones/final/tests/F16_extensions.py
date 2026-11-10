# feature: F16
"""Application contracts must affect checked calls and subsequent uses."""
from F16_helpers import check_application


def test_callable_and_constructor_contracts():
    check_application('''
        from application import loose, Record
        from typing import assert_type
        def use():
            assert_type(loose(3), str)
            loose('wrong')  # E: incompatible_argument
            loose()  # E: incompatible_call
            assert_type(loose(3), int)  # E: inference_failure
            assert_type(Record('name'), Record)
            Record(4)  # E: incompatible_argument
            Record()  # E: incompatible_call
    ''')


def test_argument_aware_check_and_result():
    _, findings = check_application('''
        from application import select
        from typing import assert_type
        def use(text: str, number: int):
            assert_type(select('ready'), bytes)
            assert_type(select(7), int)
            assert_type(select(number), int)
            assert_type(select(text), str)  # E: application_policy
            select('blocked')  # E: application_policy
            assert_type(select('ready'), str)  # E: inference_failure
            wrong: bytes = select(number)  # E: incompatible_assignment
    ''')
    by_line = {item['lineno']: item for item in findings}
    assert 'Selector requires a known string' in by_line[7]['description']
    assert 'Selector blocked by application' in by_line[8]['description']


def test_attribute_and_wrapper_contracts():
    check_application('''
        from application import Entity, Wrapped, Record
        from typing import assert_type, Literal
        def use(entity: Entity, cls: type[Entity]):
            assert_type(entity.title, str)
            assert_type(cls.title, str)
            entity.title = 5
            entity.title = 'wrong'  # E: incompatible_assignment
            assert_type(Entity.virtual, Literal[b'resolved'])
            assert_type(Wrapped('name'), Record)
            Wrapped(5)  # E: incompatible_argument
            assert_type(entity.title, int)  # E: inference_failure
    ''')


def test_registered_category_controls():
    from velnora.error_code import register_error_code
    registered = register_error_code("application_metadata", "Application category explanation")
    assert registered.name == "application_metadata"
    assert registered.description == "Application category explanation"
    source = '''
        from application import select
        def use():
            select('blocked')  # E: application_policy
    '''
    _, findings = check_application(source)
    assert 'Selector blocked by application' in findings[0]['description']
    clean = source.replace('  # E: application_policy', '')
    check_application(clean, settings='application_policy = false\n')
    check_application(source, settings='application_policy = true\n',
                      base_settings='application_policy = false\n')
    suppressed = clean.replace("select('blocked')", "select('blocked')  # static analysis: ignore[application_policy]")
    check_application(suppressed)
    check_application(suppressed + "        wrong: int = 'text'  # E: incompatible_assignment\n")


def test_approved_evaluation_results_and_failure():
    _, findings = check_application('''
        from application import evaluate
        from typing import assert_type, Literal
        def use():
            assert_type(evaluate('ab', 3), Literal['ababab'])
            assert_type(evaluate('q'), Literal['q'])
            assert_type(evaluate('xy', count=2), Literal['xyxy'])
            assert_type(evaluate('ab', 3), Literal['ab'])  # E: inference_failure
            evaluate('x', -1)  # E: incompatible_call
    ''')
    failed = [item for item in findings if item['code'] == 'incompatible_call']
    assert len(failed) == 1
    assert 'Negative repetition requested' in failed[0]['description']
