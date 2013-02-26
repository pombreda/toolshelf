#!/usr/bin/env python

# Copyright (c)2012 Chris Pressey, Cat's Eye Technologies
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

# toolshelf.py:

# Invoked by `toolshelf.sh` (for which `toolshelf` is an alias) to do the
# heavy lifting involved in docking packages and placing their relevant
# directories on the search path.

# Still largely under construction.

"""\
toolshelf {options} <subcommand>

Manage sources and paths maintained by the toolshelf environment.
Each <subcommand> has its own syntax.  <subcommand> is one of:

    dock {<external-source-spec>}
        Obtain source trees from a remote source, build executables for
        them as needed, and place those executables on your $PATH.
        Triggers a `path rebuild`.

    path rebuild {<docked-source-spec>}
        Update your $PATH to contain the executables for the given
        docked sources.  If none are given, all docked sources will apply.

    path disable {<docked-source-spec>}
        Temporarily remove the executables in the given docked projects
        from your $PATH.  A subsequent `path rebuild` will restore them.
        If no source specs are given, all docked sources will apply.

    path show {<docked-source-spec>}
        Display the directories that have been put on your $PATH by the
        given docked sources.  Also show the executables in those
        directories.

    path check                                 (:not yet implemented:)
        Analyze the current $PATH and report any directories in it which are
        missing from the filesystem, and any executables on it which are
        shadowed by prior entries with the same name.

    path config <docked-source-spec>           (:not yet implemented:)
        Change the hints for a docked source.

    cd <docked-source-spec>
        Change the current working directory to the directory of the
        given docked source.

    consult <docked-source-spec>               (:not yet implemented:)
        Display a menu containing all files in the given docked source
        which are likely to be documentation; when one is selected,
        display its contents with $PAGER.
"""

import ConfigParser as configparser
import os
import optparse
import re
import subprocess
import sys


### Constants (per each run)

SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
TOOLSHELF = os.environ.get('TOOLSHELF')

RESULT_SH_FILENAME = os.path.join(TOOLSHELF, '.tmp-toolshelf-result.sh')

# TODO: these should be regexes
UNINTERESTING_EXECUTABLES = (
    'build.sh', 'make.sh', 'clean.sh', 'install.sh', 'test.sh',
    'build-cygwin.sh', 'make-cygwin.sh', 'install-cygwin.sh',
    'build.pl', 'make.pl', 'install.pl',
    'configure', 'config.status',
)

CWD = os.getcwd()


### Globals

OPTIONS = None
CONFIG = None
COOKIES = None


### Helper Functions

def is_executable(filename):
    basename = os.path.basename(filename)
    if basename in UNINTERESTING_EXECUTABLES:
        return False
    return os.path.isfile(filename) and os.access(filename, os.X_OK)


def find_executables(dirname, index):
    for name in os.listdir(dirname):
        if name in ('.git', '.hg'):
            continue
        filename = os.path.join(dirname, name)
        if is_executable(filename):
            index.setdefault(dirname, []).append(name)
        elif os.path.isdir(filename):
            find_executables(filename, index)


def run(*args):
    note("* Runnning `%s`..." % ' '.join(args))
    subprocess.check_call(args)


def note(msg):
    if OPTIONS.verbose:
        print msg


### Exceptions

class CommandLineSyntaxError(ValueError):
    pass


class SourceSpecSyntaxError(ValueError):
    pass


### Classes

class LazyFile(object):
    def __init__(self, filename):
        self.filename = filename
        self.file = None

    def write(self, data):
        if self.file is None:
            self.file = open(self.filename, 'w')
        self.file.write(data)

    def close(self):
        if self.file is not None:
            self.file.close()


class Config(object):
    def __init__(self):
        self.filename = os.path.join(TOOLSHELF, '.toolshelfrc')
        self._config = None

    @property
    def config(self):
        if self._config is None:
            self._config = configparser.RawConfigParser()
            self._config.read([self.filename])
            if not self._config.has_section('hints'):
                self._config.add_section('hints')
        return self._config

    def get_hints(self, source):
        try:
            hints = self.config.get('hints', source.name)
        except configparser.NoOptionError:
            return None
        return hints

    def set_hints(self, source):
        self.config.set('hints', source.name, source.hints)

    def save(self):
        if self._config is not None:
            f = open(self.filename, 'w')
            self.config.write(f)
            f.close()


