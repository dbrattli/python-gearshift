import logging
from datetime import datetime

from google.appengine.ext import db
from google.appengine.api import memcache

import gearshift
from gearshift import identity
from gearshift.util import load_class

log = logging.getLogger("gearshift.identity.aeprovider")

def to_db_encoding(s, encoding):
    if isinstance(s, str):
        pass
    elif hasattr(s, '__unicode__'):
        s = unicode(s)
    if isinstance(s, unicode):
        s = s.encode(encoding)
    return s


# Global class references --
# these will be set when the provider is initialised.
user_class = None
group_class = None
permission_class = None
visit_class = None
foreign_user_class = None

class AppEngineIdentity(object):
    """Identity that uses a model from a database (via App Engine Datastore)."""

    def __init__(self, visit_key=None, user=None):
        self.visit_key = visit_key
        if user:
            self._user = user
            if visit_key is not None:
                self.login()

    @property
    def user(self):
        """Get user instance for this identity."""
        try:
            return self._user
        except AttributeError:
            # User hasn't already been set
            pass
        # Attempt to load the user. After this code executes, there *will* be
        # a _user attribute, even if the value is None.
        visit = self.visit_link
        if visit:
            try:
                self._user = user_class.get(db.Key(visit.user_id))
            except db.Timeout:
                log.warning("Datastore timeout for user with ID: %s", 
                            visit.user_id)
                self_user = None
                
            if not self._user:
                log.warning("No such user with ID: %s", visit.user_id)
        else:
            self._user = None
        return self._user

    @property
    def user_name(self):
        """Get user name of this identity."""
        if not self.user:
            return None
        return self.user.user_name

    @property
    def user_id(self):
        """Get user id of this identity."""
        if not self.user:
            return None
        return self.user.id

    @property
    def anonymous(self):
        """Return true if not logged in."""
        return not self.user

    @property
    def permissions(self):
        """Get set of permission names of this identity."""
        try:
            return self._permissions
        except AttributeError:
            # Permissions haven't been computed yet
            pass
        if not self.user:
            self._permissions = frozenset()
        else:
            self._permissions = frozenset(
                p.permission_name for p in self.user.permissions)
        return self._permissions

    @property
    def groups(self):
        """Get set of group names of this identity."""
        
        if not self.user:
            return frozenset()
                
        try:
            return self._groups
        except AttributeError:
            # Groups haven't been computed yet
            pass
                
        groups = memcache.get('groups', namespace=str(self.user.key()))
        if groups:
            self._groups = groups
            return groups

        groups = frozenset(ug.group.group_name for ug in self.user.user_groups)
        memcache.set('groups', groups, namespace=str(self.user.key()))
        self._groups = groups

        return groups

    @property
    def group_ids(self):
        """Get set of group IDs of this identity."""
        try:
            return self._group_ids
        except AttributeError:
            # Groups haven't been computed yet
            pass
        if not self.user:
            self._group_ids = frozenset()
        else:
            self._group_ids = frozenset(
                ug.group.id for ug in self.user.user_groups)
        return self._group_ids

    @property
    def visit_link(self):
        """Get the visit link to this identity."""
        if self.visit_key is None:
            return None
        return visit_class.by_visit_key(self.visit_key)

    @property
    def login_url(self):
        """Get the URL for the login page."""
        return identity.get_failure_url()

    def login(self):
        """Set the link between this identity and the visit."""
        visit = self.visit_link
        if visit:
            visit.user_id = str(self._user.key())
        else:
            key = "VISITIDENTITY:%s" % self.visit_key
            visit = visit_class(key_name=key, user_id=str(self._user.key()))
        visit.put()

    def logout(self):
        """Remove the link between this identity and the visit."""
        visit = self.visit_link
        if visit:
            visit.delete()
        # Clear the current identity
        identity.set_current_identity(AppEngineIdentity())


