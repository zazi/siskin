# coding: utf-8
# pylint: disable=F0401,C0111,W0232,E1101,E1103,C0301,C0103,W0614,W0401,E0202

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
Various utilities.
"""

from __future__ import print_function

import errno
import hashlib
import itertools
import json
import logging
import operator
import os
import random
import re
import string
import sys
import tempfile
import xml.etree.cElementTree as ET

import bs4
import requests
import six
from dateutil import relativedelta
from future import standard_library
from six import string_types

import backoff
import luigi
from siskin import __version__
from siskin.mappings import languages
from six.moves.urllib.parse import urlparse

# XXX: move to six.
standard_library.install_aliases()

logger = logging.getLogger('siskin')


class SetEncoder(json.JSONEncoder):
    """
    Helper to encode python sets into JSON lists.

    So you can write something like this:

        json.dumps({"things": set([1, 2, 3])}, cls=SetEncoder)
    """
    def default(self, obj):
        """
        Decorate call to standard implementation.
        """
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


def date_range(start_date, end_date, increment, period):
    raise NotImplementedError('use: from gluish.utils import date_range, https://git.io/fpDU1')


def iterfiles(directory='.', fun=None):
    """
    Shortcut for os.walk, yield paths below a directory, optionally filter the
    paths by function given in `fun`.
    """
    if fun is None:
        fun = lambda path: True
    for root, _, files in os.walk(directory):
        for f in files:
            path = os.path.join(root, f)
            if fun(path):
                yield path


def random_string(length=16):
    """
    Return a random string(upper and lowercase letters) of length `length`,
    defaults to 16.
    """
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def nwise(iterable, n=2):
    """
    Generalized: func: `pairwise`. Split an iterable after every `n` items.
    """
    i = iter(iterable)
    piece = tuple(itertools.islice(i, n))
    while piece:
        yield piece
        piece = tuple(itertools.islice(i, n))


def dictcheck(obj, contains=None, absent=None, ignore=None):
    """
    Check if a dictionary contains values for the keys given in `contains` and at
    the same time it does not contain values for keys, which are given in
    `absent`.

    >>> dictcheck({"name": "x"}, contains=["name"])
    True

    >>> dictcheck({"name": "x"}, contains=["name"], absent=["key"])
    True

    >>> dictcheck({"name": "x", "key": "1234"}, contains=["name"], absent=["key"])
    False

    >>> dictcheck({"key": None}, absent=["key"])
    True

    >>> dictcheck({}, absent=["key"])
    True

    This is a helper for AMSL-API cases (https://git.io/vpHgS).
    """
    if not isinstance(obj, dict):
        raise ValueError('dictionary only')
    if contains is None:
        contains = []
    if absent is None:
        absent = []
    if ignore is None:
        ignore = []

    for key in contains:
        if key in ignore:
            continue
        if key not in obj:
            return False
        if not bool(operator.itemgetter(key)(obj)):
            return False

    for key in absent:
        if key in ignore:
            continue
        if key not in obj:
            continue
        if bool(operator.itemgetter(key)(obj)):
            return False

    return True


def get_task_import_cache():
    """
    Load or create `taskname: modulename` mappings. Return a tuple containing
    the dictionary and the path to the cache file.

    The command line entry points (e.g. taskdo and friends) need to import all
    modules in order to find a task. The import process actually takes a while
    (few seconds), so the import cache shortens the startup time of the command
    line tools by only importing the module the given task is in.

    It is save to remove the file returned by `taskimportcache` at any time.
    """
    task_import_cache = None
    path = os.path.join(tempfile.gettempdir(), 'siskin_task_import_cache_%s' % __version__)
    if not os.path.exists(path):
        logger.debug("creating task import cache at %s", path)
        from siskin.cacheutils import _write_task_import_cache
        _write_task_import_cache(path)

    with open(path) as handle:
        try:
            task_import_cache = json.load(handle)
        except Exception as err:
            print("failed to load task import cache, remove %s, then try again" % path, file=sys.stderr)
            sys.exit(1)

    return task_import_cache, path


def load_set(obj, func=lambda v: v):
    """
    Load a set from a filename, file-like object or a luigi.LocalTarget.
    """
    s = set()

    if isinstance(obj, luigi.LocalTarget):
        with obj.open() as handle:
            for line in (line.strip() for line in handle):
                if not line:
                    continue
                s.add(func(line))
    elif isinstance(obj, string_types):
        with open(obj) as handle:
            for line in (line.strip() for line in handle):
                if not line:
                    continue
                s.add(func(line))
    else:
        for line in (line.strip() for line in obj):
            if not line:
                continue
            s.add(func(line))

    return s


def load_set_from_target(target, func=lambda v: v):
    """
    Deprecated. Use load_set instead. Given a luigi.LocalTarget, load each line
    of the file into a set.
    """
    return load_set(target, func=func)


def load_set_from_file(filename, func=lambda v: v):
    """
    Deprecated. Use load_set instead. Given a filename, load each non-empty line into a set.
    """
    return load_set(filename, func=func)


class URLCache(object):
    """
    A simple URL content cache. Stores everything on the filesystem. Content is
    first written to a temporary file and then renamed. With concurrent
    requests for the same URL, the last one wins (LOW). Raises exception on any
    HTTP status >= 400. Retries supported.

    It is not very efficient, as it creates lots of directories.
    > 396140 directories, 334024 files ... ...

    To clean the cache just remove the cache directory.

    >>> cache = URLCache()
    >>> cache.get_cache_file("https://www.google.com")
    /tmp/ef/7e/fc/ef7efc9839c3ee036f023e9635bc3b056d6ee2d

    >>> cache.is_cached("https://www.google.com")
    False

    >>> page = cache.get("https://www.google.com")
    >>> page[:15]
    '<!doctype html>'

    >>> cache.is_cached("https://www.google.com")
    True

    It is possible to force a download, too:

    >>> page = cache.get("https://www.google.com", force=True)
    """
    def __init__(self, directory=None, max_tries=12):
        """
        If `directory` is not explictly given, all files will be stored under
        the temporary directory. Requests can be retried, if they resulted in
        a non 200 HTTP status code. A server might send a HTTP 500 (Internal
        Server Error), even if it really is a HTTP 503 (Service Unavailable).
        We therefore treat HTTP 500 errors as something to retry on,
        at most `max_tries` times.
        """
        self.directory = directory or tempfile.gettempdir()
        self.sess = requests.session()
        self.max_tries = max_tries

    def get_cache_file(self, url):
        """
        Return the cache file path for a URL. This will - as a side effect -
        create the parent directories, if necessary.
        """
        digest = hashlib.sha1(six.b(url)).hexdigest()
        d0, d1, d2 = digest[:2], digest[2:4], digest[4:6]
        path = os.path.join(self.directory, d0, d1, d2)

        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError as e:
                if e.errno == errno.EEXIST:
                    pass
                else:
                    raise
        return os.path.join(path, digest)

    def is_cached(self, url):
        return os.path.exists(self.get_cache_file(url))

    def get(self, url, force=False):
        """
        Return URL, either from cache or the web.
        """
        @backoff.on_exception(backoff.expo, RuntimeError, max_tries=self.max_tries)
        def fetch(url):
            """
            Nested function, so we can configure number of retries.
            """
            r = self.sess.get(url, timeout=600)
            if r.status_code >= 400:
                raise RuntimeError('%s on %s' % (r.status_code, url))
            with tempfile.NamedTemporaryFile(delete=False) as output:
                output.write(r.text.encode('utf-8'))
            os.rename(output.name, self.get_cache_file(url))

        if not self.is_cached(url) or force is True:
            fetch(url)

        with open(self.get_cache_file(url)) as handle:
            return handle.read()


def scrape_html_listing(url, with_head=False):
    """
    Given a URL to a webpage containing a simple (Apache) file listing, try to
    return a list of links to the files on the page.

    >>> scrape_html_listing("http://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.08.01/")
    ['https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.04.01/archlinux-2019.08.01-x86_64.iso',
     'https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.04.01/archlinux-2019.08.01-x86_64.iso.sig',
     'https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.04.01/archlinux-2019.08.01-x86_64.iso.torr',
     'https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.04.01/archlinux-bootstrap-2019.08.01-x86_64.tar.gz',
     'https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.04.01/archlinux-bootstrap-2019.08.01-x86_64.tar.gz.sig',
     'https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.08.01/md5sums.txt',
     'https://ftp.halifax.rwth-aachen.de/archlinux/iso/2019.08.01/sha1sums.txt']

    Will fail if the request fails. If parsing fails, return an empty list.
    Optionally, only include links in the list which return something ok on
    HTTP HEAD (might take a while).
    """
    filelike_p = re.compile(r"[0-9-_\w.]*[.][a-z0-9]{2,4}")

    # Find base url to prepend on relative links.
    pr = urlparse(url)
    pr = pr._replace(path=os.path.dirname(pr.path))
    pr = pr._replace(params="")
    pr = pr._replace(query="")
    pr = pr._replace(fragment="")
    baseurl = pr.geturl()

    r = requests.get(url)
    if r.status_code >= 400:
        raise RuntimeError("fetch failed with %s: %s", r.status_code, url)

    soup = bs4.BeautifulSoup(r.text, features="lxml")
    links = set()

    for a in soup.find_all("a"):
        match = filelike_p.search(a.get("href"))
        if not match:
            continue

        # This might be an absolute link or just a filename.
        link = match.group()
        if not link.startswith("http") and not link.startswith("/"):
            link = os.path.join(baseurl, link)
        if not with_head or requests.head(link).status_code < 400:
            links.add(link)

    return sorted(links)


def compare_files(a, b):
    """
    Compare two paths by sha1 checksum. Returns True, if files are
    byte-identical.
    """
    with open(a) as fa:
        chka = hashlib.sha1()
        while True:
            data = fa.read(4096)
            if not data:
                break
            chka.update(data)

    with open(b) as fb:
        chkb = hashlib.sha1()
        while True:
            data = fb.read(4096)
            if not data:
                break
            chkb.update(data)

    return chka.hexdigest() == chkb.hexdigest()


def xmlstream(filename, tag):
    """
    Given a path to an XML file and a tag name (without namespace), stream
    through the XML, and emit the element denoted by tag for processing, e.g.
    via xmltodict, more convenient DOM parser or something else.

        for snippet in xmlstream("sample.xml", "sometag"):
            print(len(snippet))

    """
    def strip_ns(tag):
        if not '}' in tag:
            return tag
        return tag.split('}')[1]

    # https://stackoverflow.com/a/13261805, http://effbot.org/elementtree/iterparse.htm
    context = iter(ET.iterparse(filename, events=(
        'start',
        'end',
    )))
    _, root = next(context)

    for event, elem in context:
        if not strip_ns(elem.tag) == tag or event == 'start':
            continue

        yield ET.tostring(elem)
        root.clear()


def marc_clean_subfields(field, inplace=True):
    """
    Given a pymarc.field.Field, return a list of subfields, without empty
    values or perform modification in place.
    """
    cleaned_subfields = []
    it = iter(field.subfields)
    for code, value in zip(it, it):
        if not value:
            continue
        cleaned_subfields.append(code)
        cleaned_subfields.append(value)
    if inplace:
        field.subfields = cleaned_subfields
    else:
        return cleaned_subfields


def marc_clean_record(record):
    """
    Modifies record to get rid of possible edge cases regarding empty subfield
    values. Works in-place.
    """
    for field in record.fields:
        if field.tag.startswith('00'):
            continue
        marc_clean_subfields(field, inplace=True)


def marc_build_imprint(place="", publisher="", year=""):
    """
    Takes place, publisher, year and returns imprint with delimiters as list.
    """
    if place != "" and publisher != "":
        del1 = " : "
    else:
        del1 = ""

    if (place != "" or publisher != "") and year != "":
        del2 = ", "
    else:
        del2 = ""

    return ["a", place + del1, "b", publisher + del2, "c", year]


def marc_build_field_008(year="", periodicity="", language=""):
    """
    Takes year of publication, periodicity and language and returns entire field.
    """
    if isinstance(year, six.string_types):
        match = re.search("(\d\d\d\d)", year)
        if match:
            year = match.group(1)
        else:
            year = "    "
    else:
        year = "    "

    if len(periodicity) != 1:
        periodicity = " "

    if isinstance(language, list):
        if len(language) == 0:
            language = "   "
        elif len(language) > 0 and len(language) < 3:
            language = language[0]
        else:
            language = "mul"

    if language and isinstance(language, six.string_types):
        if len(language) != 3:
            lang = language.lower()
            language = languages.get(lang, "   ")
            if language == "   ":
                print("Die Sprache '%s' ist in der Mapping-Tabelle nicht enthalten." % lang, file=sys.stderr)
    else:
        language = "   "

    return 7 * ' ' + year + 10 * ' ' + periodicity + 13 * ' ' + language + 2 * ' '


def check_isbn(isbn=""):
    """
    Check and clean ISBN.
    """
    isbn = isbn.strip()
    isbn = isbn.replace(" ", "-")
    isbn = isbn.replace(".", "-")
    match1 = re.search("(\d[0-9xX-]{16,16})", isbn)
    match2 = re.search("(\d[0-9xX-]{12,12})", isbn)
    match3 = re.search("(\d[0-9xX]{9,9})", isbn)
    match4 = re.search("(\d[0-9xX]{12,12})", isbn)

    if match1:
        return match1.group(1)
    elif match2:
        return match2.group(1)
    elif match3:
        return match3.group(1)
    elif match4:
        return match4.group(1)
    else:
        return ""


def check_issn(issn=""):
    """
    Check and clean ISSN.
    """
    issn = issn.strip()
    if len(issn) == 8:
        issn1 = issn[:4]
        issn2 = issn[4:]
        issn = issn1 + "-" + issn2
    issn = issn.replace(" ", "-")
    issn = issn.replace(".", "-")
    match = re.search("([0-9xX-]{9,9})", issn)
    if match:
        return match.group(1)
    return ""
