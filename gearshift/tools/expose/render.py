# For lazy imports
genshi = None
genshi_loader = dict()
simplejson = None
kid = None
mako = None
mako_lookup = None
kajiki_loader = None

try:
    from pkg_resources import resource_filename
except ImportError:
    def resource_filename(module, filename):
        names = module.split(".")+ [filename]
        pathname = os.path.join(*names)
        return pathname

import os.path
import logging

import cherrypy
from cherrypy import request, response

from gearshift import config
from gearshift.util import (
    get_template_encoding_default,
    get_mime_type_for_format, mime_type_has_charset, Bunch)
from gearshift.view import stdvars
from gearshift.i18n import gettext, lazy_gettext

log = logging.getLogger("gearshift.expose")

engines = dict()

def render_kajiki(template=None, info=None, format=None, fragment=False, mapping=None):
    global kajiki_loader
    if kajiki_loader is None:
        # Lazy imports of Kajiki
        from kajiki import PackageLoader
        kajiki_loader = PackageLoader()
            
    Template = kajiki_loader.import_(template)
       
    context = Bunch()
    context.update(stdvars())
    context.update(info)

    templ = Template(context)
    return templ.render()

engines['kajiki'] = render_kajiki

def render_genshi(template=None, info=None, format=None, fragment=False, mapping=None):
    global genshi, genshi_loader
    if genshi is None:
        # Lazy imports of Genshi
        import genshi
        import genshi.template
        import genshi.output
        import genshi.input
        import genshi.filters
    
        def genshi_loader_callback(template):
            """This function will be called by genshi TemplateLoader after
            loading the template"""
            translator = genshi.filters.Translator(gettext)
            # Genshi 0.6 supports translation directives. Lets use them if available.
            if hasattr(translator, "setup"):
                translator.setup(template)
            else:
                template.filters.insert(0, translator)
        
        if config.get("i18n.run_template_filter", False):
            callback = genshi_loader_callback
        else:
            callback = None
        
        auto_reload = config.get("genshi.auto_reload", "1")
        if isinstance(auto_reload, basestring):
            auto_reload = auto_reload.lower() in ('1', 'on', 'yes', 'true')

        max_cache_size = config.get("genshi.max_cache_size", 25)

        genshi_loader = genshi.template.TemplateLoader([""],
                auto_reload=auto_reload,
                callback=genshi_loader_callback,
                max_cache_size=max_cache_size,
        )

    # Choose Genshi template engine
    if format == "text":
        cls = genshi.template.NewTextTemplate
        default_extension = "txt"
    else:
        cls = None # Default is Markup
        default_extension = "html"
        
    if "/" in template:
        # Path notation. Use first path part as module name
        module, pathname = template.split("/", 1)
        template = resource_filename(module, pathname)
    elif "." in template:
        # Dotted notation
        module, filename = template.rsplit(".", 1)
        filename = '%s.%s' % (filename, default_extension)
        template = resource_filename(module, filename)
    else:
        template = '%s.%s' % (template, default_extension)
    
    encoding = config.get("genshi.encoding", "utf-8")
    templ = genshi_loader.load(template, encoding=encoding, cls=cls)

    if format == 'html' and not fragment:
        mapping.setdefault('doctype', config.get('genshi.default_doctype',
                                                 'html-transitional'))
                                                 
    serializer = genshi.output.get_serializer(format, **mapping)
    
    extras = { 
        'XML' : genshi.input.XML, 
        'HTML' : genshi.input.HTML,
        'ET' : genshi.input.ET,
        '_' : lazy_gettext
    }
    
    context = genshi.template.Context(**extras)
    context.push(stdvars())
    context.push(info)
    
    stream = templ.generate(context)
    if config.get('genshi.html_form_filler', False):
        stream = stream | genshi.filters.HTMLFormFiller(data=info)
    
    encode = genshi.output.encode
    return encode(serializer(stream), method=serializer, encoding=encoding)

engines['genshi'] = render_genshi

def default_json(obj):
    if hasattr(obj, '__json__'):
        return obj.__json__()

    return ""

