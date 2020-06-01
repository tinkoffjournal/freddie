# 🕺 Freddie

Declarative CRUD viewsets for [FastAPI](https://fastapi.tiangolo.com/),
inspired by [Django REST Framework](https://www.django-rest-framework.org/).

## Installation

```bash
pip install freddie
```

## Usage

```python
from fastapi import FastAPI
from freddie.exceptions import NotFound
from freddie.schemas import Schema
from freddie.viewsets import FieldedRetrieveViewset, PaginatedListViewset, route, ViewSet

# Schema is just a superset of Pydantic model
class Post(Schema):
    id: int = ...
    title: str = ...
    content: str = ''
    metadata: dict = {}

    class Config:
        # By default, only post id & title will be returned in API response
        default_readable_fields = {'id', 'title'}


post = Post(id=1, title='Freddie', content='Mercury', metadata={'views': 42})

# Viewset is a full-packed CRUD class, so all actions (list/retrieve/create/update/delete) must be implemented,
# other combinations are also possible, as in DRF (see freddie.viewsets)
class PostViewSet(
    FieldedRetrieveViewset,  # This mixin allows retrieving non-default schema fields from query params
    PaginatedListViewset,  # This mixin adds paginator parameter with limit/offset query params
    ViewSet
):
    schema = Post

    # Default viewset pagination options are set here
    class Paginator:
        default_limit = 10
        max_limit = 100

    async def list(self, *, paginator, **params):
        for i in range(1, paginator.limit + 1):
            item_id = i + paginator.offset
            yield Post(id=item_id, title=f'Freddie #{item_id}')

    # Both sync & async handlers are supported, thanks to Starlette
    def retrieve(self, pk: int, **params):
        if pk != post.id:
            raise NotFound
        return post

    async def create(self, body: Post, **params):
        return body

    async def update(self, pk: int, body: Schema, **params):
        updated_post = post.copy()
        for key, value in body.dict(exclude_unset=True).items():
            setattr(updated_post, key, value)
        return updated_post

    async def destroy(self, pk: int, **params):
        ...

    # Add custom handler on /{pk}/meta path
    @route(detail=True)
    async def meta(self, pk: int):
        return {pk: post.metadata}

    # Add custom handler on /meta path
    @route(detail=False, name='meta')
    async def other_meta(self):
        return post.metadata


app = FastAPI()
app.include_router(PostViewSet(), prefix='/posts')
```
