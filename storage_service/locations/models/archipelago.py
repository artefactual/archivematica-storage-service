import requests
import logging
import subprocess
import os
import json
from .location import Location
from lxml import etree
from django.utils.translation import ugettext_lazy as _

# Core Django, alphabetical
from django.db import models

LOGGER = logging.getLogger(__name__)

class Archipelago(models.Model):
    """Integration with Archipelago using the REST API."""
    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    archipelago_url = models.URLField(
        max_length=256,
        verbose_name=_("Archipelago URL"),
        help_text=_("Archipelago URL"),
    )

    archipelago_user = models.CharField(
        max_length=64,
        verbose_name=_("Archipelago username"),
        help_text=_("Archiipelago username for authentication"),
    )

    archipelago_password = models.CharField(
        max_length=64,
        verbose_name=_("Archipelago password"),
        help_text=_("Archipelago password for authentication"),
    )

    class Meta:
        verbose_name = _("Archipelago via REST API")
        app_label = "locations"

    ALLOWED_LOCATION_PURPOSE = [Location.AIP_STORAGE, Location.DIP_STORAGE]

    def _upload_file(self,filename, source_path):
        url = self.archipelago_url+f'/jsonapi/node/aip/field_file_drop'
        headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': f'file; filename="{filename}"'
        }
        try:
            with open(source_path, 'rb') as file:
                response = requests.post(url, data=file, headers=headers, auth=(self.archipelago_user, self.archipelago_password))
                response.raise_for_status()

            if response.status_code == 201:
                LOGGER.info('AIP file uploaded successfully!')
                response_json = response.json()
                fid = response_json.get('data', {}).get('attributes', {}).get('drupal_internal__fid')
                return fid
            else:
                LOGGER.error(f'File upload failed with status code {response.status_code}: {response.text}')
        except (IOError, requests.exceptions.RequestException) as e:
            LOGGER.error("Error during AIP upload to archipelago", str(e))
    
    def extract_title_from_mets_xml(self, xml_string):
        try:
            root = etree.fromstring(xml_string)
            namespaces = {
                "mets": "http://www.loc.gov/METS/",
                "dc": "http://purl.org/dc/elements/1.1/",
                "dcterms": "http://purl.org/dc/terms/"
            }
            title_element = root.find(".//mets:dmdSec/mets:mdWrap/mets:xmlData/dcterms:dublincore/dc:title", namespaces=namespaces)
            if title_element is not None:
                return title_element.text.strip()
        except Exception as e:
            LOGGER.error("Error extracting title from METS XML:", str(e))
        return None

    def get_dc_metadata(self, xml_string):
        try:
            root = etree.fromstring(xml_string)
            namespaces = {
                "dc": "http://purl.org/dc/elements/1.1/",
            }
            dc_fields = {}
            for dc_element in root.findall(".//dc:*", namespaces=namespaces):
                field_name = dc_element.tag.split("}")[-1]
                if field_name == "title":
                    continue
                appended_field = "field_"+field_name
                field_value = dc_element.text.strip() if dc_element.text else None
                LOGGER.info(f"dc value added which is {field_value} where the field is {appended_field}")
                dc_fields[appended_field] = field_value
            strawberry = json.dumps(dc_fields)
            LOGGER.info(f"strawberry json is {strawberry}")
            return strawberry

        except Exception as e:
            LOGGER.error("Error extracting dc fields", str(e))
        return None

    @staticmethod
    def _get_mets_el(package_type, output_dir, input_path, dirname, aip_uuid):
        """Locate, extract (if necessary), XML-parse and return the METS file
        for this package.
        """
        if package_type == "AIP":
            relative_mets_path = os.path.join(
                dirname, "data", "METS." + str(aip_uuid) + ".xml"
            )
            mets_path = os.path.join(output_dir, relative_mets_path)
            command = [
                "unar",
                "-force-overwrite",
                "-o",
                output_dir,
                input_path,
                relative_mets_path,
            ]
            try:
                subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ).communicate()
                mets_el = etree.parse(mets_path)
                os.remove(mets_path)
                return mets_el
            except subprocess.CalledProcessError as err:
                raise Exception(
                    "Could not extract {} from {}: {}.".format(
                        mets_path, input_path, err
                    )
                )
        elif package_type == "DIP":
            for dip_file in os.listdir(input_path):
                if dip_file.startswith("METS") and dip_file.endswith(".xml"):
                    mets_path = os.path.join(input_path, dip_file)
                    return etree.parse(mets_path)

    def _get_metadata(self, input_path, aip_uuid, package_type):
        output_dir = os.path.dirname(input_path) + "/"
        dirname = os.path.splitext(os.path.basename(input_path))[0]
        mets_el = self._get_mets_el(package_type, output_dir, input_path, dirname, aip_uuid)
        return etree.tostring(mets_el)

    def _upload_metadata(self, fid, strawberry, title):
        LOGGER.info("uploading metadata")
        url = self.archipelago_url + f'/jsonapi/node/aip'
        archivematica_zip_link = {"label": title, "archivematica_zip": fid, #links new aip entity to uploaded zip file
            "ap:entitymapping": {
            "entity:file": [
                "archivematica_zip"
            ],
            "entity:node": [
                "ispartof",
                "ismemberof"
            ]
         },}
        headers = {
            'Content-Type': 'application/vnd.api+json'
        }
        strawberry_dict = json.loads(strawberry)
        combined_data = {**strawberry_dict, **archivematica_zip_link} #these are our strawberry field
        json_metadata = json.dumps(combined_data)
        request_data = {
            "data": {
                "type": "AIP",
                "attributes": {
                    "title": title,
                    "field_descriptive_metadata": json_metadata
                }
            }
        }
        json_data = json.dumps(request_data)
        try:
            response = requests.post(url, data=json_data, headers=headers, auth=(self.archipelago_user, self.archipelago_password))
            response.raise_for_status()

            if response.status_code == 201:
                LOGGER.info('AIP entity created successfully!')
            else:
                LOGGER.error(f'File upload failed with status code {response.status_code}: {response.text}')
        except (IOError, requests.exceptions.RequestException) as e:
            LOGGER.error("Error during AIP upload to archipelago", str(e))


    
    def move_from_storage_service(self, source_path, destination_path, package=None):
        """ Moves self.staging_path/src_path to dest_path. """
        if package is None:
            raise Exception("Archipelago requires package param.")
        LOGGER.info(
            "source_path: %s, destination_path: %s, package: %s",
            source_path,
            destination_path,
            package
        )
        field_uuid = package.uuid
        mets_xml = self._get_metadata(source_path, field_uuid, package_type="AIP")
        title = self.extract_title_from_mets_xml(mets_xml)
        filename = os.path.basename(source_path)
        if title is None: #use transfer name if title was not defined in metadata.
            parts = filename.split("-")
            if len(parts) < 2:
                title = "Default title for Archipelago AIP"
            else:
                title = parts[0] #splitting title from uuid
        try:
            fid = self._upload_file(filename, source_path)
            LOGGER.info(f"fid found to be {fid}")
            strawberry = self.get_dc_metadata(mets_xml) #getting other dublic core metadata fields
            if strawberry is not None:
                try:
                    self._upload_metadata(fid, strawberry, title)
                except:
                    LOGGER.error("could not upload metadata (make aip entity to archipelago): %s", str(e))
            else:
                LOGGER.info("strawberry was not found")
        except Exception as e:
            LOGGER.error("could not upload AIP file: %s", str(e))


    def browse(self, path):
        raise NotImplementedError("Archipelago does not implement browse")

    def delete_path(self, delete_path):
        raise NotImplementedError("Archipelago does not implement browse")

    def move_to_storage_service(self, src_path, dest_path, dest_space):
       raise NotImplementedError("Archipelago does not implement browse")