class AppEngineIdentityProvider(object):
    """IdentityProvider that uses a model from a database (via SQLObject)."""

    def __init__(self):
        super(AppEngineIdentityProvider, self).__init__()
        get = gearshift.config.get

        global user_class, group_class, permission_class, visit_class, \
               foreign_user_class

        user_class_path = get("tools.identity.aeprovider.model.user",
            __name__ + ".TG_User")
        user_class = load_class(user_class_path)
        if not user_class:
            log.error("Error loading \"%s\"" % user_class_path)
        try:
            self.user_class_db_encoding = \
                user_class.sqlmeta.columns['user_name'].dbEncoding
        except (KeyError, AttributeError):
            self.user_class_db_encoding = 'UTF-8'
        group_class_path = get("tools.identity.aeprovider.model.group",
            __name__ + ".TG_Group")
        group_class = load_class(group_class_path)
        if not group_class:
            log.error("Error loading \"%s\"" % group_class_path)

        permission_class_path = get("tools.identity.aeprovider.model.permission",
            __name__ + ".TG_Permission")
        permission_class = load_class(permission_class_path)
        if not permission_class:
            log.error("Error loading \"%s\"" % permission_class_path)

        visit_class_path = get("tools.identity.aeprovider.model.visit",
            __name__ + ".TG_VisitIdentity")
        visit_class = load_class(visit_class_path)
        if not visit_class:
            log.info("Error loadeing \"%s\"" % visit_class_path)

        foreign_user_class_path = get("tools.identity.aeprovider.model.foreign_user",
            __name__ + ".TG_ForeignUser")
        foreign_user_class = load_class(foreign_user_class_path)
        if not foreign_user_class:
            log.error("Error loading \"%s\"" % foreign_user_class_path)

        # Default encryption algorithm is to use plain text passwords
        algorithm = get("tools.identity.aeprovider.encryption_algorithm", None)
        self.encrypt_password = lambda pw: \
            identity.encrypt_pw_with_algorithm(algorithm, pw)

    def create_provider_model(self):
        """Create the database tables if they don't already exist."""
        return

    def validate_identity(self, user_name, password, visit_key):
        """Validate the identity represented by user_name using the password.

        Must return either None if the credentials weren't valid or an object
        with the following properties:
            user_name: original user name
            user: a provider dependant object (TG_User or similar)
            groups: a set of group names
            permissions: a set of permission names

        """
        user_name = to_db_encoding(user_name, self.user_class_db_encoding)
        user = user_class.by_user_name(user_name)
        if user:
            if not self.validate_password(user, user_name, password):
                log.info("Passwords don't match for user: %s", user_name)
                return None
            log.info("Associating user (%s) with visit (%s)",
                user_name, visit_key)
            return AppEngineIdentity(visit_key, user)
        else:
            log.warning("No such user: %s", user_name)
            return None
            
    def validate_foreign_user(self, site_id, foreign_user, visit_key):
        fuser = foreign_user_class.lookup_user(site_id, foreign_user)
        if fuser:
            log.info("Associating foreign user (%s) with visit (%s)",
                foreign_user, visit_key)
            return AppEngineIdentity(visit_key, fuser.user)
        else:
            log.warning("No such foreign user: %s", foreign_user)
            return None
        
    def validate_password(self, user, user_name, password):
        """Check the user_name and password against existing credentials.

        Note: user_name is not used here, but is required by external
        password validation schemes that might override this method.
        If you use SqlObjectIdentityProvider, but want to check the passwords
        against an external source (i.e. PAM, a password file, Windows domain),
        subclass SqlObjectIdentityProvider, and override this method.

        """
        return user.password == self.encrypt_password(password)

    def load_identity(self, visit_key):
        """Lookup the principal represented by user_name.

        Return None if there is no principal for the given user ID.

        Must return an object with the following properties:
            user_name: original user name
            user: a provider dependant object (TG_User or similar)
            groups: a set of group names
            permissions: a set of permission names

        """
        return AppEngineIdentity(visit_key)

    def anonymous_identity(self):
        """Return anonymous identity.

        Must return an object with the following properties:
            user_name: original user name
            user: a provider dependant object (TG_User or similar)
            groups: a set of group names
            permissions: a set of permission names

        """
        return SqlObjectIdentity()

    def authenticated_identity(self, user):
        """Constructs Identity object for users with no visit_key."""
        return SqlObjectIdentity(user=user)


class TG_VisitIdentity(db.Model):
    """A visit to your website."""

##    visit_key = db.StringProperty(required=True)
    user_id = db.IntegerProperty()
    
    @classmethod
    def by_visit_key(cls, visit_key):
        """Look up VisitIdentity by given visit key."""
        key = "VISITIDENTITY:%s" % visit_key
        return cls.get_by_key_name(key)

