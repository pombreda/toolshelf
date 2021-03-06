`toolshelf` — Theory of Operation
=================================

Heuristics
----------

This section describes how `toolshelf` goes about figuring out where it should
grab a source from, how it should build it, and what it should put on your
search paths; and how you can influence it when it's not clever enough to
figure these things out by itself.

When you refer to a source, `toolshelf` tries to do some clever guessing
about what source you mean, how to build it, and how to put its executables
on your search path.  It also allows you to supply explicit hints to help it
along in this process.

Sections marked ♦ are not yet implemented.

### How does it know which source you mean? ###

#### When docking sources ####

When docking a source, the source must be explicitly specified, although
there are shortcuts you can use.  Unsurprisingly,

    toolshelf dock https://github.com/alincoln/Gettysburg-Address.git

will clone a `git` repo from github to use as the source.  Similarly,

    toolshelf dock https://bitbucket.org/plato/the-republic

will clone a Mercurial repo from Bitbucket.  It does not know that

    toolshelf dock https://github.com/alincoln/Gettysburg-Address

is *not* a Mercurial repo, but in fact a git repo, so what it does in this
case is to try cloning it with Mercurial first, then if that fails, it tries
git.

And you can dock a vanilla, non-version-controlled tarball by saying

    toolshelf dock http://example.com/distfiles/foo-1.0.tar.gz

(It will download the tarball to `$TOOLSHELF/.distfiles/foo-1.0.tar.gz`
and cache it there, extract it to a temporary directory, and place the
source tree in `$TOOLSHELF/example.com/distfile/foo-1.0`.  This will work
regardless of whether the tarball contains a single directory called
`foo-1.0`, as is standard, or if it is a "tarbomb" where all the files are
contained in the root of the tar archive.  Which is frowned upon.)
(Note also that if this is a `.tar.gz` or `.zip` of an entire Git or
Mercurial repository, `toolshelf` will recognize this once it has been
extracted, and will treat it as such.)

`toolshelf` understands a few shortcuts for Github and Bitbucket:

    toolshelf dock gh:hhesse/Steppenwolf
    toolshelf dock bb:jswift/amodestproposal

This syntax is called a _source specification_.  There are a few other source
specifications you can use.  For example,

    toolshelf dock @/home/me/my-sources.catalog

will read a list of source specifications, one per line, from the given text
file (called a _catalog file_.)  These specification may themselves use
shortcuts, or refer to other catalogs.

As a sort of bonus, `@` after a source spec can be used to indicate a revision
to rewind the repository to (which happens immediately after docking and
immediately before building):

    toolshelf dock https://bitbucket.org/user/project@v1.7

...will attempt to build version 1.7 of the project, assuming the tag
(or branch) `v1.7` exists in the repo.

#### When referring to an already-docked source ####

When referring to a source which is already docked, a single source
specification may resolve to multiple sources.  Notably, the source
specification `all` refers to all sources which are currently docked:

    toolshelf build all

(No commands (anymore) take `all` to be the default if no source spec is given.
If you want to do something to all, say `all`.  A common case is
`toolshelf relink all`.)

To refer to all locally-docked source trees by a particular user, the
following syntax may be used:

    toolshelf build alincoln/all

When referring to a single source which is already docked, `toolshelf` allows
you to give just the source's base name, omitting the site name and the
user name.  For example, to build the first source we docked above, you
can say

    toolshelf build Gettysburg-Address

If more than one source has the same base name, the source specification
will resolve to all sources that have that base name.  You may supply the
username as well to resolve the ambiguity:

    toolshelf build alincoln/Gettysburg-Address

but an ambiguity may still occur, and the specification may refer to
multiple sources from multiple hosts.  In this case, you must add both the
host name and the username to resolve the ambiguity:

    toolshelf build github.com/alincoln/Gettysburg-Address

You can also refer to the source tree in the current working directory
(if the current working directory is in a docked source...) with `.`:

    toolshelf build .

### How does it know which executables to place on your path? ###

After a source tree has been docked and built (see below for building,)
`toolshelf` traverses the source tree, looking for interesting files.  When
it finds such things, it collects their names into a set.  It then creates
symlinks in an appropriate "link farm".  For example, for executable files,
the link farm is `$TOOLSHELF/.bin`, and `init.sh` ensures that this directory
is on your `$PATH`.

