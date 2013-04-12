# `source`d by your `.bashrc` to initialize the `toolshelf` environment in
# your shell session.  Also `source`d by the bootstrap script.  The name of
# the `toolshelf` directory is expected to be passed as the first argument.

export TOOLSHELF=$1

function toolshelf {
    F=$TOOLSHELF/.tmp-toolshelf-result.sh
    python $TOOLSHELF/.toolshelf/toolshelf.py $*
    if [ -e $F ]; then
        source $F
        rm -f $F
    fi
}

#toolshelf path rebuild
export PATH="$TOOLSHELF/.bin:$PATH"
