from flask import Blueprint, request, abort, make_response, render_template, redirect
from flask.ext.login import current_user

import portality.util as util
from portality.core import app
import portality.models as models

from copy import deepcopy
import json, csv, StringIO, time

blueprint = Blueprint('collab', __name__)

# base organisation api
#####################################################################

@blueprint.route("/")
def organisation():
    q = request.values.get("q")
    query = deepcopy(org_search_query)
    query["facets"]["orgs"]["terms"]["script"] = "term.toLowerCase() contains '" + q.lower() + "'"
    result = models.Record.query(q=query)
    terms = result.get("facets", {}).get("orgs", {}).get("terms")
    return make_response(json.dumps(terms))

org_search_query = {
    "query" : {
    	"match_all" : {}
    },
    "size" : 0,
    "facets" : {
        "orgs" : {
            "terms" : {
                "field" : "collaboratorOrganisation.canonical.exact",
                "size" : 25,
                "script" : "term.toLowerCase() contains '<q>'"
            }
        }
    }
}

# FIXME: mainorg is currently ignored here, as there is no way to constrain the list of people
# to the supplied organisation with the index in its current form
@blueprint.route("/person")
@blueprint.route("/<mainorg>/person")
def person(mainorg=None):
    q = request.values.get("q")
    query = deepcopy(person_search_query)
    query["facets"]["people"]["terms"]["script"] = "term.toLowerCase() contains '" + q.lower() + "'"
    result = models.Record.query(q=query)
    terms = result.get("facets", {}).get("people", {}).get("terms")
    return make_response(json.dumps(terms))

person_search_query = {
    "query" : {
    	"match_all" : {}
    },
    "size" : 0,
    "facets" : {
        "people" : {
            "terms" : {
                "field" : "collaboratorPerson.canonical.exact",
                "size" : 25,
                "script" : "term.toLowerCase() contains '<q>'"
            }
        }
    }
}

# benchmarking report
#####################################################################

@blueprint.route("/<mainorg>/benchmarking", methods=["GET", "POST"])
def benchmarking(mainorg=None):
    if request.method == "GET":
        return GET_benchmarking(mainorg)
    elif request.method == "POST":
        return POST_benchmarking(mainorg)

def GET_benchmarking(mainorg):
    return render_template('collab/bench.html', mainorg=mainorg)

def POST_benchmarking(mainorg):
    j = request.json
    benchmark = {"parameters" : j, "report" : {}}
    
    # there are three different kinds of report, and we require
    # two differnent queries to service them
    if j["type"] == "publications":
        _publicationsReport(mainorg, j, benchmark)
    else:
        _valueCountReport(mainorg, j, benchmark)
    
    # now make the response
    resp = make_response(json.dumps(benchmark))
    resp.mimetype = "application/json"
    return resp

def _publicationsReport(mainorg, j, benchmark):
    q = deepcopy(publications_query_template)
    
    # build in the standard parts of the query
    if j.get("start", "") != "":
        qs = deepcopy(b_publication_from_template)
        qs['range']['project.publication.date']['from'] = j.get("start")
        q['query']['bool']['must'].append(qs)
    
    if j.get("end", "") != "":
        qe = deepcopy(b_publication_to_template)
        qe['range']['project.publication.date']['to'] = j.get("end")
        q['query']['bool']['must'].append(qe)
    
    if j.get("granularity", "") != "":
        if j.get("granularity") in ["month", "quarter", "year"]:
            q['facets']['publication_dates']['date_histogram']['interval'] = j.get("granularity")
    
    lower_time = -1 if j.get("start", "") == "" else int(time.mktime(time.strptime(j.get("start"), "%Y-%m-%d"))) * 1000
    upper_time = -1 if j.get("end", "") == "" else int(time.mktime(time.strptime(j.get("end"), "%Y-%m-%d"))) * 1000
    
    for org in j.get("compare_org", []):
        _publicationsBenchmarkOrg(q, org, lower_time, upper_time, benchmark)
    
    # for each of the groups of people do the group query
    for gname, people in j.get("compare_groups", {}).iteritems():
        _publicationsBenchmarkGroup(q, gname, people, lower_time, upper_time, benchmark)

def _publicationsBenchmarkGroup(base_query, gname, people, lower_time, upper_time, benchmark):
    query = deepcopy(base_query)
    qp = deepcopy(b_group_template)
    
    for person in people:
        qp["terms"]["collaboratorPerson.canonical.exact"].append(person)
    query["query"]["bool"]["must"].append(qp)
    
    result = models.Record.query(q=query)
    entries = result.get("facets", {}).get("publication_dates", {}).get("entries")
    
    _trimTimesAndAdd(gname, entries, lower_time, upper_time, benchmark)

def _publicationsBenchmarkOrg(base_query, org, lower_time, upper_time, benchmark):
    query = deepcopy(base_query)
    qo = deepcopy(query_org_template)
    
    qo['term']["collaboratorOrganisation.canonical.exact"] = org
    query['query']['bool']['must'].append(qo)
    
    result = models.Record.query(q=query)
    entries = result.get("facets", {}).get("publication_dates", {}).get("entries")
    
    _trimTimesAndAdd(org, entries, lower_time, upper_time, benchmark)

