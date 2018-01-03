# coding: utf-8
# pylint: disable=F0401,C0111,W0232,E1101,R0904,E1103,C0301

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
VKFilm Bundesarchiv, #8695.

TODO: Unify VKFilm* tasks.

Config
------

[vkfilmba]

baseurl = https://example.com

"""

import datetime
import hashlib
import os
import tempfile

import luigi

from gluish.format import TSV
from gluish.parameter import ClosestDateParameter
from gluish.utils import shellout
from siskin.common import FTPMirror
from siskin.task import DefaultTask


class VKFilmBATask(DefaultTask):
    TAG = '148'

    # As this is a manual process, adjust this list by hand and rerun tasks.
    filenames = [
        "adlr.zip",
        "adlr_171011.zip",
        "adlr_1712.zip",
    ]

    def fingerprint(self):
        """
        Generate a name based on the inputs, so everytime we adjust the file
        list, we get another output.
        """
        h = hashlib.sha1()
        h.update("".join(self.filenames).encode("utf-8"))
        return h.hexdigest()


class VKFilmBADump(VKFilmBATask):
    """
    Concatenate a list of URLs.

    XXX: There is a "delete-list" of ID, which should be filtered here.
    """

    def run(self):
        _, stopover = tempfile.mkstemp(prefix='siskin-')
        for fn in self.filenames:
            link = os.path.join(self.config.get("vkfilmba", "baseurl"), fn)
            output = shellout("""wget -O {output} "{link}" """, link=link)
            output = shellout(""" unzip -p "{input}" > "{output}" """,
                              input=output)
            output = shellout("""yaz-marcdump -i marcxml -o marc "{input}" > "{output}"  """,
                              input=output, ignoremap={5: "Fixme."})
            shellout("""cat "{input}" >> "{stopover}" """,
                     input=output, stopover=stopover)
        luigi.LocalTarget(stopover).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(filename="%s.mrc" % self.fingerprint()))


class VKFilmBAMARC(VKFilmBATask):
    """
    Run conversion script.
    """

    def requires(self):
        return VKFilmBADump()

    def run(self):
        output = shellout("python {script} {input} {output}",
                          script=self.assets("148/148_marcbinary.py"),
                          input=self.input().path)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(filename="%s.mrc" % self.fingerprint()))
