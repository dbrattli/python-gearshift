"""Convenient access to an SQLObject or SQLAlchemy managed database."""

import sys
import time
import logging

import cherrypy
from cherrypy import request

try:
    import sqlobject
    from sqlobject.dbconnection import ConnectionHub, Transaction, TheURIOpener
    from sqlobject.util.threadinglocal import local as threading_local
    have_sqlobject = True
except ImportError:
    have_sqlobject = False
    
from gearshift import config
from gearshift.util import remove_keys

log = logging.getLogger("gearshift.database")

hub_registry = set()

_hubs = dict() # stores the AutoConnectHubs used for each connection URI

# Provide support for SQLObject
def _mysql_timestamp_converter(raw):
    """Convert a MySQL TIMESTAMP to a floating point number representing
    the seconds since the Un*x Epoch. It uses custom code the input seems
    to be the new (MySQL 4.1+) timestamp format, otherwise code from the
    MySQLdb module is used."""
    if raw[4] == '-':
        return time.mktime(time.strptime(raw, '%Y-%m-%d %H:%M:%S'))
    else:
        import MySQLdb.converters
        return MySQLdb.converters.mysql_timestamp_converter(raw)

class SODataManager:
    """Integrates with TurboGears SQLObject PackageHubs.

    One phase variant.
    """
    transaction_manager = None

    def __init__(self):
        request.in_transaction = True 

    def abort(self, transaction):
##            print "SODataManager.abort()"

        rollback_all() 

    def tpc_begin(self, transaction):
##            print "SODataManager.tpc_begin()"
        pass
    
    def commit(self, transaction):
##            print "SODataManager.commit()"
        pass

    def tpc_vote(self, transaction):
##            print "SODataManager.tpc_vote()"

        # for a one phase data manager commit last in tpc_vote
        commit_all() 

    def tpc_finish(self, transaction):
        pass
    
    def tpc_abort(self, transaction):
        raise TypeError("Already committed")

    def sortKey(self):
        # Try to sort last, so that we vote last - we may commit in tpc_vote(),        
        return "~tg:sqlobject:%d" % id(self.hub)

if have_sqlobject:
    class AutoConnectHub(ConnectionHub):
        """Connects to the database once per thread. The AutoConnectHub also
        provides convenient methods for managing transactions."""
        uri = None
        params = {}

        def __init__(self, uri=None, supports_transactions=True):
            if not uri:
                uri = config.get("sqlobject.dburi")
            self.uri = uri
            self.supports_transactions = supports_transactions
            hub_registry.add(self)
            ConnectionHub.__init__(self)

        def _is_interesting_version(self):
            """Return True only if version of MySQLdb <= 1.0."""
            import MySQLdb
            module_version = MySQLdb.version_info[0:2]
            major = module_version[0]
            minor = module_version[1]
            # we can't use Decimal here because it is only available for Python 2.4
            return (major < 1 or (major == 1 and minor < 2))

        def _enable_timestamp_workaround(self, connection):
            """Enable a workaround for an incompatible timestamp format change
            in MySQL 4.1 when using an old version of MySQLdb. See trac ticket
            #1235 - http://trac.gearshift.org/ticket/1235 for details."""
            # precondition: connection is a MySQLConnection
            import MySQLdb
            import MySQLdb.converters
            if self._is_interesting_version():
                conversions = MySQLdb.converters.conversions.copy()
                conversions[MySQLdb.constants.FIELD_TYPE.TIMESTAMP] = \
                    _mysql_timestamp_converter
                # There is no method to use custom keywords when using
                # "connectionForURI" in sqlobject so we have to insert the
                # conversions afterwards.
                connection.kw["conv"] = conversions

        def getConnection(self):
            try:
                conn = self.threadingLocal.connection
                return self.begin(conn)
            except AttributeError:
                if self.uri:
                    conn = sqlobject.connectionForURI(self.uri)
                    # the following line effectively turns off the DBAPI connection
                    # cache. We're already holding on to a connection per thread,
                    # and the cache causes problems with sqlite.
                    if self.uri.startswith("sqlite"):
                        TheURIOpener.cachedURIs = {}
                    elif self.uri.startswith("mysql") and \
                         config.get("gearshift.enable_mysql41_timestamp_workaround", False):
                        self._enable_timestamp_workaround(conn)
                    self.threadingLocal.connection = conn
                    return self.begin(conn)
                raise AttributeError(
                    "No connection has been defined for this thread "
                    "or process")

        def reset(self):
            """Used for testing purposes. This drops all of the connections
            that are being held."""
            self.threadingLocal = threading_local()

        def begin(self, conn=None):
            """Start a transaction."""
            if not self.supports_transactions:
                return conn
            if not conn:
                conn = self.getConnection()
            if isinstance(conn, Transaction):
                if conn._obsolete:
                    conn.begin()
                return conn
            self.threadingLocal.old_conn = conn
            trans = conn.transaction()
            self.threadingLocal.connection = trans
        
            return trans

        def commit(self):
            """Commit the current transaction."""
            if not self.supports_transactions:
                return
            try:
                conn = self.threadingLocal.connection
            except AttributeError:
                return
            if isinstance(conn, Transaction):
                self.threadingLocal.connection.commit()

        def rollback(self):
            """Rollback the current transaction."""
            if not self.supports_transactions:
                return
            try:
                conn = self.threadingLocal.connection
            except AttributeError:
                return
            if isinstance(conn, Transaction) and not conn._obsolete:
                self.threadingLocal.connection.rollback()

        def end(self):
            """End the transaction, returning to a standard connection."""
            if not self.supports_transactions:
                return
            try:
                conn = self.threadingLocal.connection
            except AttributeError:
                return
            if not isinstance(conn, Transaction):
                return
            if not conn._obsolete:
                conn.rollback()
            self.threadingLocal.connection = self.threadingLocal.old_conn
            del self.threadingLocal.old_conn
            self.threadingLocal.connection.expireAll()

