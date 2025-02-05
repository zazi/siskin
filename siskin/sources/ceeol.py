# coding: utf-8
# pylint: disable=C0301,E1101

# Copyright 2017 by Leipzig University Library, http://ub.uni-leipzig.de
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
https://www.ceeol.com/, refs #9398.

Currently, there are two XML formats used, a custom CEEOL XML and a slightly
invalid MARCXML. The last update was manually uploaded to a colorful server
@Telekom.

Config:

[ceeol]

disk-dir = /path/to/disk
updates = /path/to/file.xml, /path/to/another.xml, ...
updates-marc = /path/to/file.xml, /path/to/file.xml

"""

from __future__ import print_function

import glob
import hashlib
import json
import os
import re
import sys
import tempfile

import luigi
import marcx
import pymarc
from gluish.utils import shellout
from siskin.task import DefaultTask


class CeeolTask(DefaultTask):
    """
    Base task.
    """
    TAG = '53'

    def updateid(self):
        """
        Only use the string of files as hashed identifier. TODO(miku): It would
        be more robust to use the checksums of all input files.
        """
        sha1 = hashlib.sha1()
        sha1.update(self.config.get("ceeol", "updates").encode('utf-8'))
        sha1.update(self.config.get("ceeol", "updates-marc").encode('utf-8'))
        return sha1.hexdigest()


class CeeolJournalsUpdates(CeeolTask):
    """
    Create an intermediate schema from zero or more update XML (in MARCXML).
    The output will depend on the set and order of the input files.
    """
    def run(self):
        paths = [p.strip() for p in self.config.get("ceeol", "updates").split(",") if p.strip()]
        _, stopover = tempfile.mkstemp(prefix="siskin-")
        self.logger.debug("found %d updates", len(paths))
        for p in paths:
            shellout("span-import -i ceeol-marcxml {input} >> {output}", input=p, output=stopover)

        # Append MARC updates.
        paths = [p.strip() for p in self.config.get("ceeol", "updates-marc").split(",") if p.strip()]
        _, stopover = tempfile.mkstemp(prefix="siskin-")
        self.logger.debug("found %d updates (MARC)", len(paths))
        with open(stopover, 'a') as output:
            for p in paths:
                self.logger.debug("converting: %s", p)
                for doc in convert_ceeol_to_intermediate_schema(p):
                    output.write(json.dumps(doc) + "\n")
        luigi.LocalTarget(stopover).move(self.output().path)

    def output(self):
        filename = "{}.ndj".format(self.updateid())
        return luigi.LocalTarget(path=self.path(filename=filename))


class CeeolJournalsIntermediateSchema(CeeolTask):
    """
    Combine all journals from disk dump and convert them to intermediate
    schema. Add updates. The output name of this task depends on the update id.

    This task depends on a fixed subdirectory, e.g. articles or 1Journal-Articles-XML..
    """
    def requires(self):
        return CeeolJournalsUpdates()

    def run(self):
        diskdir = self.config.get('ceeol', 'disk-dir')
        _, stopover = tempfile.mkstemp(prefix='siskin-')
        for path in glob.glob(os.path.join(diskdir, 'articles', 'articles_*xml')):
            shellout("span-import -i ceeol {input} | pigz -c >> {output}", input=path, output=stopover)
        shellout("cat {update} | pigz -c >> {output}", update=self.input().path, output=stopover)
        luigi.LocalTarget(stopover).move(self.output().path)

    def output(self):
        filename = "{}.ldj.gz".format(self.updateid())
        return luigi.LocalTarget(path=self.path(filename=filename))


# Helper for MARC, XXX: maybe move this out.

_362a_pattern = re.compile(r"vol[.]?[ ]*([0-9]+)?,[ ]*no[.][ ]*([0-9]+)[ ]*\(([0-9]+)\)-?", re.IGNORECASE)


def format_date(value, iso=False):
    """
    Try to get a suitable date out of the value.
    """
    if len(value) == 4 and value.isnumeric():
        if iso:
            return "{}-01-01T00:00:00Z".format(value)
        else:
            return "{}-01-01".format(value)

    raise ValueError("could not handle: %s", value)


def clean_260a(value):
    """
    Strip place value.
    """
    return value.replace("[1] :", "").strip()


def parse_volume_from_362a(value, default=None):
    """
    Try to parse volume from 362a.

    Example value: Vol. 1, no. 113 (2006)-
    """
    if value is None:
        return default
    match = _362a_pattern.search(value)
    if not match:
        return default
    return match.group(1).strip() if match.group(1) else default


def parse_issue_from_362a(value, default=None):
    """
    Try to parse volume from 362a.

    Example value: Vol. 1, no. 113 (2006)-
    """
    if value is None:
        return default
    match = _362a_pattern.search(value)
    if not match:
        return default
    return match.group(2).strip() if match.group(1) else default


def convert_ceeol_to_intermediate_schema(filename):
    """
    Given an XML filename, convert data to intermediate schema. Note: The XML
    refers to the partially broken XML supplied as of 07/2019.

    File must fit into memory.

    Yields converted dictionaries.
    """
    article_url_re = re.compile(r"https://www.ceeol.com/search/article-detail\?id=([0-9]+)")

    with open(filename) as handle:
        records = pymarc.marcxml.parse_xml_to_array(handle)
        for record in records:
            record = marcx.Record.from_record(record)

            # Try to find ID.
            for url in record.itervalues("856.u"):
                match = article_url_re.search(url)
                if not match:
                    continue
                record_id = match.group(1)
                break
            else:
                raise ValueError("missing record id")

            doc = {
                "abstract": record.firstvalue("520.a", default=""),
                "authors": [{
                    "rft.auname": v
                } for v in record.itervalues("100.a")],
                "finc.format": "ElectronicArticle",
                "finc.id": "ai-53-{}".format(record_id),
                "finc.mega_collection": ["CEEOL Central and Eastern European Online Library"],
                "finc.record_id": record_id,
                "finc.source_id": "53",
                "languages": list(record.itervalues("041.a")),
                "rft.atitle": record.firstvalue("245.a", default=""),
                "rft.date": format_date(record.firstvalue("260.c", default="")),
                "rft.genre": "article",
                "rft.issn": list(record.itervalues("022.a")),
                "rft.issue": parse_issue_from_362a(record.firstvalue("362.a", default=""), default=""),
                "rft.place": [clean_260a(v) for v in record.itervalues("260.a")],
                "rft.pub": list(record.itervalues("260.b")),
                "rft.volume": parse_volume_from_362a(record.firstvalue("362.a", default=""), default=""),
                "ris.type": "EJOUR",
                "subjects": list(record.itervalues("650.a")),
                "url": list(record.itervalues("856.u")),
                "x.date": format_date(record.firstvalue("260.c", default=""), iso=True),
            }
            yield doc
