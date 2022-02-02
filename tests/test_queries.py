from pytest import mark

from freddie.db.queries import Prefetch, prefetch_related

from .app import Author, AuthorTags
from .factories import AuthorFactory, TagFactory

pytestmark = [mark.asyncio, mark.db]


class TestManyToManyModelViewSet:
    async def test_prefetched_relations(self):
        author = AuthorFactory.create()
        watched_tag, ignored_tag = TagFactory.create_batch(2)
        AuthorTags(author=author, tag=watched_tag, is_notifications_on=True).save()
        AuthorTags(author=author, tag=ignored_tag, is_notifications_on=False).save()

        prefetcher = Prefetch(
            field=Author.tags, attr_name='tags', relation_fields=['is_notifications_on']
        )
        author = await prefetch_related([author], [prefetcher]).__anext__()

        expected = set(map(lambda x: (x.id, x.is_notifications_on), author.tags))
        assert expected == {(watched_tag.id, True), (ignored_tag.id, False)}
