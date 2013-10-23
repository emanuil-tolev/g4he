
from copy import deepcopy
from datetime import datetime

from portality.dao import DomainObject as DomainObject
from portality.core import app

'''
Define models in here. They should all inherit from the DomainObject.
Look in the dao.py to learn more about the default methods available to the DomainObject which is a version of the DomainObject.
When using portality in your own flask app, perhaps better to make your own models file somewhere and copy these examples
'''

#  a config indextype simply for storing config vars
class Config(DomainObject):
    __type__ = 'config'


# Raw GtR models
class Project(DomainObject):
    __type__ = "project"
    INDEX = app.config.get('GTR_INDEX','gtr')

class CerifProject(DomainObject):
    __type__ = "cerifproject"
    INDEX = app.config.get('GTR_INDEX','gtr')

class Person(DomainObject):
    __type__ = "person"
    INDEX = app.config.get('GTR_INDEX','gtr')
    
    @classmethod
    def org_record(cls, person_id):
        full_pers = cls.pull_by_key("person.id", person_id)
        org = full_pers.get("organisation")
        return org

class PersonHistory(DomainObject):
    __type__ = "personhistory"
    INDEX = app.config.get('GTR_INDEX','gtr')
    
    @classmethod
    def get_org_id(cls, person_id, project_id):
        q = {
            "query" : {
                "bool" : {
                    "must" : [
                        { "term" : { "project.exact" : project_id } },
                        { "term" : { "person.exact" : person_id } }
                    ]
                }
            }
        }
        res = cls.query(q=q)
        orgs = [r.get("_source", {}).get("org") for r in res.get("hits", {}).get("hits", [])]
        
        if len(orgs) > 0:
            return orgs[0]
        return None
    
class Organisation(DomainObject):
    __type__ = "organisation"
    INDEX = app.config.get('GTR_INDEX','gtr')
    
class Publication(DomainObject):
    __type__ = "publication"
    INDEX = app.config.get('GTR_INDEX','gtr')
    
class CerifClass(DomainObject):
    __type__ = "cerifclass"
    INDEX = app.config.get('GTR_INDEX','gtr')

class RecordA(DomainObject):
    __type__ = "record"
    INDEX = 'g4hea'

class RecordB(DomainObject):
    __type__ = "record"
    INDEX = 'g4heb'

class Record(DomainObject):
    __type__ = "record"
    
    # custom target attribute so that the Record class can be retrieved from
    # one of the two possible record indices
    @classmethod
    def target(cls,layer='type'):
        t = str(app.config['ELASTIC_SEARCH_HOST'])
        t = t.rstrip('/') + '/'
        if layer == 'host': return t
        
        t += Config.pull('indexing').data['live'] if Config.pull('indexing') is not None else str(app.config['ELASTIC_SEARCH_DB'])
        t += '/'
        if layer == 'index': return t

        return t + cls.__type__ + '/'


    def ordered_collaborators(self, mainorg, count):
        q = deepcopy(query_template)
        qo = deepcopy(query_org_template)
        
        size = count + 1 if count != 0 else 0
        
        qo['term']["collaboratorOrganisation.canonical.exact"] = mainorg
        q['query']['filtered']['query']['bool']['must'].append(qo)
        q["facets"]["collaborators"]["terms_stats"]["size"] = size
        
        result = self.query(q=q)
        terms = result.get("facets", {}).get("collaborators", {}).get("terms", [])
        
        # the first result is always the mainorg
        terms = terms[1:]
        
        for t in terms:
            t['formatted_total'] = "{:,.0f}".format(t['total'])
        
        return terms

    def ordered_funders(self, mainorg):
        q = deepcopy(query_template)
        qo = deepcopy(query_org_template)
        
        qo['term']["collaboratorOrganisation.canonical.exact"] = mainorg
        q['query']['filtered']['query']['bool']['must'].append(qo)
        
        result = self.query(q=q)
        facets = result.get("facets", {})
        terms = facets.get("funders", {}).get("terms", [])
        
        for t in terms:
            t['formatted_total'] = "{:,.0f}".format(t['total'])
        
        return terms
        
    def all_funders(self):
        q = deepcopy(all_funders_template)
        result = self.query(q=q)
        terms = result.get("facets", {}).get("funders", {}).get("terms", [])
        return terms
    
    def grant_categories(self):
        q = deepcopy(grant_categories_template)
        result = self.query(q=q)
        terms = result.get("facets", {}).get("categories", {}).get("terms", [])
        return terms

    def collaboration_report(self, mainorg, funder=None, collab_orgs=[], start=None, end=None, lower=None, upper=None):
        q = deepcopy(query_template)
        
        # main organisation
        qmo = deepcopy(query_org_template)
        qmo['term']["collaboratorOrganisation.canonical.exact"] = mainorg
        q['query']['filtered']['query']['bool']['must'].append(qmo)
        
        # collaborating organisations
        for org in collab_orgs:
            qo = deepcopy(query_org_template)
            qo['term']["collaboratorOrganisation.canonical.exact"] = org
            q['query']['filtered']['query']['bool']['must'].append(qo)
        
        # funder
        if funder is not None and funder != "":
            qf = deepcopy(query_funder_template)
            qf['term']['primaryFunder.name.exact'] = funder
            q['query']['filtered']['query']['bool']['must'].append(qf)
        
        # start date
        if start != "" and start is not None:
            qs = deepcopy(query_start_template)
            qs['range']['project.fund.end']['from'] = start
            q['query']['filtered']['query']['bool']['must'].append(qs)
        
        # end date 
        if end != "" and end is not None:
            qe = deepcopy(query_end_template)
            qe['range']['project.fund.start']['to'] = end
            q['query']['filtered']['query']['bool']['must'].append(qe)
        
        # lower project value bound
        if lower != "" and lower is not None:
            ql = deepcopy(query_lower_template)
            ql['range']['project.fund.valuePounds']['from'] = lower
            q['query']['filtered']['query']['bool']['must'].append(ql)
        
        # upper project value bound
        if upper != "" and upper is not None:
            qu = deepcopy(query_upper_template)
            qu['range']['project.fund.valuePounds']['to'] = upper
            q['query']['filtered']['query']['bool']['must'].append(qu)
        
        result = self.query(q=q)
        projects = [i.get("_source") for i in result.get("hits", {}).get("hits", [])]
        facets = result.get("facets", {})
        count = result.get("hits", {}).get("total", 0)
        
        return projects, facets, count
        

