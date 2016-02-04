# coding: utf-8
#
#  Copyright 2015 by Leipzig University Library, http://ub.uni-leipzig.de
#                 by The Finc Authors, http://finc.info
#                 by Martin Czygan, <martin.czygan@uni-leipzig.de>
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
#

"""
Electronic Resource Management System Based on Linked Data Technologies.

http://amsl.technology

Config:

[amsl]

isil-rel = https://x.com/static/about.json
holdings = https://x.com/inhouseservices/list?do=holdings

"""

from gluish.utils import shellout
from siskin.configuration import Config
from siskin.task import DefaultTask
import datetime
import json
import luigi

config = Config.instance()

class AMSLTask(DefaultTask):
    TAG = 'amsl'

class AMSLCollections(AMSLTask):
    """ Get a list of ISIL, source and collection choices via JSON API. """

    date = luigi.DateParameter(default=datetime.date.today())

    def run(self):
        output = shellout("""curl --fail "{link}" > {output} """, link=config.get('amsl', 'isil-rel'))
        luigi.File(output).move(self.output().path)

    def output(self):
       return luigi.LocalTarget(path=self.path())

class AMSLHoldings(AMSLTask):
    """
    Download AMSL tasks.
    """
    date = luigi.Parameter(default=datetime.date.today())

    def run(self):
	output = shellout(""" curl --fail "{link}" > {output} """, link=config.get('amsl', 'holdings'))
	luigi.File(output).move(self.output().path)

    def output(self):
       return luigi.LocalTarget(path=self.path())

class AMSLHoldingsISILList(AMSLTask):
    """
    Return a list of ISILs that are returned by the API.
    """
    date = luigi.Parameter(default=datetime.date.today())

    def requires(self):
	return AMSLHoldings(date=self.date)

    def run(self):
	output = shellout("jq -r '.[].ISIL' {input} | sort > {output}", input=self.input().path)
	luigi.File(output).move(self.output().path)

    def output(self):
       return luigi.LocalTarget(path=self.path())

class AMSLHoldingsFile(AMSLTask):
    """
    Access AMSL files/get?setResource= facilities.
    """
    isil = luigi.Parameter(description='ISIL, case sensitive')
    date = luigi.Parameter(default=datetime.date.today())

    def requires(self):
	return AMSLHoldings(date=self.date)

    def run(self):
	with self.input().open() as handle:
	    holdings = json.load(handle)

	for holding in holdings:
	    if holding["ISIL"] == self.isil:
		link = "https://live.amsl.technology/OntoWiki/files/get?setResource=%s" % holding['DokumentURI']
		output = shellout("curl --fail {link} > {output} ", link=link)
		luigi.File(output).move(self.output().path)
		break
	else:
	    raise RuntimeError('cannot find ISIL in AMSL holdings API: %s' % self.isil)

    def output(self):
       return luigi.LocalTarget(path=self.path())
