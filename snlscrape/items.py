# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

import scrapy

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
  year = scrapy.Field()

class Episode(BaseSnlItem):
  epid = scrapy.Field()
  # epno = n -> this is the nth episode of the season (starting from 0)
  # may be None if this is a special episode (e.g. anniversary special)
  epno = scrapy.Field()
  sid = scrapy.Field()
  aired = scrapy.Field()

class Host(BaseSnlItem):
  # NB: an episode may have more than one host.
  # (Might even have zero? Probably only if it's a special)
  epid = scrapy.Field()
  aid = scrapy.Field()

# Not sure if I want to track info about musical guests and performances.
# If so, might want to rename this 'Performer'
class Actor(BaseSnlItem):
  aid = scrapy.Field(pkey=True)
  name = scrapy.Field()
  # This is based on snlarchive's schema, which assigns exactly one of these
  # categories to each person. I believe cast > crew > guest in terms of precedence.
  # That is, if someone has been a crew member and a cast member (e.g. Mike O'Brien)
  # or a cast member and a guest (e.g. Kristen Wiig), they'll have type 'cast'.
  # If they've been a crew member and a guest (e.g. Conan O'Brien), they'll have type 'crew'.
  # (This field is therefore probably less useful than the 'capacity' field on Appearance,
  # which lets us distinguish times that the same person has appeared as cast member
  # vs. host vs. cameo vs. ...)
  type = scrapy.Field(possible_values = {'cast', 'guest', 'crew'})

class Title(BaseSnlItem):
  tid = scrapy.Field()
  epid = scrapy.Field()
  name = scrapy.Field()
  category = scrapy.Field(possible_values = {
    'Cold Opening', 'Monologue', 'Sketch', 'Show', 'Film', 'Musical Performance',
    'Weekend Update', 'Goodnights', 'Guest Performance',
    })
  skid = scrapy.Field(optional=True)
  # Counting from cold opening = 0
  order = scrapy.Field()

class Appearance(BaseSnlItem):
  aid = scrapy.Field()
  tid = scrapy.Field()
  capacity = scrapy.Field()
  role = scrapy.Field()
  impid = scrapy.Field()
  charid = scrapy.Field()
  voice = scrapy.Field(default=False)

class Character(BaseSnlItem):
  charid = scrapy.Field(pkey=True)
  name = scrapy.Field()
  aid = scrapy.Field()

class Impression(BaseSnlItem):
  impid = scrapy.Field(pkey=True)
  name = scrapy.Field()
  aid = scrapy.Field()
