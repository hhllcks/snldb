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
To use the scrapy crawler please make sure that you are working in an environment with Python 3 and that you have installed the modules listed in the requirements.txt.

After that you can test everything by running 
```shell
./crawl_single_episode.sh
```
The folder single_ep_output should now contain .json-files with the crawled data.

To start a complete crawl you have to run
```shell
./crawl_all.sh
```
This should place the .json-files in the output folder.

You can convert the .json-files into .csv-files by running
```shell
python convert_json_to_csv.py
```
This should place the corresponding .csv files next to the .json files.

# Contact us

If you have any ideas of how to improve this project or if you have new questions you want to answer with the data don't hesitate to contact us.

Hendrik Hilleckes ([@hhllcks](http://www.twitter.com/hhllcks), [hllcks@gmail.com](hhllcks@gmail.com), [blog.hhllcks.de](https://blog.hhllcks.de) )

Colin Morris (http://colinmorris.github.io/)
