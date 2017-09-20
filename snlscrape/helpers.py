import datetime

class Tid(object):

  @staticmethod
  def to_date(tid):
    year, month, day = map(int, [tid[:4], tid[4:6], tid[6:8]])
    return datetime.date(year, month, day)

class Sid(object):

  @staticmethod
  def from_date(date):
    assert date.month != 8
    # Seasons start around sept-oct, and usually end around may, though there's
    # at least one case that ends in july.
    early = date.month <= 7
    sid = 1 + (date.year - 1975)
    if early:
      sid -= 1
    return sid

  @classmethod
  def from_tid(cls, tid):
    date = Tid.to_date(tid)
    return cls.from_date(date)

class Epid(object):

  @staticmethod
  def from_tid(tid):
    epid_len = 4 + 2 + 2
    return tid[:epid_len]
