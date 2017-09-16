import scrapy
import re
import string


def removeTags(sXML):
  cleanr = re.compile('<.*?>')
  sText = re.sub(cleanr, '', sXML)
  return sText


class snl(scrapy.Spider):
  name = 'snl'
  start_urls = ['http://www.snlarchives.net/Seasons/']
  base_url = "http://www.snlarchives.net"
  base_url_imdb = "http://www.imdb.com/title/tt0072562/episodes?season="

  actor_seen = set()
  cleanr = re.compile('<.*?>')
  printable = set(string.printable)

  def removeTags(self, sXML):
    sText = re.sub(self.cleanr, '', sXML)
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

      yield scrapy.Request(response.urljoin(next_page), callback=self.parseSeason, meta={'season': item_season})

      # at this point we branch out to get the ratings from imdb.com
      # the root URL for SNL is http://www.imdb.com/title/tt0072562
      # we can find the episodes at http://www.imdb.com/title/tt0072562/episodes
      # an we can select a certain episode like this http://www.imdb.com/title/tt0072562/episodes?season=1
      yield scrapy.Request(self.base_url_imdb + str(sid), callback=self.parseRatingsSeason, meta={'season': item_season})

      # remove statement to scrape more than one season
      # break

  def parseRatingsSeason(self, response):
    # parsing the ratings of the episodes of a season
    item_season = response.meta['season']
    eid = 0
    for episode in response.css(".eplist > .list_item > .image > a"):
      item_rating = {}
      eid += 1
      item_rating["type"] = "rating"
      item_rating["eid"] = eid
      item_rating["sid"] = item_season["sid"]
      href_url = episode.css("a ::attr(href)").extract_first()
      url_split = href_url.split("?")
      href_url = "http://www.imdb.com" + url_split[0] + "ratings"
      yield scrapy.Request(href_url, callback=self.parseRatingsEpisode, meta={'season': item_season, 'rating': item_rating})

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
        # remove statement to scrape more than one episode
        # break

  def parseEpisode(self, response):
    item_season = response.meta['season']

    episode = {}
    episode['sid'] = item_season['sid']
    episode['year'] = item_season['year']
    episode['type'] = 'episode'

    for epInfoTr in response.css("table.epGuests tr"):
      epInfoTd = epInfoTr.css("td")
      if epInfoTd[0].css("td p ::text").extract_first() == 'Aired:':
        airedInfo = epInfoTd[1].css("td p ::text").extract()
        episode['aired'] = airedInfo[0][:-2]
        episode['eid'] = int(airedInfo[2].split(' ')[0][1:])
      if epInfoTd[0].css("td p ::text").extract_first() == 'Host:':
        host = epInfoTd[1].css("td p ::text").extract()
        episode['host'] = host[0]
      if epInfoTd[0].css("td p ::text").extract_first() == 'Hosts:':
        host = epInfoTd[1].css("td p ::text").extract()
        episode['host'] = host

    yield episode
    # initially the titles tab is opened
    for sketchInfo in response.css("div.sketchWrapper"):
      sketch = {}
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
      yield scrapy.Request(sketch_url, callback=self.parseTitle, meta={'title': sketch, 'episode': episode})
      # remove statement to scrape more than one sketch
      # break

  def parseTitle(self, response):
    sketch = response.meta['title']
    episode = response.meta['episode']
    actor_seen_title = set()
    for actor in response.css(".roleTable > tr"):
      actor_dict = {}
      actor_sketch = {}
      actor_dict['name'] = actor.css("td ::text").extract_first()
      if actor_dict['name'] == ' ... ':
        actor_dict['name'] = episode['host']
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
