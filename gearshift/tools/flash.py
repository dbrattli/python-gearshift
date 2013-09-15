import logging

import cherrypy
from cherrypy import request, response
from gearshift import config

import gearshift.util as tg_util

log = logging.getLogger("gearshift.flash")

class FlashTool(cherrypy.Tool):
    """A TurboGears Flash Tool"""

    def __init__(self, commit_veto=None):        
        
        log.debug("Flash Tool initialized")
        
        # Lower the priority to make it run before expose (default=50)
        return super(FlashTool, self).__init__(point="before_handler", 
                                               callable=self.before_handler,
                                               priority=30)

    def get_flash(self):
        """Retrieve the flash message (if one is set), clearing the message."""
        request_cookie = request.cookie
        response_cookie = response.cookie

        def clearcookie():
            response_cookie["tg_flash"] = ""
            response_cookie["tg_flash"]['expires'] = 0
            response_cookie['tg_flash']['path'] = '/'

        if response_cookie.has_key("tg_flash"):
            message = response_cookie["tg_flash"].value
            response_cookie.pop("tg_flash")
            if request_cookie.has_key("tg_flash"):
                # New flash overrided old one sitting in cookie. Clear that old cookie.
                clearcookie()
            
        elif request_cookie.has_key("tg_flash"):
            message = request_cookie["tg_flash"].value
            if not response_cookie.has_key("tg_flash"):
                clearcookie()
        else:
            message = None
        if message:
            message = unicode(tg_util.unquote_cookie(message), 'utf-8')
    
        return message
                
    def before_handler(self):
        if cherrypy.request.handler is None:
            return
            
        # Replace request.handler with self
        oldhandler = cherrypy.request.handler
        
        def wrap(*args, **kwargs):
            return self.handler(oldhandler, *args, **kwargs)
            
        cherrypy.request.handler = wrap
                
    def handler(self, oldhandler, *args, **kwargs):
        output = oldhandler(*args, **kwargs)

        if not isinstance(output, dict):
            # Nothing for us to do
            return output

        tg_flash = self.get_flash()
        if tg_flash:
            output["tg_flash"] = tg_flash
        elif config.get("tg.empty_flash", True):
            output["tg_flash"] = None

        return output
                
    def __call__(self, message):
        """Set a message to be displayed in the browser on next page display."""
        
        logging.info("Setting flash: %s" % message)
        
        message = tg_util.quote_cookie(tg_util.to_utf8(message))
        response.cookie['tg_flash'] = message
        response.cookie['tg_flash']['path'] = '/'

__all__ = ["FlashTool"]
