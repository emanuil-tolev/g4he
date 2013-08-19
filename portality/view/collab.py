from flask import Blueprint, request, abort, make_response, render_template, redirect
from flask.ext.login import current_user

import portality.util as util
from portality.core import app
import portality.models as models
import portality.g4hemodels as gmodels

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
@blueprint.route("/<mainorg>/benchmarking.<suffix>", methods=["GET"])
def benchmarking(mainorg=None, suffix=None):
    if request.method == "GET":
        returntype = "csv" if suffix == "csv" else "html"
        return GET_benchmarking(mainorg, returntype)
    elif request.method == "POST":
        return POST_benchmarking(mainorg)

def GET_benchmarking(mainorg, returntype):
    if returntype == "html":
        return render_template('collab/bench.html', mainorg=mainorg)
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
    # two differnent queries to service them
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
    
    # pass the parameters to the Collaboration model
    c = gmodels.Collaboration()
    top_collabs = c.ordered_collaborators(mainorg, count)
    
    # make the response and send it back
    if form == "json":
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
    c = gmodels.Collaboration()
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
    
    # if we've been asked for the landing page for the collaboration report,
    # don't bother doing any of the hard work
    if (result_format == "html" and funder is None and start is None and
            end is None and lower is None and upper is None and len(collab_orgs) == 0):
        return render_template('collab/collab.html', mainorg=mainorg, report=None)
    
    c = gmodels.Collaboration()
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
            row['endDate'] = p.get("project", {}).get("fund", {}).get("end")
            report.append(row)
    
    data = {
        "rows" : report,
        "facets" : facets,
        "count" : count
    }
    
    if result_format == "html":
        return render_template('collab/collab.html', mainorg=mainorg, report=data)
    
    elif result_format == "csv":
        headers = ["collaborator", "project title", "collaboration size", "funding", "funder", "award ref", "start date", "end date"]
        rows = []
        for row in report:
            rows.append([row['collaborator'], row['projectTitle'], row['collaborationSize'], row['projectValue'], row['funder'], row['awardRef'], row['startDate'], row['endDate']])
        return _make_csv(mainorg + " Collaborations Report", headers, rows)
        
    elif result_format == "json":
        resp = make_response(json.dumps(data))
        resp.mimetype = "application/json"
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
    
