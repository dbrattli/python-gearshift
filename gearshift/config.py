import os, glob
import os.path
import ConfigParser
import logging
import logging.handlers
import warnings

import cherrypy
from cherrypy import request, config as cp_config
from cherrypy.lib.reprconf import unrepr

import configobj
from configobj import ConfigObj
# Need to monkey-patch configobj for the App Engine
if configobj.compiler is None:
    def unrepr(s):
        return eval(s)
    configobj.unrepr = unrepr

try:
    from pkg_resources import resource_filename
except ImportError:
    def resource_filename(module, filename):
        names = module.split(".")+ [filename]
        pathname = os.path.join(*names)
        return pathname

try: 
    import compiler
    has_compiler = True
except ImportError:
    has_compiler = False

import gearshift

__all__ = ["update_config", "get", "update"]

# GearShift's server config just points directly to CherryPy
server = cp_config

# Application config is used when mounting applications.
#   Config values that are not server-wide should be put here.
app = dict()

def get(*args):
    """Get a config setting.  Uses request.config if available,
    otherwise defaults back to server's config settings.
    """
    if getattr(request, 'stage', None):
        ret = request.config.get(*args)
    else: 
        ret = server.get(*args)
    
    return ret

def items():
    """A dict.items() equivalent for config values.  Returns request
    specific information if available, otherwise falls back to server
    config.
    """
    if getattr(request, 'stage', None):
        return request.config.items()
    else:
        return server.items()

class ConfigParser(ConfigParser.ConfigParser):
    """We use the ConfigParser to parse app.cfg since we need to support
    custom dispatchers which configobj cannot parse.
    """
    def as_dict(self, raw=False, vars=None):
        """Convert an INI file to a dictionary"""
        # Load INI file into a dict
        result = {}
        for section in self.sections():
            if section not in result:
                result[section] = {}
            for option in self.options(section):
                # Do not parse logging config to Python values.
                if section == 'global' or section.startswith('/'):
                    value = self.get(section, option, raw, vars)
                    try:
                        value = unrepr(value)
                    except Exception, x:
                        msg = ("Config error in section: %r, option: %r, "
                               "value: %r. Config values must be valid Python." %
                               (section, option, value))
                        raise ValueError(msg, x.__class__.__name__, x.args)
                else:
                    value = self.get(section, option, raw=True)

                result[section][option] = value
        return result
    
    def dict_from_files(self, file, vars=None):
        if hasattr(file, 'read'):
            self.readfp(file)
        else:
            self.read(file)
        return self.as_dict(vars=vars)

class ConfigError(Exception):
    pass

def _get_formatters(formatters):
    for key, formatter in formatters.items():
        kw = {}
        fmt = formatter.get("format", None)
        if fmt:
            fmt = fmt.replace("*(", "%(")
            kw["fmt"] = fmt
        datefmt = formatter.get("datefmt", None)
        if datefmt:
            kw["datefmt"] = datefmt
        formatter = logging.Formatter(**kw)
        formatters[key] = formatter

def _get_handlers(handlers, formatters):
    for key, handler in handlers.items():
        kw = {}
        try:
            cls = handler.get("class")
            args = handler.get("args", tuple())
            level = handler.get("level", None)
            try:
                cls = eval(cls, logging.__dict__)
            except NameError:
                try:
                    cls = eval(cls, logging.handlers.__dict__)
                except NameError, err:
                    raise ConfigError("Specified class in handler "
                        "%s is not a recognizable logger name" % key)
            try:
                handler_obj = cls(*eval(args, logging.__dict__))
            except IOError,err:
                raise ConfigError("Missing or wrong argument to "
                    "%s in handler %s -> %s " % (cls.__name__,key,err))
            except TypeError,err:
                raise ConfigError("Wrong format for arguments "
                    "to %s in handler %s -> %s" % (cls.__name__,key,err))
            if level:
                level = eval(level, logging.__dict__)
                handler_obj.setLevel(level)
        except KeyError:
            raise ConfigError("No class specified for logging "
                "handler %s" % key)
        formatter = handler.get("formatter", None)
        if formatter:
            try:
                formatter = formatters[formatter]
            except KeyError:
                raise ConfigError("Handler %s references unknown "
                            "formatter %s" % (key, formatter))
            handler_obj.setFormatter(formatter)
        handlers[key] = handler_obj

