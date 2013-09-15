import logging
try:
	from hashlib import sha1
except ImportError:
	from sha import sha as sha1
import threading
import time

from random import random
from datetime import timedelta, datetime

import cherrypy
from cherrypy import request

from gearshift import config
from gearshift.util import load_class
from gearshift.identity.base import verify_identity_status

log = logging.getLogger("gearshift.visit")

# Global VisitManager
_manager = None

# Global list of plugins for the Visit Tracking framework
_plugins = list()

# Accessor functions for getting and setting the current visit information.
def current():
    """Retrieve the current visit record from the cherrypy request."""
    return getattr(cherrypy.request, "tg_visit", None)

def set_current(visit):
    """Set the current visit record on the cherrypy request being processed."""
    cherrypy.request.tg_visit = visit

def _create_visit_manager(timeout):
    """Create a VisitManager based on the plugin specified in the config file."""
    plugin_name = config.get("tools.visit.manager", 
                             "gearshift.visit.sovisit.SqlObjectVisitManager")

    try:
        plugin = load_class(plugin_name)
    except Exception, e:
        log.error("Error loading visit plugin '%s': %s", plugin_name, e)
        raise RuntimeError("VisitManager plugin missing: %s" % plugin_name)
     
    log.debug("Loading visit manager from plugin: %s", plugin_name)
    return plugin(timeout)

# Interface for the TurboGears extension


def shutdown_extension():
    # Bail out if this extension is not running.
    global _manager
    if not _manager:
        return
    log.info("Visit Tracking shutting down")
    _manager.shutdown()
    _manager = None

def create_extension_model():
    """Create the data model of the VisitManager if one exists."""
    if _manager:
        _manager.create_model()

def enable_visit_plugin(plugin):
    """Register a visit tracking plugin.

    These plugins will be called for each request.

    """
    _plugins.append(plugin)

class Visit(object):
    """Basic container for visit related data."""

    def __init__(self, key, is_new):
        self.key = key
        self.is_new = is_new

class VisitTool(cherrypy.Tool):
    """A tool that automatically tracks visitors."""

    def __init__(self):
        log.debug("Visit tool initialised")

