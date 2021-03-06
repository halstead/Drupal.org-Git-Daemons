#!/usr/bin/env python
from twisted.internet import epollreactor
epollreactor.install()

import os
import shlex
import sys
from twisted.conch.avatar import ConchUser
from twisted.internet.error import ProcessExitedAlready
from twisted.conch.error import ConchError, UnauthorizedLogin, ValidPublicKey
from twisted.conch.ssh.channel import SSHChannel
from twisted.conch.ssh.session import ISession, SSHSession, SSHSessionProcessProtocol
from twisted.conch.ssh.factory import SSHFactory
from twisted.conch.ssh.keys import Key
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernamePassword, ISSHPrivateKey
from twisted.cred.portal import IRealm, Portal
from twisted.internet import reactor, defer
from twisted.internet.defer import DeferredList
from twisted.python import components, log
from twisted.python.failure import Failure
from zope import interface

# Workaround for early EOF in git-receive-pack
# Seems related to Twisted bug #4350
# See: http://twistedmatrix.com/trac/ticket/4350
SSHSessionProcessProtocol.outConnectionLost = lambda self: None

import urllib
import base64
import hashlib
import json

from config import config
from service import Service
from service.protocols import AuthProtocol
from drupalpass import DrupalHash

class DrupalMeta(object):
    def __init__(self):
        self.anonymousReadAccess = config.getboolean('drupalSSHGitServer', 'anonymousReadAccess')

    def request(self, uri):
        """Build the request to run against drupal

        request(project uri)

        Values and structure returned:
        {username: {uid:int, 
                    repo_id:int, 
                    access:int, 
                    branch_create:boolean, 
                    branch_update:boolean, 
                    branch_delete:boolean, 
                    tag_create:boolean,
                    tag_update:boolean,
                    tag_delete:boolean,
                    per_label:list,
                    name:str,
                    pass:md5,
                    ssh_keys: { key_name:fingerprint }
                   }
        }"""
        auth_service = Service(AuthProtocol('vcs-auth-data'))
        auth_service.request_json({"project_uri":self.projectname(uri)})
        pushctl_service= Service(AuthProtocol('pushctl-state'))
        pushctl_service.request_json()
        def NoDataHandler(fail):
            fail.trap(ConchError)
            message = fail.value.value
            log.err(message)
            # Return a stub auth_service object
            return {"users":{}, "repo_id":None}
        auth_service.addErrback(NoDataHandler)
        return DeferredList([auth_service.deferred, pushctl_service.deferred])

    def repopath(self, scheme, subpath):
        '''Note, this is where we do further mapping into a subdirectory
        for a user or issue's specific sandbox'''

        # Build the path to the repository
        try:
            scheme_path = config.get(scheme, 'repositoryPath')
        except:
            # Fall back to the default configured path scheme
            scheme_path = config.get('drupalSSHGitServer', 'repositoryPath')
        path = os.path.join(scheme_path, *subpath)
        if path[-4:] != ".git":
            path += ".git"
        # Check to see that the folder exists
        if not os.path.exists(path):
            return None
        return path

    def projectname(self, uri):
        '''Extract the project name alone from a path like /project/views.git'''

        parts = uri.split('/')
        project = parts[-1]
        if len(project) > 4 and project[-4:] == '.git':
            return project[:-4]
        else:
            return project

def find_error_script():
    for directory in sys.path:
        full_path = os.path.join(directory, "git-error")
        if (os.path.exists(full_path) and 
            os.access(full_path, (os.F_OK | os.X_OK))):
            return full_path
    raise Exception('Could not find git-error executable!')

def find_git_shell():
    # Find git-shell path.
    # Adapted from http://bugs.python.org/file15381/shutil_which.patch
    path = os.environ.get("PATH", os.defpath)
    for dir in path.split(os.pathsep):
        full_path = os.path.join(dir, 'git-shell')
        if (os.path.exists(full_path) and 
                os.access(full_path, (os.F_OK | os.X_OK))):
            return full_path
    raise Exception('Could not find git executable!')

