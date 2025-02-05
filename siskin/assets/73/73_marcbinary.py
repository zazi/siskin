#!/usr/bin/env python
# coding: utf-8
"""
Notes:

* XML contains entities: "... Bedeutung und Gef&#xE4;hrdung der Sinne ..."
"""

from __future__ import print_function

import base64
import io
import re
import sys
from builtins import *

import xmltodict

import marcx

try:
    basestring
except NameError:
    basestring = str

lang_map = {"": "ger", "de": "ger", "deu": "ger"}

# Default input and output.
inputfilename = "73_input_datacite.xml"
outputfilename = "73_output.mrc"

if len(sys.argv) == 3:
    inputfilename, outputfilename = sys.argv[1:]

inputfile = io.open(inputfilename, "r", encoding='utf-8')
outputfile = io.open(outputfilename, "wb")
xmlfile = inputfile.read()
xmlrecords = xmltodict.parse(xmlfile)

for i, xmlrecord in enumerate(xmlrecords["Records"]["Record"]):
    marcrecord = marcx.Record(force_utf8=True)
    marcrecord.strict = False

    # Leader
    marcrecord.leader = "     nab  22        4500"

    # Identifier
    f001 = xmlrecord["header"]["identifier"]
    f001 = f001.encode("utf-8")
    f001 = base64.b64encode(f001)
    f001 = f001.decode("ascii").rstrip("=")
    marcrecord.add("001", data="finc-73-" + f001)

    # 007
    marcrecord.add("007", data="cr")

    # ISSN
    try:
        identifiers = xmlrecord.get("metadata", {}).get("dcite:resource",
                                                        {}).get("dcite:relatedIdentifiers",
                                                                {}).get("dcite:relatedIdentifier", [])
        for identifier in identifiers:
            if identifier["@relatedIdentifierType"] == "ISSN":
                f022a = identifier["#text"]
                marcrecord.add("022", a=f022a)
                break
    except Exception as exc:
        pass

    # Sprache
    try:
        language = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:language", "")
        f041a = lang_map.get(language, "")
        if f041a != "":
            pass
            marcrecord.add("008", data="130227uu20uuuuuuxx uuup%s  c" % f041a)
            marcrecord.add("041", a=f041a)
        else:
            print("Die Sprache %s fehlt in der Lang_Map!" % language)
    except Exception as exc:
        print('[language] %s' % exc, file=sys.stderr)

    # 1. Urheber
    try:
        f100a = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:creators",
                                                                            {}).get("dcite:creator", "")
    except Exception as exc:
        f100a = ""
        print('[100] %s' % type(f100a))
    if isinstance(f100a, list):
        f100a = f100a[0]
    elif isinstance(f100a, dict):
        f100a = f100a["dcite:creatorName"]["#text"]
    elif isinstance(f100a, str):
        print(f100a)
    marcrecord.add("100", a=f100a)

    # Haupttitel, Titelzusatz, Verantwortlichenangabe
    try:
        f245 = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:titles", {}).get("dcite:title", "")

        if "MEDIENwissenschaft: Rezensionen | Reviews" in f245:  # überspringt Gesamtaufnahmen der Zeitschriftehefte
            continue

        if not isinstance(f245, basestring):
            print("245 is not a string: %s (%s)" % (f245, type(f245)), file=sys.stderr)
            continue

        f245 = f245.split(":")
        f245a = f245[0]
        f245a = f245a.strip(" ")
        if len(f245) > 1:
            f245a += " - " + f245[1].strip(" ")
        if len(f245) > 2:
            f245b = ""
            for titlepart in f245[2:]:
                titlepart = titlepart.strip(" ")
                f245b += titlepart + " : "
        else:
            f245b = ""
        marcrecord.add("245", a=f245a, b=f245b.rstrip(" : "))
    except Exception as exc:
        print("[245] %s: %s" % (f245, exc), file=sys.stderr)
        continue

    # Erscheinungsvermerk
    f260c = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:publicationYear", "")
    publisher = ["a", "Marburg", "b", " : " + u"Schüren Verlag, ", "c", f260c]
    marcrecord.add("260", subfields=publisher)

    # Rechtehinweis
    try:
        f500a = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:rightsList", "")
        if f500a:
            f500a = f500a.get("dcite:rights")
            f500a = f500a[0]
            marcrecord.add("500", a=f500a)
    except Exception as exc:
        print('[500]', file=sys.stderr)
        raise

    # Schlagwort
    try:
        f650a = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:subjects", [])
        if f650a:
            f650a = f650a.get("dcite:subject")
            if isinstance(f650a, list):
                for subject in f650a:
                    if subject:
                        marcrecord.add("650", a=subject)
            else:
                marcrecord.add("650", a=f650a)
    except Exception as exc:
        print('[650]', file=sys.stderr)
        raise

    # übergeordnete Ressource
    f773g = xmlrecord.get("metadata", {}).get("dcite:resource", {}).get("dcite:publicationYear", "")
    marcrecord.add("773", g="(" + f773g + ")", t=u"MEDIENwissenschaft: Rezensionen | Reviews")

    # Link zur Ressource
    try:
        identifiers = xmlrecord.get("metadata", {}).get("dcite:resource",
                                                        {}).get("dcite:relatedIdentifiers",
                                                                {}).get("dcite:relatedIdentifier", [])
        for identifier in identifiers:
            if identifier["@relatedIdentifierType"] == "URL":
                f856u = identifier["#text"]
                marcrecord.add("856", q="text/html", _3="Link zur Ressource", u=f856u)
                break
    except Exception as exc:
        print('[856]', file=sys.stderr)
        raise

    # Medienform
    marcrecord.add("935", b="cofz")

    # Kollektion
    marcrecord.add("980", a=f001, b="73", c="sid-73-col-medienw")

    try:
        outputfile.write(marcrecord.as_marc())
    except UnicodeDecodeError as exc:
        print("#%08d failed: %s" % (i, marcrecord["001"]), file=sys.stderr)
        raise

inputfile.close()
outputfile.close()
