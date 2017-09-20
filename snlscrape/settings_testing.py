# Some settings overrides for unit tests

ITEM_PIPELINES = {
    'snlscrape.pipelines.EntityDedupePipeline': 300,
    # Don't include the json output pipeline during testing
}    

LOG_LEVEL = 'WARN'
