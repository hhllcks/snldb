import scrapy
import re
import string
import logging

from collections import defaultdict

# TODO:
# - rename 'type' to 'entityType' for clarity?
# - also, rename those types (i.e. the table names) for clarity and formatting consistency
# - this seems... hard to parse. Is this typical? http://www.snlarchives.net/Episodes/?200604158
#       - further complicated by the fact that (rarely) an actor can legitimately appear in multiple
#         roles in a single sketch. Example: http://www.snlarchives.net/Episodes/?2005111211
#         Chris Parnell has a role in the live sketch (Mr. Singer), but also did recorded voice work

def removeTags(sXML):
  cleanr = re.compile('<.*?>')
  sText = re.sub(cleanr, '', sXML)
  return sText

class UnrecognizedActorException(Exception):
  pass

class Snl(scrapy.Spider):
  name = 'snl'
  start_urls = ['http://www.snlarchives.net/Seasons/']
  base_url = "http://www.snlarchives.net"
  base_url_imdb = "http://www.imdb.com/title/tt0072562/episodes?season="

  # TODO: will need to do something similar to avoid dupes for...
  #     sketches, impressions, characters
  # Contains aids
  actor_seen = set()
  seen_charids = set()
  seen_impids = set()
  cleanr = re.compile('<.*?>')
  printable = set(string.printable)

  custom_settings = dict(
      CONCURRENT_REQUESTS_PER_DOMAIN=1,
      DOWNLOAD_DELAY=1.5,
  )

  def __init__(self, season_limit=None, ep_limit=None, title_limit=None, mini=False, 
                episode=None,
                scrape_ratings=False, *args, **kwargs):
    super(Snl, self).__init__(*args, **kwargs)
    self.season_limit = float('inf') if season_limit is None else int(season_limit)
    self.ep_limit = float('inf') if ep_limit is None else int(ep_limit)
    self.title_limit = float('inf') if title_limit is None else int(title_limit)
    if mini:
      self.season_limit = self.ep_limit = self.title_limit = 1
    self.scraped = defaultdict(int)
    self.scrape_ratings = scrape_ratings
    if episode is not None:
      ep_url = self.base_url + '/Episodes/?' + str(episode)
      self.start_urls = [ep_url]

  def start_requests(self):
    url = self.start_urls[0]
    yield scrapy.Request(url, 
        callback = self.parseEpisode if 'Episodes' in url else self.parse
        )

  @classmethod
  def removeTags(cls, sXML):
    sText = re.sub(cls.cleanr, '', sXML)
    return sText

  def parse_role_cell(self, role_td, actor_title):
    rolename = role_td.css('::text').extract_first()
    voice_suffix = ' (voice)'
    if rolename.endswith(voice_suffix):
      rolename = rolename[:-len(voice_suffix)]
      actor_title['voice'] = True
    actor_title['role'] = rolename
    role_link = role_td.css('a')
    if role_link:
      href = role_link.css('::attr(href)').extract_first()
      id = int(self.id_from_url(href))
      if href.startswith('/Impressions/'):
        actor_title['impid'] = id
      elif href.startswith('/Characters/'):
        actor_title['charid'] = id
      else:
        raise Exception('Unrecognized role URL: {}'.format(href))
    return actor_title

  def parse_cast_entry_tr(self, row, extra_cast_lookup, tid):
    cells = row.css('td')
    actor_cell = cells[0]
    actor_class = actor_cell.css('::attr(class)').extract_first()
    actor_link = actor_cell.css('a')
    # What's the context of this actor's appearance? Default is that they're appearing
    # as a cast member, but could also be host, cameo, etc.
    capacity = 'cast'
    if not actor_link:
      # Actor name is not linkified. This means they're not cast members. They could
      # be the host, cameos, or musical guest (though this code path currently isn't
      # reached for musical titles). The td class gives a hint.
      actor_name = actor_cell.css('::text').extract_first()
      assert actor_class, "No class found in actor cell {}".format(actor_cell)
      if actor_class not in ('host', 'cameo'):
        logging.warn('Unrecognized actor class {}'.format(actor_class))
      capacity = actor_class
      try:
        actor = extra_cast_lookup[actor_name]
      except KeyError:
        raise UnrecognizedActorException
    else:
      actor = self.actor_from_link(actor_link)

    actor_title = dict(type='actor_title', aid=actor['aid'], tid=tid,
        role=None, impid=None, charid=None, capacity=capacity, voice=False)
    if len(cells) == 3:
      _dots, role_td = cells[1:]
      actor_title = self.parse_role_cell(role_td, actor_title)
    else:
      assert len(cells) == 1

    return actor, actor_title

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
        type='actor',
        )

  @staticmethod
  def id_from_url(url):
    qmark_idx = url.rfind('?')
    return url[qmark_idx+1:]

  def parseEpisode(self, response, target_tid=None):
    # XXX. Hack for the single episode flag.
    if 'season' in response.meta:
      item_season = response.meta['season']
      sid = item_season['sid']
    else:
      sid = -1

    episode = {}
    episode['sid'] = sid
    episode['type'] = 'episode'

    hosts = []
    cameos = []
    musical_guests = []
    actor_fieldname_to_list = {'Host:': hosts, 'Hosts:': hosts,
        'Cameo:': cameos, 'Cameos:': cameos,
        'Musical Guest:': musical_guests, 'Musical Guests:': musical_guests,
        }
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
      elif field in actor_fieldname_to_list:
        dest = actor_fieldname_to_list[field]
        for actor_ele in valueTd.css('a'):
          actor = self.actor_from_link(actor_ele)
          dest.append(actor)

    extra_actors = hosts + cameos + musical_guests
    extra_lookup = {a['name']: a for a in extra_actors}

    yield episode
    assert len(hosts) > 0
    for host_actor in hosts:
      yield dict(type='host', eid=episode['eid'], aid=host_actor['aid'])
    # initially the titles tab is opened
    order = 0 # Record the relative order of sketches
    for sketchInfo in response.css("div.sketchWrapper"):
      order += 1
      sketch = {}
      # e.g. /Episodes/?197510111
      href_url = sketchInfo.css("a ::attr(href)").extract_first()
      # TODO: almost all of this metadata (everything except order, which is kind
      # of inferrable from the url anyways), is accessible from the sketch page.
      # Scraping it there (and therefore in the parseTitle method) would make for
      # a much cleaner separation of concerns.
      sketch['sid'] = sid
      sketch['eid'] = episode['eid']
      sketch['tid'] = int(href_url.split('?')[1])
      sketch['title'] = sketchInfo.css(".title ::text").extract_first()
      sketch['type'] = 'title'
      sketch['titleType'] = sketchInfo.css(".type ::text").extract_first()
      sketch['order'] = order
      sketch['skid'] = None

      title_url = sketchInfo.css(".title a ::attr(href)")
      if title_url:
        if title_url.startswith('/Sketches/'):
          # Could yield sketch entities here, but maybe just makes more sense
          # to build that table as a postprocessing step?
          sketch['skid'] = self.id_from_url(title_url)
        elif title_url.startswith('/Commercials/'):
          # meh
          pass
        else:
          logging.warn('Unrecognized title url format: {}'.format(title_url))

      if sketch['title'] is None:
        sketch['title'] = ""

      sketch_url = self.base_url + href_url
      yield scrapy.Request(sketch_url, callback=self.parseTitle, 
            meta={'title': sketch, 'episode': episode, 'extra_cast': extra_lookup},
          )
      self.scraped['titles'] += 1
      if self.scraped['titles'] >= self.title_limit:
        break

  def parseTitle(self, response):
    sketch = response.meta['title']
    extra_cast = response.meta['extra_cast']
    if sketch['titleType'] in ('Musical Performance', 
      'Guest Performance',
      ):
      # Nothing to do here. There are no roles, no 'ActorTitle' rows to add,
      # no impressions or characters. (Probably)
      yield sketch
      raise StopIteration
    # I guess this is to avoid counting the same performer twice in one sketch.
    aids_this_title = {}
    for cast_entry in response.css(".roleTable > tr"):
      try:
        actor, actor_title = self.parse_cast_entry_tr(cast_entry, extra_cast,
            sketch['tid'])
      except UnrecognizedActorException as e:
        logging.warn('Skipping unparseable row in sketch {}:\n{}'.format(
          response.url, cast_entry))
        continue
      aid, impid, charid = actor['aid'], actor_title['impid'], actor_title['charid']
      if impid and impid not in self.seen_impids:
        yield dict(type='impression', impid=impid, aid=aid, name=actor_title['role'])
        self.seen_impids.add(impid)
      if charid and charid not in self.seen_charids:
        yield dict(type='character', charid=charid, aid=aid, name=actor_title['role'])
        self.seen_charids.add(charid)
      if aid not in self.actor_seen:
        yield actor
        self.actor_seen.add(aid)

      if aid not in aids_this_title:
        yield actor_title
        aids_this_title[aid] = actor_title
      else:
        logging.warn('Actor {} appeared multiple times in sketch at {}'.format(
          actor['name'], response.url))
        prev = aids_This_title[aid]
        # if both roles have a name, and those names are distinct, then maybe they
        # did legit appear in the same sketch twice in two different roles/capacities.
        # can happen rarely.
        if prev['role'] and actor_title['role'] and prev['role'] != actor_title['role']:
          yield actor_title
        # (God help us if actors appear more than twice in the same sketch...)

      # NB: the td class might be a useful hint for some failure cases
    yield sketch