class GitSession(object):
    interface.implements(ISession)

    def __init__(self, user):
        self.user = user

    def map_user(self, username, fingerprint, users):
        """Map the username from name or fingerprint, to users item."""
        if username == "git":
            # Use the fingerprint
            for user in users.values():
                if fingerprint in user["ssh_keys"].values():
                    return user
            # No fingerprints match
            return None
        elif username in users:
            # Use the username
            return users[username]
        else:
            return None

    def pushcontrol(self, deferred_results, argv):
        auth_result, pushctl_result = deferred_results
        auth_status, auth_service = auth_result
        pushctl_status, pushctl_service = pushctl_result
        if not auth_service:
            error = "Repository does not exist. Verify that your remote is correct."
            raise ConchError(error)
        if pushctl_status and auth_status:
            mask = auth_service["repo_group"] & pushctl_service
            if mask:
                error = "Pushes for this type of repo are currently disabled."
                # This type of repo has pushes disabled
                if mask & 0x01:
                    error = "Pushes to core are currently disabled."
                if mask & 0x02:
                    error = "Pushes to projects are currently disabled."
                if mask & 0x04:
                    error = "Pushes to sandboxes are currently disabled."
                return Failure(ConchError(error))
            else:
                # Good to continue with auth
                return auth_service
        elif not auth_status:
            # This will be a failure, not the auth data in this case
            return auth_service
        else:
            return pushctl_service

    def auth(self, auth_service, argv):
        """Verify we have permission to run the request command."""
        # Key fingerprint
        if hasattr(self.user.meta, "fingerprint"):
            fingerprint = self.user.meta.fingerprint
        else:
            fingerprint = None

        if hasattr(self.user.meta, "password"):
            password = self.user.meta.password
        else:
            password = None

        # Check permissions by mapping requested path to file system path
        repostring = argv[-1]
        repolist = repostring.split('/')
        if repolist[0]:
            # No leading /
            scheme = repolist[0]
            projectpath = repolist[1:]
        else:
            scheme = repolist[1]
            projectpath = repolist[2:]
        repopath = self.user.meta.repopath(scheme, projectpath)
        if not repopath:
            return Failure(ConchError("The remote repository at '{0}' does not exist. Verify that your remote is correct.".format(repostring)))
        projectname = self.user.meta.projectname(repostring)

        # Map the user
        users = auth_service["users"]
        user = self.map_user(self.user.username, fingerprint, users)
        execGitCommand = repopath, user, auth_service

        # Check to see if anonymous read access is enabled and if
        # this is a read
        if (self.user.meta.anonymousReadAccess and \
                'git-upload-pack' in argv[:-1]):
            # Read only command, and anonymous access is enabled
            return execGitCommand
        else:
            # First, error out if the project itself is disabled.
            if not auth_service["status"]:
                error = "Project {0} has been disabled.".format(projectname)
                return Failure(ConchError(error))
            # Now, deny if the user isn't listed, or doesn't have push access.
            # See http://drupalcode.org/project/versioncontrol.git/blob/refs/heads/6.x-2.x:/includes/plugins/vcs_auth/VersioncontrolAuthHandlerMappedAccounts.class.php
            # for an explanation on the values used here. Drupal.org currently
            # only exercises the simplest subset of these values - the global
            # access value, and with the 'ALL' value, which == 2. 1 is also
            # valid ('GRANT'), though it should never come back in the current
            # drupal.org implementation state.
            if not user or user["access"] not in [1,2]:
                error = "You do not have write permissions for the '{0}' repository.".format(projectname)
                return Failure(ConchError(error))
            elif user["global"]:
                # Account is globally disabled or disallowed
                # 0x01 = no Git user role, but unknown reason (probably a bug!)
                # 0x02 = Git account suspended
                # 0x04 = Git ToS unchecked
                # 0x08 = Drupal.org account blocked
                error = ''
                if user["global"] & 0x02:
                    error += "Your Git access has been suspended.\n"
                if user["global"] & 0x04:
                    error += "You are required to accept the Git Access Agreement in your user profile before using Git.\n"
                if user["global"] & 0x08:
                    error += "Your Drupal.org account has been blocked.\n"

                if not error and user["global"] == 0x01:
                    error = "You do not have permission to access '{0}' with the provided credentials.\n".format(projectname)
                elif not error:
                    # unknown situation, but be safe and error out
                    error = "This operation cannot be completed at this time.  It may be that we are experiencing technical difficulties or are currently undergoing maintenance."
                return Failure(ConchError(error))
            else:
                # last check ensuring either fingerprint or pw match
                if fingerprint in user["ssh_keys"].values() or user["pass"] == password:
                    return execGitCommand
                else:
                    # Both kinds of username auth failed
                    error = "Permission denied when accessing '{0}' as user '{1}'".format(projectname, self.user.username)
                    return Failure(ConchError(error))

    def errorHandler(self, fail, proto):
        """Catch any unhandled errors and send the exception string to the remote client."""
        fail.trap(ConchError)
        message = fail.value.value
        log.err(message)
        if proto.connectionMade():
            proto.loseConnection()
        error_script = self.user.error_script
        reactor.spawnProcess(proto, error_script, (error_script, message))

    def execCommand(self, proto, cmd):
        """Execute a git-shell command."""
        argv = shlex.split(cmd)
        # This starts an auth request and returns.
        try:
            auth_service_deferred = self.user.meta.request(argv[-1])
        except ConchError, e:
            # The request could not be started
            self.errorHandler(Failure(e), proto)
        else:
            # Check if pushes are disabled for this path
            auth_service_deferred.addCallback(self.pushcontrol, argv)
            # Once it completes, auth is run
            auth_service_deferred.addCallback(self.auth, argv)
            # Then the result of auth is passed to execGitCommand to run git-shell
            auth_service_deferred.addCallback(self.execGitCommand, argv, proto)
            auth_service_deferred.addErrback(self.errorHandler, proto)

    def execGitCommand(self, auth_values, argv, proto):
        """After all authentication is done, setup an environment and execute the git-shell commands."""
        repopath, user, auth_service = auth_values
        sh = self.user.shell
        repo_id = auth_service["repo_id"]

        if proto.session.localClosed:
            # The channel has been closed while we were performing the
            # authentication request, exit.
            return

        env = {}
        if user:
            # The UID is known, populate the environment
            # Be positive that we only use strings in our command and environment since we
            # cast everything we could to integers when loading JSON data
            env['VERSION_CONTROL_GIT_UID'] = str(user["uid"])
            env['VERSION_CONTROL_GIT_REPO_ID'] = str(repo_id)
            env['VERSION_CONTROL_VCS_AUTH_DATA'] = json.dumps(auth_service)
        
        
        argv = [str(e) for e in argv]
        
        command = ' '.join(argv[:-1] + ["'{0}'".format(repopath)])
        self.pty = reactor.spawnProcess(proto, sh, (sh, '-c', command), env=env)

    def eofReceived(self):
        if hasattr(self, 'pty'):
            self.pty.closeStdin()

    def closed(self):
        if hasattr(self, 'pty'):
            try:
                self.pty.signalProcess('HUP')
            except (OSError,ProcessExitedAlready):
                pass
            self.pty.loseConnection()


