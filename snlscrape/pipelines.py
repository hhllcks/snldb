# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

import os
import logging
from collections import defaultdict

import scrapy.exporters
from scrapy.exceptions import DropItem

# from items import *
#import items

# It's conceivable that a 'duplicate' entity could have more information than the
# version that came before it. Could make allowances for somehow letting 'new' information
# through. In practice, I'm dubious as to whether this would actually come up.
class EntityDedupePipeline(object):
  """Keeps track of seen entities and drops dupes (after matching on the 'pkey' field, if present).
  """

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

  def __init__(self, output_dir):
    self.output_dir = output_dir
    assert os.path.isdir(output_dir), 'Directory {} does not exist'.format(output_dir)

  @classmethod
  def from_crawler(cls, crawler):
    return cls(output_dir=crawler.settings.get('SNL_OUTPUT_DIR'))

  def open_spider(self, spider):
    self.exporters = {}

  def close_spider(self, spider):
    for key in self.exporters:
      exporter = self.exporters[key]
      exporter.finish_exporting()
      exporter.file.close()

  def exporter_for_item(self, item):
    classname = item.__class__.__name__ 
    table_name = classname.lower() + 's'
    # sketchs is enough to drive me crazy
    if classname == 'Sketch':
      table_name = 'sketches'
    if table_name not in self.exporters:
      fname = '{}.json'.format(table_name)
      path = os.path.join(self.output_dir, fname)
      f = open(path, 'wb')
      exporter = scrapy.exporters.JsonLinesItemExporter(f)
      exporter.start_exporting()
      self.exporters[table_name] = exporter
    return self.exporters[table_name]

  def process_item(self, item, spider):
    exporter = self.exporter_for_item(item)
    exporter.export_item(item)
    return item

class FieldValidationException(Exception):
  pass

class ValidatorPipeline(object):
  """Validates an item's field values according to the per-field metadata in items.py.
  Logs warnings on any validation failures.
  """

  def process_item(self, item, spider):
    for fieldname, meta in item.fields.items(): 
      value = item.get(fieldname)
      try:
        self.validate_field_value(meta, value, fieldname)
      except AssertionError as e:
        #raise FieldValidationException(e.message)
        # Actually, raising an exception here is probably a bit too harsh, since
        # it'll have the affect of supressing the item from the output.
        # And it'd be annoying for an otherwise good full scrape to have a few missing
        # items here and there because there was a title category I forgot to include
        # or something.
        logging.warn('Validation error on item: {}\n{}'.format(item, e.message))
    return item

  def validate_field_value(self, field, value, fieldname):
    if value is None:
      assert field.get('optional'), "No value for non-optional field {}".format(fieldname)
      # If a field has no value, the other rules don't apply.
      return
    if 'type' in field:
      assert isinstance(value, field['type']), "Got value {} for field {}. Expected type {}.".format(
          value, fieldname, field['type'])
    if 'min' in field:
      assert value >= field['min'], "Value {} for field {} less than minimum = {}".format(
          value, fieldname, field['min'])
    if 'possible_values' in field:
      assert value in field['possible_values'], (
        "Value {} for field {} not among possible values: {}".format(
            value, fieldname, field['possible_values'])
        )
    if 'keys' in field:
      assert set(value.keys()) == set(field['keys'])

class DefaultValueSetterPipeline(object):
  """If a field has no value but has a default specified in its metadata, set that default value.
  """

  def process_item(self, item, spider):
    for fieldname, meta in item.fields.items():
      val = item.get(fieldname)
      if val is None:
        item[fieldname] = meta.get('default')
    return item

