#!/bin/bash

# Episode id (per snlarchive) can be specified as command line argument. Otherwise,
# default to some arbitrarily chosen episode from 2002.
epid=${1:-20020518}

# May want to set SNL_SCRAPE_IMDB to 1 if you want to check IMDB scraping (though it will 
# scrape the ratings for all the episodes in the chosen epid's season)
scrapy crawl \
  -s SNL_TARGET_EPID=$epid\
  -s SNL_OUTPUT_DIR=single_ep_output\
  -s SNL_SCRAPE_IMDB=0\
  snlspider
