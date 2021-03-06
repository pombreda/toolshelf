"""
Find documentation files and write out Yaml file summarizing them.

Looks for documentation in local repository clones and writes out
a file that can be used to update the Documentation nodes in the
Chrysoberyl data.

"""

import codecs
import os

from toolshelf.toolshelf import BaseCommand

class Command(BaseCommand):
    def setup(self, shelf):
        self.docdict = {}

    def perform(self, shelf, source):
        for path in source.find_likely_documents():
            self.docdict.setdefault(source.name, []).append(path)

    def teardown(self, shelf):
        import yaml

        output_filename = os.path.join(shelf.cwd, 'docs.yaml')
        with codecs.open(output_filename, 'w', 'utf-8') as file:
            file.write('# encoding: UTF-8\n')
            file.write('# AUTOMATICALLY GENERATED BY chrysoberyl.py\n')
            file.write(yaml.dump(self.docdict, Dumper=yaml.Dumper, default_flow_style=False))