def _trimTimesAndAdd(name, entries, lower_time, upper_time, benchmark):
    if lower_time > -1 or upper_time > -1:
        valid_entries = []
        for entry in entries:
            print entry["time"]
            if entry["time"] >= lower_time and (upper_time == -1 or entry["time"] <= upper_time):
                print "valid"
                valid_entries.append(entry)
        benchmark["report"][name] = valid_entries
    else:
        benchmark["report"][name] = entries

def _valueCountReport(mainorg, j, benchmark):
    q = deepcopy(valuecount_query_template)
    
    # build in the standard parts of the query
    if j.get("start", "") != "":
        qs = deepcopy(b_query_start_template)
        qs['range']['project.fund.start']['from'] = j.get("start")
        q['query']['bool']['must'].append(qs)
    
    if j.get("end", "") != "":
        qe = deepcopy(b_query_end_template)
        qe['range']['project.fund.start']['to'] = j.get("end")
        q['query']['bool']['must'].append(qe)
    
    if j.get("granularity", "") != "":
        if j.get("granularity") in ["month", "quarter", "year"]:
            q['facets']['award_values']['date_histogram']['interval'] = j.get("granularity")
    
    # for each of the additional orgs, do the same query with the different org
    for o in j.get("compare_org", []):
        org_query = deepcopy(q)
        qo = deepcopy(query_org_template)
        qo['term']["collaboratorOrganisation.canonical.exact"] = o
        org_query['query']['bool']['must'].append(qo)
        compare_result = models.Record.query(q=org_query)
        benchmark["report"][o] = compare_result.get("facets", {}).get("award_values", {}).get("entries")
        
    # for each of the groups of people do the group query
    for gname, people in j.get("compare_groups", {}).iteritems():
        pers_query = deepcopy(q)
        qp = deepcopy(b_group_template)
        for person in people:
            qp["terms"]["collaboratorPerson.canonical.exact"].append(person)
        pers_query["query"]["bool"]["must"].append(qp)
        result = models.Record.query(q=pers_query)
        benchmark["report"][gname] = result.get("facets", {}).get("award_values", {}).get("entries")

publications_query_template = {
    "query" : {
        "bool" : {
        	"must" : []
        }
    },
    "size" : 0,
    "facets" : {
        "publication_dates" : {
            "date_histogram" : {
                "field" : "project.publication.date",
                "interval" : "quarter"
            }
        }
    }
}

b_publication_to_template = {
    "range" : {
        "project.publication.date" : {
            "to" : "<end of range>"
        }
    }
}

b_publication_from_template = {
    "range" : {
        "project.publication.date" : {
            "from" : "<start of range>"
        }
    }
}


valuecount_query_template = {
    "query" : {
        "bool" : {
        	"must" : []
        }
    },
    "size" : 0,
    "facets" : {
        "award_values" : {
            "date_histogram" : {
                "key_field" : "project.fund.start",
                "value_field" : "project.fund.valuePounds",
                "interval" : "quarter"
            }
        }
    }
}

b_query_end_template = {
    "range" : {
        "project.fund.start" : {
            "to" : "<end of range>"
        }
    }
}

b_query_start_template = {
    "range" : {
        "project.fund.start" : {
            "from" : "<start of range>"
        }
    }
}

b_group_template = {
	"terms" : {
		"collaboratorPerson.canonical.exact" : []
	}
}


# collaboration report
######################################################################

