
from copy import deepcopy
from datetime import datetime
import json, time

from portality.dao import DomainObject as DomainObject
from portality.core import app

'''
Define models in here. They should all inherit from the DomainObject.
Look in the dao.py to learn more about the default methods available to the DomainObject which is a version of the DomainObject.
When using portality in your own flask app, perhaps better to make your own models file somewhere and copy these examples
'''

##########################################################################
# System Configuration
##########################################################################

#  a config indextype simply for storing config vars
class Config(DomainObject):
    __type__ = 'config'


##########################################################################
# Raw GtR models
##########################################################################
# These model objects speak to the GtR raw index which is a clone of any
# data that we collect from their API
##########################################################################

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


##############################################################################
# Alternate index models
##############################################################################
# These classes represent the two possible indexes that we might index into
##############################################################################

class RecordA(DomainObject):
    __type__ = "record"
    INDEX = 'g4hea'

class RecordB(DomainObject):
    __type__ = "record"
    INDEX = 'g4heb'

##############################################################################
# Core Record object
##############################################################################
# This object represents the actual G4HE records, and provides an API through
# which to interact with the content for the purposes of reporting
##############################################################################

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
    
    #######################################################################
    # methods for general information
    #######################################################################
    
    def all_funders(self):
        q = InfoQuery()
        q.add_all_funders()
        result = self.query(q=q.query)
        terms = result.get("facets", {}).get("funders", {}).get("terms", [])
        return terms
    
    def grant_categories(self):
        q = InfoQuery()
        q.add_grant_categories()
        result = self.query(q=q.query)
        terms = result.get("facets", {}).get("categories", {}).get("terms", [])
        return terms
    #######################################################################
    
    #######################################################################
    # methods used for collaboration reports
    #######################################################################

    def ordered_collaborators(self, mainorg, count, collaboration_definition, start=None, order="projects"):
        q = CollaborationQuery()
        q.set_main_org(mainorg)
        
        # start date
        if start != "" and start is not None:
            q.set_start(start)
        
        # we make the initial request very large - much larger than it ought
        # ever need to be, just because there isn't an ES size which means "everything"
        size = 10000
        q.set_size(size)
        
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
        # This is a catch just in case the massive size above isn't enough.  If we
        # wind up hitting this, the reality is that we need to change the way we
        # do this query, as this would be quite inefficient
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
        
        if order == "projects":
            return sorted(facet, key=lambda f: f["count"], reverse=True)[1:]
        elif order == "funding":
            return sorted(facet, key=lambda f: f["total"], reverse=True)[1:]
        
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
    
    def funders(self, mainorg, start=None):
        q = FundersQuery(mainorg, start)
        result = self.query(q=q.query())
        
        # get the terms stats facet
        terms = result.get("facets", {}).get("funders", {}).get("terms", [])
        
        # format the money and return
        for t in terms:
            t['formatted_total'] = "{:,.0f}".format(t['total'])
        
        return terms
    
    def collaboration_report(self, mainorg, collaboration_definition, 
                                funder=None, collab_orgs=[], start=None, end=None, 
                                lower=None, upper=None, category=None, status=None):
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
    
    #######################################################################
    
    #######################################################################
    # methods for the benchmarking report
    #######################################################################
    
    def benchmark(self, mainorg=None, type=None, granularity="monthly", 
                        start=None, end=None, funder=None, grantcategory=None, 
                        leadonly=False, compare_org=None, compare_groups=None):
        
        # there are three different kinds of report, and we require
        # two different queries to service them
        if type == "publications":
            return self._publicationsReport(mainorg=mainorg, granularity=granularity, 
                            start=start, end=end, funder=funder, grantcategory=grantcategory, 
                            leadonly=leadonly, compare_org=compare_org, compare_groups=compare_groups)
        elif type in ["award_value", "num_projects"]:
            return self._valueCountReport(mainorg=mainorg, granularity=granularity, 
                            start=start, end=end, funder=funder, grantcategory=grantcategory, 
                            leadonly=leadonly, compare_org=compare_org, compare_groups=compare_groups)
        
        return None
    
    def benchmark_details(self, mainorg=None, type=None, granularity="monthly", 
                        start=None, end=None, funder=None, grantcategory=None, 
                        leadonly=False, compare_org=None, compare_groups=None):
        
        # sanitise some of the input
        compare_org = [] if compare_org is None else compare_org
        compare_groups = {} if compare_groups is None else compare_groups
        
        # set up the objects we are going to work with
        benchmark = {}
        common_query = BenchmarkingQuery("results_only")
        
        self._add_benchmark_constraints(common_query, project_start=start, 
                                        project_end=end, funder=funder, 
                                        grantcategory=grantcategory)
        
        # for each of the additional orgs, do the same query with the different org
        for org in compare_org:
            report = self._details_benchmark_org(common_query, org, leadonly)
            benchmark[org] = report
            
        # for each of the groups of people do the group query
        for gname, people in compare_groups.iteritems():
            report = self._details_benchmark_group(common_query, people)
            benchmark[gname] = report
        
        return benchmark
    
    def _publicationsReport(self, mainorg=None, granularity="monthly", 
                        start=None, end=None, funder=None, grantcategory=None, 
                        leadonly=False, compare_org=None, compare_groups=None):
        
        # sanitise some of the input
        compare_org = [] if compare_org is None else compare_org
        compare_groups = {} if compare_groups is None else compare_groups
        
        # set up the main objects we need to work with here
        benchmark = {}
        common_query = BenchmarkingQuery("publications")
        
        self._add_benchmark_constraints(common_query, publication_start=start, 
                                        publication_end=end, funder=funder, 
                                        grantcategory=grantcategory, granularity=granularity)
        
        # calculate integer timestamps for the start and end of the histogram, which we will
        # ask the reports to constrain themselves to
        lower_time = self._date_to_time(start)
        upper_time = self._date_to_time(end)
        
        # first we get the data for each of the individual organisations being benchmarked
        for org in compare_org:
            report = self._histogram_benchmark_org(common_query, org, leadonly)
            report = self._trim_histogram(report, lower_time, upper_time)
            benchmark[org] = report
        
        # then for each of the groups of people 
        for gname, people in compare_groups.iteritems():
            report = self._histogram_benchmark_group(common_query, people)
            report = self._trim_histogram(report, lower_time, upper_time)
            benchmark[gname] = report
        
        return benchmark
    
    def _valueCountReport(self, mainorg, granularity="monthly", 
                        start=None, end=None, funder=None, grantcategory=None, 
                        leadonly=False, compare_org=None, compare_groups=None):
        
        # sanitise some of the input
        compare_org = [] if compare_org is None else compare_org
        compare_groups = {} if compare_groups is None else compare_groups
        
        # set up the main objects we need to work with here
        benchmark = {}
        common_query = BenchmarkingQuery("value_count")
        
        self._add_benchmark_constraints(common_query, project_start=start, 
                                        project_end=end, funder=funder, 
                                        grantcategory=grantcategory, granularity=granularity)
        
        # for each of the additional orgs, do the same query with the different org
        for org in compare_org:
            report = self._histogram_benchmark_org(common_query, org, leadonly)
            benchmark[org] = report
            
        # for each of the groups of people do the group query
        for gname, people in compare_groups.iteritems():
            report = self._histogram_benchmark_group(common_query, people)
            benchmark[gname] = report
            
        return benchmark
    
    def _date_to_time(self, date):
        return -1 if date == "" or date is None else int(time.mktime(time.strptime(date, "%Y-%m-%d"))) * 1000
    
    def _details_benchmark_group(self, base_query, people):
        result = self._do_group_query(base_query, people)
        entries = [hit.get("_source", {}) for hit in result.get("hits", {}).get("hits", [])]
        return entries

    def _details_benchmark_org(self, base_query, org, leadonly):
        result = self._do_org_query(base_query, org, leadonly)
        entries = [hit.get("_source", {}) for hit in result.get("hits", {}).get("hits", [])]
        return entries

    def _histogram_benchmark_group(self, base_query, people):
        result = self._do_group_query(base_query, people)
        entries = result.get("facets", {}).get("histogram", {}).get("entries")
        return entries

    def _histogram_benchmark_org(self, base_query, org, leadonly):
        result = self._do_org_query(base_query, org, leadonly)
        entries = result.get("facets", {}).get("histogram", {}).get("entries")
        return entries
    
    def _do_group_query(self, base_query, people):
        q = deepcopy(base_query)
        q.set_people(people)
        result = self.query(q=q.query)
        return result
    
    def _do_org_query(self, base_query, org, leadonly):
        q = deepcopy(base_query)
        if leadonly:
            q.lead_only(org)
        else:
            q.any_collaborator(org)
        result = self.query(q=q.query)
        return result
    
    def _trim_histogram(self, entries, lower_time, upper_time):
        if lower_time > -1 or upper_time > -1:
            valid_entries = []
            for entry in entries:
                # print entry["time"]
                if entry["time"] >= lower_time and (upper_time == -1 or entry["time"] <= upper_time):
                    # print "valid"
                    valid_entries.append(entry)
            return valid_entries
        else:
            return entries
    
    def _add_benchmark_constraints(self, query, project_start=None, project_end=None, 
                                publication_start=None, publication_end=None, funder=None, 
                                grantcategory=None, granularity=None):
        """
        Add the standard set of query constraints, which apply to all queries to the benchmarking
        report
        """
        # project start date
        if project_start != "" and project_start is not None:
            query.set_project_start(project_start)
            
        # project end date 
        if project_end != "" and project_end is not None:
            query.set_project_end(project_end)
        
        # funder 
        if funder != "" and funder is not None:
            query.set_funder(funder)
        
        # grant category
        if grantcategory != "" and grantcategory is not None:
            query.set_grantcategory(grantcategory)
        
        # publication start date
        if publication_start != "" and publication_start is not None:
            query.set_publication_start(publication_start)
            
        # publication end date 
        if publication_end != "" and publication_end is not None:
            query.set_publication_end(publication_end)
        
        # granularity
        if granularity != "" and granularity is not None:
            query.set_granularity(granularity)
    
        
    #######################################################################

