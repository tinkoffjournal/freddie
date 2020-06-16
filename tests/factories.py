from factory import Faker

from .app import Author, Post, Tag
from .utils import BaseFactory


class PostFactory(BaseFactory):
    slug = Faker('slug')
    title = Faker('catch_phrase')
    content = Faker('text')
    metadata = Faker('pydict', nb_elements=3, value_types=(int, str))
    author_id = Faker('random_digit_not_null')

    class Meta:
        model = Post


class AuthorFactory(BaseFactory):
    first_name = Faker('first_name')
    last_name = Faker('last_name')
    nickname = Faker('slug')

    class Meta:
        model = Author


class TagFactory(BaseFactory):
    name = Faker('word')
    slug = Faker('slug')

    class Meta:
        model = Tag
