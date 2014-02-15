# Key runnable files

* index_gtr - clone the entire GtR database via the GtR-1.0 API
* personhistory - load from the csvs provided by GtR the historical person/project/org affiliations
* index_g4he - take the raw indexed gtr data and munge it into the Record format required by the g4he application

# Process

1. Run index_gtr; this will clone all of the data in the GtR service into a local copy of the index

2. Run personhisotry; this will load the historical person/project/org affiliations into our local index

3. Run index_g4he; this will take the local indexes and build the g4he reporting index

# Files you can ignore

* comparepeople - this was an initial experiment to ascertain the impact on the index of incorporating the historical person data
* index_projects - the original attempt to build the g4he index directly from GtR.  It has been superseded by index_gtr
