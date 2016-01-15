from collections import OrderedDict

from django.utils.functional import cached_property
from rest_framework.fields import empty
from rest_framework.relations import RelatedField, ManyRelatedField, HyperlinkedRelatedField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework.serializers import ModelSerializer, HyperlinkedModelSerializer, BaseSerializer
from drf_nested_fields.serializers import NestedFieldsSerializerMixin

from drf_hal_json import LINKS_FIELD_NAME, EMBEDDED_FIELD_NAME


class HalEmbeddedSerializer(NestedFieldsSerializerMixin, ModelSerializer):
    pass


class HalModelSerializer(NestedFieldsSerializerMixin, ModelSerializer):
    """
    Serializer for HAL representation of django models
    """
    serializer_related_field = HyperlinkedRelatedField
    links_serializer_class = HyperlinkedModelSerializer
    embedded_serializer_class = HalEmbeddedSerializer

    def __init__(self, instance=None, data=empty, **kwargs):
        super(HalModelSerializer, self).__init__(instance, data, **kwargs)
        self.nested_serializer_class = self.__class__
        if data != empty and not LINKS_FIELD_NAME in data:
            data[LINKS_FIELD_NAME] = dict()  # put links in data, so that field validation does not fail

    def get_default_field_names(self, declared_fields, model_info):
        """
        Return the default list of field names that will be used if the
        `Meta.fields` option is not specified.
        """
        return (
            [self.url_field_name] +
            list(declared_fields.keys()) +
            list(model_info.fields.keys()) +
            list(model_info.forward_relations.keys())
        )

    def get_fields(self):
        fields = super(HalModelSerializer, self).get_fields()

        embedded_fields = dict()
        link_fields = dict()
        resulting_fields = OrderedDict()
        resulting_fields[LINKS_FIELD_NAME] = None  # assign it here because of the order -> links first

        for field_name, field in fields.items():
            if self._is_link_field(field):
                link_fields.update({field_name: field})
            elif self._is_embedded_field(field):
                embedded_fields.update({field_name: field})
            else:
                resulting_fields[field_name] = field

        links_serializer = self._get_links_serializer(self.Meta.model, link_fields)
        if not links_serializer:
            # in case the class is overridden and the inheriting class wants no links to be serialized, the links field is removed
            del resulting_fields[LINKS_FIELD_NAME]
        else:
            resulting_fields[LINKS_FIELD_NAME] = links_serializer
        if embedded_fields:
            resulting_fields[EMBEDDED_FIELD_NAME] = self._get_embedded_serializer(self.Meta.model, getattr(self.Meta, "depth", 0),
                                                                                  embedded_fields)
        return resulting_fields

    def _get_links_serializer(self, model_cls, link_fields):
        class HalNestedLinksSerializer(self.links_serializer_class):
            serializer_related_field = self.serializer_related_field
            serializer_url_field = self.serializer_url_field

            class Meta:
                model = model_cls

            def get_fields(self):
                return link_fields

        return HalNestedLinksSerializer(instance=self.instance, source="*")

    def _get_embedded_serializer(self, model_cls, embedded_depth, embedded_fields):
        defined_nested_fields = getattr(self.Meta, "nested_fields", None)
        nested_class = self.__class__

        embedded_field_names = list(embedded_fields.keys())

        class HalNestedEmbeddedSerializer(self.embedded_serializer_class):
            nested_serializer_class = nested_class

            class Meta:
                model = model_cls
                fields = embedded_field_names
                nested_fields = defined_nested_fields
                depth = embedded_depth

            def get_fields(self):
                return embedded_fields

        return HalNestedEmbeddedSerializer(source="*")

    @staticmethod
    def _is_link_field(field):
        return isinstance(field, RelatedField) or isinstance(field, ManyRelatedField) \
               or isinstance(field, HyperlinkedIdentityField)

    @staticmethod
    def _is_embedded_field(field):
        return isinstance(field, BaseSerializer)

    @cached_property
    def _writable_fields(self):
        return super()._writable_fields + [
            field for field in self.fields[LINKS_FIELD_NAME].fields.values()
            if (not field.read_only) or (field.default is not empty)
            ]