This approach occasionally results in useless executables on your
path, in the case where are files in the source tree which aren't really
executable, but have the executable bit (`+x`) set anyway, perhaps by
accident, or perhaps because they were taken off a filesystem which doesn't
support the idea of execute permissions.  Or, perhaps they are genuine
executables, but of limited day-to-day use (build scripts, test scripts,
demos, and the like.)

One specific instance of this problem arises when the files came from a `.zip`
archive, which doesn't store executable permission information on files.  In
this case, `toolshelf` traverses all of the files in the source tree just after
extracting them from the archive, running `file` on each one, and setting its
executable permission based on whether `file` called it `executable` or not.

This applies to files that aren't executables, too.  Links to found shared
objects (`.so`'s) are placed in the `$TOOLSHELF/.lib` link farm.  Links to
(specified only, for now) Python modules are placed in the `$TOOLSHELF/.python`
link farm.  And there will be more in the future.

### How does it know how to build the executables from the sources? ###

If the source has a cookie that specifies a `build_command` hint, that
command will be used.  Otherwise...

If there is a script called `build.sh` or `make.sh`, it will run that.
Otherwise...

If there's a `build.xml`, it runs `ant`.  Otherwise...

If there's an `autogen.sh` but no `configure`, it runs that first, to
create `configure`.

If there's no `autogen.sh`, but there is a `configure.in`, it tries to run
`autconf` to create `configure`.

If there's a `configure`, it runs `./configure --prefix=$PWD` to create a
`Makefile`.  Note that it uses the source distribution directory *itself*
as the install target.

If there's a `Makefile`, it runs `make`.

### "Cookies" ###

`toolshelf` comes with a (small) database of "cookies" which supplies extra
information (hints) about the idiosyncracies of particular, known projects.
As you discover idiosyncracies of new software you try to dock, you can add
new hints to this database (and open a pull request to push them upstream for
everyone to benefit from.  But it's even better if you can somehow fix the
source (or the heuristics!) so that cookies aren't required.)

The use of the term "cookie" here is not like "HTTP cookie" or "magic cookie",
but more like how it was used in Windows 3.1 (and may, for all I know, still
be used in modern Windows.)  Such cookies informed the OS about how to deal
with particular hardware for which the generic handling was not sufficient.
This usage of the word is apparently derived from the word "kooky" — that is,
idiosyncratic and non-standard.

In some ways, `toolshelf`'s cookies file is like the `Makefile`s used in
FreeBSD's package system — the information contained in it is similar.
However, it is much more lightweight — the idea is that ideally, no cookies
are needed — so it is just a single file, and is parsed directly instead of
being a `Makefile`.

The cookies file for `toolshelf` consists of a list of source specifications
with hints.  When `toolshelf` is given a source specification which matches
one in the cookies file, it automatically applies those hints.

Example of an entry in the cookies file:

    gh:user/project
      exclude_paths tests
      build_command ./configure --with-lighter-fluid --no-barbecue && make

The global shared cookies file which ships with `toolshelf` is located at
`$TOOLSHELF/.toolshelf/cookies.catalog`.  The file 
`$TOOLSHELF/.toolshelf/local-cookies.catalog` can be created and edited by
the user to supply their own local cookies; this file will not (and should not)
be checked in to the `toolshelf` repo (it's in `.gitignore` and `.hgignore`.)

#### Hints ####

Hints are given, one per line, underneath a source specification in the
cookies file.  Each hint consists of the hint name, some whitespace, and
the hint value (the syntax of which is determined by the hint name.)

Hint names are verbose because they're more readable that way and you'll
probably just be copy-pasting them from other cookies in the cookies file.

It is not possible to give ad-hoc hints on the command line, but only because
it is not a recommended practice; you'll probably want to record those hints
for future use (or for sharing) anyway.

The names of hints are as follows.

*   `build_command`
    
    Example: `build_command ./configure --no-cheese --prefix=\`pwd\` && make`
    
    A shell command that will be used to build the source.  `toolshelf`
    passes the entire hint value to the shell for execution.  The command
    will be run with the root of the source tree as the working directory.
    `toolshelf`'s built-in heuristics for building sources will not be used.
    
*   `exclude_paths`
    
    A space-separated list of directory names that should not be added to the
    executable search path.  This could be useful if there are executables
    included in a source tree that you don't want put on your path, but
    `toolshelf` itself isn't clever enough to figure out that you don't want
    them.  Example: `x=tests/x86`.  Note that this rejects all directories that
    start with the text, so the example would prevent executables in all of the
    following directories from being put on the path: `tests/x86/passing`,
    `tests/x86/failing`, `tests/x8600`.
    
*   `only_paths`
    
    Example: `only_paths bin`
    
    A space-separated list of directory names.  If this hint is given, any
    `exclude_paths` hint is ignores, and *only* these subdirectories will be
    added to the executable search path.  Unlike `exclude_paths`, these
    directories are specific; i.e. if `bin/subdir` contains executables, but
    `only_paths bin` is given, `bin/subdir` will not be added to the search
    path.
    
*   `rectify_permissions`
    
    Example: `rectify_permissions yes`
    
    Either `yes` or `no`.  If `yes`, rectify the execute permissions of the
    source, which means: after checking out the source but before building
    it, traverse all of the files in the source tree, run `file` on each one,
    and set its executable permission based on whether `file` called it
    `executable` or not.  This defaults to `no` for all sources except for
    `.zip` archives, for which it defaults to `yes`; this hint will override
    the default.


Internal Mechanics
------------------

### `bootstrap-toolshelf.sh` ###

The bootstrap script does a few things:

- It checks that you have `git` and `python` installed.  If you don't, it asks
  you to install them, and stops.
- It asks you where you want to store source trees for the packages you dock
  using toolshelf; it calls this `$TOOLSHELF`.  The default is
  `$HOME/toolshelf`.
- It then clones the `toolshelf` git repo into `$TOOLSHELF/.toolshelf`.
- It then asks permission to modify your `.profile` or equivalent shell
  startup script.  If you decline, you are asked to make these changes
  manually.  It adds a line that sources (using `.`) `init.sh` (see below.)
- Finally, it `source`s `init.sh` itself, so that `toolshelf` is available
  immediately after bootstrapping (you don't need to start a new shell.)

### `init.sh` ###

The script `init.sh` initializes `toolshelf` for use; it is typically
sourced (using `.`) from within `.profile` (or equivalent shell startup
script.)  This is what it does:

-   Takes a single command-line argument, which is the `toolshelf` directory,
    and exports it as the `TOOLSHELF` environment variable
-   Puts `$TOOLSHELF/.bin` (the link farm `toolshelf` will create) onto the
    shell's executable search path (`$PATH`.)
-   Puts a bunch of other link farms (`.lib`, `.include`, `.pkconfig`,
    `.python`, `.lua`) on their respective search paths.
-   Defines a shell function called `toolshelf`, which does the following:
    -   If the first argument is `cd`, it:
        -   runs `$TOOLSHELF/.toolshelf/bin/toolshelf pwd` with the arguments
            that were passed after the `cd`
        -   It attempts to change directory to the output of `toolshelf pwd`.
        -   This is done in this shell function because the `toolshelf`
            executable itself can't affect the user's shell.
    -   If not, it simply runs `$TOOLSHELF/.toolshelf/bin/toolshelf` with
        the arguments it was passed.

### `toolshelf` ###

The executable Python script `toolshelf` finds the `toolshelf.py` module,
imports it, and runs the thing in it that does all the real work.

### `toolshelf.py` ###

The Python module `toolshelf.py` is the workhorse:

-   It checks its arguments for an appropriate subcommand.
-   For the subcommand `dock`, it expects to find a source specifier.  It parses
    that specifier to determine where it should find that source.  It attempts
    to obtain that source (using `git clone` or whatever) and places the source
    tree under a subdirectory (organized by domain name and user name) under
    `$TOOLSHELF`.  It then decides if the obtained source needs building, and if
    so, builds it.  It then calls `toolshelf relink` (internally) to rebuild the
    link farm.
-   It checks for other arguments as needed.  Since it's trivial to remove a
    package that has been docked, there is no `undock` subcommand.

Loose `toolshelf` Integration
-----------------------------

If you want to write a "toolshelf plugin", or more literally, any Python program
that can optionally use functions from `toolshelf.py` when a toolshelf is in use,
you can use the following code:

    import os
    if 'TOOLSHELF' in os.environ and os.environ['TOOLSHELF']:
        sys.path.insert(0, os.path.join(
            os.environ['TOOLSHELF'], '.toolshelf', 'src'
        ))
        import toolshelf
    else:
        toolshelf = None

Then later on...

    if toolshelf:
        t = toolshelf.Toolshelf()
        t.dock(['gh:user/repo'])

Note that toolshelf is in constant flux, even if it is a slow flux, so don't
rely on this too heavily.
