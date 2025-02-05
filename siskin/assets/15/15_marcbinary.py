#!/usr/bin/env python
# coding: utf-8
# pylint: disable=C0103,C0301
"""
Custom conversion for IMSLP XML. Usually a set of files within a given
directory, refs #1240.

Usage:

    $ python 15_marcbinary.py [INPUT-DIRECTORY [, OUTPUT-FILE [, FIELDMAP]]

"""

from __future__ import print_function

import collections
import io
import json
import os
import re
import sys
from xml.sax.saxutils import escape, unescape

import xmltodict

import marcx
from siskin.mappings import formats

langmap = {
    "Ancient Greek": "grc",
    "Armenian": "arm",
    "Catalan": "cat",
    "Catalàn": "cat",
    "Church Slavonic": "chu",
    "Croatian": "hrv",
    "Czech": "cze",
    "Danish": "dan",
    "Deutsch": "ger",
    "Dutch": "dut",
    "English": "eng",
    "Esperanto": "epo",
    "Finnish": "fin",
    "Français": "fre",
    "french": "fre",
    "French": "fre",
    "German": "ger",
    "german": "ger",
    "Greek": "ell",
    "Hebrew": "heb",
    "Hungarian": "hun",
    "Icelandic": "ice",
    "Irish": "gle",
    "Italian": "ita",
    "italian": "ita",
    "Italiano": "ita",
    "Italien": "ita",
    "Japanese": "jpn",
    "Latein": "lat",
    "Latin": "lat",
    "latin": "lat",
    "Middle French": "frm",
    "Neapolitan": "nap",
    "Norwegian": "nor",
    "Polish": "pol",
    "Portuguese": "por",
    "Romanian": "rom",
    "Russian": "rus",
    "Serbian (Cyrillic)": "srp",
    "Serbian": "srp",
    "Spanish": "spa",
    "Swedish": "swe",
    "Telugu": "tel",
    "Turkish": "tur",
    "Ukrainian": "ukr",
    "Welsh": "wel",
    "Yiddish": "yid",
}

html_escape_table = {'"': "&quot;", "'": "&apos;"}
html_unescape_table = {v: k for k, v in html_escape_table.items()}


def html_escape(text):
    """ Escape HTML, see also: https://wiki.python.org/moin/EscapingHtml"""
    return escape(text, html_escape_table)


def html_unescape(text):
    """ Unescape HTML, see also: https://wiki.python.org/moin/EscapingHtml"""
    return unescape(text, html_unescape_table)


def get_field(tag):
    try:
        return record[tag]
    except:
        return ""


if len(sys.argv) < 4:
    # Means: no fieldmap file provided.
    input_directory = "IMSLP_alt"

    fieldmap = collections.defaultdict(dict)

    for root, _, files in os.walk(input_directory):
        for filename in files:
            if not filename.endswith(".xml"):
                continue
            filepath = os.path.join(root, filename)
            inputfile = io.open(filepath, "r", encoding="utf-8")

            title = False
            f001 = ""
            f1000 = ""
            f245a = ""

            for line in inputfile:

                regexp = re.search("<recordId>(.*)<\/recordId>", line)
                if regexp:
                    f001 = regexp.group(1)
                    fieldmap[f001]["title"] = f245a
                    continue

                # Deutscher Werktitel
                if title:
                    regexp = re.search(r"<string>(.*)<\/string>", line)
                    if regexp:
                        f245a = regexp.group(1)
                        f245a = html_unescape(f245a)

                regexp = re.search(r"name=\"worktitle\"", line)
                title = True if regexp else False

                # VIAF
                regexp = re.search(r"<viafId>(\d+)</viafId>", line)  # Feld manchmal vorhanden, aber leer
                if regexp:
                    f1000 = regexp.group(1)
                    f1000 = "(VIAF)" + f1000
                    fieldmap[f001]["viaf"] = f1000

        inputfile.close()

    with open("15_fieldmap.json", "w") as output:
        json.dump(fieldmap, output)

input_directory = "IMSLP_neu"
output_filename = "15_output.mrc"

if len(sys.argv) > 1:
    input_directory = sys.argv[1]
if len(sys.argv) > 2:
    output_filename = sys.argv[2]
if len(sys.argv) > 3:
    with open(sys.argv[3]) as handle:
        fieldmap = json.load(handle)