class Cookies(object):
    def __init__(self):
        self.filename = os.path.join(
            TOOLSHELF, '.toolshelf', 'cookies.catalog'
        )
        self._source_map = None

    @property
    def source_map(self):
        if self._source_map is None:
            problems = []
            sources = Source.from_catalog('external', self.filename, problems)
            if problems:
                raise ValueError(problems)
            self._source_map = {}
            for source in sources:
                self._source_map[source.name] = source
        return self._source_map

    def apply_hints(self, sources):
        for source in sources:
            if source.hints:
                # already specified; they override what we think we know
                continue
            if source.name in self.source_map:
                source.hints = self.source_map[source.name].hints


class Path(object):
    def __init__(self, value=None):
        if value is None:
            value = os.environ['PATH']
        self.components = [dir.strip() for dir in value.split(':')]

    def write(self, result):
        value = ':'.join(self.components)
        result.write("export PATH='%s'\n" % value)

    def remove_components_by_prefix(self, prefix):
        self.components = [dir for dir in self.components
                           if not dir.startswith(prefix)]

    def add_component(self, dir):
        self.components.insert(0, dir)

    def which(self, filename):
        found = []
        for component in self.components:
            full_filename = os.path.join(component, filename)
            # TODO: this only looks for "interesting" executables...
            # should look for any
            if is_executable(full_filename):
                found.append(full_filename)
        return found


