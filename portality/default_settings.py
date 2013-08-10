SECRET_KEY = "default-key" # make this something secret in your overriding app.cfg

# contact info
ADMIN_NAME = "Cottage Labs LLP"
ADMIN_EMAIL = ""

# service info
SERVICE_NAME = "G4HE"
SERVICE_TAGLINE = "The gateway for higher education"
HOST = "0.0.0.0"
DEBUG = True
PORT = 5004

# list of superuser account names
SUPER_USER = ["test"]

PUBLIC_REGISTER = True # Can people register publicly? If false, only the superuser can create new accounts
SHOW_LOGIN = True # if this is false the login link is not shown in the default template, but login is not necessarily disabled

# elasticsearch settings
ELASTIC_SEARCH_HOST = "http://localhost:9200"
ELASTIC_SEARCH_DB = "g4he2"
INITIALISE_INDEX = False # whether or not to try creating the index and required index types on startup
NO_QUERY_VIA_API = ['account'] # list index types that should not be queryable via the API
PUBLIC_ACCESSIBLE_JSON = True # can not logged in people get JSON versions of pages by querying for them?

# if search filter is true, anonymous users only see visible and accessible pages in query results
# if search sort and order are set, all queries from /query will return with default search unless one is provided
# placeholder image can be used in search result displays
ANONYMOUS_SEARCH_FILTER = False
SEARCH_SORT = ''
SEARCH_SORT_ORDER = ''

JSITE_OPTIONS = {'facetview':{}}

# a dict of the ES mappings. identify by name, and include name as first object name
# and identifier for how non-analyzed fields for faceting are differentiated in the mappings
FACET_FIELD = ".exact"
MAPPINGS = {
    "record" : {
        "record" : {
            "dynamic_templates" : [
                {
                    "default" : {
                        "match" : "*",
                        "match_mapping_type": "string",
                        "mapping" : {
                            "type" : "multi_field",
                            "fields" : {
                                "{name}" : {"type" : "{dynamic_type}", "index" : "analyzed", "store" : "no"},
                                "exact" : {"type" : "{dynamic_type}", "index" : "not_analyzed", "store" : "yes"}
                            }
                        }
                    }
                }
            ]
        }
    }
}
MAPPINGS['account'] = {'account':MAPPINGS['record']['record']}

