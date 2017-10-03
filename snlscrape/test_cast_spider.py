from scrapy.http import HtmlResponse
from betamax import Betamax
from betamax.fixtures.unittest import BetamaxTestCase

from spiders.cast import CastSpider

with Betamax.configure() as config:
  config.cassette_library_dir = 'cassettes'
  config.preserve_exact_body_bytes = True
  config.default_cassette_options['record_mode'] = 'new_episodes'

class TestCastScrape(BetamaxTestCase):

  def setUp(self):
    self.spider = CastSpider()
    super(TestCastScrape, self).setUp()

  def cast_response(self, tag):
    cast_url = 'http://www.snlarchives.net/Cast/?{}'.format(tag)
    re = self.session.get(cast_url)
    return HtmlResponse(body=re.content, url=cast_url)

  def parse_cast(self, aid):
    return list(self.spider.parseCastMember(self.cast_response(aid)))

  def test_jld(self):
    casts = self.parse_cast('JuLD')
    assert len(casts) == 3
    assert all(c['aid'] == 'Julia Louis-Dreyfus' for c in casts)
    assert [c['sid'] for c in casts] == [8, 9, 10]
    for k in ['featured', 'update_anchor', 'first_epid', 'last_epid']:
      assert not any(c.get(k) for c in casts)

  def test_featured(self):
    casts = self.parse_cast('KyMo')
    assert [c.get('featured', False) for c in casts] == [True, True, False, False]

  def test_midseason_start(self):
    # Abby Elliott
    casts = self.parse_cast('AbEl')
    assert casts[0]['first_epid'] == '20081115'

  def test_early_end(self):
    # Janeane Garofalo
    casts = self.parse_cast('JaGa')
    assert len(casts) == 1
    assert casts[0]['last_epid'] == '19950225'

  def test_update_anchor(self):
    # Michael Che
    casts = self.parse_cast('MiCh')
    assert all([c.get('update_anchor') for c in casts])
    assert [c.get('featured', False) for c in casts] == [True, True, False]