class Source(object):
    def __init__(self, url=None, host=None, user=None, project=None,
                 type=None, hints=''):
        # TODO: look up specifier in database, to obtain "cookies"
        self.url = url
        self.host = host
        self.user = user
        self.project = project
        self.type = type
        self.hints = hints
        self.subdir = self.user or self.host

    @classmethod
    def from_catalog(klass, type, filename, problems):
        filename = os.path.join(CWD, filename)
        try:
            file = open(filename)
        except IOError as e:
            problems.append(e)
            return []
        sources = []
        for line in file:
            line = line.strip()
            if line == '' or line.startswith('#'):
                continue
            sources += Source.from_spec(type, line, problems)
        file.close()
        return sources

    @classmethod
    def from_specs(klass, type, names, problems):
        sources = []
        for name in names:
            sources += klass.from_spec(type, name, problems)
        return sources

    @classmethod
    def from_spec(klass, type, name, problems):
        if name.startswith('@@'):
            filename = os.path.join(
                TOOLSHELF, '.toolshelf', 'catalog', name[2:] + '.catalog'
            )
            return klass.from_catalog(type, filename, problems)
        if name.startswith('@'):
            return klass.from_catalog(type, name[1:], problems)
        if type == 'external':
            return klass.external_from_spec(name, problems)
        elif type == 'docked':
            return klass.docked_from_spec(name, problems)
        else:
            raise KeyError("type must be 'external' or 'docked'")

    @classmethod
    def external_from_spec(klass, name, problems):
        """Parse an external source specifier and return a list of
        Source objects.

        An external source specifier may take any of the following forms:

          git://host.dom/.../user/repo.git       git
          http[s]://host.dom/.../user/repo.git   git
          http[s]://host.dom/.../user/repo       Mercurial
          http[s]://host.dom/.../distfile.tgz    |
          http[s]://host.dom/.../distfile.tar.gz | archive ("tarball")
          http[s]://host.dom/.../distfile.zip    |
          gh:user/project            short for git://github.com/...
          bb:user/project            short for https://bitbucket.org/...
          @local/file/name           read list of sources from file
          @@foo                      read list in .toolshelf/catalog/foo

        If problems are encountered while parsing the source spec,
        they will be added to the problems parameter, assumed to be
        a list-like object.

        """

        hints = None

        # resolve name shorthands
        # TODO: make these configurable
        match = re.match(r'^gh:(.*?)\/(.*?)$', name)
        if match:
            # TODO: allow different styles (https, git, ssh+git...)
            name = 'git://github.com/%s/%s.git' % (match.group(1), match.group(2))
        match = re.match(r'^bb:(.*?)\/(.*?)$', name)
        if match:
            # TODO: allow different styles (https, git, ssh+git...)
            name = 'https://bitbucket.org/%s/%s' % (match.group(1), match.group(2))

        match = re.match(r'^git:\/\/(.*?)/(.*?)/(.*?)\.git$', name)
        if match:
            host = match.group(1)
            user = match.group(2)
            project = match.group(3)
            return [
                Source(url=name, host=host, user=user, project=project,
                       type='git', hints=hints)
            ]

        match = re.match(r'^https?:\/\/(.*?)/(.*?)/(.*?)\.git$', name)
        if match:
            host = match.group(1)
            user = match.group(2)
            project = match.group(3)
            return [
                Source(url=name, host=host, user=user, project=project,
                       type='git', hints=hints)
            ]

        match = re.match(r'^https?:\/\/(.*?)/.*?\/?([^/]*?)'
                         r'\.(zip|tgz|tar\.gz)$', name)
        if match:
            host = match.group(1)
            project = match.group(2)
            ext = match.group(3)
            return [
                Source(url=name, host=host, project=project, type=ext,
                       hints=hints)
            ]

        match = re.match(r'^https?:\/\/(.*?)/(.*?)/(.*?)\/?$', name)
        if match:
            host = match.group(1)
            user = match.group(2)
            project = match.group(3)
            return [
                Source(url=name, host=host, user=user, project=project,
                       type='hg', hints=hints)
            ]

        problems.append("Couldn't parse source spec '%s'" % name)
        return []

    @classmethod
    def docked_from_spec(klass, name, problems):
        """Parse a docked source specifier and return a list of Source
        objects.

        A docked source specifier may take any of the following forms:

          user/project               the source docked under this name
          user/*                 NYI all docked projects for this user
          *                          all docked projects
          project                NYI unambiguous project in toolshelf
          @local/file/name       NYI read list of sources from file
          @@foo                  NYI read list in toolshelf/catalog/foo

        If problems are encountered while parsing the source spec,
        they will be added to the problems parameter, assumed to be
        a list-like object.

        """
        # TODO: look up specifier in database, to obtain "cookies"

        if name.startswith('@@'):
            filename = os.path.join(
                TOOLSHELF, '.toolshelf', 'catalog', name[2:] + '.catalog'
            )
            return klass.from_catalog(
                'docked', filename, problems
            )
        if name.startswith('@'):
            return klass.from_catalog(
                'docked', name[1:], problems
            )

        if name == '*':
            # TODO: should divine whether a docked project is a git
            # repo, a mercurial repo, or whatnot.
            sources = []
            for user in os.listdir(TOOLSHELF):
                if user in ('.toolshelf', '.toolshelfrc'):
                    # skip the toolshelf dir itself
                    continue
                sub_dirname = os.path.join(TOOLSHELF, user)
                for project in os.listdir(sub_dirname):
                    project_dirname = os.path.join(sub_dirname, project)
                    if not os.path.isdir(project_dirname):
                        continue
                    # TODO: do we apply the given hints here?  (depends)
                    s = Source(user=user, project=project, type='unknown')
                    s.load_hints()
                    sources.append(s)
            return sources

        match = re.match(r'^(.*?)\/(.*?)$', name)
        if match:
            user = match.group(1)
            project = match.group(2)
            if os.path.isdir(os.path.join(TOOLSHELF, user, project)):
                s = Source(user=user, project=project, type='unknown')
                s.load_hints()
                return [s]
            problems.append("Source '%s' not docked" % name)
            return []

        problems.append("Couldn't parse source spec '%s'" % name)
        return []

    @property
    def distfile(self):
        if self.type in ('zip', 'tgz', 'tar.gz'):
            return os.path.join(TOOLSHELF, self.subdir,
                                '%s.%s' % (self.project, self.type))
        else:
            return None

    @property
    def name(self):
        return os.path.join(self.subdir, self.project)

    @property
    def dir(self):
        return os.path.join(TOOLSHELF, self.name)

    def save_hints(self):
        CONFIG.set_hints(self)

    def load_hints(self):
        hints = CONFIG.get_hints(self)
        if hints is not None:
            self.hints = hints

    @property
    def docked(self):
        return os.path.isdir(self.dir)

    def checkout(self):
        note("* Checking out %s/%s..." % (self.subdir, self.project))

        os.chdir(TOOLSHELF)
        if not os.path.isdir(self.subdir):
            os.mkdir(self.subdir)
        os.chdir(self.subdir)

        if self.type == 'git':
            run('git', 'clone', self.url)
        elif self.type == 'hg':
            run('hg', 'clone', self.url)
        elif self.distfile is not None:
            run('rm', '-f', self.distfile)
            run('wget', '-nc', '-O', self.distfile, self.url)
            extract_dir = os.path.join(
                TOOLSHELF, self.subdir, '.extract_' + self.project
            )
            run('mkdir', '-p', extract_dir)
            os.chdir(extract_dir)
            if self.type == 'zip':
                run('unzip', self.distfile)
            elif self.type in ('tgz', 'tar.gz'):
                # TODO: use modern command line arguments to tar
                run('tar', 'zxvf', self.distfile)

            files = os.listdir(extract_dir)
            if len(files) == 1:
                extracted_dir = os.path.join(extract_dir, files[0])
                if not os.path.isdir(extracted_dir):
                    extracted_dir = extract_dir
            else:
                extracted_dir = extract_dir
            run('mv', extracted_dir, self.dir)
            run('rm', '-rf', extract_dir)

            if self.type == 'zip':
                self.rectify_executable_permissions()
        else:
            raise NotImplementedError(self.type)

        self.save_hints()

    def build(self):
        if not OPTIONS.build:
            note("* SKIPPING build of %s" % self.name)
            return
        note("* Building %s..." % self.name)

        os.chdir(self.dir)
        if os.path.isfile('configure'):
            run('./configure')
        if os.path.isfile('Makefile'):
            run('make')
        elif os.path.isfile('src/Makefile'):
            os.chdir('src')
            run('make')
        elif os.path.isfile('build.sh'):
            run('./build.sh')

    def find_path_components(self):
        index = {}
        find_executables(self.dir, index)
        components = []
        for dirname in sorted(index):
            # TODO: rewrite this more elegantly
            add_it = True
            for hint in self.hints.split(':'):
                # TODO: better hint parsing
                try:
                    (name, value) = hint.split('=')
                except ValueError:
                    continue
                if name == 'x':
                    verboten = os.path.join(self.dir, value)
                    if dirname.startswith(verboten):
                        add_it = False
                        break
            if not add_it:
                note("(SKIPPING %s)" % dirname)
                continue
            note("  %s:" % dirname)
            for filename in index[dirname]:
                note("    %s" % filename)
            components.append(dirname)
        return components

    def rectify_executable_permissions(self):
        def traverse(dirname):
            for name in os.listdir(dirname):
                if name in ('.git', '.hg'):
                    continue
                filename = os.path.join(dirname, name)
                if os.path.isdir(filename):
                    traverse(filename)
                else:
                    make_it_executable = False
                    pipe = subprocess.Popen(["file", filename],
                                            stdout=subprocess.PIPE)
                    output = pipe.communicate()[0]
                    if 'executable' in output:
                        make_it_executable = True
                    if make_it_executable:
                        note("* Making %s executable" % name)
                        subprocess.check_call(["chmod", "u+x", filename])
                    else:
                        note("* Making %s NON-executable" % name)
                        subprocess.check_call(["chmod", "u-x", filename])

        traverse(self.dir)


