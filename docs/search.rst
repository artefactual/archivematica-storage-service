:Authors:
    Mike Cantelon

Search API
================================================================================

In addition to the search functionality present in the web interface, the
storage service also includes a REST search API. Searches are performed by
sending an HTTP GET request.

Search results will include a count of how many items were found and will
include next and previous properties indicating links to more items in the
result set.

Location search
--------------------------------------------------------------------------------

The endpoint for searching locations is::

    http://<storage service URL>/api/v2/search/location/

Locations can be searched using the following search parameters:

* uuid (location UUID)
* space (space UUID)
* purpose (purpose code)
* enabled (whether the location is enabled)

For example, if you wanted to get details about the transfer source location
contained in the space 6d0b6cce-4372-4ef8-bf48-ce642761fd41 you could HTTP get::

    http://<storage service URL>/api/v2/search/location/?space=7ec3d5d9-23ec-4fd5-b9fb-df82da8de630&purpose=TS

Here is an example JSON response::

    {
      "count": 1,
      "next": null,
      "previous": null,
      "results": [
        {
          "uuid": "f74c23e1-6737-4c24-a470-a003bc573051",
          "space": "7ec3d5d9-23ec-4fd5-b9fb-df82da8de630",
          "pipelines": [
            "2a351be8-99b4-4f53-8ea5-8d6ace6e0243",
            "b9d676ff-7c9d-4777-9a19-1b4b76a6542f"
           ],
           "purpose": "TS",
           "quota": null,
           "used": 0,
           "enabled": true
        }
      ]
    }


Package search
--------------------------------------------------------------------------------

The endpoint for searching packages is::

    http://<storage service URL>/api/v2/search/package/

Packages can be searched using the following search parameters:

* uuid (package UUID)
* pipeline (pipeline UUID)
* location (location UUID)
* package_type (package type code: "AIP", "AIC", "SIP", "DIP", "transfer", "file", "deposit")
* status (package status code: "PENDING", "STAGING", "UPLOADED", "VERIFIED",
  "DEL_REQ", "DELETED", "RECOVER_REQ", "FAIL",  or "FINALIZE")
* min_size (minimum package filesize)
* max_size (maximum package filesize)

For example, if you wanted to get details about packages contained in the location
7c9ddb60-3d16-4fa3-a41e-4a1a876d2a89 you could HTTP GET::

    http://<storage service URL>/api/v2/search/package/?package_type=AIP

Here is an example JSON response::

    {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          uuid: "96365d3d-6656-4fdd-a247-f85c9e0ddd43",
          current_path: "9636/5d3d/6656/4fdd/a247/f85c/9e0d/dd43/Apples-96365d3d-6656-4fdd-a247-f85c9e0ddd43.7z",
          size: 7918099,
          origin_pipeline: "b9d676ff-7c9d-4777-9a19-1b4b76a6542f",
          current_location: "a3d95a1b-f8fb-4e34-9f15-60dcdf178470",
          package_type: "AIP",
          status: "UPLOADED",
          pointer_file_location: "c2dfb32b-77dd-4597-abff-7c52e05e6d01",
          pointer_file_path: "9636/5d3d/6656/4fdd/a247/f85c/9e0d/dd43/pointer.96365d3d-6656-4fdd-a247-f85c9e0ddd43.xml"
        }
      ]
    }


File search
--------------------------------------------------------------------------------

The endpoint for searching files is::

    http://<storage service URL>/api/v2/search/file/

Files can be searched using the following search criteria:

* uuid (file UUID)
* package (package UUID)
* name (full or partial filename)
* pronom_id (PRONOM PUID)
* format_name (format name)
* min_size (minimum filesize)
* max_size (maximum filesize)
* normalized (boolean: whether or not file was normalized)
* valid (nullable boolean: whether or not file was validated and, if so, its
  validity)
* file_type (one of 'AIP' or 'Transfer')
* pipeline (UUID of Archivematica pipeline the file came from)
* ingestion_time (date of ingestion)
* ingestion_time_at_or_before (latest possible ingestion date)
* ingestion_time_at_or_after (earliest possible ingestion date)

For example, if you wanted to get details about files that are 29965171 bytes
or larger, you could HTTP GET::

    http://<storage service URL>/api/v2/search/file/?min_size=29965171

Here is an example JSON response::

    {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          uuid: "bd2074bb-2086-40b5-9c3f-3657cb900681",
          name: "Bodring-5f0fa831-a74b-4bf5-8598-779d49c3663a/objects/pictures/Landing_zone-e50c8452-0791-4fac-9f45-15b088a39b10.tif",
          file_type: "AIP",
          size: 29965171,
          format_name: "TIFF",
          pronom_id: "",
          source_package: "",
          normalized: null,
          validated: null,
          ingestion_time: "2015-10-30T04:16:39Z"
        }
      ]
    }
