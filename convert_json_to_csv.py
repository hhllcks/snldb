"""
Goes through the 'raw' json files scraped by snlscrape and saves them to csv after
applying the following transformations:
  - Manually corrects a few errors in the metadata from snlarchive
  - Adds some useful merge columns (e.g. season id in titles)
  - Adds some other useful derived columns, e.g. to the seasons table add columns 
    for the ids of the first and last episode of each season, and the total number of episodes
  - Adds a column to the actors table with inferred gender (using the gender_guesser library,
    with some manual corrections)
  - Creates a new derived table, tenure, with a row for each cast member describing 
    their time on the show (how many episodes they appeared in, how many episodes
    there were between their first and last show, and how many seasons they were on)
"""
from __future__ import division, print_function
import pandas as pd
import glob
import os

DATA_ROOT = 'output'
OUTPUT_ROOT = 'output'

# Whether to add derived columns to titles/episodes that useful specifically for
# analyzing cast member airtimes.
AIRTIME = False

def eps_in_range(start, end, episodes):
  epidx = (
    (episodes['epid'] >= start)
    & (episodes['epid'] <= end)
  )
  return epidx.sum()

def load_tables():
  tables = {}
  for path in glob.glob('{}/*.json'.format(DATA_ROOT)):
    fname = os.path.basename(path)
    name = fname.split('.')[0]
    df = pd.read_json(path, lines=True)
    tables[name] = df
  return tables

def add_indices(tables):
  # Has no effect on final output, but some of the code here relies on these indices, so.
  _table_names = ['actors', 'appearances', 'characters', 'episodes', 'hosts', 'impressions',
		 'seasons', 'sketches', 'titles', 'casts',
		]
  table_to_index = dict(episodes='epid', impressions='impid', seasons='sid', titles='tid', actors='aid')
  for (tablename, idx_col) in table_to_index.items():
      tables[tablename].set_index(idx_col, drop=False, inplace=True)

def add_merge_cols(tables):
  # Add epid, sid to appearances
  apps = tables['appearances']
  mg = apps.merge(tables['titles'], on='tid')\
      .drop(['category', 'order', 'skid', 'name'], axis=1)
  mg = mg.merge(tables['episodes'], on='epid')\
      .drop(['aired', 'epno'], axis=1)
  tables['appearances'] = mg

  # Add sid to titles
  titles = tables['titles']
  mg = titles.merge(tables['episodes'], on='epid')\
      .drop(['aired', 'epno'], axis=1)
  tables['titles'] = mg 

def enrich_seasons(seasons, episodes):
  """Add some derived columns to the seasons table."""
  first_eps = []
  last_eps = []
  n_eps = []
  for season in seasons.itertuples():
    epids = episodes[episodes['sid']==season.sid]['epid']
    first_eps.append(epids.min())
    last_eps.append(epids.max())
    n_eps.append(len(epids))
  seasons['first_epid'] = first_eps
  seasons['last_epid'] = last_eps
  seasons['n_episodes'] = n_eps
  

def enrich_casts(casts, seasons, episodes):
  """Add a column for each cast-year entry with the number of episodes the cast member
  was eligible to appear in in that season. (Normally this will be fixed per season across
  all cast members. The exception is cast members who start late in the season or end their
  run mid-season.)
  """
  n_eps = []
  fracs = []
  for cast in casts.itertuples():
    first = cast.first_epid
    if pd.isnull(first):
      first = seasons.loc[cast.sid, 'first_epid']
    last = cast.last_epid
    if pd.isnull(last):
      last = seasons.loc[cast.sid, 'last_epid']
    count = eps_in_range(first, last, episodes)
    n_eps.append(count)
    frac = count / seasons.loc[cast.sid, 'n_episodes']
    fracs.append(frac)
  casts['n_episodes'] = n_eps
  casts['season_fraction'] = fracs

