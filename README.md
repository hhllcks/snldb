# snldb
This project aims to scrape a Saturday Night Live database from the web. For now the following sources were used:

  * http://www.snlarchives.net
  * http://www.imdb.com/title/tt0072562
 
Thanks to Joel Navaroli ([@snlmedia](https://twitter.com/snlmedia @snlmedia)) for creating the awesome archive that is snlarchives.net. Please visit the site to answer all of your questions about snl.

What's missing from the archive is some analysis. That why I created this project. I wanted to answer questions like:

  * How have the ratings developed over the years?
  * Which actors had the biggest presence on the show (most titles per episode on average)?
  * Which actor had the most appearances in a single episode?

If you have some ideas for other questions to answer, just send them to me or play with the data yourself.

# The technology

To create this database I used python and Scrapy. [Scrapy](https://scrapy.org/ Scrapy) is a framework to scrape data from the web. If you want to learn about how that works look at the [notebook](snl.ipynb) that explains the process.

To display graphs in my analysis I used [bokeh](http://bokeh.pydata.org). Sadly github does not support it. Therefor my graphs do not appear if you open the notebooks on github. If you want the full experience please clone the repository and open the notebook in an environment that supports bokeh. The easiest way would be to create an [anaconda](https://anaconda.org/) environment with the following python modules installed:

  * pandas
  * numpy
  * bokeh
  * scrapy

# Example analysis

If you want to see an example analysis of the data, please refer to my [analysis notebook](snl_analysis.ipynb). It answers the questions above. 

# Contact me

If you have any ideas of how to improve this project or if you have new questions you want to answer with the data don't hesitate to contact me.

Twitter | Mail  | Blog
------------ | ------------- | -------------
[@hhllcks](http://www.twitter.com/hhllcks) | [hllcks@gmail.com](hhllcks@gmail.com)  | [blog.hhllcks.de](https://blog.hhllcks.de)
