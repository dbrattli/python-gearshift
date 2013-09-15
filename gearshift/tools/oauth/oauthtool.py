import os, logging
import datetime as dt

import cherrypy
from cherrypy import request, response
from cherrypy.lib import http

from oauth import oauth

import gearshift
from gearshift import config, identity
from gearshift.util import load_class
from gearshift.tools.oauth import sodatastore as sods

log = logging.getLogger("gearshift.oauth")

class OAuthTool(cherrypy.Tool):
    
    def __init__(self):
        realm = config.get("tools.oauth.realm", "http://www.example.com")
        datastore_class_path = config.get("tools.oauth.datastore",
                        "gearshift.tools.oauth.sodatastore.OAuthDataStore")
        datastore_class = load_class(datastore_class_path)
        if datastore_class:
            log.info("Successfully loaded \"%s\"" % datastore_class_path)
        else:
            log.error("Unable to load \"%s\"" % datastore_class_path)
            return

        self.datastore = datastore_class()

        self.request_token_url = config.get('oauth.request_token.url', 
                                            '/request_token')
        self.access_token_url = config.get('oauth.access_token.url', 
                                           '/access_token')
        self.realm = realm

        self.oauth_server = oauth.OAuthServer(self.datastore)
        self.oauth_server.add_signature_method(
                                    oauth.OAuthSignatureMethod_PLAINTEXT())
        self.oauth_server.add_signature_method(
                                    oauth.OAuthSignatureMethod_HMAC_SHA1())

        log.info("OAuthTool initialized")

        return super(OAuthTool, self).__init__(point='before_handler', 
                                               callable=self.before_handler, 
                                               priority=10)
    def _setup(self):
        super(OAuthTool, self)._setup()
        cherrypy.request.hooks.attach(
                point='before_finalize',
                callback=self.before_finalize,
                )
    
    # example way to send an oauth error
    def send_oauth_error(self, err=None):
        # return the authenticate header
        header = oauth.build_authenticate_header(realm=self.realm)
        for k, v in header.iteritems():
            response.headers[k] = v
            
        # send a 401 error
        raise cherrypy.HTTPError(401, str(err.message))
        
    def before_handler(self, **kwargs):
        from_request = oauth.OAuthRequest.from_request
        headers = request.headers.copy()

        # Some tools or dispatchers (Rest) may have altered the params, so we
        # need to make sure we use the original parameters. To be sure, we 
        # reparse the query_string.
        params = http.parse_query_string(request.query_string)
        if request.body_params:
            params.update(request.body_params)
        
        # http_url must match exactly with what the client is requesting, and 
        # the best way to do that is to use the X-Forwarded-Host or Host 
        # headers.
        path_info = cherrypy.request.path_info
        scheme = request.base[:request.base.find("://")]
        host = cherrypy.request.headers.get("X-Forwarded-Host") or \
            cherrypy.request.headers.get("Host")
                        
        http_url = "%s://%s%s" % (scheme, host, path_info)
        oauth_request = from_request(
                http_method=request.method,
                http_url=http_url,
                headers=headers,
                parameters=params, 
                query_string=request.query_string,
                )
        
        # If *any* Authorization header, params or query string is supplied,
        # even with solely non-OAuth parameters, we'll get back an
        # oauth_request object. Even if it entirely uselessly only has,
        # for example, "forward_url" in its parameters.
        
        request.oauth_request = oauth_request
        request.oauth_server = self.oauth_server
        
        if not oauth_request or not 'oauth_consumer_key' in oauth_request.parameters:
            # If no useful oauth request, then we do nothing.
            # Protected resources must be protected by GearShift identity
            return
        
        # Remove any oauth-related params from the request, so that
        # those params don't get passed around and confuse handlers.
        for key in request.params.keys():
            if key.startswith('oauth_'):
                del(request.params[key])
        
        if request.path_info.endswith(self.request_token_url):
            try:
                # create a request token
                token = self.oauth_server.fetch_request_token(oauth_request)
            except oauth.OAuthError, err:
                self.send_oauth_error(err)
                return 

            # Tell CherryPy that we have processed the request
            response.body = [token.to_string()]
            request.handler = None

            # Delete Content-Length header so finalize() recalcs it.
            response.headers.pop("Content-Length", None)

        if request.path_info.endswith(self.access_token_url):
            try:
                # create an access token
                token = self.oauth_server.fetch_access_token(oauth_request)
            except oauth.OAuthError, err:
                self.send_oauth_error(err)

            # Tell CherryPy that we have processed the request
            response.body = [token.to_string()]
            request.handler = None
            
            # Delete Content-Length header so finalize() recalcs it.
            response.headers.pop("Content-Length", None)
        
    def before_finalize(self, **kwargs):
        # Even if we have an oauth_request, that doesn't mean it's valid
        oauth_request = getattr(cherrypy.request, 'oauth_request', None)
        if hasattr(identity.current, 'user'):
            # Have to use hasattr here, as using getattr with a default
            # will still trigger an IdentityManagementNotEnabledException.
            user = identity.current.user
        else:
            user = None
        if user and oauth_request and 'oauth_nonce' in oauth_request.parameters:
            # We have a valid user from a valid oauth_request, so we can
            # remove any outdated nonces.
            # 'Outdated' meaning anything with a timestamp (`expires`) outside
            # of the divergence limit enforced by the oauth library.
            timeout = dt.datetime.now() - dt.timedelta(seconds=request.oauth_server.timestamp_threshold)
            nonce_class = sods.nonce_class
            for nonce in nonce_class.select(nonce_class.q.expires < timeout):
                nonce.destroySelf()
            
            # Creating the nonce DB entry here also means they only get added
            # if the OAuth request as a whole was valid.
            timestamp = oauth_request.parameters['oauth_timestamp']
            timestamp = dt.datetime.fromtimestamp(int(timestamp))
            nonce = sods.nonce_class(
                    nonce=oauth_request.parameters['oauth_nonce'],
                    consumer_key=oauth_request.parameters['oauth_consumer_key'],
                    expires=timestamp,
                    )
        
    