class TG_Group(db.Model):
    """An ultra-simple group definition."""

    group_name = db.StringProperty(required=True)
    display_name = db.StringProperty()
    created = db.DateTimeProperty(auto_now=True)

    # collection of all users belonging to this group
    #users = RelatedJoin("TG_User", intermediateTable="tg_user_group",
    #    joinColumn="group_id", otherColumn="user_id")

    # collection of all permissions for this group
    #permissions = RelatedJoin("TG_Permission", joinColumn="group_id",
    #    intermediateTable="tg_group_permission",
    #    otherColumn="permission_id")

    @classmethod
    def by_group_name(cls, group_name):
        """Look up Group by given group name."""

        query = db.Query(cls)
        query.filter('group_name =', group_name)
        return query.get()
    by_name = by_group_name

class TG_User(db.Model):
    """Reasonably basic User definition."""

    user_name = db.StringProperty(required=True)
    email_address = db.StringProperty(required=True)
    display_name = db.StringProperty()
    password = db.StringProperty()
    created = db.DateTimeProperty(auto_now=True)

    # groups this user belongs to
    #groups = RelatedJoin("TG_Group", intermediateTable="tg_user_group",
    #    joinColumn="user_id", otherColumn="group_id")

    @classmethod
    def by_user_name(cls, user_name):
        """Look up Group by given group name."""
        query = db.Query(cls)
        query.filter('user_name =', user_name)
        return query.get()
    by_name = by_user_name

    @classmethod
    def by_email_address(cls, email_address):
        """Look up User by given email address."""
        query = db.Query(cls)
        query.filter('email_address =', email_address)
        return query.get()
    by_name = by_user_name


    def _get_permissions(self):
        perms = set()
        for g in self.groups:
            perms = perms | set(g.permissions)
        return perms

    def _set_password(self, cleartext_password):
        """Run cleartext_password through the hash algorithm before saving."""
        try:
            hash = identity.current_provider.encrypt_password(cleartext_password)
        except identity.exceptions.IdentityManagementNotEnabledException:
            # Creating identity provider just to encrypt password
            # (so we don't reimplement the encryption step).
            ip = AppEngineIdentityProvider()
            hash = ip.encrypt_password(cleartext_password)
            if hash == cleartext_password:
                log.info("Identity provider not enabled,"
                    " and no encryption algorithm specified in config."
                    " Setting password as plaintext.")
        self._SO_set_password(hash)

    def set_password_raw(self, password):
        """Save the password as-is to the database."""
        self._SO_set_password(password)

class TG_UserGroup(db.Model):
    user = db.ReferenceProperty(TG_User, collection_name="user_groups")
    group = db.ReferenceProperty(TG_Group, collection_name="group_users")
    
class TG_Permission(db.Model):
    """Permissions for a given group."""

    permission_name = db.StringProperty(required=True)
    description = db.StringProperty()

    #groups = RelatedJoin("TG_Group", intermediateTable="tg_group_permission",
    #    joinColumn="permission_id", otherColumn="group_id")

    @classmethod
    def by_permission_name(cls, permission_name):
        """Look up Group by given group name."""
        query = db.Query(cls)
        query.filter('permission_name =', permission_name)
        return query.get()
    by_name = by_permission_name

class TG_GroupPermission(db.Model):
    group = db.ReferenceProperty(TG_Group, collection_name="groups")
    permission = db.ReferenceProperty(TG_User, collection_name="permissons")

class TG_ForeignUser(db.Model):
    """A mapping from foreign users to User"""
        
    user = db.ReferenceProperty(TG_User, collection_name="foreign_users")
    foreign_user = db.StringProperty(required=True)
    site_id = db.StringProperty(required=True)

    @classmethod
    def lookup_user(cls, site_id, foreign_user):
        query = db.Query(cls)
        query.filter('site_id =', site_id)
        query.filter('foreign_user =', foreign_user)
        return query.get()

def encrypt_password(cleartext_password):
    """Encrypt given cleartext password."""
    try:
        hash = identity.current_provider.encrypt_password(cleartext_password)
    except identity.exceptions.RequestRequiredException:
        # Creating identity provider just to encrypt password
        # (so we don't reimplement the encryption step).
        ip = AppEngineIdentityProvider()
        hash = ip.encrypt_password(cleartext_password)
        if hash == cleartext_password:
            log.info("Identity provider not enabled, and no encryption "
                "algorithm specified in config. Setting password as plaintext.")
    return hash
