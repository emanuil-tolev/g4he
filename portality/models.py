
from copy import deepcopy
from datetime import datetime
import json

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
    
    definition_map = {
        "leadro" : "leadRo.name.exact",
        "principal_investigator" : "principalInvestigator.organisation.name.exact",
        "co_investigator" : "coInvestigator.organisation.name.exact",
        "cofunder" : "coFunder.name.exact",
        "project_partner" : "projectPartner.name.exact",
        "collaboration" : "collaboration.name.exact",
        "fellow" : "fellow.name.exact"
    }
    
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


    def ordered_collaborators(self, mainorg, count, collaboration_definition, start=None):
        q = CollaborationQuery()
        # q.set_size(0) # we don't need any project results
        q.set_main_org(mainorg)
        
        # start date
        if start != "" and start is not None:
            q.set_start(start)
        
        # determine the size of the result set we want.  Note that due to a bug in 
        # Elasticsearch, we actually want to make this much bigger than the requirement (so we add 10000)
        #excess = 10000
        #size = count + 1 + excess if count != 0 else 0
        #q.set_terms_stats_size("collaborators", size)
        size = 10000
        q.set_size(size)
        
        # add each of the collaboration definition facets
        #for cd in collaboration_definition:
        #    mapped = self.definition_map.get(cd)
        #    if mapped is None:
        #        continue
        #    q.add_terms_facet(cd, mapped, size)
        
        # add only the fields that we are interested in
        q.add_field("project.fund.valuePounds")
        for cd in collaboration_definition:
            mapped = self.definition_map.get(cd)
            if mapped is None:
                continue
            q.add_field(mapped)
        
        # do the query
        # print json.dumps(q.query)
        result = self.query(q=q.query)
        
        # make sure we got everything
        total = result.get("hits", {}).get("total")
        if total > size:
            q.set_size(total)
            result = self.query(q=q.query)
        
        fields = [hit.get("fields") for hit in result.get("hits", {}).get("hits", [])]
        
        collaborator_facet = {}
        for field in fields:
            # extract a unique list of the orgs in this record
            all_orgs = []
            for key, orgs in field.iteritems():
                if key == "project.fund.valuePounds": continue    
                if isinstance(orgs, list):
                     for o in orgs:
                        if o not in all_orgs: all_orgs.append(o)
                else:
                    if orgs not in all_orgs: all_orgs.append(orgs)
            
            # find out the value of the project
            value = field.get("project.fund.valuePounds")
            
            # for each org sum the value, and increment/start the count
            for org in all_orgs:
                # add to the collaborator_facet, or append to the org_record in that facet
                # and increment a counter for number of projects
                if org in collaborator_facet:
                    collaborator_facet[org]["count"] += 1
                    collaborator_facet[org]["total"] += value
                else:
                    collaborator_facet[org] = {"term" : org, "count" : 1, "total": value}
        
        facet = collaborator_facet.values()
        for f in facet:
            f["formatted_total"] = "{:,.0f}".format(f['total'])
        
        return sorted(facet, key=lambda f: f["count"], reverse=True)[1:]
        
    def ordered_funders(self, mainorg, start=None):
        q = CollaborationQuery()
        q.set_size(0) # we don't need any project results
        q.set_main_org(mainorg)
        
        # start date
        if start != "" and start is not None:
            q.set_start(start)
        
        # do the query
        result = self.query(q=q.query)
        
        # get the terms stats facet
        terms = result.get("facets", {}).get("funders", {}).get("terms", [])
        
        # format the money and return
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

    def collaboration_report(self, mainorg, collaboration_definition, funder=None, collab_orgs=[], start=None, end=None, lower=None, upper=None, category=None, status=None):
        q = CollaborationQuery()
        q.set_main_org(mainorg)
        
        # add each of the collaboration definition facets
        for cd in collaboration_definition:
            mapped = self.definition_map.get(cd)
            if mapped is None:
                continue
            q.add_terms_facet(cd, mapped, 10000) # FIXME: hardcoded size, which should catch everything, re: ES bug in facet counts
        
        # translate the collaboration definitions to fields (could do this at the same time as the above, if we wanted)
        cdefn = [self.definition_map.get(cd) for cd in collaboration_definition if self.definition_map.get(cd) is not None]
        
        # collaborating organisations
        for org in collab_orgs:
            q.add_collaborator(org, cdefn)
        
        # funder
        if funder is not None and funder != "":
            q.set_funder(funder)
        
        # start date
        if start != "" and start is not None:
            q.set_start(start)
        
        # end date 
        if end != "" and end is not None:
            q.set_end(end)
        
        # lower project value bound
        if lower != "" and lower is not None:
            q.set_lower(lower)
        
        # upper project value bound
        if upper != "" and upper is not None:
            q.set_upper(upper)
        
        # grant category
        if category != "" and category is not None:
            q.set_grant_category(category)
        
        # project status
        if status != "" and status is not None:
            q.set_project_status(status)
        
        # do the query
        result = self.query(q=q.query)
        
        # return the report object
        report = CollaborationReport(result, collaboration_definition)
        return report

