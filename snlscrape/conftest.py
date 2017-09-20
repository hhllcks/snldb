
def pytest_assertrepr_compare(op, left, right):
  if isinstance(left, set) and isinstance(right, set) and op == '<=':
    return [
        'Elements not contained in RHS:',
        '{}'.format(left - right),
        ]
