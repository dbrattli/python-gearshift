"""Things to do when the TurboGears server is started."""

__all__ = [
    'call_on_startup',
    'call_on_shutdown',
    'reloader_thread',
    'start_bonjour',
    'stop_bonjour',
    'start_server',
    'startTurboGears',
    'stopTurboGears',
]

import logging
import os
import sys

from os.path import abspath, exists

import cherrypy

from gearshift import config, database, view
from gearshift.visit.api import VisitTool
#from gearshift.database.so import hub_registry

from gearshift import controllers
from gearshift import visit
from gearshift.tools.identity import IdentityTool
from gearshift import identity
    
try:
    import tools.toscawidgets as toscawidgets
    have_toscawidgets = True
except ImportError:
    have_toscawidgets = False
    
try:
    from gearshift.tools.oauth import OAuthTool
    have_oauth = True
except ImportError:
    have_oauth = False

# module globals
call_on_startup = []
call_on_shutdown = []
log = logging.getLogger("gearshift.startup")

# Config is tricky with CP3. We must make sure that all application specific
# config is available at mount time, and startTurboGears() is too late. The
# safest thing to do is just to do it at import time.

# Decode filter is deprecated in CherryPy 3.2
if cherrypy.__version__.split(".") < ['3', '2', '0']:
    config.update({'/': {
        # Add decoding filter. Use this tool to decode cherrypy.request.params
        # (GET and POST query arguments) from on-the-wire strings to Unicode. If
        # you think you know exactly what encoding the client used, and want to
        # be strict about it, set tools.decode.encoding; otherwise, set
        # tools.decode.default_encoding as needed (it defaults to UTF-8). Note
        # that, if the encodings you supply fail, the tool will fall back to
        # decoding from ISO-8859-1 (as the HTTP spec requires).
        'tools.decode.on' : True,
    }})
    
config.update({'/': {
    # Encode the outgoing response body, from Unicode to an encoded string.
    # The tool will use the 'Accept-Charset' request header to attempt to
    # provide suitable encodings, usually attempting utf-8 if the client
    # doesn't specify a charset, but following RFC 2616 and trying
    # ISO-8859-1 if the client sent an empty 'Accept-Charset' header.
    'tools.encode.on' : True,
    'tools.encode.encoding' : 'utf-8'
}})

# Identity must be available at import time because its also a decorator
cherrypy.tools.identity = IdentityTool()
identity.require = cherrypy.tools.identity

cherrypy.tools.visit = VisitTool()

def startTurboGears():
    """Handles TurboGears tasks when the CherryPy server starts.

    This adds the "tg_js" configuration to make MochiKit accessible.
    It also turns on stdlib logging when in development mode.

    """
    conf = config.get

#    cherrypy.tools.visit = VisitTool()
    cherrypy.tools.expose = controllers.expose
    cherrypy.tools.flash = controllers.flash
    
    cherrypy.tools.visit.start_extension()
    cherrypy.tools.identity.start_extension()

    if have_toscawidgets:
        toscawidgets.start_extension()

    if have_oauth:
        cherrypy.tools.oauth = OAuthTool()

    # Bind metadata for SQLAlchemy
    if conf('sqlalchemy.dburi'):
        database.bind_metadata()

    # Call registered startup functions
    for item in call_on_startup:
        item()

    # Start the scheduler
    ## No more scheduler. It's useless with both the App Engine and with WSGI
    
def stopTurboGears():
    """Handles TurboGears tasks when the CherryPy server stops.

    Ends all open database transactions, shuts down all extensions, calls user
    provided shutdown functions and stops the scheduler.

    """
    # end all transactions and clear out the hubs to
    # help ensure proper reloading in autoreload situations
#    for hub in hub_registry:
#        hub.end()
#    hub_registry.clear()

    #  Stops all TurboGears extensions
    visit.shutdown_extension()

    for item in call_on_shutdown:
        item()

def start_server(root):
    app = cherrypy.tree.mount(root, config=config.app)

    if config.get("tg.fancy_exception", False):
        from paste import evalexception
        app.wsgiapp.pipeline.append(
            ('paste_exc', evalexception.middleware.EvalException))

    cherrypy.engine.start()
    cherrypy.engine.block()

# Subscribe to engine events at import time so that our callbacks get used
#  regardless of how the server is started.
cherrypy.engine.subscribe('start', startTurboGears)
cherrypy.engine.subscribe('stop', stopTurboGears)
