import getpass

# pip install --user bitbucket-api
from bitbucket.bitbucket import Bitbucket

from toolshelf.toolshelf import BaseCommand

class Command(BaseCommand):
    def process_args(self, shelf, args):
        # this only works for the logged-in user.  It would be great if...
        # yeah.
        username = args[0]
        assert shelf.options.login is not None, \
            '--login must be supplied when accessing the Bitbucket API'
        password = getpass.getpass('Password: ')
        bb = Bitbucket(username, password)
        success, repositories = bb.repository.all()
        for repo in sorted(repositories):
            print 'bb:%s/%s' % (username, repo['slug'])
        return []
