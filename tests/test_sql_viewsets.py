from http import HTTPStatus
from random import choice as rand_choice

from playhouse.shortcuts import model_to_dict
from pydantic import Field, constr
from pytest import fixture, mark, raises

from freddie.db.queries import set_related
from freddie.viewsets import ModelViewSet

from .app import Log, Post, PostSchema, PostTags, TagSchema
from .factories import AuthorFactory, PostFactory, TagFactory
from .utils import WithClient

pytestmark = [mark.asyncio, mark.db]
post_model = PostFactory._meta.model
author_model = AuthorFactory._meta.model


class ModelViewSetMixin(WithClient):
    @fixture(scope='function', autouse=True)
    def _add_related_items(self):
        self.authors = AuthorFactory.create_batch(size=10)
        self.tags = TagFactory.create_batch(size=5)


class TestSimpleModelViewSet(ModelViewSetMixin):
    async def test_list(self):
        batch_size = 3
        posts = PostFactory.create_batch(size=batch_size)
        response = await self.client.get('/post/')
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert len(response_data) == batch_size
        assert response_data == await PostSchema.serialize(posts)

    async def test_list_pagination(self):
        first_chunk_size = 5
        second_chunk_size = 3
        posts = PostFactory.create_batch(size=first_chunk_size + second_chunk_size)
        response = await self.client.get('/post/', query_string={'limit': first_chunk_size})
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert len(response_data) == first_chunk_size
        assert response_data == await PostSchema.serialize(posts[:first_chunk_size])
        response = await self.client.get('/post/', query_string={'offset': first_chunk_size})
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert len(response_data) == second_chunk_size
        assert response_data == await PostSchema.serialize(posts[first_chunk_size:])

    @fixture
    def slugs(self):
        posts = PostFactory.create_batch(size=10)
        return [post.slug for post in posts]

    @mark.parametrize(
        'slug_getter,results_count',
        [(lambda slugs: rand_choice(slugs), 1), (lambda slugs: 'non-existing-slug', 0)],
        ids=['existing', 'nonexisting'],
    )
    async def test_filtering(self, slug_getter, results_count, slugs):
        lookup_slug = slug_getter(slugs)
        response = await self.client.get('/post/', query_string={'slug': lookup_slug})
        assert response.status_code == HTTPStatus.OK
        assert len(response.json()) == results_count

    @mark.parametrize('pk_attr', ['id', 'slug'])
    async def test_retrieve(self, pk_attr):
        post = PostFactory()
        pk = getattr(post, pk_attr)
        response = await self.client.get(f'/post/{pk}')
        assert response.status_code == HTTPStatus.OK
        assert response.json() == await PostSchema.serialize(post)

    async def test_create(self):
        author = AuthorFactory()
        post_data = {
            'title': 'Very New Post',
            'slug': 'post',
            'author_id': author.id,
        }
        response = await self.client.post('/post/', json=post_data)
        assert response.status_code == HTTPStatus.CREATED
        response_data = response.json()
        post_id = response_data['id']
        for key, value in post_data.items():
            assert response_data[key] == value
        response = await self.client.get(f'/post/{post_id}')
        assert response.status_code == HTTPStatus.OK
        obj = Post.get_by_id(post_id)
        assert await PostSchema.serialize(obj) == response.json()

    async def test_create_empty_body(self):
        response = await self.client.post('/post-create/', json={})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    async def test_update(self):
        post = PostFactory()
        updated_data = {
            'title': 'Much Updated Title',
            'slug': 'new-slug',
        }
        response = await self.client.patch(f'/post/{post.id}', json=updated_data)
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        obj = Post.get_by_id(post.id)
        for key, value in updated_data.items():
            assert response_data[key] == value
            assert getattr(obj, key) == value

    async def test_destroy(self):
        post = PostFactory()
        response = await self.client.delete(f'/post/{post.id}')
        assert response.status_code == HTTPStatus.NO_CONTENT
        assert response.text == ''
        with raises(Post.DoesNotExist):
            Post.get_by_id(post.id)

    @mark.parametrize(
        'post_data,expected',
        [
            ({'title': None, 'slug': 'post-slug'}, HTTPStatus.UNPROCESSABLE_ENTITY,),
            (
                {'title': 'The New Post', 'slug': 'post-slug', 'author_id': 100500},
                HTTPStatus.BAD_REQUEST,
            ),
        ],
        ids=['unset_required_field', 'nonexisting_fk'],
    )
    async def test_invalid_create_request(self, post_data, expected):
        response = await self.client.post('/post/', json=post_data)
        assert response.status_code == expected

    async def test_unique_violation(self):
        slug = 'post'
        PostFactory(slug=slug)
        response = await self.client.post('/post/', json={'title': 'Some', 'slug': slug})
        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestValidatedModelViewSet(ModelViewSetMixin):
    async def test_list(self):
        batch_size = 3
        PostFactory.create_batch(size=batch_size)
        response = await self.client.get('/post-validated/')
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert len(response_data) == batch_size


class TestRequestFields(ModelViewSetMixin):
    async def test_subfields(self):
        post = PostFactory()
        request_fields = {'author': ['nickname'], 'tags': ['slug']}
        fields_config = ','.join(
            (f'{field}({",".join(subfields)})' for field, subfields in request_fields.items())
        )
        response = await self.client.get(f'/post/{post.id}', query_string={'fields': fields_config})
        response_data = response.json()
        for field, subfields in request_fields.items():
            for subfield in subfields:
                subitem = response_data[field]
                if isinstance(subitem, dict):
                    assert subfield in response_data[field]
                elif isinstance(subitem, list):
                    for i in subitem:
                        assert subfield in i

    async def test_extra_fn(self):
        batch_size = 3
        PostFactory.create_batch(size=batch_size)
        response = await self.client.get(f'/post/extra')
        assert response.json() == batch_size


