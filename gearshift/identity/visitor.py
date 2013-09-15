"""The visit and identity management *plugins* are defined here."""

import base64

from cherrypy import request

import gearshift
from gearshift.identity import create_default_provider
from gearshift.identity import set_current_identity
from gearshift.identity import set_current_provider
from gearshift.identity import set_login_attempted

from gearshift.identity.exceptions import *

from gearshift import visit

oauth = None

import logging
log = logging.getLogger("gearshift.identity")

def create_extension_model():
    provider = create_default_provider()
    provider.create_provider_model()

class IdentityVisitPlugin(object):
    def __init__(self):
        log.info("Identity visit plugin initialised")
        get = gearshift.config.get

        self.provider = create_default_provider()

        # When retrieving identity information from the form, use the following
        # form field names. These fields will be removed from the post data to
        # prevent the controller from receiving unexpected fields.
        self.user_name_field = get('tools.identity.form.user_name', 'user_name')
        self.password_field = get('tools.identity.form.password', 'password')
        self.submit_button_name = get('tools.identity.form.submit', 'login')

        # Sources for identity information and the order in which they should be
        # checked. These terms are mapped to methods by prepending
        # "identity_from_".
        sources = get('tools.identity.source', 'form,http_auth,visit').split(',')
        self.identity_sources = list()
        for s in sources:
            try:
                source_method = getattr(self, 'identity_from_' + s)
            except AttributeError:
                raise IdentityConfigurationException(
                    "Invalid identity source: %s" % s)
            self.identity_sources.append(source_method)

    def identity_from_request(self, visit_key):
        """Retrieve identity information from the HTTP request.

        Checks first for form fields defining the identity then for a cookie.
        If no identity is found, returns an anonymous identity.

        """
        identity = None
        log.debug("Retrieving identity for visit: %s", visit_key)
        for source in self.identity_sources:
            identity = source(visit_key)
            if identity:
                return identity

        log.info("No identity found")
        # No source reported an identity
        return self.provider.anonymous_identity()

    def decode_basic_credentials(self, credentials):
        """Decode base64 user_name:password credentials used in Basic Auth.

        Returned with username in element 0 and password in element 1.

        """
        return base64.decodestring(credentials.strip()).split(':')

    def identity_from_oauth(self, visit_key):
        # If oauth_consumer is set then the request has been verified
        if not (hasattr(request, 'oauth_request') and request.oauth_request):
            return None
        
        # Lazy import oauth
        global oauth
        if not oauth:
            from oauth import oauth
        
        server = request.oauth_server
        try:
            # verify the request has been oauth authorized
            consumer, token, params = server.verify_request(
                request.oauth_request)
        except oauth.OAuthError, err:
            log.error("OAuth: %s" % err.message)
            return None
        
        return self.provider.authenticated_identity(consumer.user)

    def identity_from_gfc(self, visit_key):
        """Identity from Google Friend Connect"""
        
        if not hasattr(request, 'google_friend_connect'):
            return None
        
        gfc_user = request.google_friend_connect.fetch_person()
        uid = gfc_user.get_id()
        return self.provider.validate_foreign_user("gfc", uid, visit_key)
        
    def identity_from_fbc(self, visit_key):
        """Identity from Facebook Connect"""
        
        if not hasattr(request, "facebook"):
            return None

        uid = request.facebook.uid
        return self.provider.validate_foreign_user("fbc", uid, visit_key)

    def identity_from_http_auth(self, visit_key):
        """Only basic auth is handled at the moment."""
        try:
            authorisation = request.headers['Authorization']
        except KeyError:
            return None

        authScheme, schemeData = authorisation.split(' ', 1)
        # Only basic is handled at the moment
        if authScheme.lower() != 'basic':
            log.error("HTTP Auth is not basic")
            return None

        # decode credentials
        user_name, password = self.decode_basic_credentials(schemeData)
        set_login_attempted(True)
        return self.provider.validate_identity(user_name, password, visit_key)

    def identity_from_visit(self, visit_key):
        return self.provider.load_identity(visit_key)

    def identity_from_form(self, visit_key):
        """Inspect the form to pull out identity information.

        Must have fields for user name, password, and a login submit button.

        Returns an identity dictionary or none if the form contained no
        identity information or the information was incorrect.

        """
        params = request.params
        # only try to process credentials for login forms
        if params.has_key(self.submit_button_name):
            try:
                # form data contains login credentials
                user_name = params.pop(self.user_name_field)
                pw = params.pop(self.password_field)
                # just lose the submit button to prevent passing to final controller
                submit = params.pop(self.submit_button_name, None)
                submit_x = params.pop('%s.x' % self.submit_button_name, None)
                submit_y = params.pop('%s.y' % self.submit_button_name, None)
                set_login_attempted(True)
                identity = self.provider.validate_identity(user_name, pw, visit_key)
                if identity is None:
                    log.warning("The credentials specified weren't valid")
                    return None
                return identity
            except KeyError:
                log.error("Missing fields in login form")
                return None
        else:
            return None

    def record_request(self, visit):
        # default to keeping the identity hook off
        if not gearshift.config.get('tools.identity.on', True):
            log.debug("Identity is not enabled. Setting current identity to None")
            set_current_identity(None)
            return

        try:
            identity = self.identity_from_request(visit.key)
        except IdentityException, e:
            log.exception("Caught exception while getting identity from request")
            errors = [str(e)]
            raise IdentityFailure(errors)

        # stash the user in the thread data for this request
        set_current_identity(identity)
        set_current_provider(self.provider)
        