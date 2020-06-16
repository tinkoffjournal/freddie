from typing import Union
from uuid import UUID

from pydantic import BaseModel, create_model
from pytest import mark, raises

from freddie.schemas import Schema
from freddie.viewsets.generics import GenericViewSet

from .utils import create_schema_from_config


class InvalidViewSet(GenericViewSet):
    ...


class ViewSet(GenericViewSet):
    def api_actions(self):
        pass


class UserString(str):
    ...


class TestViewSetInit:
    def test_viewset_without_actions(self):
        with raises(TypeError):
            InvalidViewSet()

    @mark.parametrize('schema', ['not_a_class', BaseModel])
    def test_invalid_viewset_schema_class(self, schema):
        with raises(AssertionError):
            ViewSet(schema=schema)

    def test_auto_component_names(self):
        schema_class = create_model('FooBar', __base__=Schema)
        viewset = ViewSet(schema=schema_class)
        assert viewset._component_name == 'foobar'
        assert viewset._component_name_plural == 'foobars'

    @mark.parametrize(
        'config_names,viewset_names',
        [
            (('api_component', None), ('api_component', 'api_components')),
            (('api_component', ''), ('api_component', 'api_components')),
            (('One_More_Name', 'and_anothers'), ('one_more_name', 'and_anothers')),
        ],
    )
    def test_custom_component_names(self, config_names, viewset_names):
        component_name, component_name_plural = config_names
        expected_name, expected_name_plural = viewset_names
        config = {
            'api_component_name': component_name,
            'api_component_name_plural': component_name_plural,
        }
        schema = create_schema_from_config(config)
        viewset = ViewSet(schema=schema)
        assert viewset._component_name == expected_name
        assert viewset._component_name_plural == expected_name_plural

    @mark.parametrize(
        'pk_type,choices',
        [
            (int, (int,)),
            (UUID, (UUID,)),
            (Union[int, UserString, UUID], (int, UserString, UUID)),
            (UserString, (UserString,)),
        ],
        ids=('simple_pk', 'uuid', 'types_union', 'user_type'),
    )
    def test_valid_pk_types(self, pk_type, choices):
        assert ViewSet(pk_type=pk_type)._pk_type_choices == choices

    @mark.parametrize(
        'pk_type',
        [list, BaseModel, Union[str, tuple]],
        ids=('simple', 'model_class', 'part_valid_union'),
    )
    def test_invalid_pk_types(self, pk_type):
        with raises(TypeError):
            ViewSet(pk_type=pk_type)
