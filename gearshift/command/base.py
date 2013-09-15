"""Commands for the TurboGears command line tool."""

import glob
import optparse
import os
import sys

import pkg_resources
import configobj

import gearshift
from gearshift.util import get_model, load_project_config, \
        get_project_config, get_package_name
from gearshift.identity import SecureObject, from_any_host
from gearshift import config, database

from sacommand import sacommand

sys.path.insert(0, os.getcwd())

no_connection_param = ["help", "list"]
no_model_param = ["help"]


def silent_os_remove(fname):
    """Try to remove file 'fname' but mute any error that may happen.

    Returns True if file was actually removed and False otherwise.

    """
    try:
        os.remove(fname)
        return True
    except os.error:
        pass
    return False


class CommandWithDB(object):
    """Base class for commands that need to use the database"""

    config = None

    def __init__(self, version):
        pass

    def find_config(self):
        """Chooses the config file, trying to guess whether this is a
        development or installed project."""
        load_project_config(self.config)
        self.dburi = config.get("sqlobject.dburi", None)
        if self.dburi and self.dburi.startswith("notrans_"):
            self.dburi = self.dburi[8:]


class SQL(CommandWithDB):
    """Wrapper command for sqlobject-admin, and some sqlalchemy support.

    This automatically supplies sqlobject-admin with the database that
    is found in the config file.

    Will also supply the model module as appropriate.

    """

    desc = "Run the database provider manager"
    need_project = True

    def __init__(self, version):
        if len(sys.argv) == 1 or sys.argv[1][0] == "-":
            parser = optparse.OptionParser(
                usage="%prog sql [command]\n\n" \
                      "hint: '%prog sql help' will list the sqlobject " \
                      "commands",
                version="%prog " + version)
            parser.add_option("-c", "--config", help="config file",
                              dest="config")
            options, args = parser.parse_args(sys.argv[1:3])

            if not options.config:
                parser.error("Please provide a valid option or command.")
            self.config = options.config
            # get rid of our config option
            if args:
                del sys.argv[1]
            else:
                del sys.argv[1:3]

        self.find_config()

    def run(self):
        """Run the sqlobject-admin tool or functions from the sacommand module."""

        if not "--egg" in sys.argv and not gearshift.util.get_project_name():
            print "This doesn't look like a GearShift project."
            return
        else:
            command = sys.argv[1]

            if config.get("sqlalchemy.dburi"):
                try:
                    sacommand(command, sys.argv)
                except Exception: # NoApplicableMethods:
                    # Anonymous except to avoid making entire
                    # gearshift dependent on peak.rules just to get
                    # this ONE case of NoApplicableMethods...
                    sacommand("help", [])
                return

            try:
                from sqlobject.manager import command
            except ImportError:
                from gearshift.util import missing_dependency_error
                print missing_dependency_error('SQLObject')
                return

            sqlobjcommand = command
            if sqlobjcommand not in no_connection_param:
                if self.dburi:
                    print "Using database URI %s" % self.dburi
                    sys.argv.insert(2, self.dburi)
                    sys.argv.insert(2, "-c")
                else:
                    print ("Database URI not specified in the config file"
                        " (%s).\nPlease be sure it's on the command line."
                            % (self.config or get_project_config()))

            if sqlobjcommand not in no_model_param:
                if not "--egg" in sys.argv:
                    eggname = glob.glob("*.egg-info")
                    if not eggname or not os.path.exists(
                            os.path.join(eggname[0], "sqlobject.txt")):
                        eggname = self.fix_egginfo(eggname)
                    eggname = eggname[0].replace(".egg-info", "")
                    if not "." in sys.path:
                        sys.path.append(".")
                        pkg_resources.working_set.add_entry(".")
                    sys.argv.insert(2, eggname)
                    sys.argv.insert(2, "--egg")

            command.the_runner.run(sys.argv)

    def fix_egginfo(self, eggname):
        """Add egg-info directory if necessary."""
        print """
This project seems incomplete. In order to use the sqlobject commands
without manually specifying a model, there needs to be an
egg-info directory with an appropriate sqlobject.txt file.

I can fix this automatically. Would you like me to?
"""
        dofix = raw_input("Enter [y] or n: ")
        if not dofix or dofix.lower()[0] == 'y':
            oldargs = sys.argv
            sys.argv = ["setup.py", "egg_info"]
            import imp
            imp.load_module("setup", *imp.find_module("setup", ["."]))
            sys.argv = oldargs

            import setuptools
            package = setuptools.find_packages()[0]
            eggname = glob.glob("*.egg-info")
            sqlobjectmeta = open(os.path.join(eggname[0], "sqlobject.txt"), "w")
            sqlobjectmeta.write("""db_module=%(package)s.model
history_dir=$base/%(package)s/sqlobject-history
""" % dict(package=package))
        else:
            sys.exit(0)
        return eggname


