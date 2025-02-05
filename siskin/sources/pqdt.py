# coding: utf-8
# pylint: disable=F0401,C0111,W0232,E1101,R0904,E1103,C0301

# Copyright 2015 by Leipzig University Library, http://ub.uni-leipzig.de
#                   The Finc Authors, http://finc.info
#                   Martin Czygan, <martin.czygan@uni-leipzig.de>
#
# This file is part of some open source application.
#
# Some open source application is free software: you can redistribute
# it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
#
# Some open source application is distributed in the hope that it will
# be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
# @license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
"""
PQDT, http://pqdtopen.proquest.com.

Config
------

[pqdt]

oai = http://example.endpoint.com/x/y/z

"""

import datetime

import luigi
from gluish.common import Executable
from gluish.format import Gzip
from gluish.intervals import monthly
from gluish.parameter import ClosestDateParameter
from gluish.utils import shellout
from siskin.sources.amsl import AMSLFilterConfig
from siskin.task import DefaultTask


class PQDTTask(DefaultTask):
    """ PQDT open. """
    TAG = '34'

    def closest(self):
        return monthly(date=self.date)


class PQDTCombine(PQDTTask):
    """ Combine files."""

    date = ClosestDateParameter(default=datetime.date.today())
    prefix = luigi.Parameter(default="oai_dc")

    def requires(self):
        return Executable(name='metha-sync', message='https://github.com/miku/metha')

    def run(self):
        url = self.config.get('pqdt', 'oai')
        shellout("METHA_DIR={dir} metha-sync -format {prefix} {url}",
                 prefix=self.prefix,
                 url=url,
                 dir=self.config.get('core', 'metha-dir'))
        output = shellout("METHA_DIR={dir} metha-cat -root Records -format {prefix} {url} | pigz -c > {output}",
                          prefix=self.prefix,
                          url=url,
                          dir=self.config.get('core', 'metha-dir'))
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext="xml.gz"))


class PQDTIntermediateSchema(PQDTTask):
    """
    OAI to intermediate schema.
    """
    date = ClosestDateParameter(default=datetime.date.today())

    def requires(self):
        return PQDTCombine(date=self.date)

    def run(self):
        mapdir = 'file:///%s' % self.assets("maps/")
        output = shellout("""flux.sh {flux} in={input} MAP_DIR={mapdir} | pigz -c > {output}""",
                          flux=self.assets("34/flux.flux"),
                          mapdir=mapdir,
                          input=self.input().path)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='ldj.gz'), format=Gzip)


class PQDTExport(PQDTTask):
    """
    OAI to SOLR schema.
    """
    date = ClosestDateParameter(default=datetime.date.today())
    format = luigi.Parameter(default='solr5vu3')

    def requires(self):
        return {
            'file': PQDTIntermediateSchema(date=self.date),
            'config': AMSLFilterConfig(date=self.date),
        }

    def run(self):
        output = shellout(""" span-tag -c {config} {input} > {output} """,
                          config=self.input().get('config').path,
                          input=self.input().get('file').path)
        output = shellout(""" span-export -o {format} {input} > {output} """, input=output, format=self.format)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='ldj'))
