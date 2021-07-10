from django.db import migrations, models
import locations.models.space
import django.core.validators
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [("locations", "0013_pipeline_local_rsync_daemon")]

    operations = [
        migrations.AlterField(
            model_name="arkivum",
            name="host",
            field=models.CharField(
                help_text="Hostname of the Arkivum web instance. Eg. arkivum.example.com:8443",
                max_length=256,
                verbose_name="Host",
            ),
        ),
        migrations.AlterField(
            model_name="arkivum",
            name="remote_name",
            field=models.CharField(
                help_text="Optional: Name or IP of the remote machine.",
                max_length=256,
                null=True,
                verbose_name="Remote name",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="arkivum",
            name="remote_user",
            field=models.CharField(
                help_text="Optional: Username on the remote machine accessible via passwordless ssh.",
                max_length=64,
                null=True,
                verbose_name="Remote user",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="callback",
            name="enabled",
            field=models.BooleanField(
                default=True,
                help_text="Enabled if this callback should be executed.",
                verbose_name="Enabled",
            ),
        ),
        migrations.AlterField(
            model_name="callback",
            name="event",
            field=models.CharField(
                help_text="Type of event when this callback should be executed.",
                max_length=15,
                verbose_name="Event",
                choices=[(b"post_store", b"Post-store")],
            ),
        ),
        migrations.AlterField(
            model_name="callback",
            name="expected_status",
            field=models.IntegerField(
                default=200,
                help_text="Expected HTTP response from the server, used to validate the callback response.",
                verbose_name="Expected Status",
            ),
        ),
        migrations.AlterField(
            model_name="callback",
            name="method",
            field=models.CharField(
                help_text="HTTP request method to use in connecting to the URL.",
                max_length=10,
                verbose_name="Method",
                choices=[
                    (b"delete", b"DELETE"),
                    (b"get", b"GET"),
                    (b"head", b"HEAD"),
                    (b"options", b"OPTIONS"),
                    (b"patch", b"PATCH"),
                    (b"post", b"POST"),
                    (b"put", b"PUT"),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="callback",
            name="uri",
            field=models.CharField(
                help_text="URL to contact upon callback execution.",
                max_length=1024,
                verbose_name="URI",
            ),
        ),
        migrations.AlterField(
            model_name="dataverse",
            name="agent_identifier",
            field=models.CharField(
                help_text="URI agent identifier for premis:agentIdentifierValue in Archivematica",
                max_length=256,
                verbose_name="Agent identifier",
            ),
        ),
        migrations.AlterField(
            model_name="dataverse",
            name="agent_name",
            field=models.CharField(
                help_text="Agent name for premis:agentName in Archivematica",
                max_length=50,
                verbose_name="Agent name",
            ),
        ),
        migrations.AlterField(
            model_name="dataverse",
            name="agent_type",
            field=models.CharField(
                help_text="Agent type for premis:agentType in Archivematica",
                max_length=50,
                verbose_name="Agent type",
            ),
        ),
        migrations.AlterField(
            model_name="dataverse",
            name="api_key",
            field=models.CharField(
                help_text="API key for Dataverse instance. Eg. b84d6b87-7b1e-4a30-a374-87191dbbbe2d",
                max_length=50,
                verbose_name="API key",
            ),
        ),
        migrations.AlterField(
            model_name="dataverse",
            name="host",
            field=models.CharField(
                help_text="Hostname of the Dataverse instance. Eg. apitest.dataverse.org",
                max_length=256,
                verbose_name="Host",
            ),
        ),
        migrations.AlterField(
            model_name="dspace",
            name="password",
            field=models.CharField(
                help_text="DSpace password to authenticate with",
                max_length=64,
                verbose_name="Password",
            ),
        ),
        migrations.AlterField(
            model_name="dspace",
            name="user",
            field=models.CharField(
                help_text="DSpace username to authenticate as",
                max_length=64,
                verbose_name="User",
            ),
        ),
        migrations.AlterField(
            model_name="duracloud",
            name="duraspace",
            field=models.CharField(
                help_text="Name of the Space within DuraCloud",
                max_length=64,
                verbose_name="Duraspace",
            ),
        ),
        migrations.AlterField(
            model_name="duracloud",
            name="host",
            field=models.CharField(
                help_text="Hostname of the DuraCloud instance. Eg. trial.duracloud.org",
                max_length=256,
                verbose_name="Host",
            ),
        ),
        migrations.AlterField(
            model_name="duracloud",
            name="password",
            field=models.CharField(
                help_text="Password to authenticate with",
                max_length=64,
                verbose_name="Password",
            ),
        ),
        migrations.AlterField(
            model_name="duracloud",
            name="user",
            field=models.CharField(
                help_text="Username to authenticate as",
                max_length=64,
                verbose_name="User",
            ),
        ),
        migrations.AlterField(
            model_name="fedora",
            name="fedora_name",
            field=models.CharField(
                help_text="Name or IP of the remote Fedora machine.",
                max_length=256,
                verbose_name="Fedora name",
            ),
        ),
        migrations.AlterField(
            model_name="fedora",
            name="fedora_password",
            field=models.CharField(
                help_text="Fedora password (for SWORD functionality)",
                max_length=256,
                verbose_name="Fedora password",
            ),
        ),
        migrations.AlterField(
            model_name="fedora",
            name="fedora_user",
            field=models.CharField(
                help_text="Fedora user name (for SWORD functionality)",
                max_length=64,
                verbose_name="Fedora user",
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="description",
            field=models.CharField(
                default=None,
                max_length=256,
                blank=True,
                help_text="Human-readable description.",
                null=True,
                verbose_name="Description",
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="enabled",
            field=models.BooleanField(
                default=True,
                help_text="True if space can be accessed.",
                verbose_name="Enabled",
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="pipeline",
            field=models.ManyToManyField(
                help_text="UUID of the Archivematica instance using this location.",
                to="locations.Pipeline",
                verbose_name="Pipeline",
                through="locations.LocationPipeline",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="purpose",
            field=models.CharField(
                help_text="Purpose of the space.  Eg. AIP storage, Transfer source",
                max_length=2,
                verbose_name="Purpose",
                choices=[
                    (b"AR", "AIP Recovery"),
                    (b"AS", "AIP Storage"),
                    (b"CP", "Currently Processing"),
                    (b"DS", "DIP Storage"),
                    (b"SD", "FEDORA Deposits"),
                    (b"SS", "Storage Service Internal Processing"),
                    (b"BL", "Transfer Backlog"),
                    (b"TS", "Transfer Source"),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="quota",
            field=models.BigIntegerField(
                default=None,
                help_text="Size, in bytes (optional)",
                null=True,
                verbose_name="Quota",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="relative_path",
            field=models.TextField(
                help_text="Path to location, relative to the storage space's path.",
                verbose_name="Relative Path",
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="used",
            field=models.BigIntegerField(
                default=0, help_text="Amount used, in bytes.", verbose_name="Used"
            ),
        ),
        migrations.AlterField(
            model_name="nfs",
            name="manually_mounted",
            field=models.BooleanField(default=False, verbose_name="Manually mounted"),
        ),
        migrations.AlterField(
            model_name="nfs",
            name="remote_name",
            field=models.CharField(
                help_text="Name of the NFS server.",
                max_length=256,
                verbose_name="Remote name",
            ),
        ),
        migrations.AlterField(
            model_name="nfs",
            name="remote_path",
            field=models.TextField(
                help_text="Path on the NFS server to the export.",
                verbose_name="Remote path",
            ),
        ),
        migrations.AlterField(
            model_name="nfs",
            name="version",
            field=models.CharField(
                default=b"nfs4",
                help_text="Type of the filesystem, i.e. nfs, or nfs4.         Should match a command in `mount`.",
                max_length=64,
                verbose_name="Version",
            ),
        ),
        migrations.AlterField(
            model_name="pipeline",
            name="api_key",
            field=models.CharField(
                default=None,
                max_length=256,
                blank=True,
                help_text="API key to use when making API calls to the pipeline.",
                null=True,
                verbose_name="API key",
            ),
        ),
        migrations.AlterField(
            model_name="pipeline",
            name="api_username",
            field=models.CharField(
                default=None,
                max_length=256,
                blank=True,
                help_text="Username to use when making API calls to the pipeline.",
                null=True,
                verbose_name="API username",
            ),
        ),
        migrations.AlterField(
            model_name="pipeline",
            name="description",
            field=models.CharField(
                default=None,
                max_length=256,
                blank=True,
                help_text="Human readable description of the Archivematica instance.",
                null=True,
                verbose_name="Description",
            ),
        ),
        migrations.AlterField(
            model_name="pipeline",
            name="enabled",
            field=models.BooleanField(
                default=True,
                help_text="Enabled if this pipeline is able to access the storage service.",
                verbose_name="Enabled",
            ),
        ),
        migrations.AlterField(
            model_name="pipeline",
            name="remote_name",
            field=models.CharField(
                default=None,
                max_length=256,
                blank=True,
                help_text="Host or IP address of the pipeline server for making API calls.",
                null=True,
                verbose_name="Remote name",
            ),
        ),
        migrations.AlterField(
            model_name="pipeline",
            name="uuid",
            field=django_extensions.db.fields.UUIDField(
                auto=False,
                validators=[
                    django.core.validators.RegexValidator(
                        b"\\w{8}-\\w{4}-\\w{4}-\\w{4}-\\w{12}",
                        "Needs to be format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx where x is a hexadecimal digit.",
                        "Invalid UUID",
                    )
                ],
                help_text="Identifier for the Archivematica pipeline",
                unique=True,
                verbose_name="UUID",
            ),
        ),
        migrations.AlterField(
            model_name="pipelinelocalfs",
            name="remote_name",
            field=models.CharField(
                help_text="Name or IP of the remote machine.",
                max_length=256,
                verbose_name="Remote name",
            ),
        ),
        migrations.AlterField(
            model_name="pipelinelocalfs",
            name="remote_user",
            field=models.CharField(
                help_text="Username on the remote machine accessible via ssh",
                max_length=64,
                verbose_name="Remote user",
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                help_text="How the space can be accessed.",
                max_length=8,
                verbose_name="Access protocol",
                choices=[
                    (b"ARKIVUM", "Arkivum"),
                    (b"DV", "Dataverse"),
                    (b"DC", "DuraCloud"),
                    (b"DSPACE", "DSpace via SWORD2 API"),
                    (b"FEDORA", "FEDORA via SWORD2"),
                    (b"FS", "Local Filesystem"),
                    (b"LOM", "LOCKSS-o-matic"),
                    (b"NFS", "NFS"),
                    (b"PIPE_FS", "Pipeline Local Filesystem"),
                    (b"SWIFT", "Swift"),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="last_verified",
            field=models.DateTimeField(
                default=None,
                help_text="Time this location was last verified to be accessible.",
                null=True,
                verbose_name="Last verified",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="path",
            field=models.TextField(
                default=b"",
                help_text="Absolute path to the space on the storage service machine.",
                verbose_name="Path",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="size",
            field=models.BigIntegerField(
                default=None,
                help_text="Size in bytes (optional)",
                null=True,
                verbose_name="Size",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="staging_path",
            field=models.TextField(
                help_text="Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.",
                verbose_name="Staging path",
                validators=[locations.models.space.validate_space_path],
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="used",
            field=models.BigIntegerField(
                default=0, help_text="Amount used in bytes", verbose_name="Used"
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="verified",
            field=models.BooleanField(
                default=False,
                help_text="Whether or not the space has been verified to be accessible.",
                verbose_name="Verified",
            ),
        ),
        migrations.AlterField(
            model_name="swift",
            name="auth_url",
            field=models.CharField(
                help_text="URL to authenticate against",
                max_length=256,
                verbose_name="Auth URL",
            ),
        ),
        migrations.AlterField(
            model_name="swift",
            name="auth_version",
            field=models.CharField(
                default=b"2",
                help_text="OpenStack auth version",
                max_length=8,
                verbose_name="Auth version",
            ),
        ),
        migrations.AlterField(
            model_name="swift",
            name="container",
            field=models.CharField(max_length=64, verbose_name="Container"),
        ),
        migrations.AlterField(
            model_name="swift",
            name="password",
            field=models.CharField(
                help_text="Password to authenticate with",
                max_length=256,
                verbose_name="Password",
            ),
        ),
        migrations.AlterField(
            model_name="swift",
            name="region",
            field=models.CharField(
                help_text="Optional: Region in Swift",
                max_length=64,
                null=True,
                verbose_name="Region",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="swift",
            name="tenant",
            field=models.CharField(
                help_text="The tenant/account name, required when connecting to an auth 2.0 system.",
                max_length=64,
                null=True,
                verbose_name="Tenant",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="swift",
            name="username",
            field=models.CharField(
                help_text="Username to authenticate as. E.g. http://example.com:5000/v2.0/",
                max_length=64,
                verbose_name="Username",
            ),
        ),
    ]