outputfile = io.open(output_filename, "wb")

failed = 0

for root, _, files in os.walk(input_directory):
    for filename in files:
        if not filename.endswith(".xml"):
            continue
        filepath = os.path.join(root, filename)
        inputfile = io.open(filepath, "r", encoding="utf-8")

        f650a = []

        record = xmltodict.parse(inputfile.read())
        record = record["document"]

        try:
            title = record["title"]
            #title = record["subject"]
        except:
            continue

        marcrecord = marcx.Record(force_utf8=True)
        marcrecord.strict = False

        format = "Score"

        # Leader
        leader = formats[format]["Leader"]
        marcrecord.leader = leader

        # Identifikator
        f001 = record["identifier"]["#text"]
        marcrecord.add("001", data="finc-15-%s" % f001)

        # Zugangsart
        f007 = formats[format]["e007"]
        marcrecord.add("007", data=f007)

        # Sprache
        # besser: aus vifaxml parsen!!
        f041a = get_field("languages")
        marcrecord.add("008", data="130227uu20uuuuuuxx uuup%s  c" % f041a)
        marcrecord.add("041", a=f041a)

        # Komponist
        f100a = record["creator"]["mainForm"]
        f1000 = fieldmap.get(f001, {}).get("viaf", "")
        marcrecord.add("100", a=f100a, e="cmp", _0=f1000)

        # Werktitel
        f240a = fieldmap.get(f001, {}).get("title", "")
        marcrecord.add("240", a=f240a)

        # Sachtitel
        f245a = record["title"]
        f245a = html_unescape(f245a)
        marcrecord.add("245", a=f245a)

        # Alternativtitel
        f246a = get_field("additionalTitle")
        f246a = html_unescape(f246a)
        marcrecord.add("246", a=f246a)

        # RDA-Inhaltstyp
        f336b = formats[format]["336b"]
        marcrecord.add("336", b=f336b)

        # RDA-Datenträgertyp
        f338b = formats[format]["338b"]
        marcrecord.add("338", b=f338b)

        # Erscheinungsjahr
        # nicht mehr enthalten

        # Kompositionsjahr
        year = get_field("date")
        marcrecord.add("260", c=year)
        marcrecord.add("650", y=year)

        # Fußnote
        f500a = get_field("abstract")
        if len(f500a) > 8000:
            f500a = f500a[:8000]
        marcrecord.add("500", a=f500a)

        # Stil / Epoche
        try:
            subject = record["subject"]
        except:
            subject = ""
        if subject != "":
            if isinstance(subject, list):
                # [OrderedDict([('mainForm', 'Piano piece')]), OrderedDict([('mainForm', 'Romantic')])]
                style = subject[0]["mainForm"]
                style = style.title()
                epoch = subject[1]["mainForm"]  # Martin fragen, wegen "TypeError: string indices must be integers"
                epoch = epoch.title()
            else:
                epoch = record["subject"]["mainForm"]
                epoch = epoch.title()
            f650a.append(epoch)
            f590a = epoch

        # Besetzung
        instrumentation = get_field("music_arrangement_of")
        instrumentation = instrumentation.title()
        f650a.append(instrumentation)
        f590b = instrumentation
        marcrecord.add("590", subfields=["a", f590a, "b", f590b])

        # GND-Inhalts- und Datenträgertyp
        f655a = formats[format]["655a"]
        f6552 = formats[format]["6552"]
        marcrecord.add("338", a=f655a, _2=f6552)

        # Schlagwörter
        subtest = []
        for subject in f650a:
            subject = subject.title()
            if subject not in subtest:
                subtest.append(subject)
                marcrecord.add("689", a=subject)

        # Beitragende
        try:
            f700a = record["contributor"]["mainForm"]
            marcrecord.add("700", a=f700a, e="ctb")
        except:
            pass

        # URL
        f856u = record["url"]["#text"]
        marcrecord.add("856", q="text/html", _3="Petrucci Musikbibliothek", u=f856u)

        # SWB-Inhaltstyp
        f935c = formats[format]["935c"]
        marcrecord.add("935", c=f935c)

        marcrecord.add("970", c="PN")

        marcrecord.add("980", a=f001, b="15", c="sid-15-col-imslp")

        outputfile.write(marcrecord.as_marc())

        inputfile.close()

outputfile.close()
