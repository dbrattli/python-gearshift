import logging

import cherrypy
from cherrypy import request, response

log = logging.getLogger("gearshift.elements")

try:
    import simplejson
except ImportError:
    try:
        from django.utils import simplejson # App Engine friendly
    except ImportError:
        log.error("SimpleJSON is not installed")
        simplejson = None

try:
    import elements
    have_elements = True
except ImportError:
    log.error("Elements is not installed")
    have_elements = False

import gearshift
from gearshift import util as tg_util

class ElementTool(cherrypy.Tool):
    """A CP3 tools for parsing XML/JSON using Elements

    For more information about Elements, see 
        http://code.google.com/p/python-elements/
        
    For GearShift it will probably be Atom Feeds and Entries, but you can
    define your own formats. Handles feeds and entries in both XML and JSON
    in GData format (http://code.google.com/intl/nb-NO/apis/gdata/json.html)
    """
    
    def __init__(self):
        log.info("ElementTool initialized")
        
        return super(ElementTool, self).__init__("before_handler", 
                                                 self.before_handler)

    def before_handler(self, **kwargs):
        # Remove tg_format from params list and stitch it into the request so
        # we can find it later. The controllers does not want this param
        if not hasattr(request, 'tg_format'):
            request.tg_format = request.params.pop('tg_format', None)

        if cherrypy.request.handler is None:
            return
            
        # Replace request.handler with self
        oldhandler = cherrypy.request.handler
        
        def wrap(*args, **kwargs):
            return self.handler(oldhandler, *args, **kwargs)
            
        cherrypy.request.handler = wrap

    def handler(self, oldhandler, *args, **kwargs):                
        content_type = request.headers.get('Content-Type', "")

        get = request.config.get
        allow_json = get('tools.elements.allow_json', False)

        element = get('tools.elements.element', None)
        if element:
            elem = element()

            if cherrypy.request.body:
                body = cherrypy.request.body.read()
            else:
                body = ""
            
            if "application/json" in content_type and allow_json:
                json = simplejson.loads(body)
                elem.from_dict(json)
            elif body:
                elem.from_string(body)
        
            # Put back in request params as tag or root element
            cherrypy.request.params[elem._tag] = elem

        output = oldhandler(*args, **kwargs)
        
        # If output is not a dict then it's nothing more for us to do
        if not isinstance(output, dict):
            return output

        # Get the tool decorator parameters
        allow_json = get('tools.elements.allow_json', False)
        as_format = get("tools.elements.as_format")
        accept_format = get("tools.elements.accept_format")
        content_type = get("tools.elements.content_type")

        accept = request.headers.get('Accept', "").lower()
        accept = tg_util.simplify_http_accept_header(accept)

        format = None
        tg_format = request.tg_format

        if allow_json and (tg_format=="json" or accept in ("application/json",
                                                           "text/javascript")):
            format = "json"
        elif as_format in ("default", tg_format) or accept_format in ("*/*", accept):
            format = "xml"
        else:
            # No format specified
            return output

        # Find Element object in output that we can process
        elem = None
        for key, value in output.items():
            if isinstance(value, elements.Element):
                elem = value
                break
                
        if not elem:
            return output
        
        # JSON or XML/Atom format
        if format == "json":
            output = simplejson.dumps(elem.to_dict())
            cherrypy.response.headers["Content-Type"] = "application/json"
        else:
            output =  elem.to_string()
            cherrypy.response.headers["Content-Type"] = content_type

        return output

    def __call__(self, element=None, *args, **kwargs):
        if args:
            raise TypeError("The %r Tool does not accept positional arguments"
                            " exept for 'element'; you must use keyword "
                            "arguments." % self._name)

        global have_elements
        if not have_elements:
            log.error('Elements (python-elements) is not installed')

        kwargs['element'] = element
                
        def tool_decorator(func):
            if not hasattr(func, "_cp_config"):
                func._cp_config = {}
                
            subspace = self.namespace + "." + self._name + "."
            func._cp_config[subspace + "on"] = True
            for k, v in kwargs.iteritems():
                func._cp_config[subspace + k] = v

            return func
        return tool_decorator
