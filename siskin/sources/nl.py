# coding: utf-8
# pylint: disable=F0401,C0111,W0232,E1101,E1103,C0301

"""
Nationallizenzen.

Configuration keys:

[core]

swb-mirror = /path/to/swb-mirror

google-username = user.name
google-password = secret
google-docs-key = crypticstring

"""

from gluish.benchmark import timed
from gluish.common import Directory
from gluish.esindex import CopyToIndex
from gluish.format import TSV
from gluish.intervals import hourly
from gluish.parameter import ClosestDateParameter
from gluish.path import iterfiles
from gluish.utils import shellout
from siskin.configuration import Config
from siskin.task import DefaultTask
import datetime
import gspread
import json
import logging
import luigi
import os
import re
import string
import sys
import tempfile

config = Config.instance()

class NLTask(DefaultTask):
    TAG = '017'

    def closest(self):
        if not hasattr(self, 'date'):
            raise RuntimeError('task has no date: %s' % self)
        task = NLLatestPackageDate(date=self.date)
        luigi.build([task], local_scheduler=True)
        s = task.output().open().read().strip()
        result = datetime.date(*(int(v) for v in s.split('-')))
        return result

class NLSync(NLTask):
    """ Sync the complete 'nationallizenzen' folder as is. """
    indicator = luigi.Parameter(default=hourly(fmt='%s'))

    def requires(self):
        return Directory(path=os.path.dirname(self.output().path))

    def run(self):
        source = os.path.join(config.get('core', 'swb-mirror'), 'nationallizenzen')
        target = os.path.dirname(self.output().path)
        shellout("rsync -avz {source} {target}", source=source, target=target)
        with self.output().open('w') as output:
            for path in iterfiles(target):
                output.write_tsv(path)

    def output(self):
        return luigi.LocalTarget(path=self.path(), format=TSV)

class NLInventory(NLTask):
    """ All (date, path) for a section, type, format and tag. """
    indicator = luigi.Parameter(default=hourly(fmt='%s'))
    section = luigi.Parameter(default='Monografien',
                              description='Monographien, ZDB, ZDB_in_Ein...')
    type = luigi.Parameter(default='SA', description='SA or SZ')
    format = luigi.Parameter(default='MARC', description='MARC, PICA, OLIX, '
                             'MAB2, MABPPN, MABPPNOS, MABPPNOScomb, MARCcomb')
    tag = luigi.Parameter(default='NL', description='NL or ILN')

    def requires(self):
        return NLSync(indicator=self.indicator)

    def run(self):
        template = (r'.*nationallizenzen/{0.section}/{0.type}-{0.format}-{0.tag}-'
                    r'(\d{{2}})(\d{{2}})(\d{{2}}).tar.gz')
        pattern = template.format(self)
        events = []

        with self.input().open() as handle:
            for row in handle.iter_tsv(cols=('path',)):
                match = re.search(pattern, row.path)
                if match:
                    year, month, day = map(int, match.groups())
                    year += 2000
                    date = datetime.date(year, month, day)
                    events.append((date, row.path))

        with self.output().open('w') as output:
            for date, path in sorted(events):
                output.write_tsv(date, path)

    def output(self):
        return luigi.LocalTarget(path=self.path(digest=True), format=TSV)

class NLLatestDateAndPath(NLTask):
    """ The latest (date, path) for a section, type, format and tag. """
    indicator = luigi.Parameter(default=hourly(fmt='%s'))
    date = luigi.DateParameter(default=datetime.date.today())
    section = luigi.Parameter(default='Monografien',
                              description='Monographien, ZDB, ZDB_in_Ein...')
    type = luigi.Parameter(default='SA', description='SA or SZ')
    format = luigi.Parameter(default='MARC', description='MARC, PICA, OLIX, '
                             'MAB2, MABPPN, MABPPNOS, MABPPNOScomb, MARCcomb')
    tag = luigi.Parameter(default='NL', description='NL or ILN')

    def requires(self):
        return NLInventory(indicator=self.indicator, section=self.section,
                           type=self.type, format=self.format, tag=self.tag)

    def run(self):
        pathmap = {}
        with self.input().open() as handle:
            for row in handle.iter_tsv(cols=('date', 'path')):
                date = datetime.datetime.strptime(row.date, '%Y-%m-%d').date()
                pathmap[date] = row.path

        def closest_keyfun(date):
            if date > self.date:
                return datetime.timedelta(999999999)
            return abs(date - self.date)

        closest = min(pathmap.keys(), key=closest_keyfun)
        if closest > self.date:
            raise RuntimeError('No shipment before: %s for %s' % (
                               min(pathmap.keys()), self))

        with self.output().open('w') as output:
            output.write_tsv(closest, pathmap.get(closest))

    def output(self):
        return luigi.LocalTarget(path=self.path(digest=True), format=TSV)

class NLPackageDescriptor(NLTask):
    """ Download package descriptor from google docs. """
    indicator = luigi.Parameter(default=hourly(fmt='%s'))

    def run(self):
        gc = gspread.login(config.get('core', 'google-username'),
                           config.get('core', 'google-password'))
        doc = gc.open_by_key(config.get('core', 'google-docs-key'))
        sheet = doc.get_worksheet(4)
        with self.output().open('w') as output:
            list_of_lists = iter(sheet.get_all_values())
        list_of_lists.next()
        with self.output().open('w') as output:
            for row in list_of_lists:
                section, type, format, tag = map(string.strip, row)
                output.write_tsv(section, type, format, tag)

    def output(self):
        return luigi.LocalTarget(path=self.path(digest=True), format=TSV)