def render_json(template=None, info=None, format=None, fragment=False, mapping=None):
    """Engine for JSON. Misses most of the features of TurboJSON, but this
    one works on the Google App Engine
    """
    global simplejson
    if not simplejson:
        try:
            from django.utils import simplejson # App Engine friendly
        except ImportError:
            import simplejson
            
    # filter info parameters
    info = dict([(key, info[key]) for key in info.keys() if not (key.startswith("tg_") and key != "tg_flash")])
    
    return simplejson.dumps(info, default=default_json)

engines['json'] = render_json

def render_kid(template=None, info=None, format=None, fragment=False, mapping=None):
    """We need kid support in order to get some of the tests working
    """
    global kid
    if kid is None:
        import kid

    extension = "kid"
    if "." in template:
        module, filename = template.rsplit(".", 1)
        filename = '%s.%s' % (filename, extension)
        template = resource_filename(module, filename)
    else:
        template = '%s.%s' % (template, extension)

    template = kid.Template(file=template, fragment=fragment, **info)
    return template.serialize()

engines['kid'] = render_kid

def render_mako(template=None, info=None, format=None, fragment=False, mapping=None):
    global mako, mako_lookup
    if mako is None:
        import mako
        import mako.lookup
        mako_lookup = mako.lookup.TemplateLookup(directories=[''])

    extension = format
    if "." in template:
        module, filename = template.rsplit(".", 1)
        filename = '%s.%s' % (filename, extension)
        template = resource_filename(module, filename)
    else:
        template = '%s.%s' % (template, extension)
    
    templ = mako_lookup.get_template(template)
    try:
        ret = templ.render(**info)
    except Exception:
        ret = mako.exceptions.html_error_template().render()
    return ret

engines['mako'] = render_mako

def _choose_engine(template):
    if isinstance(template, basestring):
        colon = template.find(":")
        if colon > -1:
            enginename = template[:colon]
            template = template[colon+1:]
        else:
            engine = engines.get(template, None)
            if engine:
                return engine, None, template
            enginename = config.get("tg.defaultview", "genshi")
    else:
        enginename = config.get("tg.defaultview", "genshi")
    engine = engines.get(enginename, None)
    if not engine:
        raise KeyError, \
            "Template engine %s is not installed" % enginename
    return engine, template, enginename

def render(info, template=None, format=None, headers=None, mapping=None, 
           fragment=False):
    """Renders data in the desired format.

    @param info: the data itself
    @type info: dict

    @param format: "html", "xml", "text" or "json"
    @type format: string

    @param headers: for response headers, primarily the content type
    @type headers: dict

    @param fragment: passed through to tell the template if only a
                     fragment of a page is desired
    @type fragment: bool

    @param template: name of the template to use
    @type template: string
    """
    
    # What's this stuff for? Just for testing?
    environ = getattr(cherrypy.request, 'wsgi_environ', {})
    if environ.get('paste.testing', False):
        cherrypy.request.wsgi_environ['paste.testing_variables']['raw'] = info

    template = format == 'json' and 'json' or info.pop("tg_template", template)
    engine, template, enginename = _choose_engine(template)
    if format:
        if format == 'plain':
            if enginename == 'genshi':
                format = 'text'
        elif format == 'text':
            if enginename == 'kid':
                format = 'plain'
    else:
        format = enginename == 'json' and 'json' or config.get(
            "%s.outputformat" % enginename,
            config.get("%s.default_format" % enginename, 'html'))

    if isinstance(headers, dict):
        # Determine the proper content type and charset for the response.
        # We simply derive the content type from the format here
        # and use the charset specified in the configuration setting.
        # This could be improved by also examining the engine and the output.
        content_type = headers.get('Content-Type')
        if not content_type:
            if format:
                content_format = format
                if isinstance(content_format, (tuple, list)):
                    content_format = content_format[0]
                if isinstance(content_format, str):
                    content_format = content_format.split(
                        )[0].split('-' , 1)[0].lower()
                else:
                    content_format = 'html'
            else:
                content_format = 'html'
            content_type = get_mime_type_for_format(content_format)
        if mime_type_has_charset(
                content_type) and '; charset=' not in content_type:
            charset = get_template_encoding_default(enginename)
            if charset:
                content_type += '; charset=' + charset
        headers['Content-Type'] = content_type
    
    mapping = mapping or dict()
    return engine(info=info, format=format, fragment=fragment, 
                  template=template, mapping=mapping)
