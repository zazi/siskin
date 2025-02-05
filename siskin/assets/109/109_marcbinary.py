#!/usr/bin/env python3
# coding: utf-8

# SID: 109
# Collection: Kunsthochschule für Medien Köln (VK Film)
# Ticket: #8391
# technicalCollectionID: sid-109-col-kunsthochschulekoeln
# Task: khm.py
"""
Review notes:

* get_datafield depends on a name in module scope, brittle
* get_field_* might be a single function
* format = str(format), seems format can be a list, too
* format, large if/else
"""

from __future__ import print_function

import re
import sys

import xmltodict

import marcx
from siskin.utils import marc_build_imprint, xmlstream

formatmap = {
    "Buch": {
        "leader": "cam",
        "007": "tu",
        "935b": "druck"
    },
    u"Mehrbänder": {
        "007": "tu",
        "935b": "druck"
    },
    "DVD": {
        "leader": "ngm",
        "007": "vd",
        "935b": "dvdv",
        "935c": "vide"
    },
    "Blu-ray": {
        "leader": "ngm",
        "007": "vd",
        "935b": "bray",
        "935c": "vide"
    },
    "Videodatei": {
        "leader": "cam",
        "007": "cr",
        "935b": "cofz",
        "935c": "vide"
    },
    "CD": {
        "leader": "  m",
        "007": "c",
        "935b": "cdda"
    },
    "Videokassette": {
        "leader": "cgm",
        "007": "vf",
        "935b": "vika",
        "935c": "vide"
    },
    "Noten": {
        "leader": "nom",
        "007": "zm",
        "935c": "muno"
    },
    "Loseblattsammlung": {
        "leader": "nai",
        "007": "td",
    },
    "Film": {
        "leader": "cam",
        "007": "mu",
        "935b": "sobildtt"
    },
    "Aufsatz": {
        "leader": "naa",
        "007": "tu"
    },
    "Objekt": {
        "leader": "crm",
        "007": "zz",
        "935b": "gegenst"
    },
    "Zeitschrift": {
        "leader": "nas",
        "007": "tu",
        "008": "                     p"
    },
    "Sonstiges": {
        "leader": "npa",
        "007": "tu"
    }
}


def get_datafield(record, tag, code, all=False):
    """
    Return string value for (record, tag, code) or list of values if all is True.
    """
    values = []
    for field in record["ns0:record"]["ns0:datafield"]:
        if field["@tag"] != tag:
            continue
        if isinstance(field["ns0:subfield"], list):
            for subfield in field["ns0:subfield"]:
                if subfield["@code"] != code:
                    continue
                if not all:
                    return subfield["#text"]
                values.append(subfield["#text"])
        else:
            if field["ns0:subfield"]["@code"] == code:
                if not all:
                    return field["ns0:subfield"]["#text"]
                values.append(field["ns0:subfield"]["#text"])
    return values


def get_leader(format="Buch"):
    if format == u"Mehrbänder":
        return "     cam  22       a4500"
    return "     %s  22        4500" % formatmap[format]["leader"]


def get_field_007(format="Buch"):
    return formatmap[format]["007"]


def get_field_008(format="Zeitschrift"):
    if "008" not in formatmap[format]:
        return ""
    return formatmap[format]["008"]


def get_field_935b(format="Buch"):
    if "935b" not in formatmap[format]:
        return ""
    return formatmap[format]["935b"]


def get_field_935c(format="Buch"):
    if "935c" not in formatmap[format]:
        return ""
    return formatmap[format]["935c"]


def remove_brackets(field):
    if isinstance(field, list) and len(field) == 0:
        return ""
    return field.replace("<<", "").replace(">>", "")


inputfilename = "109_input.xml"
outputfilename = "109_output.mrc"

if len(sys.argv) == 3:
    inputfilename, outputfilename = sys.argv[1:]

outputfile = open(outputfilename, "wb")

parent_ids = []
parent_titles = {}

for oldrecord in xmlstream(inputfilename, "record"):

    record = xmltodict.parse(oldrecord)
    parent_id = get_datafield(record, "010", "a")

    if len(parent_id) > 0:
        parent_ids.append(parent_id)

for oldrecord in xmlstream(inputfilename, "record"):

    record = xmltodict.parse(oldrecord)
    id = get_datafield(record, "001", "a")
    title = get_datafield(record, "331", "a")

    if id in parent_ids:
        parent_titles[id] = title

