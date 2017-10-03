import scrapy
import scrapy.crawler
from scrapy.utils.project import get_project_settings

from snlscrape.items import *
import snlscrape.settings_testing
from snlscrape.spiders.snl import SnlSpider

def crawl(tids):
  """Do a crawl targetting the given title ids, and return an ItemBasket with
  all crawled entities.
  """
  settings = get_project_settings()
  settings.setmodule(snlscrape.settings_testing)
  settings.set('SNL_TARGET_TIDS', tids)
  crawler = scrapy.crawler.Crawler(SnlSpider, settings)

  collector = CollectorExtension.from_crawler(crawler)

  cp = scrapy.crawler.CrawlerProcess(settings)
  cp.crawl(crawler)
  cp.start()
  return collector.items

def assert_item_props(item, **kwargs):
  """Do the given key, values match the given Item? i.e. are they a subset of
  the Item's items (in the lowercase, dict sense)"""
  for k, v in kwargs.items():
    assert item.get(k) == v

# Sorry, this class was already pretty sprawling and crufty, and it got even more
# crufty after refactoring Actor items to use name as primary key instead of old 'aid's
class ItemBasket(object):
  """A container class for Items. Has a bunch of helper methods to facilitate
  querying for particular kinds of items matching certain criteria. (Implementation
  is not at all efficient, but that's fine because this is only used for testing, 
  where we're unlikely to scrape more than ~100s of entities.
  """

  def __init__(self):
    self.items = []

  def add_item(self, item):
    self.items.append(item)

  def of_type(self, entity_type):
    return [item for item in self.items if isinstance(item, entity_type)]

  def actor_names(self):
    return set(self.actor_lookup().keys())

  def actor_lookup(self):
    return self._get_name_lookup(Actor)

  def _get_by_name(self, name, entity_type):
    return self._get_name_lookup(entity_type)[name]

  def _get_name_lookup(self, entity_type):
    namekey = 'aid' if entity_type == Actor else 'name'
    return {entity[namekey] : entity for entity in self.of_type(entity_type)}

  def get_title(self, name):
    return self._get_by_name(name, Title)

  def get_actor(self, name):
    return self._get_by_name(name, Actor)

  def query(self, entity_type, **kwargs):
    """Yield all items matching criteria.
    """
    cands = self.of_type(entity_type)
    for cand in cands:
      for (fieldname, target_val) in kwargs.items():
        if cand.get(fieldname) != target_val:
          break
      # If we didn't break (i.e. no mismatch), then this is a good candidate
      else:
        yield cand

  def get_matches(self, entity_type, by=None, **kwargs):
    if by:
      return {thing[by]: thing for thing in self.query(entity_type, **kwargs)}
    return list(self.query(entity_type, **kwargs))

  def get(self, entity_type, key=None, **kwargs):
    """Return only item matching criteria.
    """
    things = self.get_matches(entity_type, **kwargs)
    assert len(things) == 1
    thing = things[0]
    if key:
      return thing[key]
    else:
      return thing

  def by_actor(self, entities):
    actor_lookup = self.get_matches(Actor, by='aid')
    res = {}
    for thing in entities:
      name = thing['aid']
      if name in res:
        # We're not going above 2 for now
        assert not isinstance(res[name], list)
        res[name] = [res[name], thing]
      else:
        res[name] = thing
    return res

  def appearance_lookup(self, **kwargs):
    apps = self.query(Appearance, **kwargs)
    return self.by_actor(apps)

  def get_host(self, name):
    aid = self.get_actor(name)['aid']
    return self.get(Host, aid=aid)

class CollectorExtension(object):
  """An extension for collecting scraped items into an ItemBasket.
  """

  def __init__(self):
    self.items = ItemBasket()

  @classmethod
  def from_crawler(cls, crawler):
    ext = cls()
    crawler.signals.connect(ext.item_scraped, signal=scrapy.signals.item_scraped)
    return ext

  def item_scraped(self, item, spider):
    self.items.add_item(item)
