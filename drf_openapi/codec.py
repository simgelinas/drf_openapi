# coding=utf-8
"""Adapted from https://github.com/core-api/python-openapi-codec/blob/master/openapi_codec/encode.py
and https://github.com/marcgibbons/django-rest-swagger/blob/master/rest_framework_swagger/renderers.py
"""
import json
from collections import OrderedDict

import coreschema
from coreapi import Document
from coreapi.compat import urlparse, force_bytes
from openapi_codec import OpenAPICodec as _OpenAPICodec
from openapi_codec.encode import _get_links, _get_field_description
from openapi_codec.utils import get_method, get_encoding, get_location
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework_swagger.renderers import OpenAPIRenderer as _OpenAPIRenderer, \
    SwaggerUIRenderer as _SwaggerUIRenderer


def _get_field_required(field):
    return getattr(field, 'required', True)


def parse_nested_field(nested_field):
    items_type = _get_field_type(nested_field)

    result = {
        'description': _get_field_description(nested_field),
        'type': items_type
    }

    if items_type == 'array':
        if hasattr(nested_field, 'schema'):
            items = nested_field.schema.items
        else:
            items = nested_field.items

        result['items'] = {'type': _get_field_type(items)}
        if hasattr(items, 'properties'):
            result['items']['properties'] = {name: parse_nested_field(prop) for name, prop in items.properties.items()}
            result['items']['required'] = items.required
        # else:
        #     result['items']['properties'] = {nested_field.name: parse_nested_field(items)}
    elif items_type == 'object':
        if hasattr(nested_field, 'schema'):
            result['properties'] = {
                name: parse_nested_field(prop) for name, prop in nested_field.schema.properties.items()
            }
            result['required'] = nested_field.schema.required
        elif hasattr(nested_field, 'properties'):
            result['properties'] = {
                name: parse_nested_field(prop) for name, prop in nested_field.properties.items()
            }
            result['required'] = nested_field.required
    elif items_type == 'enum':
        result['type'] = 'string'
        result['enum'] = nested_field.enum

    else:
        if hasattr(nested_field, 'name'):
            result['name'] = nested_field.name
    return result


class OpenApiFieldParser:

    def __init__(self, link, field):
        self.field = field
        self.field_description = _get_field_description(field)
        self.field_type = _get_field_type(field)
        self.field_required = _get_field_required(field)
        self.location = get_location(link, field)

    @property
    def location_string(self):
        return 'formData' if self.location == 'form' else self.location

    def as_parameter(self):
        if (self.field_type == 'object' and self.location_string != 'query') or self.field_type == 'array':
            param = parse_nested_field(self.field)
        elif self.field_type  == 'enum':
            # CoreApi and OpenApi don't handle Enum the same way (field property vs field type)
            param = {
                'name': self.field.name,
                'required': self.field_required,
                'description': self.field_description,
                'type': 'string',
                'enum': self.field.schema.enum,
            }
        else:
            param = {
                'name': self.field.name,
                'required': self.field_required,
                'description': self.field_description,
                'type': self.field_type
            }

        param['in'] = self.location_string
        return param

    def as_body_parameter(self, encoding):
        if encoding == 'application/octet-stream':
            # https://github.com/OAI/OpenAPI-Specification/issues/50#issuecomment-112063782
            schema = {'type': 'string', 'format': 'binary'}
        else:
            schema = {}

        param = self.as_parameter()
        param['schema'] = schema
        return param

    def as_schema_property(self):
        if self.field_type in ('object', 'array'):
            return parse_nested_field(self.field)
        elif self.field_type == 'enum':
            return {
                'description': self.field_description,
                'type': 'string',
                'enum': self.field.schema.enum,
                'required': self.field_required,
            }
        return {
            'description': self.field_description,
            'type': self.field_type,
            'required': self.field_required,
        }


