from flask import Blueprint, request, abort, make_response, render_template, redirect

import portality.util as util
import portality.models as models
import portality.mine as mine
from portality.view.forms import dropdowns

from datetime import datetime
from copy import deepcopy
import json, csv, StringIO, time, os, requests

blueprint = Blueprint('organisation', __name__)

# base organisation api
#####################################################################

@blueprint.route("/")
def organisations():

    if 'q' in request.values:
        query = {
            "query" : {
                "query_string" : {
                    "query" : "collaboratorOrganisation.canonical:*" + request.values['q'] + "*"
                }
            },
            "size" : 0,
            "facets" : {
                "orgs" : {
                    "terms" : {
                        "field" : "collaboratorOrganisation.canonical.exact",
                        "size" : 25,
                        "script" : "term.toLowerCase() contains '" + request.values['q'].lower() + "'"
                    }
                }
            }
        }
        r = models.Record.query(q=query)
        resp = make_response(json.dumps(r['facets']['orgs']['terms']))
        resp.mimetype = "application/json"
        return resp
        
    else:

        #logofolder = os.path.dirname(os.path.abspath( __file__ )).replace('/view','/static/logos')
        #logos=sorted(os.listdir(logofolder))
        logos = []

        return render_template(
            'organisation/orgs.html',
            logos=logos,
            orgs=json.dumps(dropdowns('record','collaboratorOrganisation.canonical'))
        )


