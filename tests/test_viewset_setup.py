from http import HTTPStatus

import pytest
from async_asgi_testclient import TestClient

from .main import app, Item, test_item, test_items_list

client = TestClient(app)
pytestmark = pytest.mark.asyncio
api_prefixes = {
    'argnames': 'prefix',
    'argvalues': ['', '/other'],
    'ids': ['unvalidated', 'validated']
}
pk = 42


class TestBasicViewSet:
    async def test_api_schema_is_accessable(self):
        response = await client.get('/openapi.json')
        assert response.status_code == HTTPStatus.OK

    @pytest.mark.parametrize(**api_prefixes)
    async def test_list(self, prefix):
        response = await client.get(prefix + '/')
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await Item.serialize(test_items_list)

    @pytest.mark.parametrize(**api_prefixes)
    async def test_retrieve(self, prefix):
        response = await client.get(f'{prefix}/{pk}')
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await test_item.get_serialized()

    @pytest.mark.parametrize(**api_prefixes)
    async def test_invalid_pk_retrieve(self, prefix):
        response = await client.get(prefix + '/foobar')
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.parametrize(**api_prefixes)
    async def test_create(self, prefix):
        data = {'id': 43, 'title': 'Yay'}
        created_item = Item(**data)
        response = await client.post(prefix + '/', json=data)
        assert response.status_code == HTTPStatus.CREATED
        assert response.json() == await created_item.get_serialized()

    @pytest.mark.parametrize(**api_prefixes)
    async def test_update(self, prefix):
        updated_item = Item(title='Yello')
        response = await client.put(f'{prefix}/{pk}', json=updated_item.dict())
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await updated_item.get_serialized()

    @pytest.mark.parametrize(**api_prefixes)
    async def test_update_partial(self, prefix):
        data = {'title': 'OK'}
        updated_item = Item(**data)
        response = await client.patch(f'{prefix}/{pk}', json=data)
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await updated_item.get_serialized()

    @pytest.mark.parametrize(**api_prefixes)
    async def test_destroy(self, prefix):
        response = await client.delete(f'{prefix}/{pk}')
        assert response.status_code == HTTPStatus.NO_CONTENT
        assert response.text == ''

    @pytest.mark.parametrize('path', [
        '/listroute', f'/{pk}/detail', '/listcustom', f'/{pk}/detailcustom'
    ], ids=['list', 'detail', 'list_named', 'detail_named'])
    async def test_custom_route(self, path):
        query_params = {'foo': 'one', 'bar': 42}
        invalid_response = await client.get(path)
        assert invalid_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        response = await client.get(path, query_string=query_params)
        assert response.status_code == HTTPStatus.OK
        assert response.json() == query_params
