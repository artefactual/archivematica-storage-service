import requests
import logging
import subprocess
import os
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

    def _make_aip_entity(self,field_uuid, title, dc_fields=None):
        url = self.archipelago_url+'/jsonapi/node/aip'
        headers = {
            'Content-Type': 'application/vnd.api+json'
        }
        payload = {
            'data': {
                'type': 'aip',
                'attributes': {
                    'field_uuid': field_uuid,
                    'title': title
                }
            }
        }

        if dc_fields:
            LOGGER.info('Adding DC fields')
            payload['data']['attributes'].update(dc_fields)
        try:
            response = requests.post(url, json=payload, headers=headers, auth=(self.archipelago_user, self.archipelago_password))
            response.raise_for_status()
            if response.status_code == 201:
                LOGGER.info('Made the AIP entity')
            else:
                LOGGER.error(f'Request returned status code {response.status_code}: {response.text}')
        except requests.exceptions.RequestException as e:
            LOGGER.info('An error occurred while sending the request:', str(e))

    def _get_entity_id(self,field_uuid):
        url = self.archipelago_url+'/jsonapi/node/aip'
        headers = {
            'Content-Type': 'application/vnd.api+json'
        }
        params = {
            'filter[field_uuid.value]': field_uuid
        }

        try:
            response = requests.get(url, headers=headers, params=params, auth=(self.archipelago_user, self.archipelago_password))
            response.raise_for_status()
            response_json = response.json()
            if response.status_code == 200 and 'data' in response_json:
                data = response_json['data']
                if len(data) > 0:
                    return data[0]['id']
            else:
                LOGGER.error("No id found for uuid " + field_uuid)
                return None
        except requests.exceptions.RequestException as e:
            LOGGER.error('Error occurred when getting entity ID from archipelago:', str(e))
            return None

    def _upload_AIP(self,filename, source_path, entity_id):
        if entity_id is not None:
            url = self.archipelago_url+f'/jsonapi/node/aip/{entity_id}/field_zip_file'
            headers = {
                'Content-Type': 'application/octet-stream',
                'Content-Disposition': f'file; filename="{filename}"'
        }
        try:
            with open(source_path, 'rb') as file:
                response = requests.post(url, data=file, headers=headers, auth=(self.archipelago_user, self.archipelago_password))
                response.raise_for_status()

            if response.status_code == 200:
                LOGGER.info('AIP file uploaded successfully!')
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
                dc_fields[appended_field] = field_value
            return dc_fields

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
                dirname, "data", "METS." + aip_uuid + ".xml"
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

        LOGGER.info("About to make AIP entity")
        try:
            dc_fields = self.get_dc_metadata(mets_xml) #getting other dublic core metadata fields
            if dc_fields is not None:
                self._make_aip_entity(field_uuid, title, dc_fields)
            else:
                self._make_aip_entity(field_uuid, title)
            LOGGER.info("Made AIP entity")
            LOGGER.info("Field uuid is "+field_uuid+" and title is "+title)
            try:
                entity_id = self._get_entity_id(field_uuid)
                LOGGER.info("entity ID was found to be "+entity_id)
                try:
                    self._upload_AIP(filename, source_path, entity_id)
                except:
                    LOGGER.error("Error while uploading AIP: %s", str(e))
            except Exception as e:
                LOGGER.error("Error while getting entity ID: %s", str(e))
        except Exception as e:
            LOGGER.error("Error while making AIP entity: %s", str(e))


    def browse(self, path):
        raise NotImplementedError("Archipelago does not implement browse")

    def delete_path(self, delete_path):
        raise NotImplementedError("Archipelago does not implement browse")

    def move_to_storage_service(self, src_path, dest_path, dest_space):
       raise NotImplementedError("Archipelago does not implement browse")
