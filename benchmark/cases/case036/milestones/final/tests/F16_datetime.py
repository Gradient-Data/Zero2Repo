# feature: F16
"""Acceptance tests for calendar and signed-duration operations."""
from datetime import date, datetime, timedelta
from _helpers import environment, require_python
from F16_helpers import CalendarWorkflow


def test_date_representations_and_ranges():
    require_python((3, 13))
    w = CalendarWorkflow()
    for text, value in [('2032-07-09', datetime(2032, 7, 9)),
                        ('2032-07-09 14', datetime(2032, 7, 9, 14)),
                        ('2032-07-09 14:23', datetime(2032, 7, 9, 14, 23)),
                        ('2032-07-09 14:23:41.123456', datetime(2032, 7, 9, 14, 23, 41, 123456)),
                        ('1900-01-01', datetime(1900, 1, 1)),
                        ('9999-12-31 23:59:59', datetime(9999, 12, 31, 23, 59, 59))]:
        w.operation('Convert Date', text, result_format='datetime', expected=value)
    value = datetime(2032, 7, 9, 14, 23, 41, 123000)
    w.operation('Convert Date', value, expected='2032-07-09 14:23:41.123')
    w.operation('Convert Date', value, result_format='date', expected=value.date())
    for value in (date(1, 1, 1), date(9999, 12, 31), date(2000, 2, 29)):
        w.operation('Convert Date', value, result_format='datetime', expected=datetime.combine(value, datetime.min.time()))
    w.operation('Convert Date', datetime(1, 1, 1, 12, 34, 56), result_format='datetime', expected=datetime(1, 1, 1, 12, 34, 56))
    for pattern in ('%d/%m/%Y %H:%M:%S.%f', '%Y-%j %H:%M:%S', '%Y-%m-%d'):
        value = datetime(2036, 2, 29, 17, 12, 33, 456789)
        text = value.strftime(pattern)
        w.operation('Convert Date', text, date_format=pattern, result_format='datetime',
                    expected=datetime.strptime(text, pattern))
        w.operation('Convert Date', value, result_format=pattern, expected=text)
    w.run_and_verify()
    # Fixed-offset zones make local epoch conversion observable without assuming
    # the judge's configured local zone or a platform-specific zone database.
    for zone in ('UTC0', 'EST5'):
        with environment({'TZ': zone}):
            w = CalendarWorkflow()
            w.lines += ['    ${epoch}=    Evaluate    datetime.datetime(2032,7,9,14,23,41,125000).timestamp()    modules=datetime',
                        '    ${actual}=    DateTime.Convert Date    ${epoch}    result_format=datetime',
                        '    Check    ${actual}    datetime(2032,7,9,14,23,41,125000)',
                        '    ${actual}=    DateTime.Convert Date    2032-07-09 14:23:41.125    result_format=epoch',
                        '    Should Be Equal    ${actual}    ${epoch}',
                        # Integer epoch seconds are numeric input too.
                        '    ${epoch}=    Evaluate    int(datetime.datetime(2032,7,9,14,23,41).timestamp())    modules=datetime',
                        '    ${actual}=    DateTime.Convert Date    ${epoch}    result_format=datetime',
                        '    Check    ${actual}    datetime(2032,7,9,14,23,41)',
                        # Epoch input keeps sub-millisecond precision in datetime results.
                        '    ${epoch}=    Evaluate    datetime.datetime(2032,7,9,14,23,41,125678).timestamp()    modules=datetime',
                        '    ${actual}=    DateTime.Convert Date    ${epoch}    result_format=datetime',
                        '    Check    ${actual}    datetime(2032,7,9,14,23,41,125678)']
            w.run_and_verify()