# Collaboration Report object
##################################################################################

class CollaborationReport(object):
    definition_map = {
        "leadro" : "leadRo",
        "principal_investigator" : "principalInvestigator",
        "co_investigator" : "coInvestigator",
        "cofunder" : "coFunder",
        "project_partner" : "projectPartner",
        "collaboration" : "collaboration",
        "fellow" : "fellow"
    }
    
    def __init__(self, es_result, collaboration_definition):
        self.raw = es_result
        self.collaboration_definition = collaboration_definition
        self.projects = [i.get("_source") for i in self.raw.get("hits", {}).get("hits", [])]
        
        # format the numbers in the facets
        for f in self.raw.get("facets", {}).get("collaborators", {}).get("terms"):
            f['formatted_total'] = "{:,.0f}".format(f['total'])
        
        # format the numbers for the value stats
        self.raw["facets"]['value_stats']['formatted_total'] = "{:,.0f}".format(self.raw.get("facets", {}).get("value_stats", {}).get("total", 0))
        
        # format the numbers for the funders
        for f in self.raw.get("facets", {}).get("funders", {}).get("terms"):
            f['formatted_total'] = "{:,.0f}".format(f['total'])
    
    def count(self):
        return self.raw.get("hits", {}).get("total", 0)
    
    def collaborators(self, project):
        org_dict = {}
        for cd in self.collaboration_definition:
            mapped = self.definition_map.get(cd)
            # print mapped
            if mapped is None:
                continue
            orgs = project.get(mapped, [])
            # print orgs
            # special treatment for PI and CoI
            if mapped == "principalInvestigator" or mapped == "coInvestigator":
                orgs = [o.get("organisation") for o in orgs]
            for org in orgs:
                # this ensures that we only ever keep one record per organisation
                org_dict[org.get("name")] = org
        # just return the values of the dict
        return org_dict.values()
    
    def roles(self, org, project):
        rs = []
        for cd in self.collaboration_definition:
            mapped = self.definition_map.get(cd)
            if mapped is None:
                continue
            print mapped
            orgs = project.get(mapped, [])
            
            # special treatment for PI and CoI
            if mapped == "principalInvestigator" or mapped == "coInvestigator":
                orgs = [o.get("organisation") for o in orgs]
            for o in orgs:
                print o, o.get("name")
                if org == o.get("name"):
                    rs.append(mapped)
        return list(set(rs))
            
    def collaborators_facet(self):
        # get the deduplicated list of collaborators that are allowed
        duplicated_all = []
        for cd in self.collaboration_definition:
            duplicated_all += [t.get("term") for t in self.raw.get("facets", {}).get(cd, {}).get("terms", [])]
        unique_collaborators = set(duplicated_all)
        
        # now go through the full collaborator terms stats and keep the ones which belong to defined collaborators
        newterms = []
        for t in self.raw.get("facets", {}).get("collaborators", {}).get("terms", []):       
            if t.get("term") in unique_collaborators:
                # format the numbers here, as it is easier than in javascript
                t['formatted_total'] = "{:,.0f}".format(t['total'])
                
                # keep this one
                newterms.append(t)
        
        return newterms
    
    def value_stats(self):
        return self.raw.get("facets", {}).get("value_stats", {})
        
    def funders_facet(self):
        return self.raw.get("facets", {}).get("funders", {}).get("terms", [])

