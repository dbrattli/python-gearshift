import logging
import codecs
from cherrypy import request

try:
    from pkg_resources import resource_filename
except ImportError:
    def resource_filename(module, filename):
        names = module.split(".")+ [filename]
        pathname = os.path.join(*names)
        return pathname

import cherrypy
from cherrypy import response

from gearshift import config

log = logging.getLogger("gearshift.markup")

engines = {}

# Lazy import modules
textile = None
markdown = None
publish_parts = None
trac = None

class TextileEngine(object):
    """Engine for Textile (http://hobix.com/textile/)"""
    
    extension = "txt"
    
    def render(self, markup, encoding="utf-8"):
        global textile
        if not textile:
            try:
                import textile
            except ImportError:
                return markup
        
        return textile.textile(markup, encoding=encoding, output='utf-8')

engines['textile'] = TextileEngine()

class RestEngine(object):
    """Engine for RestructuredText (http://docutils.sourceforge.net/rst.html)"""
    
    extension = "rst"
    
    def render(self, markup, encoding):
        global publish_parts
        if not publish_parts:
            try:
                from docutils.core import publish_parts
            except ImportError:
                return markup
        
        parts = publish_parts(source=markup, writer_name="html4css1", 
                              settings_overrides=None)
        return parts["html_body"]
        
engines['rest'] = RestEngine()

class MarkdownEngine(object):
    """Engine for Markdown
    
    For more information see: 
     * http://daringfireball.net/projects/markdown/
     * http://www.freewisdom.org/projects/python-markdown/
    """
    
    extension = "txt"
    
    def render(self, markup, encoding, **kwargs):
        global markdown
        if not markdown:
            try:
                import markdown
            except ImportError:
                return "Error: markdown is not installed"
                
        safe_mode = kwargs.get('safe_mode', False)
        extensions = kwargs.get('extensions', [])
        return markdown.markdown(markup, extensions, safe_mode=safe_mode)

engines['markdown'] = MarkdownEngine()

class TracWikiEngine(object):
    extension = "txt"
    
    def __init__(self):
        global trac
        if not trac:
            try:
                import trac
            except ImportError:
                return

        from trac.test import EnvironmentStub, Mock, MockPerm
        from trac.mimeview import Context
        from trac.wiki.formatter import HtmlFormatter
        from trac.web.href import Href

        self.env = EnvironmentStub()
        req = Mock(href=Href('/'), abs_href=Href('http://www.example.com/'),
                   authname='anonymous', perm=MockPerm(), args={})
        self.context = Context.from_request(req, 'wiki')
        self.formatter = HtmlFormatter

    def render(self, markup, encoding):
        global trac
        if not trac:
            return markup
            
        return self.formatter(self.env, self.context, markup).generate()

def _choose_engine(template):
    if isinstance(template, basestring):
        colon = template.find(":")
        if colon > -1:
            enginename = template[:colon].lower()
            template = template[colon+1:]
        else:
            engine = engines.get(template, None)
            if engine:
                return engine, None, template
            enginename = config.get("tg.defaultmarkup", "markdown")
    else:
        enginename = config.get("tg.defaultmarkup", "markdown")
    engine = engines.get(enginename, None)
    if not engine:
        raise KeyError, \
            "Template engine %s is not installed" % enginename
    return engine, template, enginename

class MarkupTool(cherrypy.Tool):
    """A Markup tool for CherryPy
    
    The markup tool works almost the same way as expose, and you can decorate 
    functions just like expose:
    
    @gearshift.expose(template="genshi:templates.index")
    @gearshift.markup(template="rest:templates.markup")
    def index(self):
        return dict()
        
    In this example the markup will be available in the parameter "tg_markup"
    inside the Genshi template, and you can use it like this:
    
    <div py:replace="HTML(tg_markup)">Markup goes here.</div>

    Supported template engines includes Markdown, RestructuredText, Textile
    and TracWiki. In each case, if the required library is not installed, the 
    tool will silently fail and return the un-marked-up text.

    The template can be set dynamically by including a parameter named
    "tg_markup_template" in the output (similar to tg_template).
    """
    
    def __init__(self):
        log.debug("Markup Tool initialized")

        return super(MarkupTool, self).__init__(point="before_handler",
                     callable=self.before_handler, priority=35)

    def before_handler(self, markups=None, **kwargs):

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
        markups = get('tools.markup.markups', {})

        template = markups.get('template', output.get('tg_markup_template'))
        engine, template, enginename = _choose_engine(template)
        encoding = kwargs.get('encoding', 'utf-8')
        extension = markups.get('extension', engine.extension)
        fragment = markups.get('fragment', True)
        options = markups.get('options', dict())
        
        if template:
            if "." in template:
                module, filename = template.rsplit(".", 1)
                filename = '%s.%s' % (filename, extension)
            else:
                module = ""
                filename = '%s.%s' % (template, extension)

            try:
                pathname = resource_filename(module, filename)
            except ImportError:
                # Caused when user attempts to open /markups/blahblah.html
                # (the . make it try to import module "blahblah")
                raise cherrypy.HTTPError(404, "Document does not exist")

            try:
                markup = codecs.open(pathname, encoding="utf-8").read()
            except IOError:
                # Caused when user attempts to open /markups/nonexistantpage/
                raise cherrypy.HTTPError(404, "Document does not exist")
        else:
            # Get markup from output data (generated by controller, database)
            markup = output.get('tg_markup')

        value = engine.render(markup, encoding=encoding, **options)
        
        # Check if we should insert the rendered output in the output 
        # dictionary or if the rendered output is the final output
        if fragment:
            output['tg_markup'] = value
        else:
            output = value
            
        return output

    def __call__(self, template=None, *args, **kwargs):
        """Markup tool decorator
        
        @param template "templateengine:dotted.reference" reference along the
            Python path for the template and the template engine. For
            example, "rest:foo.bar" will render the bar template in
            the foo package as RestructuredText.
        @keyparam options A dictionary of options that will be sent to the 
            template engine
        @keyparam fragment If True the rendered output will made available in
            the "tg_markup" parameter of the output. Thus you can use this 
            parameter inside Genshi templates etc. If False, the output will 
            be replaced with the rendered output of the template engine.
        @keyparam extension The file extension of the template to render. Each
            template engine has a default file extension that you can override
            if needed
        """
        if args:
            raise TypeError("The %r Tool does not accept positional arguments"
                            " other than 'template'." % self._name)

        # Add positional arguments back on kwargs
        if template:
            kwargs['template'] = template
    
        def tool_decorator(func):
            log.debug("Markup %s", func)

            if not hasattr(func, "_cp_config"):
                func._cp_config = {}
            subspace = self.namespace + "." + self._name + "."
            func._cp_config[subspace + "on"] = True
            for k, v in kwargs.iteritems():
                func._cp_config[subspace + k] = v
            
            if not func._cp_config.has_key(subspace + 'markups'):
                func._cp_config[subspace + 'markups'] = {}
            
            key = subspace + 'markups'
            func._cp_config[key] = kwargs
                
            return func
        return tool_decorator

__all__ = ["MarkupTool"]
