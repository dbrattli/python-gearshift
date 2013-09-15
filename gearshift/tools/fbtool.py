import os, logging

import gearshift

import cherrypy
from cherrypy import request

facebook = None # Lazy imported

log = logging.getLogger("gearshift")

class FacebookTool(cherrypy.Tool):
    
    def __init__(self, config):
        self.config = config
                    
        log.debug("FacebookTool initialized")

        return super(FacebookTool, self).__init__(point='before_handler', 
                                                  callable=self.before_handler, 
                                                  priority=10)  
    def before_handler(self, **kwargs):
        log.debug("FacebookTool: before_handler")

        global facebook
        if facebook is None:
            try:
                import facebook
            except ImportError:
                log.error("Facebook is not available")
            
            self.api_key = self.config.get("facebook.apikey")
            self.secret_key = self.config.get("facebook.secret")

        fb = facebook.Facebook(api_key=self.api_key, secret_key=self.secret_key)
        cherrypy.request.facebook = fb
        
        fb.in_canvas = (request.params.get('fb_sig_in_canvas') == '1')

        # Check if we already have a session
        if fb.session_key and (fb.uid or fb.page_id):
            return True

        if request.method == 'POST':
            params = fb.validate_signature(request.params)
        else:
            if 'installed' in request.params:
                fb.added = True

            if 'fb_page_id' in request.params:
                fb.page_id = request.params['fb_page_id']

            if 'auth_token' in request.params:
                fb.auth_token = request.params['auth_token']

                try:
                    fb.auth.getSession()
                except facebook.FacebookError, e:
                    log.error("FBTool: Unable to get session")
                    fb.auth_token = None
                    return False
                
                return True

            params = fb.validate_signature(request.params)

        if not params:
            # first check if we are in django - to check cookies
            if hasattr(request, 'cookie'):
                params = self.validate_cookie_signature(request.cookie)
            else:
                # if not, then we might be on GoogleAppEngine, check their request object cookies
                if hasattr(request,'cookie'):
                    params = self.validate_cookie_signature(request.cookies)

        if not params:
            return False

        if params.get('in_canvas') == '1':
            fb.in_canvas = True

        if params.get('added') == '1':
            fb.added = True

        if params.get('expires'):
            fb.session_key_expires = int(params['expires'])

        if 'friends' in params:
            if params['friends']:
                fb._friends = params['friends'].split(',')
            else:
                fb._friends = []

        if 'session_key' in params:
            fb.session_key = params['session_key']
            if 'user' in params:
                fb.uid = params['user']
            elif 'page_id' in params:
                fb.page_id = params['page_id']
            else:
                return False
        elif 'profile_session_key' in params:
            fb.session_key = params['profile_session_key']
            if 'profile_user' in params:
                fb.uid = params['profile_user']
            else:
                return False
        else:
            return False

        return True
        
    def validate_cookie_signature(self, cookies):
        """
        Validate parameters passed by cookies, namely facebookconnect or js api.
        """
        
        if not self.api_key in cookies.keys():
            return None

        sigkeys = []
        params = dict()
        for k in sorted(cookies.keys()):
            if k.startswith(self.api_key+"_"):
                sigkeys.append(k)
                params[k.replace(self.api_key+"_","")] = cookies[k].value

        vals = ''.join(['%s=%s' % (x.replace(self.api_key+"_",""), cookies[x].value) for x in sigkeys])
        hasher = md5.new(vals)
        
        hasher.update(self.secret_key)
        digest = hasher.hexdigest()
        if digest == cookies[self.api_key].value:
            return params
        else:
            return False

cherrypy.tools.facebook = FacebookTool(gearshift.config)

__all__ = ["FacebookTool"]
