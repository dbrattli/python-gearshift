import logging

import cherrypy
from cherrypy import request

from gearshift import identity, config, visit
from gearshift.identity import visitor

log = logging.getLogger("gearshift.identity")

class IdentityTool(cherrypy.Tool):
    """A TurboGears identity tool"""

    def __init__(self):
        log.debug("Identity Tool initialized")

        return super(IdentityTool, self).__init__("before_handler",
                                                  self.before_handler,
                                                  priority=30)

    def start_extension(self):
        # Bail out if the application hasn't enabled this extension
        if not config.get('tools.identity.on', False):
            return

        # Identity requires that Visit tracking be enabled
        if not config.get('tools.visit.on', False):
            raise identity.IdentityConfigurationException(
                    "Visit tracking must be enabled (tools.visit.on)")

        log.info("Identity starting")
        # Temporary until tg-admin can call create_extension_model
        visitor.create_extension_model()
        # Register the plugin for the Visit Tracking framework
        visit.enable_visit_plugin(visitor.IdentityVisitPlugin())

    def before_handler(self, *args, **kwargs):
        predicates = []

        # Here we get decorator @identity.require(identity.not_anonymous() or 
        # _cp_config = { 'tools.identity.require' : identity.not_anonymous() }
        predicate = kwargs.get('require', None)
        if predicate is not None:
            predicates.append(predicate)
            
        # Get any SecureResource require=identity.not_anonymous(). These are 
        # queued up along the way to the resulting controller.
        if hasattr(request, "tg_predicates"):
            predicates.extend(request.tg_predicates)
            
        # Check them all for identity failures
        for predicate in predicates:
            errors = []
            if not predicate.eval_with_object(identity.current, errors):
                raise identity.IdentityFailure(errors)
        request.tg_predicates = []

    def __call__(self, require, *args, **kwargs):
        if args:
            raise TypeError("The %r Tool does not accept positional arguments"
                            " exept for 'require'; you must use keyword "
                            "arguments." % self._name)

        kwargs['require'] = require
                
        def tool_decorator(func):
            if not hasattr(func, "_cp_config"):
                func._cp_config = {}
            subspace = self.namespace + "." + self._name + "."
            func._cp_config[subspace + "on"] = True
            for k, v in kwargs.iteritems():
                func._cp_config[subspace + k] = v
                
            return func
        return tool_decorator
