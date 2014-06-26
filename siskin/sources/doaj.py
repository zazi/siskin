# coding: utf-8
# pylint: disable=F0401,W0232,E1101,C0103,C0301
"""
Directory of Open Access Journals.
"""

from gluish.benchmark import timed
from gluish.intervals import monthly
from gluish.parameter import ClosestDateParameter
from gluish.utils import shellout
from siskin.configuration import Config
from siskin.task import DefaultTask
import datetime
import elasticsearch
import json
import luigi

config = Config.instance()

class DOAJTask(DefaultTask):
    """ Base task for DOAJ. """
    TAG = '028'

    def closest(self):
        """ Monthly schedule. """
        return monthly(date=self.date)

class DOAJCSV(DOAJTask):
    """ CSV dump, updated every 30 minutes. Not sure what's in there. """
    date = luigi.DateParameter(default=datetime.date.today())
    url = luigi.Parameter(default='http://doaj.org/csv', significant=False)

    @timed
    def run(self):
        """ Just download file. """
        output = shellout('wget -q --retry-connrefused {url} -O {output}', url=self.url)
        luigi.File(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='csv'))

class DOAJDump(DOAJTask):
    """ Complete DOAJ Elasticsearch dump. """
    date = ClosestDateParameter(default=datetime.date.today())

    host = luigi.Parameter(default='doaj.org', significant=False)
    port = luigi.IntParameter(default=80, significant=False)
    url_prefix = luigi.Parameter(default='query', significant=False)

    batch_size = luigi.IntParameter(default=1000, significant=False)
    timeout = luigi.IntParameter(default=60, significant=False)
    max_retries = luigi.IntParameter(default=3, significant=False)

    @timed
    def run(self):
        """ Connect to ES and issue queries. TODO: See if they support scan. """
        hosts = [{'host': self.host, 'port': self.port, 'url_prefix': self.url_prefix}]
        es = elasticsearch.Elasticsearch(hosts, timeout=self.timeout, max_retries=self.max_retries)
        with self.output().open('w') as output:
            offset = 0
            total = es.count(body={'query': {'match_all': {}}}, index=('journal', 'article')).get('count')
            while offset <= total:
                self.logger.debug(json.dumps({'offset': offset, 'total': total}))
                result = es.search(body={'constant_score':
                                   {'query': {'match_all': {}}}},
                                   index=('journal', 'article'),
                                   size=self.batch_size, from_=offset)
                for doc in result['hits']['hits']:
                    output.write("%s\n" % json.dumps(doc))
                offset += self.batch_size

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='ldj'))
