import scrapy

from snlscrape import helpers
from snlscrape.items import Cast

class CastSpider(scrapy.Spider):
  name = 'castspider'
  start_urls = ['http://www.snlarchives.net/Cast/?FullList']

  def parse(self, response):
    """Parse the list of all cast members."""
    listdiv = response.css('div.contentFullList')
    for anchor in listdiv.css('a'):
      href = anchor.css('::attr(href)').extract_first()
      yield scrapy.Request(response.urljoin(href), callback=self.parseCastMember)

  def parseCastMember(self, response):
    aid = response.url.split('?')[1]
    name = response.css('div.contentWrapper .contentHD h1 ::text').extract_first()

    popup_idx = 0
    while 1:
      popup_idx += 1
      popup = response.css('#popup_{}'.format(popup_idx))
      if not popup:
        break
      
      cast = Cast(aid=aid)
      for i, p in enumerate(popup.css('p')):
        p_text = p.css('::text').extract_first()
        # First p should have season link
        if i == 0:
          href = p.css('a ::attr(href)').extract_first()
          if not href or not href.startswith('/Seasons'):
            # The first sequence of popup_ elements represent seasons, but there
            # are others that immediately follow with stuff like characters and
            # impressions. If we've reached one of those, we've fallen off the end.
            raise StopIteration
          year = int(href.split('?')[1])
          sid = helpers.Sid.from_year(year)
          assert 'sid' not in cast
          cast['sid'] = sid
        elif p_text.startswith('Featured Player'):
          cast['featured'] = True
        elif 'episode' in p_text:
          if p_text.startswith('First episode'):
            k = 'first_epid'
          elif p_text.startswith('Last episode'):
            k = 'last_epid'
          else:
            raise Exception('Unrecognized cast episode text: "{}"'.format(p_text))
          ep_href = p.css('a ::attr(href)').extract_first()
          epid = self.id_from_url(ep_href)
          cast[k] = epid
        elif p_text == 'Update':
          cast['update_anchor'] = True
        else:
          logging.warn("Don't know what to do with cast text: {}".format(p_text))
      yield cast

  @staticmethod
  def id_from_url(url):
    qmark_idx = url.rfind('?')
    return url[qmark_idx+1:]

