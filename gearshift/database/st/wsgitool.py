import atexit
import logging

from storm.store import Store
from storm.locals import create_database

import cherrypy
#from cherrypy import request

from gearshift import config

log = logging.getLogger("gearshift.database")

storm_stores = []

class StormWsgiTool(cherrypy.Tool):
    """Transaction tool"""
    def __init__(self):
        super(StormWsgiTool, self).__init__("on_start_resource", self.connect, priority=40)

        atexit.register(StormWsgiTool.disconnect)

    def connect(self):
        global storm_stores

        if hasattr(cherrypy.thread_data, "store"):
            return

        dburi = config.get('storm.dburi')
        database = create_database(dburi)
        try:
            local_store = Store(database)
        except Exception:
            log.error("Unable to connect to database: %s" % dburi)
            cherrypy.engine.exit()
            return

        storm_stores.append(local_store)
        cherrypy.thread_data.store = local_store

    @staticmethod
    def disconnect():
        global storm_stores
        for s in storm_stores:
            log.info("Cleaning up store.")
            s.close()

cherrypy.tools.storm_wsgi = StormWsgiTool()
