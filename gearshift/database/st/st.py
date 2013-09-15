import sys
import logging

import cherrypy
from cherrypy import request

import storm.store
from storm.store import Store
from storm.locals import *
#from storm.tracer import debug
#debug(True, stream=sys.stdout)

from gearshift import config

log = logging.getLogger("gearshift.database")

storm_stores = {}

def connect_db(thread_index):
    global storm_stores

    dburi = config.get('storm.dburi')
    database = create_database(dburi)
    try:
        local_store = Store(database)       
    except Exception:
        log.error("Unable to connect to database: %s" % dburi)
        cherrypy.engine.exit()
        return

    timezone = config.get("storm.timezone")
    if timezone:
        local_store.execute(SQL("SET time_zone=?", (timezone, )));

    storm_stores[thread_index] = local_store
    cherrypy.thread_data.store = local_store

def disconnect_db(thread_index):
    global storm_stores
    s = storm_stores.pop(thread_index, None)
    if s is not None:
        log.info("Cleaning up store.")
        s.close()
    else:
        log.error("Could not find store.")

def start():
    cherrypy.engine.subscribe('start_thread', connect_db)
    cherrypy.engine.subscribe('stop_thread', disconnect_db)
