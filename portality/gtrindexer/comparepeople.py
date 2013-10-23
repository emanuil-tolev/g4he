from __future__ import print_function
from portality import models
import sys

q = {
    "query" : {
        "match_all" : {}
    }
}

triples = {
    "query" : {
        "bool" : {
            "must" : [
                { "term" : {"project.exact" : "<project>" } }
            ]
        }
    }
}

g = models.Record.iterate(q)

print("Initialising...", end='\r')
sys.stdout.flush()

COUNTER = 0
broken = []
for project in g:
    COUNTER += 1
    pid = project.get("project", {}).get("id")
    
    pis = project.get("principalInvestigator", [])
    cis = project.get("coInvestigator", [])
    people = {}
    for pi in pis:
        personid = pi.get("person", {}).get("id")
        orgid = pi.get("organisation", {}).get("id")
        people[personid] = orgid
    for ci in cis:
        personid = ci.get("person", {}).get("id")
        orgid = ci.get("organisation", {}).get("id")
        people[personid] = orgid
    
    triples["query"]["bool"]["must"][0]["term"]["project.exact"] = pid
    res = models.PersonHistory.query(q=triples)
    trips = [r.get("_source") for r in res.get("hits", {}).get("hits", [])]
    
    print(str(COUNTER) + ":" + pid + " - " + str(len(trips)) + " triples, " + str(len(people.keys())) + " people", end='\r')
    sys.stdout.flush()
    
    for t in trips:
        pers = t.get("person")
        org = t.get("org")
        
        if people.get(pers) != org:
            print("pid:" + str(pid) + ": person:" + str(pers) + " associated with org:" + str(people.get(pers)) + "; should be org:" + str(org)) 
            sys.stdout.flush()
            broken.append((t.get("person"), t.get("project"), t.get("org")))

print(broken)
print(str(len(broken)), "assciations")

        
        
        