for oldrecord in xmlstream(inputfilename, "record"):

    record = xmltodict.parse(oldrecord)
    marcrecord = marcx.Record(force_utf8=True)
    marcrecord.strict = False

    id = get_datafield(record, "001", "a")
    parent_id = get_datafield(record, "010", "a")
    title = get_datafield(record, "331", "a")

    if "Brockhaus" in title or len(title) == 0:
        continue

    f245a = title
    f245p = ""
    f773w = ""

    if len(parent_id) > 0:
        has_parent_title = parent_titles.get(parent_id, None)
        if has_parent_title:
            f245a = parent_titles[parent_id]
            f245p = title
            f773w = "(DE-576)" + parent_id

    # Format
    format = get_datafield(record, "433", "a")
    format = u'%s' % format
    isbn = get_datafield(record, "540", "a")
    regexp = re.search("S\.\s\d+\s?-\s?\d+", format)

    if id in parent_ids:
        format = u"Mehrbänder"
    elif len(isbn) > 0 and "Videokassette" not in format and "VHS" not in format and "DVD" not in format:
        format = "Buch"
    elif ("S." in format or "Bl." in format or "Ill." in format or " p." in format or "XI" in format or "XV" in format
          or "X," in format or "Bde." in format or ": graph" in format):
        format = "Buch"
    elif "CD" in format:
        format = "CD"
    elif "DVD" in format:
        format = "DVD"
    elif "Blu-ray" in format:
        format = "Blu-ray"
    elif "Videokassette" in format or "VHS" in format or "Min" in format:
        format = "Videokassette"
    elif "Losebl.-Ausg." in format:
        format = "Loseblattsammlung"
    elif regexp:
        format = "Aufsatz"
    elif ("Plakat" in format or "Kassette" in format or "Box" in format or "Karton" in format or "Postkarten" in format
          or "Teile" in format or "USB" in format or "Schachtel" in format or "Schautafel" in format
          or "Medienkombination" in format or "Tafel" in format or "Faltbl" in format or "Schuber" in format):
        format = "Objekt"
    elif id in parent_ids and len(isbn) == 0:  # Zeitschrift
        continue
    else:
        format = "Buch"

    # Leader
    leader = get_leader(format=format)
    marcrecord.leader = leader

    # Identifier
    f001 = get_datafield(record, "001", "a")
    marcrecord.add("001", data="finc-109-" + f001)

    # 007
    f007 = get_field_007(format=format)
    marcrecord.add("007", data=f007)

    # 008
    f008 = get_field_008(format=format)
    marcrecord.add("008", data=f008)

    # ISBN
    f020a = get_datafield(record, "540", "a")
    marcrecord.add("020", a=f020a)
    f020a = get_datafield(record, "570", "a")
    marcrecord.add("020", a=f020a)

    # Sprache
    f041a = get_datafield(record, "037", "a")
    marcrecord.add("041", a=f041a)

    # 1. Urheber
    f100a = get_datafield(record, "100", "a")
    f100a = remove_brackets(f100a)
    marcrecord.add("100", a=f100a)

    # Haupttitel & Verantwortlichenangabe
    f245a = remove_brackets(f245a)
    f245c = get_datafield(record, "359", "a")
    f245p = remove_brackets(f245p)
    f245 = ["a", f245a, "c", f245c, "p", f245p]
    marcrecord.add("245", subfields=f245)

    # Erscheinungsvermerk
    f260a = get_datafield(record, "410", "a")
    if isinstance(f260a, list):
        f260a = ""
    f260b = get_datafield(record, "412", "a")
    if isinstance(f260b, list):
        f260b = ""
    f260b = remove_brackets(f260b)
    f260c = get_datafield(record, "425", "a")
    if isinstance(f260c, list):
        f260c = ""
    subfields = marc_build_imprint(f260a, f260b, f260c)
    marcrecord.add("260", subfields=subfields)

    # Umfangsangabe
    f300a = get_datafield(record, "433", "a")
    f300a = remove_brackets(f300a)
    f300b = get_datafield(record, "434", "a")
    f300 = ["a", f300a, "b", f300b]
    marcrecord.add("300", subfields=f300)

    f490 = get_datafield(record, "451", "a")
    if len(f490) > 0:
        f490 = f490.split(" ; ")
        if len(f490) == 2:
            f490a = f490[0]
            f490v = f490[1]
        else:
            f490a = f490
            f490v = ""
        marcrecord.add("490", a=f490a, v=f490v)

    for f650a in set(get_datafield(record, "710", "a", all=True)):
        f650a = remove_brackets(f650a)
        marcrecord.add("650", a=f650a)

    for f650a in set(get_datafield(record, "711", "a", all=True)):
        f650a = remove_brackets(f650a)
        marcrecord.add("650", a=f650a)

    # weitere Urheber
    for tag in range(101, 200):
        f700a = get_datafield(record, str(tag), "a")
        f700a = remove_brackets(f700a)
        marcrecord.add("700", a=f700a)

    # weitere Körperschaften
    for tag in range(200, 300):
        f710a = get_datafield(record, str(tag), "a")
        f710a = remove_brackets(f710a)
        marcrecord.add("710", a=f710a)

    # übergeordnetes Werk
    marcrecord.add("773", w=f773w)

    # Links
    f856u = get_datafield(record, "655", "u")
    f8563 = get_datafield(record, "655", "x")
    if len(f8563) == 0:
        f8563 = u"zusätzliche Informationen"
    if "http" in f856u:
        marcrecord.add("856", q="text/html", _3=f8563, u=f856u)

    # Format
    f935b = get_field_935b(format=format)
    f935c = get_field_935c(format=format)
    marcrecord.add("935", b=f935b, c=f935c)

    # Kollektion
    collection = ["a", f001, "b", "109", "c", "sid-109-col-kunsthochschulekoeln"]
    marcrecord.add("980", subfields=collection)

    try:
        outputfile.write(marcrecord.as_marc())
    except UnicodeEncodeError as exc:
        print("%s: %s" % (marcrecord["001"], exc), file=sys.stderr)

outputfile.close()