def _get_loggers(loggers, handlers):
    for key, logger in loggers.items():
        qualname = logger.get("qualname", None)
        if qualname:
            log = logging.getLogger(qualname)
        else:
            log = logging.getLogger()

        level = logger.get("level", None)
        if level:
            level = eval(level, logging.__dict__)
        else:
            level = logging.NOTSET
        log.setLevel(level)

        propagate = logger.get("propagate", None)
        if propagate is not None:
            log.propagate = propagate

        cfghandlers = logger.get("handlers", None)
        if cfghandlers:
            if isinstance(cfghandlers, basestring):
                cfghandlers = [cfghandlers]
            for handler in cfghandlers:
                try:
                    handler = handlers[handler]
                except KeyError:
                    raise ConfigError("Logger %s references unknown "
                                "handler %s" % (key, handler))
                log.addHandler(handler)

def configure_loggers(logcfg):
    """Configures the Python logging module, using options that are very
    similar to the ones listed in the Python documentation. This also
    removes the logging configuration from the configuration dictionary
    because CherryPy doesn't like it there. Here are some of the Python
    examples converted to the format used here:

    [logging]
    [[loggers]]
    [[[parser]]]
    [logger_parser]
    level="DEBUG"
    handlers="hand01"
    propagate=1
    qualname="compiler.parser"

    [[handlers]]
    [[[hand01]]]
    class="StreamHandler"
    level="NOTSET"
    formatter="form01"
    args="(sys.stdout,)"

    [[formatters]]
    [[[form01]]]
    format="F1 *(asctime)s *(levelname)s *(message)s"
    datefmt=


    One notable format difference is that *() is used in the formatter
    instead of %() because %() is already used for config file
    interpolation.

    """
    formatters = logcfg.get("formatters", {})
    _get_formatters(formatters)

    handlers = logcfg.get("handlers", {})
    _get_handlers(handlers, formatters)

    loggers = logcfg.get("loggers", {})
    _get_loggers(loggers, handlers)

def config_defaults():
    """Return a dict with default global config settings."""
    return dict(
        current_dir_uri = os.path.abspath(os.getcwd())
    )

def update_config(configfile=None, modulename=None):
    """Update the system configuration from given config file and/or module.

    'configfile' is a ConfigObj (INI-style) config file, 'modulename' a module
    path in dotted notation. The function looks for files with a ".cfg"
    extension if the given module name refers to a package directory or a file
    with the base name of the right-most part of the module path and a ".cfg"
    extension added.

    If both 'configfile' and 'modulname' are specified, the module is read
    first, followed by the config file. This means that the config file's
    options override the options in the module file.

    """

    defaults = config_defaults()

    configdata = ConfigObj(unrepr=True)
    if modulename:
        lastdot = modulename.rfind('.')
        firstdot = modulename.find('.')
        packagename = modulename[:lastdot]
        top_level_package = modulename[:firstdot]
        modname = modulename[lastdot+1:]
        modfile = resource_filename(packagename, modname + '.cfg')
        if not os.path.exists(modfile):
            modfile = resource_filename(packagename, modname)
        if os.path.isdir(modfile):
            configfiles = glob.glob(os.path.join(modfile, '*.cfg'))
        else:
            configfiles = [modfile]

        top_level_dir = os.path.normpath(resource_filename(top_level_package, ''))

        package_dir = os.path.normpath(resource_filename(packagename, ''))

        defaults.update(dict(top_level_dir=top_level_dir,
                             package_dir=package_dir))
        
        # Update Python logging config
        for pathname in configfiles:
            if 'app.cfg' in pathname:
                parser = ConfigParser()
                conf = parser.dict_from_files(pathname, vars=defaults)
            else:
                obj = ConfigObj(pathname, unrepr=True)
                obj.merge(dict(DEFAULT=defaults))
                conf = obj.dict()
            configdata.merge(conf)

    if configfile:
        obj = ConfigObj(configfile, unrepr=True)
        obj.merge(dict(DEFAULT=defaults))
        conf = obj.dict()
        configdata.merge(conf)
    update(configdata.dict())

def update(configvalues):
    """Update the configuration with values from a dictionary.
    The values are sent to the appropriate config system 
    (server, app, or logging) automatically.
    """
    global server, app

    # Send key values for applications to app, logging to logging, and
    # the rest to server.  app keys are identified by their leading slash.
    for (key, value) in configvalues.items():
        if key.startswith('/'):
            if not app.has_key(key):
                app[key] = value
            else: 
                app[key].update(value)
        elif key == 'logging':
            configure_loggers(value)
        else:
            if isinstance(value, dict):
                server.update(value)
            else:
                server[key] = value

                if key == 'visit.on':
                    warnings.warn("Config key visit.on is deprecated.  "
                                  "Use tools.visit.on instead.",
                                  DeprecationWarning, 2)                
                    server['tools.visit.on'] = value

