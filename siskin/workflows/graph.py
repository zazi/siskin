# coding: utf-8
# pylint: disable=F0401,C0111,W0232,E1101,E1103,C0301

from gluish.benchmark import timed
from gluish.common import Executable
from gluish.esindex import CopyToIndex
from gluish.intervals import monthly
from gluish.parameter import ClosestDateParameter
from gluish.utils import shellout
from siskin.sources.dbpedia import DBPAbbreviatedNTriples
from siskin.sources.gnd import GNDAbbreviatedNTriples
from siskin.task import DefaultTask
import datetime
import luigi
import shutil
import tempfile

class GraphTask(DefaultTask):
    TAG = 'graph'

    def closest(self):
        return monthly(date=self.date)

class GraphCombinedNTriples(GraphTask):
    date = ClosestDateParameter(default=datetime.date.today())
    version = luigi.Parameter(default="3.9")

    def requires(self):
        return {'gnd': GNDAbbreviatedNTriples(date=self.date),
                'de': DBPAbbreviatedNTriples(version=self.version, language='de'),
                'en': DBPAbbreviatedNTriples(version=self.version, language='en')}

    @timed
    def run(self):
        _, stopover = tempfile.mkstemp(prefix='siskin-')
        for _, target in self.input().iteritems():
            shellout("cat {input} >> {output}", input=target.path, output=stopover)
        luigi.File(stopover).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='nt'))

class GraphCombinedJson(GraphTask):
    date = ClosestDateParameter(default=datetime.date.today())
    version = luigi.Parameter(default="3.9")
    language = luigi.Parameter(default="de")

    def requires(self):
        return {'ntriples': GraphCombinedNTriples(date=self.date),
                'ntto': Executable(name='ntto')}

    @timed
    def run(self):
        output = shellout("ntto -w 2 -i -j {input} > {output}", input=self.input().get('ntriples').path)
        luigi.File(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='ldj'))

class GraphIndex(GraphTask, CopyToIndex):
    date = ClosestDateParameter(default=datetime.date.today())
    version = luigi.Parameter(default="3.9")
    language = luigi.Parameter(default="de")

    index = 'graph'
    doc_type = 'de'
    purge_existing_index = True
    mapping = {'de': {'date_detection': False,
                      'properties': {
                        's': {'type': 'string', 'index': 'not_analyzed'},
                        'p': {'type': 'string', 'index': 'not_analyzed'},
                        'o': {'type': 'string', 'index': 'not_analyzed'}}}}

    def requires(self):
        return GraphCombinedJson(date=self.date, version=self.version, language=self.language)

class GraphCayleyLevelDB(GraphTask):
    """ Create a Cayley LevelDB database from GND and dbpedia data. """
    date = ClosestDateParameter(default=datetime.date.today())
    version = luigi.Parameter(default="3.9")
    language = luigi.Parameter(default="de")

    gomaxprocs = luigi.IntParameter(default=8, significant=False)

    def requires(self):
        return {'ntriples': GraphCombinedNTriples(date=self.date),
                'cayley': Executable(name='cayley', message='http://git.io/KH-wFA')}

    @timed
    def run(self):
        dbpath = tempfile.mkdtemp(prefix='siskin-')
        shellout("cayley init -alsologtostderr -config {config} -dbpath={dbpath}",
             config=self.assets('cayley.leveldb.conf'), dbpath=dbpath)
        shellout("GOMAXPROCS={gomaxprocs} cayley load -config {config} -alsologtostderr -dbpath={dbpath} --triples {input}",
             gomaxprocs=self.gomaxprocs, config=self.assets('cayley.leveldb.conf'), dbpath=dbpath, input=self.input().get('ntriples').path)
        shutil.move(dbpath, self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='leveldb'))

class GraphCayleyMongoDB(GraphTask):
    """ Create a Cayley MongoDB database from GND and dbpedia data. """
    date = ClosestDateParameter(default=datetime.date.today())
    version = luigi.Parameter(default="3.9")
    language = luigi.Parameter(default="de")

    gomaxprocs = luigi.IntParameter(default=8, significant=False)

    def requires(self):
        return {'ntriples': GraphCombinedNTriples(date=self.date),
                'cayley': Executable(name='cayley', message='http://git.io/KH-wFA')}

    @timed
    def run(self):
        shellout("cayley init -alsologtostderr -config {config}",
                 config=self.assets('cayley.mongodb.conf'))
        shellout("cayley load -config {config} -alsologtostderr --triples {input}",
                 config=self.assets('cayley.mongodb.conf'),
                 input=self.input().get('ntriples').path)
        shellout("touch {output}", output=self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='mongo'))
