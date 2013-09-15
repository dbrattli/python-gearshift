import gearshift
from gearshift import controllers, expose
from gearshift.testutil import make_app, start_server, stop_server

import cherrypy
from cherrypy import request

def setup_module():
    start_server()

def teardown_module():
    stop_server()

class Ringtones(controllers.RestController):
    exposed = True

    _cp_config = {
        "rest_idname" : "ringtone_id",
        "rest_format" : "format"
    }

    # We can choose to use GET_ONE/GET_ALL instead of GET, so for this controller we test the support
    # for GET_ONE/GET_ALL

    # Get all ringtones (ringtone_id='all')
    def GET_ALL(self, **kwargs):
        phone_id = kwargs.get('phone_id', 'all')
        person_id = kwargs.get('person_id', 'all')
        
        ret = "%s Ringtones phone_id=%s, person_id=%s"% \
            (request.method, phone_id, person_id)
        return ret
    
    # Get ringtone (ringtone_id=xyz)
    def GET_ONE(self, ringtone_id, **kwargs):
        phone_id = kwargs.get('phone_id', 'all')
        person_id = kwargs.get('person_id', 'all')
        
        ret = "%s Ringtone ringtone_id=%s, phone_id=%s, person_id=%s"% \
            (request.method, ringtone_id, phone_id, person_id)
        return ret
    
class Phones(controllers.RestController):
    exposed = True

    _cp_config = {
        "rest_idname" : "phone_id",
        "rest_format" : "format"
    }
    
    ringtones = Ringtones()
    
    # Get phone(s)
    def GET(self, phone_id='all', person_id='all'):
        return "%s Phones phone_id=%s, person_id=%s" % \
            (request.method, phone_id, person_id)
    
    # Create new phone
    def POST(self, phone, person_id):
        cherrypy.response.status = "201 Created"
        return "%s Phones person_id=%s, phone=%s" % \
            (request.method, person_id, phone)

    # Update phone
    def PUT(self, phone, phone_id, person_id):
        return "PUT Phones phone_id=%s, person_id=%s, phone=%s" % \
            (phone_id, person_id, phone)
            
    @gearshift.expose()
    def edit(self, phone_id):
        return "edit Phones phone_id=%s" % phone_id
        
    # Get new phone form
    @gearshift.expose()
    def new(self):
        return "new Phones form"

class People(controllers.RestController):
    exposed = True

    _cp_config = {
        "rest_idname" : "person_id",
        "rest_format" : "format"
    }

    phones = Phones()
    
    def GET(self, person_id="all", **kw):
        return "%s People person_id=%s" % (request.method, person_id)
    
    def PUT(self, person_id, format='xml'):
        return "PUT People person_id=%s, format=%s" % \
            (person_id, format)
    
    @gearshift.expose()
    def edit(self, person_id, **kw):
        return "edit People person_id=%s" % person_id
                            
class Root(controllers.Controller):
    people = People()
    
    @gearshift.expose()
    def index(self):
        return "running"

def test_Rest_Dispatch():
    d = gearshift.dispatch.RestDispatcher()
    conf = {'/people': {'request.dispatch': d}}

    app = make_app(Root, conf=conf)
    
    response = app.get("/")
    assert response.status == "200 OK"

    # Get all people
    response = app.get("/people")
    assert response.status == "200 OK"
#    print response.body
    assert response.body == "GET People person_id=all"
    
    # Get person 345
    response = app.get("/people/345")
    assert response.status == "200 OK"
    assert response.body == "GET People person_id=345"

    # Get edit form for person 345
    response = app.get("/people/345/edit")
    assert response.status == "200 OK"
    assert response.body == "edit People person_id=345"
    
    # Get all phones for all people
    response = app.get("/people/phones")
    assert response.status == "200 OK"
    assert response.body == "GET Phones phone_id=all, person_id=all"

    # Get phone 5 for person 3
    response = app.get("/people/3/phones/5")
    assert response.status == "200 OK"
    assert response.body == "GET Phones phone_id=5, person_id=3"

    # Get phone 1 for person 1 (repeated value)
    response = app.get("/people/1/phones/1")
    assert response.status == "200 OK"
    assert response.body == "GET Phones phone_id=1, person_id=1"

    # Create a new phone for a person 4
    response = app.post("/people/4/phones/", dict(phone="new"))
    assert response.status == "201 Created"
    assert response.body == "POST Phones person_id=4, phone=new"

    # Update phone 3 for a person 4
    response = app.put("/people/4/phones/3", dict(phone="update"))
    assert response.status == "200 OK"
    assert response.body == "PUT Phones phone_id=3, person_id=4, phone=update"

    # Update phone 3 for a person 4
    response = app.post("/people/4/phones/3?_method=PUT", dict(phone="update"))
    assert response.status == "200 OK"
    assert response.body == "PUT Phones phone_id=3, person_id=4, phone=update"

    # Get all ringtones for all phones for all people
    response = app.get("/people/phones/ringtones")
    assert response.status == "200 OK"
    assert response.body == "GET Ringtones phone_id=all, person_id=all"

    # Get all ringtones for phone 5
    response = app.get("/people/phones/5/ringtones")
    assert response.status == "200 OK"
    assert response.body == "GET Ringtones phone_id=5, person_id=all"

    # Get all ringtones for all phones for a person 3
    response = app.get("/people/3/phones/ringtones")
    assert response.status == "200 OK"
    assert response.body == "GET Ringtones phone_id=all, person_id=3"

    # Get ringtone 4 for phone 45 for a person 3
    response = app.get("/people/3/phones/45/ringtones/4")
    assert response.status == "200 OK"
    assert response.body == "GET Ringtone ringtone_id=4, phone_id=45, " \
                       "person_id=3"

    # Should not exist
    response = app.get("/phones/2", status=404)

    # Should not exist
    response = app.get("/phones/2/people/3", status=404)

    # Request JSON using .json
    response = app.put("/people/2.json")
    assert response.body == "PUT People person_id=2, format=json"

