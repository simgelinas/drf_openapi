from rest_framework.compat import coreschema
from django.utils.encoding import force_text
from rest_framework import serializers
from collections import OrderedDict
# from utils import Definition
from codec import parse_nested_field


class Definition(object):
    def __init__(self, schema_object, sub_defs):
        self._schema_object = schema_object
        self._sub_defs = sub_defs

    @property
    def schema_object(self):
        return self._schema_object

    @property
    def sub_defs(self):
        return self._sub_defs


def create_serializer_schema(field, definitions, title, description, allow_update_definitions):
    new_def_name = '_'.join([field.__class__.__module__.replace('.', '_'), field.__class__.__name__])
    sub_definitions = {}
    schema = coreschema.Object(
                properties=OrderedDict([
                    (key, field_to_schema(value, definitions, allow_update_definitions))
                    for key, value
                    in field.fields.items()
                ]),
                required=[field_name for field_name, field_data in field.fields.items() if
                          getattr(field_data, 'required', True) is True],
                title=title,
                description=description
            )

    # To be clear, this should never happen, keeping in as a check for now
    for sub_def_name, sub_def in sub_definitions.items():
        if sub_def_name in definitions:
            nested_field_existing = parse_nested_field(definitions[sub_def_name])
            nested_field_new = parse_nested_field(sub_def)
            if nested_field_existing != nested_field_new:
                raise Exception('Sub def not matching, how did this happen?')
        else:
            raise Exception('How is sub def not already in dict')

    return_ref = True

    if new_def_name in definitions:
        if definitions[new_def_name] is None:
            return_ref = False
        else:
            nested_field_existing = parse_nested_field(definitions[new_def_name].schema_object)
            nested_field_new = parse_nested_field(schema)
            if nested_field_existing != nested_field_new:
                for old_def_name in definitions.keys():
                    old_def = definitions[old_def_name]
                    if new_def_name in old_def.sub_defs:
                        new_properties = {}
                        for k, v in old_def.schema_object.properties.items():
                            if isinstance(v, coreschema.Ref) and v.ref == new_def_name:
                                new_properties[k] = schema
                            else:
                                new_properties[k] = v
                        new_schema = coreschema.Object(
                            properties=OrderedDict(new_properties),
                            required=old_def.schema_object.required,
                            title=old_def.schema_object.title,
                            description=old_def.schema_object.description)
                        new_sub_defs = set(old_def.sub_defs)
                        new_sub_defs.remove(new_def_name)
                        definitions[old_def_name] = Definition(new_schema, new_sub_defs)
                definitions[new_def_name] = None
                return_ref = False
    else:
        if allow_update_definitions:
            definitions[new_def_name] = Definition(schema, set(sub_definitions.keys()))
        else:
            return_ref = False

    if not return_ref:
        return schema
    else:
        return coreschema.Ref(new_def_name)


def field_to_schema(field, definitions, allow_update_definitions):
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
            child_schema = field_to_schema(child_class.child, definitions, allow_update_definitions)
        else:
            child_schema = field_to_schema(field.child, definitions, allow_update_definitions)
        return coreschema.Array(
            items=child_schema,
            title=title,
            description=description
        )
    elif isinstance(field, serializers.Serializer):
        return create_serializer_schema(field, definitions, title, description, allow_update_definitions)
    elif isinstance(field, serializers.DictField):
        return coreschema.Object(title=title,
                                 description=description,
                                 additional_properties=field_to_schema(field.child, definitions, allow_update_definitions))
    elif isinstance(field, serializers.SerializerMethodField) and hasattr(field, 'method_output_type'):
        return field_to_schema(field.method_output_type, definitions, allow_update_definitions)
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
