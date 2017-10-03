import scrapy
import string
import logging
import re

from collections import defaultdict
from lazy import lazy

from snlscrape import helpers
from snlscrape.items import *

# TODO:
# - this seems... hard to parse. Is this typical? http://www.snlarchives.net/Episodes/?200604158
#       - further complicated by the fact that (rarely) an actor can legitimately appear in multiple
#         roles in a single sketch. Example: http://www.snlarchives.net/Episodes/?2005111211
#         Chris Parnell has a role in the live sketch (Mr. Singer), but also did recorded voice work

# TODO: The 'full summary' tab in snlarchive episode pages has all the information that we're
# currently getting by scraping a page per sketch/segment. Using that could reduce the number
# of requests needed by an order of magnitude. However, those tabs seemingly don't have permalinks -
# the navigation is with js. So probably technically tricky.

# XXX: Y'know what, it actually looks like the content of all those tabs is present in the
# html on load. The js just deals with hiding/showing. So this shouldn't actually be that hard.

def removeTags(sXML):
  cleanr = re.compile('<.*?>')
  sText = re.sub(cleanr, '', sXML)
  return sText

class UnrecognizedActorException(Exception):
  def __init__(self, name, *args, **kwargs):
    super(UnrecognizedActorException, self).__init__(*args, **kwargs)
    self.name = name

