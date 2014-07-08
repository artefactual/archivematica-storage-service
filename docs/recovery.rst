:Authors:
    Mike Cantelon

AIP Recovery
============

AIP recovery support allows a storage service administrator to replace a
corrupt version of a stored AIP with a correct version (restored from a backup,
for example).

The AIP recovery process involves copying a recovered version of an AIP
into a dedicated recovery directory accessible by the storage service. You can
determine the location of this directory by clicking "Locations" in the storage
service administration web interface then finding the path assocated with AIP
recovery.

Once the recovered version is in place, recovery can be requested via the
storage service's REST interface.

The recovery request must then be approved by an administrator. To get to the
recovery request administration page, click "Packages" then "View recovery
requests" in the storage service administration web interface. Enter a reason
for approval then click "Approve" to start recovery.


How Recovery Works
------------------

One an AIP recovery has been approved, the storage service does the following:

#. Checks the fixity data of the recovered AIP files, failing recovery if the
   fixity check fails
#. Copies the corrupt AIP file to a backup directory within the recovery
   location
#. Copies the recovered AIP files to AIP storage
#. Checks the fixity data of the stored AIP, failing recovery if the fixity
   check fails


Reporting Recovery Progress to External Systems
-----------------------------------------------

AIP recovery can be optionally configured to report progress to another system,
via a REST POST call, when an AIP recovery has been approved, rejected, or has
failed. The information sent includes the ID of the recover request, whether
the recovery request was processed successfully, and a text message including
the recover request status ("APPROVE" or "REJECT") and the administrator's
reasoning for the decision.

The following is an example of the JSON sent by this POST call:

::

    {
      "event_id": 127,
      "message": "APPROVE: Request approved, files look good.",
      "success": true
    }

To configure the storage service to report AIP restore progress to another
system, click "Administration" in the storage service administration web
interface and enter a REST endpoint URL into the "Recover request notification
url" field.

If the endpoint requires basic authentication, you'll also need to enter a
username and password into the two fields below it. Click "Save" when you're done.