##############################################################################
# Benchmarking Report objects
##############################################################################
# These classes provide support for abstract representations of the
# benchmarking report and the queries needed by it
##############################################################################

class BenchmarkingQuery(object):
    
    publication_end_template = {"range" : {"project.publication.date" : {"to" : "<end of range>"}}}
    publication_start_template = {"range" : {"project.publication.date" : {"from" : "<start of range>"}}}
    project_start_template = { "range" : {"project.fund.start" : {"from" : "<start of range>"}}}
    project_end_template = {"range" : {"project.fund.start" : {"to" : "<end of range>"}}}
    funder_template = { "term" : {"primaryFunder.name.exact" : None} }
    grantcategory_template = {"term" : {"project.grantCategory.exact" : None}}
    leadro_template = {"term" : {"leadRo.name.exact" : None}}
    org_template = { "term" : {"collaboratorOrganisation.canonical.exact" : None} }
    group_template = {"terms" : {"collaboratorPerson.canonical.exact" : []}}
    
    publications_query_template = {
        "query" : {
            "bool" : {
            	"must" : []
            }
        },
        "size" : 0,
        "facets" : {
            "histogram" : {
                "date_histogram" : {
                    "field" : "project.publication.date",
                    "interval" : "quarter"
                }
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
            "histogram" : {
                "date_histogram" : {
                    "key_field" : "project.fund.start",
                    "value_field" : "project.fund.valuePounds",
                    "interval" : "quarter"
                }
            }
        }
    }
    
    results_only_query_template = {
        "query" : {
            "bool" : {
            	"must" : []
            }
        },
        "size" : 10000 # a suitably large number
    }

    def __init__(self, type):
        # the copy of the base query that we'll be working with
        if type == "publications":
            self.query = deepcopy(self.publications_query_template)
        elif type == "value_count":
            self.query = deepcopy(self.valuecount_query_template)
        elif type == "results_only":
            self.query = deepcopy(self.results_only_query_template)
    
    def set_project_start(self, start):
        qs = deepcopy(self.project_start_template)
        qs['range']['project.fund.start']['from'] = start
        self.query['query']['bool']['must'].append(qs)
    
    def set_project_end(self, end):
        qs = deepcopy(self.project_end_template)
        qs['range']['project.fund.start']['to'] = end
        self.query['query']['bool']['must'].append(qs)
    
    def set_publication_start(self, start):
        qs = deepcopy(self.publication_start_template)
        qs['range']['project.publication.date']['from'] = start
        self.query['query']['bool']['must'].append(qs)
    
    def set_publication_end(self, end):
        qs = deepcopy(self.publication_end_template)
        qs['range']['project.publication.date']['to'] = end
        self.query['query']['bool']['must'].append(qs)
    
    def set_granularity(self, granularity):
        if granularity in ["month", "quarter", "year"]:
            self.query['facets']['histogram']['date_histogram']['interval'] = granularity
    
    def set_funder(self, funder):
        qf = deepcopy(self.funder_template)
        qf['term']['primaryFunder.name.exact'] = funder
        self.query['query']['bool']['must'].append(qf)
    
    def set_grantcategory(self, grantcategory):
        qf = deepcopy(self.grantcategory_template)
        qf['term']['project.grantCategory.exact'] = grantcategory
        self.query['query']['bool']['must'].append(qf)
    
    def lead_only(self, org):
        qo = deepcopy(self.leadro_template)
        qo['term']["leadRo.name.exact"] = org
        self.query['query']['bool']['must'].append(qo)
    
    def any_collaborator(self, org):
        qo = deepcopy(self.org_template)
        qo['term']["collaboratorOrganisation.canonical.exact"] = org
        self.query['query']['bool']['must'].append(qo)
    
    def set_people(self, people):
        qp = deepcopy(self.group_template)
        for person in people:
            qp["terms"]["collaboratorPerson.canonical.exact"].append(person)
        self.query["query"]["bool"]["must"].append(qp)


##############################################################################
# Collaboration Report objects
##############################################################################
# These classes provide support for abstract representations of the
# collaboration report and for the queries needed by that report
##############################################################################

class CollaborationReport(object):
    """
    An object which wraps an ES result object for the list of projects
    returned by a collaboration report request
    """
    
    # map of collaboration definitions from outside to names of fields in the index
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


class CollaborationQuery(object):
    """
    This class provides an interface to the complex ES query that is required
    in order to query for collaborators.  Callers who wish to do stuff with
    collaborations should use this object only in order to make their requests.
    """
    
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

##############################################################################
# Small Query Managers
##############################################################################
# Objects which represent different kinds of queries that need to be done
# against the dataset
##############################################################################

class InfoQuery(object):
    """
    Query manager that handles general information about the content of the
    index
    """
    
    funders_facet = {"terms": {"field" : "primaryFunder.name.exact", "all_terms" : True}}
    grant_categories = {"terms" : {"field" : "project.grantCategory.exact", "all_terms" : True}}
    
    base_query = {
        "query" : {
            "match_all" : {}
        }
    }
    
    def __init__(self):
        self.query = deepcopy(self.base_query)

    def add_all_funders(self):
        if "facets" not in self.query:
            self.query["facets"] = {}
        self.query["facets"]["funders"] = deepcopy(self.funders_facet)
    
    def add_grant_categories(self):
        if "facets" not in self.query:
            self.query["facets"] = {}
        self.query["facets"]["categories"] = deepcopy(self.grant_categories)

class FundersQuery(object):

    base_query = {
        "query" : {
            "bool" : {
                "must" : []
            }
        },
        "size" : 0,
        "facets" : {
            "funders" : {
                "terms_stats" : {
                    "key_field" : "primaryFunder.name.exact",
                    "value_field" : "project.fund.valuePounds",
                    "size" : 0
                }
            }
        }
    }
    
    org_template = { "term" : {"collaboratorOrganisation.canonical.exact" : None} }
    start_template = { "range" : { "project.fund.end" : { "from" : "<start of range>" } } }

    def __init__(self, mainorg, start):
        self.mainorg = mainorg
        self.start = start
    
    def query(self):
        q = deepcopy(self.base_query)
        
        qo = deepcopy(self.org_template)
        qo['term']["collaboratorOrganisation.canonical.exact"] = self.mainorg
        q['query']['bool']['must'].append(qo)
        
        if self.start is not None:
            qs = deepcopy(self.start_template)
            qs['range']['project.fund.end']['from'] = self.start
            q['query']['bool']['must'].append(qs)
        
        return q

#############################################################################
# Accounts/User objects
#############################################################################
# These objects help us manage users of the system
#############################################################################


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

            
            