class Shell(CommandWithDB):
    """Convenient version of the Python interactive shell.

    This shell attempts to locate your configuration file and model module
    so that it can import everything from your model and make it available
    in the Python shell namespace.

    """

    desc = "Start a Python prompt with your database available"
    need_project = True

    def run(self):
        """Run the shell"""
        self.find_config()

        locals = dict(__name__="tg-admin")
        try:
            mod = get_model()
            if mod:
                locals.update(mod.__dict__)
        except (pkg_resources.DistributionNotFound, ImportError), e:
            mod = None
            print "Warning: Failed to import your data model: %s" % e
            print "You will not have access to your data model objects."
            print

        if config.get("sqlalchemy.dburi"):
            using_sqlalchemy = True
            database.bind_metadata()
            locals.update(session=database.session,
                metadata=database.metadata)
        else:
            using_sqlalchemy = False

        class CustomShellMixin(object):
            def commit_changes(self):
                if mod:
                    # XXX Can we check somehow, if there are actually any
                    # database changes to be commited?
                    r = raw_input("Do you wish to commit"
                        " your database changes? [yes]")
                    if not r.startswith("n"):
                        if using_sqlalchemy:
                            self.push("session.flush()")
                        else:
                            self.push("hub.commit()")

        try:
            # try to use IPython if possible
            from IPython import iplib, Shell

            class CustomIPShell(iplib.InteractiveShell, CustomShellMixin):
                def raw_input(self, *args, **kw):
                    try:
                         # needs decoding (see below)?
                        return iplib.InteractiveShell.raw_input(self, *args,
                                                                **kw)
                    except EOFError:
                        self.commit_changes()
                        raise EOFError

            shell = Shell.IPShell(user_ns=locals, shell_class=CustomIPShell)
            shell.mainloop()
        except ImportError:
            import code

            class CustomShell(code.InteractiveConsole, CustomShellMixin):
                def raw_input(self, *args, **kw):
                    try:
                        import readline
                    except ImportError:
                        pass
                    try:
                        r = code.InteractiveConsole.raw_input(self,
                            *args, **kw)
                        for encoding in (getattr(sys.stdin, 'encoding', None),
                                sys.getdefaultencoding(), 'utf-8', 'latin-1'):
                            if encoding:
                                try:
                                    return r.decode(encoding)
                                except UnicodeError:
                                    pass
                        return r
                    except EOFError:
                        self.commit_changes()
                        raise EOFError

            shell = CustomShell(locals=locals)
            shell.interact()


