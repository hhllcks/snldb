# snldb
This project aims to scrape a Saturday Night Live database from the web. For now the following sources were used:

  * http://www.snlarchives.net
  * http://www.imdb.com/title/tt0072562
 
Thanks to Joel Navaroli ([@snlmedia](https://twitter.com/snlmedia)) for creating the awesome archive that is snlarchives.net. Please visit the site to answer all of your questions about snl.

What's missing from the archive is some analysis. That why I created this project. I wanted to answer questions like:

  * How have the ratings developed over the years?
  * Which actors had the biggest presence on the show (most titles per episode on average)?
  * Which actor had the most appearances in a single episode?

If you have some ideas for other questions to answer, just send them to me or play with the data yourself.

# Where is the data
If you are only interested in the data you can find it in the output folder. However we will not guarantee that the data is up to date. If you want a fresh dataset you should crawl the data yourself or look at the [kaggle dataset page](https://www.kaggle.com/hhllcks/snldb).

# How to crawl fresh data
To use the scrapy crawler, make sure you've first installed the modules listed in requirements.txt (`pip install -r requirements.txt`). We recommend using Python 3 (at time of writing, Python 2 also works, but isn't officially supported).

After that you can test everything by running 
```shell
./crawl_single_episode.sh
```
The folder single_ep_output should now contain json files with the crawled data for one episode.

To perform a complete crawl, run
```shell
./crawl_all.sh
```
This will overwrite the json files in the output folder.

You can convert the json files to csvs by running
```shell
python convert_json_to_csv.py
```
This should place the corresponding .csv files next to the .json files in the output directory.

# Development

There are some unit tests in the `snlscrape` package which can by run by invoking `pytest` from the project root.

`crawl_single_episode.sh` takes an episode id as an optional command-line argument (e.g. `./crawl_single_episode.sh 20130511`), which can be useful for debugging. For debugging parsing issues, the `scrapy shell` command is highly useful (e.g. `scrapy shell http://www.snlarchives.net/Cast/?KrWi`).

# Contact us

If you have any ideas of how to improve this project or if you have new questions you want to answer with the data don't hesitate to contact us.

[Hendrik Hilleckes](https://github.com/hhllcks) ([@hhllcks](http://www.twitter.com/hhllcks), [hllcks@gmail.com](hhllcks@gmail.com), [blog.hhllcks.de](https://blog.hhllcks.de) )

[Colin Morris](https://github.com/colinmorris) (http://colinmorris.github.io/)
