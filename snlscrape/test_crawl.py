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

# TODO: Organize this module, maybe split into additional modules.

# TODO: Unfortunately the current mechanics of crawling and testing are good
# for testing recall but not precision. i.e. it's easy to declare which items
# *should* be scraped and detect if they're missing, but harder to identify
# items that were scraped but shouldn't have been. (Basically because we scrape
# everything in one go, for technical twisted reasons, all scraped items are
# in the same pool, so it'd be exhausting to enumerate every single item that
# should be scraped.)

class ItemBasket(object):

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
    return {entity['name'] : entity for entity in self.of_type(entity_type)}

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
      name = actor_lookup[thing['aid']]['name']
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

named_tids = dict(
  # S27 E20 (Winona Ryder)
  jeopardy = '200205183',
  botox = '200205186',
  lovers = '2002051810',

  # S39 E4 (Edward Norton)
  cold_open_obamacare = '201310261',
  monologue_ed_norton = '201310262',
)

all_tids = named_tids.values()

# Useful as a check to make sure that if an episode has n titles, then that many get scraped.
# But as long as there's no on-disk caching layer, I'm going to leave it off by default, to
# keep the number of requests per test invocation low.
SCRAPE_FULL_EP = 0
if SCRAPE_FULL_EP:
  full_episode = dict(epid='20020518', ntitles=14)
  full_episode_tids = [ full_episode['epid'] + str(i+1) for i in range(full_episode['ntitles']) ]

  dedupe_list = lambda lst: list(set(lst))
  all_tids = dedupe_list(all_tids + full_episode_tids)

@pytest.fixture(scope="module")
def basket():
  return crawl(all_tids)

def test_total_scrape_stats(basket):
  scraped_sids = {s['sid'] for s in basket.of_type(Season)}
  all_sids = set(map(helpers.Sid.from_tid, all_tids))
  assert 27 in all_sids
  assert set(all_sids) == set(scraped_sids)

  scraped_epids = {e['epid'] for e in basket.of_type(Episode)}
  all_epids = map(helpers.Epid.from_tid, all_tids)
  assert set(all_epids) == set(scraped_epids)

  scraped_tids = {t['tid'] for t in basket.of_type(Title)}
  assert scraped_tids == set(all_tids)

def test_season(basket):
  season = basket.get(Season, sid=27)
  assert season
  assert season == Season(sid=27, year=2001)

# Episode-level data
def test_episode_stuff(basket):
  # Season 27, ep 20
  epid = '20020518'
  ep = basket.get(Episode, epid=epid)
  assert_item_props(ep, epid=epid, epno=19, sid=27)

  # host
  host = basket.get(Host, epid=epid)
  assert host
  wino = basket.get(Actor, aid=host['aid'])
  assert wino['name'] == 'Winona Ryder'

# Basically just test a bunch of basics of scraped sketches.
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

  apps = basket.appearance_lookup(tid=tid)
  assert len(apps) == 4
  assert set(apps.keys()) == actor_names

  wino = apps['Winona Ryder']
  assert_item_props(wino, capacity='host', role='Clarissa', impid=None, charid=None, voice=False) 
  rd = apps['Rachel Dratch']
  assert_item_props(rd, capacity='cast', role='Virginia Klarvin', impid=None, charid=559)
  imp = basket.get(Character, name='Virginia Klarvin')
  assert imp
  assert imp['charid'] == 559
  jf = apps['Jimmy Fallon']
  assert_item_props(jf, capacity='cast', role='Dave', charid=570)

def assert_item_props(item, **kwargs):
  """Do the given key, values match the given Item? i.e. are they a subset of
  the Item's items (in the lowercase, dict sense)"""
  for k, v in kwargs.items():
    assert item.get(k) == v


# Test the id utils in the helpers module
def test_helpers():
  tid = '2002051810' # lovers
  date = helpers.Tid.to_date(tid)
  assert date == datetime.date(2002, 5, 18)
  sid = helpers.Sid.from_tid(tid)
  assert sid == 27
  epid = helpers.Epid.from_tid(tid)
  assert epid == '20020518'

# Test the case where the same actor appears in a sketch more than once.
def test_multiple_appearances(basket):
  tid = named_tids['botox']
  aid = basket.get(Actor, key='aid', name='Ana Gasteyer')
  apps = basket.get_matches(Appearance, by='role', tid=tid, aid=aid)
  assert len(apps) == 2
  assert set(apps.keys()) == {'announcer', 'user'}

  announcer = apps['announcer']
  assert announcer['voice']

def test_impression(basket):
  tid = named_tids['cold_open_obamacare']
  title = basket.get(Title, tid=tid)
  assert_item_props(title, tid=tid, name='Obamacare Website', category='Cold Opening',
      skid=None, order=0)
  impressed = 'Kathleen Sebelius'
  app = basket.get(Appearance, tid=tid, role=impressed)
  imp = basket.get(Impression, name=impressed)
  assert app['impid'] == imp['impid']

def test_cameo(basket):
  tid = named_tids['monologue_ed_norton']
  apps = basket.appearance_lookup(tid=tid)
  assert set(apps.keys()) == {'Edward Norton', 'Alec Baldwin', 'Miley Cyrus'}
  alec = apps['Alec Baldwin'] 
  assert_item_props(alec, capacity='cameo', role=None, impid=None, charid=None, voice=False)

def test_recurring_sketch(basket):
  tid = named_tids['jeopardy']
  title = basket.get(Title, tid=tid)
  skid = title['skid']
  sketch = basket.get(Sketch, skid=skid)
  assert title['name'] == sketch['name'] == 'Jeopardy!'
