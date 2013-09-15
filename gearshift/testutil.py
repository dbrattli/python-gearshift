import os
import types
import logging
import string
import unittest
import cStringIO as StringIO

import cherrypy
from cherrypy.process.wspbus import states
from webtest import TestApp

try:
    import sqlobject
    from sqlobject.inheritance import InheritableSQLObject
except ImportError:
    sqlobject = None
try:
    import sqlalchemy
except ImportError:
    sqlalchemy = None

from gearshift import startup, config, update_config, \
    controllers, database, validators
from gearshift.identity import current_provider
#from gearshift.util import get_model

cwd = os.getcwd()

# For clean tests, remove all compiled Kid templates
for w in os.walk('.'):
    if not os.sep + '.' in w[0]:
        for f in w[2]:
            if f.endswith('.kid'):
                f = os.path.join(w[0], f[:-3] + 'pyc')
                if os.path.exists(f):
                    os.remove(f)

# Load test configuration
if os.path.exists('test.cfg'):
    # Look for a 'config' package
    for dirpath, dirs, dummy2 in os.walk('.'):
        basename = os.path.basename(dirpath)
        dirname = os.path.normpath(os.path.dirname(dirpath))
        init_py = os.path.join(dirpath, '__init__.py')
        if basename == 'config' and os.path.exists(init_py) and \
                dirname[0] in string.ascii_letters + '_':
            modulename = "%s.app" % dirpath[2:].replace(os.sep, ".")
            break
    else:
        modulename = None
    update_config(configfile="test.cfg", modulename=modulename)
else:
    database.set_db_uri("sqlite:///:memory:")

config.update({'global':
        {'autoreload.on': False, 'tg.new_style_logging': True, 'tools.expose.on' : True}})


def start_server():
    """Start the server if it's not already."""
    if not config.get("cp_started"):
        cherrypy.engine.start()
        config.update({"cp_started" : True})

    if not config.get("server_started"):
        startup.startTurboGears()
        config.update({"server_started" : True})


def stop_server(tg_only = False):
    """Stop the server and unmount the application.  \
    Use tg_only = True to leave CherryPy running (for faster tests).
    """
    unmount()
    if not tg_only:
        if not cherrypy.engine.state in [states.STOPPED]:
            cherrypy.engine.exit()
        config.update({"cp_started" : False})

    if config.get("cp_started") and not tg_only:
       cherrypy.server.stop()
       config.update({"cp_started" : False})

    if config.get("server_started"):
        startup.stopTurboGears()
        config.update({"server_started" : False})


def make_wsgiapp():
    """Return a WSGI application from cherrypy's root object."""
    return cherrypy.tree


def make_app(controller=None, conf=None):
    """Return a WebTest.TestApp instance from Cherrypy.

    If a Controller object is provided, it will be mounted at the root level.
    If not, it'll look for an already mounted root.

    """
    
    if conf:
        config.app.update(conf)
    
    if controller:
        wsgiapp = mount(controller(), '/')
    else:
        wsgiapp = make_wsgiapp()
    return TestApp(wsgiapp)


class TGTest(unittest.TestCase):
    """A WebTest enabled unit testing class.

    To use, subclass & set root to your controller object, or set app to a 
    webtest.TestApp instance.  

    In your tests, use self.app to make WebTest calls.
    """

    root = None
    app = None
    stop_tg_only = False

    def setUp(self):
        """Set up the WebTest by starting the server.

        You should override this and make sure you have properly
        mounted a root for your server before calling super,
        or simply pass a root controller to super.
        Otherwise the Cherrypy filters for TurboGears will not be used.
        """
        assert self.root or self.app, "Either self.root or self.app must be set"
        if not self.app: 
            self.app = make_app(self.root) 
        start_server()

    def tearDown(self):
        """Tear down the WebTest by stopping the server."""
        stop_server(tg_only = self.stop_tg_only)

    def login_user(self, user):
        """Log a specified user object into the system."""
        self.app.post(config.get('tools.identity.failure_url'), dict(
            user_name=user.user_name, password=user.password, login='Login'))


class BrowsingSession(object):

    def __init__(self):
        self.visit = None
        self.response, self.status = None, None
        self.cookie = {}
        self.app = make_app()

    def goto(self, path, headers=None, **kwargs):
        if headers is None:
            headers = {}
        if self.cookie:
            headers['Cookie'] = self.cookie_encoded
        response = self.app.get(path, headers=headers, **kwargs)

        # If we were given an encoding in the content type we should use it to
        # decode the response:
        ctype_parts = response.headers['Content-Type'].split(';')
        for parameter in ctype_parts[1:]:
            attribute, value = parameter.strip().split('=')
            try:
                self.unicode_response = response.body.decode(value)
                break
            except:
                # If the named encoding doesn't work then it doesn't work.  We
                # just won't create the unicode_response field.
                pass

        self.response = response.body
        self.full_response = response
        self.status = response.status
        self.cookie = response.cookies_set
        self.cookie_encoded = response.headers.get('Set-Cookie', '')


