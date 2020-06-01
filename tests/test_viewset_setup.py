from http import HTTPStatus

import pytest
from async_asgi_testclient import TestClient

from freddie.viewsets.dependencies import Paginator
from .main import app, Item, test_item, test_items_seq

client = TestClient(app)
pytestmark = pytest.mark.asyncio
api_prefixes = {
    'argnames': 'prefix',
    'argvalues': ['/unvalidated', '/validated', '/sync'],
    'ids': ['unvalidated', 'validated', 'synchronous']
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
        assert response.json() == await Item.serialize(test_items_seq)

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

    ROUTE_QUERY_PARAMS = {'foo': 'one', 'bar': 42}

    @pytest.mark.parametrize('path', [
        '/unvalidated/listroute', f'/unvalidated/{pk}/detail',
        '/unvalidated/listcustom', f'/unvalidated/{pk}/detailcustom'
    ], ids=['list', 'detail', 'list_named', 'detail_named'])
    async def test_custom_route(self, path):
        invalid_response = await client.get(path)
        assert invalid_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        response = await client.get(path, query_string=self.ROUTE_QUERY_PARAMS)
        assert response.status_code == HTTPStatus.OK
        assert response.json() == self.ROUTE_QUERY_PARAMS


class TestPaginatedViewSet:
    @pytest.mark.parametrize('limit,offset', [
        (Paginator.default_limit, Paginator.default_offset),
        (10, 3),
    ])
    async def test_default_pagination(self, limit, offset):
        response = await client.get('/paginated/', query_string={'limit': limit, 'offset': offset})
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert len(response_data) == limit
        assert response_data[limit - 1]['id'] == limit + offset

    @pytest.mark.parametrize('limit,offset', [
        ('string', 10),
        (20, 'foobar'),
        (Paginator.max_limit + 1, 0),
        (Paginator.max_limit + 100, 200),
    ])
    async def test_invalid_values(self, limit, offset):
        response = await client.get('/paginated/', query_string={'limit': limit, 'offset': offset})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestFieldedViewSet:
    async def test_keys_passed(self):
        fields = ['title']
        response = await client.get(f'/fielded/{pk}', query_string={'fields': ','.join(fields)})
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        for field in fields:
            assert field in response_data


async def test_http_exceptions():
    detail = 'NOTFOUND'
    header = 'custom-header'
    response = await client.get('/notfound', query_string={'detail': detail, 'header': header})
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json().get('detail') == detail
    assert response.headers['x-custom-header'] == header