##        start_extension()

        # Raise priority since we need the VisitTool to run as early as 
        # possible
        return super(VisitTool, self).__init__(point="before_handler", 
                                               callable=self.before_handler,
                                               priority=20)

    def start_extension(self):
        # Bail out if the application hasn't enabled this extension
        if not config.get("tools.visit.on", False):
            return
        # Bail out if this extension is already running
        global _manager
        if _manager:
            return

        log.info("Visit Tracking starting")
        # How long may the visit be idle before a new visit ID is assigned?
        # The default is 20 minutes.
        timeout = timedelta(minutes=config.get("tools.visit.timeout", 20))
        # Create the thread that manages updating the visits
        _manager = _create_visit_manager(timeout)

    def before_handler(self, **kw):
        """Check whether submitted request belongs to an existing visit."""

        get = kw.get
        # Where to look for the session key in the request and in which order
        source = [s.strip().lower() for s in 
            kw.get('source', 'cookie').split(',')]
        if set(source).difference(('cookie', 'form')):
            log.warning("Unsupported 'tools.visit.source' '%s' in configuration.")
        # Get the name to use for the identity cookie.
        self.cookie_name = get("cookie.name", "tg-visit")
        # and the name of the request param. MUST NOT contain dashes or dots,
        # otherwise the NestedVariablesFilter will chocke on it.
        visit_key_param = get("form.name", "tg_visit")
        # TODO: The path should probably default to whatever
        # the root is masquerading as in the event of a
        # virtual path filter.
        self.cookie_path = get("cookie.path", "/")
        # The secure bit should be set for HTTPS only sites
        self.cookie_secure = get("cookie.secure", False)
        # By default, I don't specify the cookie domain.
        self.cookie_domain = get("cookie.domain", None)
        assert self.cookie_domain != "localhost", "localhost" \
            " is not a valid value for visit.cookie.domain. Try None instead."
        # Use max age only if the cookie shall explicitly be permanent
        self.cookie_max_age = get("cookie.permanent",
            False) and int(get("timeout", "20")) * 60 or None

        cpreq = cherrypy.request
        visit = current()
        if not visit:
            visit_key = None
            for source in source:
                if source == 'cookie':
                    visit_key = cpreq.cookie.get(self.cookie_name)
                    if visit_key:
                        visit_key = visit_key.value
                        log.debug("Retrieved visit key '%s' from cookie '%s'.",
                            visit_key, self.cookie_name)
                elif source == 'form':
                    visit_key = cpreq.params.pop(visit_key_param, None)
                    log.debug(
                        "Retrieved visit key '%s' from request param '%s'.",
                        visit_key, visit_key_param)
                if visit_key:
                    visit = _manager.visit_for_key(visit_key)
                    break
            if visit:
                log.debug("Using visit from request with key: %s", visit_key)
            else:
                visit_key = self._generate_key()
                visit = _manager.new_visit_with_key(visit_key)
                log.debug("Created new visit with key: %s", visit_key)
            self.send_cookie(visit_key)
            set_current(visit)
        # Inform all the plugins that a request has been made for the current
        # visit. This gives plugins the opportunity to track click-path or
        # retrieve the visitor's identity.
        try:
            for plugin in _plugins:
                plugin.record_request(visit)
        except cherrypy.InternalRedirect, e:
            # Can't allow an InternalRedirect here because CherryPy is dumb,
            # instead change cherrypy.request.path_info to the url desired.
            cherrypy.request.path_info = e.path

    def _generate_key():
        """Return a (pseudo)random hash based on seed."""
        # Adding remote.ip and remote.port doesn't make this any more secure,
        # but it makes people feel secure... It's not like I check to make
        # certain you're actually making requests from that host and port. So
        # it's basically more noise.
        key_string = '%s%s%s%s' % (random(), datetime.now(),
            cherrypy.request.remote.ip, cherrypy.request.remote.port)
        return sha1(key_string).hexdigest()
    _generate_key = staticmethod(_generate_key)

    def clear_cookie(self):
        """Clear any existing visit ID cookie."""
        cookies = cherrypy.response.cookie
        # clear the cookie
        log.debug("Clearing visit ID cookie")
        cookies[self.cookie_name] = ''
        cookies[self.cookie_name]['path'] = self.cookie_path
        cookies[self.cookie_name]['expires'] = ''
        cookies[self.cookie_name]['max-age'] = 0

    def send_cookie(self, visit_key):
        """Send an visit ID cookie back to the browser."""
        cookies = cherrypy.response.cookie
        cookies[self.cookie_name] = visit_key
        cookies[self.cookie_name]['path'] = self.cookie_path
        if self.cookie_secure:
            cookies[self.cookie_name]['secure'] = True
        if self.cookie_domain:
            cookies[self.cookie_name]['domain'] = self.cookie_domain
        max_age = self.cookie_max_age
        if max_age:
            # use 'expires' because MSIE ignores 'max-age'
            cookies[self.cookie_name]['expires'] = '"%s"' % time.strftime(
                "%a, %d-%b-%Y %H:%M:%S GMT",
                time.gmtime(time.time() + max_age))
            # 'max-age' takes precedence on standard conformant browsers
            # (this is better because there of no time sync issues here)
            cookies[self.cookie_name]['max-age'] = max_age
        log.debug("Sending visit ID cookie: %s",
            cookies[self.cookie_name].output())


class BaseVisitManager(threading.Thread):

    def __init__(self, timeout):
        super(BaseVisitManager, self).__init__(name="VisitManager")
        self.timeout = timeout
        self.queue = dict()
        self.lock = threading.Lock()
        self._shutdown = threading.Event()
        self.interval = 30
        self.setDaemon(True)
        # We need to create the visit model before the manager thread is
        # started.
        self.create_model()
        self.start()

    def create_model(self):
        pass

    def new_visit_with_key(self, visit_key):
        """Return a new Visit object with the given key."""
        raise NotImplementedError

    def visit_for_key(self, visit_key):
        """Return the visit for this key.

        Return None if the visit doesn't exist or has expired.

        """
        raise NotImplementedError

    def update_queued_visits(self, queue):
        """Extend the expiration of the queued visits."""
        raise NotImplementedError

    def update_visit(self, visit_key, expiry):
        try:
            self.lock.acquire()
            self.queue[visit_key] = expiry
        finally:
            self.lock.release()

    def shutdown(self, timeout=None):
        self._shutdown.set()
        self.join(timeout)
        if self.isAlive():
            log.error("Visit Manager thread failed to shutdown.")

    def run(self):
        while not self._shutdown.isSet():
            self.lock.acquire()
            queue = None
            try:
                # make a copy of the queue and empty the original
                if self.queue:
                    queue = self.queue.copy()
                    self.queue.clear()
            finally:
                self.lock.release()
            if queue is not None:
                self.update_queued_visits(queue)
            self._shutdown.wait(self.interval)
