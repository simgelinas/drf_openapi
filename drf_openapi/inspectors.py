from rest_framework.compat import coreschema
from django.utils.encoding import force_text
from rest_framework import serializers
from collections import OrderedDict


def field_to_schema(field):
    title = force_text(field.label) if field.label else ''
    description = force_text(field.help_text) if field.help_text else ''

    if isinstance(field, (serializers.ListSerializer, serializers.ListField)):
        # If it's a nested list of lists - find the nested non-list object
        if isinstance(field.child.__class__(), (serializers.ListSerializer, serializers.ListField)):
            array_dimensions = 2
            child_class = field.child.__class__()
            while isinstance(child_class.child.__class__(),
                             (serializers.ListSerializer, serializers.ListField)):
                array_dimensions += 1
                child_class = child_class.child.__class__()

            description = '{}D Array'.format(array_dimensions) + description
            child_schema = field_to_schema(child_class.child)
        else:
            child_schema = field_to_schema(field.child)
        return coreschema.Array(
            items=child_schema,
            title=title,
            description=description
        )
    elif isinstance(field, serializers.Serializer):
        return coreschema.Object(
            properties=OrderedDict([
                (key, field_to_schema(value))
                for key, value
                in field.fields.items()
            ]),
            required=[field_name for field_name, field_data in field.fields.items() if
                      getattr(field_data, 'required', True) is True],
            title=title,
            description=description
        )
    elif isinstance(field, serializers.ManyRelatedField):
        return coreschema.Array(
            items=coreschema.String(),
            title=title,
            description=description
        )
    elif isinstance(field, serializers.RelatedField):
        return coreschema.String(title=title, description=description)
    elif isinstance(field, serializers.MultipleChoiceField):
        return coreschema.Array(
            items=coreschema.Enum(enum=list(field.choices.keys())),
            title=title,
            description=description
        )
    elif isinstance(field, serializers.ChoiceField):
        return coreschema.Enum(
            enum=list(field.choices.keys()),
            title=title,
            description=description
        )
    elif isinstance(field, serializers.BooleanField):
        return coreschema.Boolean(title=title, description=description)
    elif isinstance(field, (serializers.DecimalField, serializers.FloatField)):
        return coreschema.Number(title=title, description=description)
    elif isinstance(field, serializers.IntegerField):
        return coreschema.Integer(title=title, description=description)
    elif isinstance(field, serializers.DateField):
        return coreschema.String(
            title=title,
            description=description,
            format='date'
        )
    elif isinstance(field, serializers.DateTimeField):
        return coreschema.String(
            title=title,
            description=description,
            format='date-time'
        )

    if field.style.get('base_template') == 'textarea.html':
        return coreschema.String(
            title=title,
            description=description,
            format='textarea'
        )
    return coreschema.String(title=title, description=description)
