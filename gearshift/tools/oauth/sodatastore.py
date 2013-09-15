from datetime import datetime
import logging
import uuid

import cherrypy

from oauth import oauth

from sqlobject import SQLObject, SQLObjectNotFound, RelatedJoin, \
    DateTimeCol, IntCol, StringCol, UnicodeCol, ForeignKey

from gearshift.database.so import PackageHub
from gearshift.util import load_class
from gearshift import config

hub = PackageHub("gearshift.oauth")
__connection__ = hub

token_class = None
nonce_class = None

log = logging.getLogger("gearshift.oauth.sodatastore")

class OAuthConsumer(oauth.OAuthConsumer):
    def __init__(self, key, secret, user):
        super(OAuthConsumer, self).__init__(key, secret)
        
        self.user = user

class OAuthDataStore(oauth.OAuthDataStore):
    def __init__(self):
        super(OAuthDataStore, self).__init__()
        
        global token_class
        token_class_path = config.get("tools.oauth.sodatastore.model.token",
            "gearshift.tools.oauth.sodatastore.TG_Token")
        token_class = load_class(token_class_path)
        if token_class:
            log.info("Successfully loaded \"%s\"" % token_class_path)

        global nonce_class
        nonce_class_path = config.get("tools.oauth.sodatastore.model.nonce",
            "gearshift.tools.oauth.sodatastore.TG_Nonce")
        nonce_class = load_class(nonce_class_path)
        if nonce_class:
            log.info("Successfully loaded \"%s\"" % nonce_class_path)

    def lookup_consumer(self, key):
        try:
            api_token = token_class.by_key(key)
        except SQLObjectNotFound:
            log.error('OAuthDataStore:consumer not found!')
            return None

        return OAuthConsumer(api_token.key, api_token.secret, api_token.user)

    def lookup_token(self, token_type, token):
        try:
            token = token_class.by_key(token)
        except SQLObjectNotFound:
            return None

        return oauth.OAuthToken(token.key, token.secret)

    def lookup_nonce(self, oauth_consumer, oauth_token, nonce):
        try:
            db_nonce = nonce_class.by_nonce_consumer(nonce, oauth_consumer.key)
        except SQLObjectNotFound:
            # Nonces are not created here, but in OAuthTool.before_finalize.
            # Which is a good thing, because methods called "lookup" shouldn't
            # really do anything but look things up.
            return None

        # Nonce is not unique
        return db_nonce.nonce

    def fetch_request_token(self, oauth_consumer):
        api_token = token_class.by_key(oauth_consumer.key)
        user = api_token.user
        
        request_token = token_class(token_type=token_class.TOKEN_REQUEST, 
                                    user=user, label=api_token.label)
                                    
        request_token.label = api_token.label
        return oauth.OAuthToken(request_token.key, request_token.secret)

    def fetch_access_token(self, oauth_consumer, oauth_token):
        api_token = token_class.by_key(oauth_consumer.key)
        user = api_token.user
        
        # Check if request token has been authorized
        request_token = token_class.by_key(oauth_token.key)
        if not request_token.authorized:
            log.warning('request_token not authorized!')
            return None

        # Upgrade request token to access token
        access_token = request_token.upgrade()
        return oauth.OAuthToken(access_token.key, access_token.secret)

    def authorize_request_token(self, oauth_token, user):
        try:
            request_token = token_class.by_key(oauth_token.key)
        except SQLObjectNotFound:
            return None
        
        # Make sure only the token owner can authorize the token
        if request_token.user != user:
            return None

        request_token.authorized = True
        return oauth.OAuthToken(request_token.key, request_token.secret)

def make_hash():
    # SHA1 hashing
    text = str(uuid.uuid1())
    try: 
        import hashlib # Python 2.5
        obj = hashlib.sha1(text)
    except ImportError:        
        import sha # Python 2.4
        obj = sha.sha(text)
    return obj.hexdigest()

class TG_Token(SQLObject):
    TOKEN_API = 0
    TOKEN_REQUEST = 1
    TOKEN_ACCESS = 2
    
    class sqlmeta:
        table = "tg_token"

    key = UnicodeCol(length=40, default=make_hash, alternateID=True, 
                     alternateMethodName="by_key")
    secret = UnicodeCol(length=40, default=make_hash)
    label = UnicodeCol(length=40)
    token_type = IntCol(default=TOKEN_API)
    scopes = UnicodeCol(length=128, default="")
    authorized = IntCol(default=0)
    created = DateTimeCol(default=datetime.now)
    
    user = ForeignKey("User")
        
    def upgrade(self):
        self.token_type = self.TOKEN_ACCESS
        
        # Upgraded token gets new key and secret just in case
        self.key = make_hash()
        self.secret = make_hash()
        
        return self 

    def reset_key(self):
        # Upgraded token gets new key and secret just in case
        self.key = make_hash()
        self.secret = make_hash()
        
        return self
   
class TG_Nonce(SQLObject):
    class sqlmeta:
        table = "tg_nonce"
        
    nonce = UnicodeCol(length=255, alternateID=True, 
                       alternateMethodName="by_nonce")
    consumer_key = UnicodeCol(length=255, alternateID=True, alternateMethodName='by_consumer_key')
    expires = DateTimeCol(default=datetime.now)
    
    @classmethod
    def by_nonce_consumer(cls, nonce, consumer_key):
        """
            Fetches a nonce entry associated with a specific consumer key.
            
            This method is NOT automatically generated.
        """
        try:
            result = cls.selectBy(nonce=nonce, consumer_key=consumer_key)[0]
        except IndexError:
            raise SQLObjectNotFound
        return result
