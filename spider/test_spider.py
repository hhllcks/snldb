from collections import defaultdict

import scrapy
from scrapy.http import HtmlResponse

from betamax import Betamax

import pytest

from snl import Snl as SnlSpider

with Betamax.configure() as config:
  config.cassette_library_dir = 'cassettes'
  config.preserve_exact_body_bytes = True
  config.default_cassette_options['record_mode'] = 'new_episodes'

@pytest.mark.usefixtures('betamax_session')

def crawl_sketch(skid, sess, extras):
  if isinstance(extras, basestring):
    extras = [extras]
  url = 'http://www.snlarchives.net/Episodes/?{}'.format(skid)
  response = sess.get(url)
  req = scrapy.Request(url=url)
  scrapy_response = HtmlResponse(body=response.content, url=url, request=req)

  dummy_sketch = dict(tid=skid, titleType='Sketch')
  dummy_cast = {name: dict(aid=i, name=name) for i, name in enumerate(extras)}
  meta = scrapy_response.meta
  meta['title'] = dummy_sketch
  meta['extra_cast'] = dummy_cast
  spider = SnlSpider()
  return spider.parseTitle(scrapy_response)

def crawl2(tid, sess):
  spider = SnlSpider()
  epid_len = 4 + 2 + 2
  epid = tid[:epid_len]
  url = 'http://www.snlarchives.net/Episodes/?{}'.format(epid)
  response = sess.get(url)
  req = scrapy.Request(url=url)
  scrapy_response = HtmlResponse(body=response.content, url=url, request=req)
  return spider.parseEpisode(scrapy_response, tid)

def sort_entities(entities):
  res = defaultdict(list)
  for ent in entities:
    res[ent['type']].append(ent)
  return res

def test_butt_pregnancy(betamax_session):
  #gen = crawl_sketch('2005111211', betamax_session, 'Jason Lee')
  gen = crawl2('2005111211', betamax_session)
  bytype = sort_entities(gen)
  actors = bytype['actor']
  assert len(actors) == 7
  roles = bytype['actor_title']
  assert len(roles) == 8
  return
  sketch = gen.next()
  jason = gen.next()
  assert False, jason
  assert jason['name'] == 'Jason Lee'
  assert jason['aid'] == 0
  role = gen.next()
  assert role['role'] == 'husband'
  assert role['aid'] == 0
  assert role['impid'] is None
  # blah blah