def test_duration_representations_units_and_rejections():
    w = CalendarWorkflow()
    units = [('nanoseconds', 1e-9), ('microseconds', 1e-6), ('milliseconds', .001),
             ('seconds', 1.), ('minutes', 60.), ('hours', 3600.), ('days', 86400.), ('weeks', 604800.)]
    for unit, ratio in units:
        w.operation('Convert Time', '1.25 ' + unit, expected=1.25 * ratio)
    for value, expected in [(17, 17.), (-2.125, -2.125), ('3.25', 3.25),
                            ('2:03', 123.), ('-1:02:03.125', -3723.125),
                            (timedelta(days=-1, seconds=2), -86398.)]:
        w.operation('Convert Time', value, expected=expected)
    for form, expected in [('number', -93784.125), ('verbose', '- 1 day 2 hours 3 minutes 4 seconds 125 milliseconds'),
                            ('compact', '- 1d 2h 3min 4s 125ms'), ('timer', '-26:03:04.125'),
                            ('timedelta', timedelta(seconds=-93784.125))]:
        w.operation('Convert Time', '-1 day 2 hours 3 minutes 4.125 seconds', result_format=form, expected=expected)
    w.operation('Convert Time', 360061.5, result_format='timer', expected='100:01:01.500')
    for value, options in [('not a duration', {}), ('1:2:3:4', {}), ('2 fortnights', {}), (1, {'result_format': 'unsupported'})]:
        w.operation('Convert Time', value, reject=True, **options)
    w.run_and_verify()


