import os, logging
import os.path

import gearshift
from gearshift import config

import cherrypy
from cherrypy import request

import opensocial
import opensocial.request

log = logging.getLogger("gearshift")

API_END_POINT = "http://www.google.com/friendconnect/api/"

class GFCTool(cherrypy.Tool):
    
    def __init__(self):
        log.debug("GFCTool initialized")
        
        self.site_id = config.get("gfc_consumer_key", ":").split(":")[1]
        
        return super(GFCTool, self).__init__(point='before_handler', 
                                             callable=self.before_handler, 
                                             priority=10)
                
    def before_handler(self, **kwargs):
##        log.debug("GFCTool:before_handler(), fcauth=%s" % "fcauth" + self.site_id)

        self.security_token = request.cookie.get("fcauth" + self.site_id, None)
        if self.security_token:
##            log.info("security token: %s", self.security_token.value)
            request.google_friend_connect = self.get_container()

    def get_current_user(self, user_id='@me'):
##        log.info("GFCTool:get_current_user()")
        container = self.get_container()
            
        me = container.fetch_person()
##        log.info(repr(me))
        return me

    def get_container(self):
        params = {
            "server_rest_base" : API_END_POINT,
            "security_token" : self.security_token.value,
            "security_token_param" : "fcauth",
        }
        gfc_config = opensocial.ContainerConfig(**params)
        return opensocial.ContainerContext(gfc_config)
    
__all__ = ["GFCTool"]
