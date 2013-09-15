from cherrypy import request

import couchdb
from couchdb.client import Server

from gearshift import config

class CouchDBDatastore(object):

    def db(self):
        if hasattr(request, "_couchdb_db"):
            db = request._couchdb_db
        else:
            dburi = config.get("couchdb.dburi")
            server = Server(dburi)
            username = config.get("couchdb.username")
            password = config.get("couchdb.password")
            if username:
                server.resource.http.add_credentials(username, password)
            db = server[config.get("couchdb.database")]
            request._couchdb_db = db
        return db
    
    db = property(db)
        
datastore = CouchDBDatastore()