class ToolboxCommand(CommandWithDB):

    desc = "Launch the TurboGears Toolbox"

    def __init__(self, version):
        self.hostlist = ['127.0.0.1','::1']

        parser = optparse.OptionParser(
            usage="%prog toolbox [options]",
            version="%prog " + version)
        parser.add_option("-n", "--no-open",
            help="don't open browser automatically",
            dest="noopen", action="store_true", default=False)
        parser.add_option("-c", "--add-client",
            help="allow client ip address specified to connect to toolbox"
                " (can be specified more than once)",
            dest="host", action="append", default=None)
        parser.add_option("-p", "--port",
            help="port to run the Toolbox on",
            dest="port", default=7654)
        parser.add_option("--config", help="config file to use",
            dest="config", default=self.config or get_project_config())

        options, args = parser.parse_args(sys.argv[1:])
        self.port = int(options.port)
        self.noopen = options.noopen
        self.config = options.config

        if options.host:
            self.hostlist = self.hostlist + options.host

        gearshift.widgets.load_widgets()

    def openbrowser(self):
        import webbrowser
        webbrowser.open("http://localhost:%d" % self.port)

    def run(self):
        import cherrypy
        from gearshift import toolbox

        # TODO: remove this check once we convert the whole toolbox to genshi
        try:
            import turbokid
        except ImportError:
            # we could not import turbokid, the toolbox will crash with
            # horrible tracebacks...
            print "Please easy_install turbokid, toolbox cannot run without it"
            # sys exit with different than zero error code in case someone
            # is using the error code to know if it worked...
            sys.exit(2)

        # Make sure we have full configuration with every option
        # in it so other plugins or whatever find what they need
        # when starting even inside the toolblox
        conf = get_package_name()
        conf = conf and "%s.config" % conf or None
        conf = config.config_obj(configfile=self.config, modulename=conf)

        if 'global' in conf:
            config.update({'global': conf['global']})

        root = SecureObject(toolbox.Toolbox(), from_any_host(self.hostlist),
                exclude=['noaccess'])

        cherrypy.tree.mount(root, '/', config=gearshift.config.app)

        # amend some parameters since we are running from the command
        # line in order to change port, log methods...
        config.update({'global': {
            'server.socket_port': self.port,
            'server.webpath': '/',
            'server.environment': 'development',
            'server.log_to_screen': True,
            'autoreload.on': False,
            'server.package': 'gearshift.toolbox',
            'log_debug_info_filter.on': False,
            'tools.identity.failure_url': '/noaccess',
            'tools.identity.force_external_redirect': False,
            'tg.defaultview': 'kid',
            'tg.strict_parameters': False,
            'kid.outputformat': 'html default',
            'kid.encoding': 'utf-8'
            }})

        gearshift.view.load_engines()
        if self.noopen:
            cherrypy.engine.start()
        else:
            cherrypy.engine.start_with_callback(self.openbrowser)
        cherrypy.engine.block()


commands = None

def main():
    """Main command runner. Manages the primary command line arguments."""
    # add commands defined by entrypoints
    commands = {}
    for entrypoint in pkg_resources.iter_entry_points("gearshift.command"):
        command = entrypoint.load()
        commands[entrypoint.name] = (command.desc, entrypoint)

    def _help():
        """Custom help text for tg-admin."""

        print """
GearShift %s command line interface

Usage: %s [options] <command>

Options:
    -c CONFIG --config=CONFIG    Config file to use
    -e EGG_SPEC --egg=EGG_SPEC   Run command on given Egg

Commands:""" % (gearshift.__version__, sys.argv[0])

        longest = max([len(key) for key in commands.keys()])
        format = "%" + str(longest) + "s  %s"
        commandlist = commands.keys()
        commandlist.sort()
        for key in commandlist:
            print format % (key, commands[key][0])

    parser = optparse.OptionParser()
    parser.allow_interspersed_args = False
    parser.add_option("-c", "--config", dest="config")
    parser.add_option("-e", "--egg", dest="egg")
    parser.print_help = _help
    options, args = parser.parse_args(sys.argv[1:])

    # if command is not found display help
    if not args or not commands.has_key(args[0]):
        _help()
        sys.exit()

    commandname = args[0]
    # strip command and any global options from the sys.argv
    sys.argv = [sys.argv[0]] + args[1:]
    command = commands[commandname][1]
    command = command.load()

    if options.egg:
        egg = pkg_resources.get_distribution(options.egg)
        os.chdir(egg.location)

    if hasattr(command,"need_project"):
        if not gearshift.util.get_project_name():
            print "This command needs to be run from inside a project directory"
            return
        elif not options.config and not os.path.isfile(get_project_config()):
            print """No default config file was found.
If it has been renamed use:
tg-admin --config=<FILE> %s""" % commandname
            return
    command.config = options.config
    command = command(gearshift.__version__)
    command.run()


__all__ = ["main"]
