import scrapy
from scrapy.http import HtmlResponse

from betamax import Betamax

import pytest

from snl import Snl as SnlSpider

with Betamax.configure() as config:
  config.cassette_library_dir = 'cassettes'
  config.preserve_exact_body_bytes = True

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

def test_butt_pregnancy(betamax_session):
  gen = crawl_sketch('2005111211', betamax_session, 'Jason Lee')
  jason = gen.next()
  assert jason['name'] == 'Jason Lee'
  assert jason['aid'] == 0
  role = gen.next()
  assert role['role'] == 'husband'
  assert role['aid'] == 0
  assert role['impid'] is None
  # blah blah
