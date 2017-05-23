# coding: utf-8
# pylint: disable=F0401,C0111,W0232,E1101,R0904,E1103,C0301
# Copyright 2015 by Leipzig University Library, http://ub.uni-leipzig.de
#                   The Finc Authors, http://finc.info
#                   Tracy Hoffmann, <tracy.hoffmann@uni-leipzig.de>
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
KHM Koeln Tasks

"""

import datetime

import luigi

from gluish.parameter import ClosestDateParameter
from gluish.utils import shellout
from siskin.task import DefaultTask

class KHMTask(DefaultTask):
    """ Base task for KHM Koeln (sid 109) """
    TAG = 'khm'

    def closest(self):
        return monthly(date=self.date)

class KHMTransformation(KHMTask):
    """
    Transform
    Get dump from "Datenklappe" and transform via metafacture
    """