import scrapy
import string
import logging
import re

from collections import defaultdict
from lazy import lazy

from snlscrape import helpers
from snlscrape.items import *

def removeTags(sXML):
  cleanr = re.compile('<.*?>')
  sText = re.sub(cleanr, '', sXML)
  return sText

class EmptyCastRowException(Exception):
  """Raised when a row in a table that's supposed to contain the cast of a sketch
  is actually mysteriously empty, as in the second row here:
  http://www.snlarchives.net/Episodes/?197802182
  """
  pass

class SnlSpider(scrapy.Spider):
  name = 'snlspider'
  start_urls = ['http://www.snlarchives.net/Seasons/']
  base_url = "http://www.snlarchives.net"
  base_url_imdb = "http://www.imdb.com/title/tt0072562/episodes?season="
  printable = set(string.printable)

  def _target_ids_from_settings(self, idtype):
    """Given a kind of id (tid, epid, sid), return the set of those ids we're
    targetting for this scrape. (either because they're explicitly given in the 
    corresponding settings variable, or because they're implied by a different 
    selection. e.g. if we're targetting tid 200604151, that entails also scraping
    the episode in which that title appears, epid 20060415.

    In the normal case where we're crawling all titles/episodes/seasons we can get
    our hands on, return an empty set.
    """
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
    """Should we yield this item and recurse on it (i.e. continue to the
    episodes in this season, or the titles in this episode)?"""
    if isinstance(item, Season):
      return not self.target_sids or item['sid'] in self.target_sids
    elif isinstance(item, Episode):
      return not self.target_epids or item['epid'] in self.target_epids
    elif isinstance(item, Title):
      return not self.target_tids or item['tid'] in self.target_tids
    else:
      assert False, "What're you doing passing this: {}".format(item)

  def parse(self, response):
    """Parse the entry page - the listing of all seasons."""
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

  def parseRatingsSeason(self, response):
    """From the IMDB page for a particular SNL season, crawl the user ratings for
    all episodes in that season.
    Example url: http://www.imdb.com/title/tt0072562/episodes?season=42
    """
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
    """Parse the user ratings for a particular episode.
    Example url: http://www.imdb.com/title/tt6075310/?ref_=ttep_ep1
    """
    item_rating = response.meta['rating']
    tables = response.css("table[cellpadding='0']")
    
    # 1st table is vote distribution on rating
    # 2nd table is vote distribution on age and gender
    try:
      ratingTable = tables[0]
      ageGenderTable = tables[1]
    except IndexError:
      # e.g. http://www.imdb.com/title/tt7399178/ratings
      logging.warn('Insufficient user ratings for episode at {}'.format(response.url))
      raise StopIteration

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

  def parseSeason(self, response):
    """Parse a season, recursing into its episodes.
    Example url: snlarchives.net/Seasons/?1975
    """
    item_season = response.meta['season']

    for episode in response.css('#section_1 a'):
      href_url = episode.css("a ::attr(href)").extract_first()
      if href_url.startswith("/Episodes/?") and len(href_url) == 19:
        episode_url = self.base_url + href_url
        dummy_ep = Episode(epid=self.id_from_url(episode_url))
        if not self.interested(dummy_ep):
          continue
        yield scrapy.Request(episode_url, callback=self.parseEpisode, meta={'season': item_season})

  def parseEpisode(self, response, target_tid=None):
    """Parse an episode, recursing into its titles.
    Example url: http://www.snlarchives.net/Episodes/?20150328
    """
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
          episode['epno'] = int(epstr.split(' ')[0][1:])
        except ValueError:
          # NB: Currently deliberately skipping episodes that aren't part of a normal season.
          logging.warn("Couldn't parse epno from values = {}. (Was this a special?)".format(
            values, response.url))
          return
      elif field in actor_fieldname_to_list:
        dest = actor_fieldname_to_list[field]
        for actor_ele in valueTd.css('a'):
          actor = self.actor_from_link(actor_ele)
          dest.append(actor)

    extra_actors = hosts + cameos + musical_guests + filmed_cameos
    # We pass these extra people on when we parse this episodes titles. Just because of how snlarchive
    # structures its pages, there's certain actor metadata available here that isn't available on
    # the title pages, specifically in the case of hosts, cameos, and musical guests.
    extra_lookup = {a['aid']: a for a in extra_actors}

    yield episode

    for host_actor in hosts:
      yield Host(epid=epid, aid=host_actor['aid'])

    order = -1 # Record the relative order of sketches
    for sketchInfo in response.css("div.sketchWrapper"):
      order += 1
      for thing in self.parseSketchDiv(sketchInfo, order, episode['epid'], extra_lookup):
        yield thing


  def parseSketchDiv(self, sketchInfo, order, epid, extra_cast):
    """Yield a Title, and any other associated entities, given a 'div.sketchWrapper'
    from an snlarchive episode page.
    """
    title = Title(order=order, epid=epid)
    # e.g. /Episodes/?197510111
    href_url = sketchInfo.css("a ::attr(href)").extract_first()
    title['tid'] = href_url.split('?')[1]
    if not self.interested(title):
      raise StopIteration
    # In some cases, the sketch name may not be contained to a single node. e.g. the SNL
    # digital short in this episode: http://www.snlarchives.net/Episodes/?20051217
    title['name'] = ''.join(sketchInfo.css(".title ::text").extract())
    title['category'] = sketchInfo.css(".type ::text").extract_first()

    title_url = sketchInfo.css(".title a ::attr(href)").extract_first()
    # If the title is linkfified, that means it has an snlarchive page under /Sketches or /Commercials
    if title_url:
      if title_url.startswith('/Sketches/'):
        skid = self.id_from_url(title_url)
        title['skid'] = skid 
        # The name for the series of recurring sketches may not be the same as the name of
        # this instance of the recurring sketch. e.g. 'SNL Digital Short - Lazy Sunday' vs.
        # 'SNL Digital Short'
        name = sketchInfo.css('.title a ::text').extract_first()
        rec_sketch = Sketch(skid=skid, name=name)
        yield rec_sketch
      elif title_url.startswith('/Commercials/'):
        # meh. We could add another item type for Commercials and add a foreign key
        # here. I'm not sure it's worth it though - commercial parodies that are
        # repeated seem to be *very* rare.
        pass
      else:
        logging.warn('Unrecognized title url format: {}'.format(title_url))

    aids_this_title = {}
    # Parse the Appearances in this title
    for cast_entry in sketchInfo.css(".roleTable > tr"):
      try:
        actor, app = self.parse_cast_entry_tr(cast_entry, extra_cast, title['tid'])
      except EmptyCastRowException as e:
        logging.warn(e.message)
        continue
      yield actor
      
      aid = actor['aid']
      # Since Character and Impression entities are derivable from the corresponding
      # Appearance entities, I was hoping to put the logic for generating them in a 
      # pipeline, but scrapy pipelines can't yield multiple items :(
      # https://github.com/scrapy/scrapy/issues/1915
      impid, charid = app.get('impid'), app.get('charid')
      if impid:
        yield Impression(impid=impid, aid=aid, name=app['role'])
      if charid:
        yield Character(charid=charid, aid=aid, name=app['role'])

      if aid not in aids_this_title:
        yield app
        aids_this_title[aid] = app
      else:
        prev = aids_this_title[aid]
        # if both roles have a name, and those names are distinct, then maybe they
        # did legit appear in the same sketch twice in two different roles/capacities.
        # can happen rarely. e.g. http://www.snlarchives.net/Episodes/?2005111211
        a_role, b_role = app.get('role'), prev.get('role')
        if a_role and b_role and (a_role != b_role):
          yield app
        else:
          # Example where this happens: http://www.snlarchives.net/Episodes/?200604158
          logging.warn('Actor {} appeared multiple times in sketch with tid={}, and one '
          'role was empty, or both were the same.'.format(
            actor['aid'], title['tid']))
          # Y'know what, just yield it anyways for now.
          yield app
        # (God help us if actors appear more than twice in the same sketch...)

    yield title

  def parse_cast_entry_tr(self, row, extra_cast_lookup, tid):
    """Parse a row that describes a cast member in a particular segment, and their role."""
    cells = row.css('td')
    actor_cell = cells[0]
    actor_class = actor_cell.css('::attr(class)').extract_first()
    actor_link = actor_cell.css('a')
    # What's the context of this actor's appearance? As a cast member, host, cameo, etc.
    capacity = 'unknown'
    actor_name = actor_cell.css('::text').extract_first()
    if actor_name is None:
      raise EmptyCastRowException('Found no name for cast tr in sketch with tid={}'.format(tid))
    actor_name = actor_name.strip()
    actor_name = helpers.Aid.asciify(actor_name)
    if actor_name == 'Jack Handey':
      # This is a weird special case. Jack Handey appears in a bunch of 'Deep Thoughts'
      # segments in the 90's, e.g.: http://www.snlarchives.net/Episodes/?1991032313
      # And he is one of the few people to appear in a sketch who has no page 
      # on snlarchive - not as cast, crew, or guest. He isn't listed as a cast member
      # for any of the seasons on which his Deep Thoughts appear, nor is he listed as
      # a 'special guest' or 'cameo' on the corresponding episode pages. Anyways,
      # we'll give him a made-up aid and give him the 'crew' capacity (because wikipedia
      # says he was credited as an snl writer).
      capacity = 'other'
      actor = Actor(aid=actor_name, type='crew')
    elif not actor_link:
      # Actor name is not linkified. This means they're not cast members. They could
      # be the host, cameos, or musical guest (though this code path currently isn't
      # reached for musical titles). The td class gives a hint.
      if not actor_class:
        logging.warn("No class found in actor cell {}".format(actor_cell))
        capacity = 'unknown'
      else:
        capacity = actor_class
      try:
        actor = extra_cast_lookup[actor_name]
      except KeyError:
        # Example of how this can happen: http://www.snlarchives.net/Episodes/?201405039
        # The musical guest this episode is Coldplay. Chris Martin is a member of Coldplay,
        # and is appearing in a musical-guest-ish capacity in a sketch, but we fail to match him up
        # with the name we scraped for the musical guest. And in fact, there is no page
        # on snlarchive for 'Chris Martin', and therefore no corresponding 'aid'.
        logging.warn('"{}" appeared in sketch with tid={}, but their name was not linkified, '
            'and they were not listed on the episode page as host, guest, cameo etc.'.format(
              actor_name, tid)
            )
        # ( This is actually not that uncommon. Might want to log at info level if it gets too spammy.)
        # The consequence of this is that we don't know their relation to the show
        # (cast member, crew, guest), or have an snlarchive url for them.
        actor = Actor(aid=actor_name, type='unknown')
    else:
      capacity = actor_class or 'cast'
      actor = self.actor_from_link(actor_link)

    app = Appearance(aid=actor['aid'], tid=tid, capacity=capacity)
    if len(cells) == 3:
      _dots, role_td = cells[1:]
      app = self.parse_role_cell(role_td, app, tid)
    else:
      assert len(cells) == 1

    return actor, app

  def parse_role_cell(self, role_td, appearance, tid):
    rolenames = role_td.css('::text').extract()
    # Strip whitespace, and filter any resulting empty strings
    rolenames = [name.strip() for name in rolenames if name.strip()]
    if rolenames[-1] == '(voice)':
      appearance['voice'] = True
      rolenames = rolenames[:-1]
    rolename = ' '.join(rolenames)
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
        raise Exception('Unrecognized role URL in sketch with tid={}: {}'.format(tid, href))
    return appearance

  @classmethod
  def actor_from_link(self, anchor):
    href = anchor.css('::attr(href)').extract_first()
    if href.startswith('/Guests/'):
      atype = 'guest'
    elif href.startswith('/Cast/'):
      atype = 'cast'
    elif href.startswith('/Crew/'):
      atype = 'crew'
    else:
      raise Exception('Unrecognized actor url: {}'.format(href))
    name = anchor.css('::text').extract_first().strip()
    name = helpers.Aid.asciify(name)
    return Actor(
        aid=name,
        url=href,
        type=atype,
        )

  @staticmethod
  def id_from_url(url):
    qmark_idx = url.rfind('?')
    return url[qmark_idx+1:]

