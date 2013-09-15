"""The TurboGears identity management package.

@TODO: Laundry list of things yet to be done:
    * IdentityFilter should support HTTP Digest Auth
    * Also want to support Atom authentication (similar to digest)

"""

# declare what should be exported
__all__ = [
    '_encrypt_password',
    'create_default_provider',
    'current',
    'current_provider',
    'encrypt_password',
    'encrypt_pw_with_algorithm',
    'get_identity_errors',
    'get_failure_url',
    'set_current_identity',
    'set_current_provider',
    'set_identity_errors',
    'set_login_attempted',
    'was_login_attempted',
    'verify_identity_status',
]


import logging
try:
	from hashlib import md5, sha1
except ImportError:
	from md5 import md5
	from sha import sha as sha1
import threading

import cherrypy
##import pkg_resources
import gearshift

from gearshift.util import deprecated, request_available, load_class
from gearshift.identity.exceptions import *


log = logging.getLogger('gearshift.identity')


def create_default_provider():
    """Create default identity provider.

    Creates an identity provider according to what is found in
    the configuration file for the current TurboGears application

    Returns an identity provider instance or
    raises an IdentityConfigurationException.

    """
    provider_plugin = gearshift.config.get('tools.identity.provider', 
                    'gearshift.identity.soprovider.SqlObjectIdentityProvider')

    log.debug("Loading provider from plugin: %s", provider_plugin)

    provider_class = None
    if not provider_class:
        provider_class = load_class(provider_plugin)

    if not provider_class:
        raise IdentityConfigurationException(
            "IdentityProvider plugin missing: %s" % provider_plugin )
    else:
        return provider_class()

def was_login_attempted():
    try:
        return cherrypy.request.identity_login_attempted
    except AttributeError:
        return False

def set_login_attempted(flag):
    cherrypy.request.identity_login_attempted = flag

def set_current_identity(identity):
    cherrypy.request.identity = identity
    try:
        user_name = identity.user_name
    except AttributeError:
        user_name = None
    
    cherrypy.request.user_name = user_name

    # So the cherrypy access log prints the correct name
    # (but we don't want to wipe it out if tools.identity is off)
    if user_name is not None:
        cherrypy.request.login = user_name


def set_current_provider(provider):
    cherrypy.request.identityProvider = provider


def encrypt_pw_with_algorithm(algorithm, password):
    """Hash the given password with the specified algorithm.

    Valid values for algorithm are 'md5' and 'sha1' or 'custom'. If the
    algorithm is 'custom', the config setting 'tools.identity.custom_encryption'
    needs to be set to a dotted-notation path to a callable that takes
    an unencrypted password and gives back the password hash.

    All other algorithm values will be essentially a no-op.

    """
    
    hashed_password = password
    # The algorithms don't work with unicode objects, so decode first.
    if isinstance(password, unicode):
        password_8bit = password.encode('utf-8')
    else:
        password_8bit = password
    if algorithm == 'md5':
        hashed_password =  md5(password_8bit).hexdigest()
    elif algorithm == 'sha1':
        hashed_password = sha1(password_8bit).hexdigest()
    elif algorithm == 'custom':
        custom_encryption_path = gearshift.config.get(
            'tools.identity.custom_encryption', None)
        if custom_encryption_path:
            custom_encryption = gearshift.util.load_class(
                custom_encryption_path)
        if custom_encryption:
            hashed_password = custom_encryption(password_8bit)
    # Make sure the hashed password is a unicode object at the end of the
    # process, because SQLAlchemy _wants_ that for Unicode columns.
    if not isinstance(hashed_password, unicode):
        hashed_password = hashed_password.decode('utf-8')
    return hashed_password

_encrypt_password = deprecated(
    "Use identity.encrypt_pw_with_algorithm instead."
)(encrypt_pw_with_algorithm)

def encrypt_password(cleartext):
    return current_provider.encrypt_password(cleartext)


class IdentityWrapper(object):
    """A wrapper class for the thread local data.

    This allows developers to access the current user information via
    gearshift.identity.current and get the identity for the current request.

    """

    def identity(self):
        try:
            identity = cherrypy.request.identity
        except AttributeError:
            identity = None

        if not identity:
            if not request_available():
                raise RequestRequiredException()
            raise IdentityManagementNotEnabledException()

        return identity

    def __getattr__(self, name):
        """Return the named attribute of the global state."""
        identity = self.identity()
        if name == '__str__':
            return identity.__str__
        elif name == '__repr__':
            return identity.__repr__
        else:
            return getattr(identity, name)

    def __setattr__(self, name, value):
        """Stash a value in the global state."""
        identity = self.identity()
        setattr(identity, name, value)


class ProviderWrapper(object):

    def __getattr__(self, name):
        try:
            provider = cherrypy.request.identityProvider
        except AttributeError:
            try:
                provider = create_default_provider()
            except Exception:
                provider = None

        if provider is None:
            if not request_available():
                raise RequestRequiredException()
            raise IdentityManagementNotEnabledException()

        return getattr(provider, name)

current = IdentityWrapper()
current_provider = ProviderWrapper()


def verify_identity_status():
    """A tool that sets response status based on identity's success or failure.

    This is necessary since the status will be overriden by the result of 
    forwarding the user to the login page.

    Does not override status if the login controller errors out.
    """

    if (cherrypy.response.status < '400'):
        new_status = cherrypy.request.wsgi_environ.get('identity_status', None)
        if new_status:
            cherrypy.response.status = new_status

