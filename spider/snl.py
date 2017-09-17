import scrapy
import re
import string

from collections import defaultdict

# TODO:
# - rename 'type' to 'entityType' for clarity?

def removeTags(sXML):
  cleanr = re.compile('<.*?>')
  sText = re.sub(cleanr, '', sXML)
  return sText


class Snl(scrapy.Spider):
  name = 'snl'
  start_urls = ['http://www.snlarchives.net/Seasons/']
  base_url = "http://www.snlarchives.net"
  base_url_imdb = "http://www.imdb.com/title/tt0072562/episodes?season="

  # TODO: will need to do something similar to avoid dupes for...
  #     sketches, impressions, characters
  # Contains aids
  actor_seen = set()
  cleanr = re.compile('<.*?>')
  printable = set(string.printable)

  custom_settings = dict(
      CONCURRENT_REQUESTS_PER_DOMAIN=1,
      DOWNLOAD_DELAY=.5,
  )

  def __init__(self, season_limit=None, ep_limit=None, title_limit=None, mini=False, 
                scrape_ratings=False, *args, **kwargs):
    super(Snl, self).__init__(*args, **kwargs)
    self.season_limit = float('inf') if season_limit is None else int(season_limit)
    self.ep_limit = float('inf') if ep_limit is None else int(ep_limit)
    self.title_limit = float('inf') if title_limit is None else int(title_limit)
    if mini:
      self.season_limit = self.ep_limit = self.title_limit = 1
    self.scraped = defaultdict(int)
    self.scrape_ratings = scrape_ratings

  @classmethod
  def removeTags(cls, sXML):
    sText = re.sub(cls.cleanr, '', sXML)
    return sText

  def parse(self, response):
    snl = {}
    # parsing snlarchives. Entrypoint is the seasons page at www.snlarchives.net/Seasons/
    for season in response.css('div.thumbRectInner'):
      sid = int(season.css('::text').extract_first())
      year = 1974 + sid
      next_page = '?{}'.format(year)

      item_season = {}
      item_season['sid'] = int(sid)
      item_season['year'] = int(year)
      item_season['type'] = 'season'

      yield item_season
      self.scraped['seasons'] += 1

      yield scrapy.Request(response.urljoin(next_page), callback=self.parseSeason, meta={'season': item_season})

      # at this point we branch out to get the ratings from imdb.com
      # the root URL for SNL is http://www.imdb.com/title/tt0072562
      # we can find the episodes at http://www.imdb.com/title/tt0072562/episodes
      # an we can select a certain episode like this http://www.imdb.com/title/tt0072562/episodes?season=1
      if self.scrape_ratings:
        yield scrapy.Request(self.base_url_imdb + str(sid), callback=self.parseRatingsSeason, meta={'season': item_season})

      if self.scraped['seasons'] >= self.season_limit:
        break

  def parseRatingsSeason(self, response):
    # parsing the ratings of the episodes of a season
    item_season = response.meta['season']
    epno = 0
    for episode in response.css(".eplist > .list_item > .image > a"):
      item_rating = {}
      epno += 1
      item_rating["type"] = "rating"
      item_rating["epno"] = epno
      item_rating["sid"] = item_season["sid"]
      href_url = episode.css("a ::attr(href)").extract_first()
      url_split = href_url.split("?")
      href_url = "http://www.imdb.com" + url_split[0] + "ratings"
      yield scrapy.Request(href_url, callback=self.parseRatingsEpisode, meta={'season': item_season, 'rating': item_rating})
      if self.mini:
        break

  def parseRatingsEpisode(self, response):
    item_season = response.meta['season']
    item_rating = response.meta['rating']
    tables = response.css("table[cellpadding='0']")

    # 1st table is vote distribution on rating
    # 2nd table is vote distribution on age and gender
    ratingTable = tables[0]
    ageGenderTable = tables[1]

    trCount = 0
    for tableTr in ratingTable.css("tr"):
      if trCount > 0:
        sRating = str(11 - trCount)
        item_rating[sRating] = int(removeTags(tableTr.css("td")[0].extract()))
      trCount += 1

    trCount = 0
    for tableTr in ageGenderTable.css("tr"):
      if trCount > 0:
        tableTd = tableTr.css("td").extract()
        if len(tableTd) > 1:
          sKey = removeTags(tableTd[0]).lstrip().rstrip()
          sValue = int(removeTags(
              "".join(filter(lambda x: x in self.printable, tableTd[1]))))
          sValueAvg = float(removeTags(
              "".join(filter(lambda x: x in self.printable, tableTd[2]))))
          item_rating[sKey] = sValue
          item_rating[sKey + "_avg"] = sValueAvg
      trCount += 1
    yield item_rating

  def parseSeason(self, response):
    # parsing a season (e.g. www.snlarchives.net/Seasons/?1975)
    # episodes is already chosen
    item_season = response.meta['season']

    for episode in response.css('a'):
      href_url = episode.css("a ::attr(href)").extract_first()
      if href_url.startswith("/Episodes/?") and len(href_url) == 19:
        episode_url = self.base_url + href_url
        yield scrapy.Request(episode_url, callback=self.parseEpisode, meta={'season': item_season})
        self.scraped['episodes'] += 1
        if self.scraped['episodes'] >= self.ep_limit:
          break

  @classmethod
  def actor_from_link(self, anchor):
    href = anchor.css('::attr(href)').extract_first()
    qmark_idx = href.rfind('?')
    id = href[qmark_idx+1:]
    if href.startswith('/Guests/'):
      prefix = 'g_'
      atype = 'guest'
    elif href.startswith('/Cast/'):
      prefix = 'c_'
      atype = 'cast'
    elif href.startswith('/Crew/'):
      prefix = 'cr_'
      atype = 'crew'
    name = anchor.css('::text').extract_first()
    return dict(
        aid=prefix+id,
        name=name,
        actorType=atype,
        )

  def parseEpisode(self, response):
    item_season = response.meta['season']

    episode = {}
    episode['sid'] = item_season['sid']
    episode['type'] = 'episode'

    hosts = []
    # Parse table with basic episode metadata (date, host, musical guest, cameos...)
    # TODO: Some fields not currently parsed (musical guest, cameo, filmed cameos), which
    # may be worth parsing.
    for epInfoTr in response.css("table.epGuests tr"):
      epInfoTd = epInfoTr.css("td")
      fieldTd, valueTd = epInfoTd # e.g. ("<td><p>Host:</p></td>", "<td><p>Anna Faris</p></td>")
      field = fieldTd.css("td p ::text").extract_first()
      values = valueTd.css("td p ::text").extract()
      if field == 'Aired:':
        # e.g. "October 4, 2014 (", "<a href="/Seasons/?2014">S40</a>", "E2 / #768)"
        datestr, seasonlink, epstr = values
        episode['aired'] = datestr[:-2]
        # TODO: Maybe should use whatever string snlarchive uses in the url
        # (which I think is just a munged date)
        # That's what we do for tids for sketches (which, incidentally, also seem to be munged
        # dates, just with an ordinal tacked on)
        episode['eid'] = int(epstr.split(' ')[2].strip('#) \n\t'))
        try:
          episode['epno'] = int(epstr.split(' ')[0][1:])
        except ValueError:
          raise Exception("Couldn't parse epno from values = {}. (Was this a special?)".format(
            values, response.url))
          episode['epno'] = None
      elif field in ('Host:', 'Hosts:'):
        for host_ele in valueTd.css('a'):
          actor = self.actor_from_link(host_ele)
          hosts.append(actor)

    yield episode
    assert len(hosts) > 0
    for host_actor in hosts:
      yield dict(type='host', eid=episode['eid'], aid=host_actor['aid'])
    # initially the titles tab is opened
    for sketchInfo in response.css("div.sketchWrapper"):
      sketch = {}
      # e.g. /Episodes/?197510111
      href_url = sketchInfo.css("a ::attr(href)").extract_first()
      sketch['sid'] = item_season['sid']
      sketch['eid'] = episode['eid']
      sketch['tid'] = int(href_url.split('?')[1])
      sketch['title'] = sketchInfo.css(".title ::text").extract_first()
      sketch['type'] = 'title'
      sketch['titleType'] = sketchInfo.css(".type ::text").extract_first()
      if sketch['title'] == None:
        sketch['title'] = ""

      sketch_url = self.base_url + href_url
      yield scrapy.Request(sketch_url, callback=self.parseTitle, 
            meta={'title': sketch, 'episode': episode, 'host': hosts[0]['name']} # XXX
          )
      self.scraped['titles'] += 1
      if self.scraped['titles'] >= self.title_limit:
        break

  def parseTitle(self, response):
    sketch = response.meta['title']
    episode = response.meta['episode']
    actor_seen_title = set()
    for actor in response.css(".roleTable > tr"):
      actor_dict = {}
      actor_sketch = {}
      actor_dict['name'] = actor.css("td ::text").extract_first()
      if actor_dict['name'] == ' ... ':
        # TODO: ????
        actor_dict['name'] = response.meta['host']
      if actor_dict['name'] != None:
        actor_dict['type'] = 'actor'
        href_url = actor.css("td > a ::attr(href)").extract_first()
        if href_url != None:
          if href_url.split('?')[0] == '/Cast/':
            actor_dict['aid'] = href_url.split('?')[1]
            actor_dict['isCast'] = 1
            actor_sketch['actorType'] = 'cast'
          elif href_url.split('?')[0] == '/Crew/':
            actor_dict['aid'] = href_url.split('?')[1]
            actor_dict['isCast'] = 0
            actor_sketch['actorType'] = 'crew'
          else:
            raise Exception("Couldn't handle actor url {} on title page {}".format(
              href_url, response.url))

        else:
          actor_dict['aid'] = actor_dict['name']
          actor_dict['isCast'] = 0
          actor_sketch['actorType'] = actor.css(
              "td ::attr(class)").extract_first()
          if actor_sketch['actorType'] == None:
            actor_sketch['actorType'] = "unknown"

        if not actor_dict['aid'] in self.actor_seen:
          self.actor_seen.add(actor_dict['aid'])
          yield actor_dict

        actor_sketch['tid'] = sketch['tid']
        actor_sketch['sid'] = sketch['sid']
        actor_sketch['eid'] = sketch['eid']
        actor_sketch['aid'] = actor_dict['aid']
        actor_sketch['type'] = 'actor_sketch'

        if not actor_sketch['aid'] in actor_seen_title:
          actor_seen_title.add(actor_sketch['aid'])
          yield actor_sketch
    yield sketch
