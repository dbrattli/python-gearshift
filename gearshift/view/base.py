"""Template processing for TurboGears view templates."""

import sys
import re
import logging
from itertools import chain, imap
from itertools import cycle as icycle
from urllib import quote_plus

import cherrypy

import gearshift
from gearshift import identity, config
from gearshift.i18n import get_locale
from gearshift.util import (
    Bunch, get_template_encoding_default,
    get_mime_type_for_format, mime_type_has_charset)

log = logging.getLogger("gearshift.view")

variable_providers = []
root_variable_providers = []

class cycle:
    """Loops forever over an iterator.

    Wraps the itertools.cycle method, but provides a way to get the current
    value via the 'value' attribute.

    """
    value = None

    def __init__(self, iterable):
        self._cycle = icycle(iterable)

    def __str__(self):
        return self.value.__str__()

    def __repr__(self):
        return self.value.__repr__()

    def next(self):
        self.value = self._cycle.next()
        return self.value


def selector(expression):
    """If the expression is true, return the string 'selected'.

    Useful for HTML <option>s.

    """
    if expression:
        return "selected"
    else:
        return None


def checker(expression):
    """If the expression is true, return the string "checked".

    This is useful for checkbox inputs.

    """
    if expression:
        return "checked"
    else:
        return None


def ipeek(iterable):
    """Lets you look at the first item in an iterator.

    This is a good way to verify that the iterator actually contains something.
    This is useful for cases where you will choose not to display a list or
    table if there is no data present.

    """
    iterable = iter(iterable)
    try:
        item = iterable.next()
        return chain([item], iterable)
    except StopIteration:
        return None

def stdvars():
    """Create a Bunch of variables that should be available in all templates.

    These variables are:

    checker
        the checker function
    config
        the cherrypy config get function
    cycle
        cycle through a set of values
    errors
        validation errors
    identity
        the current visitor's identity information
    inputs
        input values from a form
    ipeek
        the ipeek function
    locale
        the default locale
    quote_plus
        the urllib quote_plus function
    request
        the cherrypy request
    selector
        the selector function
    session
        the current cherrypy.session if the session_filter.on it set
        in the app.cfg configuration file. If it is not set then session
        will be None.
    tg_js
        the url path to the JavaScript libraries
    tg_static
        the url path to the TurboGears static files
    tg_toolbox
        the url path to the TurboGears toolbox files
    tg_version
        the version number of the running TurboGears instance
    url
        the gearshift.url function for creating flexible URLs

    Additionally, you can add a callable to gearshift.view.variable_providers
    that can add more variables to this list. The callable will be called with
    the vars Bunch after these standard variables have been set up.

    """

    if config.get('tools.sessions.on', None):
        session = cherrypy.session
    else:
        session = None

    webpath = '' ## FIXME: gearshift.startup.webpath or 
    tg_vars = Bunch(
        checker = checker,
        config = config.get,
        cycle = cycle,
        errors = getattr(cherrypy.request, 'validation_errors', {}),
        identity = identity.current,
        inputs = getattr(cherrypy.request, 'input_values', {}),
        ipeek = ipeek,
        locale = get_locale(),
        quote_plus = quote_plus,
        request = cherrypy.request,
        selector = selector,
        session = session,
        tg_js = '/' + webpath + 'tg_js',
        tg_static = '/' + webpath + 'tg_static',
        tg_toolbox = '/' + webpath + 'tg_toolbox',
        tg_version = gearshift.__version__,
        url = gearshift.url,
        widgets = '/' + webpath + 'tg_widgets',
    )
    for provider in variable_providers:
        provider(tg_vars)
    root_vars = dict()
    for provider in root_variable_providers:
        provider(root_vars)
    root_vars['tg'] = tg_vars
    
    # Deprecated but keep them here anyway for now
    root_vars['tg_js_head'] = []
    root_vars['tg_js_bodytop'] = []
    root_vars['tg_js_bodybottom'] = []
    
    return root_vars

# def load_engines():
#     """Load and initialize all templating engines.
# 
#     This is called during startup after the configuration has been loaded.
#     You can call this earlier if you need the engines before startup;
#     the engines will then be reloaded with the custom configuration later.
# 
#     """
#     get = config.get
#     engine_options = {
#         "cheetah.importhooks": get("cheetah.importhooks", False),
#         "cheetah.precompiled": get("cheetah.precompiled", False),
# 
# #        "genshi.encoding": get("genshi.encoding", "utf-8"),
# #        "genshi.default_doctype": get("genshi.default_doctype", 'html'),
#         "genshi.lookup_errors": get("genshi.lookup_errors", "strict"),
# #        "genshi.loader_callback" : get("genshi.loader_callback", None),
#         
#         "json.skipkeys": get("json.skipkeys", False),
#         "json.sort_keys": get("json.sort_keys", False),
#         "json.check_circular": get("json.check_circular", True),
#         "json.allow_nan": get("json.allow_nan", True),
#         "json.indent": get("json.indent", None),
#         "json.separators": get("json.separators", None),
#         "json.ensure_ascii": get("json.ensure_ascii", False),
#         "json.encoding": get("json.encoding", "utf-8"),
#         "json.assume_encoding": get("json.assume_encoding", "utf-8"),
#         "json.descent_bases": get("json.descent_bases", get("turbojson.descent_bases", True)),
#         "kid.encoding": get("kid.encoding", "utf-8"),
#         "kid.assume_encoding": get("kid.assume_encoding", "utf-8"),
#         "kid.precompiled": get("kid.precompiled", False),
#         "kid.i18n.run_template_filter": get("i18n.run_template_filter", False),
#         "kid.i18n_filter": i18n_filter,
#         "kid.sitetemplate": get("tg.sitetemplate", "gearshift.view.templates.sitetemplate"),
#         "kid.reloadbases": get("kid.reloadbases", False),
#         "mako.directories": get("mako.directories", ['']),
#         "mako.output_encoding": get("mako.output_encoding", "utf-8")
#     }
