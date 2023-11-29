NeuroJSON Client (`neuroj`)
============================

Utilities to convert datasets to JSON and access RESTful data on NeuroJSON.io

-   Maintainer: Qianqian Fang (q.fang at neu.edu)
-   License: BSD 3-Clause License
-   Version: 0.5
-   Website: <https://neurojson.org>


Table of content
 * [Terminology](#terminology)
 * [Introduction](#introduction)
 * [Data conversion strategies and recommendations](#data-conversion-strategies-and-recommendations)
 * [Utility overview](#utility-overview)
 * [neuroj](#neuroj)
    * [dataset conversion (local only)](#dataset-conversion-local-only)
    * [list and query NeuroJSON.io (requires Internet)](#list-and-query-neurojsonio-requires-internet)
    * [retrieve/upload NeuroJSON.io (except -g, other functions requires -U/-P or NEUROJSON_IO environment variable)](#retrieveupload-neurojsonio-except--g-other-functions-requires--u-p-or-neurojson_io-environment-variable)
    * [admin authentication (-p/-c/-d requires admin account)](#admin-authentication--p-c-d-requires-admin-account)
    * [Note for admins:](#note-for-admins)
    * [Examples:](#examples)
 * [njprep](#njprep)
    * [how to use njprep](#how-to-use-njprep)
 * [Dependencies](#dependencies)


Terminology
--------------

- **"database"**: a collection of datasets, such as OpenNeuro, Dandi, BrainLife etc
- **"dataset"** : a group of data files that are acquired for a specific study/purpose, may have multiple subjects folders
- **"subject folder"** : a folder storing data obtained from a study subject (human or animal)
- **"data file"**: a single data file that is part of a dataset
- **"BIDS dataset"**: a dataset that is organized following the BIDS standard <https://bids.neuroimaging.io/>


Introduction
--------------

The NeuroJSON project (https://neurojson.org), funded by the US National Institute of Health (NIH),
is aimed at promoting and curating scalable, searchable, and reusable neuroimaging datasets among
the communities. The NeuroJSON project adopts [JSON](https://www.json.org/json-en.html) and
[binary JSON](https://json.nlohmann.me/features/binary_formats/) formats as the primary underlying
data formats to reinforce searchbility and scalability. JSON is an
[internationally standardized](https://www.iso.org/standard/71616.html) format that is 
universally supported across wide range of programming environments. JSON has a
vast toolchain ecosystem that can be readily applied for processing neuroimaging data once
converted. Specifically, modern document-store and NoSQL databases, such as
[Radis](https://redis.io/), [CouchDB](https://couchdb.apache.org/), [MongoDB](https://www.mongodb.com/),
or [JSON type support in MySQL](https://dev.mysql.com/doc/refman/8.0/en/json.html) or
[Sqlite](https://www.sqlite.org/json1.html), provides rapid and extensive search capability
of large datasets that can easily handle millions of datasets at scale.

This toolbox provides a set of lightweight, easy-to-use shell-based utilities to convert
neuroimaging datasets from native modality-specific data formats to JSON, and subsequently
allow users to upload their JSON-encoded data to NeuroJSON.io, our primary document-store
database built upon an open-source CouchDB server, for sharing and data publication.
The utilities also provide convenient functions to query all free/public datasets provided
on NeuroJSON.io, search specific datasets and data records for reusing those in secondary
data analysis or testing. The CouchDB server exposes all provided dataset information using
intuitive [RESTful APIs](https://docs.couchdb.org/en/stable/api/index.html) for neuroimaging
end-users and tool developers to query, combine and download JSON-encoded data that are
relevant to their project.

The migration from zip-file based neuroimaging data sharing to modern NoSQL database
based data dissemination not only greatly enhances the scalability of neuroimaging datasets,
but also make datasets findable, searchable, and easy to integrate with diverse
data analysis tools. This also prepares the community towards building complex data
analysis pipelines that requires interoperable data-exchange between complex software
tools running on the cloud or web-based applications.


Data conversion strategies and recommendations
---------------

We map neuroimaging datasets and dataset collections to CouchDB/NoSQL database
object hierarchies. The below table shows the conceptual mapping of the data logical
structures to the CouchDB object hierarchies.


|  Data logical structure               |  CouchDB object             |  Examples                      |
|---------------------------------------|-----------------------------|--------------------------------|
| a dataset collection                  | a CouchDB database          | openneuro, dandi, openfnirs,...|
| a dataset                             | a CouchDB document          | ds000001, ds000002, ...        |
| files and folders related to a subject| JSON keys inside a document | sub-01, sub-1/anat/scan.tsv,...|
| human-readable binary content (small) | an attachment to a document | .png, .jpg, .pdf, ...          |
| non-searchable binary content (large) | `_DataLink_` JSON key       | `"_DataLink_":"http://url/to/ds/filehash.jbd"` |


A CouchDB (similarly other NoSQL database engines) can hold and process enormous numbers of
databases (i.e. collections) and documents (i.e. datasets) in each database, however, for
high-performance search capabilities, our CouchDB server follows the best practice recommendations
and set the maximum document size to 8 MB. That means the searchable JSON-encoded content of
a dataset should be limited to ~10-15MB if stored in raw JSON text files (after parsing, the
data will be reduced). In practices, the searchable content in most existing datasets can
fit in this limit (for example, over 90% of OpenNeuro datasets have less than 10 MB raw
JSON size after conversion). After capping the sizes of large .tsv files, nearly all OpenNeuro
datasets can be stored in a CouchDB document.

It is highly recommended to only encode human-readable and searchable data in the JSON
encoded datasets and offload the non-searchable binary data in externally linked files.
This way, the JSON document can be small and easy to query, download and manipulate.
CouchDB can perform complex searches of a database containing millions of small documents (kB)
in a fraction of a second (MongoDB can be even faster; Radis DB offers the fastest speed
if the entire database can be fit in the memory of the server).


Utility overview
--------------

Primary tools:

- **`neuroj`**: NeuroJSON client - the primary utility that calls other tools to convert and query NeuroJSON.io
- **`njprep`**: a bash script to convert databases, single dataset or single data file


Helper functions (called by `neuroj` and `njprep`)

- `bids2json`: a utility to merge converted dataset JSON files to a single `datasetname.json` file for upload
- `link2json`: a utility to create a JSON file for symbolic links
- `listdatalink`: a utility to list/extract all URL/externally linked data files (`_DataLink_`) for batch download
- `mergejson`: a bash/jq script to merge all converted files under a subject-folder to a single `subject.jbids` file
- `tsv2json`: a Perl script to convert tsv/csv to JSON


`neuroj` and `njprep` data conversion overview
---------------

In the below diagram, we show the data conversion input/output folder structrues.

```
[input folder]                                  [output folder]
/orig/data/collection/root           =>         /coverted/json/root
  |                                                |----------------------------- **database1.json** -> push to NeuroJSON.io CouchDB
  |-- dataset1/                                    |-- dataset1/                                ^
  |   |-- dataset_description.json   => (copy)     |   |-- dataset_description.json             | merge by `bids2json`
  |   |-- README                     => (convert)  |   |-- README.jbids                         |
  |   |                                            |   |---------------------- **subj-01.jbids**
  |   |-- sub-01/                                  |   |-- sub-01/                       \  ^
  |   |   |-- sub-01_scans.tsv       => (convert)  |   |   |-- sub-01_scans.tsv.json     |  |
  |   |   |-- anat/                                |   |      |-- anat/                  |--| merge by `mergejson`
  |   |      |-- sub-01_T1w.nii.gz   => (convert)  |   |      |-- sub-01_T1w.nii.gz.json |
  |   |      |-- sub-01_events.tsv                 |   |         |-- sub-01_events.tsv.json
  |   |      |-- sub-01-file <symlink> -> git/annex/...|         |-- sub-01-file.json: ["_DataLink_":"symlink:git/annex/..."]
  |   |                                            |   |---------------------- **subj-02.jbids**
  |   |-- sub-02/                                  |   |-- sub-02/
  |   |   |-- ...                    =>            |   |   |-- ...
  |                                                |----------------------------- **database2.json** -> push to NeuroJSON.io CouchDB
  |-- dataset2/                                    |-- dataset2/
  |   |-- ...                        =>            |   |-- ...
  |...                                             |...
                                                   |.att/  # attachment data files      -> upload to your preferred or NeuroJSON server
                                                       |-- dataset1/
                                                       |   |-- md5_pathhash_file1-zlib.jdb 
                                                       |   |-- md5_pathhash_file2-zlib.jdb
                                                       |   |-- ...
                                                       |-- dataset2/
                                                       |   |-- md5_pathhash_file1-zlib.jdb 
                                                       |   |-- md5_pathhash_file2-zlib.jdb
                                                       |   |-- ...
                                                       ...
```

`neuroj`
--------------

`neuroj` is the NeuroJSON client script that provides most of the functionalities. It calls `njprep` to
perform batched and parallel dataset/datafile conversion to JSON, as well as listing, searching, downloading,
databases and datasets from NeuroJSON.io, our open data dissemination portal. NeuroJSON.io
shares open datasets publically and permits anonymous access.

For neuroimaging dataset creators, uploaders and collection administrators, you can also use `neuroj`
to perform administrative tasks such as uploading new JSON-encoded datasets to an existing database, updating
dataset JSON document with new revision, deleting old versions and other maintenance commands supported
by the CouchDB REST API.


Command format: `neuroj -flag1 <param1> -flag2 <param2> ...`

Suported flags include

### dataset conversion (local only)
```
-i/--input folderpath   path to the top folder of a data collection (such as OpenNeuro)
-o/--output folderpath  path to the output folder storing the converted JSON files
-db/--database dbname   database name (such as openneuro, openfnirs, dandi etc)
-ds/--dataset dataset   dataset name (a single dataset in a collection, such as ds000001)
-v/--rev revision       dataset revision key hash
-r/--convert            convert database (-db) or dataset (-db .. -ds ..) (in parallel) to JSON
-t/--threads num        set the thread number for parallel conversion (4 by default)
```
### list and query NeuroJSON.io (requires Internet)
```
-l/--list               list all database if -db is given; or the dataset if both -db/-ds are given
-q/--info               query database info if -db is given; or dataset info if both -db/-ds are given
-f/--find '{" selector ":,...}' use the CouchDB _find API to search dataset
```

### retrieve/upload NeuroJSON.io (except -g, other functions requires -U/-P or NEUROJSON_IO environment variable)
```
-g/--get/--pull         retrieve and display JSON encoded dataset, or complete database (slow)
-p/--put/--push dataset.json  upload JSON data to a database (-db) and dataset (if -ds is missing, use file name), (admin only)
-c/--create             create a specified database (-db), (admin only)
-d/--delete             delete specified database (-ds) from a database (-db), (admin only)
-u/--url https://...    CouchDB REST API root url, use https://neurojson.io:7777 (default) or use NEUROJSON_IO env variable
```
### admin authentication (-p/-c/-d requires admin account)
```
-n                      read from \$HOME/.netrc (Linux/MacOS) or \%HOME\%/_netrc for username/password for admin tasks
--netrc-file /path/netrcfile  same as -n, specify netrc file path (see https://everything.curl.dev/usingcurl/netrc)
-U/--user username      set username for admin tasks (unless use -n or -c or NEUROJSON_IO URL has user info)
-P/--pass password      set password for admin tasks (unless use -n or -c or NEUROJSON_IO URL has password info)
```

### Note for admins:
neuroj accepts 3 ways to set username/password if you are running admin tasks (create/upload/update/delete datasets).
Using curl with -n/--netrc-file is the recommended approach as it does not leave passwords in the commands or system logs.

If one can not install curl, neuroj attempts to use Perl module LWP::UserAgent to communicate with the server.
In this case, user may set an environment variable NEUROJSON_IO in the form of https://user:pass\@example.com:port.
If user/pass contains special characters, they must be URL-encoded. This way, the neuroj command will not show
any password in the log. If you are on a secure computer, using -U/-P will also allow LWP::UserAgent to authenticate.

### Examples:

```shell
# print help information and flags
neuroj

# preview commands (dry-run, does not execute) to convert a database (including all included datasets) to JSON
neuroj -i /path/to/database/rootfolder -o /path/to/output/json/folder -db openneuro

# convert a database (a collection of datasets) to JSON in batch with 12 parallel threads (1 thread per dataset)
neuroj -i /path/to/database/rootfolder -o /path/to/output/json/folder -db openneuro --convert -t 12

# convert a single dataset (including all files under sub-folders) to JSON in parallel (1 thread per file)
neuroj -i /path/to/database/rootfolder -o /path/to/output/json/folder -db openneuro -ds ds000001 --convert

# convert a database to JSON, assuming the last segment of the input path as database name
neuroj -i /path/to/database/databasename -o /path/to/output/json/folder

# convert a single dataset ds000001 to JSON (dry-run only, add --convert to run)
neuroj -i /path/to/database/databasename -o /path/to/output/json/folder -ds ds000001

# list all databases currently hosted on NeuroJSON.io
neuroj --list

# list all databases currently hosted on NeuroJSON.io, format the output with jq
neuroj --list | jq '.'

# list all datasets stored under the 'openneuro' database
neuroj --list -db openneuro

# list all datasets strored under the 'openneuro' database and print all datasets using jq filters
neuroj --list -db openneuro | jq '.rows[] | .id'

# query server-level information of the database openneuro (return dataset count, file sizes etc)
neuroj --info -db openneuro

# search the IDs of the first 10 (limit:10) datasets in the openneuro database starting from the 3rd (skip:2) datasets
neuroj -db openneuro --find '{"selector":{},"fields":["_id"],"limit":10,"skip":2}'

# query the dataset name "_id" and "dataset_description.json" records of the first two datasets in "openneuro" and format with jq
neuroj -db openneuro --find '{"selector":{},"fields":["_id","bids_dataset_info.dataset_description\\\\.json"],"limit":2}' | jq '.'
```


`njprep`
--------------

`njprep` is a **neuroimaging-data file to JSON converter** following the general
principles of the NeuroJSON project - that is to separate a dataset
into human-readable/searchable part and a non-searchable/binary data part.

The human-readable part is stored in the JSON format and can be readily uploaded
to modern document-store databases to allow data analyses to scale to large
datasets, making the data **searchable, findable and universally accessible and
parsable**. The human-readability of the data format also ensures future **reusability**.

The non-searchable data are stored in binary JSON, or their original formats and
can be stored externally while still being associated with the searchable
JSON data using links, URLs or stored as "attachments" to the JSON document.
They can be "re-united" with the searchable data on-demand to restore the
full dataset for data analysis.

For conversion of human-readable data files, `njprep` currently supports
`.json`, `.tsv`, `.csv`, and various text files (`.txt/.md/.rst`); for a limit set
of neuroimaging data files, such as `.nii.gz`, `.snirf`, `njprep` parse the file
header into JSON while storing the rest into binary files. `njprep` also converts
symbolic links to a special JSON element to maintain the linkage. Other human-readable
documentation files, such as `.png`, `.jpg`, `.pdf` are stored as attachments

### how to use `njprep`
```shell
# convert all datasets in a database to JSON
njprep /database/root/ /output/json/root/ database_name

# convert a specific dataset "dataset_name" in a specific database to JSON
njprep /database/root/ /output/json/root/ database_name dataset_name

# convert a single file or subject-folder in a given 
njprep /database/root/ /output/json/root/ database_name dataset_name /path/to/a/file
```

Dependencies
--------------

For Linux and Mac OS:
- jq
- curl
- GNU Octave
- jbids https://github.com/NeuroJSON/jbids - including 4 submodules under tools)
- libparallel-forkmanager-perl (for Parallel::ForkManager)
- libwww-perl (for LWP::UserAgent)
- libjson-xs-perl (for JSON::XS)

For Windows: please first install cygwin64 (http://cygwin.com/) or MSYS2 (http://msys2.org/)
and also install the above packages in the corresponding cygwin64/msys2 installers.

When converting datasets with `neuroj` or `njprep`, conversion for some of the data files,
such as `.snirf` or `.nii/.nii.gz` requires octave and the jbids toolbox (including its submodules).
Other functionalities does not require octave.
