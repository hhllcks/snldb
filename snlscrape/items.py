# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

import scrapy

"""
TODO: I'm tempted to 'denormalize' here and add a bunch of redundant fields that
will make life easier. e.g. everywhere there's an aid, also have an actor_name field?
The ultimate size of the whole dataset should be pretty puny, so it's not like 
optimizing for compact storage or efficient queries is particularly important.

Could probably even do the denormalization automagically with a pipeline and some
field metadata, without having to touch the spider.

TODO: Be more consistent about whether id fields should be ints or strs?
Main advantage of using strs for epid/tid is that it makes it simpler to 
break them up into their component parts (year, mo, day, no)
"""

class BaseSnlItem(scrapy.Item):
  
  @classmethod
  def dedupable(cls):
    return cls.key_field() is not None

  @classmethod
  def key_field(cls):
    for fieldname, meta in cls.fields.iteritems():
      if 'pkey' in meta:
        return fieldname

  @property
  def pkey(self):
    return self[self.key_field()]


class Season(BaseSnlItem):
  sid = scrapy.Field(type=int, min=1)
  # Year in which the season began (e.g. season 1 has year 1975)
  year = scrapy.Field(type=int)

# Not sure if I want to track info about musical guests and performances.
# If so, might want to rename this 'Performer'
class Actor(BaseSnlItem):
  aid = scrapy.Field(pkey=True, type=basestring)
  name = scrapy.Field(type=basestring)
  # This is based on snlarchive's schema, which assigns exactly one of these
  # categories to each person. I believe cast > crew > guest in terms of precedence.
  # That is, if someone has been a crew member and a cast member (e.g. Mike O'Brien)
  # or a cast member and a guest (e.g. Kristen Wiig), they'll have type 'cast'.
  # If they've been a crew member and a guest (e.g. Conan O'Brien), they'll have type 'crew'.
  # (This field is therefore probably less useful than the 'capacity' field on Appearance,
  # which lets us distinguish times that the same person has appeared as cast member
  # vs. host vs. cameo vs. ...)
  type = scrapy.Field(possible_values = {'cast', 'guest', 'crew'})

class Cast(BaseSnlItem):
  """A cast member on a particular season."""
  aid = scrapy.Field(type=basestring)
  sid = scrapy.Field(type=int, min=1)
  # Was this cast member a "featured player" during this season? (This is the level
  # most cast members start at)
  featured = scrapy.Field(type=bool, default=False)
  update_anchor = scrapy.Field(type=bool, default=False)
  # These fields are only present if this person wasn't present for the full
  # season (i.e. they started in the middle of a season, or left early)
  first_epid = scrapy.Field(type=basestring, optional=True)
  last_epid = scrapy.Field(type=basestring, optional=True)

class Episode(BaseSnlItem):
  # We use the ids snlarchives use in their urls. In practice, these look
  # like dates, e.g. '20020518'
  epid = scrapy.Field(type=basestring)
  # epno = n -> this is the nth episode of the season (starting from 0)
  # Specials have no epno, but for the moment I'm making a deliberate 
  # decision to exclude them from the scrape.
  epno = scrapy.Field(type=int, min=0)
  # Could maybe do the 'foreign key' thing more elegantly with some 
  # metaclass magic, but don't want to mess around with that too much
  # since scrapy is clearly already doing some metaclass magic here.
  sid = scrapy.Field()
  aired = scrapy.Field(type=basestring)

class Host(BaseSnlItem):
  # NB: an episode may have more than one host.
  # (Might even have zero? Probably only if it's a special)
  epid = scrapy.Field(type=basestring)
  aid = scrapy.Field(type=basestring)

class Title(BaseSnlItem):
  tid = scrapy.Field(type=basestring)
  epid = scrapy.Field(type=basestring)
  category = scrapy.Field(possible_values = {
    # Standard 1-every-episode things
    'Cold Opening', 'Monologue', 'Goodnights', 
    # Update, and a couple off-brand versions that ran during Ebersol years
    'Weekend Update', 'Saturday Night News', 'SNL Newsbreak',

    # Sketches
    'Sketch', 'Musical Sketch',
    # These are just (live) sketches that take the format of a tv show / game show
    # (May be a fake show, or a parody of a real show.)
    'Show', 'Game Show',
    # Again, just a live sketch that takes the form of an awards show (real or fake)
    'Award Show',

    # Recorded segments
    'Film', 'Commercial', 'Cartoon',

    'Musical Performance',
    # In recent years, this category has been mostly used for musical performances by 
    # someone other than the musical guest (e.g. whatever the hell happened with the Baha
    # men in 2000 here: http://www.snlarchives.net/Episodes/?200010217)
    # Back in the 70's and 80's, they did some other stuff like guest magic performances
    # by Penn and Teller (which I guess were a regular thing around '86?) and guests
    # doing a set of stand-up comedy
    'Guest Performance', 
    'Miscellaneous', 'In Memoriam', 
    # This one only seems to show up in 81-82
    'Talent Entrance',
    # I guess like an intro to a musical act or something? e.g. http://www.snlarchives.net/Episodes/?1982121112
    'Intro', 
    # idk what this is. Example: http://www.snlarchives.net/Episodes/?201410118
    'Encore Presentation',
    })
  # Name is empty for certain categories such as Monologue, Weekend Update, and 
  # Goodnights.
  name = scrapy.Field(type=basestring, optional=True)
  skid = scrapy.Field(optional=True, type=basestring)
  order = scrapy.Field(type=int, min=0)

# A recurring sketch (having a /Sketches url on snlarchive)
class Sketch(BaseSnlItem):
  skid = scrapy.Field(pkey=True, type=basestring)
  name = scrapy.Field(type=basestring)

class Appearance(BaseSnlItem):
  aid = scrapy.Field()
  tid = scrapy.Field()
  capacity = scrapy.Field(possible_values = {
    'cast', 'host', 'cameo', 
    'music', # cameo by musical guest  
    'filmed', # filmed cameo
    'guest', # 'special guest' - so far only seen for muppets in 75
    })
  # The name of the credited role. Occasionally, this may be empty. This mostly happens
  # in the monologue and Weekend Update, and means they're playing themselves. 
  role = scrapy.Field(optional=True)
  impid = scrapy.Field(optional=True)
  charid = scrapy.Field(optional=True, type=int)
  voice = scrapy.Field(default=False)

class Character(BaseSnlItem):
  charid = scrapy.Field(pkey=True, type=int)
  name = scrapy.Field()
  aid = scrapy.Field()

class Impression(BaseSnlItem):
  impid = scrapy.Field(pkey=True)
  name = scrapy.Field()
  aid = scrapy.Field()