### Subcommands


def dock_cmd(result, args):
    problems = []
    sources = Source.from_specs('external', args, problems)
    # TODO: improve this
    if problems:
        raise SourceSpecSyntaxError(repr(problems))
    COOKIES.apply_hints(sources)
    for source in sources:
        source.checkout()
        source.build()
    path_cmd(result, ['rebuild'] + [s.name for s in sources])


def path_cmd(result, args):
    def clean_path(path, sources, all=False):
        # special case to handle total rebuilds/disables:
        if all:
            note("* Removing from your PATH all toolshelf directories")
            path.remove_components_by_prefix(TOOLSHELF)
        else:
            note("* Removing from your PATH all directories that "
                 "start with one of the following...")
            for source in sources:
                note("  " + source.dir)
                path.remove_components_by_prefix(source.dir)

    if args[0] == 'rebuild':
        specs = args[1:]
        if not specs:
            specs = ['*']
        problems = []
        sources = Source.from_specs('docked', specs, problems)
        # TODO: improve this
        if problems:
            raise SourceSpecSyntaxError(repr(problems))
        p = Path()
        clean_path(p, sources, all=(specs == ['*']))
        note("* Adding the following executables to your PATH...")
        for source in sources:
            for component in source.find_path_components():
                p.add_component(component)
        p.write(result)
    elif args[0] == 'disable':
        specs = args[1:]
        if not specs:
            specs = ['*']
        problems = []
        sources = Source.from_specs('docked', specs, problems)
        # TODO: improve this
        if problems:
            raise SourceSpecSyntaxError(repr(problems))
        p = Path()
        clean_path(p, sources, all=(specs == ['*']))
        p.write(result)
    elif args[0] == 'show':
        specs = args[1:]
        if not specs:
            specs = ['*']
        problems = []
        sources = Source.from_specs('docked', specs, problems)
        # TODO: improve this
        if problems:
            raise SourceSpecSyntaxError(repr(problems))
        p = Path()
        for component in p.components:
            for source in sources:
                if component.startswith(source.dir):
                    print component
                    for filename in sorted(os.listdir(component)):
                        if is_executable(os.path.join(component, filename)):
                            print "  %s" % filename
    else:
        raise CommandLineSyntaxError(
            "Unrecognized 'path' subcommand '%s'\n" % args[0]
        )