@blueprint.route("/<mainorg>")
@blueprint.route("/<mainorg>.json")
def organisation(mainorg, raw=False):
    # TODO:
    # list all this orgs projects
    # list a blurb and website about this org
    # list the main contact of this org (and perhaps other users)
    # offer ability to update the page about this org
    # show this org snapshot data, top projects, recent funding by years, pubs
    # offer a download report overview of this org

    #logo = mainorg.lower().replace(' ','_').replace("'",'').replace('university_','').replace('_university','').replace('_of','').replace('of_','').replace('_the','').replace('the_','').replace('_and','').replace('and_','').replace('_for','').replace('for_','').replace('_.','.') + '.png';
    
    #logofolder = os.path.dirname(os.path.abspath( __file__ )).replace('/view','/static/logos')
    #logos=os.listdir(logofolder)
    #if logo not in logos:
    #    logo = ''
    #else:
    #    logo = '/static/logos/' + logo
    logo = ""

    qry = {
        "query": {
            "term": {
                "collaboratorOrganisation.canonical.exact": mainorg
            }
        },
        "size": 0,
        "facets": {
            "collaborators":{
                "terms_stats" : {
                    "key_field" : "collaboratorOrganisation.canonical.exact",
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
    r = models.Record.query(q=qry)

    org = {
        'name': mainorg,
        'logo': logo,
        'projects': r.get('hits',{}).get('total',0),
        'collaborators': len(r.get('facets',{}).get('collaborators',{}).get('terms',[])) - 1,
        'totalfunding': "{:,.0f}".format(r.get('facets',{}).get('value_stats',{}).get('total',0))
    }

    # TODO: should really have an org object with the above info in it and it 
    # should be passed to the page instead of the mainorg string
    if raw:
        return org
    elif util.request_wants_json():
        resp = make_response(json.dumps(org))
        resp.mimetype = "application/json"
        return resp
    else:
        return render_template('organisation/org.html', org=org)




# matching report
#####################################################################

@blueprint.route("/<mainorg>/matching", methods=["GET", "POST"])
@blueprint.route("/<mainorg>/matching.<suffix>", methods=["GET", "POST"])
def matching(mainorg, suffix=None):

    # get any match parameters provided in the request
    if request.json:
        project = request.json.get('project',[])
        person = request.json.get('person',[])
        keyword = request.json.get('keyword',[])
        url = request.json.get('url',[])
    else:
        project = request.values.get('project',"").split(',')
        person = request.values.get('person',"").split(',')
        keyword = request.values.get('keyword',"").split(',')
        url = request.values.get('url',"").split(',')

    # process the match parameters into search parameters
    # TODO: should make this a dict by weightings and include them from below
    # and also enable end users to prioritise certain keywords or types
    # TODO: perhaps also add maximums from each source, or maximum length of params overall?    
    params = []
    for k in keyword:
        if k not in params and len(k) > 0: params.append(k)

    for pr in project:
        # match project title to a project
        if len(pr) > 0:
            r = models.Record.pull_by_key('project.title',pr)
            if r is not None:
                extract = mine.mine_project_record(r)
                count = 0 # TODO: proper control of how many url-extracted keywords to include
                for e in extract:
                    for i in extract[e]:
                        count += 1
                        if count <= 10:
                            if i not in params: params.append(i.replace('(','')) # TODO: regex out anything non-az09

    for u in url:
        if len(u) > 0:
            if not u.startswith('http://') and not u.startswith('https://'):
                u = 'http://' + u
            #try:
            r = requests.get(u)
            clean = mine.html_text(r.text)
            extract = mine.full_extract(web_text=clean, web_weight=5)
            count = 0 # TODO: proper control of how many url-extracted keywords to include
            for e in extract:
                for i in extract[e]:
                    count += 1
                    if count <= 10:
                        if i not in params: params.append(i)
            #except:
            #    pass

    potential = []
    # perform the search with the defined params and build a list of matching orgs
    if len(params) > 0 or len(person) > 0:
        qry = {
            'query': {
                'bool': {
                    'must': [
                        {
                            'query_string': {
                                'query': " OR ".join(params)
                            }
                        }
                    ],
                    'must_not': [
                        {
                            'term': {
                                'collaboratorOrganisation.canonical.exact': mainorg
                            }
                        }
                    ]
                }
            },
            "size": 1000,
            "facets" : {
                "collaborators" : {
                    "terms" : {
                        "field" : "collaboratorOrganisation.canonical.exact",
                        "size" : 100
                    }
                }
            }
        }

        # add people, if any , to the search
        if len(person) > 0:
            qry['query']['bool']['should'] = []
            qry['query']['bool']['minimum_should_match'] = 1
            for p in person:
                if len(p) > 0:
                    qry['query']['bool']['should'].append({
                        'term': {
                            'collaboratorPerson.canonical.exact': p
                        }
                    })

        # get the collaborator orgs found in the search results
        # strip the ones who already collaborate with the mainorg
        # then find out some info about the remaining ones
        r = models.Record.query(q=qry)
        collabs = [i['term'] for i in r.get("facets", {}).get("collaborators", {}).get("terms", [])]

        cs = [i['term'] for i in models.Record().ordered_collaborators(mainorg=mainorg,count=10000)]

        for collab in collabs:
            if collab not in cs and len(potential) < 10:
                p = organisation(collab, raw=True)
                p['related'] = []
                for i in r.get("hits", {}).get("hits",[]):
                    canonicals = [l.get('canonical','') for l in i['_source'].get('collaboratorOrganisation',[])]
                    title = i['_source']['project']['title']
                    if collab in canonicals and mainorg not in canonicals and title not in p['related']:
                        p['related'].append(title)
                potential.append(p)
                
        
    matchinfo = {
        "new_potential": potential,
        "params": params,
        "person": person,
        "project": project,
        "keyword": keyword,
        "url": url
    }
    
    if util.request_wants_json():
        resp = make_response(json.dumps(matchinfo))
        resp.mimetype = "application/json"
        return resp
    elif suffix == "csv":
        output = StringIO.StringIO()
        writer = csv.writer(output)
    
        if len(potential) > 0:
            headers = ["name","projects","collaborators","funding","related"]
            writer.writerow(headers)
            for p in potential:
                r = [
                    p['name'],
                    p['projects'],
                    p['collaborators'],
                    p['totalfunding'],
                    len(p['related'])
                ]
                writer.writerow(r)
    
        resp = make_response(output.getvalue())
        resp.mimetype = "text/csv"
        resp.headers['Content-Disposition'] = 'attachment; filename="' + mainorg + '_new_potential_report.csv"'
        return resp
    else:
        return render_template('organisation/match.html', org=mainorg, matchinfo=matchinfo)









# benchmarking report
#####################################################################

@blueprint.route("/<mainorg>/allfunders")
def allfunders(mainorg=None):
    c = models.Record()
    funders = c.all_funders()
    resp = make_response(json.dumps(funders))
    resp.mimetype = "application/json"
    return resp

@blueprint.route("/<mainorg>/grantcategories")
def grantcategories(mainorg=None):
    c = models.Record()
    funders = c.grant_categories()
    resp = make_response(json.dumps(funders))
    resp.mimetype = "application/json"
    return resp

# FIXME: this is a near-straight copy of the valueCount report, with a different
# query and different thing returned, but all the guts are the same.  This stuff
# is becoming in urgent need of a refactor
@blueprint.route("/<mainorg>/benchmarking/details", methods=["POST"])
def details(mainorg=None):
    j = request.json
    benchmark = {"parameters" : j, "report" : {}}
    
    q = deepcopy(projects_query_template)
    
    start = j.get("start")
    end = j.get("end")
    
    try:
        if start is not None:
            start = datetime.strftime(datetime.strptime(start, "%d/%m/%Y"), "%Y-%m-%d")
        if end is not None:
            end = datetime.strftime(datetime.strptime(end, "%d/%m/%Y"), "%Y-%m-%d")
    except ValueError:
        # do nothing, it's fine
        pass
    
    # build in the standard parts of the query
    if j.get("start", "") != "":
        qs = deepcopy(b_query_start_template)
        qs['range']['project.fund.start']['from'] = start
        q['query']['bool']['must'].append(qs)
    
    if j.get("end", "") != "":
        qe = deepcopy(b_query_end_template)
        qe['range']['project.fund.start']['to'] = end
        q['query']['bool']['must'].append(qe)
    
    if j.get("funder", "") != "":
        qf = deepcopy(query_funder_template)
        qf["term"]["primaryFunder.name.exact"] = j.get("funder")
        q['query']['bool']['must'].append(qf)
        
    if j.get("grantcategory", "") != "":
        qg = deepcopy(b_grant_category_template)
        qg["term"]["project.grantCategory.exact"] = j.get("grantcategory")
        q['query']['bool']['must'].append(qg)
    
    # for each of the additional orgs, do the same query with the different org
    for o in j.get("compare_org", []):
        org_query = deepcopy(q)
        if j.get("leadonly", False):
            qo = deepcopy(leadro_template)
            qo['term']["leadRo.name.exact"] = o
            org_query['query']['bool']['must'].append(qo)
        else:
            qo = deepcopy(query_org_template)
            qo['term']["collaboratorOrganisation.canonical.exact"] = o
            org_query['query']['bool']['must'].append(qo)
        print json.dumps(org_query)
        compare_result = models.Record.query(q=org_query)
        benchmark["report"][o] = [hit.get("_source", {}) for hit in compare_result.get("hits", {}).get("hits", [])]
        
    # for each of the groups of people do the group query
    for gname, people in j.get("compare_groups", {}).iteritems():
        pers_query = deepcopy(q)
        qp = deepcopy(b_group_template)
        for person in people:
            qp["terms"]["collaboratorPerson.canonical.exact"].append(person)
        pers_query["query"]["bool"]["must"].append(qp)
        result = models.Record.query(q=pers_query)
        benchmark["report"][gname] = [hit.get("_source", {}) for hit in compare_result.get("hits", {}).get("hits", [])]
    
    # now make the response
    resp = make_response(json.dumps(benchmark))
    resp.mimetype = "application/json"
    return resp

@blueprint.route("/<mainorg>/benchmarking", methods=["GET", "POST"])
@blueprint.route("/<mainorg>/benchmarking.<suffix>", methods=["GET"])
def benchmarking(mainorg=None, suffix=None):
    if request.method == "GET":
        returntype = "csv" if suffix == "csv" else "html"
        return GET_benchmarking(mainorg, returntype)
    elif request.method == "POST":
        return POST_benchmarking(mainorg)

def GET_benchmarking(mainorg, returntype):
    if returntype == "html":
        return render_template('organisation/bench.html', mainorg=mainorg)
    elif returntype == "csv":
        j = request.values.get("obj")
        obj = json.loads(j)
        benchmark = {"parameters" : obj, "report" : {}}
        return _get_csv(mainorg, benchmark)
        
def _get_csv(mainorg, benchmark):
    # call generic method to calculate the benchmarking data
    _populate_benchmark(mainorg, benchmark)

    value_field = "count"
    date_field = "time"
    if benchmark["parameters"]["type"] == "award_value":
        value_field = "total"
    
    rows, dates, orgs = _get_report_rows(benchmark["report"], value_field=value_field, date_field=date_field)

    output = StringIO.StringIO()
    writer = csv.writer(output)
    
    headers = ["date"] + [org for org in orgs]
    writer.writerow(headers)
    for row in rows:
        formatted = [time.strftime("%Y-%m-%d", time.gmtime(row[0]/1000))] + row[1:]
        writer.writerow(formatted)
    
    resp = make_response(output.getvalue())
    resp.mimetype = "text/csv"
    resp.headers['Content-Disposition'] = 'attachment; filename="' + mainorg + '_benchmarking_report.csv"'
    return resp

def _populate_benchmark(mainorg, benchmark):
    # there are three different kinds of report, and we require
    # two different queries to service them
    if benchmark["parameters"]["type"] == "publications":
        _publicationsReport(mainorg, benchmark["parameters"], benchmark)
    else:
        _valueCountReport(mainorg, benchmark["parameters"], benchmark)

def _get_report_rows(data, value_field="count", date_field="time"):
    dates = []
    orgs = []
    row_sets = {}
    for org in data:
        orgs.append(org)
        org_rows = {}
        for p in data.get(org):
            if p[date_field] not in dates:
                dates.append(p[date_field])
            org_rows[p[date_field]] = p[value_field]
        row_sets[org] = org_rows
    
    dates.sort()
    orgs.sort()
    rows = []
    for date in dates:
        row = [date]
        for org in orgs:
            if date in row_sets[org]:
                row.append(row_sets[org][date])
            else:
                row.append(0)
        rows.append(row)
    
    return rows, dates, orgs

def POST_benchmarking(mainorg):
    j = request.json
    benchmark = {"parameters" : j, "report" : {}}
    
    # call generic method to actually calculate the businesss
    _populate_benchmark(mainorg, benchmark)
    
    # now make the response
    resp = make_response(json.dumps(benchmark))
    resp.mimetype = "application/json"
    return resp

def _publicationsReport(mainorg, j, benchmark):
    q = deepcopy(publications_query_template)
    
    start = j.get("start")
    end = j.get("end")
    
    try:
        if start is not None:
            start = datetime.strftime(datetime.strptime(start, "%d/%m/%Y"), "%Y-%m-%d")
        if end is not None:
            end = datetime.strftime(datetime.strptime(end, "%d/%m/%Y"), "%Y-%m-%d")
    except ValueError:
        # do nothing, it's fine
        pass
    
    # build in the standard parts of the query
    if j.get("start", "") != "":
        qs = deepcopy(b_publication_from_template)
        qs['range']['project.publication.date']['from'] = start
        q['query']['bool']['must'].append(qs)
    
    if j.get("end", "") != "":
        qe = deepcopy(b_publication_to_template)
        qe['range']['project.publication.date']['to'] = end
        q['query']['bool']['must'].append(qe)
    
    if j.get("granularity", "") != "":
        if j.get("granularity") in ["month", "quarter", "year"]:
            q['facets']['publication_dates']['date_histogram']['interval'] = j.get("granularity")
    
    if j.get("funder", "") != "":
        qf = deepcopy(query_funder_template)
        qf["term"]["primaryFunder.name.exact"] = j.get("funder")
        q['query']['bool']['must'].append(qf)
    
    if j.get("grantcategory", "") != "":
        qg = deepcopy(b_grant_category_template)
        qg["term"]["project.grantCategory.exact"] = j.get("grantcategory")
        q['query']['bool']['must'].append(qg)
    
    lower_time = -1 if j.get("start", "") == "" else int(time.mktime(time.strptime(j.get("start"), "%Y-%m-%d"))) * 1000
    upper_time = -1 if j.get("end", "") == "" else int(time.mktime(time.strptime(j.get("end"), "%Y-%m-%d"))) * 1000
    
    for org in j.get("compare_org", []):
        _publicationsBenchmarkOrg(q, org, j.get("leadonly", False), lower_time, upper_time, benchmark)
    
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

def _publicationsBenchmarkOrg(base_query, org, leadonly, lower_time, upper_time, benchmark):
    query = deepcopy(base_query)
    
    if leadonly:
        qo = deepcopy(leadro_template)
        qo['term']["leadRo.name.exact"] = org
        query['query']['bool']['must'].append(qo)
    else:
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
    
    start = j.get("start")
    end = j.get("end")
    
    try:
        if start is not None:
            start = datetime.strftime(datetime.strptime(start, "%d/%m/%Y"), "%Y-%m-%d")
        if end is not None:
            end = datetime.strftime(datetime.strptime(end, "%d/%m/%Y"), "%Y-%m-%d")
    except ValueError:
        # do nothing, it's fine
        pass
    
    # build in the standard parts of the query
    if j.get("start", "") != "":
        qs = deepcopy(b_query_start_template)
        qs['range']['project.fund.start']['from'] = start
        q['query']['bool']['must'].append(qs)
    
    if j.get("end", "") != "":
        qe = deepcopy(b_query_end_template)
        qe['range']['project.fund.start']['to'] = end
        q['query']['bool']['must'].append(qe)
    
    if j.get("granularity", "") != "":
        if j.get("granularity") in ["month", "quarter", "year"]:
            q['facets']['award_values']['date_histogram']['interval'] = j.get("granularity")
    
    if j.get("funder", "") != "":
        qf = deepcopy(query_funder_template)
        qf["term"]["primaryFunder.name.exact"] = j.get("funder")
        q['query']['bool']['must'].append(qf)
        
    if j.get("grantcategory", "") != "":
        qg = deepcopy(b_grant_category_template)
        qg["term"]["project.grantCategory.exact"] = j.get("grantcategory")
        q['query']['bool']['must'].append(qg)
    
    # for each of the additional orgs, do the same query with the different org
    for o in j.get("compare_org", []):
        org_query = deepcopy(q)
        if j.get("leadonly", False):
            qo = deepcopy(leadro_template)
            qo['term']["leadRo.name.exact"] = o
            org_query['query']['bool']['must'].append(qo)
        else:
            qo = deepcopy(query_org_template)
            qo['term']["collaboratorOrganisation.canonical.exact"] = o
            org_query['query']['bool']['must'].append(qo)
        print json.dumps(org_query)
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

leadro_template = {
    "term" : {"leadRo.name.exact" : None}
}

b_grant_category_template = {
    "term" : {"project.grantCategory.exact" : None}
}

projects_query_template = {
    "query" : {
        "bool" : {
        	"must" : []
        }
    },
    "size" : 1000 # a suitably large number
}

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

#############################################################################

# more templates - these can be removed when the benchmarking report is
# refactored to properly encapsulate the ES connection

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

#####################################################################

def _make_csv(name, headers, rows):
    output = StringIO.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    resp = make_response(output.getvalue())
    resp.mimetype = "text/csv"
    resp.headers['Content-Disposition'] = 'attachment; filename="' + name + '.csv"'
    return resp




# collaboration report
######################################################################

@blueprint.route("/<mainorg>/collaboration/top")
@blueprint.route("/<mainorg>/collaboration/top.<form>")
def top(mainorg=None, form="json"):
    # extract the values from the request
    count = int(request.values.get("count", 0))
    
    # pass the parameters to the Record model
    c = models.Record()
    top_collabs = c.ordered_collaborators(mainorg, count)
    
    # make the response and send it back
    if form == "raw":
        return top_collabs
    elif form == "json":
        resp = make_response(json.dumps(top_collabs))
        resp.mimetype = "application/json"
        return resp
    
    elif form == "csv":
        headers = ["organisation", "number of collaborative projects", "total value of collaborative projects"]
        rows = []
        for row in top_collabs:
            rows.append([row['term'], row['count'], row['total']])
            
        return _make_csv(mainorg + " Collaborators", headers, rows)

@blueprint.route("/<mainorg>/collaboration/funders")
@blueprint.route("/<mainorg>/collaboration/funders.<form>")
def funders(mainorg=None, form="json"):
    c = models.Record()
    funders = c.ordered_funders(mainorg)
    
    if form == "json":
        resp = make_response(json.dumps(funders))
        resp.mimetype = "application/json"
        return resp
    
    elif form == "csv":
        headers = ["funder", "number of collaborative projects funded", "total value of collaborative projects funded"]
        rows = []
        for row in funders:
            rows.append([row['term'], row['count'], row['total']])
            
        return _make_csv(mainorg + " Collaboration Funders", headers, rows)

@blueprint.route('/<mainorg>/collaboration')
def collaboration(mainorg=None):
            
    # allowable parameters of the report
    funder = request.values.get("funder")
    start = request.values.get("start")
    end = request.values.get("end")
    lower = request.values.get("lower")
    upper = request.values.get("upper")
    collab_orgs = []
    result_format = request.values.get("format", "html")
    
    for k, v in request.values.items():
        if k.startswith("collab"):
            orgs = v.split(",")
            collab_orgs += orgs
    
    # we want the start and end dates in a nice big-endian format, so we 
    # may need to rejig them
    try:
        if start is not None:
            start = datetime.strftime(datetime.strptime(start, "%d/%m/%Y"), "%Y-%m-%d")
        if end is not None:
            end = datetime.strftime(datetime.strptime(end, "%d/%m/%Y"), "%Y-%m-%d")
    except ValueError:
        # do nothing, it's fine
        pass
    
    # if we've been asked for the landing page for the collaboration report,
    # don't bother doing any of the hard work
    if (result_format == "html" and funder is None and start is None and
            end is None and lower is None and upper is None and len(collab_orgs) == 0):
        return render_template('organisation/collab.html', mainorg=mainorg, report=None)
    
    c = models.Record()
    projects, facets, count = c.collaboration_report(mainorg, 
                                funder=funder, collab_orgs=collab_orgs,
                                start=start, end=end, 
                                lower=lower, upper=upper)
    
    
    # format the numbers in the facets
    for f in facets.get("collaborators", {}).get("terms"):
        f['formatted_total'] = "{:,.0f}".format(f['total'])
    
    facets['value_stats']['formatted_total'] = "{:,.0f}".format(facets.get("value_stats", {}).get("total", 0))
    
    for f in facets.get("funders", {}).get("terms"):
        f['formatted_total'] = "{:,.0f}".format(f['total'])
    
    # generate the report rows
    report = []
    for p in projects:
        for co in p.get("collaboratorOrganisation", []):
            # if the collaborating organisation is the main organisation, skip it
            if co.get("canonical") == mainorg:
                continue
            
            row = {}
            row["pid"] = p.get("id")
            row['collaborator'] = co.get("canonical")
            row['projectTitle'] = p.get("project", {}).get("title", "untitled")
            row['projectValue'] = p.get("project", {}).get("fund", {}).get("valuePounds", 0)
            row['formattedProjectValue'] = "{:,.0f}".format(row["projectValue"])
            row['collaborationSize'] = len(p.get("collaboratorOrganisation", []))
            row['awardRef'] = p.get("project", {}).get("grantReference", "unknown")
            row['funder'] = p.get("primaryFunder", {}).get("name", "unknown")
            row['startDate'] = p.get("project", {}).get("fund", {}).get("start")
            row["formattedStartDate"] = datetime.strftime(datetime.strptime(row["startDate"], "%Y-%m-%d"), "%d/%m/%Y")
            row['endDate'] = p.get("project", {}).get("fund", {}).get("end")
            row["formattedEndDate"] = datetime.strftime(datetime.strptime(row["endDate"], "%Y-%m-%d"), "%d/%m/%Y")
            
            # extract the PIs (of which there should only be one)
            pis = p.get("principalInvestigator", [])
            if len(pis) > 0:
                row["principalInvestigator"] = pis[0].get("person", {}).get("firstName", "") + " " + pis[0].get("person", {}).get("surname", "")
                row["piOrganisation"] = pis[0].get("organisation", {}).get("name", "")
            else:
                row["principalInvestigator"] = ""
                row["piOrganisation"] = ""
            
            report.append(row)
    
    data = {
        "rows" : report,
        "facets" : facets,
        "count" : count
    }
    
    #FIXME: we need to do a proper treatment of the HTML version of the report with arguments - at the 
    # moment the report is basically ignored
    if result_format == "html":
        return render_template('organisation/collab.html', mainorg=mainorg, report=data)

    elif result_format == "json":
        resp = make_response(json.dumps(data))
        resp.mimetype = "application/json"
        return resp

    elif result_format == "csv":
        headers = ["collaborator", "project title", "principal investigator", "pi organisation" , "number of project collaborators", "total project funding", 
                    "funder", "award ref", "project start date", "project end date"]
        rows = []
        for row in report:
            rows.append([row['collaborator'], row['projectTitle'], row["principalInvestigator"], row["piOrganisation"], row['collaborationSize'], row['projectValue'], 
                    row['funder'], row['awardRef'], row['startDate'], row['endDate']])
        return _make_csv(mainorg + " Collaborations Report", headers, rows)
            
    abort(406)

    