class GitConchUser(ConchUser):
    shell = find_git_shell()
    error_script = find_error_script()

    def __init__(self, username, meta):
        ConchUser.__init__(self)
        self.username = username
        self.channelLookup.update({"session": SSHSession})
        self.meta = meta

    def logout(self): pass


class GitRealm(object):
    interface.implements(IRealm)

    def __init__(self, meta):
        self.meta = meta

    def requestAvatar(self, username, mind, *interfaces):
        user = GitConchUser(username, self.meta)
        return interfaces[0], user, user.logout

class GitPubKeyChecker(object):
    """Skip most of the auth process until the SSH session starts.

    Save the public key fingerprint for later use and verify the signature."""
    credentialInterfaces = ISSHPrivateKey,
    interface.implements(ICredentialsChecker)

    def __init__(self, meta):
        self.meta = meta

    def verify(self, username, credentials, key):
        # Verify the public key signature
        # From twisted.conch.checkers.SSHPublicKeyDatabase._cbRequestAvatarId
        if not credentials.signature:
            # No signature ready
            return Failure(ValidPublicKey())
        else:
            # Ready, verify it
            try:
                if key.verify(credentials.signature, credentials.sigData):
                    return credentials.username
            except:
                log.err()
                return Failure(UnauthorizedLogin("key could not verified"))

    def requestAvatarId(self, credentials):
        key = Key.fromString(credentials.blob)
        fingerprint = key.fingerprint().replace(':', '')
        self.meta.fingerprint = fingerprint
        if (credentials.username == 'git'):
            # Todo, maybe verify the key with a process protocol call
            # (drush or http)
            def success():
                return credentials.username
            d = defer.maybeDeferred(success)
            d.addCallback(self.verify, credentials, key)
            return d
        else:
            """ If a user specified a non-git username, check that the user's key matches their username

            so that we can request a password if it does not."""
            service = Service(AuthProtocol('drupalorg-ssh-user-key'))
            service.request_bool({"username":credentials.username},
                                 {"fingerprint":fingerprint})
            def auth_callback(result):
                if result:
                    return credentials.username
                else:
                    return Failure(UnauthorizedLogin(credentials.username))
            service.addCallback(auth_callback)
            service.addCallback(self.verify, credentials, key)
            return service.deferred

