# feature: F13
"""Real framework method configuration, using the shared CLI helpers."""
from textwrap import dedent
from _helpers import workspace
from F02_helpers import config_file, check_configured


def check_task_methods():
    import asynq  # Required dependency; absence is an error, never a skip.

    source = dedent('''\
        from asynq import asynq
        @asynq()
        def number() -> int:
            return 8
        class Base:
            def regular(self):
                return number()  # checked
            def exempt(self):
                return number()
            @classmethod
            def class_method(cls):
                return number()
        class Child(Base):
            def regular(self):
                return number()  # checked
            @asynq()
            def exempt(self):
                return number()  # always
        class Unrelated:
            def regular(self):
                return number()
    ''')
    for configured in (False, True):
        with workspace({'subject.py': source}) as root:
            body = 'methods_not_checked_for_asynq = ["exempt"]\n'
            if configured:
                body += 'classes_checked_for_asynq = ["subject.Base"]\n'
            config = config_file(root, body)
            expected = [('subject.py', line, 'impure_async_call')
                        for line, text in enumerate(source.splitlines(), 1)
                        if '# always' in text or configured and '# checked' in text]
            check_configured(root, config, [root / 'subject.py'], expected=expected)
