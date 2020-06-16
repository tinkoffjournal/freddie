import pytest

from freddie.helpers import is_iterable


def gen():
    yield 'generator'


@pytest.mark.parametrize(
    'value,result',
    [
        (['foo', 'bar', 42], True),
        ({'foo', 'bar', 42}, True),
        ({'foo': 'bar'}, True),
        ((_ for _ in range(3)), True),
        (gen(), True),
        ('string', False),
        ('bytes'.encode(), False),
    ],
)
def test_is_iterable(value, result):
    assert is_iterable(value) == result