class PackageHub(object):
    """Transparently proxies to an AutoConnectHub for the URI
    that is appropriate for this package. A package URI is
    configured via "packagename.dburi" in the TurboGears config
    settings. If there is no package DB URI configured, the
    default (provided by "sqlobject.dburi") is used.

    The hub is not instantiated until an attempt is made to
    use the database.
    """
    def __init__(self, packagename):
        self.packagename = packagename
        self.hub = None

    def __get__(self, obj, type):
        if self.hub:
            return self.hub.__get__(obj, type)
        else:
            return self

    def __set__(self, obj, type):
        if not self.hub:
            self.set_hub()
        return self.hub.__set__(obj, type)

    def __getattr__(self, name):
        if not self.hub:
            self.set_hub()
        try:
            return getattr(self.hub, name)
        except AttributeError:
            return getattr(self.hub.getConnection(), name)

    def set_hub(self):
        dburi = config.get("%s.dburi" % self.packagename, None)
        if not dburi:
            dburi = config.get("sqlobject.dburi", None)
        if not dburi:
            raise KeyError, "No database configuration found!"
        if dburi.startswith("notrans_"):
            dburi = dburi[8:]
            trans = False
        else:
            trans = True
        hub = _hubs.get(dburi, None)
        if not hub:
            hub = AutoConnectHub(dburi, supports_transactions=trans)
            _hubs[dburi] = hub
        self.hub = hub

def set_db_uri(dburi, package=None):
    """Sets the database URI to use either globally or for a specific
    package. Note that once the database is accessed, calling
    setDBUri will have no effect.

    @param dburi: database URI to use
    @param package: package name this applies to, or None to set the default.
    """
    if package:
        config.update({"%s.dburi" % package : dburi})
    else:
        config.update({"sqlobject.dburi" : dburi})

def commit_all():
    """Commit the transactions in all registered hubs (for this thread)."""
    for hub in hub_registry:
        hub.commit()

def rollback_all():
    """Rollback the transactions in all registered hubs (for this thread)."""
    for hub in hub_registry:
        hub.rollback()

def end_all():
    """End the transactions in all registered hubs (for this thread)."""
    for hub in hub_registry:
        hub.end()

def restart_transaction(args):
    if have_transactions:
        zope_transaction.begin()

def dispatch_exception(exception, args, kw):
    # errorhandling import here to avoid circular imports
    from gearshift.errorhandling import dispatch_error
    # Keep in mind func is not the real func but _expose
    real_func, accept, allow_json, controller = args[:4]
    args = args[4:]
    exc_type, exc_value, exc_trace = sys.exc_info()
    remove_keys(kw, ("tg_source", "tg_errors", "tg_exceptions"))
    try:
        output = dispatch_error(
            controller, real_func, None, exception, *args, **kw)
    except NoApplicableMethods:
        raise exc_type, exc_value, exc_trace
    else:
        del exc_trace
        return output

def so_to_dict(sqlobj):
    """Convert SQLObject to a dictionary based on columns."""
    d = {}
    if sqlobj is None:
        return d # stops recursion
    for name in sqlobj.sqlmeta.columns.keys():
        d[name] = getattr(sqlobj, name)
    d['id'] = sqlobj.id # id must be added explicitly
    if sqlobj._inheritable:
        d.update(so_to_dict(sqlobj._parent))
        d.pop('childName')
    return d

def so_columns(sqlclass, columns=None):
    """Return a dict with all columns from a SQLObject.

    This includes the columns from InheritableSO's bases.

    """
    if columns is None:
        columns = {}
    columns.update(filter(lambda i: i[0] != 'childName',
                          sqlclass.sqlmeta.columns.items()))
    if sqlclass._inheritable:
        so_columns(sqlclass.__base__, columns)
    return columns

def so_joins(sqlclass, joins=None):
    """Return a list with all joins from a SQLObject.

    The list includes the columns from InheritableSO's bases.

    """
    if joins is None:
        joins = []
    joins.extend(sqlclass.sqlmeta.joins)
    if sqlclass._inheritable:
        so_joins(sqlclass.__base__, joins)
    return joins

def EndTransactions():
    end_all()

__all__ = ["metadata", "session",
           "get_engine", "get_metadata",
           "PackageHub", "AutoConnectHub", "set_db_uri",
           "commit_all", "rollback_all", "end_all", "so_to_dict",
           "so_columns", "so_joins", "EndTransactions"]