class GitPasswordChecker(object):
    """Skip most of the auth process until the SSH session starts.

    Save the password hash for later use."""
    credentialInterfaces = IUsernamePassword,
    interface.implements(ICredentialsChecker)

    def __init__(self, meta):
        self.meta = meta

    def requestAvatarId(self, credentials):
        def fetchHash(credentials):
            service = Service(AuthProtocol('drupalorg-vcs-auth-fetch-user-hash'))
            service.request_json({"username":credentials.username})
            def auth_callback(result):
                if result:
                    self.meta.password = DrupalHash(result, credentials.password).get_hash()
                    return checkAuth(credentials)
            service.addCallback(auth_callback)
            return service.deferred

        def checkAuth(credentials):
            service = Service(AuthProtocol('drupalorg-vcs-auth-check-user-pass'))
            service.request_bool({"username":credentials.username},
                                 {"password":self.meta.password})
            def auth_callback(result):
                if result:
                    return credentials.username
                else:
                    return Failure(UnauthorizedLogin(credentials.username))
            service.addCallback(auth_callback)
            return service.deferred
        return fetchHash(credentials)

class GitServer(SSHFactory):
    authmeta = DrupalMeta()
    portal = Portal(GitRealm(authmeta))
    portal.registerChecker(GitPubKeyChecker(authmeta))
    portal.registerChecker(GitPasswordChecker(authmeta))

    def __init__(self, privkey):
        pubkey = '.'.join((privkey, 'pub'))
        self.privateKeys = {'ssh-rsa': Key.fromFile(privkey)}
        self.publicKeys = {'ssh-rsa': Key.fromFile(pubkey)}

class Server(object):
    def __init__(self):
        self.port = config.getint('drupalSSHGitServer', 'port')
        self.interface = config.get('drupalSSHGitServer', 'host')
        self.key = config.get('drupalSSHGitServer', 'privateKeyLocation')
        components.registerAdapter(GitSession, GitConchUser, ISession)

    def application(self):
        return GitServer(self.key)

if __name__ == '__main__':
    log.startLogging(sys.stderr)
    ssh_server = Server()
    reactor.listenTCP(ssh_server.port, 
                      ssh_server.application(), 
                      interface=ssh_server.interface)
    reactor.run()