def eps_present_in_casts(cs, seasons, apps):
  eps = 0
  for cast in cs.itertuples():
    season = seasons.loc[cast.sid]
    if not pd.isnull(cast.first_epid):
      first = cast.first_epid
    else:
      first = season.first_epid
    if not pd.isnull(cast.last_epid):
      last = cast.last_epid
    else:
      last = season.last_epid
    present_epids = apps.loc[
      (apps['aid']==cast.aid) & 
      (apps['epid'] >= first) & (apps['epid'] <= last),
      'epid'
    ].unique()
    eps += len(present_epids)
  return eps

def build_tenure(t):
  seasons, apps, actors, casts = t['seasons'], t['appearances'], t['actors'], t['casts']
  # n_eps: how many episodes of SNL were there between this person's start and finish?
  # eps_present: how many episodes of SNL did this person appear in as a cast member?
  # (may be less than n_eps for weeks where they weren't in the show)
  
  # Haha, so I guess some performers actually have non-contiguous runs on the show (e.g. Al
  # Franken, so some previous assumptions won't work.)
  cols = ['aid', 'n_episodes', 'eps_present', 'n_seasons']
  rows = []
  cast = actors[actors['type']=='cast']
  for actor in cast.itertuples():
    aid = actor.aid
    cast_years = casts[casts['aid'] == aid].sort_values(by='sid')
    if len(cast_years) == 0:
      print("Warning: {} was in actors table with type='cast', but they aren't in casts table"\
        .format(aid))
      continue
    n_seasons = len(cast_years)
    n_episodes = cast_years['n_episodes'].sum()
    eps_present = eps_present_in_casts(cast_years, seasons, apps)

    row = [aid, n_episodes, eps_present, n_seasons]
    rows.append(row)
  return pd.DataFrame(rows, columns=cols)



weekend_update_categories = {'Weekend Update', 'Saturday Night News', 'SNL Newsbreak'}
live_sketch_categories = {'Sketch', 'Musical Sketch', 'Show', 'Game Show', 'Award Show'}
recorded_sketch_categories = {'Film', 'Commercial'}
# (See note in items.py re Miscellaneous category)
misc_performer_categories = {'Cold Opening', 'Monologue', 'Miscellaneous'}
# These are the categories of titles that count when computing airtime statistics. 
# Main omissions are Goodnights and Musical Performance. Also some rarer categories
# like Guest Performance, In Memoriam, Talent Entrance, etc.
performer_title_categories = set.union(
  misc_performer_categories, weekend_update_categories, live_sketch_categories, recorded_sketch_categories
)
def add_airtime_columns(titles, episodes, apps):
  """Add some derived columns to titles/episodes that are useful when calculating relative 'airtime'
  of cast members and guests.
  """
  # If there are n eligible titles in an episode, each has an episode_share of 1/n
  titles['episode_share'] = 0.0
  titles['n_performers'] = 0
  # The same as above, but each title is further normalized by number of performers present.
  titles['cast_episode_share'] = 0.0
  for episode in episodes.itertuples():
    ep_titles_ix = ((titles['epid']==episode.epid)
      & (titles['category'].isin(performer_title_categories)))
    n_titles = ep_titles_ix.sum()
    if n_titles == 0:
      print('Warning: Found 0 titles for epid {}. Skipping.'.format(episode.epid))
      continue
      
    titles.loc[ep_titles_ix, 'episode_share'] = 1/n_titles
    perfs = []
    for title in titles[ep_titles_ix].itertuples():
      performer_aids = apps[apps['tid']==title.tid]['aid'].unique()
      perfs.append(len(performer_aids))
    titles.loc[ep_titles_ix, 'n_performers'] = perfs
    titles.loc[ep_titles_ix, 'cast_episode_share'] = (
      titles.loc[ep_titles_ix, 'episode_share'] 
      / 
      titles.loc[ep_titles_ix, 'n_performers']
    )