class AbstractDBTest(unittest.TestCase):
    """A database enabled unit testing class.

    Creates and destroys your database before and after each unit test. 
    You must set the model attribute in order for this class to 
    function correctly.
    """
    model = None

    def setUp(self):
        raise NotImplementedError()

    def tearDown(self):
        raise NotImplementedError()

class DBTestSO(AbstractDBTest):
    def _get_soClasses(self):
        try:
            return [self.model.__dict__[x] for x in self.model.soClasses]
        except AttributeError:
            return self.model.__dict__.values()

    def setUp(self):
        if not self.model:
            self.model = get_model()
            if not self.model:
                raise Exception("Unable to run database tests without a model")
        for item in self._get_soClasses():
            if isinstance(item, types.TypeType) and issubclass(item,
                sqlobject.SQLObject) and item != sqlobject.SQLObject \
                and item != InheritableSQLObject:
                item.createTable(ifNotExists=True)

    def tearDown(self):
        database.rollback_all()
        for item in reversed(self._get_soClasses()):
            if isinstance(item, types.TypeType) and issubclass(item,
                sqlobject.SQLObject) and item != sqlobject.SQLObject \
                and item != InheritableSQLObject:
                item.dropTable(ifExists=True, cascade=True)

class DBTestSA(AbstractDBTest):
    def setUp(self):
        database.get_engine()
        database.metadata.create_all()

    def tearDown(self):
        database.metadata.drop_all()


#Determine which class to use for "DBTest".  Setup & teardown should behave 
#simularly regardless of which ORM you choose.
if config.get("sqlobject.dburi"):
    DBTest = DBTestSO
elif config.get("sqlalchemy.dburi"):
    DBTest = DBTestSA
else:
    raise Exception("Unable to find sqlalchemy or sqlobject dburi")


def unmount():
    """Remove an application from the object traversal tree."""
    for app in cherrypy.tree.apps.keys():
        del cherrypy.tree.apps[app]


def mount(controller, path="/"):
    """Mount a controller at a path.  Returns a wsgi application."""
    cherrypy.tree.mount(controller, path, config = config.app)
    return make_wsgiapp()

def catch_validation_errors(widget, value):
    """Catch and unpack validation errors (for testing purposes)."""
    try:
        value = widget.validate(value)
    except validators.Invalid, errors:
        try:
            errors = errors.unpack_errors()
        except AttributeError:
            pass
    else:
        errors = {}
    return value, errors


class MemoryListHandler(logging.Handler):

    def __init__(self):
        logging.Handler.__init__(self, level=logging.DEBUG)
        self.log = []

    def emit(self, record):
        print "Got record: %s" % record
        print "formatted as: %s" % self.format(record)
        self.log.append(self.format(record))

    def print_log(self):
        print "\n".join(self.log)
        self.log = []

    def get_log(self):
        log = self.log
        self.log = []
        return log

_memhandler = MemoryListHandler()


_currentcat = None


def capture_log(category):
    """Capture log for one category.

    The category can either be a single category (a string like 'foo.bar')
    or a list of them. You *must* call print_log() to reset when you're done.

    """
    global _currentcat
    assert not _currentcat, "_currentcat not cleared.  Use get_log to reset."
    if not isinstance(category, list) and not isinstance(category, tuple):
        category = [category]
    _currentcat = category
    for cat in category:
        log = logging.getLogger(cat)
        log.setLevel(logging.DEBUG)
        log.addHandler(_memhandler)


def _reset_logging():
    """Manage the resetting of the loggers."""
    global _currentcat
    if not _currentcat:
        return
    for cat in _currentcat:
        log = logging.getLogger(cat)
        log.removeHandler(_memhandler)
    _currentcat = None


def print_log():
    """Print the log captured by capture_log to stdout.

    Resets that log and resets the temporarily added handlers.

    """
    _reset_logging()
    _memhandler.print_log()


def get_log():
    """Return the list of log messages captured by capture_log.

    Resets that log and resets the temporarily added handlers.

    """
    _reset_logging()
    return _memhandler.get_log()


def sqlalchemy_cleanup():
    database.metadata.clear()
    try:
        database.metadata.dispose()
    except AttributeError: # not threadlocal
        if database.metadata.bind:
            database.metadata.bind.dispose()
    database._engine = None
    sqlalchemy.orm.clear_mappers()


__all__ = ["DBTest", "TGTest",
    "capture_log", "print_log", "get_log", "sqlalchemy_cleanup",
    "make_wsgiapp", "make_app", "start_server",
    "stop_server", "mount", "unmount"]