@blueprint.route('/<mainorg>/collaboration')
def collaboration(mainorg=None):
    q = deepcopy(query_template)
            
    collab_orgs = []
    funder = None
    result_format = "html"
    start = None
    end = None
    lower = None
    upper = None
    
    if mainorg is not None:
        qo = deepcopy(query_org_template)
        qo['term']["collaboratorOrganisation.canonical.exact"] = mainorg
        q['query']['filtered']['query']['bool']['must'].append(qo)
    
    for k,v in request.values.items():
        if k == "org":
            mainorg = v
            qo = deepcopy(query_org_template)
            qo['term']["collaboratorOrganisation.canonical.exact"] = mainorg
            q['query']['filtered']['query']['bool']['must'].append(qo)
            
        if k.startswith("collab"):
            orgs = v.split(",")
            for org in orgs:
                if org == "" or org is None:
                    continue
                qo = deepcopy(query_org_template)
                qo['term']["collaboratorOrganisation.canonical.exact"] = org
                q['query']['filtered']['query']['bool']['must'].append(qo)
                collab_orgs.append(org)
                
        if k == "funder":
            funder = v
            if funder != "" and funder is not None:
                qf = deepcopy(query_funder_template)
                qf['term']['primaryFunder.name.exact'] = funder
                q['query']['filtered']['query']['bool']['must'].append(qf)
        
        if k == "format":
            result_format = v
            
        if k == "start":
            start = v
            if start != "" and start is not None:
                qs = deepcopy(query_start_template)
                qs['range']['project.fund.end']['from'] = start
                q['query']['filtered']['query']['bool']['must'].append(qs)
        
        if k == "end":
            end = v
            if end != "" and end is not None:
                qe = deepcopy(query_end_template)
                qe['range']['project.fund.start']['to'] = end
                q['query']['filtered']['query']['bool']['must'].append(qe)
                
        if k == "lower":
            lower = v
            if lower != "" and lower is not None:
                ql = deepcopy(query_lower_template)
                ql['range']['project.fund.valuePounds']['from'] = lower
                q['query']['filtered']['query']['bool']['must'].append(ql)
        
        if k == "upper":
            upper = v
            if upper != "" and upper is not None:
                qu = deepcopy(query_upper_template)
                qu['range']['project.fund.valuePounds']['to'] = upper
                q['query']['filtered']['query']['bool']['must'].append(qu)

    print mainorg
    
    print json.dumps(q)
    
    result = models.Record.query(q=q)
    projects = [i.get("_source") for i in result.get("hits", {}).get("hits", [])]
    facets = result.get("facets", {})
    count = result.get("hits", {}).get("total", 0)
    
    # format the numbers in the facets
    for f in facets.get("collaborators", {}).get("terms"):
        f['formatted_total'] = "{:,.0f}".format(f['total'])
    
    facets['value_stats']['formatted_total'] = "{:,.0f}".format(facets.get("value_stats", {}).get("total", 0))
    
    for f in facets.get("funders", {}).get("terms"):
        f['formatted_total'] = "{:,.0f}".format(f['total'])
    
    report = []
    for p in projects:
        for co in p.get("collaboratorOrganisation", []):
            # if the collaborating organisation is the main organisation, skip it
            if co.get("canonical") == mainorg:
                continue
            
            row = {"data" : p}
            row['collaborator'] = co.get("canonical")
            row['projectTitle'] = p.get("project", {}).get("title", "untitled")
            row['projectValue'] = p.get("project", {}).get("fund", {}).get("valuePounds", 0)
            row['collaborationSize'] = len(p.get("collaboratorOrganisation", []))
            row['collaboratorRelationship'] = "FIXME"
            row['awardRef'] = p.get("project", {}).get("grantReference", "unknown")
            row['funder'] = p.get("primaryFunder", {}).get("name", "unknown")
            row['principalInvestigator'] = "FIXME"
            row['coInvestigator'] = "FIXME"
            row['startDate'] = p.get("project", {}).get("fund", {}).get("start")
            row['endDate'] = p.get("project", {}).get("fund", {}).get("end")
            report.append(row)
    
    if result_format == "html":
        return render_template('collab/collab.html', mainorg=mainorg, collab_orgs=collab_orgs, funder=funder, report=report, start=start, end=end, facets=facets, lower=lower, upper=upper, count=count)
    elif result_format == "csv":
        output = StringIO.StringIO()
        writer = csv.writer(output)
        writer.writerow(["collaborator", "project title", "collaboration size", "funding", "funder", "award ref", "start date", "end date"])
        for row in report:
            writer.writerow([row['collaborator'], row['projectTitle'], row['collaborationSize'], row['projectValue'], row['funder'], row['awardRef'], row['startDate'], row['endDate']])
        resp = make_response(output.getvalue())
        resp.mimetype = "text/csv"
        resp.headers['Content-Disposition'] = 'attachment; filename="' + mainorg + '_collaboration_report.csv"'
        return resp
    
    abort(406)

@blueprint.route('/project/<pid>')
def project(pid=None):
    mainorg = None
    for k,v in request.values.items():
        if k == "org":
            mainorg = v
    
    if pid is None:
        abort(404)
    
    project = models.Record.pull(pid)
    
    return render_template("collab/project.html", mainorg=mainorg, project=project)
    
query_org_template = {
    "term" : {"collaboratorOrganisation.canonical.exact" : None}
}

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

# includes a very large size, so that we can get the data for all collaborations in one hit
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


'''
{
    "query" : {
	"filtered" : {
      "query": {
          "bool": {
              "must": [
                  {
                      "term": {
                          "collaboratorOrganisation.canonical.exact": "Brunel University"
                      }
                  }
              ]
          }
      },
      "filter" : {
          "script" : {
              "script" : "doc['collaboratorOrganisation.canonical.exact'].values.size() > 1"
          }
      }
    }
    }, 
    "facets": {
    	"collaborators": {
        	"terms_stats": {
            	"value_field": "project.fund.valuePounds", 
                "key_field": "collaboratorOrganisation.canonical.exact", 
                "size": 0
            }
        },
        "funders" : {
            "terms_stats" : {
                "key_field" : "primaryFunder.name.exact",
                "value_field" : "project.fund.valuePounds",
                "size" : 0
            }
        },
        "stat1" : {
            "statistical" : {
                "field" : "project.fund.valuePounds"
            }
        }
    }, 
    "size": 10}
}
'''
