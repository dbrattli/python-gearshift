import os, logging

import cherrypy

import tw
from tw.core import view
from tw.core.util import install_framework
from tw.mods.base import HostFramework
import tw.mods.cp3 as cp
default_view = 'genshi'

import gearshift
from gearshift.i18n.tg_gettext import gettext
from gearshift.view import stdvars

install_framework()

log = logging.getLogger(__name__)

class GearShift(HostFramework):
    @property
    def request_local(self):
        try:
            rl = cherrypy.request.tw_request_local
        except AttributeError:
            rl = self.request_local_class(cherrypy.request.wsgi_environ)
            cherrypy.request.tw_request_local = rl
        return rl

    def start_request(self, environ):
        self.request_local.default_view = self._default_view
        
    def url(self, url):
        """
        Returns the absolute path for the given url.
        """
        prefix = self.request_local.environ['toscawidgets.prefix']
        
        return '/' + gearshift.url(prefix+url).lstrip('/')

def start_extension():
    if not cherrypy.config.get('tools.toscawidgets.on', False):
        return

    engines = view.EngineManager()
    engines.load_all(cp._extract_config(), stdvars)
    
    host_framework = GearShift(
        engines = engines,
        default_view = cherrypy.config.get('tg.defaultview', default_view),
        translator = gettext,
        )
    prefix = cherrypy.config.get('toscawidgets.prefix', '/toscawidgets')
    host_framework.prefix = prefix
    host_framework.webpath = cherrypy.config.get('server.webpath', '')
    
    log.info("Loaded TW GearShift HostFramework")
    filter_args = dict(
        prefix = prefix,
        serve_files = cherrypy.config.get('toscawidgets.serve_files', 1)
        )
    
    cp.start_extension(host_framework, **filter_args)