class OpenAPICodec(_OpenAPICodec):
    def encode(self, document, extra=None, **options):
        if not isinstance(document, Document):
            raise TypeError('Expected a `coreapi.Document` instance')

        data = _generate_openapi_object(document)
        if isinstance(extra, dict):
            data.update(extra)

        return force_bytes(json.dumps(data))


class OpenAPIRenderer(_OpenAPIRenderer):

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if renderer_context['response'].status_code != status.HTTP_200_OK:
            return JSONRenderer().render(data)
        extra = self.get_customizations()

        return OpenAPICodec().encode(data, extra=extra)


class SwaggerUIRenderer(_SwaggerUIRenderer):
    template = 'drf_openapi/index.html'


def _generate_openapi_object(document):
    """
    Generates root of the Swagger spec.
    """
    parsed_url = urlparse.urlparse(document.url)

    swagger = OrderedDict()

    swagger['swagger'] = '2.0'
    swagger['info'] = OrderedDict()
    swagger['info']['title'] = document.title
    swagger['info']['description'] = document.description
    swagger['info']['version'] = document.version

    if parsed_url.netloc:
        swagger['host'] = parsed_url.netloc
    if parsed_url.scheme:
        swagger['schemes'] = [parsed_url.scheme]

    swagger['paths'] = _get_paths_object(document)

    return swagger


def _get_paths_object(document):
    paths = OrderedDict()

    links = _get_links(document)

    for operation_id, link, tags in links:
        if link.url not in paths:
            paths[link.url] = OrderedDict()

        method = get_method(link)
        operation = _get_operation(operation_id, link, tags)
        paths[link.url].update({method: operation})

    return paths


def _get_operation(operation_id, link, tags):
    encoding = get_encoding(link)
    description = link.description.strip()
    # summary = description.splitlines()[0] if description else None
    summary = link.url

    operation = {
        'operationId': operation_id,
        'responses': _get_responses(link),
        'parameters': _get_parameters(link, encoding)
    }

    if description:
        operation['description'] = description
    if summary:
        operation['summary'] = summary
    if encoding:
        operation['consumes'] = [encoding]
    if tags:
        operation['tags'] = tags
    return operation


def _get_responses(link):
    """ Returns an OpenApi-compliant response
    """
    template = link.response_schema
    template.update({'description': 'Success'})
    res = {200: template}
    res.update(link.error_status_codes)
    return res


def _get_field_type(field):
    type_name_map = {
        coreschema.String: 'string',
        coreschema.Integer: 'integer',
        coreschema.Number: 'number',
        coreschema.Boolean: 'boolean',
        coreschema.Array: 'array',
        coreschema.Object: 'object',
        coreschema.Enum: 'enum',
    }

    if getattr(field, 'type', None) is not None:
        # Deprecated
        return field.type

    if field.__class__ in type_name_map:
        return type_name_map[field.__class__]

    if getattr(field, 'schema', None) is None:
        return 'string'

    return type_name_map.get(field.schema.__class__, 'string')


def _get_parameters(link, encoding):
    """
    Generates Swagger Parameter Item object.
    """
    parameters = []
    properties = {}
    required = []

    for field in link.fields:
        parser = OpenApiFieldParser(link, field)
        if parser.location == 'form':
            if encoding in ('multipart/form-data', 'application/x-www-form-urlencoded'):
                # 'formData' in swagger MUST be one of these media types.
                parameters.append(parser.as_parameter())
            else:
                # Expand coreapi fields with location='form' into a single swagger
                # parameter, with a schema containing multiple properties.
                properties[field.name] = parser.as_schema_property()
                if field.required:
                    required.append(field.name)
        elif parser.location == 'body':
            parameters.append(parser.as_body_parameter(encoding))
        else:
            parameters.append(parser.as_parameter())

    if properties:
        parameter = {
            'name': 'data',
            'in': 'body',
            'schema': {
                'type': 'object',
                'properties': properties
            }
        }
        if required:
            parameter['schema']['required'] = required
        parameters.append(parameter)

    return parameters