class NLLatestPackageDate(NLTask):
    """ Return the latest date of some combined package. """
    date = luigi.DateParameter(default=datetime.date.today())

    def requires(self):
        prerequisite = NLPackageDescriptor()
        luigi.build([prerequisite], local_scheduler=True)
        with prerequisite.output().open() as handle:
            for row in handle.iter_tsv(cols=('section', 'type', 'fmt', 'tag')):
                yield NLLatestDateAndPath(date=self.date, section=row.section,
                                          type=row.type, format=row.fmt,
                                          tag=row.tag)

    def run(self):
        dates = set()
        for target in self.input():
            date, _ = target.open().next().strip().split('\t', 1)
            dates.add(date)
        with self.output().open('w') as output:
            output.write_tsv(max(dates))

    def output(self):
        return luigi.LocalTarget(path=self.path(digest=True), format=TSV)

class NLPackage(NLTask):
    """ A custom combined NL shipment. """
    date = ClosestDateParameter(default=datetime.date.today())
    kind = luigi.Parameter(default='tit', description='tit, lok or aut')

    def requires(self):
        prerequisite = NLPackageDescriptor()
        luigi.build([prerequisite], local_scheduler=True)
        with prerequisite.output().open() as handle:
            for row in handle.iter_tsv(cols=('section', 'type', 'fmt', 'tag')):
                yield NLLatestDateAndPath(date=self.date, section=row.section,
                                          type=row.type, format=row.fmt,
                                          tag=row.tag)

    def run(self):
        _, combined = tempfile.mkstemp(prefix='tasktree-')
        for target in self.input():
            with target.open() as handle:
                _, path = handle.iter_tsv(cols=('date', 'path')).next()
		if sys.platform.startswith("linux"):
		    shellout("tar -O -zf {input} -x --wildcards --no-anchored '*-{kind}.mrc' >> {output}",
			     kind=self.kind, input=target.path, output=combined)
		if sys.platform == "darwin":
		    shellout("tar -O -zf {input} -x --include='*-{kind}.mrc' >> {output}",
			     kind=self.kind, input=target.path, output=combined)
        luigi.File(combined).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='mrc'))

class NLJson(NLTask):
    date = ClosestDateParameter(default=datetime.date.today())
    kind = luigi.Parameter(default='tit', description='tit, lok or aut')

    def requires(self):
        return NLPackage(date=self.date, kind=self.kind)

    def run(self):
        output = shellout("marctojson -m date={date} {input} > {output}",
                          input=self.input().path, date=self.closest())
        luigi.File(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='ldj'))

class NLJsonWithSuggestions(NLTask):
    """ Create Json, but prepare for completion suggester. """
    date = ClosestDateParameter(default=datetime.date.today())
    kind = luigi.Parameter(default='tit', description='tit, lok or aut')

    def requires(self):
        return NLJson(date=self.date, kind=self.kind)

    @timed
    def run(self):
        with self.input().open() as handle:
            with self.output().open('w') as output:
                for row in handle:
                    doc = json.loads(row)
                    try:
                        for i in range(len(doc['content']['245'])):
                            full_title = doc['content']['245'][i]['a']
                            parts = full_title.split()

                            suggest = {
                                'input': [full_title] + parts,
                                'output': full_title,
                                'payload': {
                                    'id': doc['content']['001'],
                                    'index': 'nl',
                                }
                            }

                            doc['content']['245'][i]['suggest'] = suggest
                    except Exception as err:
                        self.logger.warn(err)
                        continue
                    output.write(json.dumps(doc))
                    output.write('\n')

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='ldj'))

class NLIndex(NLTask, CopyToIndex):
    date = ClosestDateParameter(default=datetime.date.today())

    index = 'nl'
    doc_type = 'title'
    purge_existing_index = True

    settings = {
        "settings": {
            "number_of_shards": 5,
            "analysis": {
                "filter": {
                    "autocomplete_filter": {
                        # normal ngram vs edge?
                        "type":     "edge_ngram",
                        "min_gram": 1,
                        "max_gram": 20
                    }
                },
                "analyzer": {
                    "autocomplete": {
                        "type":      "custom",
                        "tokenizer": "standard",
                        "filter": [
                            # add more?
                            "lowercase",
                            "autocomplete_filter"
                        ]
                    }
                }
            }
        }
    }

    mapping = {
        'title': {
            'date_detection': False,
            '_id': {
                'path': 'content.001'
            },
            '_all': {
                'enabled': True,
                'term_vector': 'with_positions_offsets',
                'store': True
            },
            'properties': {
                'content': {
                    'properties': {
                        '245': {
                            'properties': {
                                # multifield?
                                'a': {
                                    'type': 'string',
                                    'index_analyzer': 'autocomplete',
                                    'search_analyzer': 'standard'
                                }
                            }
                        },
                        '100': {
                            'properties': {
                                'a': {
                                    'type': 'string',
                                    'index_analyzer': 'autocomplete',
                                    'search_analyzer': 'standard'
                                }
                            }
                        },
                        '700': {
                            'properties': {
                                'a': {
                                    'type': 'string',
                                    'index_analyzer': 'autocomplete',
                                    'search_analyzer': 'standard'
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    def update_id(self):
        """ This id will be a unique identifier for this indexing task."""
        return self.effective_task_id()

    def requires(self):
        return NLJsonWithSuggestions(date=self.date, kind='tit')
