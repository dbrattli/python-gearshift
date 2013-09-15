import logging

import cherrypy
from cherrypy import request, response

from gearshift import util as tg_util
from gearshift import config
from gearshift import view

from gearshift.tools.expose.render import render

log = logging.getLogger("gearshift.expose")

class ExposeTool(cherrypy.Tool):
    """A TurboGears compatible expose tool for CherryPy
    
    By putting the expose decorator on a method, you tell TurboGears that
    the method should be accessible via URL traversal. Additionally, expose
    handles the output processing (turning a dictionary into finished
    output) and is also responsible for ensuring that the request is
    wrapped in a database transaction.

    You can apply multiple expose decorators to a method, if
    you'd like to support multiple output formats. The decorator that's
    listed first in your code without as_format or accept_format is
    the default that is chosen when no format is specifically asked for.
    Any other expose calls that are missing as_format and accept_format
    will have as_format implicitly set to the whatever comes before
    the ":" in the template name (or the whole template name if there
    is no ":". For example, <code>expose("json")</code>, if it's not
    the default expose, will have as_format set to "json".

    When as_format is set, passing the same value in the tg_format
    parameter in a request will choose the options for that expose
    decorator. Similarly, accept_format will watch for matching
    Accept headers. You can also use both. expose("json", as_format="json",
    accept_format="application/json") will choose JSON output for either
    case: tg_format=json as a parameter or Accept: application/json as a
    request header.

    Passing allow_json=True to an expose decorator
    is equivalent to adding the decorator just mentioned.

    Each expose decorator has its own set of options, and each one
    can choose a different template or even template engine (you can
    use Kid for HTML output and Cheetah for plain text, for example).
    See the other expose parameters below to learn about the options
    you can pass to the template engine.

    Take a look at the
    <a href="tests/test_expose-source.html">test_expose.py</a> suite
    for more examples.

    @param template "templateengine:dotted.reference" reference along the
            Python path for the template and the template engine. For
            example, "kid:foo.bar" will have Kid render the bar template in
            the foo package.
    @keyparam format format for the template engine to output (if the
            template engine can render different formats. Kid, for example,
            can render "html", "xml" or "xhtml")
    @keyparam content_type sets the content-type http header
    @keyparam allow_json allow the function to be exposed as json
    @keyparam fragment for template engines (like Kid) that generate
            DOCTYPE declarations and the like, this is a signal to
            just generate the immediate template fragment. Use this
            if you're building up a page from multiple templates or
            going to put something onto a page with .innerHTML.
    @keyparam mapping mapping with options that are sent to the template
            engine
    @keyparam as_format designates which value of tg_format will choose
            this expose.
    @keyparam accept_format which value of an Accept: header will
            choose this expose.
    """

    def __init__(self):
        log.debug("Expose Tool initialized")

        super(ExposeTool, self).__init__(point="before_handler",
                                         callable=self.before_handler)
                
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
        output = oldhandler(*args, **kwargs)
        
        # If not a dict then output has been rendered and there's nothing left
        # for us to do, so bail out
        if not isinstance(output, dict):
            return output

        get = request.config.get
        exposes = get('tools.expose.exposes', dict(default={}))

        accept = request.headers.get('Accept', "").lower()
        accept = tg_util.simplify_http_accept_header(accept)
    
        tg_format = request.tg_format
                
        # Select the correct expose to use. First we trust tg_format, then 
        # accept headers, then fallback to default 
        for key in [tg_format, accept, 'default']:
            if exposes.has_key(key):
                expose = exposes[key]
                break
                
        # Unpack parameters that were supplied to @expose
        format = expose.get('format', get('tools.expose.format', None))
        template = expose.get('template', get('tools.expose.template', None))
        allow_json = expose.get('allow_json', get('tools.expose.allow_json', False))
        mapping = expose.get('mapping')
        fragment = expose.get('fragment')
        
        if format == "json" or (format is None and template is None):
            template = "json"
        
        if allow_json and (tg_format == "json" or
            accept in ("application/json", "text/javascript")):
            template = "json"
                
        if not template:
            template = format

        content_type = expose.get('content_type', 
                                  config.get("tg.content_type", None))

        if template and template.startswith("."):
            template = func.__module__[:func.__module__.rfind('.')]+template

        output["tg_css"] = tg_util.setlike()

        headers = {'Content-Type': content_type}        

        output = render(output, template=template, format=format,
                        mapping=mapping, headers=headers, fragment=fragment)

        content_type = headers['Content-Type']
        if content_type:
            response.headers["Content-Type"] = content_type        
        return output
        
        
        cherrypy.request.handler = handler
                

    def __call__(self, template=None, accept_format="*/*", as_format='default',
                 *args, **kwargs):
        
        if args:
            raise TypeError("The %r Tool does not accept positional arguments"
                            " other than 'template', 'accept_format' or"
                            " 'as_format'; you must use keyword arguments."
                            % self._name)
        
        # Add positional arguments back on kwargs
        kwargs['template'] = template
        kwargs['accept_format'] = accept_format
        kwargs['as_format'] = as_format
        
        # Make it possible to not expose a function even if you want to render,
        # We also accept both the words exposed and expose so the developer 
        # does not do any mistakes using one or the other.
        exposed = kwargs.get('exposed', kwargs.get('expose', True))
        
        def tool_decorator(func):
            if exposed:
                func.exposed = exposed

            if not hasattr(func, "_cp_config"):
                func._cp_config = {}
            subspace = self.namespace + "." + self._name + "."
            func._cp_config[subspace + "on"] = True
            
#            for k, v in kwargs.iteritems():
#                func._cp_config[subspace + k] = v
            
            if not func._cp_config.has_key(subspace + 'exposes'):
                func._cp_config[subspace + 'exposes'] = {}
            
            # Make a dictionary of exposes for this function indexed on 
            # accept_format and as_format
            key = subspace + 'exposes'
            func._cp_config[key][accept_format] = kwargs
            if as_format:
                func._cp_config[key][as_format] = kwargs
                
            # Special JSON handling, so that accept_header="application/json"
            # or ?tg_format=json will match this expose when allow_json is 
            # true
            if kwargs.get('allow_json', None) or template == "json":
                func._cp_config[key]['application/json'] = kwargs
                func._cp_config[key]['json'] = kwargs

            return func
        return tool_decorator

__all__ = ["ExposeTool"]
