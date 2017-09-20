# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

import os
from collections import defaultdict

import scrapy.exporters
from scrapy.exceptions import DropItem

from items import *

# TODO: add a validation pipeline that checks against rome rules declared with
# field metadata (e.g. possible_values={...}, optional=False, etc.)

class EntityDedupePipeline(object):

  def open_spider(self, spider):
    self.seen = defaultdict(set)

  def process_item(self, item, spider):
    if item.dedupable():
      key = item.pkey
      cache = self.seen[item.__class__.__name__]
      if key in cache:
        raise DropItem
      cache.add(key)
    return item

class MultiJsonExportPipeline(object):
  """Export to json - one json file for every entity type in items.py
  """

  # TODO: This should probably be specified in settings or something? And using rel've
  # paths can get wonky...
  output_dir = 'output'

  def open_spider(self, spider):
    self.exporters = {}

  def close_spider(self, spider):
    for exporter in self.exporters.itervalues():
      exporter.finish_exporting()
      exporter.file.close()

  def exporter_for_item(self, item):
    classname = item.__class__.__name__ 
    table_name = classname.lower() + 's'
    if table_name not in self.exporters:
      fname = '{}.json'.format(table_name)
      path = os.path.join(self.output_dir, fname)
      f = open(path, 'w')
      exporter = scrapy.exporters.JsonLinesItemExporter(f)
      exporter.start_exporting()
      self.exporters[table_name] = exporter
    return self.exporters[table_name]

  def process_item(self, item, spider):
    exporter = self.exporter_for_item(item)
    exporter.export_item(item)
    return item
