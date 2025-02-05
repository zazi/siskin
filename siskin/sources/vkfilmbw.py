# coding: utf-8
# pylint: disable=C0103,C0411,F0401,C0111,W0232,E1101,R0904,E1103,C0301

# Copyright 2017 by Leipzig University Library, http://ub.uni-leipzig.de
#                   The Finc Authors, http://finc.info
#                   Robert Schenk, <robert.schenk@uni-leipzig.de>
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
#
"""
VKFilm (BW), #8700, about 40000 records, Alephino.

TODO: Unify VK* tasks.

Config
------

[vkfilmbw]

baseurl = http://alephino.club/x
username = ADMIN
password = SECRET
"""

from __future__ import print_function

import datetime
import io
from urllib.parse import urlencode
from xml.dom.minidom import parseString

import requests
import xmltodict

import luigi
import tqdm
from gluish.intervals import monthly
from gluish.parameter import ClosestDateParameter
from gluish.utils import shellout
from siskin.task import DefaultTask


class VKFilmBWTask(DefaultTask):
    """
    Base task for VKFilm BW.
    """
    TAG = '151'

    def closest(self):
        return monthly(date=self.date)


class VKFilmBWDownload(VKFilmBWTask):
    """
    Harvest MARCXML-ish records from Alephino.
    """

    date = ClosestDateParameter(default=datetime.date.today())

    def run(self):
        baseurl = self.config.get('vkfilmbw', 'baseurl')
        query = {
            'op': 'find',
            'base': 'B-TIT',
            'query': 'IDN=1 < *',
            'usr': self.config.get('vkfilmbw', 'username'),
            'pwd': self.config.get('vkfilmbw', 'password'),
        }
        url = "%s?%s" % (baseurl, urlencode(query))

        r = requests.get(url)
        if r.status_code != 200:
            raise RuntimeError('got HTTP %s: %s' % (r.status_code, url))

        dd = xmltodict.parse(r.text)
        set_number = int(dd["find"]["set_number"])
        no_entries = int(dd["find"]["no_entries"])

        with self.output().open('w') as output:
            output.write(u"""<?xml version="1.0" encoding="UTF-8" ?>""")
            output.write(u"<collection>")
            for no in tqdm.tqdm(range(1, no_entries + 1)):
                query = {
                    'op': 'getrec',
                    'set_number': set_number,
                    'number_entry': no,
                    'usr': self.config.get('vkfilmbw', 'username'),
                    'pwd': self.config.get('vkfilmbw', 'password'),
                }
                url = "%s?%s" % (baseurl, urlencode(query))
                resp = requests.get(url)
                if resp.status_code != 200:
                    print('failed with HTTP %s: %s' % (resp.status_code, url))
                    continue

                doc = parseString(resp.text.encode('utf-8').strip())
                document = doc.childNodes[0].childNodes[0]
                document.tagName = 'record'
                document.removeAttribute('base')
                document.removeAttribute('idn')
                output.write(document.toxml())

            output.write(u"</collection>")

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='xml'))


class VKFilmBWMARC(VKFilmBWTask):
    """ Convert to MARC binary. """

    date = ClosestDateParameter(default=datetime.date.today())

    def requires(self):
        return VKFilmBWDownload(date=self.date)

    def run(self):
        output = shellout("""python {script} {input} {output}""",
                          script=self.assets("151/151_marcbinary.py"),
                          input=self.input().path)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='fincmarc.mrc'))
