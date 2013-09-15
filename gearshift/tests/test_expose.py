import simplejson
from gearshift import controllers, expose
from gearshift.testutil import make_app, start_server, stop_server

def setup_module():
    start_server()

def teardown_module():
    stop_server()


class ExposeRoot(controllers.RootController):

    _cp_config = { "tools.expose.on" : True ,
                   "tools.flash.on" : True }

    @expose("gearshift.tests.simple")
    @expose("json")
    def with_json(self):
        return dict(title="Foobar", mybool=False, someval="foo")

    @expose("gearshift.tests.simple")
    @expose("json", accept_format = "application/json", as_format="json")
    @expose('genshi:gearshift.tests.textfmt', accept_format="text/plain", 
            format="text")
    def with_json_via_accept(self):
        return dict(title="Foobar", mybool=False, someval="foo")

def test_gettinghtml():
    app = make_app(ExposeRoot)
    response = app.get("/with_json")
    assert "Paging all foo" in response

def test_gettingjson():
    app = make_app(ExposeRoot)
    response = app.get("/with_json?tg_format=json")
    assert '"title": "Foobar"' in response

def test_gettingjsonviaaccept():
    app = make_app(ExposeRoot)
    response = app.get("/with_json_via_accept",
            headers=dict(Accept="application/json"))
    assert '"title": "Foobar"' in response

def test_getting_json_with_accept_but_using_tg_format():
    app = make_app(ExposeRoot)
    response = app.get("/with_json_via_accept?tg_format=json")
    assert '"title": "Foobar"' in response

def test_getting_plaintext():
    app = make_app(ExposeRoot)
    response = app.get("/with_json_via_accept",
        headers=dict(Accept="text/plain"))
    assert response.body == "This is a plain text for foo."

def test_allow_json():

    class NewRoot(controllers.RootController):
        _cp_config = { "tools.flash.on" : True }
        
        @expose(template="gearshift.tests.doesnotexist", allow_json=True)
        def test(self):
            return dict(title="Foobar", mybool=False, someval="niggles")

    app = make_app(NewRoot)
    response = app.get("/test", headers= dict(accept="application/json"))
    values = simplejson.loads(response.body)
    assert values == dict(title="Foobar", mybool=False, someval="niggles",
        tg_flash=None)
    assert response.headers["Content-Type"] == "application/json"
    response = app.get("/test?tg_format=json")
    values = simplejson.loads(response.body)
    assert values == dict(title="Foobar", mybool=False, someval="niggles",
        tg_flash=None)
    assert response.headers["Content-Type"] == "application/json"
