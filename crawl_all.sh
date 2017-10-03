#!/bin/bash

# This spider is mainly responsible for crawling the content from snlarchive 
# pages for Episodes and their Titles (sketches). Also, IMDB ratings of episodes.
scrapy crawl snlspider
# This spider is just responsible for crawling Cast items - who was on the cast 
# of which seasons, when did they start/end, etc.
scrapy crawl castspider