import gender_guesser.detector as gender
detector = gender.Detector()

def names_from_file(fname):
  with open(fname) as f:
    return set([name.strip().decode('utf-8') for name in f])

# First names not recognized by gender_guesser
extra_malenames = {
  'Beck', 'Mikey', 'Chevy', 'Norm',
  'Nile', 'Lin-Manuel', 'Macaulay', 'Kiefer', 'Spike', 'Kanye', 'Rainn', 'Shia',
  'Sting', 'Hulk', 'Liberace', 'Yogi', 'Merv', 'Mr.', 'O.J.', 
}
extra_femalenames = {
  'Aidy', 'Sasheer', 'Janeane', 'Danitra',
  'Lorde', 'Taraji', 'Uzo', 'Brie', 'Rihanna', 'January',
  'Anjelica', 'Oprah', 'Ann-Margret',
}

# Names misgendered by gender_guesser (or labelled as androgynous/unknown)
female_fullnames = {
  'Blake Lively', 'Terry Turner', 'Dakota Johnson', 'Cameron Diaz', 'Taylor Swift',
  'Robin Wright', 'Sydney Biddle Barrows', 'Whitney Houston', 'Morgan Fairchild',
  'Reese Witherspoon',
  'Casey Wilson', 'Nasim Pedrad', 'Noel Wells', 'Jan Hooks', 'Robin Duke',
}.union(names_from_file('female_names.txt'))
male_fullnames = {
  'Kyle Gass', 'The Rock', 'Jamie Foxx', 'Kelsey Grammer', 'Leslie Nielsen',
  'Kyle MacLachlan', 'Desi Arnaz Jr.', 'Desi Arnaz', 'Kyle Mooney', 'The Weeknd',
  'Bernie Sanders', 'Sacha Baron Cohen', 'A. Whitney Brown', 'Finesse Mitchell',
  'Dana Carvey', 'Tracy Morgan',
  'Fran Tarkenton', 'Ashton Kutcher', 'Jackie Chan',
}.union(names_from_file('male_names.txt'))
# A few interesting cases: Dame Edna, RuPaul, Marilyn Manson, T.J. Jourian (transman). 
# I labelled as ffmm, respectively.

def genderize(name, confident=True):
  if name in female_fullnames:
    return 'female'
  if name in male_fullnames:
    return 'male'
  first = name.split()[0]
  if first in extra_malenames:
    return 'male'
  if first in extra_femalenames:
    return 'female'
  guess = detector.get_gender(first)
  if confident and guess == 'mostly_male':
    return 'male'
  if confident and guess == 'mostly_female':
    return 'female'
  return guess

def correct_errors(tables):
  casts = tables['casts']
  # According to Wikipedia, George Coe was only credited for SNL's very first episode
  casts.loc[casts['aid']=='George Coe', 'last_epid'] = 19751011
  # again, via wikipedia
  casts.loc[casts['aid']=="Michael O'Donoghue", 'last_epid'] = 19751108
  # Lots of other start/end dates that seem slightly off, but season 1 is the most
  # egregious - it seems to be the only time when cast members joined/left mid-season
  # and snlarchive didn't note it at all.

def save_tables(t):
  for name, df in t.items():
    fname = name + '.csv'
    path = os.path.join(OUTPUT_ROOT, fname)
    df.to_csv(path, encoding='utf-8', index=False)

def main():
  tables = load_tables()
  add_indices(tables)
  correct_errors(tables)
  add_merge_cols(tables)
  enrich_seasons(tables['seasons'], tables['episodes'])
  enrich_casts(tables['casts'], tables['seasons'], tables['episodes'])
  t = tables
  if AIRTIME:
    add_airtime_columns(t['titles'], t['episodes'], t['appearances'])
  t['tenure'] = build_tenure(t)
  t['actors']['gender'] = t['actors']['aid'].apply(genderize)
  save_tables(t)

if __name__ == '__main__':
  main()
