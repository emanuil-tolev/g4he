from copy import deepcopy

from portality.core import app
from portality.dao import DomainObject as DomainObject

class Collaboration(DomainObject):
    __type__ = "record"
    
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
