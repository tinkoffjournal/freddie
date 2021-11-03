import pytest

from freddie.viewsets.dependencies import FilterBy


@pytest.fixture
def first_filter():
    class Filter:
        slug: str = None
    return {'slug'}, FilterBy.setup(Filter)


@pytest.fixture
def second_filter():
    class Filter:
        id: int = None
        title: str = None
    return {'id', 'title'}, FilterBy.setup(Filter)


def test_filter_by_attributes_exists(first_filter, second_filter):
    assert first_filter is not second_filter
    for expected_fields, filter_class in (first_filter, second_filter):
        assert expected_fields == set(filter_class.fields)