def cd_cmd(result, args):
    problems = []
    sources = Source.from_specs('docked', args, problems)
    # TODO: improve this
    if problems:
        raise SourceSpecSyntaxError(repr(problems))
    if len(sources) != 1:
        raise CommandLineSyntaxError(
            "'cd' subcommand requires exactly one source\n"
        )
    result.write('cd %s\n' % sources[0].dir)


SUBCOMMANDS = {
    'dock': dock_cmd,
    'path': path_cmd,
    'cd': cd_cmd,
}


def main():
    global OPTIONS, CONFIG, COOKIES

    parser = optparse.OptionParser(__doc__)

    parser.add_option("-B", "--no-build", dest="build",
                      default=True, action="store_false",
                      help="don't try to build sources during docking")
    parser.add_option("-v", "--verbose", dest="verbose",
                      default=False, action="store_true",
                      help="report steps taken to standard output")

    (OPTIONS, args) = parser.parse_args()
    if len(args) == 0:
        print "Usage: " + __doc__
        sys.exit(2)

    os.chdir(TOOLSHELF)
    result = LazyFile(RESULT_SH_FILENAME)
    CONFIG = Config()
    COOKIES = Cookies()

    subcommand = args[0]
    if subcommand in SUBCOMMANDS:
        try:
            SUBCOMMANDS[subcommand](result, args[1:])
        except CommandLineSyntaxError as e:
            sys.stderr.write(str(e) + '\n')
            print "Usage: " + __doc__
            sys.exit(2)
        except SourceSpecSyntaxError as e:
            sys.stderr.write(repr(e) + '\n')
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            sys.stderr.write(str(e) + '\n')
            sys.exit(e.returncode)
    else:
        sys.stderr.write("Unrecognized subcommand '%s'\n" % subcommand)
        print "Usage: " + __doc__
        sys.exit(2)

    result.close()
    CONFIG.save()


if __name__ == '__main__':
    main()
