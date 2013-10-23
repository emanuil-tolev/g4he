import csv
from portality import models

grants = '/home/richard/Dropbox/Documents/G4HE/affiliations/grants-g4he.csv'
intramural = '/home/richard/Dropbox/Documents/G4HE/affiliations/intramural-g4he.csv'

BULK = 1000

quads = []
with open(grants) as gf:
    gr = csv.reader(gf)
    first = True
    for row in gr:
        if first:
            first = False
            continue
        quads.append({"person" : row[3].strip(), "project" : row[4].strip(), "org" : row[5].strip(), "when" : row[8].strip(), "id" : models.PersonHistory.makeid()})

with open(intramural) as intf:
    intr = csv.reader(intf)
    first = True
    for row in intr:
        if first:
            first = False
            continue
        quads.append({"person" : row[3].strip(), "project" : row[4].strip(), "org" : row[5].strip(), "when" : row[6].strip(), "id" : models.PersonHistory.makeid()})

print "loaded", len(quads), "records"

for i in range(0, len(quads), BULK):
    print "bulk", i, i+BULK
    block = quads[i:i+BULK]
    models.PersonHistory.bulk(block)
    
