import django_filters
from rest_framework import routers, serializers, viewsets, filters
from rest_framework.decorators import list_route
from rest_framework.response import Response

from django.db.models import Sum

from locations import models


class CaseInsensitiveBooleanFilter(django_filters.Filter):
    """
    This allows users to query booleans without having to use "True" and "False"
    """
    def filter(self, qs, value):
        if value is not None:
            lc_value = value.lower()
            if lc_value == "true":
                value = True
            elif lc_value == "false":
                value = False
            return qs.filter(**{self.name: value})
        return qs


class PipelineField(serializers.RelatedField):
    """
    Used to show UUID of related pipelines
    """
    def to_representation(self, value):
        return value.uuid


class LocationSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize Location model data
    """
    space = serializers.ReadOnlyField(source='space.uuid')
    pipelines = PipelineField(many=True, read_only=True, source='pipeline')

    class Meta:
        model = models.Location
        fields = ('uuid', 'space', 'pipelines', 'purpose', 'quota', 'used', 'enabled')


class LocationFilter(django_filters.FilterSet):
    """
    Filter for searching Location data
    """
    uuid = django_filters.CharFilter(name='uuid')
    space = django_filters.CharFilter(name='space')
    purpose = django_filters.CharFilter(name='purpose')
    enabled = CaseInsensitiveBooleanFilter(name='enabled')

    class Meta:
        model = models.Location
        fields = ['uuid', 'space', 'purpose', 'enabled']


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Search API view for Location model data
    """
    queryset = models.Location.objects.all()
    serializer_class = LocationSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = LocationFilter


class PackageSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize Package model data
    """
    origin_pipeline = serializers.ReadOnlyField(source='origin_pipeline.uuid')
    current_location = serializers.ReadOnlyField(source='current_location.uuid')
    pointer_file_location = serializers.ReadOnlyField(source='pointer_file_location.uuid')

    class Meta:
        model = models.Package
        fields = ('uuid', 'current_path', 'size', 'origin_pipeline', 'current_location', 'package_type', 'status', 'pointer_file_location', 'pointer_file_path')


class PackageFilter(django_filters.FilterSet):
    """
    Filter for searching Package data
    """
    min_size = django_filters.NumberFilter(name='size', lookup_type='gte')
    max_size = django_filters.NumberFilter(name='size', lookup_type='lte')
    pipeline = django_filters.CharFilter(name='origin_pipeline')
    location = django_filters.CharFilter(name='current_location')
    package_type = django_filters.CharFilter(name='package_type')

    class Meta:
        model = models.Package
        fields = ['uuid', 'min_size', 'max_size', 'pipeline', 'location', 'package_type', 'status', 'pointer_file_location']


class PackageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Search API view for Package model data
    """
    queryset = models.Package.objects.all()
    serializer_class = PackageSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = PackageFilter


class FileSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize File model data
    """
    pipeline = serializers.ReadOnlyField(source='origin.uuid')

    class Meta:
        model = models.File
        fields = ('uuid', 'name', 'file_type', 'size', 'format_name', 'pronom_id', 'pipeline', 'source_package', 'normalized', 'validated', 'ingestion_time')


class FileFilter(django_filters.FilterSet):
    """
    Filter for searching File data
    """
    min_size = django_filters.NumberFilter(name='size', lookup_type='gte')
    max_size = django_filters.NumberFilter(name='size', lookup_type='lte')
    pipeline = django_filters.CharFilter(name='origin')
    package = django_filters.CharFilter(name='source_package')
    name = django_filters.CharFilter(name='name', lookup_type='icontains')
    normalized = CaseInsensitiveBooleanFilter(name='normalized')
    ingestion_time = django_filters.DateFilter(name='ingestion_time', lookup_type='contains')
    #ingestion_time_before = django_filters.DateFilter(name='ingestion_time', lookup_type='lt')
    #ingestion_time_after = django_filters.DateFilter(name='ingestion_time', lookup_type='gt')

    class Meta:
        model = models.File
        fields = ['uuid', 'name', 'file_type', 'min_size', 'max_size',
                  'format_name', 'pronom_id', 'pipeline', 'source_package',
                  'normalized', 'validated', 'ingestion_time']
                  #'ingestion_time_before', 'ingestion_time_after']


class FileViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Search API view for File model data

    Custom endpoint "stats" provides total size of files searched for
    """
    queryset = models.File.objects.all()
    serializer_class = FileSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = FileFilter

    @list_route(methods=['get'])
    def stats(self, request):
        filtered = FileFilter(request.GET, queryset=self.get_queryset())
        count = filtered.qs.count()
        summary = filtered.qs.aggregate(Sum('size'))
        return Response({'count': count, 'total_size': summary['size__sum']})


# Route location, package, and file search API requests
router = routers.DefaultRouter()
router.register(r'location', LocationViewSet)
router.register(r'package', PackageViewSet)
router.register(r'file', FileViewSet)
