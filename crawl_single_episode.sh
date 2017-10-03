#!/bin/bash

# Episode id (per snlarchive) can be specified as command line argument. Otherwise,
# default to some arbitrarily chosen episode from 2002.
epid=${1:-20020518}
scrapy crawl \
  -s SNL_TARGET_EPID=$epid\
  -s SNL_OUTPUT_DIR=single_ep_output\
  snlspider