def test_calendar_and_duration_arithmetic():
    w = CalendarWorkflow()
    # Each boundary adds a distinct calendar rule; centuries distinguish the
    # Gregorian leap-year rule from a divisible-by-four approximation.
    for value, seconds in [(datetime(2031,12,31,23,59,59), 2),
                            (datetime(2031,4,30,23,59), 120),
                            (datetime(2000,2,28,12), 86400),
                            (datetime(1900,2,28,12), 86400),
                            (datetime(2024,3,1), -86400),
                            (datetime(2100,2,28), 86400)]:
        end = value + timedelta(seconds=seconds)
        w.operation('Add Time To Date', value, seconds, result_format='datetime', expected=end)
        w.operation('Subtract Time From Date', value, seconds, result_format='datetime', expected=value-timedelta(seconds=seconds))
        w.operation('Subtract Date From Date', end, value, expected=float(seconds))
        w.operation('Subtract Date From Date', value, end, expected=float(-seconds))
    w.operation('Subtract Date From Date', '2032-07-09 00:01:02.125', '2032-07-09', result_format='timer', expected='00:01:02.125')
    # Python results keep sub-millisecond input precision. The timedelta form is
    # exact at microsecond resolution, so any accurate subtraction method passes.
    start, later = datetime(2032,7,9), datetime(2032,7,10,0,0,1,234567)
    w.operation('Subtract Date From Date', later, start, result_format='timedelta', expected=later-start)
    w.operation('Add Time To Date', start, 90061.234567, result_format='datetime', expected=start+timedelta(seconds=90061.234567))
    # Text dates and text durations are accepted by date arithmetic.
    w.operation('Add Time To Date', '2024-02-28 23:59:59.500', '1 day 0.75 seconds', result_format='timestamp',
                expected=(datetime(2024,2,28,23,59,59,500000)+timedelta(days=1,seconds=.75)).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    w.operation('Subtract Time From Date', '2100-03-01 00:00:00.250', '1 day 0.75 seconds', result_format='timestamp',
                expected=(datetime(2100,3,1,0,0,0,250000)-timedelta(days=1,seconds=.75)).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    w.operation('Add Time To Time', '-1 hour', '15 minutes', expected=-2700.)
    w.operation('Subtract Time From Time', '15 minutes', '1 hour', expected=-2700.)
    w.operation('Subtract Time From Time', '-1 hour', '-15 minutes', result_format='timedelta', expected=timedelta(seconds=-2700))
    w.run_and_verify()


def test_current_clock_time_zones_and_increments():
    for zone in ('UTC0', 'EST5'):
        with environment({'TZ': zone}):
            w = CalendarWorkflow()
            w.lines += ['    ${before}=    Evaluate    datetime.datetime.now() - datetime.timedelta(microseconds=500)    modules=datetime',
                        '    ${text}=    DateTime.Get Current Date',
                        '    ${after}=    Evaluate    datetime.datetime.now() + datetime.timedelta(microseconds=500)    modules=datetime',
                        "    ${actual}=    Evaluate    datetime.datetime.strptime($text, '%Y-%m-%d %H:%M:%S.%f')    modules=datetime",
                        '    Should Be True    $before <= $actual <= $after']
            for selection in ('', 'time_zone=local', 'time_zone=UTC'):
                clock = 'datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)' if selection.endswith('UTC') else 'datetime.datetime.now()'
                for increment in (0, 91.125, -86400.25):
                    w.lines += [f'    ${{before}}=    Evaluate    {clock} + datetime.timedelta(seconds={increment})    modules=datetime',
                                f'    ${{actual}}=    DateTime.Get Current Date    result_format=datetime    increment={increment}    {selection}',
                                f'    ${{after}}=    Evaluate    {clock} + datetime.timedelta(seconds={increment})    modules=datetime',
                                '    Should Be True    $before <= $actual <= $after']
                # Default timestamp text follows the selection; half a millisecond of rounding.
                w.lines += [f'    ${{before}}=    Evaluate    {clock} - datetime.timedelta(microseconds=500)    modules=datetime',
                            f'    ${{text}}=    DateTime.Get Current Date    {selection}',
                            f'    ${{after}}=    Evaluate    {clock} + datetime.timedelta(microseconds=500)    modules=datetime',
                            "    ${actual}=    Evaluate    datetime.datetime.strptime($text, '%Y-%m-%d %H:%M:%S.%f')    modules=datetime",
                            '    Should Be True    $before <= $actual <= $after']
                # Text increments are durations as well.
                w.lines += [f'    ${{before}}=    Evaluate    {clock} + datetime.timedelta(hours=1)    modules=datetime',
                            f'    ${{actual}}=    DateTime.Get Current Date    result_format=datetime    increment=1 hour    {selection}',
                            f'    ${{after}}=    Evaluate    {clock} + datetime.timedelta(hours=1)    modules=datetime',
                            '    Should Be True    $before <= $actual <= $after']
                # Epoch output is the same instant under either selection and takes the increment.
                for increment in (0, 91.125):
                    w.lines += [f'    ${{before}}=    Evaluate    time.time() + {increment}    modules=time',
                                f'    ${{actual}}=    DateTime.Get Current Date    result_format=epoch    increment={increment}    {selection}',
                                f'    ${{after}}=    Evaluate    time.time() + {increment}    modules=time',
                                '    Should Be True    $before <= $actual <= $after']
            for word in ('ToDaY', 'nOw'):
                w.lines += ['    ${before}=    Evaluate    datetime.datetime.now()    modules=datetime',
                            f'    ${{actual}}=    DateTime.Convert Date    {word}    result_format=datetime',
                            '    ${after}=    Evaluate    datetime.datetime.now()    modules=datetime',
                            '    Should Be True    $before <= $actual <= $after']
            w.run_and_verify()


def test_fractional_precision_and_rounding():
    w = CalendarWorkflow()
    for micros, rounded, whole in [(123400, '2032-12-31 23:59:59.123', '2032-12-31 23:59:59'),
                                    (876600, '2032-12-31 23:59:59.877', '2033-01-01 00:00:00'),
                                    (999600, '2033-01-01 00:00:00.000', '2033-01-01 00:00:00')]:
        value = datetime(2032,12,31,23,59,59,micros)
        w.operation('Convert Date', value, expected=rounded)
        w.operation('Convert Date', value, exclude_millis=True, expected=whole)
        w.operation('Convert Date', value, result_format='datetime', expected=value)
        w.operation('Convert Date', value, result_format='datetime', exclude_millis=True, expected=datetime.fromisoformat(whole))
        w.operation('Convert Date', value, result_format='%Y-%m-%d %H:%M:%S.%f', expected=value.strftime('%Y-%m-%d %H:%M:%S.%f'))
    for value, rounded, integer in [(62.1234, '00:01:02.123', 62.), (-62.8766, '-00:01:02.877', -63.), (59.9996, '00:01:00.000', 60.)]:
        w.operation('Convert Time', value, result_format='timer', expected=rounded)
        w.operation('Convert Time', value, expected=value)
        w.operation('Convert Time', value, exclude_millis=True, expected=integer)
        w.operation('Convert Time', value, result_format='timedelta', expected=timedelta(seconds=value))
        w.operation('Convert Time', value, result_format='timedelta', exclude_millis=True, expected=timedelta(seconds=integer))
    w.operation('Convert Time', 62.1234, result_format='verbose', expected='1 minute 2 seconds 123 milliseconds')
    w.operation('Convert Time', 62.8766, result_format='compact', expected='1min 2s 877ms')
    w.operation('Convert Time', 62.8766, result_format='verbose', exclude_millis=True, expected='1 minute 3 seconds')
    w.operation('Convert Time', 62.8766, result_format='compact', exclude_millis=True, expected='1min 3s')
    w.operation('Convert Time', 62.8766, result_format='timer', exclude_millis=True, expected='00:01:03')
    w.operation('Convert Time', -62.8766, result_format='timer', exclude_millis=True, expected='-00:01:03')
    w.operation('Convert Time', -62.8766, result_format='compact', exclude_millis=True, expected='- 1min 3s')
    # Validate the whole declared carrier before interpreting its unit pairs.
    seconds = {'day': 86400, 'hour': 3600, 'minute': 60, 'second': 1, 'millisecond': .001,
               'd': 86400, 'h': 3600, 'min': 60, 's': 1, 'ms': .001}
    for form, pattern in [('verbose', r'([0-9]+) (days?|hours?|minutes?|seconds?|milliseconds?)'),
                          ('compact', r'([0-9]+)(d|h|min|s|ms)')]:
        w.lines += [f'    ${{actual}}=    DateTime.Convert Time    59.9996    result_format={form}',
                    f'    ${{valid}}=    Evaluate    re.fullmatch({(pattern + r"(?: " + pattern + r")*")!r}, $actual) is not None    modules=re',
                    '    Should Be True    ${valid}',
                    f'    ${{total}}=    Evaluate    round(sum(int(n) * {seconds!r}[u.removesuffix("s") if u.endswith("s") and u not in ("s", "ms") else u] for n, u in re.findall({pattern!r}, $actual)), 3)    modules=re',
                    '    Should Be True    $total == 60']
    # Whole-second rounding also applies to epoch results when requested.
    w.lines += ['    ${actual}=    DateTime.Convert Date    2032-07-09 14:23:41.876543    result_format=epoch    exclude_millis=True',
                '    ${expected}=    Evaluate    datetime.datetime(2032,7,9,14,23,42).timestamp()    modules=datetime',
                '    Should Be Equal    ${actual}    ${expected}']
    w.lines += ['    ${actual}=    DateTime.Convert Date    2032-07-09 14:23:41.123456    result_format=epoch',
                '    ${expected}=    Evaluate    datetime.datetime(2032,7,9,14,23,41,123456).timestamp()    modules=datetime',
                '    Should Be Equal    ${actual}    ${expected}']
    w.run_and_verify()


def test_invalid_dates_formats_and_time_zones():
    w = CalendarWorkflow()
    w.operation('Convert Date', '2000-02-29', expected='2000-02-29 00:00:00.000')
    w.operation('Convert Date', '9999-12-31', result_format='date', expected=date(9999,12,31))
    for value, options in [('1900-02-29', {}), ('2032-04-31', {}), ('2032-13-01', {}),
                            ('2032-07-09 24:00:00', {}), ('0000-01-01', {}), ('10000-01-01', {}),
                            ('09/07/2032', {'date_format':'%Y-%m-%d'}),
                            ('2032-07-09', {'date_format':'%Y-%m-%d %H:%M:%S'}),
                            ('2032-07-09', {'result_format':'unsupported'})]:
        w.operation('Convert Date', value, reject=True, **options)
    w.operation('Get Current Date', time_zone='Mars', result_format='datetime', reject=True)
    w.run_and_verify()