# Query Templates
##################################################################################

# collaborator organisation template.
# Used where a term query to exactly match the organisation name is needed
#
query_org_template = {
    "term" : {"collaboratorOrganisation.canonical.exact" : None}
}

# funding organisation template
# Used where a term query to exactly match the primary funder's name is needed

query_funder_template = {
    "term" : {"primaryFunder.name.exact" : None}
}

# I know these two look like they're the wrong way round, but they are not.
query_end_template = {
    "range" : {
        "project.fund.start" : {
            "to" : "<end of range>"
        }
    }
}

query_start_template = {
    "range" : {
        "project.fund.end" : {
            "from" : "<start of range>"
        }
    }
}

query_lower_template = {
    "range" : {
        "project.fund.valuePounds" : {
            "from" : "<lower limit of funding>"
        }
    }
}

query_upper_template = {
    "range" : {
        "project.fund.valuePounds" : {
            "to" : "<upper limit of funding>"
        }
    }
}

# Main Collaborator query
# Used to retrieve all collaboration information in one huge hit
#
query_template = {
    "query" : {
        "filtered": {
            "query" : {
                "bool" : {
                    "must" : []
                }
            },
            "filter" : {
                "script" : {
                    "script" : "doc['collaboratorOrganisation.canonical.exact'].values.size() > 1"
                }
            }
        }
    },
    "size" : 10000,
    "facets" : {
        "collaborators" : {
            "terms_stats" : {
                "key_field" : "collaboratorOrganisation.canonical.exact",
                "value_field" : "project.fund.valuePounds",
                "size" : 0
            }
        },
        "funders" : {
            "terms_stats" : {
                "key_field" : "primaryFunder.name.exact",
                "value_field" : "project.fund.valuePounds",
                "size" : 0
            }
        },
        "value_stats" : {
            "statistical" : {
                "field" : "project.fund.valuePounds"
            }
        }
    }
}

all_funders_template = {
    "query" : {
        "match_all" : {}
    },
    "size" : 0,
    "facets" : {
        "funders" : {
            "terms" : {
                "field" : "primaryFunder.name.exact",
                "all_terms" : True
            }
        }
    }
}

grant_categories_template = {
    "query" : {
        "match_all" : {}
    },
    "size" : 0,
    "facets" : {
        "categories" : {
            "terms" : {
                "field" : "project.grantCategory.exact",
                "all_terms" : True
            }
        }
    }
}


# The account object, which requires the further additional imports
# There is a more complex example below that also requires these imports
from werkzeug import generate_password_hash, check_password_hash
from flask.ext.login import UserMixin

class Account(DomainObject, UserMixin):
    __type__ = 'account'

    @classmethod
    def pull_by_email(cls,email):
        res = cls.query(q='email:"' + email + '"')
        if res.get('hits',{}).get('total',0) == 1:
            return cls(**res['hits']['hits'][0]['_source'])
        else:
            return None

    @property
    def recentsearches(self):
        res = SearchHistory.query(terms={'user':current_user.id}, sort={"_created" + app.config.get('FACET_FIELD','.exact'):{"order":"desc"}}, size=100)
        return [i.get('_source',{}) for i in res.get('hits',{}).get('hits',[])]

    def set_password(self, password):
        self.data['password'] = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.data['password'], password)

    @property
    def is_super(self):
        return not self.is_anonymous() and self.id in app.config['SUPER_USER']
        

class SearchHistory(DomainObject):
    __type__ = 'searchhistory'


# This could be used with account signup approval processes to store accounts that have been 
# created but not yet approved via email confirmation.
class UnapprovedAccount(Account):
    __type__ = 'unapprovedaccount'
    
    def requestvalidation(self):
        # send an email to account email address and await response, unless in debug mode
        # validate link is like http://siteaddr.net/username?validate=key
        msg = "Hello " + self.id + "\n\n"
        msg += "Thanks for signing up with " + app.config['SERVICE_NAME'] + "\n\n"
        msg += "In order to validate and enable your account, please follow the link below:\n\n"
        msg += app.config['SITE_URL'] + "/" + self.id + "?validate=" + self.data['validate_key'] + "\n\n"
        msg += "Thanks! We hope you enjoy using " + app.config['SERVICE_NAME']
        if not app.config['DEBUG']:
            util.send_mail([self.data['email']], app.config['EMAIL_FROM'], 'validate your account', msg)
        
    def validate(self,key):
        # accept validation and create new account
        if key == self.data['validate_key']:
            del self.data['validate_key']
            account = Account(**self.data)
            account.save()
            self.delete()
            return account
        else:
            return None

            
            