class TestSignals(ModelViewSetMixin):
    async def test_signal_on_create(self):
        post_data = {'title': 'Wow', 'slug': 'wow'}
        response = await self.client.post('/post/', json=post_data)
        post = response.json()
        post_id = post['id']
        log = Log.get(Log.obj_id == post_id, Log.action_type == Log.ActionType.CREATE)
        assert log.state_before is None
        assert log.state_after == post

    async def test_signal_on_update(self):
        post = PostFactory()
        post_serialized = await PostSchema.serialize(post, full=True)
        updated_data = {'title': 'Such'}
        await self.client.patch(f'/post/{post.id}', json=updated_data)
        log = Log.get(Log.obj_id == post.id, Log.action_type == Log.ActionType.UPDATE)
        assert log.state_before == post_serialized
        assert log.state_after == {**post_serialized, **updated_data}

    async def test_signal_on_delete(self):
        post = PostFactory()
        post_serialized = await PostSchema.serialize(post, full=True)
        await self.client.delete(f'/post/{post.id}')
        log = Log.get(Log.obj_id == post.id, Log.action_type == Log.ActionType.DESTROY)
        assert log.state_before == post_serialized
        assert log.state_after is None


class TestManyToManyModelViewSet(ModelViewSetMixin):
    post_data = {
        'title': 'Very New Post',
        'slug': 'post',
    }

    async def test_prefetched_relations(self):
        posts = PostFactory.create_batch(size=3)
        tags = await TagSchema.serialize(self.tags)
        for post in posts:
            await set_related(post.id, type(post).tags, (tag.id for tag in self.tags))
        response = await self.client.get('/post/')
        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        for post in response_data:
            assert post['tags'] == tags

    async def test_create_entry_with_relations(self):
        tags_ids = [tag.id for tag in self.tags]
        post_data = {
            **self.post_data,
            'tags_ids': tags_ids,
        }
        response = await self.client.post('/post/', json=post_data)
        assert response.status_code == HTTPStatus.CREATED
        response_data = response.json()
        post_id = response_data['id']
        assert response_data['tags'] == await TagSchema.serialize(self.tags, full=True)
        relations = PostTags.select().where(PostTags.post == post_id)
        related_tags_ids = [rel.tag_id for rel in relations]
        assert len(related_tags_ids) == len(tags_ids)

    async def test_update_entry_relations(self):
        post = PostFactory()
        await set_related(post.id, type(post).tags, (tag.id for tag in self.tags))
        updated_tags = TagFactory.create_batch(size=3)
        response = await self.client.patch(
            f'/post/{post.id}', json={'tags_ids': [tag.id for tag in updated_tags]}
        )
        response_data = response.json()
        assert response_data['tags'] == await TagSchema.serialize(updated_tags, full=True)
        assert response.status_code == HTTPStatus.OK

    def test_actions_with_field_attr(self):
        post = PostFactory()
        tags_ids = [tag.id for tag in self.tags]
        builder = type(post).tags(post.id)
        with raises(ValueError):
            builder.add()
        builder.add(*tags_ids).execute()
        relations = PostTags.select().where(PostTags.post == post.id)
        related_tags_ids = [rel.tag_id for rel in relations]
        assert related_tags_ids == tags_ids
        assert list(builder.get().execute()) == self.tags
        builder.clear().execute()
        assert len(list(PostTags.select().where(PostTags.post == post.id))) == 0


class TestOrderedModelViewSet(ModelViewSetMixin):
    async def test_model_ordering(self):
        PostFactory.create(slug='ccc')
        PostFactory.create(slug='aaa')
        PostFactory.create(slug='bbb')
        response = await self.client.get('/post-ordered/')
        response_data = response.json()
        get_post_slug = lambda post: post.get('slug')
        assert list(map(get_post_slug, response_data)) == ['aaa', 'bbb', 'ccc']


@mark.parametrize(
    'selected,expected',
    [
        ([post_model.title], ['id', 'title']),
        ([], ['id']),
        ([post_model.title, 'slug', 'nonexisting'], ['id', 'title', 'slug']),
        (['title', author_model], ['id', 'title', 'author']),
    ],
    ids=['single_field', 'empty_fieldset', 'nonexisting_field', 'joined_model'],
)
def test_model_select_only_method(selected, expected):
    author = AuthorFactory()
    post = PostFactory(author=author)
    query = post_model.select_only(*selected).where(post_model.id << [post.id])
    for post in query.execute():
        for key, value in model_to_dict(post).items():
            is_none = key not in expected
            assert (value is None) == is_none


@mark.parametrize('pk', [100500, 'unslug'])
async def test_notfound(client, pk):
    response = await client.get(f'/post/{pk}')
    assert response.status_code == HTTPStatus.NOT_FOUND


@mark.parametrize(
    'field_type,default_value',
    [(constr(), ...), (constr(max_length=256), ...), (str, Field()), (str, Field(max_length=300))],
    ids=['no_maxlen_constr', 'outbound_constr', 'no_maxlen_field', 'outbound_field'],
)
def test_incomplete_schema(field_type, default_value):
    class PostIncomplete(PostSchema):
        title: field_type = default_value

    with raises(AssertionError):
        ModelViewSet(model=Post, schema=PostIncomplete)
