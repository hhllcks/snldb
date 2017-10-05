import logging
from scrapy import logformatter

class SilentDropFormatter(logformatter.LogFormatter):
  """Scrapy's default behaviour when a pipeline raises a DropItem is to log
  a warning. In our case, dropping dupes is quite mundane, and shouldn't be 
  logged at such a high priority.
  """

  def dropped(self, item, exception, response, spider):
    return dict(level=logging.DEBUG, msg=logformatter.DROPPEDMSG,
        args=dict(exception=exception, item=item)
        )