class SnlSpider(scrapy.Spider):
  name = 'snlspider'
  start_urls = ['http://www.snlarchives.net/Seasons/']
  base_url = "http://www.snlarchives.net"
  base_url_imdb = "http://www.imdb.com/title/tt0072562/episodes?season="
  printable = set(string.printable)

  def _target_ids_from_settings(self, idtype):
    assert idtype in ('tid', 'epid', 'sid')
    id_attr = 'SNL_TARGET_{}'.format(idtype.upper())
    single_target = self.settings.get(id_attr)
    multi_attr = id_attr + 'S'
    multi_target = self.settings.getlist(multi_attr)
    assert not (single_target and multi_target)
    if single_target:
      return {single_target}
    elif multi_target:
      return set(multi_target)
    else:
      return set()

  # target_* properties: an empty value is intepreted as "everything"
  @property
  def target_tids(self):
    return self._target_ids_from_settings('tid')

  @lazy
  def target_epids(self):
    inherited = set([helpers.Epid.from_tid(tid) for tid in self.target_tids])
    return set.union(inherited, self._target_ids_from_settings('epid'))

  @lazy
  def target_sids(self):
    inherited = set([helpers.Sid.from_epid(epid) for epid in self.target_epids])
    return set.union(inherited, self._target_ids_from_settings('sid'))


  def interested(self, item):
    """Do we want to recurse on this item?"""
    if isinstance(item, Season):
      return not self.target_sids or item['sid'] in self.target_sids
    elif isinstance(item, Episode):
      return not self.target_epids or item['epid'] in self.target_epids
    elif isinstance(item, Title):
      return not self.target_tids or item['tid'] in self.target_tids
    else:
      assert False, "What're you doing passing this: {}".format(item)

  def parse_cast_entry_tr(self, row, extra_cast_lookup, tid):
    """Parse a row that describes a cast member in a particular segment, and their role."""
    cells = row.css('td')
    actor_cell = cells[0]
    actor_class = actor_cell.css('::attr(class)').extract_first()
    actor_link = actor_cell.css('a')
    # What's the context of this actor's appearance? Default is that they're appearing
    # as a cast member, but could also be host, cameo, etc.
    capacity = 'cast'
    actor_name = actor_cell.css('::text').extract_first().strip()
    if actor_name == 'Jack Handey':
      # This is a weird special case. Jack Handey appears in a bunch of 'Deep Thoughts'
      # segments in the 90's, e.g.: http://www.snlarchives.net/Episodes/?1991032313
      # And he is seemingly the only person to appear in a sketch who has no page 
      # on snlarchive - not as cast, crew, or guest. He isn't listed as a cast member
      # for any of the seasons on which his Deep Thoughts appear, nor is he listed as
      # a 'special guest' or 'cameo' on the corresponding episode pages. Anyways,
      # we'll give him a made-up aid and give him the 'crew' capacity (because wikipedia
      # says he was credited as an snl writer).
      actor = Actor(aid='special_JaHa', name=actor_name, type='crew')
    elif not actor_link:
      # Actor name is not linkified. This means they're not cast members. They could
      # be the host, cameos, or musical guest (though this code path currently isn't
      # reached for musical titles). The td class gives a hint.
      if not actor_class:
        logging.warn("No class found in actor cell {}".format(actor_cell))
      else:
        capacity = actor_class
      try:
        actor = extra_cast_lookup[actor_name]
      except KeyError:
        raise UnrecognizedActorException(name=actor_name)
    else:
      actor = self.actor_from_link(actor_link)

    app = Appearance(aid=actor['aid'], tid=tid, capacity=capacity)
    if len(cells) == 3:
      _dots, role_td = cells[1:]
      app = self.parse_role_cell(role_td, app)
    else:
      assert len(cells) == 1

    return actor, app

  def parse_role_cell(self, role_td, appearance):
    rolenames = role_td.css('::text').extract()
    rolename = rolenames[0].strip()
    if len(rolenames) > 1:
      if rolenames[1].strip() == '(voice)':
        appearance['voice'] = True
      else:
        logging.warn('Unrecognized role part: {} in role td {}'.format(rolenames[1], role_td))
      if len(rolenames) > 2:
        logging.warn('Unexpectedly large number of elements in role td: {}'.format(rolenames))
    appearance['role'] = rolename
    role_link = role_td.css('a')
    if role_link:
      href = role_link.css('::attr(href)').extract_first()
      id = int(self.id_from_url(href))
      if href.startswith('/Impressions/'):
        appearance['impid'] = id
      elif href.startswith('/Characters/'):
        appearance['charid'] = id
      else:
        raise Exception('Unrecognized role URL: {}'.format(href))
    return appearance

  def parse(self, response):
    """Parse the entry page - the listing of all seasons."""
    snl = {}
    # parsing snlarchives. Entrypoint is the seasons page at www.snlarchives.net/Seasons/
    for season in response.css('div.thumbRectInner'):
      sid = int(season.css('::text').extract_first())
      year = 1974 + sid
      next_page = '?{}'.format(year)

      item_season = Season(sid=sid, year=year)
      if not self.interested(item_season):
        continue
      yield item_season
    
      if self.settings.getbool('SNL_SCRAPE_IMDB'):
        imdb_season_url = self.base_url_imdb + str(item_season['sid'])
        yield scrapy.Request(imdb_season_url, callback=self.parseRatingsSeason, 
            meta=dict(season=item_season))

      yield scrapy.Request(response.urljoin(next_page), callback=self.parseSeason, meta={'season': item_season})


  def parseSeason(self, response):
    # parsing a season (e.g. www.snlarchives.net/Seasons/?1975)
    # episodes is already chosen
    item_season = response.meta['season']

    for episode in response.css('a'):
      href_url = episode.css("a ::attr(href)").extract_first()
      if href_url.startswith("/Episodes/?") and len(href_url) == 19:
        episode_url = self.base_url + href_url
        dummy_ep = Episode(epid=self.id_from_url(episode_url))
        if not self.interested(dummy_ep):
          if dummy_ep['epid'] == '20051112':
            self.logger.warning('Butt ep not interesting.')
          elif dummy_ep['epid'] == '20020518':
            self.logger.warning('Lovers ep not interesting')
          continue
        yield scrapy.Request(episode_url, callback=self.parseEpisode, meta={'season': item_season})

  def parseRatingsSeason(self, response):
    # parsing the ratings of the episodes of a season
    item_season = response.meta['season']
    eid = 0
    for episode in response.css(".eplist > .list_item > .image > a"):
      item_rating = EpisodeRating(epno=eid, sid=item_season['sid'])
      eid +=1
      href_url = episode.css("a ::attr(href)").extract_first()
      url_split = href_url.split("?")
      href_url = "http://www.imdb.com" + url_split[0] + "ratings"
      yield scrapy.Request(href_url, callback=self.parseRatingsEpisode, meta={'rating': item_rating})
  
  def parseRatingsEpisode(self, response): 
    item_rating = response.meta['rating']
    tables = response.css("table[cellpadding='0']")
    
    # 1st table is vote distribution on rating
    # 2nd table is vote distribution on age and gender
    ratingTable = tables[0]
    ageGenderTable = tables[1]

    trCount = 0
    # histogram of ratings from 1-10
    score_counts = {}
    for tableTr in ratingTable.css("tr"):
      if trCount > 0:
        score = 11 - trCount
        count = int(removeTags(tableTr.css("td")[0].extract()))
        score_counts[score] = count
      trCount += 1
    item_rating['score_counts'] = score_counts
    
    trCount = 0
    # Map from named demographic groups to avg scores, and counts
    demo_avgs = {}
    demo_counts = {}
    for tableTr in ageGenderTable.css("tr"):
      if trCount > 0:
        tableTd = tableTr.css("td").extract()
        if len(tableTd) > 1:
          sKey = removeTags(tableTd[0]).lstrip().rstrip()
          sValue = int(removeTags("".join(filter(lambda x: x in self.printable, tableTd[1]))))
          sValueAvg = float(removeTags("".join(filter(lambda x: x in self.printable, tableTd[2]))))
          demo_counts[sKey] = sValue
          demo_avgs[sKey] = sValueAvg
      trCount+=1
    item_rating['demographic_averages'] = demo_avgs
    item_rating['demographic_counts'] = demo_counts
    yield item_rating

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
    return Actor(
        aid=prefix+id,
        name=name,
        type=atype,
        )

  @staticmethod
  def id_from_url(url):
    qmark_idx = url.rfind('?')
    return url[qmark_idx+1:]

  def parseEpisode(self, response, target_tid=None):
    item_season = response.meta['season']
    sid = item_season['sid']

    epid = self.id_from_url(response.url)
    episode = Episode(sid=sid, epid=epid)

    hosts = []
    # NB: I don't think there's any reason to distinguish between the below lists (they just get lumped together at the end)
    cameos = []
    musical_guests = []
    filmed_cameos = []
    actor_fieldname_to_list = {'Host:': hosts, 'Hosts:': hosts,
        'Cameo:': cameos, 'Cameos:': cameos,
        'Special Guest:': cameos, 'Special Guests:': cameos,
        'Musical Guest:': musical_guests, 'Musical Guests:': musical_guests,
        'Filmed Cameo:': filmed_cameos, 'Filmed Cameos:': filmed_cameos,
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
        try:
          episode['epno'] = int(epstr.split(' ')[0][1:]) - 1
        except ValueError:
          logging.warn("Couldn't parse epno from values = {}. (Was this a special?)".format(
            values, response.url))
          return
      elif field in actor_fieldname_to_list:
        dest = actor_fieldname_to_list[field]
        for actor_ele in valueTd.css('a'):
          actor = self.actor_from_link(actor_ele)
          dest.append(actor)

    extra_actors = hosts + cameos + musical_guests + filmed_cameos
    extra_lookup = {a['name']: a for a in extra_actors}

    yield episode

    assert len(hosts) > 0
    for host_actor in hosts:
      yield Host(epid=epid, aid=host_actor['aid'])
    # initially the titles tab is opened
    order = -1 # Record the relative order of sketches
    for sketchInfo in response.css("div.sketchWrapper"):
      order += 1
      sketch = Title(epid=epid)
      # e.g. /Episodes/?197510111
      href_url = sketchInfo.css("a ::attr(href)").extract_first()
      # TODO: almost all of this metadata (everything except order, which is kind
      # of inferrable from the url anyways), is accessible from the sketch page.
      # Scraping it there (and therefore in the parseTitle method) would make for
      # a much cleaner separation of concerns.
      sketch['tid'] = href_url.split('?')[1]
      if not self.interested(sketch):
        continue
      sketch['name'] = sketchInfo.css(".title ::text").extract_first()
      sketch['category'] = sketchInfo.css(".type ::text").extract_first()
      sketch['order'] = order

      title_url = sketchInfo.css(".title a ::attr(href)").extract_first()
      if title_url:
        if title_url.startswith('/Sketches/'):
          skid = self.id_from_url(title_url)
          sketch['skid'] = skid 
          rec_sketch = Sketch(skid=skid, name=sketch['name'])
          yield rec_sketch
        elif title_url.startswith('/Commercials/'):
          # meh
          pass
        else:
          logging.warn('Unrecognized title url format: {}'.format(title_url))

      sketch_url = self.base_url + href_url
      if not self.interested(sketch):
        continue
      yield scrapy.Request(sketch_url, callback=self.parseTitle, 
            meta={'title': sketch, 'episode': episode, 'extra_cast': extra_lookup},
          )

  def parseTitle(self, response):
    sketch = response.meta['title']
    extra_cast = response.meta['extra_cast']
    if sketch['category'] in ('Musical Performance', 
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
        logging.warn('Skipping unparseable row in sketch {}:\n{}\n{} not among extra_cast = {}'.format(
          response.url, cast_entry, e.name, extra_cast))
        continue
      yield actor
      
      aid = actor['aid']
      # Since Character and Impression entities are derivable from the corresponding
      # Appearance entities, I was hoping to put the logic for generating them in a 
      # pipeline, but scrapy pipelines can't yield multiple items :(
      # https://github.com/scrapy/scrapy/issues/1915
      impid, charid = actor_title.get('impid'), actor_title.get('charid')
      if impid:
        yield Impression(impid=impid, aid=aid, name=actor_title['role'])
      if charid:
        yield Character(charid=charid, aid=aid, name=actor_title['role'])

      if aid not in aids_this_title:
        yield actor_title
        aids_this_title[aid] = actor_title
      else:
        prev = aids_this_title[aid]
        # if both roles have a name, and those names are distinct, then maybe they
        # did legit appear in the same sketch twice in two different roles/capacities.
        # can happen rarely.
        a_role, b_role = actor_title.get('role'), prev.get('role')
        if a_role and b_role and (a_role != b_role):
          yield actor_title
        else:
          logging.warn('Actor {} appeared multiple times in sketch at {}, and one role was empty, or both were the same.'.format(
            actor['name'], response.url))
          # Y'know what, just yield it anyways for now.
          yield actor_title
        # (God help us if actors appear more than twice in the same sketch...)

    yield sketch
