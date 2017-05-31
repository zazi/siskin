#!/usr/bin/env python
# coding: utf-8

"""
TODO: Crossref, DOAJ example.
"""

import luigi
from luigi.format import Gzip
from gluish.utils import shellout


class CrossrefInput(luigi.Task):

    def output(self):
        return luigi.LocalTarget('inputs/crossref.ldj')


class CrossrefIntermediateSchema(luigi.Task):

    def requires(self):
        return CrossrefInput()

    def run(self):
        output = shellout("span-import -i crossref {input} | gzip -c > {output}", input=self.input().path)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget('outputs/crossref.is.ldj.gz', format=Gzip)


class DOAJInput(luigi.Task):

    def output(self):
        return luigi.LocalTarget('inputs/doaj.ldj')


class DOAJIntermediateSchema(luigi.Task):

    def requires(self):
        return DOAJInput()

    def run(self):
        output = shellout("span-import -i doaj {input} | gzip -c > {output}", input=self.input().path)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget('outputs/doaj.is.ldj.gz', format=Gzip)

if __name__ == '__main__':
    luigi.run(local_scheduler=True)