# Collaboration Query manager
##################################################################################

class CollaborationQuery(object):
    # collaboration specific query templates
    org_template = { "term" : {"collaboratorOrganisation.canonical.exact" : None} }
    funder_template = { "term" : {"primaryFunder.name.exact" : None} }
    start_template = { "range" : { "project.fund.end" : { "from" : "<start of range>" } } }   # these two look the wrong way round
    end_template = { "range" : { "project.fund.start" : { "to" : "<end of range>" } } }       # but they are not!
    lower_template = { "range" : { "project.fund.valuePounds" : { "from" : "<lower limit of funding>" } } }
    upper_template = { "range" : { "project.fund.valuePounds" : { "to" : "<upper limit of funding>" } } }
    category_template = { "term" : { "project.grantCategory.exact" : None } }
    status_template = { "term" : { "project.status.exact" : None } }
    
    # generic ES query templates
    terms_stats = { "terms_stats" : {"key_field" : None, "value_field" : None, "size" : 0} }
    terms = { "terms" : {"field" : None, "size" : 0} }
    bool_should = {"bool" : {"should" : [], "minimum_number_should_match" : 1 }}
    term = {"term" : {}}
    
    # the base query upon which the report is broadly based
    base_query = {
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
                    "size" : 0 # for terms_stats, this means "get all of them" (not the same as a normal terms facets)
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
    
    def __init__(self):
        # the copy of the base query that we'll be working with
        self.query = deepcopy(self.base_query)
    
    def add_field(self, field):
        if "fields" not in self.query:
            self.query["fields"] = []
        if field not in self.query["fields"]:
            self.query["fields"].append(field)
    
    def set_size(self, size):
        self.query["size"] = size
    
    def set_main_org(self, mainorg):
        qo = deepcopy(self.org_template)
        qo['term']["collaboratorOrganisation.canonical.exact"] = mainorg
        self.query['query']['filtered']['query']['bool']['must'].append(qo)
    
    def set_terms_stats_size(self, name, size):
        self.query["facets"][name]["terms_stats"]["size"] = size
    
    def add_terms_facet(self, name, field, size):
        f = deepcopy(self.terms)
        f["terms"]["field"] = field
        f["terms"]["size"] = size
        self.query["facets"][name] = f
        
    def add_collaborator(self, org, fields):
        should = deepcopy(self.bool_should)
        for field in fields:
            t = deepcopy(self.term)
            t["term"][field] = org
            should["bool"]["should"].append(t)
        self.query["query"]["filtered"]["query"]["bool"]["must"].append(should)
    
    def set_funder(self, funder):
        qf = deepcopy(self.funder_template)
        qf['term']['primaryFunder.name.exact'] = funder
        self.query['query']['filtered']['query']['bool']['must'].append(qf)
        
    def set_start(self, start):
        qs = deepcopy(self.start_template)
        qs['range']['project.fund.end']['from'] = start
        self.query['query']['filtered']['query']['bool']['must'].append(qs)
    
    def set_end(self, end):
        qe = deepcopy(self.end_template)
        qe['range']['project.fund.start']['to'] = end
        self.query['query']['filtered']['query']['bool']['must'].append(qe)
        
    def set_lower(self, lower):
        ql = deepcopy(self.lower_template)
        ql['range']['project.fund.valuePounds']['from'] = lower
        self.query['query']['filtered']['query']['bool']['must'].append(ql)
        
    def set_upper(self, upper):
        qu = deepcopy(self.upper_template)
        qu['range']['project.fund.valuePounds']['to'] = upper
        self.query['query']['filtered']['query']['bool']['must'].append(qu)
        
    def set_grant_category(self, category):
        qg = deepcopy(self.category_template)
        qg['term']['project.grantCategory.exact'] = category
        self.query['query']['filtered']['query']['bool']['must'].append(qg)
    
    def set_project_status(self, status):
        qs = deepcopy(self.status_template)
        qs['term']['project.status.exact'] = status
        self.query['query']['filtered']['query']['bool']['must'].append(qs)

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

            
            

