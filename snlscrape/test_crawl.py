import scrapy
import scrapy.crawler
from scrapy.utils.project import get_project_settings

import pytest
import datetime

from snlscrape.items import *
from snlscrape import helpers
import snlscrape.items
import snlscrape.settings_testing
from snlscrape.spiders.snl import SnlSpider

# TODO: offline, Betamax, middleware, whatever

class ItemBasket(object):

  def __init__(self):
    self.items = []

  def add_item(self, item):
    self.items.append(item)

  def of_type(self, entity_type):
    return [item for item in self.items if isinstance(item, entity_type)]

  def n_of_type(self, entity_type):
    return len(self.of_type(entity_type))

  def peek(self, entity_type=None):
    for thing in self.items:
      if entity_type is None or isinstance(thing, entity_type):
        return thing
    raise Exception('empty')

  def actor_names(self):
    return set(self.actor_lookup().keys())

  def actor_lookup(self):
    actors = self.of_type(Actor)
    return {a['name']: a for a in actors}

  def appearance_lookup(self):
    actors = self.of_type(Actor)
    aid_lookup = {a['aid']: a for a in actors}
    apps = self.of_type(Appearance)
    return {aid_lookup[app['aid']] : app for app in apps}

  def get_title(self, name):
    for title in self.of_type(Title):
      if title['name'] == name:
        return title

class CollectorExtension(object):

  def __init__(self):
    self.items = ItemBasket()

  @classmethod
  def from_crawler(cls, crawler):
    ext = cls()
    crawler.signals.connect(ext.item_scraped, signal=scrapy.signals.item_scraped)
    return ext

  def item_scraped(self, item, spider):
    self.items.add_item(item)


def crawl(tids):
  settings = get_project_settings()
  settings.setmodule(snlscrape.settings_testing)
  settings.set('SNL_TARGET_TIDS', tids)
  crawler = scrapy.crawler.Crawler(SnlSpider, settings)

  collector = CollectorExtension.from_crawler(crawler)

  cp = scrapy.crawler.CrawlerProcess(settings)
  cp.crawl(crawler)
  cp.start()
  return collector.items

all_tids = [
  '2002051810', # lovers
  '2005111211', # buttp
]

@pytest.fixture(scope="module")
def basket():
  return crawl(all_tids)

def test_high_level(basket):
  scraped_sids = {s['sid'] for s in basket.of_type(Season)}
  all_sids = set(map(helpers.Sid.from_tid, all_tids))
  assert 27 in all_sids
  assert set(all_sids) == set(scraped_sids)

  scraped_epids = {e['epid'] for e in basket.of_type(Episode)}
  all_epids = map(helpers.Epid.from_tid, all_tids)
  assert set(all_epids) == set(scraped_epids)

  scraped_tids = {t['tid'] for t in basket.of_type(Title)}
  assert scraped_tids == set(all_tids)

def test_lovers(basket):
  # http://www.snlarchives.net/Episodes/?2002051810
  tid = '2002051810'
  
  title = basket.get_title('Lovers')
  assert title

  actor_names = {'Winona Ryder', 'Rachel Dratch', 'Jimmy Fallon', 'Will Ferrell'}
  assert actor_names <= basket.actor_names()

  assert title['name'] == 'Lovers'
  assert title['category'] == 'Sketch'
  # Not labelled as a recurring sketch, though I kind of feel that it should be...
  assert not title.get('skid')
  assert title['order'] == 9

  actors = basket.actor_lookup()
  winona = actors['Winona Ryder']
  assert winona['type'] == 'guest'
  assert actors['Rachel Dratch'] == Actor(name='Rachel Dratch', type='cast', aid='c_RaDr')

  #apps = thing.appearance_lookup()

def test_butt_pregnancy(basket):
  # http://www.snlarchives.net/Episodes/?2005111211
  tid = '2005111211'
  title = basket.get_title('Butt Pregnancy')
  assert title

def test_helpers():
  tid = '2002051810' # lovers
  date = helpers.Tid.to_date(tid)
  assert date == datetime.date(2002, 5, 18)
  sid = helpers.Sid.from_tid(tid)
  assert sid == 27
  epid = helpers.Epid.from_tid(tid)
  assert epid == '20020518'
