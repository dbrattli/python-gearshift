"""Classes and methods for GearShift controllers."""

import logging
import re
import urllib
import types
import cherrypy
from cherrypy import request, response, url as cp_url

import gearshift.util as tg_util
from gearshift import view, errorhandling, config
from gearshift.validators import Invalid
from gearshift.errorhandling import error_handler, exception_handler
from gearshift import identity
from gearshift import tools

log = logging.getLogger("gearshift.controllers")

class BadFormatError(Exception):
    """Output-format exception."""


class ValidatorTool(cherrypy.Tool):
    def __init__(self):
        log.debug("ValidatorTool initialized")
        
        return super(ValidatorTool, self).__init__(point="before_handler", 
                                                   callable=self.validate,
                                                   priority=50)
    
    def validate(self, form=None, validators=None,
                 failsafe_schema=errorhandling.FailsafeSchema.none,
                 failsafe_values=None, state_factory=None):
        """Validate input.

        @param form: a form instance that must be passed throught the validation
        process... you must give a the same form instance as the one that will
        be used to post data on the controller you are putting the validate
        decorator on.
        @type form: a form instance

        @param validators: individual validators to use for parameters.
        If you use a schema for validation then the schema instance must
        be the sole argument.
        If you use simple validators, then you must pass a dictionary with
        each value name to validate as a key of the dictionary and the validator
        instance (eg: tg.validators.Int() for integer) as the value.
        @type validators: dictionary or schema instance

        @param failsafe_schema: a schema for handling failsafe values.
        The default is 'none', but you can also use 'values', 'map_errors',
        or 'defaults' to map erroneous inputs to values, corresponding exceptions
        or method defaults.
        @type failsafe_schema: errorhandling.FailsafeSchema

        @param failsafe_values: replacements for erroneous inputs. You can either
        define replacements for every parameter, or a single replacement value
        for all parameters. This is only used when failsafe_schema is 'values'.
        @type failsafe_values: a dictionary or a single value

        @param state_factory: If this is None, the initial state for validation
        is set to None, otherwise this must be a callable that returns the initial
        state to be used for validation.
        @type state_factory: callable or None

        """

        if callable(form) and not hasattr(form, "validate"):
            form = form()

        # do not validate a second time if already validated
        if hasattr(request, 'validation_state'):
            return

        kw = request.params

        errors = {}
        if state_factory is not None:
            state = state_factory()
        else:
            state = None

        if form:
            value = kw.copy()
            try:
                kw.update(form.validate(value, state))
            except Invalid, e:
                errors = e.unpack_errors()
                request.validation_exception = e
            request.validated_form = form

        if validators:
            if isinstance(validators, dict):
                for field, validator in validators.iteritems():
                    try:
                        kw[field] = validator.to_python(
                            kw.get(field, None), state)
                    except Invalid, error:
                        errors[field] = error
            else:
                try:
                    value = kw.copy()
                    kw.update(validators.to_python(value, state))
                except Invalid, e:
                    errors = e.unpack_errors()
                    request.validation_exception = e
        request.validation_errors = errors
        request.input_values = kw.copy()
        request.validation_state = state

        if errors:
            request.params['tg_errors'] = errors

# Tools stay here for now
cherrypy.tools.validate = ValidatorTool()
validate = cherrypy.tools.validate
cherrypy.tools.expose = tools.ExposeTool()
expose = render = cherrypy.tools.expose
flash = tools.FlashTool()
cherrypy.tools.markup = tools.MarkupTool()
markup = cherrypy.tools.markup
cherrypy.tools.elements = tools.ElementTool()
elements = cherrypy.tools.elements

class Controller(object):
    """Base class for a web application's controller.

    Currently, this provides positional parameters functionality
    via a standard default method.

    """

class RootController(Controller):
    """Base class for the root of a web application.

    Your web application should have one of these. The root of
    your application is used to compute URLs used by your app.

    """
    is_app_root = True
    
Root = RootController

class RestController(Controller):
    """The RestController must be used together with RestDispatcher. The 
    RestController uses the _cp_dispatch feature to collect the parameters
    between the resource names. It also makes it possible to set custom
    "id"" names for each controller in config."""
    
    _cp_config = {}
    
    def _cp_dispatch(self, vpath):
        request = cherrypy.request
        config = cherrypy.config
                
        if not vpath:
            # No vpath, bailing out
            return None

        # first entry in vpath must be a REST parameter
        param = vpath[0]
        
        # Check if param has format is specified such as 3.xml, 3.json etc
        if "." in param:
            param, ext = param.rsplit('.', 1)
            format = self._cp_config.get('rest_format', 'tg_format')
            request.params[format] = ext
        
        # Check if request is for a single item or for all items
        if len(vpath) == 1 and param != self._cp_config.get('rest_allname', 'all'):
            request.tg_rest_get_one = True
    
        # Add parameter to CherryPy params
        request.params[self._cp_config.get('rest_idname', 'id')] = param
        return self
        
def url(tgpath, tgparams=None, **kw):
    """Computes URLs.

    tgpath can be a list or a string. If the path is absolute (starts
    with a "/"), the server.webpath, SCRIPT_NAME and the approot of the
    application are prepended to the path. In order for the approot to
    be detected properly, the root object should extend
    controllers.RootController.

    Query parameters for the URL can be passed in as a dictionary in
    the second argument *or* as keyword parameters.

    Values which are a list or a tuple are used to create multiple
    key-value pairs.

    """
    if not isinstance(tgpath, basestring):
        tgpath = "/".join(list(tgpath))
    webpath = config.server.get("server.webpath", "")
    if tg_util.request_available():
        tgpath = webpath + cp_url(tgpath, relative = 'server')
    elif tgpath.startswith("/"):
        tgpath = webpath + tgpath
    if tgparams is None:
        tgparams = kw
    else:
        try:
            tgparams = tgparams.copy()
            tgparams.update(kw)
        except AttributeError:
            raise TypeError('url() expects a dictionary for query parameters')
    args = []
    for key, value in tgparams.iteritems():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            pairs = [(key, v) for v in value]
        else:
            pairs = [(key, value)]
        for k, v in pairs:
            if v is None:
                continue
            if isinstance(v, unicode):
                v = v.encode('utf8')
            args.append((k, str(v)))
    if args:
        query_string = urllib.urlencode(args, True)
        if '?' in tgpath:
            tgpath += '&' + query_string
        else:
            tgpath += '?' + query_string
    return tgpath


def redirect(redirect_path, redirect_params=None, **kw):
    """Redirect (via cherrypy.HTTPRedirect).

    Raises the exception instead of returning it, this to allow
    users to both call it as a function or to raise it as an exception.

    """
    newpath = url(tgpath=redirect_path, tgparams=redirect_params, **kw)
    raise cherrypy.HTTPRedirect(newpath)


__all__ = [
    "Controller",
    "error_handler",
    "exception_handler",
    "expose",
    "redirect",
    "Root",
    "RootController",
    "RestController"
    "url",
    "validate",
]
